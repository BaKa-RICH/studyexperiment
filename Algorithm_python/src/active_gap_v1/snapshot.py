"""Snapshot builder for one planning tick."""

from __future__ import annotations

from copy import deepcopy

from .types import AnchorMode, CoordinationSnapshot, PlannerTag, ScenarioConfig, TCG, VehicleState


def _select_active_ego(world_state: dict[str, VehicleState]) -> VehicleState:
    ramp_cav_candidates = [
        state
        for state in world_state.values()
        if state.stream == "ramp" and state.is_cav
    ]
    if not ramp_cav_candidates:
        raise ValueError("No ramp CAV found for active ego selection.")

    return max(ramp_cav_candidates, key=lambda state: (state.x_pos_m, state.veh_id))


def build_coordination_snapshot(
    *,
    sim_time_s: float,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    locked_tcgs: dict[str, TCG],
    planner_tag: PlannerTag,
    anchor_mode: AnchorMode,
) -> CoordinationSnapshot:
    snapshot_id = f"snap_{sim_time_s:.3f}"
    frozen_world_state = deepcopy(world_state)
    frozen_locked_tcgs = deepcopy(locked_tcgs)
    ego_state = _select_active_ego(frozen_world_state)

    return CoordinationSnapshot(
        snapshot_id=snapshot_id,
        sim_time_s=sim_time_s,
        planner_tag=planner_tag,
        anchor_mode=anchor_mode,
        ego_id=ego_state.veh_id,
        ego_state=ego_state,
        control_zone_states=frozen_world_state,
        locked_tcgs=frozen_locked_tcgs,
        scenario=scenario,
    )
