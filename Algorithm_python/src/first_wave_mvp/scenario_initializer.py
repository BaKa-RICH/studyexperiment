"""种子驱动的最小数值实验初始化器。"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

from first_wave_mvp.types import CommitState, ExecutionState, ScenarioConfig, VehicleState


DEFAULT_MAINLINE_LANE_ID = "main_0"
DEFAULT_RAMP_LANE_ID = "ramp_0"


@dataclass(frozen=True, slots=True)
class InitializedScenario:
    scenario: ScenarioConfig
    world_state: dict[str, VehicleState]
    committed_plans: dict[str, object]
    sim_duration_s: float
    max_ticks: int
    rng_seed: str


def _vehicle_count_from_vph(vph: float, sim_duration_s: float, *, minimum: int) -> int:
    estimated = max(minimum, round(vph * sim_duration_s / 3600.0))
    return int(estimated)


def _make_vehicle(
    *,
    veh_id: str,
    stream: str,
    lane_id: str,
    x_pos_m: float,
    speed_mps: float,
    is_cav: bool,
    execution_state: ExecutionState,
) -> VehicleState:
    return VehicleState(
        veh_id=veh_id,
        stream=stream,
        lane_id=lane_id,
        x_pos_m=x_pos_m,
        speed_mps=speed_mps,
        accel_mps2=0.0,
        length_m=5.0,
        is_cav=is_cav,
        execution_state=execution_state,
        commit_state=CommitState.UNCOMMITTED,
    )


def initialize_scenario(
    *,
    experiment_id: str,
    seed: int,
    parameters: dict[str, Any],
) -> InitializedScenario:
    sim_duration_s = float(parameters.get("sim_duration_s", 20.0))
    rng_seed = f"{experiment_id}:{seed}"
    rng = Random(rng_seed)

    mainline_vph = float(parameters.get("mainline_vph", 600.0))
    ramp_vph = float(parameters.get("ramp_vph", 120.0))
    mainline_vehicle_count = int(
        parameters.get(
            "mainline_vehicle_count",
            _vehicle_count_from_vph(mainline_vph, sim_duration_s, minimum=2),
        )
    )
    ramp_vehicle_count = int(
        parameters.get(
            "ramp_vehicle_count",
            _vehicle_count_from_vph(ramp_vph, sim_duration_s, minimum=1),
        )
    )

    mainline_speed_min_mps = float(parameters.get("mainline_speed_min_mps", 9.0))
    mainline_speed_max_mps = float(parameters.get("mainline_speed_max_mps", 14.0))
    ramp_speed_min_mps = float(parameters.get("ramp_speed_min_mps", 8.0))
    ramp_speed_max_mps = float(parameters.get("ramp_speed_max_mps", 12.0))
    mainline_spacing_m = float(parameters.get("mainline_spacing_m", 35.0))
    ramp_spacing_m = float(parameters.get("ramp_spacing_m", 28.0))
    mainline_start_m = float(parameters.get("mainline_start_m", 120.0))
    ramp_start_m = float(parameters.get("ramp_start_m", 20.0))
    mainline_cav_ratio = float(parameters.get("mainline_cav_ratio", 0.5))

    scenario = ScenarioConfig(
        scenario_id=f"{experiment_id}:{seed}",
    )
    max_ticks = int(parameters.get("max_ticks", sim_duration_s / scenario.rollout_tick_s))

    world_state: dict[str, VehicleState] = {}
    for idx in range(mainline_vehicle_count):
        x_pos_m = mainline_start_m + idx * mainline_spacing_m + rng.uniform(-3.0, 3.0)
        speed_mps = rng.uniform(mainline_speed_min_mps, mainline_speed_max_mps)
        is_cav = rng.random() < mainline_cav_ratio
        veh_id = f"m{idx}"
        world_state[veh_id] = _make_vehicle(
            veh_id=veh_id,
            stream="mainline",
            lane_id=DEFAULT_MAINLINE_LANE_ID,
            x_pos_m=x_pos_m,
            speed_mps=speed_mps,
            is_cav=is_cav,
            execution_state=ExecutionState.POST_MERGE,
        )

    for idx in range(ramp_vehicle_count):
        x_pos_m = ramp_start_m + idx * ramp_spacing_m + rng.uniform(-2.0, 2.0)
        speed_mps = rng.uniform(ramp_speed_min_mps, ramp_speed_max_mps)
        veh_id = f"r{idx}"
        world_state[veh_id] = _make_vehicle(
            veh_id=veh_id,
            stream="ramp",
            lane_id=DEFAULT_RAMP_LANE_ID,
            x_pos_m=x_pos_m,
            speed_mps=speed_mps,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
        )

    return InitializedScenario(
        scenario=scenario,
        world_state=world_state,
        committed_plans={},
        sim_duration_s=sim_duration_s,
        max_ticks=max_ticks,
        rng_seed=rng_seed,
    )


__all__ = [
    "InitializedScenario",
    "initialize_scenario",
]
