from __future__ import annotations

import sys
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from first_wave_mvp.snapshot import build_snapshot, select_planning_ego  # noqa: E402
from first_wave_mvp.step2_fifo import generate_candidates  # noqa: E402
from first_wave_mvp.types import (  # noqa: E402
    CandidatePlan,
    CommitState,
    CommittedPlan,
    ExecutionState,
    GapRef,
    GateResult,
    PlanningSnapshot,
    PolicyTag,
    ScenarioConfig,
    VehicleState,
)


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


def _make_committed_plan(*, veh_id: str, t_m_s: float) -> CommittedPlan:
    candidate = CandidatePlan(
        snapshot_id=f"snap:{veh_id}",
        candidate_id=f"candidate:{veh_id}",
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        ego_id=veh_id,
        target_gap=GapRef(pred_id=None, foll_id=None),
        x_m_m=170,
        t_m_s=t_m_s,
        t_r_free_s=t_m_s,
        partner_ids=tuple(),
        sequence_relation="single_gap",
        tau_lc_s=t_m_s - 3.0,
        x_s_m=140.0,
        objective_key=(t_m_s, 0.0, 170),
    )
    gate_result = GateResult(
        snapshot_id=f"snap:{veh_id}",
        candidate_id=f"candidate:{veh_id}",
        accepted=True,
        reject_reason=None,
        checked_time_grid_s=(t_m_s,),
    )
    return CommittedPlan(
        snapshot_id=f"snap:{veh_id}",
        candidate_id=f"candidate:{veh_id}",
        commit_time_s=t_m_s - 0.1,
        commit_state=CommitState.COMMITTED,
        execution_state=ExecutionState.COMMITTED,
        candidate=candidate,
        gate_result=gate_result,
    )


def _build_snapshot(
    *,
    policy_tag: PolicyTag,
    world_state: dict[str, VehicleState],
    committed_plans: dict[str, CommittedPlan] | None = None,
    scenario: ScenarioConfig | None = None,
    sim_time_s: float = 0.0,
) -> PlanningSnapshot:
    return build_snapshot(
        sim_time_s=sim_time_s,
        scenario=scenario or ScenarioConfig(scenario_id="scenario"),
        world_state=world_state,
        committed_plans=committed_plans or {},
        policy_tag=policy_tag,
    )


def test_select_planning_ego_returns_frontmost_uncommitted_ramp_cav() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=10.0,
            speed_mps=8.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "r1": _make_vehicle(
            veh_id="r1",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=25.0,
            speed_mps=8.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "r2": _make_vehicle(
            veh_id="r2",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=30.0,
            speed_mps=8.0,
            is_cav=True,
            execution_state=ExecutionState.COMMITTED,
            commit_state=CommitState.COMMITTED,
        ),
    }

    ego = select_planning_ego(world_state)

    assert ego is not None
    assert ego.veh_id == "r1"


def test_build_snapshot_rejects_when_no_eligible_ramp_ego() -> None:
    world_state = {
        "m0": _make_vehicle(
            veh_id="m0",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=50.0,
            speed_mps=15.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }

    with pytest.raises(ValueError, match="No eligible ramp ego"):
        _build_snapshot(
            policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
            world_state=world_state,
        )


def test_build_snapshot_deepcopies_world_state_and_committed_plans() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=80.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m0": _make_vehicle(
            veh_id="m0",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=90.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    committed_plans = {"c0": _make_committed_plan(veh_id="c0", t_m_s=11.0)}

    snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=world_state,
        committed_plans=committed_plans,
    )

    world_state["r0"].x_pos_m = 5.0
    committed_plans["c0"].candidate.t_m_s = 99.0

    assert snapshot.ego_state.x_pos_m == 80.0
    assert snapshot.committed_plans["c0"].candidate.t_m_s == 11.0
    assert snapshot.target_lane_object_ids == ("c0", "m0")


def test_generate_candidates_fixed_anchor_handles_empty_target_lane() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=100.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=world_state,
    )

    candidates = generate_candidates(snapshot=snapshot)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target_gap.pred_id is None
    assert candidate.target_gap.foll_id is None
    assert candidate.x_m_m == 170
    assert candidate.candidate_id == f"{snapshot.snapshot_id}:{snapshot.policy_tag.value}:170:none:none"


def test_generate_candidates_respects_dynamic_x_lb() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=0.0,
            speed_mps=60.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }

    fixed_snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=world_state,
    )
    flex_snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR,
        world_state=world_state,
    )

    fixed_candidates = generate_candidates(snapshot=fixed_snapshot)
    flex_candidates = generate_candidates(snapshot=flex_snapshot)

    assert fixed_candidates == []
    assert flex_candidates[0].x_m_m == 230


def test_generate_candidates_returns_empty_when_l_exceeds_u() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=70.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m_pred": _make_vehicle(
            veh_id="m_pred",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=80.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m_foll": _make_vehicle(
            veh_id="m_foll",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=65.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=world_state,
    )

    assert generate_candidates(snapshot=snapshot) == []


def test_generate_candidates_uses_tie_break_and_is_input_order_invariant() -> None:
    ordered_world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=70.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m1": _make_vehicle(
            veh_id="m1",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=70.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m2": _make_vehicle(
            veh_id="m2",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=30.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    shuffled_world_state = {
        "m2": ordered_world_state["m2"],
        "m1": ordered_world_state["m1"],
        "r0": ordered_world_state["r0"],
    }

    snapshot_a = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=ordered_world_state,
    )
    snapshot_b = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        world_state=shuffled_world_state,
    )

    candidates_a = generate_candidates(snapshot=snapshot_a)
    candidates_b = generate_candidates(snapshot=snapshot_b)

    assert len(candidates_a) == 1
    assert len(candidates_b) == 1
    assert candidates_a[0].target_gap.pred_id == "m1"
    assert candidates_a[0].target_gap.foll_id == "m2"
    assert [
        (candidate.x_m_m, candidate.objective_key, candidate.target_gap.pred_id, candidate.target_gap.foll_id)
        for candidate in candidates_a
    ] == [
        (candidate.x_m_m, candidate.objective_key, candidate.target_gap.pred_id, candidate.target_gap.foll_id)
        for candidate in candidates_b
    ]


def test_generate_candidates_are_stable_across_repeated_runs_and_source_mutation() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=100.0,
            speed_mps=10.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
        "m0": _make_vehicle(
            veh_id="m0",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=95.0,
            speed_mps=9.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot = _build_snapshot(
        policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR,
        world_state=world_state,
    )

    baseline = [
        (candidate.candidate_id, candidate.x_m_m, candidate.objective_key)
        for candidate in generate_candidates(snapshot=snapshot)
    ]
    world_state["r0"].x_pos_m = 0.0
    world_state["m0"].x_pos_m = 0.0

    for _ in range(3):
        rerun = [
            (candidate.candidate_id, candidate.x_m_m, candidate.objective_key)
            for candidate in generate_candidates(snapshot=snapshot)
        ]
        assert rerun == baseline
