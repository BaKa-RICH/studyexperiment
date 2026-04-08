"""Tests for T3: quintic solver and safety certificate."""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src"))

from active_gap_v1.types import (
    AnchorMode,
    CertificateFailureKind,
    CoordinationSnapshot,
    ExecutionState,
    MergeTarget,
    PlannerTag,
    QuinticBoundaryState,
    ScenarioConfig,
    SliceKind,
    TCG,
    VehicleState,
)
from active_gap_v1.config import default_scenario_config
from active_gap_v1.quintic import solve_tcg_quintics, eval_poly, check_dynamics, _velocity_coeffs, _accel_coeffs
from active_gap_v1.certificate import build_safety_certificate


def _a0_scenario() -> tuple[CoordinationSnapshot, TCG, MergeTarget]:
    cfg = default_scenario_config()
    v0 = 16.7

    def _vs(vid: str, stream: str, x: float) -> VehicleState:
        return VehicleState(
            veh_id=vid, stream=stream, lane_id="main" if stream == "mainline" else "ramp",
            x_pos_m=x, speed_mps=v0, accel_mps2=0.0,
            length_m=5.0, is_cav=True, execution_state=ExecutionState.PLANNING,
        )

    states = {
        "p": _vs("p", "mainline", 11.0),
        "m": _vs("m", "ramp", 9.0),
        "s": _vs("s", "mainline", 5.0),
    }

    snap = CoordinationSnapshot(
        snapshot_id="snap_0.000",
        sim_time_s=0.0,
        planner_tag=PlannerTag.ACTIVE_GAP,
        anchor_mode=AnchorMode.FIXED,
        ego_id="m",
        ego_state=states["m"],
        control_zone_states=states,
        locked_tcgs={},
        scenario=cfg,
    )

    tcg = TCG(
        snapshot_id="snap_0.000",
        p_id="p", m_id="m", s_id="s",
        u_id=None, f_id=None,
        anchor_mode=AnchorMode.FIXED,
        sequence_relation="p > m > s",
    )

    H = 5.0
    v_star = 14.0
    x_m_star = 170.0
    d_pm = 5.0 + 2.5 + 1.5 * v_star
    d_ms = 5.0 + 2.5 + 2.0 * v_star
    x_p_star = x_m_star + d_pm
    x_s_star = x_m_star - d_ms

    target = MergeTarget(
        snapshot_id="snap_0.000", m_id="m",
        x_m_star_m=x_m_star, t_m_star_s=H, horizon_s=H,
        v_star_mps=v_star,
        x_p_star_m=x_p_star, x_s_star_m=x_s_star,
        delta_open_m=10.0, delta_coop_m=5.0, delta_delay_s=1.0, rho_min_m=0.0,
        ranking_key=(H, 5.0, 1.0, 0.0, x_m_star),
    )

    return snap, tcg, target


def test_solve_produces_three_profiles():
    snap, tcg, target = _a0_scenario()
    pp, pm, ps = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)
    assert pp.vehicle_id == "p"
    assert pm.vehicle_id == "m"
    assert ps.vehicle_id == "s"
    assert len(pp.coefficients) == 6
    assert len(pm.coefficients) == 6
    assert len(ps.coefficients) == 6


def test_start_boundary_conditions():
    snap, tcg, target = _a0_scenario()
    pp, pm, ps = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)

    for prof, vid in [(pp, "p"), (pm, "m"), (ps, "s")]:
        c = prof.coefficients
        st = snap.control_zone_states[vid]
        assert abs(c[0] - st.x_pos_m) < 1e-9
        assert abs(c[1] - st.speed_mps) < 1e-9
        assert abs(c[2] - st.accel_mps2 / 2.0) < 1e-9


def test_terminal_boundary_conditions():
    snap, tcg, target = _a0_scenario()
    pp, pm, ps = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)
    H = target.horizon_s

    for prof, x_star in [(pp, target.x_p_star_m), (pm, target.x_m_star_m), (ps, target.x_s_star_m)]:
        c = prof.coefficients
        x_H = eval_poly(c, H)
        vc = _velocity_coeffs(c)
        v_H = eval_poly(vc, H)
        ac = _accel_coeffs(c)
        a_H = eval_poly(ac, H)

        assert abs(x_H - x_star) < 1e-6, f"x(H)={x_H} != {x_star}"
        assert abs(v_H - target.v_star_mps) < 1e-6, f"v(H)={v_H} != {target.v_star_mps}"
        assert abs(a_H) < 1e-6, f"a(H)={a_H} != 0"


def test_dynamics_check_detects_violation():
    c = (0.0, 0.0, 0.0, 100.0, 0.0, 0.0)
    result = check_dynamics(c, H=1.0, v_max=25.0, a_max=2.6, b_max=4.5)
    assert result == CertificateFailureKind.DYNAMICS


def test_certificate_passes_for_reasonable_target():
    snap, tcg, target = _a0_scenario()
    profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)
    cert = build_safety_certificate(
        snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
        profiles=profiles, target=target,
    )
    assert cert.snapshot_id == "snap_0.000"
    assert cert.binding_constraint in ("g_pm", "g_ms", "g_up", "g_sf")
    assert cert.min_margin_pm_m is not None
    assert cert.min_margin_ms_m is not None


def test_certificate_handles_missing_u_f():
    snap, tcg, target = _a0_scenario()
    assert tcg.u_id is None
    assert tcg.f_id is None

    profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)
    cert = build_safety_certificate(
        snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
        profiles=profiles, target=target,
    )
    assert cert.min_margin_up_m is None
    assert cert.min_margin_sf_m is None
    assert cert.failure_kind is None or isinstance(cert.failure_kind, CertificateFailureKind)


def test_certificate_reports_failure():
    snap, tcg, target = _a0_scenario()
    bad_target = MergeTarget(
        snapshot_id="snap_0.000", m_id="m",
        x_m_star_m=170.0, t_m_star_s=0.5, horizon_s=0.5,
        v_star_mps=14.0,
        x_p_star_m=198.5, x_s_star_m=141.5,
        delta_open_m=50.0, delta_coop_m=30.0, delta_delay_s=0.0, rho_min_m=0.0,
        ranking_key=(0.5, 30.0, 0.0, 0.0, 170.0),
    )
    profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=bad_target)
    cert = build_safety_certificate(
        snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
        profiles=profiles, target=bad_target,
    )
    has_issue = (
        cert.failure_kind is not None
        or cert.min_margin_pm_m < 0
        or cert.min_margin_ms_m < 0
    )
    assert has_issue, "Extreme target should produce safety concerns"


def test_deterministic_results():
    snap, tcg, target = _a0_scenario()
    results = []
    for _ in range(3):
        profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=target)
        cert = build_safety_certificate(
            snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
            profiles=profiles, target=target,
        )
        results.append((
            profiles[0].coefficients,
            profiles[1].coefficients,
            profiles[2].coefficients,
            cert.min_margin_pm_m,
            cert.min_margin_ms_m,
            cert.binding_constraint,
        ))
    assert results[0] == results[1] == results[2]
