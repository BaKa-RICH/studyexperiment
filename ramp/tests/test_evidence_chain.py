from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from ramp.experiments.evidence_chain import (
    ANCHOR_EVENT_CROSS_MERGE,
    ANCHOR_EVENT_CROSS_MERGE_FALLBACK,
    ANCHOR_EVENT_LC_COMPLETE,
    CONTRACT_FIELDS,
    FEEDBACK_FIELDS,
    MERGE_POLICY_FIXED,
    MERGE_POLICY_FLEXIBLE,
    attach_actual_neighbors,
    build_contract_row,
    build_evidence_metrics,
    expected_merge_position_m,
    merge_window_half_span_s,
    resolve_anchor_event_type,
    resolve_merge_policy,
)


def test_resolve_merge_policy() -> None:
    assert resolve_merge_policy(policy='fifo', policy_variant='enhanced_fixed') == MERGE_POLICY_FIXED
    assert resolve_merge_policy(policy='dp', policy_variant='enhanced_flex') == MERGE_POLICY_FLEXIBLE
    assert resolve_merge_policy(policy='hierarchical', policy_variant='proposed_full') == MERGE_POLICY_FLEXIBLE


def test_build_contract_row_fields() -> None:
    contract_id, row, snapshot = build_contract_row(
        contract_index=3,
        sim_time=10.0,
        zoneb_algorithm='dp',
        merge_policy=MERGE_POLICY_FIXED,
        veh_id='veh_1',
        sequence_rank=2,
        target_predecessor_id='veh_prev',
        target_follower_id='veh_next',
        target_cross_time=20.0,
        merge_window_half_span_s=2.0,
        expected_merge_position_m_value=300.0,
        desired_merge_speed_mps=12.5,
    )
    assert contract_id == 'contract_00000003'
    assert row['fallback_policy'] == 'keep_lane_then_release'
    assert row['merge_window_start_s'] == 18.0
    assert row['merge_window_end_s'] == 22.0
    assert snapshot['target_predecessor_id'] == 'veh_prev'


def test_attach_actual_neighbors() -> None:
    feedback_rows = [
        {'ego_vehicle_id': 'a', 'actual_predecessor_id': '', 'actual_follower_id': ''},
        {'ego_vehicle_id': 'b', 'actual_predecessor_id': '', 'actual_follower_id': ''},
        {'ego_vehicle_id': 'c', 'actual_predecessor_id': '', 'actual_follower_id': ''},
    ]
    attach_actual_neighbors(feedback_rows=feedback_rows, cross_feedback_indices=[0, 1, 2])
    assert feedback_rows[0]['actual_predecessor_id'] == ''
    assert feedback_rows[0]['actual_follower_id'] == 'b'
    assert feedback_rows[1]['actual_predecessor_id'] == 'a'
    assert feedback_rows[1]['actual_follower_id'] == 'c'
    assert feedback_rows[2]['actual_predecessor_id'] == 'b'
    assert feedback_rows[2]['actual_follower_id'] == ''


def test_build_evidence_metrics_core_rates() -> None:
    feedback_rows = [
        {
            'contract_id': 'contract_00000001',
            'execution_state': 'merge_cross',
            'actual_merge_time_s': 12.0,
            'actual_predecessor_id': 'veh_prev',
            'fallback_reason': '',
            'replan_required': 0,
        },
        {
            'contract_id': 'contract_00000002',
            'execution_state': 'merge_cross',
            'actual_merge_time_s': 20.0,
            'actual_predecessor_id': '',
            'fallback_reason': 'zone_c_chain_incomplete',
            'replan_required': 1,
        },
    ]
    contract_by_id = {
        'contract_00000001': {
            'merge_window_start_s': 10.0,
            'merge_window_end_s': 14.0,
            'target_predecessor_id': 'veh_prev',
        },
        'contract_00000002': {
            'merge_window_start_s': 13.0,
            'merge_window_end_s': 16.0,
            'target_predecessor_id': '',
        },
    }
    metrics = build_evidence_metrics(
        duration_s=120.0,
        controlled_cav_steps=10,
        covered_control_cav_steps=10,
        autonomous_lane_change_detected_count=1,
        speed_mismatch_detected_count=2,
        zone_a_event_count=6,
        zone_c_event_count=12,
        zone_c_chain_status={'veh_1': True, 'veh_2': False},
        zone_c_chain_complete_count=1,
        contract_vehicle_ids={'veh_1', 'veh_2', 'veh_3'},
        feedback_vehicle_ids={'veh_1', 'veh_2'},
        feedback_rows=feedback_rows,
        contract_by_id=contract_by_id,
        planned_actual_time_errors=[0.2, 0.8],
        planned_actual_position_errors=[1.0, 3.0],
    )
    assert metrics['control_command_actual_coverage_rate'] == 1.0
    assert metrics['merge_window_hit_rate'] == 0.5
    assert metrics['predecessor_follower_match_rate'] == 1.0
    assert metrics['replan_rate'] == 0.5


def test_expected_merge_position_m() -> None:
    assert expected_merge_position_m(
        merge_policy=MERGE_POLICY_FIXED,
    ) == 0.0
    assert expected_merge_position_m(
        merge_policy=MERGE_POLICY_FLEXIBLE,
    ) == 20.0


def test_merge_window_half_span_s() -> None:
    assert merge_window_half_span_s(
        policy='fifo',
        step_length_s=0.1,
        fifo_gap_s=1.5,
        delta_1_s=1.5,
        delta_2_s=2.0,
    ) == 1.5
    assert merge_window_half_span_s(
        policy='dp',
        step_length_s=0.1,
        fifo_gap_s=1.5,
        delta_1_s=1.5,
        delta_2_s=2.0,
    ) == 2.0


