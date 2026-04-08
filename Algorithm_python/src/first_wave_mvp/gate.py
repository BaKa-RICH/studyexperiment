"""第一波 MVP 的共享 acceptance gate。"""

from __future__ import annotations

from math import isfinite

from first_wave_mvp.step2_fifo import (
    _calc_time_window,
    _derive_fifo_gap,
    _estimate_target_lane_arrivals,
)
from first_wave_mvp.types import GateResult, PlanningSnapshot, RejectReason, VehicleState


def _make_result(
    *,
    snapshot: PlanningSnapshot,
    candidate_id: str,
    accepted: bool,
    reject_reason: RejectReason | None,
    checked_time_grid_s: tuple[float, ...] = (),
    min_margin_m: float | None = None,
    binding_check: str | None = None,
) -> GateResult:
    return GateResult(
        snapshot_id=snapshot.snapshot_id,
        candidate_id=candidate_id,
        accepted=accepted,
        reject_reason=reject_reason,
        checked_time_grid_s=checked_time_grid_s,
        min_margin_m=min_margin_m,
        binding_check=binding_check,
    )


def _partner_ids_are_valid(snapshot: PlanningSnapshot, partner_ids: tuple[str, ...]) -> bool:
    valid_ids = set(snapshot.control_zone_states) | set(snapshot.committed_plans)
    return all(partner_id in valid_ids for partner_id in partner_ids)


def _zone_is_valid(snapshot: PlanningSnapshot, candidate_x_s_m: float, candidate_x_m_m: int) -> bool:
    legal_start_m, legal_end_m = snapshot.scenario.legal_merge_zone_m
    return legal_start_m <= candidate_x_s_m <= candidate_x_m_m <= legal_end_m


def _timing_is_valid(snapshot: PlanningSnapshot, candidate) -> bool:
    ordered_arrivals = _estimate_target_lane_arrivals(snapshot, candidate.x_m_m)
    expected_gap = _derive_fifo_gap(
        ramp_arrival_time_s=candidate.t_r_free_s,
        ordered_arrivals=ordered_arrivals,
        epsilon_t_s=snapshot.scenario.epsilon_t_s,
    )
    lower_bound_s, upper_bound_s = _calc_time_window(
        ramp_free_time_s=candidate.t_r_free_s,
        gap=expected_gap,
        ordered_arrivals=ordered_arrivals,
        snapshot=snapshot,
    )
    if lower_bound_s > upper_bound_s:
        return False

    epsilon_t_s = snapshot.scenario.epsilon_t_s
    return (
        candidate.tau_lc_s >= snapshot.sim_time_s
        and candidate.tau_lc_s < candidate.t_m_s
        and candidate.t_m_s + epsilon_t_s >= candidate.t_r_free_s
        and abs(candidate.t_m_s - lower_bound_s) <= epsilon_t_s
        and candidate.t_m_s <= upper_bound_s + epsilon_t_s
    )


def _sequence_relation(pred_id: str | None, foll_id: str | None) -> str:
    if pred_id is None and foll_id is None:
        return "single_gap"
    if pred_id is None:
        return "before_first"
    if foll_id is None:
        return "after_last"
    return "between_pred_and_foll"


def _gap_identity_is_valid(snapshot: PlanningSnapshot, candidate) -> bool:
    ordered_arrivals = _estimate_target_lane_arrivals(snapshot, candidate.x_m_m)
    expected_gap = _derive_fifo_gap(
        ramp_arrival_time_s=candidate.t_r_free_s,
        ordered_arrivals=ordered_arrivals,
        epsilon_t_s=snapshot.scenario.epsilon_t_s,
    )
    expected_relation = _sequence_relation(expected_gap.pred_id, expected_gap.foll_id)
    return (
        candidate.target_gap.pred_id == expected_gap.pred_id
        and candidate.target_gap.foll_id == expected_gap.foll_id
        and candidate.sequence_relation == expected_relation
    )


def _dynamic_limits_are_valid(snapshot: PlanningSnapshot) -> bool:
    ego = snapshot.ego_state
    vmax_mps = (
        snapshot.scenario.ramp_vmax_mps
        if ego.stream == "ramp"
        else snapshot.scenario.mainline_vmax_mps
    )
    return (
        0.0 <= ego.speed_mps <= vmax_mps
        and -snapshot.scenario.b_safe_mps2 <= ego.accel_mps2 <= snapshot.scenario.a_max_mps2
    )


