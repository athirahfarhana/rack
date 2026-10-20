import React, { useState } from "react";
import GridMap from "../components/GridMap";
import { api } from "../api";

export default function LiveTab({
  rack,
  zones,
  devicesByZone,
  occupancy,
  selectedZoneId,
  setSelectedZoneId,
  onAssignDevice,
  dragOverZoneId,
  setDragOverZoneId,
  workers,
  activeJobs,
  pushLine,
  pickList,
  onBuildPickList,
  onConfirmPickItem,
  highlightedZoneIds,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [routeInput, setRouteInput] = useState("");
  const [buildingRoute, setBuildingRoute] = useState(false);
  const operative = workers && workers[0];

  async function buildRoute() {
    const boxIds = routeInput
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!boxIds.length || !onBuildPickList) return;
    setBuildingRoute(true);
    try {
      await onBuildPickList(boxIds);
    } finally {
      setBuildingRoute(false);
    }
  }

  async function locate() {
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    try {
      const box = await api.getBox(q);
      if (box.zoneId) {
        setSelectedZoneId(box.zoneId);
        pushLine("system", "LOCATE", `Box [${box.boxId}] found in ${box.zoneName || box.zoneId}.`);
      } else {
        pushLine("system", "LOCATE", `Box [${q}] is not currently staged anywhere.`);
      }
    } catch {
      pushLine("error", "LOCATE", `No box matching "${q}" was found.`);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="live-tab">
      <div className="live-sidebar">
        <div className="text-fade" style={{ fontSize: 10.5, marginBottom: 8 }}>ACTIVE OPERATIVE</div>
        {operative ? (
          <div className="operative-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{operative.name}</div>
              <span className="live-dot" style={{ background: "var(--accent-green)" }} />
            </div>
            <div className="text-fade" style={{ fontSize: 10.5, marginTop: 2 }}>ASSIGNMENT: LEAD PICKER</div>
            <div className="operative-color-row">
              <span className="text-fade" style={{ fontSize: 10 }}>COLOR ID:</span>
              <span className="mono" style={{ fontSize: 10, color: operative.colorHex }}>{operative.colorHex}</span>
            </div>
          </div>
        ) : (
          <div className="text-fade" style={{ fontSize: 11.5 }}>No operatives configured.</div>
        )}

        <div className="text-fade" style={{ fontSize: 10.5, margin: "16px 0 6px" }}>SEARCH BOX (LOCATE)</div>
        <input
          className="live-search-input"
          placeholder="Enter Box ID, QR, or Barcode"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && locate()}
        />
        <button className="live-search-btn" onClick={locate} disabled={searching}>
          {searching ? "Searching\u2026" : "Search & Locate"}
        </button>

        <div className="text-fade" style={{ fontSize: 10.5, margin: "16px 0 6px" }}>
          PICK LIST (ROUTE SEARCH)
        </div>
        <textarea
          className="live-search-input"
          style={{ minHeight: 56, resize: "vertical", fontFamily: "inherit" }}
          placeholder={"Box IDs for this route, one per line or comma-separated\ne.g. BOX-1, BOX-2, BOX-3"}
          value={routeInput}
          onChange={(e) => setRouteInput(e.target.value)}
        />
        <button className="live-search-btn" onClick={buildRoute} disabled={buildingRoute || !onBuildPickList}>
          {buildingRoute ? "Building…" : "Build Pick List"}
        </button>

        {pickList && pickList.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {pickList.map((item, i) => (
              <div key={`${item.query}-${i}`} className="task-queue-row" style={{ opacity: item.found ? 1 : 0.55 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="mono" style={{ fontWeight: 700 }}>{item.boxId || item.query}</div>
                  <div className="text-fade" style={{ fontSize: 10.5 }}>
                    {item.found ? `${item.rackName || item.rackId || "-"} · ${item.zoneName || item.zoneId}` : item.message}
                  </div>
                </div>
                {item.found && onConfirmPickItem && (
                  <button className="btn btn-teal" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => onConfirmPickItem(item.boxId)}>
                    Picked
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="text-fade" style={{ fontSize: 10.5, margin: "16px 0 6px" }}>TASK QUEUE</div>
        {activeJobs.length === 0 ? (
          <div className="text-fade" style={{ fontSize: 11 }}>No active tasks</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {activeJobs.map((j, i) => (
              <div key={i} className="task-queue-row">
                <span className="mono">{j.boxId}</span>
                <span className="text-fade">{j.jobType} &middot; {j.zoneName || j.zoneId}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <GridMap
          rack={rack}
          zones={zones}
          devicesByZone={devicesByZone}
          occupancy={occupancy}
          selectedZoneId={selectedZoneId}
          onSelectZone={setSelectedZoneId}
          onAssignDevice={onAssignDevice}
          dragOverZoneId={dragOverZoneId}
          setDragOverZoneId={setDragOverZoneId}
          highlightedZoneIds={highlightedZoneIds}
          bare
        />
      </div>
    </div>
  );
}
