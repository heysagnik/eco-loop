import React from "react";

export default function ZoneListWidget({ zones = [] }) {
  const zoneIcons = {
    Core_ZN: "🏢",
    Perimeter_ZN_1: "🌅",
    Perimeter_ZN_2: "☀️",
    Perimeter_ZN_3: "🌇",
    Perimeter_ZN_4: "🌙",
  };

  const defaultZones = zones.length > 0 ? zones : [
    { zone: "Core_ZN", air_temp_c: 22.4, relative_humidity_pct: 42, heating_setpoint_c: 21.0, cooling_setpoint_c: 24.0, pmv: 0.1 },
    { zone: "Perimeter_ZN_1", air_temp_c: 23.1, relative_humidity_pct: 45, heating_setpoint_c: 21.0, cooling_setpoint_c: 24.0, pmv: 0.2 },
    { zone: "Perimeter_ZN_2", air_temp_c: 22.8, relative_humidity_pct: 40, heating_setpoint_c: 21.0, cooling_setpoint_c: 24.0, pmv: 0.0 },
    { zone: "Perimeter_ZN_3", air_temp_c: 23.5, relative_humidity_pct: 41, heating_setpoint_c: 21.0, cooling_setpoint_c: 24.0, pmv: 0.3 },
    { zone: "Perimeter_ZN_4", air_temp_c: 22.1, relative_humidity_pct: 44, heating_setpoint_c: 21.0, cooling_setpoint_c: 24.0, pmv: -0.1 },
  ];

  return (
    <div className="ui-card zone-list-widget">
      <div className="card-title-header">
        <span>Building Zones (5)</span>
        <span className="badge-pill indigo" style={{ fontSize: "10px", padding: "2px 8px" }}>ACTIVE</span>
      </div>

      <div className="zone-items-container">
        {defaultZones.map((z, idx) => {
          const icon = zoneIcons[z.zone] || "📍";
          const displayName = z.zone.replace("_", " ");
          const heat = z.heating_setpoint_c > 0 ? z.heating_setpoint_c : 21.0;
          const cool = z.cooling_setpoint_c > 0 ? z.cooling_setpoint_c : 24.0;
          const isOptimal = Math.abs(z.pmv || 0) <= 0.5;

          return (
            <div key={idx} className="zone-item-row">
              <div className="zone-info-left">
                <div className="zone-icon-box">{icon}</div>
                <div>
                  <div className="zone-name-title">{displayName}</div>
                  <div className="zone-sub-info">
                    Set: {heat.toFixed(1)}° / {cool.toFixed(1)}°C
                  </div>
                </div>
              </div>

              <div className="zone-temp-right">
                <div className="zone-temp-num">{z.air_temp_c?.toFixed(1)}°C</div>
                <div className="zone-status-tag" style={{ color: isOptimal ? "var(--accent-emerald)" : "var(--accent-amber)" }}>
                  {isOptimal ? "OPTIMAL" : "ADJUSTING"}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
