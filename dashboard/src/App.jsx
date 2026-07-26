import { useEffect, useRef, useState } from "react";
import {
  startPolling,
  startBenchmark,
} from "./api.js";
import MainTemperatureGauge from "./components/MainTemperatureGauge.jsx";
import ComfortDiamondCard from "./components/ComfortDiamondCard.jsx";
import ZoneListWidget from "./components/ZoneListWidget.jsx";
import SustainabilityImpact from "./components/SustainabilityImpact.jsx";
import TelemetryChart from "./components/TelemetryChart.jsx";
import AgentMCPInspector from "./components/AgentMCPInspector.jsx";
import KillSwitch from "./components/KillSwitch.jsx";

export default function App() {
  const [ticks, setTicks] = useState([]);
  const [summary, setSummary] = useState({ tick_count: 0, total_electricity_kwh: 0 });
  const [mode, setMode] = useState("ai");
  const [benchmarkStatus, setBenchmarkStatus] = useState("idle");
  const [liveTurn, setLiveTurn] = useState({ sim_time_hours: null, calls: [] });
  const pollerRef = useRef(null);

  useEffect(() => {
    pollerRef.current = startPolling(({ history, summary: sumRes, mode: m, liveTurn: lt }) => {
      setTicks(history);
      setSummary(sumRes);
      setMode(m);
      setLiveTurn(lt);
    });

    return () => {
      pollerRef.current?.stop();
    };
  }, []);

  const handleStartBenchmark = async () => {
    if (benchmarkStatus !== "idle") return;
    setBenchmarkStatus("starting");
    await startBenchmark();
    setBenchmarkStatus("running");
  };

  const latestTick = ticks[ticks.length - 1];
  const outdoorTemp = latestTick?.outdoor_air_temp_c ?? 18.5;
  const zones = latestTick?.zones ?? [];
  const coreZone = zones.find((z) => z.zone === "Core_ZN") || zones[0];
  const meanTemp = coreZone?.air_temp_c ?? 23.4;
  const humidity = coreZone?.relative_humidity_pct ?? 44;
  const pmv = coreZone?.pmv ?? 0.12;
  const ppdPct = coreZone?.ppd_pct ?? 5.2;

  return (
    <div className="app-container">
      <header className="top-navbar">
        <div className="brand-group">
          <div className="brand-dot" title="Live System Active" />
          <div>
            <div className="brand-title">Eco-Loop Intelligence</div>
            <div className="brand-subtitle">Real-Time Autonomous HVAC Control & Eco-MCP Protocol Inspector</div>
          </div>
        </div>
        <div className="nav-actions">
          <span className={`badge-pill ${mode}`}>{mode.toUpperCase()}</span>
        </div>
      </header>

      <main className="dashboard-main-grid">
        <div className="left-telemetry-grid">
          <div className="grid-row-top">
            <MainTemperatureGauge outdoorTemp={outdoorTemp} humidity={humidity} meanTemp={meanTemp} />
            <ComfortDiamondCard pmv={pmv} ppdPct={ppdPct} />
            <SustainabilityImpact summary={summary} />
          </div>

          <div className="grid-row-bottom">
            <ZoneListWidget zones={zones} />
            <TelemetryChart ticks={ticks} />
          </div>
        </div>

        <AgentMCPInspector
          ticks={ticks}
          mode={mode}
          benchmarkStatus={benchmarkStatus}
          liveTurn={liveTurn}
          onStartBenchmark={handleStartBenchmark}
          killSwitch={
            benchmarkStatus !== "idle" && <KillSwitch mode={mode} onModeChange={setMode} />
          }
        />
      </main>
    </div>
  );
}
