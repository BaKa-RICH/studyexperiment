"""Tests for T4: execution layer and state machine."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src"))

from active_gap_v1.types import (
    AnchorMode, CoordinationSnapshot, ExecutionDecisionTag,
    ExecutionState, MergeTarget, PlannerTag, ScenarioConfig,
    SliceKind, TCG, VehicleState,
)
from active_gap_v1.config import default_scenario_config
from active_gap_v1.snapshot import build_coordination_snapshot
from active_gap_v1.tcg_selector import identify_tcg
from active_gap_v1.merge_target_planner import enumerate_merge_targets
from active_gap_v1.quintic import solve_tcg_quintics
from active_gap_v1.certificate import build_safety_certificate
from active_gap_v1.state_machine import validate_transition, check_tcg_validity, is_terminal
from active_gap_v1.executor import (
    commit_first_slice, decide_execution, rollout_step,
    synthesize_coordination_slice, _try_certified_merge,
    _coordination_metrics_from_states, _coordination_reference,
    N_COORD_MAX, EPS_PROGRESS,
)


def _a0_world(v0: float = 16.7) -> dict[str, VehicleState]:
    def vs(vid: str, stream: str, x: float) -> VehicleState:
        return VehicleState(vid, stream, f"{stream}_0", x, v0, 0.0, 5.0, True, ExecutionState.PLANNING)
    return {"p": vs("p", "mainline", 11.0), "m": vs("m", "ramp", 9.0), "s": vs("s", "mainline", 5.0)}


def _a0_world_wide_gap(v0: float = 16.7) -> dict[str, VehicleState]:
    """Layout where p-s gap is already large enough for merge gate to pass."""
    def vs(vid: str, stream: str, x: float) -> VehicleState:
        return VehicleState(vid, stream, f"{stream}_0", x, v0, 0.0, 5.0, True, ExecutionState.PLANNING)
    return {"p": vs("p", "mainline", 80.0), "m": vs("m", "ramp", 45.0), "s": vs("s", "mainline", 0.0)}


def _snap_and_tcg(mode: AnchorMode = AnchorMode.FLEXIBLE, wide_gap: bool = False):
    cfg = default_scenario_config()
    world = _a0_world_wide_gap() if wide_gap else _a0_world()
    snap = build_coordination_snapshot(
        sim_time_s=0.0, scenario=cfg, world_state=world,
        locked_tcgs={}, planner_tag=PlannerTag.ACTIVE_GAP, anchor_mode=mode,
    )
    tcg = identify_tcg(snapshot=snap)
    return snap, tcg


def test_valid_transitions():
    assert validate_transition(ExecutionState.APPROACHING, ExecutionState.PLANNING) is None
    assert validate_transition(ExecutionState.PLANNING, ExecutionState.COMMITTED) is None
    assert validate_transition(ExecutionState.COMMITTED, ExecutionState.EXECUTING) is None
    assert validate_transition(ExecutionState.EXECUTING, ExecutionState.POST_MERGE) is None
    assert validate_transition(ExecutionState.FAIL_SAFE_STOP, ExecutionState.ABORTED) is None


def test_invalid_transitions():
    assert validate_transition(ExecutionState.PLANNING, ExecutionState.EXECUTING) is not None
    assert validate_transition(ExecutionState.COMMITTED, ExecutionState.PLANNING) is not None
    assert validate_transition(ExecutionState.ABORTED, ExecutionState.PLANNING) is not None
    assert validate_transition(ExecutionState.POST_MERGE, ExecutionState.PLANNING) is not None


def test_tcg_validity_check():
    assert check_tcg_validity(10.0, 9.0, 5.0, 600.0) is True
    assert check_tcg_validity(10.0, 9.0, -1.0, 600.0) is False
    assert check_tcg_validity(601.0, 9.0, 5.0, 600.0) is False


def test_merge_branch_iterates_candidates():
    snap, tcg = _snap_and_tcg(AnchorMode.FLEXIBLE, wide_gap=True)
    result = _try_certified_merge(snap, tcg)
    assert result is not None, "A0 flexible should find a certified merge target"
    target, profiles, cert = result
    assert cert.failure_kind is None
    assert target.delta_open_m >= 0.0


def test_merge_branch_blocks_initial_pairwise_unready_state():
    snap, tcg = _snap_and_tcg()
    result = _try_certified_merge(snap, tcg)
    assert result is None


def test_coordination_slice_basic():
    snap, tcg = _snap_and_tcg()
    coord = synthesize_coordination_slice(snapshot=snap, tcg=tcg)
    assert coord is not None
    assert coord.slice_kind == SliceKind.COORDINATION
    assert coord.certificate.failure_kind is None


def test_coordination_reduces_pairwise_virtual_gap_error():
    snap, tcg = _snap_and_tcg()
    coord = synthesize_coordination_slice(snapshot=snap, tcg=tcg)
    assert coord is not None

    x_m_expected, v_ref = _coordination_reference(snapshot=snap, tcg=tcg)
    before = _coordination_metrics_from_states(
        scenario=snap.scenario,
        p_x=snap.control_zone_states["p"].x_pos_m,
        p_v=snap.control_zone_states["p"].speed_mps,
        m_x=snap.control_zone_states["m"].x_pos_m,
        m_v=snap.control_zone_states["m"].speed_mps,
        s_x=snap.control_zone_states["s"].x_pos_m,
        s_v=snap.control_zone_states["s"].speed_mps,
        x_m_expected=x_m_expected,
        v_ref=v_ref,
    )
    after = _coordination_metrics_from_states(
        scenario=snap.scenario,
        p_x=coord.profile_p.terminal_state.x_m,
        p_v=coord.profile_p.terminal_state.v_mps,
        m_x=coord.profile_m.terminal_state.x_m,
        m_v=coord.profile_m.terminal_state.v_mps,
        s_x=coord.profile_s.terminal_state.x_m,
        s_v=coord.profile_s.terminal_state.v_mps,
        x_m_expected=x_m_expected,
        v_ref=v_ref,
        xi_override=float(before["xi"]),
    )
    assert (
        after["e_pm_virt"] < before["e_pm_virt"] - EPS_PROGRESS
        or after["e_ms_virt"] < before["e_ms_virt"] - EPS_PROGRESS
    )


def test_decide_execution_merge_found():
    snap, tcg = _snap_and_tcg(wide_gap=True)
    result = _try_certified_merge(snap, tcg)
    assert result is not None
    target, profiles, cert = result
    plan = commit_first_slice(
        snapshot=snap, tcg=tcg, certificate=cert,
        profiles=profiles, target=target, slice_kind=SliceKind.MERGE,
    )
    decision = decide_execution(
        snapshot=snap, tcg=tcg, plan_slice=plan, failure_reason=None,
    )
    assert decision.decision_tag == ExecutionDecisionTag.COMMIT_MERGE_SLICE
    assert decision.state_after == ExecutionState.COMMITTED


def test_decide_execution_no_slice_safe_wait():
    snap, tcg = _snap_and_tcg()
    decision = decide_execution(
        snapshot=snap, tcg=tcg, plan_slice=None, failure_reason="no_certified_slice",
    )
    assert decision.decision_tag == ExecutionDecisionTag.SAFE_WAIT
    assert decision.state_after == ExecutionState.PLANNING


def test_decide_execution_emergency_tail():
    cfg = default_scenario_config()
    world = _a0_world()
    world["m"] = VehicleState("m", "ramp", "ramp_0", 291.0, 16.7, 0.0, 5.0, True, ExecutionState.PLANNING)
    snap = build_coordination_snapshot(
        sim_time_s=0.0, scenario=cfg, world_state=world,
        locked_tcgs={}, planner_tag=PlannerTag.ACTIVE_GAP, anchor_mode=AnchorMode.FLEXIBLE,
    )
    tcg = identify_tcg(snapshot=snap)
    decision = decide_execution(
        snapshot=snap, tcg=tcg, plan_slice=None, failure_reason="all_branches_failed",
    )
    assert decision.decision_tag == ExecutionDecisionTag.FAIL_SAFE_STOP


def test_rollout_advances_state():
    snap, tcg = _snap_and_tcg(wide_gap=True)
    result = _try_certified_merge(snap, tcg)
    assert result is not None
    target, profiles, cert = result
    plan = commit_first_slice(
        snapshot=snap, tcg=tcg, certificate=cert,
        profiles=profiles, target=target, slice_kind=SliceKind.MERGE,
    )
    new_world = rollout_step(
        scenario=snap.scenario, world_state=snap.control_zone_states,
        active_slices={"m": plan},
    )
    for vid in ["p", "m", "s"]:
        old = snap.control_zone_states[vid]
        new = new_world[vid]
        assert new.x_pos_m != old.x_pos_m or abs(old.speed_mps) < 1e-9, f"{vid} should have moved"


def test_rollout_does_not_modify_tcg_fields():
    snap, tcg = _snap_and_tcg(wide_gap=True)
    result = _try_certified_merge(snap, tcg)
    assert result is not None
    target, profiles, cert = result
    plan = commit_first_slice(
        snapshot=snap, tcg=tcg, certificate=cert,
        profiles=profiles, target=target, slice_kind=SliceKind.MERGE,
    )
    tcg_before = (tcg.p_id, tcg.m_id, tcg.s_id, tcg.anchor_mode)
    _ = rollout_step(
        scenario=snap.scenario, world_state=snap.control_zone_states,
        active_slices={"m": plan},
    )
    tcg_after = (tcg.p_id, tcg.m_id, tcg.s_id, tcg.anchor_mode)
    assert tcg_before == tcg_after


def test_terminal_states():
    assert is_terminal(ExecutionState.POST_MERGE) is True
    assert is_terminal(ExecutionState.ABORTED) is True
    assert is_terminal(ExecutionState.PLANNING) is False
