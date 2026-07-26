import React from "react";

export default function ComfortDiamondCard({ pmv = 0.12, ppdPct = 5.2 }) {
  const isOptimal = Math.abs(pmv) <= 0.5;
  const isWarm = pmv > 0.5;

  const clampedPmv = Math.min(Math.max(pmv, -2.0), 2.0);
  const barPercentage = ((clampedPmv - (-2.0)) / (2.0 - (-2.0))) * 100;

  const statusTheme = isOptimal
    ? { color: "var(--accent-emerald)", bg: "var(--accent-emerald-bg)", border: "var(--accent-emerald-border)", label: "GOOD" }
    : isWarm
    ? { color: "var(--accent-amber)", bg: "var(--accent-amber-bg)", border: "var(--accent-amber-border)", label: "WARM" }
    : { color: "var(--accent-cyan)", bg: "var(--accent-cyan-bg)", border: "var(--accent-cyan-border)", label: "COOL" };

  return (
    <div className="ui-card comfort-diamond-card">
      <div className="card-title-header" style={{ width: "100%" }}>
        <span>Thermal Comfort</span>
        <span className="badge-pill emerald" style={{ fontSize: "10px", padding: "2px 8px" }}>ASHRAE 55</span>
      </div>

      <div className="diamond-container">
        <div
          className="diamond-shape"
          style={{
            width: "68px",
            height: "68px",
            background: statusTheme.bg,
            border: `2.5px solid ${statusTheme.border}`,
            transform: "rotate(45deg)",
            borderRadius: "12px",
            position: "absolute",
          }}
        />
        <div className="diamond-content" style={{ position: "relative", zIndex: 2, textAlign: "center" }}>
          <div style={{ fontSize: "18px", fontWeight: 800, color: "var(--text-main)", lineHeight: 1 }}>
            {pmv > 0 ? `+${pmv.toFixed(2)}` : pmv.toFixed(2)}
          </div>
          <div style={{ fontSize: "9px", fontWeight: 800, color: statusTheme.color, letterSpacing: "0.5px", marginTop: "3px" }}>
            {statusTheme.label}
          </div>
        </div>
      </div>

      <div style={{ width: "100%", margin: "2px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: "var(--text-muted)", marginBottom: "4px" }}>
          <span>-2.0 (Cool)</span>
          <span style={{ color: "var(--accent-emerald)", fontWeight: 700 }}>[-0.5 to +0.5]</span>
          <span>+2.0 (Warm)</span>
        </div>
        <div style={{ position: "relative", height: "6px", background: "#e2e8f0", borderRadius: "3px" }}>
          <div
            style={{
              position: "absolute",
              left: "37.5%",
              width: "25%",
              height: "100%",
              background: "var(--accent-emerald-bg)",
              borderRadius: "2px",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${barPercentage}%`,
              top: "-3px",
              width: "12px",
              height: "12px",
              borderRadius: "50%",
              background: statusTheme.color,
              border: "2px solid #ffffff",
              boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
              transform: "translateX(-50%)",
              transition: "left 0.3s ease",
            }}
          />
        </div>
      </div>

      <div className="comfort-subtext">
        {isOptimal
          ? "Occupant thermal comfort is inside optimal ASHRAE 55 neutral zone."
          : "PMV is drifting outside neutral target band."}
      </div>

      <div className="comfort-metrics-rows">
        <div className="comfort-metric-row">
          <span className="name">PMV Target Band</span>
          <span className="val">[-0.5, +0.5]</span>
        </div>
        <div className="comfort-metric-row">
          <span className="name">Dissatisfied (PPD)</span>
          <span className="val">{ppdPct.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  );
}
