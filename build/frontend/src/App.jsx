import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, connectLiveEvents } from "./api";
import Header from "./components/Header";
import LogisticsPanel from "./components/LogisticsPanel";
import DeviceSidebar from "./components/DeviceSidebar";
import DigitalTwinTabs from "./components/DigitalTwinTabs";
import PropertiesPanel from "./components/PropertiesPanel";
import EventStream from "./components/EventStream";
import { overlapsAny, clampBoxToBounds } from "./lib/geometry";

const EMPTY_STATS = { itemsStored: 0, pendingJobs: 0, devicesOnline: 0, devicesOffline: 0, mode: "mock" };

let lineId = 0;
function nextId() {
  lineId += 1;
  return lineId;
}

function timeNow() {
  return new Date().toLocaleTimeString();
}

export default function App() {
  const [racks, setRacks] = useState([]);
  const [zones, setZones] = useState([]);
  const [devices, setDevices] = useState([]);
  const [gateways, setGateways] = useState([]);
  const [occupancy, setOccupancy] = useState({});
  const [stats, setStats] = useState(EMPTY_STATS);
  const [wsConnected, setWsConnected] = useState(false);
  const [mqttConnected, setMqttConnected] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [dragOverZoneId, setDragOverZoneId] = useState(null);
  const [lines, setLines] = useState([]);
  const [busy, setBusy] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [banner, setBanner] = useState(null);
  const [activeTab, setActiveTab] = useState("mapping");
  const [activeJobs, setActiveJobs] = useState([]);
  const [pickList, setPickList] = useState([]);
  const [mode, setModeState] = useState("mock");
  const [ollamaReachable, setOllamaReachable] = useState(false);
  const [workers, setWorkers] = useState([]);
  const [systemConfig, setSystemConfig] = useState(null);

  const pushLine = useCallback((level, tag, message) => {
    setLines((cur) => [...cur.slice(-199), { id: nextId(), time: timeNow(), level, tag, message }]);
  }, []);

  const refreshLayout = useCallback(async () => {
    try {
      const layout = await api.getLayout();
      setRacks(layout.racks || []);
      setZones(layout.zones || []);
      setDevices(layout.zoneModules || []);
      setGateways(layout.gateways || []);
    } catch (err) {
      pushLine("error", "ERROR", `Failed to load layout: ${err.message}`);
    }
  }, [pushLine]);

  const refreshOccupancy = useCallback(async () => {
    try {
      const occ = await api.getZoneOccupancy();
      setOccupancy(occ || {});
    } catch {
      /* non-fatal */
    }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      const s = await api.getStats();
      setStats(s);
    } catch {
      /* non-fatal */
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.getHealth();
      setMqttConnected(!!h.mqttConnected);
    } catch {
      setMqttConnected(false);
    }
  }, []);

  const refreshMode = useCallback(async () => {
    try {
      const m = await api.getMode();
      setModeState(m.mode);
      setMqttConnected(!!m.mqttConnected);
      setOllamaReachable(!!m.ollamaReachable);
    } catch {
      /* non-fatal */
    }
  }, []);

  async function handleSetMode(nextMode) {
    try {
      await api.setMode(nextMode);
      pushLine("system", "SYSTEM", `Operating mode switched to ${nextMode.toUpperCase()}.`);
      await refreshMode();
    } catch (err) {
      pushLine("error", "ERROR", `Could not switch mode: ${err.message}`);
    }
  }

  useEffect(() => {
    refreshLayout();
    refreshOccupancy();
    refreshStats();
    refreshHealth();
    refreshMode();
    api.getWorkers().then(setWorkers).catch(() => {});
    api.getSystemConfig().then(setSystemConfig).catch(() => {});
    pushLine("system", "SYSTEM", "Digital Twin dashboard connected to backend API.");

    const poll = setInterval(() => {
      refreshStats();
      refreshHealth();
      refreshMode();
    }, 8000);

    const disconnect = connectLiveEvents(handleEvent, setWsConnected);
    return () => {
      clearInterval(poll);
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleEvent(evt) {
    if (evt.type === "job_queued") {
      const verb = evt.jobType === "STORE" ? "INBOUND QUEUED" : "OUTBOUND QUEUED";
      const capacityTxt = evt.capacity ? ` (${evt.capacity})` : "";
      pushLine(
        "queued",
        verb,
        `Box [${evt.boxId}] ${evt.jobType === "STORE" ? "headed to" : "picking from"} ${evt.zoneName || evt.zoneId}${capacityTxt}. LED (ON) activated.`
      );
      setActiveJobs((cur) => [...cur, { boxId: evt.boxId, jobType: evt.jobType, zoneId: evt.zoneId, zoneName: evt.zoneName, queuedAt: Date.now() }]);
      refreshStats();
    } else if (evt.type === "job_done") {
      const remaining = evt.jobType === "STORE" ? `Remaining capacity: ${evt.capacity}.` : `Zone now ${evt.capacity || "0/0"}.`;
      pushLine("done", "PROCESS DONE", `Box [${evt.boxId}] ${evt.jobType === "STORE" ? "stored in" : "fully picked from"} ${evt.zoneName || evt.zoneId}. ${remaining}`);
      setActiveJobs((cur) => cur.filter((j) => !(j.boxId === evt.boxId && j.jobType === evt.jobType)));
      refreshStats();
      refreshOccupancy();
    } else if (evt.type === "job_failed") {
      pushLine("error", "ERROR", `${evt.jobType} for box [${evt.boxId}] failed: ${evt.reason}`);
      setActiveJobs((cur) => cur.filter((j) => !(j.boxId === evt.boxId && j.jobType === evt.jobType)));
      refreshStats();
    } else if (evt.type === "gateway_heartbeat") {
      refreshLayout();
    } else if (evt.type === "mqtt_status") {
      setMqttConnected(!!evt.connected);
    } else if (evt.type === "node_discovered" || evt.type === "topology_report") {
      refreshLayout();
    }
  }

  async function handleStore(boxId, zoneId) {
    setBusy(true);
    try {
      await api.inboundStore(boxId, zoneId);
    } catch (err) {
      pushLine("error", "ERROR", `Store request for [${boxId}] rejected: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleBuildPickList(boxIds) {
    try {
      const items = await api.buildPickList(boxIds);
      setPickList(items);
      const foundCount = items.filter((i) => i.found).length;
      pushLine(
        "system",
        "PICK LIST",
        `Route built: ${foundCount}/${items.length} box(es) located. Matching zone LEDs are now ON.`
      );
      await refreshOccupancy();
    } catch (err) {
      pushLine("error", "ERROR", `Could not build pick list: ${err.message}`);
    }
  }

  async function handleConfirmPickItem(boxId) {
    try {
      await api.confirmPick(boxId);
      setPickList((cur) => cur.filter((i) => i.boxId !== boxId));
      pushLine("done", "PICKED", `Box [${boxId}] confirmed picked and removed from the route.`);
      await refreshOccupancy();
      await refreshStats();
    } catch (err) {
      pushLine("error", "ERROR", `Could not confirm pick for [${boxId}]: ${err.message}`);
    }
  }

  async function handleAssignDevice(zoneId, zoneModuleId) {
    try {
      await api.assignZoneModule(zoneId, zoneModuleId);
      const device = devices.find((d) => d.id === zoneModuleId);
      pushLine("system", "HARDWARE MAPPED", `Linked ${zoneId} to physical device [${device?.nodeUuid || zoneModuleId}].`);
      await refreshLayout();
      setSelectedZoneId(zoneId);
    } catch (err) {
      pushLine("error", "ERROR", `Could not assign device to ${zoneId}: ${err.message}`);
    }
  }

  async function handleUnassign(zoneId) {
    try {
      await api.unassignZone(zoneId);
      pushLine("system", "HARDWARE UNMAPPED", `Cleared physical device assignment for ${zoneId}.`);
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not unassign ${zoneId}: ${err.message}`);
    }
  }

  async function handleUpdateZones(nextZones) {
    try {
      const payload = {
        racks: racks.map((r) => ({ id: r.id, name: r.name, rows: r.rows, cols: r.cols, x: r.x, y: r.y, rotation: r.rotation })),
        zones: nextZones.map((z) => ({
          id: z.id,
          rackId: z.rackId,
          name: z.name,
          group: z.group,
          x: z.x,
          y: z.y,
          w: z.w,
          h: z.h,
          barcode: z.barcode,
          defaultLed: z.defaultLed,
          maxBoxes: z.maxBoxes,
        })),
      };
      await api.saveLayout(payload);
      pushLine("system", "LAYOUT", "Zone geometry updated.");
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not update layout: ${err.message}`);
    }
  }

  async function handleSaveConfig({ zoneId, name, group, defaultLed, moduleType, moduleId, w, h }) {
    setSavingConfig(true);
    try {
      const target = zones.find((z) => z.id === zoneId);
      let nextZones = zones.map((z) =>
        z.id === zoneId
          ? { ...z, name: name || z.name, group, defaultLed }
          : z
      );

      let resizeRejected = false;
      if (target && (w !== target.w || h !== target.h)) {
        const rackForZone = racks.find((r) => r.id === target.rackId);
        const candidate = rackForZone
          ? clampBoxToBounds({ x: target.x, y: target.y, w, h }, rackForZone.cols, rackForZone.rows)
          : { x: target.x, y: target.y, w, h };
        const siblings = zones.filter((z) => z.id !== zoneId && z.rackId === target.rackId);
        if (overlapsAny(candidate, siblings)) {
          resizeRejected = true;
          pushLine(
            "error",
            "RESIZE BLOCKED",
            `${zoneId} can't grow to that size - it would overlap a neighboring zone. Move or shrink nearby zones first, then try again.`
          );
        } else {
          nextZones = nextZones.map((z) => (z.id === zoneId ? { ...z, ...candidate } : z));
        }
      }
      const payload = {
        racks: racks.map((r) => ({ id: r.id, name: r.name, rows: r.rows, cols: r.cols, x: r.x, y: r.y, rotation: r.rotation })),
        zones: nextZones.map((z) => ({
          id: z.id,
          rackId: z.rackId,
          name: z.name,
          group: z.group,
          x: z.x,
          y: z.y,
          w: z.w,
          h: z.h,
          barcode: z.barcode,
          defaultLed: z.defaultLed,
          maxBoxes: z.maxBoxes,
        })),
      };
      await api.saveLayout(payload);
      if (moduleId) {
        await api.updateZoneModule(moduleId, { moduleType });
      }
      if (!resizeRejected) {
        pushLine("system", "CONFIG SAVED", `Zone ${zoneId} configuration updated.`);
      }
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Failed to save configuration: ${err.message}`);
    } finally {
      setSavingConfig(false);
    }
  }

  const rack = racks[0] || null;
  const devicesByZone = {};
  devices.forEach((d) => {
    if (d.zoneId) devicesByZone[d.zoneId] = d;
  });
  const selectedZone = zones.find((z) => z.id === selectedZoneId) || null;
  const selectedZoneDevice = selectedZone ? devicesByZone[selectedZone.id] : null;
  const highlightedZoneIds = new Set(pickList.filter((i) => i.found && i.zoneId).map((i) => i.zoneId));

  return (
    <div className="app-shell">
      <Header stats={stats} online={mqttConnected} wsConnected={wsConnected} />

      <LogisticsPanel zones={zones} onStore={handleStore} busy={busy} />

      <div className="main-grid">
        <DeviceSidebar devices={devices} onSelectDevice={setSelectedDeviceId} selectedDeviceId={selectedDeviceId} />

        <DigitalTwinTabs
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          racks={racks}
          rack={rack}
          zones={zones}
          devicesByZone={devicesByZone}
          devices={devices}
          gateways={gateways}
          occupancy={occupancy}
          selectedZoneId={selectedZoneId}
          setSelectedZoneId={setSelectedZoneId}
          onAssignDevice={handleAssignDevice}
          onUpdateZones={handleUpdateZones}
          dragOverZoneId={dragOverZoneId}
          setDragOverZoneId={setDragOverZoneId}
          stats={stats}
          mode={mode}
          handleSetMode={handleSetMode}
          mqttConnected={mqttConnected}
          ollamaReachable={ollamaReachable}
          workers={workers}
          activeJobs={activeJobs}
          systemConfig={systemConfig}
          refreshLayout={refreshLayout}
          pushLine={pushLine}
          pickList={pickList}
          onBuildPickList={handleBuildPickList}
          onConfirmPickItem={handleConfirmPickItem}
          highlightedZoneIds={highlightedZoneIds}
        />

        <PropertiesPanel
          zone={selectedZone}
          device={selectedZoneDevice}
          onSave={handleSaveConfig}
          onUnassign={handleUnassign}
          saving={savingConfig}
        />
      </div>

      <EventStream lines={lines} />
    </div>
  );
}
