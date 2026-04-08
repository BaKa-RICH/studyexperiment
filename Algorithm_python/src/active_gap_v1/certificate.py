"""SafetyCertificate builder for active_gap_v1."""

from __future__ import annotations

from .predictor import predict_optional_free_position
from .quintic import (
    _accel_coeffs,
    _roots_in_interval,
    _velocity_coeffs,
    check_dynamics,
    eval_poly,
)
from .types import (
    CertificateFailureKind,
    CoordinationSnapshot,
    MergeTarget,
    QuinticLongitudinalProfile,
    SafetyCertificate,
    SliceKind,
    TCG,
)

_EPS_G = 0.001


def _gap_function_min(
    leader_pos_coeffs: tuple[float, ...],
    follower_pos_coeffs: tuple[float, ...],
    follower_vel_coeffs: tuple[float, ...],
    L: float,
    s0: float,
    headway: float,
    lo: float,
    hi: float,
) -> tuple[float, tuple[float, ...]]:
    """Compute min of g(τ) = x_lead(τ) - x_follow(τ) - D(v_follow(τ)) over [lo, hi].

    Returns (min_margin, checked_taus).
    """
    n = max(len(leader_pos_coeffs), len(follower_pos_coeffs), len(follower_vel_coeffs))

    def g(tau: float) -> float:
        x_lead = eval_poly(leader_pos_coeffs, tau)
        x_follow = eval_poly(follower_pos_coeffs, tau)
        v_follow = eval_poly(follower_vel_coeffs, tau)
        return x_lead - x_follow - (L + s0 + headway * v_follow)

    candidates = [lo, hi]

    g_coeffs = _build_gap_poly(
        leader_pos_coeffs, follower_pos_coeffs, follower_vel_coeffs,
        L, s0, headway,
    )
    g_deriv = tuple(g_coeffs[i] * i for i in range(1, len(g_coeffs)))
    if len(g_deriv) > 0:
        candidates.extend(_roots_in_interval(g_deriv, lo, hi))

    checked: list[float] = []
    min_val = float("inf")
    for tau in candidates:
        tau = max(lo, min(hi, tau))
        val = g(tau)
        if val < min_val:
            min_val = val
        checked.append(tau)

    return min_val, tuple(sorted(set(checked)))


def _build_gap_poly(
    lead_pos: tuple[float, ...],
    follow_pos: tuple[float, ...],
    follow_vel: tuple[float, ...],
    L: float,
    s0: float,
    headway: float,
) -> tuple[float, ...]:
    max_len = max(len(lead_pos), len(follow_pos), len(follow_vel) + 1)

    def pad(t: tuple[float, ...], n: int) -> list[float]:
        return list(t) + [0.0] * (n - len(t))

    lp = pad(lead_pos, max_len)
    fp = pad(follow_pos, max_len)
    fv = pad(follow_vel, max_len)

    result = [0.0] * max_len
    for i in range(max_len):
        result[i] = lp[i] - fp[i]
    result[0] -= (L + s0)
    for i in range(len(follow_vel)):
        if i < max_len:
            result[i] -= headway * fv[i]

    return tuple(result)


def _boundary_prediction_coeffs(
    vehicle_state_x: float,
    vehicle_state_v: float,
) -> tuple[float, float, float]:
    return (vehicle_state_x, vehicle_state_v, 0.0)


