
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from agent.pmv import ppd, pmv
from simulation.runner import SimulationRunner, StateSnapshot

HEATING_RANGE_C = (15.0, 25.0)
COOLING_RANGE_C = (21.0, 30.0)
MAX_RATE_OF_CHANGE_C = 2.0
MIN_DEADBAND_C = 1.5

OCCUPIED_HOURS = range(8, 18)
COMFORT_BAND_OCCUPIED_C = (23.0, 26.0)  
COMFORT_BAND_UNOCCUPIED_C = (16.0, 29.0)


@dataclass
class Decision:
    timestamp: datetime
    zone: str
    requested_heating_c: float
    requested_cooling_c: float
    applied_heating_c: float | None
    applied_cooling_c: float | None
    accepted: bool
    reason: str


class ZoneState(BaseModel):
    zone: str
    air_temp_c: float
    relative_humidity_pct: float
    heating_setpoint_c: float
    cooling_setpoint_c: float
    pmv: float
    ppd_pct: float


class CurrentState(BaseModel):
    sim_time_hours: float
    outdoor_air_temp_c: float
    facility_electricity_kw: float
    zones: list[ZoneState]


class ComfortBounds(BaseModel):
    zone: str
    occupied: bool
    min_temp_c: float
    max_temp_c: float


class ProposeSetpointChange(BaseModel):
    zone: str
    heating_setpoint_c: float = Field(description="Requested heating setpoint in Celsius")
    cooling_setpoint_c: float = Field(description="Requested cooling setpoint in Celsius")


class ProposalResult(BaseModel):
    accepted: bool
    applied_heating_c: float | None
    applied_cooling_c: float | None
    reason: str


class HistoryEntry(BaseModel):
    zone: str
    accepted: bool
    reason: str
    applied_heating_c: float | None
    applied_cooling_c: float | None


class ToolLayer:
    def __init__(self, runner: SimulationRunner) -> None:
        self._runner = runner
        self._latest_snapshot: StateSnapshot | None = None
        self._history: list[Decision] = []
        self._last_applied: dict[str, tuple[float, float]] = {}

    def ingest_snapshot(self, snapshot: StateSnapshot) -> None:
        self._latest_snapshot = snapshot

    def get_current_state(self) -> CurrentState:
        snapshot = self._latest_snapshot
        if snapshot is None:
            raise RuntimeError("no simulation snapshot available yet")

        zones = []
        for zone, z in snapshot.zones.items():
            mrt_c = z.mean_radiant_temp_c if z.mean_radiant_temp_c is not None else z.mean_air_temp_c
            pmv_value = pmv(z.mean_air_temp_c, mrt_c, z.relative_humidity_pct)
            zones.append(ZoneState(
                zone=zone,
                air_temp_c=z.mean_air_temp_c,
                relative_humidity_pct=z.relative_humidity_pct,
                heating_setpoint_c=z.heating_setpoint_c,
                cooling_setpoint_c=z.cooling_setpoint_c,
                pmv=pmv_value,
                ppd_pct=ppd(pmv_value),
            ))

        return CurrentState(
            sim_time_hours=snapshot.sim_time_hours,
            outdoor_air_temp_c=snapshot.outdoor_air_temp_c,
            facility_electricity_kw=snapshot.facility_electricity_w / 1000.0,
            zones=zones,
        )

    def get_comfort_bounds(self, zone: str) -> ComfortBounds:
        snapshot = self._latest_snapshot
        hour_of_day = int(snapshot.sim_time_hours % 24) if snapshot else 12
        occupied = hour_of_day in OCCUPIED_HOURS
        band = COMFORT_BAND_OCCUPIED_C if occupied else COMFORT_BAND_UNOCCUPIED_C
        return ComfortBounds(zone=zone, occupied=occupied, min_temp_c=band[0], max_temp_c=band[1])

    def get_recent_history(self, n: int) -> list[Decision]:
        return self._history[-n:]

    def get_recent_history_entries(self, n: int) -> list[HistoryEntry]:
        
        return [
            HistoryEntry(zone=d.zone, accepted=d.accepted, reason=d.reason,
                          applied_heating_c=d.applied_heating_c, applied_cooling_c=d.applied_cooling_c)
            for d in self._history[-n:]
        ]

    def propose_setpoint_change(self, request: ProposeSetpointChange) -> ProposalResult:
        result = self._validate(request, self._last_applied.get(request.zone))

        self._history.append(Decision(
            timestamp=datetime.now(timezone.utc),
            zone=request.zone,
            requested_heating_c=request.heating_setpoint_c,
            requested_cooling_c=request.cooling_setpoint_c,
            applied_heating_c=result.applied_heating_c,
            applied_cooling_c=result.applied_cooling_c,
            accepted=result.accepted,
            reason=result.reason,
        ))

        if result.accepted:
            self._last_applied[request.zone] = (result.applied_heating_c, result.applied_cooling_c)
            self._runner.submit_setpoints(request.zone, result.applied_heating_c, result.applied_cooling_c)

        return result

    def _validate(self, request: ProposeSetpointChange, current: tuple[float, float] | None) -> ProposalResult:
        if self._latest_snapshot is None:
            return ProposalResult(accepted=False, applied_heating_c=None, applied_cooling_c=None,
                                   reason="no live telemetry available yet")
        if request.zone not in self._latest_snapshot.zones:
            return ProposalResult(accepted=False, applied_heating_c=None, applied_cooling_c=None,
                                   reason=f"unknown zone '{request.zone}'")

        heating_c = min(max(request.heating_setpoint_c, HEATING_RANGE_C[0]), HEATING_RANGE_C[1])
        cooling_c = min(max(request.cooling_setpoint_c, COOLING_RANGE_C[0]), COOLING_RANGE_C[1])

        if current is not None:
            prev_heating, prev_cooling = current
            heating_c = max(prev_heating - MAX_RATE_OF_CHANGE_C, min(prev_heating + MAX_RATE_OF_CHANGE_C, heating_c))
            cooling_c = max(prev_cooling - MAX_RATE_OF_CHANGE_C, min(prev_cooling + MAX_RATE_OF_CHANGE_C, cooling_c))

        if cooling_c - heating_c < MIN_DEADBAND_C:
            return ProposalResult(
                accepted=False, applied_heating_c=None, applied_cooling_c=None,
                reason=f"cooling/heating deadband below {MIN_DEADBAND_C}C after clamping",
            )

        clamped = (heating_c != request.heating_setpoint_c) or (cooling_c != request.cooling_setpoint_c)
        reason = "accepted with clamping" if clamped else "accepted"
        return ProposalResult(accepted=True, applied_heating_c=heating_c, applied_cooling_c=cooling_c, reason=reason)
