"""Evidence-chain schema for ramp-merge experiments.

Anchor semantics (frozen by Todo 2.1)
--------------------------------------
``expected_merge_position_m`` = remaining distance (m) to *merge_edge* at the
planned merge moment.

* **fixed** policy: the merge action is crossing the merge_edge itself,
  so ``expected = 0.0``.  Authoritative feedback event: ``cross_merge``.
* **flexible** policy: the merge action is the L0→L1 lane change,
  which happens *before* the merge_edge, so
  ``expected = FLEXIBLE_POSITION_OFFSET_M``.
  Authoritative feedback event: ``lc_complete``.

For flexible, a ``cross_merge`` feedback is still recorded for lifecycle
tracking, but its position error is only calculated when no prior
``lc_complete`` was observed (indicating a fallback / prediction failure).
"""
from __future__ import annotations

from collections import Counter

MERGE_POLICY_FIXED = 'fixed'
MERGE_POLICY_FLEXIBLE = 'flexible'
FALLBACK_POLICY_KEEP_LANE = 'keep_lane_then_release'
SPEED_MISMATCH_THRESHOLD_MPS = 2.0
FLEXIBLE_POSITION_OFFSET_M = 20.0

ANCHOR_EVENT_CROSS_MERGE = 'cross_merge'
ANCHOR_EVENT_LC_COMPLETE = 'lc_complete'
ANCHOR_EVENT_CROSS_MERGE_FALLBACK = 'cross_merge_fallback'

CONTROL_FIELDS = [
    'time',
    'event_id',
    'contract_id',
    'veh_id',
    'commanded_speed',
    'actual_speed',
    'speed_error',
    'speed_mode_applied',
    'lane_change_command_issued',
    'lane_change_mode_applied',
    'autonomous_lane_change_detected',
    'controlled_cav_step',
]

CONTRACT_FIELDS = [
    'time',
    'contract_id',
    'zoneb_algorithm',
    'merge_policy',
    'ego_vehicle_id',
    'vehicle_type',
    'stream',
    'sequence_rank',
    'target_predecessor_id',
    'target_follower_id',
    'merge_window_start_s',
    'merge_window_end_s',
    'expected_merge_time_s',
    'expected_merge_position_m',
    'desired_merge_speed_mps',
    'valid_until_s',
    'fallback_policy',
]

FEEDBACK_FIELDS = [
    'time',
    'event_id',
    'contract_id',
    'ego_vehicle_id',
    'stream',
    'anchor_event_type',
    'execution_state',
    'gap_found',
    'gap_reject_reason',
    'actual_merge_time_s',
    'actual_merge_position_m',
    'actual_predecessor_id',
    'actual_follower_id',
    'planned_actual_time_error_s',
    'planned_actual_position_error_m',
    'fallback_reason',
    'replan_required',
]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * q))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return float(sorted_vals[idx])


def resolve_merge_policy(*, policy: str, policy_variant: str) -> str:
    variant = policy_variant.lower()
    if 'flex' in variant:
        return MERGE_POLICY_FLEXIBLE
    if 'fixed' in variant:
        return MERGE_POLICY_FIXED
    if policy == 'hierarchical':
        return MERGE_POLICY_FLEXIBLE
    return MERGE_POLICY_FIXED


def resolve_anchor_event_type(*, merge_policy: str) -> str:
    """Return the authoritative feedback event type for a given merge policy.

    * fixed  → cross_merge  (merge action = reaching the merge edge)
    * flexible → lc_complete (merge action = L0→L1 lane change)
    """
    if merge_policy == MERGE_POLICY_FIXED:
        return ANCHOR_EVENT_CROSS_MERGE
    if merge_policy == MERGE_POLICY_FLEXIBLE:
        return ANCHOR_EVENT_LC_COMPLETE
    raise ValueError(f'Unknown merge_policy: {merge_policy!r}')


