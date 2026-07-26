
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Full, Queue

from pyenergyplus.api import EnergyPlusAPI

logger = logging.getLogger(__name__)

ZONES = ["Core_ZN", "Perimeter_ZN_1", "Perimeter_ZN_2", "Perimeter_ZN_3", "Perimeter_ZN_4"]
LOCKSTEP_WAIT_TIMEOUT_SECONDS = float(os.environ.get("LOCKSTEP_WAIT_TIMEOUT_SECONDS", 1800.0))

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
IDF_PATH = MODELS_DIR / "ASHRAE901_OfficeSmall_STD2019_Denver.idf"
EPW_PATH = MODELS_DIR / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
OUTPUT_DIR = MODELS_DIR / "out"


@dataclass
class ZoneSnapshot:
    mean_air_temp_c: float
    relative_humidity_pct: float
    heating_setpoint_c: float
    cooling_setpoint_c: float
    mean_radiant_temp_c: float | None = None


@dataclass
class StateSnapshot:
    sim_time_hours: float
    outdoor_air_temp_c: float
    facility_electricity_w: float
    zones: dict[str, ZoneSnapshot] = field(default_factory=dict)


class SimulationRunner:
    def __init__(self, control_interval_minutes: int = 15, queue_maxsize: int = 1,
                 lockstep: bool = False, output_dir: Path | None = None) -> None:
        
        self.api = EnergyPlusAPI()
        self.control_interval_hours = control_interval_minutes / 60.0
        self._lockstep = lockstep
        
        
        self._output_dir = output_dir or OUTPUT_DIR

        self._lock = threading.Lock()
        self._handles_ready = False
        self._sensor_handles: dict[str, int] = {}
        self._actuator_handles: dict[str, tuple[int, int]] = {}
        self._last_control_time_hours = 0.0

        self.latest_validated_setpoints: dict[str, tuple[float, float]] = {}
        self.state_queue: Queue[StateSnapshot] = Queue(maxsize=queue_maxsize)
        self._decision_applied = threading.Event()

        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit_setpoints(self, zone: str, heating_c: float, cooling_c: float) -> None:
        with self._lock:
            self.latest_validated_setpoints[zone] = (heating_c, cooling_c)

    def decision_applied(self) -> None:
        
        self._decision_applied.set()

    def latest_snapshot(self, timeout: float | None = None) -> StateSnapshot | None:
        try:
            return self.state_queue.get(timeout=timeout)
        except Empty:
            return None

    def _run(self) -> None:
        state = self.api.state_manager.new_state()
        self.api.exchange.request_variable(state, "Site Outdoor Air Drybulb Temperature", "Environment")
        self.api.exchange.request_variable(state, "Facility Total Electricity Demand Rate", "Whole Building")
        for zone in ZONES:
            self.api.exchange.request_variable(state, "Zone Mean Air Temperature", zone)
            self.api.exchange.request_variable(state, "Zone Mean Radiant Temperature", zone)
            self.api.exchange.request_variable(state, "Zone Air Relative Humidity", zone)

        self.api.runtime.callback_begin_zone_timestep_after_init_heat_balance(state, self._on_timestep_begin)
        self.api.runtime.callback_end_zone_timestep_after_zone_reporting(state, self._on_timestep_end)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.api.runtime.run_energyplus(
            state, ["-w", str(EPW_PATH), "-d", str(self._output_dir), str(IDF_PATH)]
        )
        self.api.state_manager.delete_state(state)

    def _ensure_handles(self, state) -> None:
        if self._handles_ready or not self.api.exchange.api_data_fully_ready(state):
            return

        ex = self.api.exchange
        self._sensor_handles["outdoor_air_temp"] = ex.get_variable_handle(
            state, "Site Outdoor Air Drybulb Temperature", "Environment"
        )
        self._sensor_handles["facility_electricity"] = ex.get_variable_handle(
            state, "Facility Total Electricity Demand Rate", "Whole Building"
        )

        for zone in ZONES:
            self._sensor_handles[f"{zone}_temp"] = ex.get_variable_handle(
                state, "Zone Mean Air Temperature", zone
            )
            self._sensor_handles[f"{zone}_mrt"] = ex.get_variable_handle(
                state, "Zone Mean Radiant Temperature", zone
            )
            self._sensor_handles[f"{zone}_rh"] = ex.get_variable_handle(
                state, "Zone Air Relative Humidity", zone
            )
            self._actuator_handles[zone] = (
                ex.get_actuator_handle(state, "Zone Temperature Control", "Heating Setpoint", zone),
                ex.get_actuator_handle(state, "Zone Temperature Control", "Cooling Setpoint", zone),
            )

        self._handles_ready = True

    def _on_timestep_begin(self, state) -> None:
        self._ensure_handles(state)
        if not self._handles_ready:
            return

        ex = self.api.exchange
        with self._lock:
            setpoints = dict(self.latest_validated_setpoints)

        for zone, (heating_handle, cooling_handle) in self._actuator_handles.items():
            if zone not in setpoints:
                continue
            heating_c, cooling_c = setpoints[zone]
            ex.set_actuator_value(state, heating_handle, heating_c)
            ex.set_actuator_value(state, cooling_handle, cooling_c)

    def _on_timestep_end(self, state) -> None:
        ex = self.api.exchange
        if not self._handles_ready or ex.warmup_flag(state):
            return

        sim_time_hours = ex.current_sim_time(state)
        if sim_time_hours < self._last_control_time_hours:
            self._last_control_time_hours = 0.0
        if sim_time_hours - self._last_control_time_hours < self.control_interval_hours:
            return
        self._last_control_time_hours = sim_time_hours

        zones = {}
        for zone in ZONES:
            heating_handle, cooling_handle = self._actuator_handles[zone]
            mrt_handle = self._sensor_handles.get(f"{zone}_mrt", -1)
            mrt_val = ex.get_variable_value(state, mrt_handle) if mrt_handle != -1 else ex.get_variable_value(state, self._sensor_handles[f"{zone}_temp"])
            zones[zone] = ZoneSnapshot(
                mean_air_temp_c=ex.get_variable_value(state, self._sensor_handles[f"{zone}_temp"]),
                mean_radiant_temp_c=mrt_val,
                relative_humidity_pct=ex.get_variable_value(state, self._sensor_handles[f"{zone}_rh"]),
                heating_setpoint_c=ex.get_actuator_value(state, heating_handle),
                cooling_setpoint_c=ex.get_actuator_value(state, cooling_handle),
            )

        snapshot = StateSnapshot(
            sim_time_hours=sim_time_hours,
            outdoor_air_temp_c=ex.get_variable_value(state, self._sensor_handles["outdoor_air_temp"]),
            facility_electricity_w=ex.get_variable_value(state, self._sensor_handles["facility_electricity"]),
            zones=zones,
        )

        try:
            self.state_queue.put_nowait(snapshot)
        except Full:
            try:
                self.state_queue.get_nowait()
            except Empty:
                pass
            self.state_queue.put_nowait(snapshot)

        if self._lockstep:
            self._decision_applied.clear()
            applied = self._decision_applied.wait(timeout=LOCKSTEP_WAIT_TIMEOUT_SECONDS)
            if not applied:
                logger.error(
                    "lockstep wait timed out after %.0fs at sim_time_hours=%.2f - the control "
                    "loop appears stuck; proceeding with the last submitted setpoints instead "
                    "of hanging EnergyPlus indefinitely",
                    LOCKSTEP_WAIT_TIMEOUT_SECONDS, sim_time_hours,
                )
