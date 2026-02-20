from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.scheduler.arrival_time import minimum_arrival_time_at_on_ramp
from ramp.scheduler.dp import dp_schedule


def _calc_next_time(
    *,
    pre_time_s: float,
    pre_lane: int,
    lane: int,
    t_min_s: float,
    delta_1_s: float,
    delta_2_s: float,
) -> float:
    if pre_lane == -1:
        return t_min_s
    gap_s = delta_1_s if lane == pre_lane else delta_2_s
    return max(t_min_s, pre_time_s + gap_s)


def _bruteforce_best_cost(
    *,
    main_seq: list[str],
    ramp_seq: list[str],
    t_min_s: dict[str, float],
    delta_1_s: float,
    delta_2_s: float,
) -> float:
    m_total = len(main_seq)
    n_total = len(ramp_seq)

    if m_total == 0 and n_total == 0:
        return 0.0

    best = float('inf')
    # Enumerate all interleavings that keep internal order (choose positions for main vehicles).
    for main_positions in itertools.combinations(range(m_total + n_total), m_total):
        main_positions = set(main_positions)
        m_idx = 0
        n_idx = 0
        pre_time_s = 0.0
        pre_lane = -1
        delay_s = 0.0
        for k in range(m_total + n_total):
            if k in main_positions:
                lane = 0
                veh = main_seq[m_idx]
                m_idx += 1
            else:
                lane = 1
                veh = ramp_seq[n_idx]
                n_idx += 1

            tmin = float(t_min_s[veh])
            time_s = _calc_next_time(
                pre_time_s=pre_time_s,
                pre_lane=pre_lane,
                lane=lane,
                t_min_s=tmin,
                delta_1_s=delta_1_s,
                delta_2_s=delta_2_s,
            )
            delay_s += time_s - tmin
            pre_time_s = time_s
            pre_lane = lane

        cost = pre_time_s + delay_s
        best = min(best, cost)

    return best


def _cost_of_schedule(
    *,
    passing_order: list[str],
    t_min_s: dict[str, float],
    lane_by_vehicle: dict[str, int],
    delta_1_s: float,
    delta_2_s: float,
) -> float:
    pre_time_s = 0.0
    pre_lane = -1
    delay_s = 0.0
    for veh in passing_order:
        lane = lane_by_vehicle[veh]
        tmin = float(t_min_s[veh])
        time_s = _calc_next_time(
            pre_time_s=pre_time_s,
            pre_lane=pre_lane,
            lane=lane,
            t_min_s=tmin,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )
        delay_s += time_s - tmin
        pre_time_s = time_s
        pre_lane = lane
    return pre_time_s + delay_s


def test_arrival_time_boundary_conditions() -> None:
    t_now = 10.0
    assert minimum_arrival_time_at_on_ramp(
        t_now_s=t_now, distance_m=0.0, speed_mps=5.0, a_max_mps2=2.0, v_max_mps=10.0
    ) == pytest.approx(t_now)

    # No acceleration -> constant-speed fallback (with vmax cap).
    t_min = minimum_arrival_time_at_on_ramp(
        t_now_s=t_now, distance_m=100.0, speed_mps=0.0, a_max_mps2=0.0, v_max_mps=10.0
    )
    assert t_min > t_now

    # v >= vmax should not go negative.
    t_min = minimum_arrival_time_at_on_ramp(
        t_now_s=t_now, distance_m=100.0, speed_mps=30.0, a_max_mps2=2.0, v_max_mps=20.0
    )
    assert t_min == pytest.approx(t_now + 100.0 / 20.0)


@pytest.mark.parametrize('m_total', [0, 1, 2, 3])
@pytest.mark.parametrize('n_total', [0, 1, 2, 3])
def test_dp_matches_bruteforce_small(m_total: int, n_total: int) -> None:
    rng = random.Random(0)
    delta_1_s = 1.5
    delta_2_s = 2.0

    main_seq = [f'm{i}' for i in range(m_total)]
    ramp_seq = [f'r{i}' for i in range(n_total)]

    for _ in range(50):
        t_min_s: dict[str, float] = {}
        base = rng.uniform(0.0, 5.0)
        for veh in main_seq + ramp_seq:
            t_min_s[veh] = base + rng.uniform(0.0, 10.0)

        expected = _bruteforce_best_cost(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            t_min_s=t_min_s,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )

        result = dp_schedule(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            t_min_s=t_min_s,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )

        lane_by_vehicle = {veh: 0 for veh in main_seq} | {veh: 1 for veh in ramp_seq}
        got = _cost_of_schedule(
            passing_order=result.passing_order,
            t_min_s=t_min_s,
            lane_by_vehicle=lane_by_vehicle,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )

        assert got == pytest.approx(expected, rel=1e-9, abs=1e-9)

        # Internal order per stream must be preserved.
        assert [v for v in result.passing_order if v in main_seq] == main_seq
        assert [v for v in result.passing_order if v in ramp_seq] == ramp_seq

        # target_cross_time_s must be consistent with the returned passing order.
        assert set(result.target_cross_time_s) == set(main_seq + ramp_seq)
        pre_time_s = 0.0
        pre_lane = -1
        for veh in result.passing_order:
            lane = lane_by_vehicle[veh]
            tmin = float(t_min_s[veh])
            expected_time_s = _calc_next_time(
                pre_time_s=pre_time_s,
                pre_lane=pre_lane,
                lane=lane,
                t_min_s=tmin,
                delta_1_s=delta_1_s,
                delta_2_s=delta_2_s,
            )
            assert result.target_cross_time_s[veh] == pytest.approx(
                expected_time_s, rel=1e-9, abs=1e-9
            )
            assert result.target_cross_time_s[veh] >= tmin
            pre_time_s = expected_time_s
            pre_lane = lane
