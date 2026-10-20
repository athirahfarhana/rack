import React, { useState } from "react";
import { api } from "../api";

export default function SettingsTab({
  mode,
  handleSetMode,
  mqttConnected,
  ollamaReachable,
  gateways,
  devices,
  systemConfig,
  refreshLayout,
  pushLine,
}) {
  const [newGwId, setNewGwId] = useState("");
  const [newModule, setNewModule] = useState({ nodeUuid: "", gatewayId: "", moduleType: "Medium Module" });
  const [busy, setBusy] = useState(false);

  async function addGateway() {
    if (!newGwId.trim()) return;
    setBusy(true);
    try {
      await api.addGateway(newGwId.trim());
      pushLine("system", "DEVICE", `Gateway ${newGwId.trim()} registered.`);
      setNewGwId("");
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not add gateway: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function deleteGateway(id) {
    setBusy(true);
    try {
      await api.deleteGateway(id);
      pushLine("system", "DEVICE", `Gateway ${id} removed.`);
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not remove gateway: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function pingGateway(gwId) {
    try {
      const res = await api.pingGateway(gwId);
      pushLine("system", "PING", `Gateway ${gwId}: ${res.published ? "ping published" : "not published"} (MQTT ${res.mqttConnected ? "connected" : "disconnected"}).`);
    } catch (err) {
      pushLine("error", "ERROR", `Ping failed: ${err.message}`);
    }
  }

  async function addModule() {
    if (!newModule.nodeUuid.trim() || !newModule.gatewayId) return;
    setBusy(true);
    try {
      await api.addZoneModule(newModule);
      pushLine("system", "DEVICE", `Module ${newModule.nodeUuid} registered.`);
      setNewModule({ nodeUuid: "", gatewayId: "", moduleType: "Medium Module" });
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not add module: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function deleteModule(id) {
    setBusy(true);
    try {
      await api.deleteZoneModule(id);
      pushLine("system", "DEVICE", `Module ${id} removed.`);
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not remove module: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function identifyModule(id, uuid) {
    try {
      await api.identifyModule(id);
      pushLine("system", "IDENTIFY", `Blink requested for ${uuid}.`);
    } catch (err) {
      pushLine("error", "ERROR", `Identify failed: ${err.message}`);
    }
  }

  return (
    <div className="settings-tab">
      <div className="settings-card">
        <div className="settings-card-title">Operating Mode</div>
        <div className="text-fade" style={{ fontSize: 11.5, lineHeight: 1.6, marginBottom: 12 }}>
          <b style={{ color: "var(--accent-amber)" }}>Mock</b> mode runs the built-in simulator, which plays the role of Gateways
          over real MQTT so the app is fully demoable with zero hardware attached.{" "}
          <b style={{ color: "var(--accent-green)" }}>Live</b> mode pauses the simulator - only real MQTT traffic and real API
          calls drive what you see.
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className={`mode-btn${mode === "mock" ? " active-amber" : ""}`} onClick={() => handleSetMode("mock")}>
            Mock Mode
          </button>
          <button className={`mode-btn${mode === "live" ? " active-green" : ""}`} onClick={() => handleSetMode("live")}>
            Live Mode
          </button>
        </div>
        <div className="settings-status-row">
          <StatusItem label="Backend" ok value="Reachable" />
          <StatusItem label="MQTT Broker" ok={mqttConnected} value={mqttConnected ? "Connected" : "Disconnected"} />
          <StatusItem label="AI (Assistant)" ok={ollamaReachable} value={ollamaReachable ? "Reachable" : "Unreachable"} />
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Device Management</span>
        </div>
        <div className="text-fade" style={{ fontSize: 11, marginBottom: 10 }}>
          Gateways are the WiFi/MQTT-speaking hardware; Zone Modules talk to their parent Gateway. Register hardware here
          before it's powered on, or inspect the MQTT traffic for debugging.
        </div>

        <div className="settings-subhead">
          <span>Gateways ({gateways.length})</span>
        </div>
        <div className="device-mgmt-list">
          {gateways.map((g) => (
            <div key={g.id} className="device-mgmt-row">
              <span className={`live-dot ${g.status === "Online" ? "" : "offline"}`} />
              <div style={{ flex: 1 }}>
                <div className="mono" style={{ fontSize: 12, fontWeight: 700 }}>{g.gwId}</div>
                <div className="text-fade" style={{ fontSize: 10 }}>
                  {g.status} &middot; {g.activeNodesCount ?? 0} nodes {g.isSimulated ? "\u00b7 simulated" : ""}
                </div>
              </div>
              <button className="icon-btn" title="Ping" onClick={() => pingGateway(g.gwId)}>⚡</button>
              <button className="icon-btn danger" title="Remove" onClick={() => deleteGateway(g.id)}>🗑</button>
            </div>
          ))}
        </div>
        <div className="add-inline-form">
          <input placeholder="New gateway ID (e.g. GW-RACK-B1)" value={newGwId} onChange={(e) => setNewGwId(e.target.value)} />
          <button className="btn-solid-blue" onClick={addGateway} disabled={busy}>+ Add Gateway</button>
        </div>

        <div className="settings-subhead" style={{ marginTop: 16 }}>
          <span>Zone Modules ({devices.length})</span>
        </div>
        <div className="device-mgmt-list scroll">
          {devices.map((m) => (
            <div key={m.id} className="device-mgmt-row">
              <span className={`live-dot ${m.status === "Online" ? "" : "offline"}`} />
              <div style={{ flex: 1 }}>
                <div className="mono" style={{ fontSize: 12, fontWeight: 700 }}>{m.nodeUuid}</div>
                <div className="text-fade" style={{ fontSize: 10 }}>
                  {m.moduleType} &middot; via {m.gwId} &middot; {m.zoneId ? `assigned to ${m.zoneId}` : "unassigned"}
                </div>
              </div>
              <button className="icon-btn" title="Identify (blink)" onClick={() => identifyModule(m.id, m.nodeUuid)}>💡</button>
              <button className="icon-btn danger" title="Remove" onClick={() => deleteModule(m.id)}>🗑</button>
            </div>
          ))}
        </div>
        <div className="add-inline-form">
          <input placeholder="MAC / node UUID" value={newModule.nodeUuid} onChange={(e) => setNewModule({ ...newModule, nodeUuid: e.target.value })} />
          <select value={newModule.gatewayId} onChange={(e) => setNewModule({ ...newModule, gatewayId: e.target.value })}>
            <option value="">Gateway&hellip;</option>
            {gateways.map((g) => (
              <option key={g.id} value={g.id}>{g.gwId}</option>
            ))}
          </select>
          <select value={newModule.moduleType} onChange={(e) => setNewModule({ ...newModule, moduleType: e.target.value })}>
            <option>Small Module</option>
            <option>Medium Module</option>
            <option>Large Module</option>
          </select>
          <button className="btn-solid-blue" onClick={addModule} disabled={busy}>+ Add Module</button>
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">MQTT Configuration</div>
        <div className="text-fade" style={{ fontSize: 11, marginBottom: 10 }}>
          Broker connection is configured on the backend (<span className="mono">backend/.env</span>) so every client shares
          one source of truth. Shown here for reference.
        </div>
        {systemConfig ? (
          <div className="settings-field-grid">
            <Field label="Broker Host" value={systemConfig.mqttHost} />
            <Field label="Port" value={systemConfig.mqttPort} />
            <Field label="Topic Prefix" value={systemConfig.mqttTopicPrefix} />
            <Field label="Heartbeat Timeout" value={`${systemConfig.heartbeatTimeoutSec}s`} />
          </div>
        ) : (
          <div className="text-fade">Loading&hellip;</div>
        )}
      </div>

      <div className="settings-card">
        <div className="settings-card-title">AI Assistant</div>
        <div className="text-fade" style={{ fontSize: 11, marginBottom: 10 }}>
          The chatbot runs against a local Ollama server. Change the model or host in{" "}
          <span className="mono">backend/.env</span> (OLLAMA_HOST, OLLAMA_MODEL).
        </div>
        {systemConfig ? (
          <div className="settings-field-grid">
            <Field label="Model" value={systemConfig.ollamaModel} />
            <Field label="Host" value={systemConfig.ollamaHost} />
          </div>
        ) : (
          <div className="text-fade">Loading&hellip;</div>
        )}
      </div>
    </div>
  );
}

function StatusItem({ label, ok, value }) {
  return (
    <div className="settings-status-item">
      <span className={`live-dot ${ok ? "" : "offline"}`} />
      <div>
        <div style={{ fontSize: 10.5 }}>{label}</div>
        <div className="text-fade" style={{ fontSize: 10 }}>{value}</div>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-fade" style={{ fontSize: 9.5, marginBottom: 3 }}>{label.toUpperCase()}</div>
      <div className="settings-field-value mono">{value}</div>
    </div>
  );
}
