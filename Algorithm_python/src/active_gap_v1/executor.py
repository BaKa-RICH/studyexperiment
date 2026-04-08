"""Execution layer: merge/coordination branches, rollout, and decision logic."""

from __future__ import annotations

from .certificate import build_safety_certificate
from .merge_target_planner import enumerate_merge_targets
from .predictor import predict_free_position
from .quintic import (
    _accel_coeffs,
    _solve_one_quintic,
    _velocity_coeffs,
    eval_poly,
    solve_tcg_quintics,
)
from .state_machine import check_tcg_validity, validate_transition
from .types import (
    AnchorMode,
    CertificateFailureKind,
    CoordinationSnapshot,
    ExecutionDecision,
    ExecutionDecisionTag,
    ExecutionState,
    MergeTarget,
    QuinticBoundaryState,
    QuinticLongitudinalProfile,
    RollingPlanSlice,
    SafetyCertificate,
    ScenarioConfig,
    SliceKind,
    TCG,
    VehicleState,
)

N_COORD_MAX = 50
EPS_PROGRESS = 0.01
N_EMERGENCY_MAX = 3
_GAP_READY_RATIO = 0.5


def _try_certified_merge(
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> tuple[MergeTarget, tuple[QuinticLongitudinalProfile, ...], SafetyCertificate] | None:
    cfg = snapshot.scenario
    states = snapshot.control_zone_states
    p_st = states[tcg.p_id]
    m_st = states[tcg.m_id]
    s_st = states[tcg.s_id]

    v_ref = (p_st.speed_mps + m_st.speed_mps + s_st.speed_mps) / 3.0
    d_pm = cfg.vehicle_length_m + cfg.min_gap_m + cfg.h_pr_s * v_ref
    d_ms = cfg.vehicle_length_m + cfg.min_gap_m + cfg.h_rf_s * v_ref
    gap_needed = d_pm + d_ms
    gap_current = p_st.x_pos_m - s_st.x_pos_m

    if gap_current < _GAP_READY_RATIO * gap_needed:
        return None

    targets = enumerate_merge_targets(snapshot=snapshot, tcg=tcg)
    for target in targets:
        profiles = solve_tcg_quintics(snapshot=snapshot, tcg=tcg, target=target)
        cert = build_safety_certificate(
            snapshot=snapshot, tcg=tcg, slice_kind=SliceKind.MERGE,
            profiles=profiles, target=target,
        )
        if cert.failure_kind is None:
            return target, profiles, cert
    return None


def _constant_accel_coeffs(
    x0: float, v0: float, a: float,
) -> tuple[float, float, float, float, float, float]:
    """Build a quadratic profile (constant acceleration) stored in quintic format."""
    return (x0, v0, 0.5 * a, 0.0, 0.0, 0.0)


def synthesize_coordination_slice(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> RollingPlanSlice | None:
    cfg = snapshot.scenario
    states = snapshot.control_zone_states
    dt = cfg.planning_tick_s

    p_st = states[tcg.p_id]
    m_st = states[tcg.m_id]
    s_st = states[tcg.s_id]

    v_target = (p_st.speed_mps + m_st.speed_mps + s_st.speed_mps) / 3.0

    gap_current = p_st.x_pos_m - s_st.x_pos_m
    d_pm = cfg.vehicle_length_m + cfg.min_gap_m + cfg.h_pr_s * v_target
    d_ms = cfg.vehicle_length_m + cfg.min_gap_m + cfg.h_rf_s * v_target
    gap_needed = d_pm + d_ms

    if gap_current < gap_needed:
        p_v_target = min(p_st.speed_mps + cfg.a_max_mps2 * dt, cfg.mainline_vmax_mps)
        s_v_target = max(s_st.speed_mps - cfg.comfortable_brake_mps2 * dt, 0.0)
    else:
        p_v_target = v_target
        s_v_target = v_target

    m_v_target = m_st.speed_mps

    vehicles = [
        (tcg.p_id, p_st, p_v_target),
        (tcg.m_id, m_st, m_v_target),
        (tcg.s_id, s_st, s_v_target),
    ]

    profiles: list[QuinticLongitudinalProfile] = []
    for vid, vs, vf in vehicles:
        a_desired = (vf - vs.speed_mps) / dt if dt > 0 else 0.0
        xf = vs.x_pos_m + vs.speed_mps * dt + 0.5 * a_desired * dt * dt
        coeffs = _constant_accel_coeffs(vs.x_pos_m, vs.speed_mps, a_desired)
        profiles.append(QuinticLongitudinalProfile(
            vehicle_id=vid, t0_s=snapshot.sim_time_s, horizon_s=dt,
            coefficients=coeffs,
            start_state=QuinticBoundaryState(vs.x_pos_m, vs.speed_mps, vs.accel_mps2),
            terminal_state=QuinticBoundaryState(xf, vf, a_desired),
        ))

    cert = build_safety_certificate(
        snapshot=snapshot, tcg=tcg, slice_kind=SliceKind.COORDINATION,
        profiles=(profiles[0], profiles[1], profiles[2]), target=None,
    )

    if cert.failure_kind is not None:
        return None

    delta_open_before = max(0.0, gap_needed - gap_current)
    p_new_x = profiles[0].terminal_state.x_m
    s_new_x = profiles[2].terminal_state.x_m
    gap_after = p_new_x - s_new_x
    delta_open_after = max(0.0, gap_needed - gap_after)

    dv_before = abs(p_st.speed_mps - m_st.speed_mps) + abs(m_st.speed_mps - s_st.speed_mps)
    dv_after = abs(p_v_target - m_v_target) + abs(m_v_target - s_v_target)

    improved = (
        (delta_open_after < delta_open_before - EPS_PROGRESS)
        or (dv_after < dv_before - EPS_PROGRESS)
    )
    if not improved:
        return None

    return RollingPlanSlice(
        snapshot_id=snapshot.snapshot_id,
        m_id=tcg.m_id,
        slice_kind=SliceKind.COORDINATION,
        tcg=tcg,
        merge_target=None,
        certificate=cert,
        exec_start_s=snapshot.sim_time_s,
        exec_end_s=snapshot.sim_time_s + dt,
        profile_p=profiles[0],
        profile_m=profiles[1],
        profile_s=profiles[2],
        delta_open_before_m=delta_open_before,
        delta_open_after_m=delta_open_after,
        speed_alignment_before_mps=dv_before,
        speed_alignment_after_mps=dv_after,
    )


def commit_first_slice(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    certificate: SafetyCertificate,
    profiles: tuple[
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
    ],
    target: MergeTarget | None,
    slice_kind: SliceKind,
) -> RollingPlanSlice:
    dt = snapshot.scenario.planning_tick_s
    return RollingPlanSlice(
        snapshot_id=snapshot.snapshot_id,
        m_id=tcg.m_id,
        slice_kind=slice_kind,
        tcg=tcg,
        merge_target=target,
        certificate=certificate,
        exec_start_s=snapshot.sim_time_s,
        exec_end_s=snapshot.sim_time_s + dt,
        profile_p=profiles[0],
        profile_m=profiles[1],
        profile_s=profiles[2],
    )


def decide_execution(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG | None,
    plan_slice: RollingPlanSlice | None,
    failure_reason: str | None,
) -> ExecutionDecision:
    ego = snapshot.ego_state
    cfg = snapshot.scenario
    emergency_start = cfg.emergency_tail_m[0]

    if plan_slice is not None:
        if plan_slice.slice_kind == SliceKind.MERGE:
            return ExecutionDecision(
                decision_tag=ExecutionDecisionTag.COMMIT_MERGE_SLICE,
                state_after=ExecutionState.COMMITTED,
                reason="certified_merge_slice_found",
                tcg_locked=True, target_locked=False,
                plan_slice=plan_slice,
            )
        else:
            return ExecutionDecision(
                decision_tag=ExecutionDecisionTag.COMMIT_COORDINATION_SLICE,
                state_after=ExecutionState.COMMITTED,
                reason="certified_coordination_slice_found",
                tcg_locked=True, target_locked=False,
                plan_slice=plan_slice,
            )

    if ego.x_pos_m >= emergency_start:
        return ExecutionDecision(
            decision_tag=ExecutionDecisionTag.FAIL_SAFE_STOP,
            state_after=ExecutionState.FAIL_SAFE_STOP,
            reason=failure_reason or "ego_in_emergency_tail_no_certified_slice",
            tcg_locked=False, target_locked=False,
        )

    return ExecutionDecision(
        decision_tag=ExecutionDecisionTag.SAFE_WAIT,
        state_after=ExecutionState.PLANNING,
        reason=failure_reason or "no_certified_slice_safe_to_wait",
        tcg_locked=False, target_locked=False,
    )


def rollout_step(
    *,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    active_slices: dict[str, RollingPlanSlice],
) -> dict[str, VehicleState]:
    dt = scenario.rollout_tick_s
    new_state: dict[str, VehicleState] = {}

    controlled_ids: set[str] = set()
    for slice_owner, rps in active_slices.items():
        for prof in (rps.profile_p, rps.profile_m, rps.profile_s):
            vid = prof.vehicle_id
            controlled_ids.add(vid)
            vs = world_state[vid]

            vc = _velocity_coeffs(prof.coefficients)
            ac = _accel_coeffs(prof.coefficients)

            new_x = eval_poly(prof.coefficients, dt)
            new_v = max(0.0, eval_poly(vc, dt))
            new_a = eval_poly(ac, dt)

            new_state[vid] = VehicleState(
                veh_id=vid, stream=vs.stream, lane_id=vs.lane_id,
                x_pos_m=new_x, speed_mps=new_v, accel_mps2=new_a,
                length_m=vs.length_m, is_cav=vs.is_cav,
                execution_state=vs.execution_state,
            )

    for vid, vs in world_state.items():
        if vid not in controlled_ids:
            new_state[vid] = VehicleState(
                veh_id=vid, stream=vs.stream, lane_id=vs.lane_id,
                x_pos_m=vs.x_pos_m + vs.speed_mps * dt,
                speed_mps=vs.speed_mps, accel_mps2=0.0,
                length_m=vs.length_m, is_cav=vs.is_cav,
                execution_state=vs.execution_state,
            )

    return new_state
