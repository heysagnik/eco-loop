import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.llm_client import LLMCallError, LLMRateLimitError
from agent.orchestrator import Orchestrator
from agent.rate_limiter import TokenBucket
from agent.tools import ToolLayer
from simulation.runner import StateSnapshot, ZoneSnapshot


def make_tool_layer():
    runner = MagicMock()
    tool_layer = ToolLayer(runner)
    tool_layer.ingest_snapshot(StateSnapshot(
        sim_time_hours=9.0, outdoor_air_temp_c=5.0, facility_electricity_w=0.0,
        zones={"Core_ZN": ZoneSnapshot(mean_air_temp_c=22.0, relative_humidity_pct=40.0,
                                        heating_setpoint_c=20.0, cooling_setpoint_c=24.0)},
    ))
    return tool_layer, runner


def test_holds_last_safe_setpoints_when_rate_limited():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    exhausted_bucket = TokenBucket(capacity=1, refill_per_minute=0)
    exhausted_bucket.try_acquire()  

    orchestrator = Orchestrator(llm, tool_layer, rate_limiter=exhausted_bucket)
    result = orchestrator.run_control_step()

    assert result.degraded
    assert result.actions == []
    llm.call.assert_not_called()
    runner.submit_setpoints.assert_not_called()


def test_holds_last_safe_setpoints_on_llm_error():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.side_effect = LLMCallError("simulated timeout")

    orchestrator = Orchestrator(llm, tool_layer)
    result = orchestrator.run_control_step()

    assert result.degraded
    assert "simulated timeout" in result.rationale
    runner.submit_setpoints.assert_not_called()


def test_holds_last_safe_setpoints_when_token_budget_exhausted():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    exhausted_budget = TokenBucket(capacity=100, refill_per_minute=0)
    exhausted_budget.try_acquire(100)  

    orchestrator = Orchestrator(llm, tool_layer, token_budget=exhausted_budget)
    result = orchestrator.run_control_step()

    assert result.degraded
    assert "token budget" in result.rationale
    llm.call.assert_not_called()
    runner.submit_setpoints.assert_not_called()


def test_token_budget_corrected_by_actual_usage():
    tool_layer, _ = make_tool_layer()
    llm = MagicMock()
    llm.call.return_value = {"content": "done", "tool_calls": [], "total_tokens": 200}
    budget = TokenBucket(capacity=1500, refill_per_minute=0)

    orchestrator = Orchestrator(llm, tool_layer, token_budget=budget)
    orchestrator.run_control_step()

    
    assert budget.try_acquire(1300)


def test_comfort_safety_net_corrects_untouched_out_of_band_zone():
    
    
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.return_value = {
        "content": "No changes needed, all zones are comfortable.",
        "tool_calls": [], "total_tokens": 300,
    }

    orchestrator = Orchestrator(llm, tool_layer)
    result = orchestrator.run_control_step()

    safety_actions = [a for a in result.actions if a["request"].get("source") == "comfort_safety_net"]
    assert len(safety_actions) == 1
    assert safety_actions[0]["request"]["zone"] == "Core_ZN"
    assert safety_actions[0]["result"]["accepted"]
    runner.submit_setpoints.assert_called_once()


def test_comfort_safety_net_does_not_override_llm_actions():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.side_effect = [
        {
            "content": None,
            "tool_calls": [{"id": "1", "name": "propose_setpoint_change",
                             "arguments": {"zone": "Core_ZN", "heating_setpoint_c": 23.5, "cooling_setpoint_c": 26.0}}],
            "total_tokens": 300,
        },
        {"content": "Done.", "tool_calls": [], "total_tokens": 300},
    ]

    orchestrator = Orchestrator(llm, tool_layer)
    result = orchestrator.run_control_step()

    safety_actions = [a for a in result.actions if a["request"].get("source") == "comfort_safety_net"]
    assert safety_actions == []
    assert runner.submit_setpoints.call_count == 1


def test_wait_on_limits_retries_rate_limit_then_succeeds():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.side_effect = [
        LLMRateLimitError("429"),
        {"content": "done", "tool_calls": [], "total_tokens": 200},
    ]

    orchestrator = Orchestrator(llm, tool_layer, wait_on_limits=True)
    with patch("agent.orchestrator.time.sleep"):
        result = orchestrator.run_control_step()

    assert not result.degraded
    assert llm.call.call_count == 2


def test_wait_on_limits_gives_up_after_max_retries():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.side_effect = LLMRateLimitError("429")

    orchestrator = Orchestrator(llm, tool_layer, wait_on_limits=True)
    with patch("agent.orchestrator.time.sleep"):
        result = orchestrator.run_control_step()

    assert result.degraded
    assert "LLM call failed" in result.rationale


def test_without_wait_on_limits_rate_limit_degrades_immediately():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.side_effect = LLMRateLimitError("429")

    orchestrator = Orchestrator(llm, tool_layer)
    result = orchestrator.run_control_step()

    assert result.degraded
    assert llm.call.call_count == 1


def test_wait_on_limits_polls_token_budget_until_available():
    tool_layer, runner = make_tool_layer()
    llm = MagicMock()
    llm.call.return_value = {"content": "done", "tool_calls": [], "total_tokens": 200}
    budget = TokenBucket(capacity=1500, refill_per_minute=0)
    budget.try_acquire(1500)  

    def fake_sleep(_):
        budget.adjust(1500)  

    orchestrator = Orchestrator(llm, tool_layer, token_budget=budget, wait_on_limits=True)
    with patch("agent.orchestrator.time.sleep", side_effect=fake_sleep):
        result = orchestrator.run_control_step()

    assert not result.degraded
    llm.call.assert_called_once()


def test_stops_after_max_turns_without_crashing():
    tool_layer, _ = make_tool_layer()
    llm = MagicMock()
    llm.call.return_value = {
        "content": None,
        "tool_calls": [{"id": "1", "name": "get_current_state", "arguments": {}}],
        "total_tokens": 200,
    }

    orchestrator = Orchestrator(llm, tool_layer)
    result = orchestrator.run_control_step()

    assert not result.degraded
    assert "max tool-call turns" in result.rationale
