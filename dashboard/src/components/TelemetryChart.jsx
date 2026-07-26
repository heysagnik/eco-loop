import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

const BASELINE_COLOR = "#f59e0b";
const AI_COLOR = "#10b981";
const TEMP_COLOR = "#0284c7";

const tooltipStyle = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: "10px",
  fontSize: "11px",
  boxShadow: "0 10px 25px -5px rgba(0,0,0,0.08)",
};

const axisTick = { fontSize: 10, fill: "#64748b" };

const VISIBLE_TICKS = 10;

export default function TelemetryChart({ ticks = [] }) {
  const chartData = ticks.slice(-VISIBLE_TICKS).map((d) => ({
    t: `T+${d.sim_time_hours.toFixed(1)}h`,
    baseline_kw: Number((d.baseline_kw || d.facility_electricity_kw || 0).toFixed(2)),
    ai_kw: Number((d.ai_kw || d.facility_electricity_kw || 0).toFixed(2)),
    ai_temp: Number((d.ai_temp_c || 22.0).toFixed(1)),
  }));

  return (
    <div className="ui-card chart-widget">
      <div className="card-title-header">
        <span>Baseline vs. AI Demand Profile — Real-Time Comparison</span>
        <span className="badge-pill cyan" style={{ fontSize: "10px", padding: "2px 8px" }}>LIVE 50ms</span>
      </div>

      {chartData.length === 0 ? (
        <div
          className="chart-area-box"
          style={{
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-muted)",
            fontSize: "12px",
            border: "1px dashed var(--card-border)",
            borderRadius: "8px",
          }}
        >
          <div>Ready to benchmark.</div>
          <div style={{ fontSize: "11px", opacity: 0.7, marginTop: "4px" }}>
            Click <strong>"▶ Run Baseline vs. AI"</strong> to start live execution.
          </div>
        </div>
      ) : (
        <>
          <div className="chart-area-box" style={{ height: "68%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="t" stroke="#94a3b8" tick={axisTick} />
                <YAxis stroke="#94a3b8" tick={axisTick} unit=" kW" />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: "4px" }} />
                <Bar dataKey="baseline_kw" name="Baseline (kW)" fill={BASELINE_COLOR} radius={[3, 3, 0, 0]} />
                <Bar dataKey="ai_kw" name="AI Agent (kW)" fill={AI_COLOR} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-area-box" style={{ height: "26%", marginTop: 4 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 6, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="t" stroke="#94a3b8" tick={axisTick} />
                <YAxis stroke="#94a3b8" tick={axisTick} unit="°C" domain={["auto", "auto"]} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}°C`, "AI Zone Temp"]} />
                <Line type="monotone" dataKey="ai_temp" name="AI Zone Temp (°C)" stroke={TEMP_COLOR} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      <div className="scientific-advisory-box">
        <strong>Engineering Advisory:</strong> AI dynamic setpoints exploit building thermal mass during peak solar load to reduce power draw while preserving ASHRAE 55 thermal comfort.
      </div>
    </div>
  );
}