def merge_window_half_span_s(
    *,
    policy: str,
    step_length_s: float,
    fifo_gap_s: float,
    delta_1_s: float,
    delta_2_s: float,
) -> float:
    if policy == 'fifo':
        return max(step_length_s, fifo_gap_s)
    if policy in {'dp', 'hierarchical'}:
        return max(step_length_s, delta_1_s, delta_2_s)
    return step_length_s


def expected_merge_position_m(
    *,
    merge_policy: str,
) -> float:
    """Expected remaining distance to merge edge at merge moment.

    Fixed policy: vehicle merges at merge edge (d_to_merge = 0).
    Flexible policy: vehicle merges ~FLEXIBLE_POSITION_OFFSET_M before merge edge.
    """
    if merge_policy == MERGE_POLICY_FLEXIBLE:
        return FLEXIBLE_POSITION_OFFSET_M
    return 0.0


def build_contract_row(
    *,
    contract_index: int,
    sim_time: float,
    zoneb_algorithm: str,
    merge_policy: str,
    veh_id: str,
    vehicle_type: str = '',
    stream: str = 'unknown',
    sequence_rank: int,
    target_predecessor_id: str,
    target_follower_id: str,
    target_cross_time: float,
    merge_window_half_span_s: float,
    expected_merge_position_m_value: float,
    desired_merge_speed_mps: float,
) -> tuple[str, dict[str, str | float | int], dict[str, float | str]]:
    contract_id = f'contract_{contract_index:08d}'
    merge_window_start_s = max(sim_time, target_cross_time - merge_window_half_span_s)
    merge_window_end_s = target_cross_time + merge_window_half_span_s
    row: dict[str, str | float | int] = {
        'time': sim_time,
        'contract_id': contract_id,
        'zoneb_algorithm': zoneb_algorithm,
        'merge_policy': merge_policy,
        'ego_vehicle_id': veh_id,
        'vehicle_type': vehicle_type,
        'stream': stream,
        'sequence_rank': sequence_rank,
        'target_predecessor_id': target_predecessor_id,
        'target_follower_id': target_follower_id,
        'merge_window_start_s': merge_window_start_s,
        'merge_window_end_s': merge_window_end_s,
        'expected_merge_time_s': target_cross_time,
        'expected_merge_position_m': expected_merge_position_m_value,
        'desired_merge_speed_mps': desired_merge_speed_mps,
        'valid_until_s': merge_window_end_s,
        'fallback_policy': FALLBACK_POLICY_KEEP_LANE,
    }
    snapshot: dict[str, float | str] = {
        'expected_merge_time_s': target_cross_time,
        'expected_merge_position_m': expected_merge_position_m_value,
        'merge_window_start_s': merge_window_start_s,
        'merge_window_end_s': merge_window_end_s,
        'target_predecessor_id': target_predecessor_id,
        'target_follower_id': target_follower_id,
    }
    return contract_id, row, snapshot


def attach_actual_neighbors(
    *,
    feedback_rows: list[dict[str, str | float | int]],
    cross_feedback_indices: list[int],
) -> None:
    for index, row_index in enumerate(cross_feedback_indices):
        row = feedback_rows[row_index]
        previous_vehicle_id = ''
        next_vehicle_id = ''
        if index > 0:
            previous_vehicle_id = str(
                feedback_rows[cross_feedback_indices[index - 1]]['ego_vehicle_id']
            )
        if index + 1 < len(cross_feedback_indices):
            next_vehicle_id = str(feedback_rows[cross_feedback_indices[index + 1]]['ego_vehicle_id'])
        row['actual_predecessor_id'] = previous_vehicle_id
        row['actual_follower_id'] = next_vehicle_id


