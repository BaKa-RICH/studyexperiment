from __future__ import annotations

from collections import Counter

MERGE_POLICY_FIXED = 'fixed'
MERGE_POLICY_FLEXIBLE = 'flexible'
FALLBACK_POLICY_KEEP_LANE = 'keep_lane_then_release'
SPEED_MISMATCH_THRESHOLD_MPS = 2.0
FLEXIBLE_POSITION_OFFSET_M = 20.0

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

    merge_window_hit_count = 0
    merge_window_checked_count = 0
    predecessor_match_count = 0
    predecessor_checked_count = 0
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

    merge_window_hit_rate = (
        merge_window_hit_count / merge_window_checked_count if merge_window_checked_count else 0.0
    )
    if predecessor_checked_count == 0:
        predecessor_follower_match_rate = 1.0
    else:
        predecessor_follower_match_rate = predecessor_match_count / predecessor_checked_count

    fallback_rate_by_reason: dict[str, float] = {}
    for reason, count in sorted(fallback_counter.items()):
        fallback_rate_by_reason[reason] = count / len(feedback_rows) if feedback_rows else 0.0

    replan_rate = replan_required_count / len(feedback_rows) if feedback_rows else 0.0
    zone_a_event_rate = zone_a_event_count / duration_s if duration_s > 0 else 0.0
    zone_c_event_rate = zone_c_event_count / duration_s if duration_s > 0 else 0.0

    return {
        'control_command_actual_coverage_rate': control_command_actual_coverage_rate,
        'zone_c_action_chain_complete_rate': zone_c_action_chain_complete_rate,
        'autonomous_merge_leakage_rate': autonomous_merge_leakage_rate,
        'contract_realization_rate': contract_realization_rate,
        'merge_window_hit_rate': merge_window_hit_rate,
        'predecessor_follower_match_rate': predecessor_follower_match_rate,
        'planned_actual_time_error_p50_s': percentile(planned_actual_time_errors, 0.50),
        'planned_actual_time_error_p95_s': percentile(planned_actual_time_errors, 0.95),
        'planned_actual_position_error_p50_m': percentile(planned_actual_position_errors, 0.50),
        'planned_actual_position_error_p95_m': percentile(planned_actual_position_errors, 0.95),
        'fallback_rate_by_reason': fallback_rate_by_reason,
        'replan_rate': replan_rate,
        'zone_a_event_rate': zone_a_event_rate,
        'zone_c_event_rate': zone_c_event_rate,
        'autonomous_lane_change_anomaly_count': autonomous_lane_change_detected_count,
        'speed_mismatch_anomaly_count': speed_mismatch_detected_count,
        'zone_c_action_count': zone_c_action_count,
        'zone_c_chain_complete_count': zone_c_chain_complete_effective,
    }
