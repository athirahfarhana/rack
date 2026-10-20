import React, { useState } from "react";
import { api } from "../api";

export default function DashboardTab({ stats, mode, ollamaReachable, pushLine }) {
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([
    {
      role: "assistant",
      text: "Hi! I can look up real box locations, zone capacity, device health, and recent activity for you. Try asking \u201cwhere is BOX-1?\u201d or \u201cany devices offline?\u201d",
    },
  ]);
  const [chatBusy, setChatBusy] = useState(false);

  async function sendChat() {
    const message = chatInput.trim();
    if (!message || chatBusy) return;
    setChatInput("");
    setChatMessages((cur) => [...cur, { role: "user", text: message }]);
    setChatBusy(true);
    try {
      const res = await api.sendChat(message, "dashboard-tab");
      setChatMessages((cur) => [...cur, { role: "assistant", text: res.reply }]);
    } catch (err) {
      setChatMessages((cur) => [...cur, { role: "assistant", text: `Sorry, I couldn't reach the assistant (${err.message}).` }]);
    } finally {
      setChatBusy(false);
    }
  }

  const recentPicks = stats.recentPicks || [];
  const alerts = stats.alerts || [];

  return (
    <div className="dash-tab">
      <div className="dash-tab-header">
        <div className="dash-tab-title">
          System <span style={{ color: "var(--accent-cyan)" }}>Dashboard</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`chip ${mode === "mock" ? "chip-amber" : "chip-green"}`}>{mode === "mock" ? "MOCK DATA" : "LIVE DATA"}</span>
          <span className="chip chip-cyan-soft">
            <span className="live-dot" /> LIVE UPDATES ACTIVE
          </span>
        </div>
      </div>

      <div className="dash-stat-grid">
        <StatCard label="Items Stored" value={stats.itemsStored ?? 0} sub="Currently Staged" icon="📦" />
        <StatCard label="Items Processing" value={stats.pendingJobs ?? 0} sub="In queue right now" icon="⏱" subColor="var(--accent-cyan)" />
        <StatCard label="Zone Capacity" value={`${stats.capacityPct ?? 0}%`} sub={<Progress pct={stats.capacityPct ?? 0} />} icon="📐" />
        <StatCard
          label="Devices Online"
          value={stats.devicesOnline ?? 0}
          sub={stats.devicesOffline ? `${stats.devicesOffline} OFFLINE` : "ALL HEALTHY"}
          subColor={stats.devicesOffline ? "var(--accent-red)" : "var(--accent-green)"}
          icon="🛰"
        />
      </div>

      <div className="dash-lower-grid">
        <div className="dash-lower-left">
          <div className="dash-card">
            <div className="dash-card-title">Recent Operations</div>
            {recentPicks.length === 0 ? (
              <div className="text-fade" style={{ padding: "16px 0", textAlign: "center", fontSize: 12 }}>
                No recent operations
              </div>
            ) : (
              <div className="dash-op-list">
                {recentPicks.map((p, i) => (
                  <div className="dash-op-row" key={i}>
                    <span className="dash-op-icon">{p.eventType === "pick" ? "\u2212" : "+"}</span>
                    <div style={{ flex: 1 }}>
                      <div className="mono" style={{ fontWeight: 700, fontSize: 12.5 }}>{p.boxId}</div>
                      <div className="text-fade" style={{ fontSize: 10.5 }}>
                        {p.zone} &middot; {p.eventType?.toUpperCase()}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 11 }}>{p.worker}</div>
                      <div className="text-fade mono" style={{ fontSize: 10 }}>{p.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="dash-card">
            <div className="dash-card-title">System Alerts</div>
            {alerts.length === 0 ? (
              <div className="text-fade" style={{ padding: "16px 0", textAlign: "center", fontSize: 12 }}>
                No active alerts
              </div>
            ) : (
              <div className="dash-op-list">
                {alerts.map((a, i) => (
                  <div className="dash-alert-row" key={i} data-level={a.level}>
                    <div style={{ fontWeight: 700, fontSize: 12 }}>{a.title}</div>
                    <div className="text-fade" style={{ fontSize: 11 }}>{a.message}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="dash-chat-card">
          <div className="dash-chat-header">
            <span className="dash-chat-avatar">🤖</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: 12.5 }}>Warehouse AI</div>
              <div style={{ fontSize: 10, color: ollamaReachable ? "var(--accent-green)" : "var(--accent-red)" }}>
                {ollamaReachable ? "\u25cf Model reachable" : "\u25cf Model unreachable"}
              </div>
            </div>
          </div>
          <div className="dash-chat-log">
            {chatMessages.map((m, i) => (
              <div key={i} className={`dash-chat-bubble ${m.role}`}>
                {m.text}
              </div>
            ))}
            {chatBusy && <div className="dash-chat-bubble assistant text-fade">Thinking&hellip;</div>}
          </div>
          <div className="dash-chat-input-row">
            <input
              placeholder="Ask about boxes, zones, or devices..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendChat()}
            />
            <button onClick={sendChat} disabled={chatBusy}>
              ➤
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, icon, subColor }) {
  return (
    <div className="dash-stat-card">
      <div className="dash-stat-top">
        <span className="text-fade" style={{ fontSize: 10.5, letterSpacing: 0.5 }}>{label.toUpperCase()}</span>
        <span style={{ opacity: 0.35, fontSize: 15 }}>{icon}</span>
      </div>
      <div className="dash-stat-value">{value}</div>
      <div style={{ fontSize: 10, color: subColor || "var(--text-muted)" }}>{sub}</div>
    </div>
  );
}

function Progress({ pct }) {
  return (
    <div className="dash-progress-track">
      <div className="dash-progress-fill" style={{ width: `${Math.min(100, pct)}%` }} />
    </div>
  );
}
