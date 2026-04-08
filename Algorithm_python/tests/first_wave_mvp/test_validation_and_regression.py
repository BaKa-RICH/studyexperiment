from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
EXPERIMENTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "first_wave_mvp"
for path in (SRC_ROOT, EXPERIMENTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from regression_gate import (  # noqa: E402
    MIN_SEED_COUNT,
    evaluate_cav_penetration_and_scope_ablation,
    evaluate_light_load_correctness,
    evaluate_medium_high_load_competition,
)


def test_light_load_gate_pass(light_load_pass_results) -> None:
    result = evaluate_light_load_correctness(light_load_pass_results)

    assert result.passed is True
    assert result.failures == ()
    assert result.summaries[0].seed_count == 3


def test_light_load_gate_fail_reports_experiment_metric_and_seed(light_load_fail_results) -> None:
    result = evaluate_light_load_correctness(light_load_fail_results)

    assert result.passed is False
    failure = result.failures[0]
    assert failure.experiment_id == "light_load_correctness"
    assert failure.metric == "planned_actual_time_error_p95_s"
    assert set(failure.violating_seeds) == {42, 123, 999}


def test_light_load_gate_fails_when_seed_count_too_low(too_few_seed_results) -> None:
    result = evaluate_light_load_correctness(too_few_seed_results)

    assert result.passed is False
    assert result.failures[0].metric == "seed_count"
    assert str(MIN_SEED_COUNT) in result.failures[0].message


def test_light_load_gate_fails_on_failed_seed_before_performance_checks(failed_seed_results) -> None:
    result = evaluate_light_load_correctness(failed_seed_results)

    assert result.passed is False
    assert result.failures[0].metric == "failed_seed"
    assert 123 in result.failures[0].violating_seeds


def test_medium_high_load_gate_pass(
    medium_high_load_fixed_results,
    medium_high_load_flexible_results,
) -> None:
    result = evaluate_medium_high_load_competition(
        fixed_results=medium_high_load_fixed_results,
        flexible_results=medium_high_load_flexible_results,
    )

    assert result.passed is True
    assert result.failures == ()
    assert len(result.summaries) == 2


def test_medium_high_load_gate_fails_on_seed_alignment(
    medium_high_load_fixed_results,
    medium_high_load_misaligned_flexible_results,
) -> None:
    result = evaluate_medium_high_load_competition(
        fixed_results=medium_high_load_fixed_results,
        flexible_results=medium_high_load_misaligned_flexible_results,
    )

    assert result.passed is False
    assert result.failures[0].metric == "seed_alignment"
    assert result.failures[0].comparison_target == "fifo_fixed_anchor vs fifo_flexible_anchor"


def test_ablation_gate_pass(ablation_pass_results_by_config) -> None:
    result = evaluate_cav_penetration_and_scope_ablation(
        results_by_config=ablation_pass_results_by_config,
        baseline_config_key="low_penetration_minimal_scope",
        enhanced_config_key="full_cav_expanded_scope",
    )

    assert result.passed is True
    assert result.failures == ()
    assert len(result.summaries) == 2


def test_ablation_gate_fails_when_enhanced_endpoint_is_worse(ablation_fail_results_by_config) -> None:
    result = evaluate_cav_penetration_and_scope_ablation(
        results_by_config=ablation_fail_results_by_config,
        baseline_config_key="low_penetration_minimal_scope",
        enhanced_config_key="full_cav_expanded_scope",
    )

    assert result.passed is False
    assert result.failures[0].experiment_id == "cav_penetration_and_scope_ablation"
    assert result.failures[0].comparison_target == "low_penetration_minimal_scope"
