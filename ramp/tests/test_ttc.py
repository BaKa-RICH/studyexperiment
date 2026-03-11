from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.runtime.ttc import build_ttc_metrics, collect_ttc_samples, summarize_ttc_samples


def _obs(
    *,
    stream: str,
    edge_id: str,
    lane_id: str,
    lane_pos: float,
    d_to_merge: float,
    speed: float,
    length: float = 5.0,
) -> dict[str, float | str]:
    return {
        'stream': stream,
        'edge_id': edge_id,
        'lane_id': lane_id,
        'lane_pos': lane_pos,
        'd_to_merge': d_to_merge,
        'speed': speed,
        'accel': 0.0,
        'length': length,
    }


def test_longitudinal_ttc_basic_closing() -> None:
    state = {
        'follower': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=10.0,
            d_to_merge=50.0,
            speed=20.0,
        ),
        'leader': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=25.0,
            d_to_merge=35.0,
            speed=10.0,
        ),
    }
    longitudinal, merge_conflict = collect_ttc_samples(ttc_observation_state=state)
    assert merge_conflict == []
    assert longitudinal == pytest.approx([1.0])


def test_longitudinal_ttc_overlap_is_zero() -> None:
    state = {
        'follower': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=10.0,
            d_to_merge=50.0,
            speed=20.0,
        ),
        'leader': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=13.0,
            d_to_merge=47.0,
            speed=10.0,
        ),
    }
    longitudinal, _ = collect_ttc_samples(ttc_observation_state=state)
    assert longitudinal == [0.0]


def test_longitudinal_ttc_non_closing_ignored() -> None:
    state = {
        'follower': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=10.0,
            d_to_merge=50.0,
            speed=10.0,
        ),
        'leader': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=25.0,
            d_to_merge=35.0,
            speed=15.0,
        ),
    }
    longitudinal, _ = collect_ttc_samples(ttc_observation_state=state)
    assert longitudinal == []


def test_merge_conflict_ttc_overlap_detected() -> None:
    state = {
        'main_veh': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=20.0,
            d_to_merge=20.0,
            speed=10.0,
        ),
        'ramp_veh': _obs(
            stream='ramp',
            edge_id='ramp_h6',
            lane_id='ramp_h6_0',
            lane_pos=15.0,
            d_to_merge=22.0,
            speed=11.0,
        ),
    }
    _, merge_conflict = collect_ttc_samples(ttc_observation_state=state)
    assert merge_conflict == pytest.approx([2.0])


def test_merge_conflict_ttc_no_overlap() -> None:
    state = {
        'main_veh': _obs(
            stream='main',
            edge_id='main_h2',
            lane_id='main_h2_0',
            lane_pos=20.0,
            d_to_merge=20.0,
            speed=10.0,
        ),
        'ramp_veh': _obs(
            stream='ramp',
            edge_id='ramp_h6',
            lane_id='ramp_h6_0',
            lane_pos=15.0,
            d_to_merge=80.0,
            speed=10.0,
        ),
    }
    _, merge_conflict = collect_ttc_samples(ttc_observation_state=state)
    assert merge_conflict == []


def test_summarize_ttc_samples_empty() -> None:
    stats = summarize_ttc_samples(samples=[], step_length_s=0.1)
    assert stats.min_s is None
    assert stats.p05_s is None
    assert stats.sample_count == 0
    assert stats.lt_3_0s_ratio is None
    assert stats.lt_1_5s_ratio is None


def test_build_ttc_metrics_core_fields() -> None:
    metrics = build_ttc_metrics(
        longitudinal_samples=[1.0, 2.0, 4.0],
        merge_conflict_samples=[0.5],
        step_length_s=0.1,
    )
    assert metrics['ttc_longitudinal_min_s'] == pytest.approx(1.0)
    assert metrics['ttc_longitudinal_p05_s'] == pytest.approx(1.0)
    assert metrics['ttc_longitudinal_lt_3_0s_count'] == 2
    assert metrics['ttc_longitudinal_lt_1_5s_count'] == 1
    assert metrics['ttc_merge_conflict_min_s'] == pytest.approx(0.5)
    assert metrics['ttc_any_sample_count'] == 4
    assert metrics['ttc_any_lt_3_0s_count'] == 3


def test_summarize_ttc_samples_invalid_step() -> None:
    with pytest.raises(ValueError):
        summarize_ttc_samples(samples=[1.0], step_length_s=0.0)