def build_safety_certificate(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    slice_kind: SliceKind,
    profiles: tuple[
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
    ],
    target: MergeTarget | None,
) -> SafetyCertificate:
    cfg = snapshot.scenario
    states = snapshot.control_zone_states

    profile_p, profile_m, profile_s = profiles
    H = profile_p.horizon_s

    L = cfg.vehicle_length_m
    s0 = cfg.min_gap_m
    tau_h = cfg.time_headway_s
    h_pr = cfg.h_pr_s
    h_rf = cfg.h_rf_s
    T_lc = cfg.lane_change_duration_s

    if slice_kind == SliceKind.MERGE:
        tau_lc = max(0.0, H - T_lc)
        pm_lo, pm_hi = tau_lc, H
        ms_lo, ms_hi = tau_lc, H
        up_lo, up_hi = 0.0, H
        sf_lo, sf_hi = 0.0, H
        valid_from = snapshot.sim_time_s
        valid_until = snapshot.sim_time_s + H
    else:
        dt_exec = cfg.planning_tick_s
        pm_lo, pm_hi = 0.0, dt_exec
        ms_lo, ms_hi = 0.0, dt_exec
        up_lo, up_hi = 0.0, dt_exec
        sf_lo, sf_hi = 0.0, dt_exec
        valid_from = snapshot.sim_time_s
        valid_until = snapshot.sim_time_s + dt_exec

    cp = profile_p.coefficients
    cm = profile_m.coefficients
    cs = profile_s.coefficients

    vp = _velocity_coeffs(cp)
    vm = _velocity_coeffs(cm)
    vs = _velocity_coeffs(cs)

    margins: dict[str, float | None] = {}
    all_checked: list[float] = []
    failure: CertificateFailureKind | None = None

    for prof in profiles:
        is_ramp = (prof.vehicle_id == tcg.m_id)
        v_limit = cfg.ramp_vmax_mps if is_ramp else cfg.mainline_vmax_mps
        dyn_fail = check_dynamics(
            prof.coefficients, prof.horizon_s,
            v_limit, cfg.a_max_mps2, cfg.b_safe_mps2,
        )
        if dyn_fail is not None and failure is None:
            failure = dyn_fail

    margin_pm: float | None = None
    margin_ms: float | None = None
    margin_up: float | None = None
    margin_sf: float | None = None

    if slice_kind == SliceKind.MERGE:
        # g_pm: x_p - x_m - D_pm(v_m) — only enforced during lane-change window
        margin_pm, checked_pm = _gap_function_min(cp, cm, vm, L, s0, h_pr, pm_lo, pm_hi)
        margins["pm"] = margin_pm
        all_checked.extend(checked_pm)
        if margin_pm < -_EPS_G and failure is None:
            failure = CertificateFailureKind.SAFETY_PM

        # g_ms: x_m - x_s - D_ms(v_s)
        margin_ms, checked_ms = _gap_function_min(cm, cs, vs, L, s0, h_rf, ms_lo, ms_hi)
        margins["ms"] = margin_ms
        all_checked.extend(checked_ms)
        if margin_ms < -_EPS_G and failure is None:
            failure = CertificateFailureKind.SAFETY_MS

        # g_up: x_u - x_p - D_up(v_p), only if u exists
        if tcg.u_id is not None and tcg.u_id in states:
            u_st = states[tcg.u_id]
            u_pos = _boundary_prediction_coeffs(u_st.x_pos_m, u_st.speed_mps)
            margin_up, checked_up = _gap_function_min(u_pos, cp, vp, L, s0, tau_h, up_lo, up_hi)
            all_checked.extend(checked_up)
            if margin_up < -_EPS_G and failure is None:
                failure = CertificateFailureKind.SAFETY_UP

        # g_sf: x_s - x_f - D_sf(v_f), only if f exists
        if tcg.f_id is not None and tcg.f_id in states:
            f_st = states[tcg.f_id]
            f_pos = _boundary_prediction_coeffs(f_st.x_pos_m, f_st.speed_mps)
            f_vel = (f_st.speed_mps,)
            margin_sf, checked_sf = _gap_function_min(cs, f_pos, f_vel, L, s0, tau_h, sf_lo, sf_hi)
            all_checked.extend(checked_sf)
            if margin_sf < -_EPS_G and failure is None:
                failure = CertificateFailureKind.SAFETY_SF
    # COORDINATION: m is on ramp (different lane from p/s).
    # Cross-lane gap constraints (g_pm, g_ms) do not apply; only dynamics checked above.

    active_margins: dict[str, float] = {}
    if margin_pm is not None:
        active_margins["g_pm"] = margin_pm
    if margin_ms is not None:
        active_margins["g_ms"] = margin_ms
    if margin_up is not None:
        active_margins["g_up"] = margin_up
    if margin_sf is not None:
        active_margins["g_sf"] = margin_sf

    binding = min(active_margins, key=lambda k: active_margins[k]) if active_margins else "dynamics"

    return SafetyCertificate(
        snapshot_id=snapshot.snapshot_id,
        m_id=tcg.m_id,
        tcg_ids=(tcg.u_id, tcg.p_id, tcg.m_id, tcg.s_id, tcg.f_id),
        slice_kind=slice_kind,
        valid_from_s=valid_from,
        valid_until_s=valid_until,
        min_margin_up_m=margin_up,
        min_margin_pm_m=margin_pm,
        min_margin_ms_m=margin_ms,
        min_margin_sf_m=margin_sf,
        binding_constraint=binding,
        failure_kind=failure,
        checked_time_candidates_s=tuple(sorted(set(all_checked))),
    )
