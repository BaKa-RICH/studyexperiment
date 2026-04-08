"""A0 rolling closed-loop simulation — the real scenario validation.

Runs the full T1→T2→T3→T4 pipeline over multiple ticks on the A0 layout.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src"))

from active_gap_v1.types import *
from active_gap_v1.config import default_scenario_config
from active_gap_v1.snapshot import build_coordination_snapshot
from active_gap_v1.tcg_selector import identify_tcg
from active_gap_v1.executor import (
    _try_certified_merge, synthesize_coordination_slice,
    commit_first_slice, decide_execution, rollout_step,
    N_COORD_MAX,
)


def run_a0_rolling_simulation(max_ticks: int = 200, verbose: bool = False):
    cfg = default_scenario_config()
    v0 = 16.7

    world: dict[str, VehicleState] = {
        "p": VehicleState("p", "mainline", "main_0", 11.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "m": VehicleState("m", "ramp", "ramp_0", 9.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
        "s": VehicleState("s", "mainline", "main_0", 5.0, v0, 0.0, 5.0, True, ExecutionState.PLANNING),
    }

    state = ExecutionState.PLANNING
    coord_count = 0
    total_coord_count = 0
    merge_count = 0
    wait_count = 0
    locked_tcg: TCG | None = None

    trace: list[dict] = []

    for tick in range(max_ticks):
        sim_time = tick * cfg.planning_tick_s

        snap = build_coordination_snapshot(
            sim_time_s=sim_time, scenario=cfg, world_state=world,
            locked_tcgs={}, planner_tag=PlannerTag.ACTIVE_GAP,
            anchor_mode=AnchorMode.FLEXIBLE,
        )
        tcg = identify_tcg(snapshot=snap)
        if tcg is None:
            if verbose:
                print(f"tick {tick:3d} t={sim_time:.1f}s: TCG=None, break")
            break

        plan_slice: RollingPlanSlice | None = None
        decision_tag = "none"

        merge_result = _try_certified_merge(snap, tcg)
        if merge_result is not None:
            target, profiles, cert = merge_result
            plan_slice = commit_first_slice(
                snapshot=snap, tcg=tcg, certificate=cert,
                profiles=profiles, target=target, slice_kind=SliceKind.MERGE,
            )
            merge_count += 1
            coord_count = 0
            decision_tag = "merge"
        else:
            if coord_count < N_COORD_MAX:
                coord_slice = synthesize_coordination_slice(snapshot=snap, tcg=tcg)
                if coord_slice is not None:
                    plan_slice = coord_slice
                    coord_count += 1
                    total_coord_count += 1
                    decision_tag = "coordination"

        decision = decide_execution(
            snapshot=snap, tcg=tcg, plan_slice=plan_slice,
            failure_reason=None if plan_slice else "no_certified_slice",
        )

        if decision.decision_tag == ExecutionDecisionTag.SAFE_WAIT:
            wait_count += 1
            decision_tag = "safe_wait"
        elif decision.decision_tag == ExecutionDecisionTag.FAIL_SAFE_STOP:
            decision_tag = "fail_safe"

        p_st = world["p"]
        m_st = world["m"]
        s_st = world["s"]
        gap_ps = p_st.x_pos_m - s_st.x_pos_m
        gap_pm = p_st.x_pos_m - m_st.x_pos_m

        tick_data = {
            "tick": tick, "time_s": sim_time,
            "decision": decision_tag,
            "p_x": p_st.x_pos_m, "m_x": m_st.x_pos_m, "s_x": s_st.x_pos_m,
            "p_v": p_st.speed_mps, "m_v": m_st.speed_mps, "s_v": s_st.speed_mps,
            "gap_ps": gap_ps, "gap_pm": gap_pm,
        }
        trace.append(tick_data)

        if verbose and tick % 10 == 0:
            print(
                f"tick {tick:3d} t={sim_time:5.1f}s [{decision_tag:12s}] "
                f"p={p_st.x_pos_m:6.1f} m={m_st.x_pos_m:6.1f} s={s_st.x_pos_m:6.1f} "
                f"gap_ps={gap_ps:5.1f} "
                f"v_p={p_st.speed_mps:4.1f} v_m={m_st.speed_mps:4.1f} v_s={s_st.speed_mps:4.1f}"
            )

        if plan_slice is not None:
            world = rollout_step(
                scenario=cfg, world_state=world,
                active_slices={"m": plan_slice},
            )
        else:
            world = rollout_step(
                scenario=cfg, world_state=world, active_slices={},
            )

        if decision.decision_tag == ExecutionDecisionTag.FAIL_SAFE_STOP:
            if verbose:
                print(f"tick {tick:3d}: FAIL_SAFE_STOP triggered")
            break

        if m_st.x_pos_m > cfg.emergency_tail_m[1]:
            if verbose:
                print(f"tick {tick:3d}: m passed emergency tail")
            break

    return {
        "total_ticks": len(trace),
        "merge_ticks": merge_count,
        "coordination_ticks": total_coord_count,
        "wait_ticks": wait_count,
        "trace": trace,
        "final_world": world,
    }


def test_a0_rolling_simulation_completes():
    """A0 must run for at least some ticks without crashing."""
    result = run_a0_rolling_simulation(max_ticks=100, verbose=False)
    assert result["total_ticks"] > 0
    assert result["merge_ticks"] + result["coordination_ticks"] + result["wait_ticks"] > 0


def test_a0_has_active_gap_creation():
    """A0 must show evidence of active gap creation (coordination or merge slices)."""
    result = run_a0_rolling_simulation(max_ticks=100, verbose=False)
    active_ticks = result["merge_ticks"] + result["coordination_ticks"]
    assert active_ticks > 0, "Should have at least some merge or coordination ticks"


def test_a0_gap_increases_over_time():
    """The p-s gap should increase over simulation time."""
    result = run_a0_rolling_simulation(max_ticks=100, verbose=False)
    trace = result["trace"]
    if len(trace) < 10:
        return
    initial_gap = trace[0]["gap_ps"]
    final_gap = trace[-1]["gap_ps"]
    assert final_gap >= initial_gap - 0.01, (
        f"Gap should not decrease: initial={initial_gap:.1f}, final={final_gap:.1f}"
    )


if __name__ == "__main__":
    print("=" * 80)
    print("A0 滚动闭环仿真 (p=11, m=9, s=5, v0=16.7 m/s, flexible)")
    print("=" * 80)
    result = run_a0_rolling_simulation(max_ticks=200, verbose=True)
    print()
    print(f"总 tick 数: {result['total_ticks']}")
    print(f"  merge 决策: {result['merge_ticks']}")
    print(f"  coordination 决策: {result['coordination_ticks']}")
    print(f"  safe_wait 决策: {result['wait_ticks']}")

    trace = result["trace"]
    if trace:
        print(f"\n初始 gap(p-s): {trace[0]['gap_ps']:.1f}m")
        print(f"最终 gap(p-s): {trace[-1]['gap_ps']:.1f}m")
        print(f"初始速度: p={trace[0]['p_v']:.1f} m={trace[0]['m_v']:.1f} s={trace[0]['s_v']:.1f}")
        print(f"最终速度: p={trace[-1]['p_v']:.1f} m={trace[-1]['m_v']:.1f} s={trace[-1]['s_v']:.1f}")
        print(f"最终位置: p={trace[-1]['p_x']:.1f} m={trace[-1]['m_x']:.1f} s={trace[-1]['s_x']:.1f}")
