"""Execution layer: merge/coordination branches, rollout, and decision logic."""

from __future__ import annotations

from .certificate import build_safety_certificate
from .merge_target_planner import enumerate_merge_targets
from .quintic import (
    _accel_coeffs,
    _velocity_coeffs,
    eval_poly,
    solve_tcg_quintics,
)
from .types import (
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
_PROGRESS_EPS_M = 1.0
_MERGE_PROGRESS_READY_XI = 0.35
_PAIRWISE_GAP_READY_MARGIN_M = 1.0
_REL_SPEED_READY_MPS = 4.5
_OPEN_GAIN = 0.30
_BALANCE_GAIN = 0.18
_SYNC_GAIN = 0.40


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _coordination_reference(
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> tuple[float, float]:
    targets = enumerate_merge_targets(snapshot=snapshot, tcg=tcg)
    if targets:
        return targets[0].x_m_star_m, targets[0].v_star_mps

    cfg = snapshot.scenario
    states = snapshot.control_zone_states
    p_st = states[tcg.p_id]
    m_st = states[tcg.m_id]
    s_st = states[tcg.s_id]
    v_ref = min(
        cfg.ramp_vmax_mps,
        cfg.mainline_vmax_mps,
        (p_st.speed_mps + m_st.speed_mps + s_st.speed_mps) / 3.0,
    )
    x_ref = float(_clamp(cfg.fixed_anchor_m, cfg.legal_merge_zone_m[0], cfg.legal_merge_zone_m[1]))
    return x_ref, v_ref


def _coordination_metrics_from_states(
    *,
    scenario: ScenarioConfig,
    p_x: float,
    p_v: float,
    m_x: float,
    m_v: float,
    s_x: float,
    s_v: float,
    x_m_expected: float,
    v_ref: float,
    xi_override: float | None = None,
) -> dict[str, float | bool]:
    x_entry = float(scenario.ramp_approach_subzone_m[0])
    progress_den = max(x_m_expected - x_entry, _PROGRESS_EPS_M)
    xi = _clamp((m_x - x_entry) / progress_den, 0.0, 1.0)
    if xi_override is not None:
        xi = _clamp(xi_override, 0.0, 1.0)

    d_pm_virt = scenario.vehicle_length_m + scenario.min_gap_m + xi * scenario.h_pr_s * max(m_v, 0.0)
    d_ms_virt = scenario.vehicle_length_m + scenario.min_gap_m + xi * scenario.h_rf_s * max(s_v, 0.0)
    gap_pm = p_x - m_x
    gap_ms = m_x - s_x
    e_pm_virt = max(0.0, d_pm_virt - gap_pm)
    e_ms_virt = max(0.0, d_ms_virt - gap_ms)

    d_pm_hard = scenario.vehicle_length_m + scenario.min_gap_m + scenario.h_pr_s * max(v_ref, 0.0)
    d_ms_hard = scenario.vehicle_length_m + scenario.min_gap_m + scenario.h_rf_s * max(v_ref, 0.0)
    hard_gap_pm_deficit = max(0.0, d_pm_hard - gap_pm)
    hard_gap_ms_deficit = max(0.0, d_ms_hard - gap_ms)

    dv_pm = abs(p_v - m_v)
    dv_ms = abs(m_v - s_v)

    return {
        "xi": xi,
        "gap_pm": gap_pm,
        "gap_ms": gap_ms,
        "d_pm_virt": d_pm_virt,
        "d_ms_virt": d_ms_virt,
        "e_pm_virt": e_pm_virt,
        "e_ms_virt": e_ms_virt,
        "d_pm_hard": d_pm_hard,
        "d_ms_hard": d_ms_hard,
        "hard_gap_pm_deficit": hard_gap_pm_deficit,
        "hard_gap_ms_deficit": hard_gap_ms_deficit,
        "dv_pm": dv_pm,
        "dv_ms": dv_ms,
        "pairwise_gap_ready": (
            xi >= _MERGE_PROGRESS_READY_XI
            and e_pm_virt <= _PAIRWISE_GAP_READY_MARGIN_M
            and e_ms_virt <= _PAIRWISE_GAP_READY_MARGIN_M
        ),
        "relative_speed_ready": (
            dv_pm <= _REL_SPEED_READY_MPS
            and dv_ms <= _REL_SPEED_READY_MPS
        ),
    }


def _terminal_from_accel(
    *,
    vehicle_state: VehicleState,
    accel_cmd_mps2: float,
    dt: float,
    vmax_mps: float,
) -> tuple[float, float, float]:
    vf = _clamp(vehicle_state.speed_mps + accel_cmd_mps2 * dt, 0.0, vmax_mps)
    accel_actual = (vf - vehicle_state.speed_mps) / dt if dt > 0.0 else 0.0
    xf = vehicle_state.x_pos_m + vehicle_state.speed_mps * dt + 0.5 * accel_actual * dt * dt
    return xf, vf, accel_actual


def _try_certified_merge(
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> tuple[MergeTarget, tuple[QuinticLongitudinalProfile, ...], SafetyCertificate] | None:
    states = snapshot.control_zone_states
    p_st = states[tcg.p_id]
    m_st = states[tcg.m_id]
    s_st = states[tcg.s_id]

    targets = enumerate_merge_targets(snapshot=snapshot, tcg=tcg)
    if not targets:
        return None

    x_m_expected, v_ref = targets[0].x_m_star_m, targets[0].v_star_mps
    readiness = _coordination_metrics_from_states(
        scenario=snapshot.scenario,
        p_x=p_st.x_pos_m,
        p_v=p_st.speed_mps,
        m_x=m_st.x_pos_m,
        m_v=m_st.speed_mps,
        s_x=s_st.x_pos_m,
        s_v=s_st.speed_mps,
        x_m_expected=x_m_expected,
        v_ref=v_ref,
    )
    if not readiness["pairwise_gap_ready"] or not readiness["relative_speed_ready"]:
        return None

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

    x_m_expected, v_ref = _coordination_reference(snapshot=snapshot, tcg=tcg)
    metrics_before = _coordination_metrics_from_states(
        scenario=cfg,
        p_x=p_st.x_pos_m,
        p_v=p_st.speed_mps,
        m_x=m_st.x_pos_m,
        m_v=m_st.speed_mps,
        s_x=s_st.x_pos_m,
        s_v=s_st.speed_mps,
        x_m_expected=x_m_expected,
        v_ref=v_ref,
    )

    center_speed = 0.5 * (p_st.speed_mps + s_st.speed_mps)
    a_p_cmd = (
        _OPEN_GAIN * float(metrics_before["e_pm_virt"])
        - _SYNC_GAIN * max(0.0, p_st.speed_mps - m_st.speed_mps)
    )
    a_s_cmd = (
        -_OPEN_GAIN * float(metrics_before["e_ms_virt"])
        + _SYNC_GAIN * max(0.0, m_st.speed_mps - s_st.speed_mps)
    )
    a_m_cmd = (
        _BALANCE_GAIN * (float(metrics_before["e_ms_virt"]) - float(metrics_before["e_pm_virt"]))
        - _SYNC_GAIN * (m_st.speed_mps - center_speed)
    )

    a_p_cmd = _clamp(a_p_cmd, -cfg.comfortable_brake_mps2, cfg.a_max_mps2)
    a_m_cmd = _clamp(a_m_cmd, -cfg.comfortable_brake_mps2, cfg.a_max_mps2)
    a_s_cmd = _clamp(a_s_cmd, -cfg.comfortable_brake_mps2, cfg.a_max_mps2)

    p_xf, p_v_target, a_p_actual = _terminal_from_accel(
        vehicle_state=p_st,
        accel_cmd_mps2=a_p_cmd,
        dt=dt,
        vmax_mps=cfg.mainline_vmax_mps,
    )
    m_xf, m_v_target, a_m_actual = _terminal_from_accel(
        vehicle_state=m_st,
        accel_cmd_mps2=a_m_cmd,
        dt=dt,
        vmax_mps=cfg.ramp_vmax_mps,
    )
    s_xf, s_v_target, a_s_actual = _terminal_from_accel(
        vehicle_state=s_st,
        accel_cmd_mps2=a_s_cmd,
        dt=dt,
        vmax_mps=cfg.mainline_vmax_mps,
    )

    vehicles = [
        (tcg.p_id, p_st, p_xf, p_v_target, a_p_actual),
        (tcg.m_id, m_st, m_xf, m_v_target, a_m_actual),
        (tcg.s_id, s_st, s_xf, s_v_target, a_s_actual),
    ]

    profiles: list[QuinticLongitudinalProfile] = []
    for vid, vs, xf, vf, a_desired in vehicles:
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

    metrics_after = _coordination_metrics_from_states(
        scenario=cfg,
        p_x=p_xf,
        p_v=p_v_target,
        m_x=m_xf,
        m_v=m_v_target,
        s_x=s_xf,
        s_v=s_v_target,
        x_m_expected=x_m_expected,
        v_ref=v_ref,
        xi_override=float(metrics_before["xi"]),
    )

    delta_open_before = float(metrics_before["e_pm_virt"]) + float(metrics_before["e_ms_virt"])
    delta_open_after = float(metrics_after["e_pm_virt"]) + float(metrics_after["e_ms_virt"])

    dv_before = float(metrics_before["dv_pm"]) + float(metrics_before["dv_ms"])
    dv_after = float(metrics_after["dv_pm"]) + float(metrics_after["dv_ms"])

    improved = (
        (float(metrics_after["e_pm_virt"]) < float(metrics_before["e_pm_virt"]) - EPS_PROGRESS)
        or (float(metrics_after["e_ms_virt"]) < float(metrics_before["e_ms_virt"]) - EPS_PROGRESS)
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
