import React from "react";

function typeIcon(type) {
  if (type?.startsWith("Large")) return "🟪";
  if (type?.startsWith("Small")) return "🟦";
  return "🟩";
}

export default function DeviceSidebar({ devices, onSelectDevice, selectedDeviceId }) {
  const unassigned = devices.filter((d) => !d.zoneId);

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
      <div className="panel-title">
        <span className="dot" style={{ background: "var(--accent-amber)" }} />
        Unassigned Devices ({unassigned.length})
      </div>
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8, overflowY: "auto" }}>
        {unassigned.length === 0 && (
          <div className="text-fade" style={{ fontSize: 12.5, padding: "10px 4px" }}>
            All discovered devices are assigned to a zone.
          </div>
        )}
        {unassigned.map((d) => (
          <div
            key={d.id}
            draggable
            onDragStart={(e) => e.dataTransfer.setData("text/zone-module-id", d.id)}
            onClick={() => onSelectDevice(d.id)}
            className="device-chip"
            style={{
              borderColor: selectedDeviceId === d.id ? "var(--accent-cyan)" : "var(--border-soft)",
            }}
            title="Drag onto a zone in the grid map to assign"
          >
            <div className="mono" style={{ fontSize: 12.5, color: "var(--accent-cyan)", fontWeight: 700 }}>
              MAC: {d.nodeUuid}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 2 }}>
              {typeIcon(d.moduleType)} Type: {d.moduleType || "Medium Module"}
            </div>
            <div style={{ fontSize: 11, marginTop: 2, display: "flex", alignItems: "center", gap: 5 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: d.status === "Online" ? "var(--accent-green)" : "var(--accent-red)",
                }}
              />
              <span style={{ color: d.status === "Online" ? "var(--accent-green)" : "var(--accent-red)" }}>
                Status: {d.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
