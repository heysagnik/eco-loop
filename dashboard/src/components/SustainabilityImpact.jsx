import React from "react";

export default function SustainabilityImpact({ summary = {} }) {
  const tickCount = summary?.tick_count || 0;
  const baselineKwh = summary?.baseline_kwh || 0.0;
  const aiKwh = summary?.ai_kwh || summary?.total_electricity_kwh || 0.0;
  const savingsPct = summary?.savings_pct ?? (baselineKwh > 0 ? ((baselineKwh - aiKwh) / baselineKwh * 100) : 0.0);
  const netSavingsKwh = baselineKwh - aiKwh;
  const carbonOffsetKg = summary?.carbon_offset_kg ?? (netSavingsKwh * 0.385);
  const isDeficit = netSavingsKwh < 0;

  return (
    <div className="ui-card">
      <div className="card-title-header">
        <span>Sustainability & Impact</span>
        <span className="badge-pill emerald" style={{ fontSize: "10px", padding: "2px 8px" }}>REAL-TIME</span>
      </div>

      <div className="sustainability-grid">
        <div className={`sustainability-stat-box energy ${isDeficit ? "deficit" : ""}`}>
          <div className="stat-box-title">ENERGY SAVINGS</div>
          <div className="stat-box-num">{savingsPct >= 0 ? "+" : ""}{savingsPct.toFixed(1)}%</div>
          <div className="stat-box-sub">Vs. Fixed Baseline</div>
        </div>

        <div className={`sustainability-stat-box carbon ${isDeficit ? "deficit" : ""}`}>
          <div className="stat-box-title">{isDeficit ? "CARBON EXCESS" : "CARBON AVOIDED"}</div>
          <div className="stat-box-num">
            {carbonOffsetKg.toFixed(1)} <span style={{ fontSize: "11px", fontWeight: 700 }}>kg CO₂e</span>
          </div>
          <div className="stat-box-sub">Offset Grid Intensity</div>
        </div>
      </div>

      <div className="comfort-metrics-rows">
        <div className="comfort-metric-row">
          <span className="name">Total Steps Processed</span>
          <span className="val">{tickCount} Ticks</span>
        </div>
        <div className="comfort-metric-row">
          <span className="name">Baseline Energy Draw</span>
          <span className="val">{baselineKwh.toFixed(2)} kWh</span>
        </div>
        <div className="comfort-metric-row">
          <span className="name">AI Controlled Energy Draw</span>
          <span className="val">{aiKwh.toFixed(2)} kWh</span>
        </div>
        <div className="comfort-metric-row">
          <span className="name">Cumulative Net Savings</span>
          <span className="val" style={{ color: isDeficit ? "var(--accent-rose)" : "var(--accent-emerald)" }}>
            {netSavingsKwh >= 0 ? "" : "-"}{Math.abs(netSavingsKwh).toFixed(2)} kWh
          </span>
        </div>
      </div>
    </div>
  );
}