def build_contract_smoke_summary(
    *,
    contract_by_id: dict[str, dict[str, float | str]],
) -> dict[str, float | int]:
    """Validate contract completeness and generate Q2 smoke summary.

    Returns a dict with contract-level quality metrics that must be checked
    before entering the Zone C execution closed-loop.
    """
    total = len(contract_by_id)
    if total == 0:
        return {
            'total_contracts': 0,
            'field_completeness_rate': 0.0,
            'merge_window_validity_rate': 0.0,
            'target_predecessor_coverage': 0.0,
            'target_follower_coverage': 0.0,
        }
    required_snapshot_keys = (
        'expected_merge_time_s', 'expected_merge_position_m',
        'merge_window_start_s', 'merge_window_end_s',
    )
    complete_count = 0
    window_valid_count = 0
    predecessor_present_count = 0
    follower_present_count = 0
    for snapshot in contract_by_id.values():
        all_present = all(
            str(snapshot.get(k, '')).strip() != '' for k in required_snapshot_keys
        )
        if all_present:
            complete_count += 1
        start = snapshot.get('merge_window_start_s', '')
        end = snapshot.get('merge_window_end_s', '')
        if start != '' and end != '' and float(end) > float(start):
            window_valid_count += 1
        if str(snapshot.get('target_predecessor_id', '')).strip():
            predecessor_present_count += 1
        if str(snapshot.get('target_follower_id', '')).strip():
            follower_present_count += 1
    return {
        'total_contracts': total,
        'field_completeness_rate': complete_count / total,
        'merge_window_validity_rate': window_valid_count / total,
        'target_predecessor_coverage': predecessor_present_count / total,
        'target_follower_coverage': follower_present_count / total,
    }


