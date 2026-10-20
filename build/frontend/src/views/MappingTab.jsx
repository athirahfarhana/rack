import React, { useState } from "react";
import GridMap from "../components/GridMap";
import { api } from "../api";

export default function MappingTab({
  racks,
  rack,
  zones,
  devicesByZone,
  occupancy,
  selectedZoneId,
  setSelectedZoneId,
  onAssignDevice,
  onUpdateZones,
  dragOverZoneId,
  setDragOverZoneId,
  refreshLayout,
  pushLine,
}) {
  const [editMode, setEditMode] = useState(false);
  const [showAddRack, setShowAddRack] = useState(false);
  const [newRack, setNewRack] = useState({ name: "", cols: 3, rows: 3 });
  const [saving, setSaving] = useState(false);

  async function addRack() {
    if (!newRack.name.trim()) return;
    setSaving(true);
    try {
      const id = newRack.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-");
      const payload = {
        racks: [
          ...racks.map((r) => ({ id: r.id, name: r.name, rows: r.rows, cols: r.cols, x: r.x, y: r.y, rotation: r.rotation })),
          { id, name: newRack.name.trim(), rows: Number(newRack.rows) || 3, cols: Number(newRack.cols) || 3, x: 0, y: 0, rotation: 0 },
        ],
        zones: zones.map((z) => ({
          id: z.id, rackId: z.rackId, name: z.name, group: z.group, x: z.x, y: z.y, w: z.w, h: z.h,
          barcode: z.barcode, defaultLed: z.defaultLed, maxBoxes: z.maxBoxes,
        })),
      };
      await api.saveLayout(payload);
      pushLine("system", "LAYOUT", `Rack "${newRack.name}" added.`);
      setShowAddRack(false);
      setNewRack({ name: "", cols: 3, rows: 3 });
      await refreshLayout();
    } catch (err) {
      pushLine("error", "ERROR", `Could not add rack: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mapping-tab">
      <div className="mapping-tab-header">
        <div className="text-fade" style={{ fontSize: 11 }}>
          Warehouse <span style={{ color: "var(--accent-cyan)" }}>Layout</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className={`btn-outline${editMode ? " active" : ""}`} onClick={() => setEditMode((v) => !v)}>
            {editMode ? "Done Editing" : "Edit Layout"}
          </button>
          <button className="btn-solid-blue" onClick={() => setShowAddRack((v) => !v)}>
            + Add Rack
          </button>
        </div>
      </div>

      {showAddRack && (
        <div className="add-rack-form">
          <input placeholder="Rack name (e.g. RACK B1)" value={newRack.name} onChange={(e) => setNewRack({ ...newRack, name: e.target.value })} />
          <input type="number" min={1} max={8} placeholder="Cols" value={newRack.cols} onChange={(e) => setNewRack({ ...newRack, cols: e.target.value })} />
          <input type="number" min={1} max={8} placeholder="Rows" value={newRack.rows} onChange={(e) => setNewRack({ ...newRack, rows: e.target.value })} />
          <button className="btn-solid-teal" onClick={addRack} disabled={saving}>
            {saving ? "Saving\u2026" : "Create"}
          </button>
        </div>
      )}

      <div className="rack-card-row">
        {racks.map((r) => (
          <div key={r.id} className={`rack-card${rack?.id === r.id ? " active" : ""}`}>
            <div style={{ fontWeight: 700, fontSize: 12.5 }}>{r.name}</div>
            <div className="text-fade" style={{ fontSize: 10 }}>
              {r.cols}×{r.rows} grid
            </div>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <GridMap
          rack={rack}
          zones={zones}
          devicesByZone={devicesByZone}
          occupancy={occupancy}
          selectedZoneId={selectedZoneId}
          onSelectZone={setSelectedZoneId}
          onAssignDevice={onAssignDevice}
          onUpdateZones={editMode ? onUpdateZones : undefined}
          dragOverZoneId={dragOverZoneId}
          setDragOverZoneId={setDragOverZoneId}
          bare
        />
      </div>
    </div>
  );
}
