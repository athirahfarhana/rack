import React from "react";

function StatCard({ label, value, accent, icon }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: "10px 18px",
        borderLeft: "1px solid var(--border-soft)",
        minWidth: 140,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}
      >
        <span>{icon}</span>
        <span>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent || "var(--text-primary)", lineHeight: 1 }}>
        {value}
      </div>
    </div>
  );
}

export default function Header({ stats, online }) {
  return (
    <header
      className="panel"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 22px",
        flexWrap: "wrap",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          aria-hidden
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: "linear-gradient(135deg, #1c2b52, #0c1226)",
            border: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--accent-cyan)",
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path
              d="M3 8L12 3L21 8L12 13L3 8Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path d="M3 12L12 17L21 12" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M3 16L12 21L21 16" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" opacity="0.5" />
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.01em" }}>
            UST Smart Warehouse{" "}
            <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>Rack Management System</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>Rack A1 &middot; Live operational view</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "stretch" }}>
        <StatCard label="Total Boxes Stored" value={stats.itemsStored} icon="📦" accent="var(--text-primary)" />
        <StatCard label="Current Pending" value={stats.pendingJobs} icon="⏳" accent="var(--accent-amber)" />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            padding: "10px 18px",
            borderLeft: "1px solid var(--border-soft)",
            minWidth: 150,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.07em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
            }}
          >
            <span>📶</span>
            <span>System Connectivity</span>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              fontSize: 20,
              fontWeight: 800,
              color: online ? "var(--accent-green)" : "var(--accent-red)",
            }}
          >
            <span
              style={{
                width: 9,
                height: 9,
                borderRadius: "50%",
                background: online ? "var(--accent-green)" : "var(--accent-red)",
                animation: online ? "pulse-glow 2s infinite" : "none",
              }}
            />
            {online ? "ONLINE" : "OFFLINE"}
          </div>
        </div>
      </div>
    </header>
  );
}