def test_resolve_anchor_event_type_fixed() -> None:
    assert resolve_anchor_event_type(merge_policy=MERGE_POLICY_FIXED) == ANCHOR_EVENT_CROSS_MERGE


def test_resolve_anchor_event_type_flexible() -> None:
    assert resolve_anchor_event_type(merge_policy=MERGE_POLICY_FLEXIBLE) == ANCHOR_EVENT_LC_COMPLETE


def test_resolve_anchor_event_type_unknown_raises() -> None:
    with pytest.raises(ValueError, match='Unknown merge_policy'):
        resolve_anchor_event_type(merge_policy='nonexistent')


def test_contract_fields_include_stream() -> None:
    assert 'stream' in CONTRACT_FIELDS
    assert 'vehicle_type' in CONTRACT_FIELDS


def test_feedback_fields_include_stream_and_anchor() -> None:
    assert 'stream' in FEEDBACK_FIELDS
    assert 'anchor_event_type' in FEEDBACK_FIELDS


def test_build_contract_row_includes_stream() -> None:
    _, row, _ = build_contract_row(
        contract_index=1,
        sim_time=5.0,
        zoneb_algorithm='fifo',
        merge_policy=MERGE_POLICY_FIXED,
        veh_id='veh_1',
        stream='ramp',
        sequence_rank=1,
        target_predecessor_id='',
        target_follower_id='veh_2',
        target_cross_time=15.0,
        merge_window_half_span_s=1.5,
        expected_merge_position_m_value=0.0,
        desired_merge_speed_mps=10.0,
    )
    assert row['stream'] == 'ramp'


def test_build_contract_row_stream_defaults_to_unknown() -> None:
    _, row, _ = build_contract_row(
        contract_index=1,
        sim_time=5.0,
        zoneb_algorithm='dp',
        merge_policy=MERGE_POLICY_FLEXIBLE,
        veh_id='veh_x',
        sequence_rank=1,
        target_predecessor_id='',
        target_follower_id='',
        target_cross_time=15.0,
        merge_window_half_span_s=2.0,
        expected_merge_position_m_value=20.0,
        desired_merge_speed_mps=8.0,
    )
    assert row['stream'] == 'unknown'


def test_contract_schema_same_for_fixed_and_flexible() -> None:
    _, row_fixed, _ = build_contract_row(
        contract_index=1,
        sim_time=5.0,
        zoneb_algorithm='fifo',
        merge_policy=MERGE_POLICY_FIXED,
        veh_id='veh_1',
        stream='ramp',
        sequence_rank=1,
        target_predecessor_id='',
        target_follower_id='',
        target_cross_time=15.0,
        merge_window_half_span_s=1.5,
        expected_merge_position_m_value=0.0,
        desired_merge_speed_mps=10.0,
    )
    _, row_flex, _ = build_contract_row(
        contract_index=2,
        sim_time=5.0,
        zoneb_algorithm='hierarchical',
        merge_policy=MERGE_POLICY_FLEXIBLE,
        veh_id='veh_2',
        stream='ramp',
        sequence_rank=1,
        target_predecessor_id='',
        target_follower_id='',
        target_cross_time=15.0,
        merge_window_half_span_s=2.0,
        expected_merge_position_m_value=20.0,
        desired_merge_speed_mps=8.0,
    )
    assert set(row_fixed.keys()) == set(row_flex.keys())
    assert isinstance(row_fixed['expected_merge_position_m'], float)
    assert isinstance(row_flex['expected_merge_position_m'], float)


def test_eligible_ramp_cav_contract_rate() -> None:
    metrics = build_evidence_metrics(
        duration_s=120.0,
        controlled_cav_steps=10,
        covered_control_cav_steps=10,
        autonomous_lane_change_detected_count=0,
        speed_mismatch_detected_count=0,
        zone_a_event_count=0,
        zone_c_event_count=0,
        zone_c_chain_status={},
        zone_c_chain_complete_count=0,
        contract_vehicle_ids={'ramp_cav_1', 'ramp_cav_2', 'main_cav_3'},
        feedback_vehicle_ids={'ramp_cav_1'},
        eligible_ramp_cav_ids={'ramp_cav_1', 'ramp_cav_2', 'ramp_cav_3'},
        feedback_rows=[],
        contract_by_id={},
        planned_actual_time_errors=[],
        planned_actual_position_errors=[],
    )
    assert abs(metrics['eligible_ramp_cav_contract_rate'] - 2.0 / 3.0) < 1e-9


def test_eligible_ramp_cav_contract_rate_none() -> None:
    metrics = build_evidence_metrics(
        duration_s=120.0,
        controlled_cav_steps=10,
        covered_control_cav_steps=10,
        autonomous_lane_change_detected_count=0,
        speed_mismatch_detected_count=0,
        zone_a_event_count=0,
        zone_c_event_count=0,
        zone_c_chain_status={},
        zone_c_chain_complete_count=0,
        contract_vehicle_ids={'a'},
        feedback_vehicle_ids=set(),
        eligible_ramp_cav_ids=None,
        feedback_rows=[],
        contract_by_id={},
        planned_actual_time_errors=[],
        planned_actual_position_errors=[],
    )
    assert metrics['eligible_ramp_cav_contract_rate'] == 0.0


def test_anchor_event_constants() -> None:
    assert ANCHOR_EVENT_CROSS_MERGE == 'cross_merge'
    assert ANCHOR_EVENT_LC_COMPLETE == 'lc_complete'
    assert ANCHOR_EVENT_CROSS_MERGE_FALLBACK == 'cross_merge_fallback'
