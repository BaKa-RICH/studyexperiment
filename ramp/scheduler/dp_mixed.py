from __future__ import annotations

from dataclasses import dataclass

from .dp import ScheduleResult

_FEASIBILITY_TOL = 1e-9


@dataclass(frozen=True)
class _MixedStateRecord:
    time_s: float
    delay_s: float
    parent: tuple[int, int, int] | None


def _rank(*, time_s: float, delay_s: float, last_lane: int) -> tuple[float, float, float, int]:
    cost = time_s + delay_s
    return (cost, time_s, delay_s, last_lane)


def dp_mixed_schedule(
    *,
    main_seq: list[str],
    ramp_seq: list[str],
    veh_type_by_id: dict[str, str],
    t_min_cav_s: dict[str, float],
    hdv_predicted_time_s: dict[str, float],
    delta_1_s: float,
    delta_2_s: float,
) -> ScheduleResult:
    """DP scheduler for mixed CAV/HDV traffic.

    State (m, n, last_lane) identical to dp_schedule.
    Transition differs by vehicle type:
      CAV: time_s = max(t_min, pre_time + gap)  (controllable)
      HDV: time_s = predicted_time  (fixed; prune if gap violated)
    HDV delay contribution is always 0.
    """

    if delta_1_s <= 0 or delta_2_s <= 0:
        raise ValueError('delta_1_s and delta_2_s must be > 0')

    m_total = len(main_seq)
    n_total = len(ramp_seq)

    best: dict[tuple[int, int, int], _MixedStateRecord] = {
        (0, 0, -1): _MixedStateRecord(0.0, 0.0, None)
    }
    frontier: dict[tuple[int, int, int], _MixedStateRecord] = {
        (0, 0, -1): best[(0, 0, -1)]
    }

    for _layer in range(m_total + n_total):
        next_frontier: dict[tuple[int, int, int], _MixedStateRecord] = {}
        for (m, n, last_lane), record in frontier.items():
            pre_time_s = record.time_s
            pre_delay_s = record.delay_s

            for lane, seq, idx, limit in [
                (0, main_seq, m, m_total),
                (1, ramp_seq, n, n_total),
            ]:
                if idx >= limit:
                    continue

                veh_id = seq[idx]
                vtype = veh_type_by_id.get(veh_id)
                if vtype not in ('cav', 'hdv'):
                    raise ValueError(
                        f'Unknown or missing vehicle type for {veh_id}: {vtype}'
                    )

                gap_s = 0.0
                if last_lane != -1:
                    gap_s = delta_1_s if last_lane == lane else delta_2_s

                prev_is_hdv = False
                if last_lane != -1:
                    if last_lane == 0 and m > 0:
                        prev_is_hdv = veh_type_by_id.get(main_seq[m - 1]) == 'hdv'
                    elif last_lane == 1 and n > 0:
                        prev_is_hdv = veh_type_by_id.get(ramp_seq[n - 1]) == 'hdv'

                if vtype == 'cav':
                    if veh_id not in t_min_cav_s:
                        raise KeyError(f'Missing t_min_cav_s for CAV: {veh_id}')
                    tmin = float(t_min_cav_s[veh_id])
                    if last_lane == -1:
                        time_s = tmin
                    else:
                        time_s = max(tmin, pre_time_s + gap_s)
                    delay_s = pre_delay_s + (time_s - tmin)
                else:
                    if veh_id not in hdv_predicted_time_s:
                        raise KeyError(
                            f'Missing hdv_predicted_time_s for HDV: {veh_id}'
                        )
                    time_s = float(hdv_predicted_time_s[veh_id])
                    if last_lane != -1:
                        if prev_is_hdv:
                            if time_s < pre_time_s - _FEASIBILITY_TOL:
                                continue
                        else:
                            if time_s < pre_time_s + gap_s - _FEASIBILITY_TOL:
                                continue
                    delay_s = pre_delay_s

                key = (
                    m + (1 if lane == 0 else 0),
                    n + (1 if lane == 1 else 0),
                    lane,
                )
                candidate = _MixedStateRecord(time_s, delay_s, (m, n, last_lane))
                existing = next_frontier.get(key)
                if existing is None or _rank(
                    time_s=time_s, delay_s=delay_s, last_lane=lane
                ) < _rank(
                    time_s=existing.time_s, delay_s=existing.delay_s, last_lane=lane
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
        if m_total == 0 and n_total == 0:
            return ScheduleResult([], {}, 0.0, 0.0, 0.0)
        raise ValueError(
            'No feasible schedule: HDV timing constraints make all orderings infeasible'
        )

    final_key = min(
        candidates,
        key=lambda k: _rank(
            time_s=best[k].time_s, delay_s=best[k].delay_s, last_lane=k[2]
        ),
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
