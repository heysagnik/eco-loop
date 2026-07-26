import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.tools import ProposeSetpointChange, ToolLayer
from simulation.runner import StateSnapshot, ZoneSnapshot


def make_tool_layer(last_applied: tuple[float, float] | None = None):
    runner = MagicMock()
    tool_layer = ToolLayer(runner)
    tool_layer.ingest_snapshot(StateSnapshot(
        sim_time_hours=10.0,
        outdoor_air_temp_c=5.0,
        facility_electricity_w=0.0,
        zones={"Core_ZN": ZoneSnapshot(
            mean_air_temp_c=22.0, relative_humidity_pct=40.0,
            heating_setpoint_c=20.0, cooling_setpoint_c=24.0,
        )},
    ))
    if last_applied is not None:
        tool_layer._last_applied["Core_ZN"] = last_applied
    return tool_layer, runner


def test_accepts_valid_proposal_within_range():
    tool_layer, runner = make_tool_layer()
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=21.0, cooling_setpoint_c=25.0,
    ))
    assert result.accepted
    runner.submit_setpoints.assert_called_once_with("Core_ZN", 21.0, 25.0)


def test_clamps_out_of_range_temperature_on_first_proposal():
    tool_layer, _ = make_tool_layer()
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=40.0, cooling_setpoint_c=45.0,
    ))
    assert result.accepted
    assert result.applied_heating_c == 25.0  
    assert result.applied_cooling_c == 30.0  


def test_caps_rate_of_change_from_last_applied():
    tool_layer, _ = make_tool_layer(last_applied=(20.0, 24.0))
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=23.0, cooling_setpoint_c=24.0,
    ))
    assert result.accepted
    assert result.applied_heating_c == 22.0  


def test_rejects_unknown_zone():
    tool_layer, runner = make_tool_layer()
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Nonexistent_Zone", heating_setpoint_c=21.0, cooling_setpoint_c=25.0,
    ))
    assert not result.accepted
    runner.submit_setpoints.assert_not_called()


def test_rejects_when_deadband_collapses():
    tool_layer, runner = make_tool_layer(last_applied=(20.0, 21.5))
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=20.5, cooling_setpoint_c=21.0,
    ))
    assert not result.accepted
    runner.submit_setpoints.assert_not_called()


def test_history_records_every_decision():
    tool_layer, _ = make_tool_layer()
    tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=21.0, cooling_setpoint_c=25.0,
    ))
    tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Nonexistent_Zone", heating_setpoint_c=21.0, cooling_setpoint_c=25.0,
    ))
    history = tool_layer.get_recent_history(10)
    assert len(history) == 2
    assert history[0].accepted and not history[1].accepted


def test_last_applied_tracked_across_calls():
    tool_layer, _ = make_tool_layer(last_applied=(20.0, 24.0))
    tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=22.0, cooling_setpoint_c=24.0,
    ))
    result = tool_layer.propose_setpoint_change(ProposeSetpointChange(
        zone="Core_ZN", heating_setpoint_c=25.0, cooling_setpoint_c=28.0,
    ))
    assert result.applied_heating_c == 24.0  
