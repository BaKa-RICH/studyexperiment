"""Three-vehicle quintic longitudinal trajectory solver for active_gap_v1."""

from __future__ import annotations

import math

from .types import (
    CertificateFailureKind,
    CoordinationSnapshot,
    MergeTarget,
    QuinticBoundaryState,
    QuinticLongitudinalProfile,
    TCG,
)


def _solve_one_quintic(
    x0: float, v0: float, a0: float,
    xf: float, vf: float, af: float,
    H: float,
) -> tuple[float, float, float, float, float, float]:
    c0 = x0
    c1 = v0
    c2 = 0.5 * a0

    dx = xf - (x0 + v0 * H + 0.5 * a0 * H * H)
    dv = vf - (v0 + a0 * H)
    da = af - a0

    H2 = H * H
    H3 = H2 * H
    H4 = H3 * H
    H5 = H4 * H

    c3 = (10.0 * dx - 4.0 * H * dv + 0.5 * H2 * da) / H3
    c4 = (-15.0 * dx + 7.0 * H * dv - H2 * da) / H4
    c5 = (6.0 * dx - 3.0 * H * dv + 0.5 * H2 * da) / H5

    return (c0, c1, c2, c3, c4, c5)


def eval_poly(coeffs: tuple[float, ...], tau: float) -> float:
    result = 0.0
    for i in range(len(coeffs) - 1, -1, -1):
        result = result * tau + coeffs[i]
    return result