def _build_checked_time_grid(snapshot: PlanningSnapshot, candidate) -> tuple[float, ...]:
    times = {candidate.tau_lc_s, candidate.t_m_s, candidate.t_m_s + snapshot.scenario.post_merge_guard_s}
    tick_s = snapshot.scenario.gate_sampling_dt_s
    current_t_s = candidate.tau_lc_s
    while current_t_s <= candidate.t_m_s + 1e-9:
        times.add(round(current_t_s, 9))
        current_t_s += tick_s
    return tuple(sorted(times))


def _position_at_time(state: VehicleState, *, sim_time_s: float, target_time_s: float) -> float:
    delta_t_s = max(target_time_s - sim_time_s, 0.0)
    return state.x_pos_m + state.speed_mps * delta_t_s


def _get_neighbor_state(snapshot: PlanningSnapshot, object_id: str | None) -> VehicleState | None:
    if object_id is None:
        return None
    return snapshot.control_zone_states.get(object_id)


def _calc_min_margin(snapshot: PlanningSnapshot, candidate, checked_time_grid_s: tuple[float, ...]) -> float:
    ego = snapshot.ego_state
    ego_length_m = ego.length_m
    min_margin_m = float("inf")

    pred_state = _get_neighbor_state(snapshot, candidate.target_gap.pred_id)
    foll_state = _get_neighbor_state(snapshot, candidate.target_gap.foll_id)

    for target_time_s in checked_time_grid_s:
        ego_x_m = _position_at_time(ego, sim_time_s=snapshot.sim_time_s, target_time_s=target_time_s)

        if pred_state is not None:
            pred_x_m = _position_at_time(
                pred_state,
                sim_time_s=snapshot.sim_time_s,
                target_time_s=target_time_s,
            )
            pred_margin_m = pred_x_m - ego_x_m - ego_length_m - (
                snapshot.scenario.min_gap_m + snapshot.scenario.time_headway_s * ego.speed_mps
            )
            min_margin_m = min(min_margin_m, pred_margin_m)

        if foll_state is not None:
            foll_x_m = _position_at_time(
                foll_state,
                sim_time_s=snapshot.sim_time_s,
                target_time_s=target_time_s,
            )
            foll_margin_m = ego_x_m - foll_x_m - foll_state.length_m - (
                snapshot.scenario.min_gap_m + snapshot.scenario.time_headway_s * foll_state.speed_mps
            )
            min_margin_m = min(min_margin_m, foll_margin_m)

    return min_margin_m


def accept_candidate(*, snapshot: PlanningSnapshot, candidate) -> GateResult:
    if not _partner_ids_are_valid(snapshot, candidate.partner_ids):
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_PARTNER_INVALID,
            binding_check="partner_ids",
        )

    if not _zone_is_valid(snapshot, candidate.x_s_m, candidate.x_m_m):
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_ZONE,
            binding_check="zone",
        )

    if not _timing_is_valid(snapshot, candidate):
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_TIMING,
            binding_check="timing",
        )

    if not _gap_identity_is_valid(snapshot, candidate):
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_GAP_IDENTITY,
            binding_check="gap_identity",
        )

    if not _dynamic_limits_are_valid(snapshot):
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_DYNAMIC_LIMIT,
            binding_check="dynamic_limit",
        )

    checked_time_grid_s = _build_checked_time_grid(snapshot, candidate)
    interval_times_s = tuple(time_s for time_s in checked_time_grid_s if time_s <= candidate.t_m_s)
    min_margin_m = _calc_min_margin(snapshot, candidate, interval_times_s)
    if isfinite(min_margin_m) and min_margin_m < 0.0:
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_INTERVAL_SAFETY,
            checked_time_grid_s=checked_time_grid_s,
            min_margin_m=min_margin_m,
            binding_check="interval_safety",
        )

    post_merge_times_s = tuple(time_s for time_s in checked_time_grid_s if time_s >= candidate.t_m_s)
    post_merge_margin_m = _calc_min_margin(snapshot, candidate, post_merge_times_s)
    if isfinite(post_merge_margin_m) and post_merge_margin_m < 0.0:
        return _make_result(
            snapshot=snapshot,
            candidate_id=candidate.candidate_id,
            accepted=False,
            reject_reason=RejectReason.REJECT_POST_MERGE_SAFETY,
            checked_time_grid_s=checked_time_grid_s,
            min_margin_m=post_merge_margin_m,
            binding_check="post_merge_safety",
        )

    return _make_result(
        snapshot=snapshot,
        candidate_id=candidate.candidate_id,
        accepted=True,
        reject_reason=None,
        checked_time_grid_s=checked_time_grid_s,
        min_margin_m=None if not isfinite(min_margin_m) else min_margin_m,
        binding_check="accept",
    )


__all__ = ["accept_candidate"]
