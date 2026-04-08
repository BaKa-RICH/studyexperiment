from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from first_wave_mvp.commit import commit_candidate  # noqa: E402
from first_wave_mvp.gate import accept_candidate  # noqa: E402
from first_wave_mvp.rollout import rollout_step  # noqa: E402
from first_wave_mvp.snapshot import build_snapshot  # noqa: E402
from first_wave_mvp.state_machine import (  # noqa: E402
    PlannerSignal,
    TransitionReason,
    derive_planner_signal,
    in_emergency_tail,
    resolve_planning_transition,
    validate_transition,
)
from first_wave_mvp.step2_fifo import generate_candidates  # noqa: E402
from first_wave_mvp.types import CommitState, ExecutionState, PolicyTag, ScenarioConfig, VehicleState  # noqa: E402


def _make_vehicle(
    *,
    veh_id: str,
    stream: str,
    lane_id: str,
    x_pos_m: float,
    speed_mps: float,
    is_cav: bool,
    execution_state: ExecutionState,
    commit_state: CommitState,
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
        commit_state=commit_state,
    )


def _make_committed_plan_for_vehicle(world_state: dict[str, VehicleState], *, scenario_id: str = "scenario"):
    planning_world_state = deepcopy(world_state)
    for state in planning_world_state.values():
        if state.stream == "ramp":
            state.x_pos_m = min(state.x_pos_m, 100.0)
            state.execution_state = ExecutionState.PLANNING
            state.commit_state = CommitState.UNCOMMITTED

    snapshot = build_snapshot(
        sim_time_s=0.0,
        scenario=ScenarioConfig(scenario_id=scenario_id),
        world_state=planning_world_state,
        committed_plans={},
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
    )
    candidate = generate_candidates(snapshot=snapshot)[0]
    gate_result = accept_candidate(snapshot=snapshot, candidate=candidate)
    committed_plan = commit_candidate(snapshot=snapshot, candidate=candidate, gate_result=gate_result)
    return committed_plan


def test_validate_transition_rejects_illegal_state_jump() -> None:
    with pytest.raises(ValueError, match="illegal state transition"):
        validate_transition(ExecutionState.PLANNING, ExecutionState.POST_MERGE)


def test_planning_transition_uses_explicit_signal_and_emergency_tail_boundary() -> None:
    scenario = ScenarioConfig(scenario_id="boundary")
    at_boundary = _make_vehicle(
        veh_id="r0",
        stream="ramp",
        lane_id="ramp_0",
        x_pos_m=290.0,
        speed_mps=0.0,
        is_cav=True,
        execution_state=ExecutionState.PLANNING,
        commit_state=CommitState.UNCOMMITTED,
    )
    past_boundary = deepcopy(at_boundary)
    past_boundary.x_pos_m = 290.1

    next_state_a, reason_a = resolve_planning_transition(
        at_boundary,
        scenario=scenario,
        signal=PlannerSignal.NO_FEASIBLE_PLAN,
    )
    next_state_b, reason_b = resolve_planning_transition(
        past_boundary,
        scenario=scenario,
        signal=PlannerSignal.NO_FEASIBLE_PLAN,
    )

    assert in_emergency_tail(at_boundary, scenario) is False
    assert in_emergency_tail(past_boundary, scenario) is True
    assert next_state_a is ExecutionState.PLANNING
    assert reason_a is TransitionReason.WAIT_NO_FEASIBLE_PLAN
    assert next_state_b is ExecutionState.FAIL_SAFE_STOP
    assert reason_b is TransitionReason.FAIL_SAFE_EMERGENCY_TAIL


def test_approaching_vehicle_enters_planning_on_rollout() -> None:
    scenario = ScenarioConfig(scenario_id="approaching")
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=10.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }

    next_world_state = rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans={},
    )

    assert next_world_state["r0"].execution_state is ExecutionState.PLANNING
    assert next_world_state["r0"].x_pos_m > world_state["r0"].x_pos_m


def test_rollout_progresses_committed_chain_to_post_merge() -> None:
    scenario = ScenarioConfig(scenario_id="chain")
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=188.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    committed_plan = _make_committed_plan_for_vehicle(world_state)
    committed_plans = {"r0": committed_plan}

    world_state = rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans=committed_plans,
    )
    assert world_state["r0"].execution_state is ExecutionState.COMMITTED
    assert world_state["r0"].commit_state is CommitState.COMMITTED

    world_state = rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans=committed_plans,
    )
    assert world_state["r0"].execution_state is ExecutionState.EXECUTING

    world_state = rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans=committed_plans,
    )
    assert world_state["r0"].execution_state is ExecutionState.POST_MERGE


def test_rollout_waits_under_repeated_no_feasible_plan_until_tail() -> None:
    scenario = ScenarioConfig(scenario_id="wait")
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=289.9,
            speed_mps=1.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }

    world_state = rollout_step(scenario=scenario, world_state=world_state, committed_plans={})
    assert world_state["r0"].execution_state is ExecutionState.PLANNING
    assert world_state["r0"].x_pos_m == pytest.approx(290.0)

    world_state = rollout_step(scenario=scenario, world_state=world_state, committed_plans={})
    assert world_state["r0"].execution_state is ExecutionState.PLANNING
    assert world_state["r0"].x_pos_m == pytest.approx(290.1)

    world_state = rollout_step(scenario=scenario, world_state=world_state, committed_plans={})
    assert world_state["r0"].execution_state is ExecutionState.FAIL_SAFE_STOP


def test_fail_safe_stop_aborts_once_and_stays_aborted() -> None:
    scenario = ScenarioConfig(scenario_id="abort")
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=291.0,
            speed_mps=0.3,
            is_cav=True,
            execution_state=ExecutionState.FAIL_SAFE_STOP,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }

    next_world_state = rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans={},
    )
    assert next_world_state["r0"].execution_state is ExecutionState.ABORTED
    assert TransitionReason.ABORT_AFTER_FAIL_SAFE_STOP.value == "abort_after_fail_safe_stop"

    final_world_state = rollout_step(
        scenario=scenario,
        world_state=next_world_state,
        committed_plans={},
    )
    assert final_world_state["r0"].execution_state is ExecutionState.ABORTED


def test_rollout_does_not_mutate_committed_plan_semantic_fields() -> None:
    scenario = ScenarioConfig(scenario_id="immutable")
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=188.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    committed_plan = _make_committed_plan_for_vehicle(world_state, scenario_id="immutable_plan")
    committed_plans = {"r0": committed_plan}
    before = (
        committed_plan.candidate.target_gap.pred_id,
        committed_plan.candidate.target_gap.foll_id,
        committed_plan.candidate.x_m_m,
        committed_plan.candidate.t_m_s,
        committed_plan.candidate.partner_ids,
        committed_plan.candidate.sequence_relation,
    )

    rollout_step(
        scenario=scenario,
        world_state=world_state,
        committed_plans=committed_plans,
    )

    after = (
        committed_plan.candidate.target_gap.pred_id,
        committed_plan.candidate.target_gap.foll_id,
        committed_plan.candidate.x_m_m,
        committed_plan.candidate.t_m_s,
        committed_plan.candidate.partner_ids,
        committed_plan.candidate.sequence_relation,
    )
    assert before == after


def test_derive_planner_signal_is_explicit() -> None:
    assert derive_planner_signal("r0", {}) is PlannerSignal.NO_FEASIBLE_PLAN
    assert derive_planner_signal("r0", {"r0": object()}) is PlannerSignal.COMMIT_AVAILABLE
