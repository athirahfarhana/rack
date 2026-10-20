import React, { useEffect, useRef, useState } from "react";
import { clampBoxToBounds, overlapsAny } from "../lib/geometry";

const ROW_HEIGHT = 120; // px per rack row
const GAP = 10; // px gap between cells

export default function GridMap({
  rack,
  zones,
  devicesByZone,
  occupancy,
  selectedZoneId,
  onSelectZone,
  onAssignDevice,
  onUpdateZones,
  dragOverZoneId,
  setDragOverZoneId,
  highlightedZoneIds,
  bare = false,
}) {
  const [width, setWidth] = useState(760);
  const [livePos, setLivePos] = useState({}); // zoneId -> {x,y,w,h} in cells, while dragging
  const [boxListZoneId, setBoxListZoneId] = useState(null);
  const containerRef = useRef(null);
  const dragState = useRef(null);

  useEffect(() => {
    const measure = () => {
      if (containerRef.current) setWidth(containerRef.current.offsetWidth - 24);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  if (!rack) {
    return (
      <div className={bare ? "" : "panel"} style={{ padding: 24, textAlign: "center" }}>
        <div className="text-fade">No rack layout loaded yet.</div>
      </div>
    );
  }

  const cols = rack.cols || 3;
  const rows = rack.rows || 3;
  const cellWidth = cols > 0 ? width / cols : 0;
  const containerHeight = rows * ROW_HEIGHT;

  function handlePointerDown(e, zone, mode) {
    if (!onUpdateZones) return;
    e.preventDefault();
    e.stopPropagation();
    dragState.current = {
      mode,
      zoneId: zone.id,
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startBox: { x: zone.x, y: zone.y, w: zone.w, h: zone.h },
      moved: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e) {
    const ds = dragState.current;
    if (!ds || ds.pointerId !== e.pointerId || cellWidth <= 0) return;

    const deltaCellsX = Math.round((e.clientX - ds.startClientX) / cellWidth);
    const deltaCellsY = Math.round((e.clientY - ds.startClientY) / ROW_HEIGHT);
    if (deltaCellsX !== 0 || deltaCellsY !== 0) ds.moved = true;

    let candidate;
    if (ds.mode === "move") {
      candidate = clampBoxToBounds(
        { x: ds.startBox.x + deltaCellsX, y: ds.startBox.y + deltaCellsY, w: ds.startBox.w, h: ds.startBox.h },
        cols,
        rows
      );
    } else {
      const maxW = Math.min(3, cols);
      const maxH = Math.min(3, rows);
      const w = Math.max(1, Math.min(maxW, ds.startBox.w + deltaCellsX));
      const h = Math.max(1, Math.min(maxH, ds.startBox.h + deltaCellsY));
      candidate = clampBoxToBounds({ x: ds.startBox.x, y: ds.startBox.y, w, h }, cols, rows);
    }

    const others = zones
      .filter((z) => z.id !== ds.zoneId)
      .map((z) => (livePos[z.id] ? livePos[z.id] : { x: z.x, y: z.y, w: z.w, h: z.h }));

    if (!overlapsAny(candidate, others)) {
      setLivePos((prev) => ({ ...prev, [ds.zoneId]: candidate }));
    }
    // if it would overlap a neighbor, the zone simply sticks at its last
    // valid spot instead of passing through it
  }

  function finishDrag(e) {
    const ds = dragState.current;
    if (!ds || ds.pointerId !== e.pointerId) return;
    dragState.current = null;

    const finalBox = livePos[ds.zoneId];
    if (finalBox && onUpdateZones) {
      const changed =
        finalBox.x !== ds.startBox.x ||
        finalBox.y !== ds.startBox.y ||
        finalBox.w !== ds.startBox.w ||
        finalBox.h !== ds.startBox.h;
      if (changed) {
        onUpdateZones(zones.map((z) => (z.id === ds.zoneId ? { ...z, ...finalBox } : z)));
      }
    }
    setLivePos((prev) => {
      const next = { ...prev };
      delete next[ds.zoneId];
      return next;
    });
  }

  const boxListZone = zones.find((z) => z.id === boxListZoneId) || null;
  const boxListBoxes = boxListZoneId ? occupancy[boxListZoneId] || [] : [];

  return (
    <div className={bare ? "" : "panel"} style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {bare ? (
        <div className="grid-hint-strip">
          <span className="grid-badge">COLS: {cols}</span>
          <span className="grid-badge">ROWS: {rows}</span>
          <span className="grid-badge grid-badge-muted">
            {onUpdateZones ? "drag: move \u00b7 corner: resize \u00b7 dbl-click: view boxes" : "click: select \u00b7 drag device to assign \u00b7 dbl-click: view boxes"}
          </span>
        </div>
      ) : (
        <div className="panel-title" style={{ justifyContent: "space-between" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="dot" style={{ background: "var(--accent-cyan)" }} />
            Real-Time Digital Twin Grid Map{" "}
            <span className="text-fade" style={{ fontWeight: 500, textTransform: "none" }}>
              (Drag / Drop Modules)
            </span>
          </span>
          <span style={{ display: "flex", gap: 6, textTransform: "none" }}>
            <span className="grid-badge">COLS: {cols}</span>
            <span className="grid-badge">ROWS: {rows}</span>
            <span className="grid-badge grid-badge-muted">drag: move &middot; corner: resize &middot; dbl-click: view boxes</span>
          </span>
        </div>
      )}
      <div style={{ flex: 1, padding: 14, overflow: "auto" }} ref={containerRef}>
        <div className="rack-floor" style={{ width, minHeight: containerHeight + 24 }}>
          <div style={{ position: "relative", width: width - 24, height: containerHeight - 24 }}>
            {zones.map((z) => {
              const device = devicesByZone[z.id];
              const boxes = occupancy[z.id] || [];
              const box = livePos[z.id] || { x: z.x, y: z.y, w: z.w, h: z.h };
              const isDragging = !!livePos[z.id];
              const selected = selectedZoneId === z.id;
              const dragOverAssign = dragOverZoneId === z.id;
              const highlighted = !!highlightedZoneIds?.has?.(z.id);

              return (
                <div
                  key={z.id}
                  onPointerDown={(e) => handlePointerDown(e, z, "move")}
                  onPointerMove={handlePointerMove}
                  onPointerUp={finishDrag}
                  onPointerCancel={finishDrag}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (dragState.current?.moved) return;
                    onSelectZone(z.id);
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setBoxListZoneId(z.id);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOverZoneId(z.id);
                  }}
                  onDragLeave={() => setDragOverZoneId((cur) => (cur === z.id ? null : cur))}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOverZoneId(null);
                    const moduleId = e.dataTransfer.getData("text/zone-module-id");
                    if (moduleId) onAssignDevice(z.id, moduleId);
                  }}
                  className={`zone-tile-canvas${isDragging ? " dragging" : ""}${highlighted ? " highlighted" : selected ? " selected" : ""}${dragOverAssign ? " drop-target" : ""}`}
                  style={{
                    left: box.x * cellWidth + (box.x > 0 ? GAP / 2 : 0),
                    top: box.y * ROW_HEIGHT + (box.y > 0 ? GAP / 2 : 0),
                    width: box.w * cellWidth - GAP,
                    height: box.h * ROW_HEIGHT - GAP,
                    touchAction: "none",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span className="mono" style={{ fontSize: 12.5, fontWeight: 700, color: selected || highlighted ? "var(--accent-cyan)" : "var(--text-primary)" }}>
                      {z.name || z.id}
                    </span>
                    {boxes.length > 0 && (
                      <span className="box-count-badge">
                        📦 {boxes.length}
                      </span>
                    )}
                  </div>

                  <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}>
                    {boxes.length > 0 ? `${boxes.length}/${z.maxBoxes || 20} BOXES` : "EMPTY"}
                  </div>

                  {boxes.length > 0 && (
                    <div className="mono" style={{ fontSize: 9.5, marginTop: 4, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {boxes.slice(0, 2).map((b) => b.boxId).join(", ")}
                      {boxes.length > 2 ? ` +${boxes.length - 2} more` : ""}
                    </div>
                  )}

                  <div style={{ marginTop: "auto", fontSize: 10, color: device ? "var(--accent-green)" : "var(--text-muted)" }}>
                    {device ? (
                      <span className="mono">⬢ {device.nodeUuid}</span>
                    ) : (
                      "--"
                    )}
                  </div>

                  {onUpdateZones && (
                    <div
                      onPointerDown={(e) => handlePointerDown(e, z, "resize")}
                      onPointerMove={handlePointerMove}
                      onPointerUp={finishDrag}
                      onPointerCancel={finishDrag}
                      onClick={(e) => e.stopPropagation()}
                      title="Drag to resize"
                      className="resize-handle"
                      style={{ touchAction: "none" }}
                    >
                      <svg viewBox="0 0 10 10" width="12" height="12">
                        <path d="M9 1 L1 9 M9 5 L5 9" stroke="currentColor" strokeWidth="1.2" fill="none" />
                      </svg>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {boxListZoneId && (
        <div className="modal-overlay" onClick={() => setBoxListZoneId(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span>
                {boxListZone?.name || boxListZoneId} <span style={{ color: "var(--accent-cyan)", fontWeight: 500 }}>Boxes</span>
              </span>
              <button className="modal-close" onClick={() => setBoxListZoneId(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              {boxListBoxes.length === 0 ? (
                <div className="text-fade" style={{ textAlign: "center", padding: "20px 0", fontSize: 12 }}>
                  No boxes currently in this zone
                </div>
              ) : (
                boxListBoxes.map((b) => (
                  <div key={b.boxId} className="modal-box-row">
                    <span className="mono">📦 {b.boxId}</span>
                    {b.processStage && <span className="modal-stage-chip">{b.processStage.replace("_", " ")}</span>}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