def build_evidence_metrics(
    *,
    duration_s: float,
    controlled_cav_steps: int,
    covered_control_cav_steps: int,
    autonomous_lane_change_detected_count: int,
    speed_mismatch_detected_count: int,
    zone_a_event_count: int,
    zone_c_event_count: int,
    zone_c_chain_status: dict[str, bool],
    zone_c_chain_complete_count: int,
    contract_vehicle_ids: set[str],
    feedback_vehicle_ids: set[str],
    eligible_ramp_cav_ids: set[str] | None = None,
    feedback_rows: list[dict[str, str | float | int]],
    contract_by_id: dict[str, dict[str, float | str]],
    planned_actual_time_errors: list[float],
    planned_actual_position_errors: list[float],
) -> dict[str, float | int | dict[str, float]]:
    control_command_actual_coverage_rate = (
        covered_control_cav_steps / controlled_cav_steps if controlled_cav_steps else 0.0
    )
    autonomous_merge_leakage_rate = (
        autonomous_lane_change_detected_count / controlled_cav_steps
        if controlled_cav_steps
        else 0.0
    )
    zone_c_action_count = len(zone_c_chain_status)
    zone_c_chain_complete_effective = zone_c_chain_complete_count
    if zone_c_action_count == 0:
        zone_c_action_chain_complete_rate = 1.0
    else:
        zone_c_action_chain_complete_rate = (
            zone_c_chain_complete_effective / zone_c_action_count
        )
    contract_realization_rate = (
        len(feedback_vehicle_ids) / len(contract_vehicle_ids) if contract_vehicle_ids else 0.0
    )
    if eligible_ramp_cav_ids is not None and eligible_ramp_cav_ids:
        eligible_with_contract = eligible_ramp_cav_ids & contract_vehicle_ids
        eligible_ramp_cav_contract_rate = len(eligible_with_contract) / len(eligible_ramp_cav_ids)
    else:
        eligible_ramp_cav_contract_rate = 0.0

    merge_window_hit_count = 0
    merge_window_checked_count = 0
    predecessor_match_count = 0
    predecessor_checked_count = 0
    follower_match_count = 0
    follower_checked_count = 0
    fallback_counter: Counter[str] = Counter()
    replan_required_count = 0

    for row in feedback_rows:
        fallback_reason = str(row['fallback_reason']).strip()
        if fallback_reason:
            fallback_counter[fallback_reason] += 1
        if int(row['replan_required']) == 1:
            replan_required_count += 1
        contract_id = str(row['contract_id']).strip()
        if not contract_id:
            continue
        if contract_id not in contract_by_id:
            continue
        actual_merge_time_s = row['actual_merge_time_s']
        if actual_merge_time_s == '':
            continue

        merge_window_checked_count += 1
        contract_snapshot = contract_by_id[contract_id]
        merge_window_start_s = float(contract_snapshot['merge_window_start_s'])
        merge_window_end_s = float(contract_snapshot['merge_window_end_s'])
        if merge_window_start_s <= float(actual_merge_time_s) <= merge_window_end_s:
            merge_window_hit_count += 1

        if str(row.get('execution_state', '')) == 'merge_cross':
            target_predecessor_id = str(contract_snapshot.get('target_predecessor_id', ''))
            if target_predecessor_id:
                predecessor_checked_count += 1
                if str(row['actual_predecessor_id']) == target_predecessor_id:
                    predecessor_match_count += 1
            target_follower_id = str(contract_snapshot.get('target_follower_id', ''))
            if target_follower_id:
                follower_checked_count += 1
                if str(row['actual_follower_id']) == target_follower_id:
                    follower_match_count += 1

    merge_window_hit_rate = (
        merge_window_hit_count / merge_window_checked_count if merge_window_checked_count else 0.0
    )
    pf_total_checked = predecessor_checked_count + follower_checked_count
    pf_total_matched = predecessor_match_count + follower_match_count
    if pf_total_checked == 0:
        predecessor_follower_match_rate = 1.0
    else:
        predecessor_follower_match_rate = pf_total_matched / pf_total_checked

    fallback_rate_by_reason: dict[str, float] = {}
    for reason, count in sorted(fallback_counter.items()):
        fallback_rate_by_reason[reason] = count / len(feedback_rows) if feedback_rows else 0.0
    fallback_total_count = sum(fallback_counter.values())
    fallback_rate = fallback_total_count / len(feedback_rows) if feedback_rows else 0.0

    replan_rate = replan_required_count / len(feedback_rows) if feedback_rows else 0.0
    zone_a_event_rate = zone_a_event_count / duration_s if duration_s > 0 else 0.0
    zone_c_event_rate = zone_c_event_count / duration_s if duration_s > 0 else 0.0

    return {
        'control_command_actual_coverage_rate': control_command_actual_coverage_rate,
        'zone_c_action_chain_complete_rate': zone_c_action_chain_complete_rate,
        'autonomous_merge_leakage_rate': autonomous_merge_leakage_rate,
        'contract_realization_rate': contract_realization_rate,
        'eligible_ramp_cav_contract_rate': eligible_ramp_cav_contract_rate,
        'merge_window_hit_rate': merge_window_hit_rate,
        'predecessor_follower_match_rate': predecessor_follower_match_rate,
        'planned_actual_time_error_p50_s': percentile(planned_actual_time_errors, 0.50),
        'planned_actual_time_error_p95_s': percentile(planned_actual_time_errors, 0.95),
        'planned_actual_position_error_p50_m': percentile(planned_actual_position_errors, 0.50),
        'planned_actual_position_error_p95_m': percentile(planned_actual_position_errors, 0.95),
        'fallback_rate': fallback_rate,
        'fallback_rate_by_reason': fallback_rate_by_reason,
        'replan_rate': replan_rate,
        'zone_a_event_rate': zone_a_event_rate,
        'zone_c_event_rate': zone_c_event_rate,
        'autonomous_lane_change_anomaly_count': autonomous_lane_change_detected_count,
        'speed_mismatch_anomaly_count': speed_mismatch_detected_count,
        'zone_c_action_count': zone_c_action_count,
        'zone_c_chain_complete_count': zone_c_chain_complete_effective,
    }
