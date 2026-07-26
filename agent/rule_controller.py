
from agent.tools import ProposeSetpointChange, ToolLayer
from simulation.runner import ZONES

OCCUPIED_HOURS = range(8, 18)


OCCUPIED_HEATING_C = 23.5
OCCUPIED_COOLING_C = 26.0
SETBACK_HEATING_C = 17.0
SETBACK_COOLING_C = 28.0


def decide(hour_of_day: int) -> tuple[float, float]:
    if hour_of_day in OCCUPIED_HOURS:
        return OCCUPIED_HEATING_C, OCCUPIED_COOLING_C
    return SETBACK_HEATING_C, SETBACK_COOLING_C


def run_control_step(tool_layer: ToolLayer, sim_time_hours: float) -> None:
    hour_of_day = int(sim_time_hours % 24)
    heating_c, cooling_c = decide(hour_of_day)
    for zone in ZONES:
        tool_layer.propose_setpoint_change(ProposeSetpointChange(
            zone=zone, heating_setpoint_c=heating_c, cooling_setpoint_c=cooling_c,
        ))
