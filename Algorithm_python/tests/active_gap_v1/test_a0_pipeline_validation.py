"""A0 scenario end-to-end pipeline validation (T1-T3 scope).

Runs the full T1->T2->T3 pipeline on A0 layout (p=11, m=9, s=5, v0=16.7)
and prints diagnostic data for human review.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src"))

from active_gap_v1.types import (
    AnchorMode, CoordinationSnapshot, ExecutionState,
    MergeTarget, PlannerTag, ScenarioConfig, SliceKind,
    TCG, VehicleState,
)
from active_gap_v1.config import default_scenario_config
from active_gap_v1.snapshot import build_coordination_snapshot
from active_gap_v1.tcg_selector import identify_tcg
from active_gap_v1.merge_target_planner import enumerate_merge_targets
from active_gap_v1.quintic import solve_tcg_quintics, eval_poly, _velocity_coeffs, _accel_coeffs, check_dynamics
from active_gap_v1.certificate import build_safety_certificate


def run_a0_pipeline():
    cfg = default_scenario_config()
    v0 = 16.7

    world_state = {
        "p": VehicleState("p", "mainline", "main_0", 11.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "m": VehicleState("m", "ramp", "ramp_0", 9.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "s": VehicleState("s", "mainline", "main_0", 5.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
    }

    print("=" * 70)
    print("A0 场景端到端管线验证 (T1->T2->T3)")
    print("=" * 70)
    print(f"\n【布局】p=11m, m=9m, s=5m, v0={v0} m/s, 同速起步")
    print(f"  初始 p-s 间距: {11.0 - 5.0:.1f} m")
    print(f"  初始 p-m 间距: {11.0 - 9.0:.1f} m")
    print(f"  初始 m-s 间距: {9.0 - 5.0:.1f} m")

    # T1: Snapshot + TCG
    print("\n--- T1: Snapshot & TCG 识别 ---")
    for mode in [AnchorMode.FIXED, AnchorMode.FLEXIBLE]:
        snap = build_coordination_snapshot(
            sim_time_s=0.0, scenario=cfg, world_state=world_state,
            locked_tcgs={}, planner_tag=PlannerTag.ACTIVE_GAP, anchor_mode=mode,
        )
        tcg = identify_tcg(snapshot=snap)
        if tcg is None:
            print(f"  [{mode}] TCG 识别失败!")
            continue
        print(f"  [{mode}] TCG = (p={tcg.p_id}, m={tcg.m_id}, s={tcg.s_id}), u={tcg.u_id}, f={tcg.f_id}")

        # T2: Merge Target Search
        targets = enumerate_merge_targets(snapshot=snap, tcg=tcg)
        print(f"\n--- T2: Merge Target 搜索 [{mode}] ---")
        print(f"  可行候选数: {len(targets)}")

        if not targets:
            print("  无可行 merge target!")
            continue

        best = targets[0]
        print(f"\n  最优 target:")
        print(f"    x_m* = {best.x_m_star_m:.1f} m (completion anchor)")
        print(f"    t_m* = {best.t_m_star_s:.1f} s (merge 完成时间)")
        print(f"    H    = {best.horizon_s:.1f} s (规划时域)")
        print(f"    v*   = {best.v_star_mps:.1f} m/s (目标速度)")
        print(f"    x_p* = {best.x_p_star_m:.1f} m (p 终端位置)")
        print(f"    x_s* = {best.x_s_star_m:.1f} m (s 终端位置)")
        print(f"    Δ_open = {best.delta_open_m:.2f} m {'← 主动造 gap!' if best.delta_open_m > 0 else ''}")
        print(f"    Δ_coop = {best.delta_coop_m:.2f} m (协同位移偏差)")
        print(f"    Δ_delay = {best.delta_delay_s:.2f} s (匝道车延迟)")
        print(f"    ρ_min  = {best.rho_min_m:.2f} m (终端安全裕度)")

        # T3: Quintic + Certificate
        print(f"\n--- T3: 三车 Quintic & 安全证书 [{mode}] ---")
        profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=best)
        pp, pm, ps = profiles

        for label, prof in [("p", pp), ("m", pm), ("s", ps)]:
            c = prof.coefficients
            H = prof.horizon_s
            vc = _velocity_coeffs(c)
            ac = _accel_coeffs(c)
            x_end = eval_poly(c, H)
            v_end = eval_poly(vc, H)
            a_end = eval_poly(ac, H)

            v_max = max(eval_poly(vc, t) for t in [i * H / 100 for i in range(101)])
            v_min = min(eval_poly(vc, t) for t in [i * H / 100 for i in range(101)])
            a_max = max(eval_poly(ac, t) for t in [i * H / 100 for i in range(101)])
            a_min = min(eval_poly(ac, t) for t in [i * H / 100 for i in range(101)])

            dyn_ok = check_dynamics(c, H, cfg.mainline_vmax_mps if label != "m" else cfg.ramp_vmax_mps,
                                     cfg.a_max_mps2, cfg.b_safe_mps2) is None
            print(f"  {label}: x(0)={c[0]:.1f} → x(H)={x_end:.1f} m, v∈[{v_min:.2f},{v_max:.2f}] m/s, a∈[{a_min:.2f},{a_max:.2f}] m/s², 动力学{'✓' if dyn_ok else '✗'}")

        cert = build_safety_certificate(
            snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
            profiles=profiles, target=best,
        )
        print(f"\n  安全证书:")
        print(f"    g_pm min margin = {cert.min_margin_pm_m:.3f} m {'✓' if cert.min_margin_pm_m >= -0.001 else '✗ 违规!'}")
        print(f"    g_ms min margin = {cert.min_margin_ms_m:.3f} m {'✓' if cert.min_margin_ms_m >= -0.001 else '✗ 违规!'}")
        print(f"    g_up min margin = {cert.min_margin_up_m if cert.min_margin_up_m is not None else 'N/A (u 不存在)'}")
        print(f"    g_sf min margin = {cert.min_margin_sf_m if cert.min_margin_sf_m is not None else 'N/A (f 不存在)'}")
        print(f"    最紧约束: {cert.binding_constraint}")
        print(f"    证书结果: {'PASS ✓' if cert.failure_kind is None else f'FAIL ✗ ({cert.failure_kind})'}")

    print("\n" + "=" * 70)


def test_a0_pipeline_produces_certified_result():
    """A0 flexible mode must find at least one fully certified merge target."""
    cfg = default_scenario_config()
    v0 = 16.7
    world_state = {
        "p": VehicleState("p", "mainline", "main_0", 11.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "m": VehicleState("m", "ramp", "ramp_0", 9.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "s": VehicleState("s", "mainline", "main_0", 5.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
    }

    snap = build_coordination_snapshot(
        sim_time_s=0.0, scenario=cfg, world_state=world_state,
        locked_tcgs={}, planner_tag=PlannerTag.ACTIVE_GAP, anchor_mode=AnchorMode.FLEXIBLE,
    )
    tcg = identify_tcg(snapshot=snap)
    assert tcg is not None, "A0 should identify a valid TCG"

    targets = enumerate_merge_targets(snapshot=snap, tcg=tcg)
    assert len(targets) > 0, "A0 should have feasible merge targets"
    assert targets[0].delta_open_m > 0, "A0 should require active gap creation"

    certified = None
    for t in targets:
        profiles = solve_tcg_quintics(snapshot=snap, tcg=tcg, target=t)
        cert = build_safety_certificate(
            snapshot=snap, tcg=tcg, slice_kind=SliceKind.MERGE,
            profiles=profiles, target=t,
        )
        if cert.failure_kind is None:
            certified = (t, cert)
            break

    assert certified is not None, (
        f"A0 flexible should have at least one fully certified target "
        f"(checked {len(targets)} candidates)"
    )
    t, cert = certified
    assert t.delta_open_m > 0, "Certified target should still show active gap creation"


if __name__ == "__main__":
    run_a0_pipeline()
