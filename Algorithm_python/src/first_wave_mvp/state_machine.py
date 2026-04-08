"""第一波 MVP 的执行状态机。"""

from __future__ import annotations

from enum import StrEnum

from first_wave_mvp.types import ExecutionState, ScenarioConfig, VehicleState


class PlannerSignal(StrEnum):
    COMMIT_AVAILABLE = "commit_available"
    NO_FEASIBLE_PLAN = "no_feasible_plan"


class TransitionReason(StrEnum):
    APPROACHING_ENTER_CONTROL_ZONE = "approaching_enter_control_zone"
    WAIT_NO_FEASIBLE_PLAN = "wait_no_feasible_plan"
    FAIL_SAFE_EMERGENCY_TAIL = "fail_safe_emergency_tail"
    COMMIT_AVAILABLE = "commit_available"
    EXECUTION_STARTED = "execution_started"
    POST_MERGE_GUARD_COMPLETE = "post_merge_guard_complete"
    ABORT_AFTER_FAIL_SAFE_STOP = "abort_after_fail_safe_stop"
    STAY_IN_STATE = "stay_in_state"


ALLOWED_STATE_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.APPROACHING: {ExecutionState.APPROACHING, ExecutionState.PLANNING},
    ExecutionState.PLANNING: {
        ExecutionState.PLANNING,
        ExecutionState.COMMITTED,
        ExecutionState.FAIL_SAFE_STOP,
    },
    ExecutionState.COMMITTED: {ExecutionState.COMMITTED, ExecutionState.EXECUTING},
    ExecutionState.EXECUTING: {ExecutionState.EXECUTING, ExecutionState.POST_MERGE},
    ExecutionState.POST_MERGE: {ExecutionState.POST_MERGE},
    ExecutionState.FAIL_SAFE_STOP: {
        ExecutionState.FAIL_SAFE_STOP,
        ExecutionState.ABORTED,
    },
    ExecutionState.ABORTED: {ExecutionState.ABORTED},
}


def validate_transition(
    current_state: ExecutionState,
    next_state: ExecutionState,
) -> None:
    allowed_states = ALLOWED_STATE_TRANSITIONS[current_state]
    if next_state not in allowed_states:
        raise ValueError(f"illegal state transition: {current_state.value} -> {next_state.value}")


def derive_planner_signal(veh_id: str, committed_plans: dict[str, object]) -> PlannerSignal:
    if veh_id in committed_plans:
        return PlannerSignal.COMMIT_AVAILABLE
    return PlannerSignal.NO_FEASIBLE_PLAN


def in_emergency_tail(state: VehicleState, scenario: ScenarioConfig) -> bool:
    emergency_tail_start_m, _ = scenario.emergency_tail_m
    return state.x_pos_m > emergency_tail_start_m


def resolve_planning_transition(
    state: VehicleState,
    *,
    scenario: ScenarioConfig,
    signal: PlannerSignal,
) -> tuple[ExecutionState, TransitionReason]:
    if signal is PlannerSignal.COMMIT_AVAILABLE:
        return ExecutionState.COMMITTED, TransitionReason.COMMIT_AVAILABLE

    if in_emergency_tail(state, scenario):
        return ExecutionState.FAIL_SAFE_STOP, TransitionReason.FAIL_SAFE_EMERGENCY_TAIL

    return ExecutionState.PLANNING, TransitionReason.WAIT_NO_FEASIBLE_PLAN


__all__ = [
    "ALLOWED_STATE_TRANSITIONS",
    "PlannerSignal",
    "TransitionReason",
    "derive_planner_signal",
    "in_emergency_tail",
    "resolve_planning_transition",
    "validate_transition",
]
