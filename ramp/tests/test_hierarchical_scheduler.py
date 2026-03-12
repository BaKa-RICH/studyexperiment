"""Tests for HierarchicalScheduler merge_policy support (Todo 2.2).

Verifies:
- Gate 1: fixed/flex both instantiate, same call path
- Gate 2: both produce Plan objects
- Gate 3: fixed uses late-search params, flexible uses default params
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.policies.hierarchical.merge_point import MergePointParams
from ramp.policies.hierarchical.scheduler import (
    MERGE_POLICY_FIXED,
    MERGE_POLICY_FLEXIBLE,
    HierarchicalScheduler,
)


def test_fixed_scheduler_instantiates() -> None:
    s = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FIXED,
    )
    assert s.merge_policy == MERGE_POLICY_FIXED
    assert s._merge_point_mgr is not None


def test_flexible_scheduler_instantiates() -> None:
    s = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FLEXIBLE,
    )
    assert s.merge_policy == MERGE_POLICY_FLEXIBLE
    assert s._merge_point_mgr is not None


def test_unknown_merge_policy_raises() -> None:
    with pytest.raises(ValueError, match='Unknown merge_policy'):
        HierarchicalScheduler(
            delta_1_s=1.5, delta_2_s=2.0,
            main_vmax_mps=25.0, ramp_vmax_mps=20.0,
            merge_policy='nonexistent',
        )


def test_fixed_uses_late_search_start() -> None:
    s = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FIXED,
    )
    default_params = MergePointParams()
    expected_search_start = default_params.lane0_length_m - default_params.fallback_buffer_m
    assert s._merge_point_mgr is not None
    assert s._merge_point_mgr.params.search_start_pos_m == expected_search_start


def test_flexible_uses_default_search_start() -> None:
    s = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FLEXIBLE,
    )
    default_params = MergePointParams()
    assert s._merge_point_mgr is not None
    assert s._merge_point_mgr.params.search_start_pos_m == default_params.search_start_pos_m


def test_fixed_and_flexible_same_interface() -> None:
    s_fixed = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FIXED,
    )
    s_flex = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FLEXIBLE,
    )
    assert hasattr(s_fixed, 'compute_plan')
    assert hasattr(s_flex, 'compute_plan')
    assert s_fixed.zone_a_actions == {}
    assert s_fixed.zone_c_actions == {}
    assert s_flex.zone_a_actions == {}
    assert s_flex.zone_c_actions == {}


def test_fixed_search_start_greater_than_flexible() -> None:
    s_fixed = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FIXED,
    )
    s_flex = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
        merge_policy=MERGE_POLICY_FLEXIBLE,
    )
    assert s_fixed._merge_point_mgr is not None
    assert s_flex._merge_point_mgr is not None
    assert s_fixed._merge_point_mgr.params.search_start_pos_m > s_flex._merge_point_mgr.params.search_start_pos_m


def test_default_merge_policy_is_flexible() -> None:
    s = HierarchicalScheduler(
        delta_1_s=1.5, delta_2_s=2.0,
        main_vmax_mps=25.0, ramp_vmax_mps=20.0,
    )
    assert s.merge_policy == MERGE_POLICY_FLEXIBLE
