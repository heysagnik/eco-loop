import React from "react";

export default function MainTemperatureGauge({ outdoorTemp = 18.5, humidity = 45, meanTemp = 24.2 }) {
  const minTemp = 0;
  const maxTemp = 40;
  const clampedTemp = Math.min(Math.max(meanTemp, minTemp), maxTemp);
  const percentage = (clampedTemp - minTemp) / (maxTemp - minTemp);

  const needleAngle = -90 + percentage * 180;
  const isWarm = meanTemp > 25;

  return (
    <div className="ui-card gauge-card">
      <div className="card-title-header" style={{ width: "100%" }}>
        <span>Building Mean Temp</span>
        <span className="badge-pill emerald" style={{ fontSize: "10px", padding: "2px 8px" }}>LIVE</span>
      </div>

      <div className="gauge-location-meta">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
        Chicago O'Hare Office Small — Standard 90.1
      </div>

      <div className="gauge-wrapper">
        <svg className="gauge-svg" viewBox="0 0 200 110">
          <defs>
            <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#38bdf8" />
              <stop offset="50%" stopColor="#10b981" />
              <stop offset="85%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#ef4444" />
            </linearGradient>
          </defs>
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#e2e8f0"
            strokeWidth="14"
            strokeLinecap="round"
          />
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="url(#gaugeGrad)"
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray="251.2"
            strokeDashoffset={251.2 * (1 - percentage)}
          />
          <g transform={`translate(100, 100) rotate(${needleAngle})`}>
            <line x1="0" y1="-50" x2="0" y2="-72" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
            <circle cx="0" cy="-80" r="6" fill="#ffffff" stroke="#0f172a" strokeWidth="3" />
          </g>
        </svg>

        <div className="gauge-readout-center">
          <div className="gauge-val-big">{meanTemp.toFixed(1)}°C</div>
        </div>
      </div>

      <div style={{ marginTop: "6px" }}>
        <span className={`badge-pill ${isWarm ? "amber" : "emerald"}`}>
          ● {isWarm ? "Peak Warmth" : "Optimal Comfort"}
        </span>
      </div>

      <div className="dark-pill-bar">
        <div className="dark-pill-item">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" />
          </svg>
          <div>
            <div className="label">Outdoor Temp</div>
            <div className="val">{outdoorTemp.toFixed(1)}°C</div>
          </div>
        </div>
        <div style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.15)" }} />
        <div className="dark-pill-item">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
          </svg>
          <div>
            <div className="label">Humidity</div>
            <div className="val">{humidity.toFixed(0)}%</div>
          </div>
        </div>
      </div>
    </div>
  );
}
