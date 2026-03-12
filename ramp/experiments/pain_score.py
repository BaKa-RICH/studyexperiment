"""PainScore: composite metric quantifying HDV-induced control-system stress.

The score measures how much a given HDV world (H1) degrades key safety
and performance indicators relative to a baseline world (H0).

Formula (Gemini-proposed, adopted via VOTE):
    PainScore(H1) = Σ [ w_i * (I_i(H1) - I_i(H0)) / max(I_i(H0), ε) ]

Where:
    I_i  = one of 5 Pain indicators
    w_i  = normalised weight for indicator i
    ε    = floor constant preventing division-by-zero

A positive PainScore means H1 is *worse* (more painful) than H0.
Gate 3 requires at least one H1 with PainScore >= 0.25 (25% degradation).
"""

from __future__ import annotations

from typing import Any

PAIN_EPSILON: float = 0.001

PAIN_INDICATORS: tuple[str, ...] = (
    'ttc_any_lt_3_0s_ratio',
    'merge_conflict_exposure',
    'cutoff_residual_ratio',
    'fallback_rate',
    'replan_rate',
)

PAIN_WEIGHTS: dict[str, float] = {
    'ttc_any_lt_3_0s_ratio': 0.30,
    'merge_conflict_exposure': 0.25,
    'cutoff_residual_ratio': 0.15,
    'fallback_rate': 0.15,
    'replan_rate': 0.15,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce *value* to float; return *default* for None / non-numeric."""
    if value is None:
        return default
    return float(value)


def extract_pain_indicators(metrics: dict[str, Any]) -> dict[str, float]:
    """Extract the 5 Pain indicators from a metrics dict.

    ``merge_conflict_exposure`` is normalised by simulation duration.
    ``cutoff_residual_ratio`` = pending_unfinished / entered_control.
    """
    duration_s = _safe_float(metrics.get('duration_s'), default=1.0)
    entered = _safe_float(metrics.get('entered_control_count'), default=1.0)

    raw_exposure = _safe_float(
        metrics.get('ttc_merge_conflict_sample_exposure_s'), default=0.0
    )
    merge_conflict_exposure = raw_exposure / max(duration_s, PAIN_EPSILON)

    pending = _safe_float(metrics.get('pending_unfinished_count'), default=0.0)
    cutoff_residual_ratio = pending / max(entered, PAIN_EPSILON)

    return {
        'ttc_any_lt_3_0s_ratio': _safe_float(
            metrics.get('ttc_any_lt_3_0s_ratio'), default=0.0
        ),
        'merge_conflict_exposure': merge_conflict_exposure,
        'cutoff_residual_ratio': cutoff_residual_ratio,
        'fallback_rate': _safe_float(
            metrics.get('fallback_rate'), default=0.0
        ),
        'replan_rate': _safe_float(
            metrics.get('replan_rate'), default=0.0
        ),
    }


def compute_pain_score(
    h1_indicators: dict[str, float],
    h0_indicators: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Return the weighted-average relative degradation of H1 vs H0.

    Returns a float >= 0 when H1 is worse than H0.
    """
    w = weights or PAIN_WEIGHTS
    score = 0.0
    for name in PAIN_INDICATORS:
        i_h1 = h1_indicators.get(name, 0.0)
        i_h0 = h0_indicators.get(name, 0.0)
        denom = max(abs(i_h0), PAIN_EPSILON)
        score += w.get(name, 0.0) * (i_h1 - i_h0) / denom
    return score


def compute_pain_score_from_metrics(
    h1_metrics: dict[str, Any],
    h0_metrics: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: extract indicators then compute PainScore.

    Returns a dict with per-indicator values, deltas, and the final score.
    """
    h1 = extract_pain_indicators(h1_metrics)
    h0 = extract_pain_indicators(h0_metrics)
    score = compute_pain_score(h1, h0, weights)
    w = weights or PAIN_WEIGHTS

    breakdown: dict[str, Any] = {}
    for name in PAIN_INDICATORS:
        i_h1 = h1[name]
        i_h0 = h0[name]
        denom = max(abs(i_h0), PAIN_EPSILON)
        rel_change = (i_h1 - i_h0) / denom
        breakdown[name] = {
            'h0': i_h0,
            'h1': i_h1,
            'rel_change': rel_change,
            'weighted_contribution': w.get(name, 0.0) * rel_change,
        }

    return {
        'pain_score': score,
        'h0_indicators': h0,
        'h1_indicators': h1,
        'breakdown': breakdown,
    }
