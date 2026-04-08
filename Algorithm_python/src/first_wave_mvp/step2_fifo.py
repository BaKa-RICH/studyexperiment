"""第一波 MVP 的 FIFO Step-2 候选生成。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, inf, isfinite

from first_wave_mvp.snapshot import select_planning_ego
from first_wave_mvp.types import (
    CandidatePlan,
    GapRef,
    PlanningSnapshot,
    PolicyTag,
    VehicleState,
)


MIN_SPEED_MPS = 0.1


@dataclass(frozen=True, slots=True)
class _OrderedArrival:
    object_id: str
    arrival_time_s: float
    kind: str


def _estimate_arrival_time(
    *,
    sim_time_s: float,
    x_anchor_m: int,
    state: VehicleState,
) -> float:
    remaining_distance_m = max(float(x_anchor_m) - state.x_pos_m, 0.0)
    if remaining_distance_m == 0.0:
        return sim_time_s

    if state.speed_mps <= 0.0:
        return inf

    return sim_time_s + remaining_distance_m / max(state.speed_mps, MIN_SPEED_MPS)


def _find_ramp_predecessor(snapshot: PlanningSnapshot) -> VehicleState | None:
    ego = snapshot.ego_state
    predecessors = [
        state
        for veh_id, state in snapshot.control_zone_states.items()
        if veh_id != ego.veh_id
        and state.stream == ego.stream
        and state.lane_id == ego.lane_id
        and state.x_pos_m > ego.x_pos_m
    ]

    if not predecessors:
        return None

    return min(predecessors, key=lambda state: (state.x_pos_m - ego.x_pos_m, state.veh_id))


def _estimate_ramp_free_completion_time(snapshot: PlanningSnapshot, x_anchor_m: int) -> float:
    ego_arrival_s = _estimate_arrival_time(
        sim_time_s=snapshot.sim_time_s,
        x_anchor_m=x_anchor_m,
        state=snapshot.ego_state,
    )
    if not isfinite(ego_arrival_s):
        return inf

    predecessor = _find_ramp_predecessor(snapshot)
    if predecessor is None:
        return ego_arrival_s

    predecessor_arrival_s = _estimate_arrival_time(
        sim_time_s=snapshot.sim_time_s,
        x_anchor_m=x_anchor_m,
        state=predecessor,
    )
    if not isfinite(predecessor_arrival_s):
        return inf

    return max(ego_arrival_s, predecessor_arrival_s + snapshot.scenario.time_headway_s)


def _estimate_x_lb(snapshot: PlanningSnapshot) -> int:
    ego_speed_mps = max(snapshot.ego_state.speed_mps, 0.0)
    legal_start_m, _ = snapshot.scenario.legal_merge_zone_m
    delta_x_lc_m = ego_speed_mps * snapshot.scenario.lane_change_duration_s
    return ceil(legal_start_m + delta_x_lc_m)


def _enumerate_anchors(snapshot: PlanningSnapshot) -> list[int]:
    lower_bound_m = _estimate_x_lb(snapshot)
    _, legal_end_m = snapshot.scenario.legal_merge_zone_m

    if lower_bound_m > legal_end_m:
        return []

    if snapshot.policy_tag is PolicyTag.FIFO_FIXED_ANCHOR:
        fixed_anchor_m = snapshot.scenario.fixed_anchor_m
        return [fixed_anchor_m] if lower_bound_m <= fixed_anchor_m <= legal_end_m else []

    if snapshot.policy_tag is PolicyTag.FIFO_FLEXIBLE_ANCHOR:
        return list(range(lower_bound_m, legal_end_m + 1))

    return []


def _estimate_target_lane_arrivals(
    snapshot: PlanningSnapshot,
    x_anchor_m: int,
) -> list[_OrderedArrival]:
    arrivals: list[_OrderedArrival] = []

    for object_id in snapshot.target_lane_object_ids:
        if object_id in snapshot.committed_plans:
            committed_plan = snapshot.committed_plans[object_id]
            arrival_time_s = committed_plan.candidate.t_m_s
            kind = "committed"
        else:
            state = snapshot.control_zone_states.get(object_id)
            if state is None:
                continue
            arrival_time_s = _estimate_arrival_time(
                sim_time_s=snapshot.sim_time_s,
                x_anchor_m=x_anchor_m,
                state=state,
            )
            kind = "mainline"

        arrivals.append(
            _OrderedArrival(
                object_id=object_id,
                arrival_time_s=arrival_time_s,
                kind=kind,
            )
        )

    return sorted(arrivals, key=lambda item: (item.arrival_time_s, item.object_id))


def _derive_fifo_gap(
    *,
    ramp_arrival_time_s: float,
    ordered_arrivals: list[_OrderedArrival],
    epsilon_t_s: float,
) -> GapRef:
    insert_index = 0
    for arrival in ordered_arrivals:
        if ramp_arrival_time_s > arrival.arrival_time_s + epsilon_t_s:
            insert_index += 1
            continue

        if abs(ramp_arrival_time_s - arrival.arrival_time_s) <= epsilon_t_s:
            insert_index += 1
            continue

        break

    pred_id = ordered_arrivals[insert_index - 1].object_id if insert_index > 0 else None
    foll_id = ordered_arrivals[insert_index].object_id if insert_index < len(ordered_arrivals) else None
    return GapRef(pred_id=pred_id, foll_id=foll_id)


def _calc_time_window(
    *,
    ramp_free_time_s: float,
    gap: GapRef,
    ordered_arrivals: list[_OrderedArrival],
    snapshot: PlanningSnapshot,
) -> tuple[float, float]:
    arrival_by_id = {arrival.object_id: arrival.arrival_time_s for arrival in ordered_arrivals}

    lower_bound_s = ramp_free_time_s
    if gap.pred_id is not None:
        lower_bound_s = max(
            lower_bound_s,
            arrival_by_id[gap.pred_id] + snapshot.scenario.h_pr_s,
        )

    upper_bound_s = inf
    if gap.foll_id is not None:
        upper_bound_s = arrival_by_id[gap.foll_id] - snapshot.scenario.h_rf_s

    return lower_bound_s, upper_bound_s


def _sequence_relation(gap: GapRef) -> str:
    if gap.pred_id is None and gap.foll_id is None:
        return "single_gap"
    if gap.pred_id is None:
        return "before_first"
    if gap.foll_id is None:
        return "after_last"
    return "between_pred_and_foll"


def _make_stable_candidate_id(snapshot: PlanningSnapshot, x_anchor_m: int, gap: GapRef) -> str:
    pred_id = gap.pred_id or "none"
    foll_id = gap.foll_id or "none"
    return f"{snapshot.snapshot_id}:{snapshot.policy_tag.value}:{x_anchor_m}:{pred_id}:{foll_id}"


def generate_candidates(*, snapshot: PlanningSnapshot) -> list[CandidatePlan]:
    if select_planning_ego(snapshot.control_zone_states) is None:
        return []

    candidates: list[CandidatePlan] = []
    ego_speed_mps = max(snapshot.ego_state.speed_mps, 0.0)

    for x_anchor_m in _enumerate_anchors(snapshot):
        ramp_free_time_s = _estimate_ramp_free_completion_time(snapshot, x_anchor_m)
        if not isfinite(ramp_free_time_s):
            continue

        ordered_arrivals = _estimate_target_lane_arrivals(snapshot, x_anchor_m)
        gap = _derive_fifo_gap(
            ramp_arrival_time_s=ramp_free_time_s,
            ordered_arrivals=ordered_arrivals,
            epsilon_t_s=snapshot.scenario.epsilon_t_s,
        )
        lower_bound_s, upper_bound_s = _calc_time_window(
            ramp_free_time_s=ramp_free_time_s,
            gap=gap,
            ordered_arrivals=ordered_arrivals,
            snapshot=snapshot,
        )
        if lower_bound_s > upper_bound_s:
            continue

        t_m_s = lower_bound_s
        tau_lc_s = t_m_s - snapshot.scenario.lane_change_duration_s
        x_s_m = x_anchor_m - ego_speed_mps * snapshot.scenario.lane_change_duration_s

        candidate = CandidatePlan(
            snapshot_id=snapshot.snapshot_id,
            candidate_id=_make_stable_candidate_id(snapshot, x_anchor_m, gap),
            policy_tag=snapshot.policy_tag,
            ego_id=snapshot.ego_id,
            target_gap=gap,
            x_m_m=x_anchor_m,
            t_m_s=t_m_s,
            t_r_free_s=ramp_free_time_s,
            partner_ids=tuple(),
            sequence_relation=_sequence_relation(gap),
            tau_lc_s=tau_lc_s,
            x_s_m=x_s_m,
            objective_key=(t_m_s, t_m_s - ramp_free_time_s, x_anchor_m),
        )
        candidates.append(candidate)

    return sorted(candidates, key=lambda candidate: candidate.objective_key)


__all__ = ["generate_candidates"]
