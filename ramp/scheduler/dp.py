from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleResult:
    passing_order: list[str]
    target_cross_time_s: dict[str, float]
    cost: float
    total_delay_s: float
    last_cross_time_s: float


@dataclass(frozen=True)
class _StateRecord:
    time_s: float
    delay_s: float
    parent: tuple[int, int, int] | None


def _rank(*, time_s: float, delay_s: float, last_lane: int) -> tuple[float, float, float, int]:
    cost = time_s + delay_s
    return (cost, time_s, delay_s, last_lane)


def dp_schedule(
    *,
    main_seq: list[str],
    ramp_seq: list[str],
    t_min_s: dict[str, float],
    delta_1_s: float,
    delta_2_s: float,
) -> ScheduleResult:
    """Compute the optimal merge passing order and target crossing times.

    Ported from CAVSim `TestingRelated/DPMethod.cpp`:
    - state key: (m, n, last_lane)
    - state value: (time, delay, parent)
    - transition: `CalNextVehTime`
    - objective: minimize `time + delay`
    """

    if delta_1_s <= 0 or delta_2_s <= 0:
        raise ValueError('delta_1_s and delta_2_s must be > 0')

    m_total = len(main_seq)
    n_total = len(ramp_seq)

    # A global dict is safe because each (m, n, last_lane) appears only at layer m+n.
    best: dict[tuple[int, int, int], _StateRecord] = {(0, 0, -1): _StateRecord(0.0, 0.0, None)}
    frontier: dict[tuple[int, int, int], _StateRecord] = {(0, 0, -1): best[(0, 0, -1)]}

    for _layer in range(m_total + n_total):
        next_frontier: dict[tuple[int, int, int], _StateRecord] = {}
        for (m, n, last_lane), record in frontier.items():
            pre_time_s = record.time_s
            pre_delay_s = record.delay_s

            if m < m_total:
                veh_id = main_seq[m]
                if veh_id not in t_min_s:
                    raise KeyError(f'Missing t_min for vehicle: {veh_id}')
                tmin = float(t_min_s[veh_id])
                if last_lane == -1:
                    time_s = tmin
                else:
                    gap_s = delta_1_s if last_lane == 0 else delta_2_s
                    time_s = max(tmin, pre_time_s + gap_s)
                delay_s = pre_delay_s + (time_s - tmin)
                key = (m + 1, n, 0)
                candidate = _StateRecord(time_s, delay_s, (m, n, last_lane))
                existing = next_frontier.get(key)
                if existing is None or _rank(time_s=time_s, delay_s=delay_s, last_lane=0) < _rank(
                    time_s=existing.time_s, delay_s=existing.delay_s, last_lane=0
                ):
                    next_frontier[key] = candidate
                    best[key] = candidate

            if n < n_total:
                veh_id = ramp_seq[n]
                if veh_id not in t_min_s:
                    raise KeyError(f'Missing t_min for vehicle: {veh_id}')
                tmin = float(t_min_s[veh_id])
                if last_lane == -1:
                    time_s = tmin
                else:
                    gap_s = delta_1_s if last_lane == 1 else delta_2_s
                    time_s = max(tmin, pre_time_s + gap_s)
                delay_s = pre_delay_s + (time_s - tmin)
                key = (m, n + 1, 1)
                candidate = _StateRecord(time_s, delay_s, (m, n, last_lane))
                existing = next_frontier.get(key)
                if existing is None or _rank(time_s=time_s, delay_s=delay_s, last_lane=1) < _rank(
                    time_s=existing.time_s, delay_s=existing.delay_s, last_lane=1
                ):
                    next_frontier[key] = candidate
                    best[key] = candidate

        frontier = next_frontier

    candidates: list[tuple[int, int, int]] = []
    if (m_total, n_total, 0) in best:
        candidates.append((m_total, n_total, 0))
    if (m_total, n_total, 1) in best:
        candidates.append((m_total, n_total, 1))

    if not candidates:
        # Only happens when both sequences are empty.
        return ScheduleResult([], {}, 0.0, 0.0, 0.0)

    final_key = min(
        candidates,
        key=lambda k: _rank(time_s=best[k].time_s, delay_s=best[k].delay_s, last_lane=k[2]),
    )

    passing_order_rev: list[str] = []
    target_cross_time_s: dict[str, float] = {}
    state_key = final_key
    while state_key != (0, 0, -1):
        record = best[state_key]
        m, n, last_lane = state_key
        if last_lane == 0:
            veh_id = main_seq[m - 1]
        else:
            veh_id = ramp_seq[n - 1]
        passing_order_rev.append(veh_id)
        target_cross_time_s[veh_id] = record.time_s
        if record.parent is None:
            raise RuntimeError('DP backtracking reached a state with no parent')
        state_key = record.parent

    passing_order = list(reversed(passing_order_rev))
    final_record = best[final_key]
    cost = final_record.time_s + final_record.delay_s
    return ScheduleResult(
        passing_order=passing_order,
        target_cross_time_s=target_cross_time_s,
        cost=cost,
        total_delay_s=final_record.delay_s,
        last_cross_time_s=final_record.time_s,
    )
