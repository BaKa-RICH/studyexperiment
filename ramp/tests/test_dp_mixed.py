from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.scheduler.dp import ScheduleResult, dp_schedule
from ramp.scheduler.dp_mixed import dp_mixed_schedule


DELTA_1 = 1.5
DELTA_2 = 2.0


def _lane_of(veh_id: str, main_seq: list[str]) -> int:
    return 0 if veh_id in main_seq else 1


def _verify_gap_constraints(
    result: ScheduleResult,
    main_seq: list[str],
    delta_1_s: float,
    delta_2_s: float,
) -> None:
    """Assert every consecutive pair in passing_order satisfies the gap constraint."""
    order = result.passing_order
    for i in range(1, len(order)):
        prev_id = order[i - 1]
        curr_id = order[i]
        prev_lane = _lane_of(prev_id, main_seq)
        curr_lane = _lane_of(curr_id, main_seq)
        gap_required = delta_1_s if prev_lane == curr_lane else delta_2_s
        actual_gap = result.target_cross_time_s[curr_id] - result.target_cross_time_s[prev_id]
        assert actual_gap >= gap_required - 1e-9, (
            f'{prev_id}({result.target_cross_time_s[prev_id]:.4f}) -> '
            f'{curr_id}({result.target_cross_time_s[curr_id]:.4f}): '
            f'gap={actual_gap:.4f} < required={gap_required}'
        )


def _verify_stream_order(result: ScheduleResult, main_seq: list[str], ramp_seq: list[str]) -> None:
    """Assert internal ordering of each stream is preserved."""
    main_in_order = [v for v in result.passing_order if v in main_seq]
    ramp_in_order = [v for v in result.passing_order if v in ramp_seq]
    assert main_in_order == main_seq
    assert ramp_in_order == ramp_seq


# ---------------------------------------------------------------------------
# 1. test_all_cav_matches_dp
# ---------------------------------------------------------------------------
def test_all_cav_matches_dp() -> None:
    """All-CAV dp_mixed must produce identical cost/total_delay as dp_schedule."""
    rng = random.Random(42)
    for m_total in range(5):
        for n_total in range(5):
            main_seq = [f'm{i}' for i in range(m_total)]
            ramp_seq = [f'r{i}' for i in range(n_total)]
            all_vehs = main_seq + ramp_seq

            for _ in range(10):
                t_min_s: dict[str, float] = {}
                for veh in all_vehs:
                    t_min_s[veh] = rng.uniform(0.0, 15.0)

                result_dp = dp_schedule(
                    main_seq=main_seq,
                    ramp_seq=ramp_seq,
                    t_min_s=t_min_s,
                    delta_1_s=DELTA_1,
                    delta_2_s=DELTA_2,
                )

                veh_type_by_id = {v: 'cav' for v in all_vehs}
                result_mixed = dp_mixed_schedule(
                    main_seq=main_seq,
                    ramp_seq=ramp_seq,
                    veh_type_by_id=veh_type_by_id,
                    t_min_cav_s=t_min_s,
                    hdv_predicted_time_s={},
                    delta_1_s=DELTA_1,
                    delta_2_s=DELTA_2,
                )

                assert result_mixed.cost == pytest.approx(result_dp.cost, abs=1e-6)
                assert result_mixed.total_delay_s == pytest.approx(result_dp.total_delay_s, abs=1e-6)
                assert result_mixed.last_cross_time_s == pytest.approx(
                    result_dp.last_cross_time_s, abs=1e-6
                )
                assert result_mixed.passing_order == result_dp.passing_order


