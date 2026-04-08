"""第一波 MVP 的 rollout 推进。"""

from __future__ import annotations

from copy import deepcopy

from first_wave_mvp.state_machine import (
    PlannerSignal,
    TransitionReason,
    derive_planner_signal,
    resolve_planning_transition,
    validate_transition,
)
from first_wave_mvp.types import CommitState, ExecutionState, ScenarioConfig, VehicleState


def _advance_constant_speed(state: VehicleState, tick_s: float) -> None:
    state.x_pos_m += state.speed_mps * tick_s


def _advance_fail_safe_stop(state: VehicleState, scenario: ScenarioConfig) -> TransitionReason:
    next_speed_mps = max(0.0, state.speed_mps - scenario.fail_safe_brake_mps2 * scenario.rollout_tick_s)
    avg_speed_mps = 0.5 * (state.speed_mps + next_speed_mps)
    state.x_pos_m += avg_speed_mps * scenario.rollout_tick_s
    state.speed_mps = next_speed_mps

    if next_speed_mps == 0.0:
        validate_transition(state.execution_state, ExecutionState.ABORTED)
        state.execution_state = ExecutionState.ABORTED
        return TransitionReason.ABORT_AFTER_FAIL_SAFE_STOP

    validate_transition(state.execution_state, ExecutionState.FAIL_SAFE_STOP)
    return TransitionReason.FAIL_SAFE_EMERGENCY_TAIL


def _require_committed_plan(veh_id: str, committed_plans: dict[str, object]) -> object:
    if veh_id not in committed_plans:
        raise ValueError(f"missing committed plan for vehicle {veh_id!r}")
    return committed_plans[veh_id]


def rollout_step(
    *,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    committed_plans: dict[str, object],
) -> dict[str, VehicleState]:
    next_world_state = deepcopy(world_state)

    for veh_id, state in next_world_state.items():
        if state.execution_state is ExecutionState.APPROACHING:
            validate_transition(state.execution_state, ExecutionState.PLANNING)
            _advance_constant_speed(state, scenario.rollout_tick_s)
            state.execution_state = ExecutionState.PLANNING
            continue

        if state.execution_state is ExecutionState.PLANNING:
            signal = derive_planner_signal(veh_id, committed_plans)
            next_state, _ = resolve_planning_transition(
                state,
                scenario=scenario,
                signal=signal,
            )
            validate_transition(state.execution_state, next_state)
            _advance_constant_speed(state, scenario.rollout_tick_s)
            state.execution_state = next_state
            if next_state is ExecutionState.COMMITTED:
                state.commit_state = CommitState.COMMITTED
            continue

        if state.execution_state is ExecutionState.COMMITTED:
            _require_committed_plan(veh_id, committed_plans)
            validate_transition(state.execution_state, ExecutionState.EXECUTING)
            _advance_constant_speed(state, scenario.rollout_tick_s)
            state.execution_state = ExecutionState.EXECUTING
            state.commit_state = CommitState.COMMITTED
            continue

        if state.execution_state is ExecutionState.EXECUTING:
            committed_plan = _require_committed_plan(veh_id, committed_plans)
            _advance_constant_speed(state, scenario.rollout_tick_s)
            threshold_x_m = (
                committed_plan.candidate.x_m_m
                + state.speed_mps * scenario.post_merge_guard_s
            )
            if state.x_pos_m >= threshold_x_m:
                validate_transition(state.execution_state, ExecutionState.POST_MERGE)
                state.execution_state = ExecutionState.POST_MERGE
            else:
                validate_transition(state.execution_state, ExecutionState.EXECUTING)
            continue

        if state.execution_state is ExecutionState.POST_MERGE:
            _advance_constant_speed(state, scenario.rollout_tick_s)
            validate_transition(state.execution_state, ExecutionState.POST_MERGE)
            continue

        if state.execution_state is ExecutionState.FAIL_SAFE_STOP:
            _advance_fail_safe_stop(state, scenario)
            continue

        if state.execution_state is ExecutionState.ABORTED:
            validate_transition(state.execution_state, ExecutionState.ABORTED)
            continue

        raise ValueError(f"unsupported execution state: {state.execution_state!r}")

    return next_world_state


__all__ = ["rollout_step"]
