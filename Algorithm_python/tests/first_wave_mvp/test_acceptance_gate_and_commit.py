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
from first_wave_mvp.snapshot import build_snapshot  # noqa: E402
from first_wave_mvp.step2_fifo import generate_candidates  # noqa: E402
from first_wave_mvp.types import (  # noqa: E402
    CandidatePlan,
    CommitState,
    ExecutionState,
    GapRef,
    PolicyTag,
    RejectReason,
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


def _build_snapshot_and_candidate(
    *,
    world_state: dict[str, VehicleState],
    policy_tag: PolicyTag = PolicyTag.FIFO_FIXED_ANCHOR,
    scenario: ScenarioConfig | None = None,
) -> tuple:
    snapshot = build_snapshot(
        sim_time_s=0.0,
        scenario=scenario or ScenarioConfig(scenario_id="scenario"),
        world_state=world_state,
        committed_plans={},
        policy_tag=policy_tag,
    )
    candidates = generate_candidates(snapshot=snapshot)
    assert candidates, "expected at least one candidate"
    return snapshot, candidates[0]


def _clone_candidate(candidate: CandidatePlan, **updates) -> CandidatePlan:
    cloned = deepcopy(candidate)
    for key, value in updates.items():
        setattr(cloned, key, value)
    return cloned


def test_accept_candidate_accepts_valid_candidate() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)

    result = accept_candidate(snapshot=snapshot, candidate=candidate)

    assert result.accepted is True
    assert result.reject_reason is None
    assert result.binding_check == "accept"


def test_accept_candidate_is_pure_and_idempotent() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    before = (
        candidate.x_m_m,
        candidate.t_m_s,
        candidate.target_gap.pred_id,
        candidate.target_gap.foll_id,
        candidate.partner_ids,
        candidate.sequence_relation,
    )

    first = accept_candidate(snapshot=snapshot, candidate=candidate)
    second = accept_candidate(snapshot=snapshot, candidate=candidate)
    after = (
        candidate.x_m_m,
        candidate.t_m_s,
        candidate.target_gap.pred_id,
        candidate.target_gap.foll_id,
        candidate.partner_ids,
        candidate.sequence_relation,
    )

    assert first == second
    assert before == after


def test_accept_candidate_rejects_invalid_partner() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    invalid_candidate = _clone_candidate(candidate, partner_ids=("ghost",))

    result = accept_candidate(snapshot=snapshot, candidate=invalid_candidate)

    assert result.accepted is False
    assert result.reject_reason is RejectReason.REJECT_PARTNER_INVALID


def test_accept_candidate_rejects_zone_violation() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    invalid_candidate = _clone_candidate(candidate, x_s_m=40.0)

    result = accept_candidate(snapshot=snapshot, candidate=invalid_candidate)

    assert result.reject_reason is RejectReason.REJECT_ZONE


def test_accept_candidate_rejects_timing_violation() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    invalid_candidate = _clone_candidate(candidate, tau_lc_s=-0.1)

    result = accept_candidate(snapshot=snapshot, candidate=invalid_candidate)

    assert result.reject_reason is RejectReason.REJECT_TIMING


def test_accept_candidate_rejects_gap_identity_violation() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    invalid_candidate = _clone_candidate(candidate, target_gap=GapRef(pred_id="m0", foll_id=None))

    result = accept_candidate(snapshot=snapshot, candidate=invalid_candidate)

    assert result.reject_reason is RejectReason.REJECT_GAP_IDENTITY


def test_accept_candidate_rejects_dynamic_limit_violation() -> None:
    world_state = {
        "r0": _make_vehicle(
            veh_id="r0",
            stream="ramp",
            lane_id="ramp_0",
            x_pos_m=100.0,
            speed_mps=20.0,
            is_cav=True,
            execution_state=ExecutionState.PLANNING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)

    result = accept_candidate(snapshot=snapshot, candidate=candidate)

    assert result.reject_reason is RejectReason.REJECT_DYNAMIC_LIMIT


def test_accept_candidate_rejects_interval_safety_violation() -> None:
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
        "m_pred": _make_vehicle(
            veh_id="m_pred",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=108.0,
            speed_mps=10.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)

    result = accept_candidate(snapshot=snapshot, candidate=candidate)

    assert result.reject_reason is RejectReason.REJECT_INTERVAL_SAFETY
    assert result.min_margin_m is not None
    assert result.min_margin_m < 0.0


def test_accept_candidate_rejects_post_merge_safety_violation() -> None:
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
        "m_pred": _make_vehicle(
            veh_id="m_pred",
            stream="mainline",
            lane_id="main_0",
            x_pos_m=133.0,
            speed_mps=8.0,
            is_cav=False,
            execution_state=ExecutionState.APPROACHING,
            commit_state=CommitState.UNCOMMITTED,
        ),
    }
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    post_risky_candidate = _clone_candidate(candidate, tau_lc_s=6.9)

    result = accept_candidate(snapshot=snapshot, candidate=post_risky_candidate)

    assert result.reject_reason is RejectReason.REJECT_POST_MERGE_SAFETY
    assert result.min_margin_m is not None
    assert result.min_margin_m < 0.0


def test_commit_candidate_requires_accepted_true() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    gate_result = accept_candidate(snapshot=snapshot, candidate=_clone_candidate(candidate, x_s_m=40.0))

    with pytest.raises(ValueError, match="accepted=True"):
        commit_candidate(snapshot=snapshot, candidate=candidate, gate_result=gate_result)


def test_commit_candidate_rejects_binding_mismatch_and_illegal_state() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    accepted_result = accept_candidate(snapshot=snapshot, candidate=candidate)

    mismatched_result = deepcopy(accepted_result)
    mismatched_result.candidate_id = "other"
    with pytest.raises(ValueError, match="candidate_id mismatch"):
        commit_candidate(snapshot=snapshot, candidate=candidate, gate_result=mismatched_result)

    bad_snapshot = deepcopy(snapshot)
    bad_snapshot.ego_state.execution_state = ExecutionState.APPROACHING
    with pytest.raises(ValueError, match="execution_state=planning"):
        commit_candidate(snapshot=bad_snapshot, candidate=candidate, gate_result=accepted_result)


def test_commit_candidate_returns_isolated_committed_copy() -> None:
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
    snapshot, candidate = _build_snapshot_and_candidate(world_state=world_state)
    gate_result = accept_candidate(snapshot=snapshot, candidate=candidate)

    committed_plan = commit_candidate(snapshot=snapshot, candidate=candidate, gate_result=gate_result)
    candidate.x_m_m = 999
    gate_result.binding_check = "mutated"

    assert committed_plan.commit_state is CommitState.COMMITTED
    assert committed_plan.execution_state is ExecutionState.COMMITTED
    assert committed_plan.candidate.x_m_m != 999
    assert committed_plan.gate_result.binding_check == "accept"
