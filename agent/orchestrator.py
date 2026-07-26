
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from agent.llm_client import LLMCallError, LLMClient, LLMRateLimitError
from agent.rate_limiter import TokenBucket
from agent.schemas import SYSTEM_PROMPT, TOOL_DEFINITIONS
from agent.tools import MIN_DEADBAND_C, ComfortBounds, CurrentState, ProposeSetpointChange, ToolLayer

ToolExecutor = Callable[[str, dict], dict]

MAX_TURNS = 6


ESTIMATED_TOKENS_PER_CALL = 1200


BUDGET_POLL_INTERVAL_SECONDS = 2.0
BUDGET_MAX_WAIT_SECONDS = 75.0
RATE_LIMIT_BACKOFF_SECONDS = 20.0
RATE_LIMIT_MAX_RETRIES = 3


def _clean_rationale(content: str) -> str:
    
    cleaned = content.strip()
    return cleaned if cleaned else "Setpoints evaluated and updated based on telemetry."


def _jsonrpc_call(name: str, arguments: dict, result: dict) -> dict:
    
    return {
        "request": {
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        "response": {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
        },
    }


@dataclass
class ControlStepResult:
    rationale: str
    actions: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    degraded: bool = False


class Orchestrator:
    def __init__(self, llm_client: LLMClient, tool_layer: ToolLayer,
                 rate_limiter: TokenBucket | None = None, token_budget: TokenBucket | None = None,
                 wait_on_limits: bool = False, tool_executor: ToolExecutor | None = None) -> None:
        self._llm = llm_client
        self._tools = tool_layer
        self._rate_limiter = rate_limiter
        self._token_budget = token_budget
        self._wait_on_limits = wait_on_limits
        
        
        self._tool_executor: ToolExecutor = tool_executor or self._execute_tool

    def set_tool_executor(self, executor: ToolExecutor) -> None:
        self._tool_executor = executor

    def run_control_step(self, on_tool_call: Callable[[dict], None] | None = None) -> ControlStepResult:
        
        if self._rate_limiter and not self._rate_limiter.try_acquire():
            return ControlStepResult(
                rationale="rate limit reached; holding last known-safe setpoints", degraded=True,
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "It is time for the next control interval. Call get_current_state now "
                                        "to observe telemetry before deciding anything."},
        ]
        actions: list[dict] = []
        tool_calls_trace: list[dict] = []
        proposed = False

        for turn in range(MAX_TURNS):
            if self._token_budget and not self._acquire_token_budget():
                return ControlStepResult(
                    rationale="token budget exhausted; holding last known-safe setpoints",
                    actions=actions, tool_calls=tool_calls_trace, degraded=True,
                )

            
            if turn == MAX_TURNS - 2 and not proposed:
                messages.append({
                    "role": "user",
                    "content": "You have not proposed any setpoint change yet. Based on the telemetry you already "
                               "observed, call propose_setpoint_change now for the zone that needs it most.",
                })

            try:
                response = self._call_llm_with_retry(messages, "auto")
            except LLMCallError as exc:
                return ControlStepResult(
                    rationale=f"LLM call failed ({exc}); holding last known-safe setpoints",
                    actions=actions, tool_calls=tool_calls_trace, degraded=True,
                )

            if not response["tool_calls"]:
                rationale = _clean_rationale(response["content"] or "")
                result = ControlStepResult(rationale=rationale, actions=actions, tool_calls=tool_calls_trace)
                self._apply_comfort_safety_net(result, on_tool_call=on_tool_call)
                return result

            messages.append({
                "role": "assistant",
                "content": response["content"],
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                    }
                    for call in response["tool_calls"]
                ],
            })

            for call in response["tool_calls"]:
                result = self._tool_executor(call["name"], call["arguments"])
                jsonrpc_entry = _jsonrpc_call(call["name"], call["arguments"], result)
                tool_calls_trace.append(jsonrpc_entry)
                if on_tool_call:
                    on_tool_call(jsonrpc_entry)
                if call["name"] == "propose_setpoint_change":
                    actions.append({"request": call["arguments"], "result": result})
                    proposed = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, default=str),
                })

        result = ControlStepResult(
            rationale="max tool-call turns reached without a final answer",
            actions=actions, tool_calls=tool_calls_trace,
        )
        self._apply_comfort_safety_net(result, on_tool_call=on_tool_call)
        return result

    def _acquire_token_budget(self) -> bool:
        if self._token_budget.try_acquire(ESTIMATED_TOKENS_PER_CALL):
            return True
        if not self._wait_on_limits:
            return False

        waited = 0.0
        while waited < BUDGET_MAX_WAIT_SECONDS:
            time.sleep(BUDGET_POLL_INTERVAL_SECONDS)
            waited += BUDGET_POLL_INTERVAL_SECONDS
            if self._token_budget.try_acquire(ESTIMATED_TOKENS_PER_CALL):
                return True
        return False

    def _call_llm_with_retry(self, messages: list[dict], tool_choice: str | dict = "auto") -> dict:
        attempts = 0
        while True:
            try:
                response = self._llm.call(messages, TOOL_DEFINITIONS, tool_choice)
            except LLMRateLimitError:
                attempts += 1
                if not self._wait_on_limits or attempts > RATE_LIMIT_MAX_RETRIES:
                    raise
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                continue

            if self._token_budget:
                self._token_budget.adjust(ESTIMATED_TOKENS_PER_CALL - response["total_tokens"])
            return response

    def _apply_comfort_safety_net(self, result: ControlStepResult,
                                   on_tool_call: Callable[[dict], None] | None = None) -> None:
        
        state_raw = self._tool_executor("get_current_state", {})
        state = CurrentState.model_validate(state_raw)
        state_call = _jsonrpc_call("get_current_state", {}, state_raw)
        result.tool_calls.append(state_call)
        if on_tool_call:
            on_tool_call(state_call)
        accepted_zones = {a["request"]["zone"] for a in result.actions if a["result"].get("accepted")}

        for zone in state.zones:
            if zone.zone in accepted_zones:
                continue
            bounds_raw = self._tool_executor("get_comfort_bounds", {"zone": zone.zone})
            bounds = ComfortBounds.model_validate(bounds_raw)
            bounds_call = _jsonrpc_call("get_comfort_bounds", {"zone": zone.zone}, bounds_raw)
            result.tool_calls.append(bounds_call)
            if on_tool_call:
                on_tool_call(bounds_call)
            invalid_setpoints = zone.cooling_setpoint_c - zone.heating_setpoint_c < MIN_DEADBAND_C
            out_of_comfort_band = bounds.occupied and not (bounds.min_temp_c <= zone.air_temp_c <= bounds.max_temp_c)
            if not invalid_setpoints and not out_of_comfort_band:
                continue

            heating_c = bounds.min_temp_c
            cooling_c = bounds.max_temp_c
            request_args = {"zone": zone.zone, "heating_setpoint_c": heating_c,
                            "cooling_setpoint_c": cooling_c, "source": "comfort_safety_net"}
            fix = self._tool_executor(
                "propose_setpoint_change",
                {"zone": zone.zone, "heating_setpoint_c": heating_c, "cooling_setpoint_c": cooling_c},
            )
            jsonrpc_entry = _jsonrpc_call("propose_setpoint_change", request_args, fix)
            result.actions.append({"request": request_args, "result": fix})
            result.tool_calls.append(jsonrpc_entry)
            if on_tool_call:
                on_tool_call(jsonrpc_entry)

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        if name == "get_current_state":
            return self._tools.get_current_state().model_dump()
        if name == "get_comfort_bounds":
            bounds: ComfortBounds = self._tools.get_comfort_bounds(arguments["zone"])
            return bounds.model_dump()
        if name == "get_recent_history":
            history = self._tools.get_recent_history(arguments["n"])
            return [
                {"zone": d.zone, "accepted": d.accepted, "reason": d.reason,
                 "applied_heating_c": d.applied_heating_c, "applied_cooling_c": d.applied_cooling_c}
                for d in history
            ]
        if name == "propose_setpoint_change":
            result = self._tools.propose_setpoint_change(ProposeSetpointChange(**arguments))
            return result.model_dump()
        return {"error": f"unknown tool '{name}'"}
