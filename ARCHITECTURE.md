# Eco-Loop — System Architecture

Closed-loop LLM-supervised EnergyPlus building energy control.

## 1. System overview

```
┌─────────────────┐   pyenergyplus callbacks   ┌──────────────────────────┐
│   EnergyPlus    │◄────────────────────────── │   ControlLoopService     │
│ (co-sim, own    │   actuator writes          │   (api/control_service)  │
│  background     │──────────────────────────► │                          │
│  thread)        │   sensor snapshot          │  ToolLayer (validate/    │
└─────────────────┘                            │  clamp every write)      │
                                               │           │              │
                                               │           ▼              │
                                               │  Orchestrator (ReAct)    │
                                               │           │              │
                                               │      MCP tool-layer      │
                                               │           |              │
                                               │           │              │
                                               │           ▼              │
                                               │   LLM (Ollama, local)    │
                                               │                          │
                                               │  SQLite (per-tick log)   │
                                               └───────────┬──────────────┘
                                                           │ HTTP long-poll
                                                           ▼
                                                   React Dashboard (Vite)
```

Two EnergyPlus instances run concurrently, each on its own thread with its own
output directory: a **baseline pass** (deterministic rule controller, no LLM,
runs fast) and the **live AI-driven run**. The dashboard compares AI telemetry
against the baseline's reference profile at matching simulated timestamps,
instead of comparing a run against itself.

## 2. Tool-calling architecture

Every actuator write is mediated by `agent/tools.py::ToolLayer`, never called
directly by the LLM. Four tools are exposed, identical whether dispatched
in-process or over MCP:

| Tool | Effect |
|---|---|
| `get_current_state` | Zone temps, RH, PMV/PPD, outdoor conditions, facility kW (read-only) |
| `get_comfort_bounds` | Live occupancy + ASHRAE 55 comfort band for a zone (read-only) |
| `get_recent_history` | Last N accepted/rejected decisions (read-only) |
| `propose_setpoint_change` | The only write path — clamped to safe ranges, rate-limited to 2°C/interval, rejected if the heating/cooling deadband collapses |

**Two dispatch paths, same `ToolLayer` instance:**
- **Direct** (`Orchestrator._execute_tool`): plain Python method calls.
- **MCP** (`agent/mcp_orchestrator.py::MCPToolExecutor`, default via
  `TOOL_TRANSPORT=mcp`): the orchestrator's tool calls cross a real MCP
  boundary — `mcp.client.streamable_http` → `ClientSession.call_tool()` against
  `agent/mcp_server.py`'s `FastMCP` server, mounted at `/mcp` in the same
  FastAPI process (`api/app.py`) and backed by the *same* live `ToolLayer` the
  direct path uses. It's not a separate demo copy of the tools.

The orchestrator (`agent/orchestrator.py`) runs a ReAct loop per control
interval: Observe (`get_current_state`) → Reason (LLM rationale) → Act
(`propose_setpoint_change`) → Validate (`ToolLayer` clamps/rejects). A
**comfort safety net** runs after every step: any zone left untouched by an
*accepted* LLM action that is either occupied-and-out-of-band or sitting on an
invalid setpoint pair gets a corrective proposal through the same validated
path — logged as a normal action (`source: comfort_safety_net`), not applied
silently. This catches both "LLM concluded no change needed but was wrong" and
"LLM's own proposals kept getting rejected, leaving the zone uncorrected."

Every tool call — LLM-issued or safety-net — is published to the dashboard the
instant it resolves (`on_tool_call` hook → `ControlLoopService`'s live-turn
buffer → HTTP long-poll), so the reasoning feed shows calls streaming in live
rather than only after the full multi-turn step finishes.

## 3. Prompt engineering strategy

`agent/schemas.py`'s `SYSTEM_PROMPT` evolved through direct empirical testing
against the running Ollama server, not guesswork:

- **Forced tool_choice doesn't work.** `tool_choice="required"` or a named
  function are silently ignored by Ollama's OpenAI-compatible layer for this
  model class — it falls back to a plain-text completion with no error. Every
  turn uses `tool_choice="auto"` instead, paired with an explicit imperative
  in the user message; a nudge message is injected if no proposal has landed
  by turn `MAX_TURNS-2`.
- **Explicit numeric guardrails, not vague guidance.** Early runs showed the
  model proposing `cooling_setpoint_c <= heating_setpoint_c` repeatedly (every
  call rejected, no proposal ever landing). The prompt now states the deadband
  rule, valid ranges, and a guaranteed-safe fallback pair explicitly.
