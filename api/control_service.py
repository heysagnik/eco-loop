
from __future__ import annotations

import asyncio
import bisect
import os
import threading
import time
import uuid

from agent.llm_client import get_llm_client
from agent.mcp_orchestrator import MCPToolExecutor
from agent.orchestrator import Orchestrator
from agent.rule_controller import run_control_step as run_rule_control_step
from agent.tools import ToolLayer
from api import db
from simulation.runner import MODELS_DIR, SimulationRunner

MODE_AI = "ai"
MODE_BASELINE = "baseline"

TOOL_TRANSPORT = os.environ.get("TOOL_TRANSPORT", "mcp")
MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp/")
BASELINE_OUTPUT_DIR = MODELS_DIR / "out_baseline"


class ControlLoopService:
    def __init__(self, control_interval_minutes: int = 15) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self.mode = MODE_AI

        self.runner = SimulationRunner(control_interval_minutes=control_interval_minutes, lockstep=True)
        self.tool_layer = ToolLayer(self.runner)
        self.orchestrator = Orchestrator(get_llm_client(), self.tool_layer)

        self.db_conn = db.connect()
        db.reset_database(self.db_conn)  

        self._thread: threading.Thread | None = None
        self._mcp_executor: MCPToolExecutor | None = None
        self._sim_started = False

        
        self._loop: asyncio.AbstractEventLoop | None = None
        self._version = 0
        self._waiters: set[asyncio.Event] = set()

        
        self._baseline_profile: list[tuple[float, float, float, float]] = []
        
        
        self._baseline_times: list[float] = []
        self._baseline_lock = threading.Lock()

        
        self._live_turn: dict = {"sim_time_hours": None, "calls": []}
        self._live_lock = threading.Lock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def get_live_turn(self) -> dict:
        with self._live_lock:
            return {"sim_time_hours": self._live_turn["sim_time_hours"], "calls": list(self._live_turn["calls"])}

    async def wait_for_change(self, since_version: int, timeout: float = 25.0) -> int:
        
        if self._version != since_version:
            return self._version
        event = asyncio.Event()
        self._waiters.add(event)
        try:
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        finally:
            self._waiters.discard(event)
        return self._version

    def _notify(self) -> None:
        
        self._version += 1
        if self._loop is None:
            return
        for event in list(self._waiters):
            self._loop.call_soon_threadsafe(event.set)

    def _publish_tool_call(self, entry: dict) -> None:
        with self._live_lock:
            self._live_turn["calls"].append(entry)
        self._notify()

    def start(self) -> None:
        
        if TOOL_TRANSPORT == "mcp":
            self._mcp_executor = MCPToolExecutor(MCP_URL)
            self.orchestrator.set_tool_executor(self._mcp_executor)
        self._thread = threading.Thread(target=self._control_loop, daemon=True)
        self._thread.start()

    def begin_run(self) -> bool:
        
        if self._sim_started:
            return False
        self.reset_run()
        self._sim_started = True
        self.resume_ai()
        threading.Thread(target=self._run_baseline_pass, daemon=True).start()
        self.runner.start()
        return True

    def _run_baseline_pass(self) -> None:
        
        
        control_interval_minutes = int(self.runner.control_interval_hours * 60)
        baseline_runner = SimulationRunner(
            control_interval_minutes=control_interval_minutes,
            queue_maxsize=100_000,  
            output_dir=BASELINE_OUTPUT_DIR,
        )
        baseline_tools = ToolLayer(baseline_runner)
        baseline_runner.start()

        while True:
            snapshot = baseline_runner.latest_snapshot(timeout=2.0)
            if snapshot is None:
                if not baseline_runner.is_running():
                    break
                continue

            baseline_tools.ingest_snapshot(snapshot)
            run_rule_control_step(baseline_tools, snapshot.sim_time_hours)
            state = baseline_tools.get_current_state()
            core = next((z for z in state.zones if z.zone == "Core_ZN"), state.zones[0])
            with self._baseline_lock:
                self._baseline_profile.append(
                    (snapshot.sim_time_hours, state.facility_electricity_kw, core.air_temp_c, core.pmv)
                )
                self._baseline_times.append(snapshot.sim_time_hours)

    def _lookup_baseline(self, sim_time_hours: float) -> tuple[float, float, float]:
        
        with self._baseline_lock:
            if not self._baseline_profile:
                return 0.0, 22.0, 0.0
            
            
            times = self._baseline_times
            idx = bisect.bisect_left(times, sim_time_hours)
            if idx == 0:
                row = self._baseline_profile[0]
            elif idx == len(times):
                row = self._baseline_profile[-1]
            else:
                before, after = self._baseline_profile[idx - 1], self._baseline_profile[idx]
                row = before if (sim_time_hours - before[0]) <= (after[0] - sim_time_hours) else after
            return row[1], row[2], row[3]

    def reset_run(self) -> bool:
        
        if self._sim_started:
            return False
        self.run_id = uuid.uuid4().hex[:8]
        db.reset_database(self.db_conn)
        return True

    def revert_to_baseline(self) -> None:
        self.mode = MODE_BASELINE

    def resume_ai(self) -> None:
        self.mode = MODE_AI

    def _control_loop(self) -> None:
        while True:
            snapshot = self.runner.latest_snapshot(timeout=2.0)
            if snapshot is None:
                if self._sim_started and not self.runner.is_running():
                    break
                time.sleep(0.1)
                continue

            self.tool_layer.ingest_snapshot(snapshot)

            
            with self._live_lock:
                self._live_turn = {"sim_time_hours": snapshot.sim_time_hours, "calls": []}
            self._notify()

            
            baseline_kw, baseline_temp, baseline_pmv = self._lookup_baseline(snapshot.sim_time_hours)

            
            if self.mode == MODE_AI:
                ai_result = self.orchestrator.run_control_step(on_tool_call=self._publish_tool_call)
                rationale = ai_result.rationale
                actions = ai_result.actions
                mcp_calls = ai_result.tool_calls
                degraded = ai_result.degraded
            else:
                
                
                run_rule_control_step(self.tool_layer, snapshot.sim_time_hours)
                rationale = "Baseline schedule active (manual override)"
                actions = []
                mcp_calls = []
                degraded = False

            ai_state = self.tool_layer.get_current_state()
            ai_kw = ai_state.facility_electricity_kw
            ai_core = next((z for z in ai_state.zones if z.zone == "Core_ZN"), ai_state.zones[0])
            ai_temp = ai_core.air_temp_c
            ai_pmv = ai_core.pmv

            tick = {
                "sim_time_hours": snapshot.sim_time_hours,
                "outdoor_air_temp_c": snapshot.outdoor_air_temp_c,
                "baseline_kw": baseline_kw,
                "baseline_temp_c": baseline_temp,
                "baseline_pmv": baseline_pmv,
                "ai_kw": ai_kw,
                "ai_temp_c": ai_temp,
                "ai_pmv": ai_pmv,
                "facility_electricity_kw": ai_kw,
                "mode": self.mode,
                "rationale": rationale,
                "degraded": degraded,
                "zones": [z.model_dump() for z in ai_state.zones],
                "actions": actions,
                "mcp_calls": mcp_calls,
            }

            db.insert_tick(self.db_conn, self.run_id, tick)
            with self._live_lock:
                self._live_turn = {"sim_time_hours": None, "calls": []}
            self._notify()

            
            self.runner.decision_applied()
