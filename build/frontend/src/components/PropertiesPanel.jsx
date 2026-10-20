import React, { useEffect, useRef, useState } from "react";

const LED_OPTIONS = [
  { value: "blue", label: "Blue", color: "#38bdf8" },
  { value: "green", label: "Green", color: "#22c55e" },
  { value: "amber", label: "Amber", color: "#f59e0b" },
  { value: "red", label: "Red", color: "#f87171" },
  { value: "purple", label: "Purple", color: "#a78bfa" },
];

const MODULE_TYPES = ["Small Module", "Medium Module", "Large Module"];

// Zone footprint presets, in grid cells (w x h) - matches the physical
// small/medium/large cubby sizes from the spec (one large cubby, two
// medium, or three small side by side within a rack tier).
const ZONE_SIZES = {
  small: { label: "Small (1×1)", w: 1, h: 1 },
  medium: { label: "Medium (2×1)", w: 2, h: 1 },
  large: { label: "Large (2×2)", w: 2, h: 2 },
};

function sizeKeyFor(w, h) {
  const match = Object.entries(ZONE_SIZES).find(([, s]) => s.w === w && s.h === h);
  return match ? match[0] : "medium";
}

export default function PropertiesPanel({ zone, device, onSave, onUnassign, saving }) {
  const [name, setName] = useState("");
  const [group, setGroup] = useState("");
  const [moduleType, setModuleType] = useState("Medium Module");
  const [led, setLed] = useState("blue");
  const [sizeKey, setSizeKey] = useState("medium");

  useEffect(() => {
    if (!zone) return;
    setName(zone.name || "");
    setGroup(zone.group || "");
    setModuleType(device?.moduleType || "Medium Module");
    setLed(zone.defaultLed || "blue");
    setSizeKey(sizeKeyFor(zone.w, zone.h));
  }, [zone?.id, device?.id]);

  // When a save finishes (whether it fully applied or part of it - e.g. a
  // resize - was rejected server-side for overlapping), resync every field
  // from the now-authoritative zone/device data instead of leaving the form
  // showing a size that didn't actually take.
  const wasSaving = useRef(false);
  useEffect(() => {
    if (wasSaving.current && !saving && zone) {
      setName(zone.name || "");
      setGroup(zone.group || "");
      setModuleType(device?.moduleType || "Medium Module");
      setLed(zone.defaultLed || "blue");
      setSizeKey(sizeKeyFor(zone.w, zone.h));
    }
    wasSaving.current = saving;
  }, [saving, zone, device]);

  if (!zone) {
    return (
      <div className="panel" style={{ padding: 24 }}>
        <div className="panel-title" style={{ padding: 0, border: "none", marginBottom: 10 }}>
          <span className="dot" style={{ background: "var(--accent-purple)" }} />
          Zone Properties &amp; Flow
        </div>
        <div className="text-fade" style={{ fontSize: 12.5 }}>
          Select a zone on the grid map to view or edit its configuration.
        </div>
      </div>
    );
  }

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="panel-title">
        <span className="dot" style={{ background: "var(--accent-purple)" }} />
        Zone Properties &amp; Flow
      </div>
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <FieldStatic label="Selected Module ID" value={zone.id} accent="var(--accent-cyan)" mono />
        <FieldStatic
          label="Hardware MAC Address"
          value={device?.nodeUuid || "-- not assigned --"}
          mono
        />

        <Field label="Assigned Custom Name">
          <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>

        <Field label="Zone / Shelf Group">
          <input className="field" value={group} onChange={(e) => setGroup(e.target.value)} placeholder="e.g. Zone A" />
        </Field>

        <Field label="Zone Size">
          <select className="field" value={sizeKey} onChange={(e) => setSizeKey(e.target.value)}>
            {Object.entries(ZONE_SIZES).map(([key, s]) => (
              <option key={key} value={key}>
                {s.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Hardware Module Type">
          <select className="field" value={moduleType} onChange={(e) => setModuleType(e.target.value)} disabled={!device}>
            {MODULE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Default LED Color">
          <select className="field" value={led} onChange={(e) => setLed(e.target.value)}>
            {LED_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
          <button
            className="btn btn-teal"
            style={{ flex: 1 }}
            disabled={saving}
            onClick={() =>
              onSave({
                zoneId: zone.id,
                name,
                group,
                defaultLed: led,
                moduleType,
                moduleId: device?.id,
                w: ZONE_SIZES[sizeKey].w,
                h: ZONE_SIZES[sizeKey].h,
              })
            }
          >
            {saving ? "Saving..." : "[ Save Configuration ]"}
          </button>
        </div>
        {device && (
          <button className="btn btn-ghost" onClick={() => onUnassign(zone.id)}>
            Unassign Device
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.05em", color: "var(--text-muted)" }}>
        {label.toUpperCase()}:
      </label>
      {children}
    </div>
  );
}

function FieldStatic({ label, value, accent, mono }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <label style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.05em", color: "var(--text-muted)" }}>
        {label.toUpperCase()}:
      </label>
      <div className={mono ? "mono" : undefined} style={{ fontSize: 13.5, fontWeight: 600, color: accent || "var(--text-secondary)" }}>
        {value}
      </div>
    </div>
  );
}