def _poly_derivative(coeffs: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(coeffs[i] * i for i in range(1, len(coeffs)))


def _quadratic_real_roots(a: float, b: float, c: float) -> list[float]:
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return []
        return [-c / b]
    disc = b * b - 4.0 * a * c
    if disc < -1e-12:
        return []
    disc = max(disc, 0.0)
    sq = math.sqrt(disc)
    return [(-b + sq) / (2.0 * a), (-b - sq) / (2.0 * a)]


def _cubic_real_roots(a: float, b: float, c: float, d: float) -> list[float]:
    if abs(a) < 1e-12:
        return _quadratic_real_roots(b, c, d)

    b, c, d = b / a, c / a, d / a
    p = c - b * b / 3.0
    q = 2.0 * b * b * b / 27.0 - b * c / 3.0 + d
    disc = q * q / 4.0 + p * p * p / 27.0

    shift = -b / 3.0
    roots: list[float] = []

    if disc > 1e-12:
        sq = math.sqrt(disc)
        u = -q / 2.0 + sq
        v = -q / 2.0 - sq
        cu = math.copysign(abs(u) ** (1.0 / 3.0), u)
        cv = math.copysign(abs(v) ** (1.0 / 3.0), v)
        roots.append(cu + cv + shift)
    elif disc < -1e-12:
        r = math.sqrt(-p * p * p / 27.0)
        theta = math.acos(max(-1.0, min(1.0, -q / (2.0 * r))))
        m = 2.0 * (r ** (1.0 / 3.0))
        for k in range(3):
            roots.append(m * math.cos((theta + 2.0 * math.pi * k) / 3.0) + shift)
    else:
        if abs(q) < 1e-12:
            roots.append(shift)
        else:
            cu = math.copysign(abs(q / 2.0) ** (1.0 / 3.0), -q)
            roots.append(2.0 * cu + shift)
            roots.append(-cu + shift)

    return roots


def _roots_in_interval(coeffs: tuple[float, ...], lo: float, hi: float) -> list[float]:
    n = len(coeffs)
    if n == 0:
        return []
    if n == 1:
        return []
    if n == 2:
        a, b = coeffs[0], coeffs[1]
        if abs(b) < 1e-15:
            return []
        r = -a / b
        return [r] if lo <= r <= hi else []
    if n == 3:
        raw = _quadratic_real_roots(coeffs[2], coeffs[1], coeffs[0])
    elif n == 4:
        raw = _cubic_real_roots(coeffs[3], coeffs[2], coeffs[1], coeffs[0])
    else:
        raw = _numeric_roots_fallback(coeffs, lo, hi)
    return [r for r in raw if lo - 1e-9 <= r <= hi + 1e-9]


def _numeric_roots_fallback(
    coeffs: tuple[float, ...], lo: float, hi: float, n_samples: int = 200,
) -> list[float]:
    roots: list[float] = []
    dt = (hi - lo) / n_samples
    prev = eval_poly(coeffs, lo)
    for i in range(1, n_samples + 1):
        t = lo + i * dt
        cur = eval_poly(coeffs, t)
        if prev * cur <= 0 and (abs(prev) > 1e-15 or abs(cur) > 1e-15):
            tl, tr = t - dt, t
            for _ in range(50):
                tm = (tl + tr) / 2.0
                vm = eval_poly(coeffs, tm)
                if abs(vm) < 1e-12:
                    break
                if vm * eval_poly(coeffs, tl) <= 0:
                    tr = tm
                else:
                    tl = tm
            roots.append((tl + tr) / 2.0)
        prev = cur
    return roots


def _velocity_coeffs(c: tuple[float, ...]) -> tuple[float, ...]:
    return (c[1], 2.0 * c[2], 3.0 * c[3], 4.0 * c[4], 5.0 * c[5])


def _accel_coeffs(c: tuple[float, ...]) -> tuple[float, ...]:
    return (2.0 * c[2], 6.0 * c[3], 12.0 * c[4], 20.0 * c[5])


def _jerk_coeffs(c: tuple[float, ...]) -> tuple[float, ...]:
    return (6.0 * c[3], 24.0 * c[4], 60.0 * c[5])


def check_dynamics(
    coeffs: tuple[float, float, float, float, float, float],
    H: float,
    v_max: float,
    a_max: float,
    b_max: float,
) -> CertificateFailureKind | None:
    vc = _velocity_coeffs(coeffs)
    ac = _accel_coeffs(coeffs)
    jc = _jerk_coeffs(coeffs)

    v_candidates = [0.0, H]
    v_candidates.extend(_roots_in_interval(ac, 0.0, H))

    for tau in v_candidates:
        v = eval_poly(vc, tau)
        if v < -0.5 or v > v_max + 0.5:
            return CertificateFailureKind.DYNAMICS

    a_candidates = [0.0, H]
    a_candidates.extend(_roots_in_interval(jc, 0.0, H))

    for tau in a_candidates:
        a = eval_poly(ac, tau)
        if a < -b_max - 0.1 or a > a_max + 0.1:
            return CertificateFailureKind.DYNAMICS

    return None


def solve_tcg_quintics(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    target: MergeTarget,
) -> tuple[QuinticLongitudinalProfile, QuinticLongitudinalProfile, QuinticLongitudinalProfile]:
    H = target.horizon_s
    t0 = snapshot.sim_time_s
    states = snapshot.control_zone_states

    p_st = states[tcg.p_id]
    m_st = states[tcg.m_id]
    s_st = states[tcg.s_id]

    vehicles = [
        (tcg.p_id, p_st, target.x_p_star_m),
        (tcg.m_id, m_st, target.x_m_star_m),
        (tcg.s_id, s_st, target.x_s_star_m),
    ]

    profiles: list[QuinticLongitudinalProfile] = []
    for vid, vs, xf in vehicles:
        coeffs = _solve_one_quintic(
            vs.x_pos_m, vs.speed_mps, vs.accel_mps2,
            xf, target.v_star_mps, 0.0,
            H,
        )
        profiles.append(QuinticLongitudinalProfile(
            vehicle_id=vid,
            t0_s=t0,
            horizon_s=H,
            coefficients=coeffs,
            start_state=QuinticBoundaryState(
                x_m=vs.x_pos_m, v_mps=vs.speed_mps, a_mps2=vs.accel_mps2,
            ),
            terminal_state=QuinticBoundaryState(
                x_m=xf, v_mps=target.v_star_mps, a_mps2=0.0,
            ),
        ))

    return (profiles[0], profiles[1], profiles[2])