# ---------------------------------------------------------------------------
# 2. test_all_hdv
# ---------------------------------------------------------------------------
def test_all_hdv() -> None:
    """All-HDV: every target_cross_time must equal t_pred exactly."""
    main_seq = ['m0', 'm1', 'm2']
    ramp_seq = ['r0', 'r1']
    veh_type_by_id = {v: 'hdv' for v in main_seq + ramp_seq}
    hdv_predicted_time_s = {
        'm0': 1.0, 'm1': 5.0, 'm2': 10.0,
        'r0': 3.0, 'r1': 8.0,
    }

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s={},
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    for veh_id in main_seq + ramp_seq:
        assert result.target_cross_time_s[veh_id] == pytest.approx(
            hdv_predicted_time_s[veh_id], abs=1e-9
        )

    assert result.total_delay_s == pytest.approx(0.0, abs=1e-9)
    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 3. test_single_hdv_main_first
# ---------------------------------------------------------------------------
def test_single_hdv_main_first() -> None:
    """First main vehicle is HDV; its time is fixed."""
    main_seq = ['m0_hdv', 'm1_cav']
    ramp_seq = ['r0_cav']
    veh_type_by_id = {'m0_hdv': 'hdv', 'm1_cav': 'cav', 'r0_cav': 'cav'}
    t_min_cav_s = {'m1_cav': 3.0, 'r0_cav': 2.0}
    hdv_predicted_time_s = {'m0_hdv': 1.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result.target_cross_time_s['m0_hdv'] == pytest.approx(1.0, abs=1e-9)
    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 4. test_single_hdv_ramp_last
# ---------------------------------------------------------------------------
def test_single_hdv_ramp_last() -> None:
    """Last ramp vehicle is HDV; its time is fixed."""
    main_seq = ['m0']
    ramp_seq = ['r0', 'r1_hdv']
    veh_type_by_id = {'m0': 'cav', 'r0': 'cav', 'r1_hdv': 'hdv'}
    t_min_cav_s = {'m0': 1.0, 'r0': 2.0}
    hdv_predicted_time_s = {'r1_hdv': 12.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result.target_cross_time_s['r1_hdv'] == pytest.approx(12.0, abs=1e-9)
    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 5. test_hdv_infeasible_pruning
# ---------------------------------------------------------------------------
def test_hdv_infeasible_pruning() -> None:
    """HDV t_pred too early prunes some paths; the DP finds the sole feasible order."""
    main_seq = ['m0', 'm1']
    ramp_seq = ['r0']
    veh_type_by_id = {'m0': 'cav', 'm1': 'hdv', 'r0': 'cav'}
    t_min_cav_s = {'m0': 1.0, 'r0': 2.0}
    hdv_predicted_time_s = {'m1': 3.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result.target_cross_time_s['m1'] == pytest.approx(3.0, abs=1e-9)
    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


def test_hdv_all_infeasible_raises() -> None:
    """When ALL orderings are infeasible, ValueError is raised."""
    main_seq = ['m0']
    ramp_seq = ['r0']
    veh_type_by_id = {'m0': 'hdv', 'r0': 'hdv'}
    hdv_predicted_time_s = {'m0': 1.0, 'r0': 1.5}

    with pytest.raises(ValueError, match='No feasible schedule'):
        dp_mixed_schedule(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            veh_type_by_id=veh_type_by_id,
            t_min_cav_s={},
            hdv_predicted_time_s=hdv_predicted_time_s,
            delta_1_s=DELTA_1,
            delta_2_s=DELTA_2,
        )


# ---------------------------------------------------------------------------
# 6. test_hdv_forces_cav_delay
# ---------------------------------------------------------------------------
def test_hdv_forces_cav_delay() -> None:
    """HDV in middle position forces subsequent CAV to wait longer."""
    main_seq = ['m0', 'm1']
    ramp_seq = ['r0']
    veh_type_by_id = {'m0': 'cav', 'r0': 'hdv', 'm1': 'cav'}
    t_min_cav_s = {'m0': 1.0, 'm1': 2.0}
    hdv_predicted_time_s = {'r0': 3.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result.target_cross_time_s['r0'] == pytest.approx(3.0, abs=1e-9)

    m1_time = result.target_cross_time_s['m1']
    assert m1_time >= 2.0, 'm1 must be >= its t_min'

    idx_r0 = result.passing_order.index('r0')
    idx_m1 = result.passing_order.index('m1')
    if idx_r0 < idx_m1:
        assert m1_time > 2.0, 'HDV r0 before m1 should force m1 to delay'

    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 7. test_mixed_50_50
# ---------------------------------------------------------------------------
def test_mixed_50_50() -> None:
    """50% HDV mixed scenario with 4 main + 4 ramp vehicles."""
    main_seq = ['m0', 'm1', 'm2', 'm3']
    ramp_seq = ['r0', 'r1', 'r2', 'r3']
    veh_type_by_id = {
        'm0': 'cav', 'm1': 'hdv', 'm2': 'cav', 'm3': 'hdv',
        'r0': 'hdv', 'r1': 'cav', 'r2': 'hdv', 'r3': 'cav',
    }
    t_min_cav_s = {'m0': 1.0, 'm2': 9.0, 'r1': 7.0, 'r3': 16.0}
    hdv_predicted_time_s = {'m1': 5.0, 'm3': 14.0, 'r0': 3.0, 'r2': 11.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert len(result.passing_order) == 8
    assert set(result.passing_order) == set(main_seq + ramp_seq)

    for veh_id in ['m1', 'm3', 'r0', 'r2']:
        assert result.target_cross_time_s[veh_id] == pytest.approx(
            hdv_predicted_time_s[veh_id], abs=1e-9
        )

    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 8. test_empty_main
# ---------------------------------------------------------------------------
def test_empty_main() -> None:
    """Main sequence is empty; only ramp vehicles."""
    main_seq: list[str] = []
    ramp_seq = ['r0', 'r1']
    veh_type_by_id = {'r0': 'cav', 'r1': 'hdv'}
    t_min_cav_s = {'r0': 1.0}
    hdv_predicted_time_s = {'r1': 5.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert len(result.passing_order) == 2
    assert result.passing_order == ['r0', 'r1']
    assert result.target_cross_time_s['r1'] == pytest.approx(5.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 9. test_empty_ramp
# ---------------------------------------------------------------------------
def test_empty_ramp() -> None:
    """Ramp sequence is empty; only main vehicles."""
    main_seq = ['m0', 'm1']
    ramp_seq: list[str] = []
    veh_type_by_id = {'m0': 'hdv', 'm1': 'cav'}
    t_min_cav_s = {'m1': 5.0}
    hdv_predicted_time_s = {'m0': 1.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert len(result.passing_order) == 2
    assert result.passing_order == ['m0', 'm1']
    assert result.target_cross_time_s['m0'] == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 10. test_both_empty
# ---------------------------------------------------------------------------
def test_both_empty() -> None:
    """Both sequences empty → trivial result."""
    result = dp_mixed_schedule(
        main_seq=[],
        ramp_seq=[],
        veh_type_by_id={},
        t_min_cav_s={},
        hdv_predicted_time_s={},
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result.passing_order == []
    assert result.target_cross_time_s == {}
    assert result.cost == pytest.approx(0.0)
    assert result.total_delay_s == pytest.approx(0.0)
    assert result.last_cross_time_s == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 11. test_large_scale
# ---------------------------------------------------------------------------
def test_large_scale() -> None:
    """M=20, N=10, 50% HDV — verify solve time < 50ms.

    Generate globally well-separated times (>= delta_2 apart) so that
    at least one interleaving is always feasible regardless of pruning.
    """
    rng = random.Random(99)
    m_total = 20
    n_total = 10
    total = m_total + n_total
    main_seq = [f'm{i}' for i in range(m_total)]
    ramp_seq = [f'r{i}' for i in range(n_total)]

    all_times: list[float] = []
    base = 0.0
    for _ in range(total):
        base += rng.uniform(DELTA_2 + 0.5, DELTA_2 + 3.0)
        all_times.append(base)

    rng.shuffle(all_times)
    main_times = sorted(all_times[:m_total])
    ramp_times = sorted(all_times[m_total:])

    veh_type_by_id: dict[str, str] = {}
    t_min_cav_s: dict[str, float] = {}
    hdv_predicted_time_s: dict[str, float] = {}

    for i, veh in enumerate(main_seq):
        t = main_times[i]
        if rng.random() < 0.5:
            veh_type_by_id[veh] = 'hdv'
            hdv_predicted_time_s[veh] = t
        else:
            veh_type_by_id[veh] = 'cav'
            t_min_cav_s[veh] = t

    for i, veh in enumerate(ramp_seq):
        t = ramp_times[i]
        if rng.random() < 0.5:
            veh_type_by_id[veh] = 'hdv'
            hdv_predicted_time_s[veh] = t
        else:
            veh_type_by_id[veh] = 'cav'
            t_min_cav_s[veh] = t

    t0 = time.perf_counter()
    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 50.0, f'Solve took {elapsed_ms:.1f}ms, expected < 50ms'
    assert len(result.passing_order) == m_total + n_total
    _verify_gap_constraints(result, main_seq, DELTA_1, DELTA_2)
    _verify_stream_order(result, main_seq, ramp_seq)


# ---------------------------------------------------------------------------
# 12. test_hdv_delay_is_zero
# ---------------------------------------------------------------------------
def test_hdv_delay_is_zero() -> None:
    """HDV vehicles contribute zero delay to total_delay_s."""
    main_seq = ['m0', 'm1']
    ramp_seq = ['r0']
    veh_type_by_id = {'m0': 'cav', 'm1': 'hdv', 'r0': 'cav'}
    t_min_cav_s = {'m0': 1.0, 'r0': 2.0}
    hdv_predicted_time_s = {'m1': 4.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    cav_delay = 0.0
    for veh_id in ['m0', 'r0']:
        cav_delay += result.target_cross_time_s[veh_id] - t_min_cav_s[veh_id]

    assert result.total_delay_s == pytest.approx(cav_delay, abs=1e-9)


# ---------------------------------------------------------------------------
# 13. test_same_stream_ordering
# ---------------------------------------------------------------------------
def test_same_stream_ordering() -> None:
    """Within the same stream, HDV cannot be overtaken — internal order preserved."""
    main_seq = ['m0_hdv', 'm1_cav', 'm2_hdv']
    ramp_seq = ['r0_cav']
    veh_type_by_id = {
        'm0_hdv': 'hdv', 'm1_cav': 'cav', 'm2_hdv': 'hdv', 'r0_cav': 'cav',
    }
    t_min_cav_s = {'m1_cav': 3.0, 'r0_cav': 1.0}
    hdv_predicted_time_s = {'m0_hdv': 1.0, 'm2_hdv': 8.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    main_in_result = [v for v in result.passing_order if v in main_seq]
    assert main_in_result == main_seq, 'Main stream order must be preserved'

    ramp_in_result = [v for v in result.passing_order if v in ramp_seq]
    assert ramp_in_result == ramp_seq, 'Ramp stream order must be preserved'


# ---------------------------------------------------------------------------
# 14. test_different_stream_gap
# ---------------------------------------------------------------------------
def test_different_stream_gap() -> None:
    """Cross-stream gap delta_2 is correctly applied between main and ramp."""
    main_seq = ['m0']
    ramp_seq = ['r0']
    veh_type_by_id = {'m0': 'cav', 'r0': 'cav'}
    t_min_cav_s = {'m0': 1.0, 'r0': 1.0}

    result = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s={},
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    t_first = result.target_cross_time_s[result.passing_order[0]]
    t_second = result.target_cross_time_s[result.passing_order[1]]
    assert t_second - t_first >= DELTA_2 - 1e-9, (
        f'Cross-stream gap {t_second - t_first:.4f} < delta_2={DELTA_2}'
    )


# ---------------------------------------------------------------------------
# 15. test_cost_with_hdv_constraint_higher
# ---------------------------------------------------------------------------
def test_cost_with_hdv_constraint_higher() -> None:
    """Cost with HDV constraints >= unconstrained (all-CAV) cost."""
    main_seq = ['m0', 'm1']
    ramp_seq = ['r0']
    all_vehs = main_seq + ramp_seq

    t_min_values = {'m0': 1.0, 'm1': 4.0, 'r0': 2.5}

    result_unconstrained = dp_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        t_min_s=t_min_values,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    veh_type_by_id = {'m0': 'cav', 'm1': 'cav', 'r0': 'hdv'}
    t_min_cav_s = {'m0': 1.0, 'm1': 4.0}
    hdv_predicted_time_s = {'r0': 2.5}

    result_constrained = dp_mixed_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        delta_1_s=DELTA_1,
        delta_2_s=DELTA_2,
    )

    assert result_constrained.cost >= result_unconstrained.cost - 1e-6, (
        f'Constrained cost {result_constrained.cost:.4f} < '
        f'unconstrained cost {result_unconstrained.cost:.4f}'
    )


# ---------------------------------------------------------------------------
# 16. test_invalid_delta_raises
# ---------------------------------------------------------------------------
def test_invalid_delta_raises() -> None:
    """delta_1_s or delta_2_s <= 0 raises ValueError."""
    with pytest.raises(ValueError, match='must be > 0'):
        dp_mixed_schedule(
            main_seq=['m0'],
            ramp_seq=[],
            veh_type_by_id={'m0': 'cav'},
            t_min_cav_s={'m0': 1.0},
            hdv_predicted_time_s={},
            delta_1_s=0.0,
            delta_2_s=2.0,
        )

    with pytest.raises(ValueError, match='must be > 0'):
        dp_mixed_schedule(
            main_seq=['m0'],
            ramp_seq=[],
            veh_type_by_id={'m0': 'cav'},
            t_min_cav_s={'m0': 1.0},
            hdv_predicted_time_s={},
            delta_1_s=1.5,
            delta_2_s=-1.0,
        )


# ---------------------------------------------------------------------------
# 17. test_missing_type_raises
# ---------------------------------------------------------------------------
def test_missing_type_raises() -> None:
    """Missing or invalid veh_type_by_id entry raises ValueError."""
    with pytest.raises(ValueError, match='Unknown or missing vehicle type'):
        dp_mixed_schedule(
            main_seq=['m0'],
            ramp_seq=[],
            veh_type_by_id={},
            t_min_cav_s={'m0': 1.0},
            hdv_predicted_time_s={},
            delta_1_s=DELTA_1,
            delta_2_s=DELTA_2,
        )


# ---------------------------------------------------------------------------
# 18. test_missing_tmin_raises
# ---------------------------------------------------------------------------
def test_missing_tmin_raises() -> None:
    """Missing t_min_cav_s for a CAV raises KeyError."""
    with pytest.raises(KeyError, match='Missing t_min_cav_s'):
        dp_mixed_schedule(
            main_seq=['m0'],
            ramp_seq=[],
            veh_type_by_id={'m0': 'cav'},
            t_min_cav_s={},
            hdv_predicted_time_s={},
            delta_1_s=DELTA_1,
            delta_2_s=DELTA_2,
        )


# ---------------------------------------------------------------------------
# 19. test_missing_tpred_raises
# ---------------------------------------------------------------------------
def test_missing_tpred_raises() -> None:
    """Missing hdv_predicted_time_s for an HDV raises KeyError."""
    with pytest.raises(KeyError, match='Missing hdv_predicted_time_s'):
        dp_mixed_schedule(
            main_seq=['m0'],
            ramp_seq=[],
            veh_type_by_id={'m0': 'hdv'},
            t_min_cav_s={},
            hdv_predicted_time_s={},
            delta_1_s=DELTA_1,
            delta_2_s=DELTA_2,
        )
