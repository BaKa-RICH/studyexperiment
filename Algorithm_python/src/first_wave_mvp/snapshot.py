"""第一波 MVP 的 snapshot 构造。"""

from __future__ import annotations

from copy import deepcopy

from first_wave_mvp.types import (
    CommitState,
    CommittedPlan,
    ExecutionState,
    PlanningSnapshot,
    PolicyTag,
    ScenarioConfig,
    VehicleState,
)


_INELIGIBLE_EXECUTION_STATES = {
    ExecutionState.COMMITTED,
    ExecutionState.EXECUTING,
    ExecutionState.POST_MERGE,
    ExecutionState.FAIL_SAFE_STOP,
    ExecutionState.ABORTED,
}


def select_planning_ego(world_state: dict[str, VehicleState]) -> VehicleState | None:
    """返回当前 tick 唯一需要被规划的 ramp CAV。"""
    eligible = [
        state
        for state in world_state.values()
        if state.stream == "ramp"
        and state.is_cav
        and state.commit_state is CommitState.UNCOMMITTED
        and state.execution_state not in _INELIGIBLE_EXECUTION_STATES
    ]

    if not eligible:
        return None

    return max(eligible, key=lambda state: (state.x_pos_m, state.veh_id))


def _collect_target_lane_object_ids(
    control_zone_states: dict[str, VehicleState],
    committed_plans: dict[str, CommittedPlan],
    ego_id: str,
) -> tuple[str, ...]:
    target_lane_ids = {
        veh_id
        for veh_id, state in control_zone_states.items()
        if veh_id != ego_id and state.stream != "ramp"
    }

    target_lane_ids.update(
        veh_id
        for veh_id in committed_plans
        if veh_id != ego_id
    )

    return tuple(sorted(target_lane_ids))


def build_snapshot(
    *,
    sim_time_s: float,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    committed_plans: dict[str, CommittedPlan],
    policy_tag: PolicyTag,
) -> PlanningSnapshot:
    ego_state = select_planning_ego(world_state)
    if ego_state is None:
        raise ValueError("No eligible ramp ego in world_state")

    frozen_world_state = deepcopy(world_state)
    frozen_committed_plans = deepcopy(committed_plans)
    frozen_ego_state = frozen_world_state[ego_state.veh_id]

    snapshot_id = f"{policy_tag.value}:{sim_time_s:.3f}:{ego_state.veh_id}"
    target_lane_object_ids = _collect_target_lane_object_ids(
        frozen_world_state,
        frozen_committed_plans,
        ego_state.veh_id,
    )

    return PlanningSnapshot(
        snapshot_id=snapshot_id,
        sim_time_s=sim_time_s,
        policy_tag=policy_tag,
        ego_id=ego_state.veh_id,
        ego_state=frozen_ego_state,
        control_zone_states=frozen_world_state,
        target_lane_object_ids=target_lane_object_ids,
        committed_plans=frozen_committed_plans,
        scenario=scenario,
    )


__all__ = [
    "build_snapshot",
    "select_planning_ego",
]
