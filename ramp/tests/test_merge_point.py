"""Tests for the flexible merge-point algorithm (merge_point.py).

Covers: gap evaluation (Eq.1-6), forward scan, fallback, speed mismatches,
multi-gap selection, and the full APPROACHING→SEARCHING→MERGING→MERGED
state machine including timeout/retry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.policies.hierarchical.merge_point import (
    MergeEvalResult,
    MergePointManager,
    MergePointParams,
    MergeState,
    VehicleState,
    evaluate_merge_point,
)

PARAMS = MergePointParams()


# ===================================================================
# evaluate_merge_point – core gap evaluation
# ===================================================================

class TestEvaluateMergePoint:

    def test_empty_lane1_always_feasible(self):
        """No vehicles on L1 → always feasible, no gap details."""
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=20.0, lane1_vehicles=[], params=PARAMS,
        )
        assert result.feasible is True
        assert result.merge_position_m == pytest.approx(100.0 + 20.0 * 3.0)
        assert result.lead_id is None
        assert result.follow_id is None
        assert result.is_fallback is False

    def test_large_gap_feasible(self):
        """Wide gap on L1 → feasible with correct metrics.

        Setup (same speed, v=20 m/s, phi_s=1.5, s0=5):
          follow v_f at 30 m, lead v_l at 200 m, CAV at 100 m
          G_f(t_lc) = (200 - 100 - 5) + 0 = 95  >= phi*v_l + s0 = 35 ✓
          G_r(t_lc) = (100 -  30 - 5) + 0 = 65  >= phi*v_c + s0 = 35 ✓
          safety_margin = min(95-35, 65-35) = 30
        """
        lane1 = [('v_lead', 200.0, 20.0), ('v_follow', 30.0, 20.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=20.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.merge_position_m == pytest.approx(160.0)
        assert result.gap_front_m == pytest.approx(95.0)
        assert result.gap_rear_m == pytest.approx(65.0)
        assert result.lead_id == 'v_lead'
        assert result.follow_id == 'v_follow'
        assert result.safety_margin == pytest.approx(30.0)
        assert result.is_fallback is False

    def test_small_gap_infeasible(self):
        """Gap smaller than D_f_min → infeasible (P2-2 numerical validation).

        At v=25 m/s, phi_s=1.5:
          G_f(t_lc) = (190-150-5) + 0 = 35  < phi*25+5 = 42.5  → S1 FAIL
        """
        lane1 = [('v_l', 190.0, 25.0), ('v_f', 70.0, 25.0)]
        result = evaluate_merge_point(
            cav_pos_m=150.0, cav_speed_mps=25.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is False
        assert result.merge_position_m is None

    def test_no_front_vehicle(self):
        """Tail gap (no lead vehicle) → S1 auto-satisfied.

        Only a follow vehicle behind CAV (phi_s=1.5, s0=5).
          G_r(t_lc) = (100-30-5) + 0 = 65  >= phi*v_c+s0 = 35  ✓
          margin_r = 65 - 35 = 30
        """
        lane1 = [('v_behind', 30.0, 20.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=20.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.lead_id is None
        assert result.follow_id == 'v_behind'
        assert result.gap_front_m is None
        assert result.gap_rear_m == pytest.approx(65.0)
        assert result.safety_margin == pytest.approx(30.0)

    def test_no_rear_vehicle(self):
        """Head gap (no follow vehicle) → S2 auto-satisfied.

        Only a lead vehicle ahead of CAV (phi_s=1.5, s0=5).
          G_f(t_lc) = (200-100-5) + 0 = 95  >= phi*v_l+s0 = 35  ✓
          margin_f = 95 - 35 = 60
        """
        lane1 = [('v_ahead', 200.0, 20.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=20.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.lead_id == 'v_ahead'
        assert result.follow_id is None
        assert result.gap_front_m == pytest.approx(95.0)
        assert result.gap_rear_m is None
        assert result.safety_margin == pytest.approx(60.0)

    def test_fallback_trigger(self):
        """CAV at/past fallback position → forced feasible with is_fallback."""
        fallback_pos = PARAMS.lane0_length_m - PARAMS.fallback_buffer_m  # 259.41
        result = evaluate_merge_point(
            cav_pos_m=260.0, cav_speed_mps=15.0,
            lane1_vehicles=[('v1', 250.0, 15.0)],
            params=PARAMS,
        )
        assert result.feasible is True
        assert result.is_fallback is True
        assert result.merge_position_m == pytest.approx(260.0 + 15.0 * 3.0)

    def test_speed_mismatch_front(self):
        """CAV faster than lead → closing gap makes S1 fail.

        v_c=30, v_l=15, phi_s=1.5.
          G_f(t_lc) = (165-100-5) + (15-30)*3 = 60-45 = 15
          threshold_f = 1.5*15+5 = 27.5.  15 < 27.5 → FAIL
        """
        lane1 = [('slow_lead', 165.0, 15.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=30.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is False

    def test_speed_mismatch_rear(self):
        """Follow faster than CAV → rear gap closes, S2 fails.

        v_c=15, v_f=30, phi_s=1.5.
          G_r(t_lc) = (100-40-5) + (15-30)*3 = 55-45 = 10
          threshold_r = 1.5*15+5 = 27.5.  10 < 27.5 → FAIL
        """
        lane1 = [('fast_follow', 40.0, 30.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=15.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is False

    def test_multiple_gaps_pick_earliest(self):
        """Multiple vehicles on L1: algorithm picks the first feasible gap.

        Vehicles (sorted): v_a(30), v_b(85), v_c(280).
        CAV at 150 (phi_s=1.5, s0=5).
        insert_idx = 2 → current gap: follow=v_b, lead=v_c.
          G_f = (280-150-5)+0 = 125 >= 35 ✓
          G_r = (150-85-5)+0  =  60 >= 35 ✓  → FEASIBLE (earliest)
          margin = min(125-35, 60-35) = 25
        """
        lane1 = [('v_a', 30.0, 20.0), ('v_b', 85.0, 20.0), ('v_c', 280.0, 20.0)]
        result = evaluate_merge_point(
            cav_pos_m=150.0, cav_speed_mps=20.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.lead_id == 'v_c'
        assert result.follow_id == 'v_b'
        assert result.gap_front_m == pytest.approx(125.0)
        assert result.gap_rear_m == pytest.approx(60.0)
        assert result.safety_margin == pytest.approx(25.0)

    def test_fallback_exact_boundary(self):
        """CAV exactly at fallback position → triggers fallback."""
        fallback_pos = PARAMS.lane0_length_m - PARAMS.fallback_buffer_m
        result = evaluate_merge_point(
            cav_pos_m=fallback_pos, cav_speed_mps=10.0,
            lane1_vehicles=[], params=PARAMS,
        )
        assert result.feasible is True
        assert result.is_fallback is True

    def test_all_vehicles_ahead_tight(self):
        """All L1 vehicles ahead of CAV, head gap is the only forward option.

        v1 at 160, v2 at 250.  CAV at 100, insert_idx=0 (phi_s=1.5, s0=5).
        Head gap: follow=None, lead=v1(160).
          G_f = (160-100-5)+0 = 55  >= 35 ✓  (margin=20)
          G_r = inf                          ✓
        """
        lane1 = [('v1', 160.0, 20.0), ('v2', 250.0, 20.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=20.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.lead_id == 'v1'
        assert result.follow_id is None
        assert result.safety_margin == pytest.approx(20.0)

    def test_zero_speed_cav(self):
        """Stationary CAV (v_c=0): merge_position equals current position.

        With follow at 30 m, G_r = (100-30-5)+0 = 65 >= s0=5 ✓
        threshold_r = phi*0 + s0 = 5.  margin = 60.
        """
        lane1 = [('v_f', 30.0, 0.0)]
        result = evaluate_merge_point(
            cav_pos_m=100.0, cav_speed_mps=0.0, lane1_vehicles=lane1, params=PARAMS,
        )
        assert result.feasible is True
        assert result.merge_position_m == pytest.approx(100.0)
        assert result.safety_margin == pytest.approx(60.0)


# ===================================================================
# MergePointManager – state machine
# ===================================================================

class TestMergePointManager:

    def test_state_machine_transitions(self):
        """Full lifecycle: APPROACHING → SEARCHING → MERGING → MERGED,
        including timeout/retry path."""
        params = MergePointParams()
        mgr = MergePointManager(params)

        # T=0: pos=20 < search_start=30 → stays APPROACHING
        cavs = {'c0': VehicleState('main_h3', 0, 20.0, 15.0)}
        actions = mgr.update(0.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.APPROACHING
        assert not actions

        # T=1: pos=35 >= 30 → APPROACHING→SEARCHING→(empty L1)→MERGING
        cavs = {'c0': VehicleState('main_h3', 0, 35.0, 15.0)}
        actions = mgr.update(1.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING
        assert actions == {'c0': (1, params.t_lc_s)}

        # T=2: still on L0, no timeout yet → stays MERGING, no new action
        cavs = {'c0': VehicleState('main_h3', 0, 50.0, 15.0)}
        actions = mgr.update(2.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING
        assert not actions

        # T=4: at t_lc boundary (1.0+3.0=4.0), still within timeout buffer
        cavs = {'c0': VehicleState('main_h3', 0, 65.0, 15.0)}
        actions = mgr.update(4.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING

        # T=5.1: timeout (>1.0+3.0+1.0=5.0), tight L1 → SEARCHING (retry)
        lane1_tight = [('blocker', 72.0, 15.0)]
        cavs = {'c0': VehicleState('main_h3', 0, 70.0, 15.0)}
        actions = mgr.update(5.1, cavs, lane1_tight)
        assert mgr.vehicle_states['c0'] == MergeState.SEARCHING
        assert mgr.get_tracker('c0').failure_count == 1

        # T=6: SEARCHING with infeasible L1 → stays SEARCHING
        cavs = {'c0': VehicleState('main_h3', 0, 85.0, 15.0)}
        actions = mgr.update(6.0, cavs, lane1_tight)
        assert mgr.vehicle_states['c0'] == MergeState.SEARCHING

        # T=7: SEARCHING with empty L1 → MERGING again
        cavs = {'c0': VehicleState('main_h3', 0, 100.0, 15.0)}
        actions = mgr.update(7.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING
        assert 'c0' in actions

        # T=8: lane change complete (lane_index=1) → MERGED
        cavs = {'c0': VehicleState('main_h3', 1, 120.0, 15.0)}
        actions = mgr.update(8.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGED
        assert not actions
        assert len(mgr.merge_history) == 1
        assert mgr.merge_history[0]['veh_id'] == 'c0'

    def test_vehicle_not_on_merge_lane(self):
        """Vehicle not on main_h3 L0 is not tracked."""
        mgr = MergePointManager()
        cavs = {'c1': VehicleState('main_h2', 0, 100.0, 20.0)}
        actions = mgr.update(0.0, cavs, [])
        assert 'c1' not in mgr.vehicle_states
        assert not actions

    def test_max_retries_exceeded(self):
        """After max_retries timeouts, forced lane-change action is issued."""
        params = MergePointParams(max_retries=1)
        mgr = MergePointManager(params)

        lane1_tight = [('blocker', 38.0, 15.0)]

        # Enter SEARCHING → MERGING (empty L1 for first enter)
        cavs = {'c0': VehicleState('main_h3', 0, 35.0, 15.0)}
        mgr.update(0.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING

        # Retry 1: timeout → SEARCHING (failure_count=1 <= max_retries=1)
        cavs = {'c0': VehicleState('main_h3', 0, 50.0, 15.0)}
        mgr.update(4.1, cavs, lane1_tight)
        assert mgr.vehicle_states['c0'] == MergeState.SEARCHING

        # Enter MERGING again (empty L1)
        cavs = {'c0': VehicleState('main_h3', 0, 60.0, 15.0)}
        mgr.update(5.0, cavs, [])
        assert mgr.vehicle_states['c0'] == MergeState.MERGING

        # Retry 2: timeout → failure_count=2 > max_retries=1 → forced action
        cavs = {'c0': VehicleState('main_h3', 0, 80.0, 15.0)}
        actions = mgr.update(9.1, cavs, lane1_tight)
        assert mgr.vehicle_states['c0'] == MergeState.MERGING
        assert actions == {'c0': (1, params.t_lc_s)}

    def test_fallback_via_state_machine(self):
        """CAV reaches fallback position during SEARCHING → MERGING."""
        params = MergePointParams()
        mgr = MergePointManager(params)
        fallback_pos = params.lane0_length_m - params.fallback_buffer_m

        lane1_tight = [('v1', fallback_pos + 2.0, 15.0)]

        cavs = {'c0': VehicleState('main_h3', 0, fallback_pos, 15.0)}
        actions = mgr.update(0.0, cavs, lane1_tight)

        assert mgr.vehicle_states['c0'] == MergeState.MERGING
        assert 'c0' in actions
        tracker = mgr.get_tracker('c0')
        assert tracker.last_eval is not None
        assert tracker.last_eval.is_fallback is True