- **Occupancy must be checked, not assumed.** The model initially reused
  "typical occupied setpoints" from its own prior turn regardless of the
  actual time of day. The workflow now requires calling `get_comfort_bounds`
  for every zone before proposing anything for it, and ties the setpoint
  choice directly to that call's live `occupied` result.
- **Framed as a competition against a known baseline.** The prompt tells the
  model it's benchmarked against a fixed-schedule controller and that
  reproducing that schedule exactly earns zero savings — it must use live
  telemetry (`get_current_state`, `outdoor_air_temp_c`, PMV) the fixed
  schedule ignores, while never leaving comfort/safety bounds.
- **Rationale text is the model's own**, not app-side string manipulation. An
  earlier version post-processed the rationale with brittle substring
  filters tuned to one model's leakage patterns (`"Hypothetical"`, `"Check"`,
  hardcoded fallback text); this was removed once found to sometimes replace
  legitimate reasoning with the fallback string. `agent/llm_client.py` strips
  only `<think>...</think>` blocks (structural, model-agnostic).

## 4. Latency management

- **The sim thread never blocks on the LLM.** `SimulationRunner` (live mode)
  applies whatever is currently in `latest_validated_setpoints`, whenever it
  gets there — a slow LLM call just means the previous safe setpoint holds
  longer, not a stall.
- **The baseline/AI comparison pass uses `lockstep=True` instead**: EnergyPlus
  blocks after each control interval until `decision_applied()` is called, so
  a batch comparison gets correct interval-for-interval application (without
  lockstep, EnergyPlus can simulate months in seconds and vastly outrun an
  LLM-backed consumer, silently invalidating the comparison).
- **Tick cadence is real-time, not artificially paced.** There is no fixed
  30-second-style delay between control intervals — a tick lands exactly as
  fast as the LLM's actual multi-turn response takes, and `decision_applied()`
  fires immediately after.
- **Dashboard updates via HTTP long-polling**, not fixed-interval polling or a
  socket: `GET /state/updates?since=<version>` blocks server-side (via an
  `asyncio.Event`, bridged from the control-loop thread with
  `call_soon_threadsafe`) until a new tick or tool call actually lands, or a
  25s timeout elapses. No wasted requests, no WebSocket infrastructure.
- **Local inference is the real bottleneck, and that's acceptable.** Each
  control interval represents 15 simulated minutes; a local model taking
  1-3 minutes per decision is negligible against that window in a real
  deployment — it only looks slow here because EnergyPlus can simulate
  months of building physics in seconds of wall-clock time, compressing many
  simulated intervals into a short session.

## 5. Handling lengthy simulation logs

EnergyPlus's own verbose output (`.err`, `.eio`, `.bnd`, `.mtr`, `.audit`,
`eplustbl.htm`, etc.) is written directly to per-run output directories
(`models/out/` for the live run, `models/out_baseline/` for the baseline pass,
`models/out/comparison-<id>-{ai,baseline}/` for ad-hoc comparisons) via
EnergyPlus's own `-d <dir>` flag — kept on disk as raw files, not parsed or
summarized by the application. This is a known gap: nothing currently
extracts or surfaces EnergyPlus warnings/errors from these files into the
agent's context or the dashboard. The application's own event stream (control
decisions, tool calls, rejections, degraded ticks) is handled differently and
does not have this gap — every tick is written to SQLite as it happens
(`api/db.py`), so the agent's own reasoning history is always queryable and
never regenerated by re-parsing a log file.

## 6. Data flow (per control interval)

1. `SimulationRunner` publishes a `StateSnapshot` (zone temps, RH, outdoor
   conditions, facility electricity) onto a thread-safe queue.
2. `ControlLoopService._control_loop` picks it up, looks up the matching
   baseline reference point (nearest-neighbor by sim time, from the
   concurrently-running baseline pass), and invokes the orchestrator (AI mode)
   or the rule controller (manual-override baseline mode).
3. The orchestrator's ReAct loop calls tools, gets a final rationale, and the
   comfort safety net corrects any zone left in an unsafe state.
4. The tick (baseline + AI telemetry, rationale, actions, full MCP call trace)
   is inserted into SQLite and the dashboard is notified.
5. `SimulationRunner.decision_applied()` releases EnergyPlus to the next
   interval.

## 7. Known limitations

- No carbon-intensity or IAQ (CO₂) signal — comfort/energy reasoning is based
  on PMV, temperature, and electricity demand only.
- No modified `.idf` snapshot is written per run; setpoints are applied live
  via EMS actuators, not by regenerating the input file.
- EnergyPlus's own log/output files are not parsed or summarized (see §5).
- Savings figures should be read per-run, not as a single validated constant —
  they vary with weather window, time-of-day mix (occupied vs. unoccupied
  hours), and the local model's run-to-run consistency.
