import React, { useEffect, useRef, useState } from "react";

const TOOL_ICON = {
  get_current_state: "📊",
  get_comfort_bounds: "📐",
  get_recent_history: "🕘",
  propose_setpoint_change: "🎛️",
};

function summarizeArgs(args) {
  if (!args || Object.keys(args).length === 0) return "";
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "number" ? v : `"${v}"`}`)
    .join(", ");
}

function parseResultObject(call) {
  try {
    const text = call.response?.result?.content?.[0]?.text;
    if (!text) return null;
    const parsed = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null ? parsed : null;
  } catch {
    return null;
  }
}

function summarizeResult(parsed) {
  if (!parsed) return null;
  if (typeof parsed.accepted === "boolean") {
    return parsed.accepted
      ? `accepted → ${parsed.applied_heating_c}° / ${parsed.applied_cooling_c}°C`
      : `rejected — ${parsed.reason}`;
  }
  if (typeof parsed.pmv === "number") return `pmv ${parsed.pmv.toFixed(2)}`;
  if (typeof parsed.occupied === "boolean") {
    return parsed.occupied ? "occupied" : "unoccupied";
  }
  return null;
}

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "true" : "false";
  if (Array.isArray(v)) return v.length === 0 ? "[]" : v.map(formatValue).join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function formatZoneName(zoneRaw) {
  if (!zoneRaw) return "Global";
  return zoneRaw
    .replace("Perimeter_ZN_", "Perimeter ")
    .replace("Core_ZN", "Core")
    .replace("_", " ");
}

function DetailSection({ label, entries }) {
  if (!entries || entries.length === 0) return null;
  return (
    <div className="mcp-detail-section">
      <div className="mcp-detail-label">{label}</div>
      <div className="mcp-detail-kv">
        {entries.map(([k, v]) => (
          <div key={k} className="mcp-detail-row">
            <span className="mcp-detail-key">{k}</span>
            <span className="mcp-detail-val">{formatValue(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ToolCallLine({ call, index, animate }) {
  const [open, setOpen] = useState(false);
  const name = call.request?.params?.name;
  const args = call.request?.params?.arguments;
  const resultObj = parseResultObject(call);
  const resultSummary = summarizeResult(resultObj);
  const failed = resultSummary?.startsWith("rejected");

  return (
    <div
      className={`mcp-live-line ${animate ? "msg-in" : ""}`}
      style={animate ? { animationDelay: `${index * 110}ms` } : undefined}
    >
      <button className="mcp-live-line-head" onClick={() => setOpen((o) => !o)}>
        <span className="mcp-live-icon">{TOOL_ICON[name] || "🔧"}</span>
        <span className="mcp-live-name">{name}</span>
        <span className={`mcp-live-result ${resultSummary ? (failed ? "fail" : "ok") : "pending"}`}>
          {resultSummary || "…"}
        </span>
        {args && Object.keys(args).length > 0 && (
          <span className="mcp-live-args">{summarizeArgs(args)}</span>
        )}
      </button>
      {open && (
        <div className="mcp-detail">
          <DetailSection label="Arguments" entries={args ? Object.entries(args) : []} />
          <DetailSection label="Result" entries={resultObj ? Object.entries(resultObj) : []} />
        </div>
      )}
    </div>
  );
}

function ToolCallsAccordion({ calls, animate }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="mcp-accordion">
      <button className="mcp-accordion-head" onClick={() => setIsOpen(!isOpen)}>
        <span className={`mcp-accordion-caret ${isOpen ? "open" : ""}`}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </span>
        <span className="mcp-accordion-title">Tool Calls</span>
        <span className="mcp-accordion-count">({calls.length})</span>
      </button>
      {isOpen && (
        <div className="mcp-live-feed" style={{ padding: "6px 8px 8px 8px" }}>
          {calls.map((call, j) => (
            <ToolCallLine key={j} call={call} index={j} animate={animate} />
          ))}
        </div>
      )}
    </div>
  );
}

function LiveTurnCard({ liveTurn }) {
  if (liveTurn.sim_time_hours == null || liveTurn.calls.length === 0) return null;

  return (
    <div className="agent-turn">
      <div className="agent-turn-timestamp">
        <span>T + {liveTurn.sim_time_hours.toFixed(1)}h</span>
        <span className="badge-pill ai" style={{ fontSize: "9px", padding: "2px 7px" }}>
          LIVE
        </span>
      </div>

      <div className="mcp-live-feed">
        {liveTurn.calls.map((call, j) => (
          <ToolCallLine key={j} call={call} index={j} animate />
        ))}
      </div>

      <div className="agent-thinking">
        <span className="agent-thinking-dot" />
        <span className="agent-thinking-dot" />
        <span className="agent-thinking-dot" />
        agent is deciding…
      </div>
    </div>
  );
}

function AgentTurn({ tick, animate }) {
  const calls = tick.mcp_calls || [];
  const actions = tick.actions || [];

  return (
    <div className="agent-turn">
      <div className="agent-turn-timestamp">
        <span>T + {tick.sim_time_hours.toFixed(1)}h</span>
        <span className={`badge-pill ${tick.mode}`} style={{ fontSize: "9px", padding: "2px 7px" }}>
          {tick.mode?.toUpperCase()}
        </span>
      </div>

      {calls.length > 0 && (
        <ToolCallsAccordion calls={calls} animate={animate} />
      )}

      <div
        className={`chat-bubble ai ${tick.degraded ? "degraded" : ""} ${animate ? "msg-in" : ""}`}
        style={animate ? { animationDelay: `120ms` } : undefined}
      >
        <div className="chat-bubble-body">
          <div className="chat-bubble-text">{tick.rationale}</div>
          {actions.length > 0 && (
            <div className="chat-bubble-badges">
              {actions.map((a, j) => (
                <span key={j} className={`zone-badge ${a.result?.accepted ? "ok" : "fail"}`}>
                  {formatZoneName(a.request?.zone)}: {a.result?.accepted ? "ACCEPTED" : "REJECTED"}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentMCPInspector({
  ticks = [],
  mode = "ai",
  benchmarkStatus = "idle",
  liveTurn = { sim_time_hours: null, calls: [] },
  onStartBenchmark,
  killSwitch,
}) {
  const feedRef = useRef(null);
  const isIdle = benchmarkStatus === "idle";
  const buttonLabel =
    benchmarkStatus === "starting"
      ? "Starting…"
      : benchmarkStatus === "running"
      ? "Running…"
      : "▶ Run Baseline vs. AI";

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [ticks.length, liveTurn.calls.length]);

  return (
    <div className="right-inspector-panel">
      <div className="card-title-header">
        <span>Agent Intelligence & Eco-MCP</span>
        <span className={`badge-pill ${mode}`}>{mode.toUpperCase()}</span>
      </div>

      <div className="inspector-actions-group">
        <button className="action-btn-primary" onClick={onStartBenchmark} disabled={!isIdle}>
          {buttonLabel}
        </button>
        {killSwitch}
      </div>

      <div className="log-feed-container chat-feed" ref={feedRef}>
        {ticks.length === 0 && (
          <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "24px", fontSize: "12px" }}>
            Click <strong>"▶ Run Baseline vs. AI"</strong> to start live execution.
          </div>
        )}

        {ticks.map((tick, i) => (
          <AgentTurn key={tick.sim_time_hours ?? i} tick={tick} animate={i === ticks.length - 1} />
        ))}

        <LiveTurnCard liveTurn={liveTurn} />
      </div>
    </div>
  );
}
