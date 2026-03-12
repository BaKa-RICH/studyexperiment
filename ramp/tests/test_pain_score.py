"""Tests for ramp.experiments.pain_score."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ramp.experiments.pain_score import (
    PAIN_EPSILON,
    PAIN_INDICATORS,
    PAIN_WEIGHTS,
    compute_pain_score,
    compute_pain_score_from_metrics,
    extract_pain_indicators,
)


def _make_metrics(**overrides) -> dict:
    base = {
        'ttc_any_lt_3_0s_ratio': 0.1,
        'ttc_merge_conflict_sample_exposure_s': 5.0,
        'duration_s': 300.0,
        'entered_control_count': 50,
        'pending_unfinished_count': 5,
        'fallback_rate': 0.05,
        'replan_rate': 0.1,
    }
    base.update(overrides)
    return base


def test_extract_pain_indicators_basic():
    m = _make_metrics()
    ind = extract_pain_indicators(m)
    assert set(ind.keys()) == set(PAIN_INDICATORS)
    assert abs(ind['ttc_any_lt_3_0s_ratio'] - 0.1) < 1e-9
    assert abs(ind['merge_conflict_exposure'] - 5.0 / 300.0) < 1e-9
    assert abs(ind['cutoff_residual_ratio'] - 5.0 / 50.0) < 1e-9
    assert abs(ind['fallback_rate'] - 0.05) < 1e-9
    assert abs(ind['replan_rate'] - 0.1) < 1e-9


def test_extract_pain_indicators_none_handling():
    m = _make_metrics(ttc_any_lt_3_0s_ratio=None, fallback_rate=None)
    ind = extract_pain_indicators(m)
    assert ind['ttc_any_lt_3_0s_ratio'] == 0.0
    assert ind['fallback_rate'] == 0.0


def test_extract_pain_indicators_zero_entered():
    m = _make_metrics(entered_control_count=0)
    ind = extract_pain_indicators(m)
    assert ind['cutoff_residual_ratio'] >= 0.0


def test_compute_pain_score_identical_worlds():
    h0 = {name: 0.1 for name in PAIN_INDICATORS}
    score = compute_pain_score(h0, h0)
    assert abs(score) < 1e-9


def test_compute_pain_score_h1_worse():
    h0 = {name: 0.1 for name in PAIN_INDICATORS}
    h1 = {name: 0.2 for name in PAIN_INDICATORS}
    score = compute_pain_score(h1, h0)
    assert score > 0.0
    expected = sum(PAIN_WEIGHTS.values()) * (0.2 - 0.1) / 0.1
    assert abs(score - expected) < 1e-9


def test_compute_pain_score_h0_zero_indicators():
    h0 = {name: 0.0 for name in PAIN_INDICATORS}
    h1 = {name: 0.05 for name in PAIN_INDICATORS}
    score = compute_pain_score(h1, h0)
    assert score > 0.0


def test_compute_pain_score_from_metrics_basic():
    h0_m = _make_metrics()
    h1_m = _make_metrics(
        ttc_any_lt_3_0s_ratio=0.2,
        fallback_rate=0.15,
        replan_rate=0.2,
    )
    result = compute_pain_score_from_metrics(h1_m, h0_m)
    assert 'pain_score' in result
    assert 'breakdown' in result
    assert result['pain_score'] > 0.0


def test_pain_weights_sum_to_one():
    total = sum(PAIN_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9


def test_pain_indicators_match_weights():
    assert set(PAIN_INDICATORS) == set(PAIN_WEIGHTS.keys())


def test_gate3_threshold():
    """If all indicators double, PainScore should be 100% (well above 25%)."""
    h0 = {name: 0.1 for name in PAIN_INDICATORS}
    h1 = {name: 0.2 for name in PAIN_INDICATORS}
    score = compute_pain_score(h1, h0)
    assert score >= 0.25
