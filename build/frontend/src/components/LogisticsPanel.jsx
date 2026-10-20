import React, { useEffect, useRef, useState } from "react";

export default function LogisticsPanel({ zones, onStore, busy }) {
  const [storeBoxId, setStoreBoxId] = useState("");
  const [targetZone, setTargetZone] = useState("");
  const scanInputRef = useRef(null);

  const zoneOptions = zones.length ? zones : [];
  const resolvedTarget = targetZone || zoneOptions[0]?.id || "";

  // Keep the Box ID field focused so a keyboard-wedge barcode scanner (it
  // just types digits + Enter wherever focus is, same as the Zebra DS2208
  // in the proposal) can be used continuously without clicking between
  // scans: focused on load, and re-focused right after each store.
  useEffect(() => {
    scanInputRef.current?.focus();
  }, []);

  function submitStore(e) {
    e.preventDefault();
    if (!storeBoxId.trim() || !resolvedTarget) return;
    onStore(storeBoxId.trim(), resolvedTarget);
    setStoreBoxId("");
    scanInputRef.current?.focus();
  }

  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      <form
        onSubmit={submitStore}
        className="panel"
        style={{ flex: "1 1 420px", padding: "14px 18px", display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, fontWeight: 700, color: "var(--accent-amber)", minWidth: 190 }}>
          <span>📥</span> Inbound Logistics <span className="text-fade" style={{ fontWeight: 500 }}>(Store Box)</span>
        </div>
        <input
          ref={scanInputRef}
          className="field"
          placeholder="Input Box ID..."
          value={storeBoxId}
          onChange={(e) => setStoreBoxId(e.target.value)}
          style={{ flex: "1 1 200px" }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 700, letterSpacing: "0.06em" }}>
            TARGET ZONE
          </label>
          <select className="field" value={resolvedTarget} onChange={(e) => setTargetZone(e.target.value)}>
            {zoneOptions.map((z) => (
              <option key={z.id} value={z.id}>
                {z.id}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn btn-teal" disabled={busy}>
          Store
        </button>
      </form>
    </div>
  );
}
