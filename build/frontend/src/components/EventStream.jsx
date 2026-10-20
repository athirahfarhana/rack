import React, { useEffect, useRef } from "react";

const LEVEL_COLOR = {
  info: "var(--text-secondary)",
  queued: "var(--accent-amber)",
  done: "var(--accent-green)",
  error: "var(--accent-red)",
  system: "var(--accent-cyan)",
};

export default function EventStream({ lines }) {
  const boxRef = useRef(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="panel-title">
        <span className="dot" style={{ background: "var(--accent-teal)" }} />
        Live Operation Event Stream
      </div>
      <div ref={boxRef} className="mono event-stream">
        {lines.length === 0 && <div className="text-fade">Waiting for warehouse activity...</div>}
        {lines.map((l) => (
          <div key={l.id} style={{ animation: "fade-in-row 0.25s ease" }}>
            <span className="text-fade">[{l.time}]</span>{" "}
            <span style={{ color: LEVEL_COLOR[l.level] || "var(--text-secondary)", fontWeight: 700 }}>{l.tag}:</span>{" "}
            <span>{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
