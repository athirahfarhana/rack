import React from "react";
import DashboardTab from "../views/DashboardTab";
import LiveTab from "../views/LiveTab";
import MappingTab from "../views/MappingTab";
import SettingsTab from "../views/SettingsTab";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "live", label: "Live" },
  { id: "mapping", label: "Mapping" },
  { id: "settings", label: "Settings" },
];

export default function DigitalTwinTabs(props) {
  const { activeTab, setActiveTab } = props;

  return (
    <div className="panel twin-panel">
      <div className="twin-tabbar">
        <div className="twin-tabbar-title">
          <span className="dot" style={{ background: "var(--accent-cyan)" }} />
          Real-Time Digital Twin Grid Map <span className="text-fade">(Drag / Drop Modules)</span>
        </div>
        <div className="twin-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`twin-tab${activeTab === t.id ? " active" : ""}`}
              onClick={() => setActiveTab(t.id)}
            >
              {t.id === "live" && <span className="live-dot" />}
              {t.label.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="twin-tab-body">
        {activeTab === "dashboard" && <DashboardTab {...props} />}
        {activeTab === "live" && <LiveTab {...props} />}
        {activeTab === "mapping" && <MappingTab {...props} />}
        {activeTab === "settings" && <SettingsTab {...props} />}
      </div>
    </div>
  );
}
