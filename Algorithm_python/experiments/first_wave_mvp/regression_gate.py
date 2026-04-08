"""第一波 MVP 的回归门禁。"""

from __future__ import annotations

from dataclasses import dataclass

from common import PerSeedResult
from first_wave_mvp.metrics import aggregate_stats_view, aggregate_to_summary
from first_wave_mvp.types import ExperimentResultSummary


MIN_SEED_COUNT = 3


@dataclass(frozen=True, slots=True)
class RegressionFailure:
    experiment_id: str
    metric: str
    violating_seeds: tuple[int, ...]
    message: str
    comparison_target: str | None = None


@dataclass(frozen=True, slots=True)
class RegressionResult:
    experiment_id: str
    passed: bool
    failures: tuple[RegressionFailure, ...]
    summaries: tuple[ExperimentResultSummary, ...]


def _seed_tuple(per_seed_results: list[PerSeedResult] | tuple[PerSeedResult, ...]) -> tuple[int, ...]:
    return tuple(sorted(result.seed for result in per_seed_results))


def _make_failure(
    *,
    experiment_id: str,
    metric: str,
    violating_seeds: tuple[int, ...],
    message: str,
    comparison_target: str | None = None,
) -> RegressionFailure:
    return RegressionFailure(
        experiment_id=experiment_id,
        metric=metric,
        violating_seeds=violating_seeds,
        message=message,
        comparison_target=comparison_target,
    )


def _safe_summary(
    per_seed_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
) -> tuple[ExperimentResultSummary, ...]:
    try:
        return (aggregate_to_summary(per_seed_results),)
    except ValueError:
        return ()


def _require_min_seed_count(
    experiment_id: str,
    per_seed_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
) -> list[RegressionFailure]:
    if len(per_seed_results) < MIN_SEED_COUNT:
        return [
            _make_failure(
                experiment_id=experiment_id,
                metric="seed_count",
                violating_seeds=_seed_tuple(per_seed_results),
                message=f"N_seed must be >= {MIN_SEED_COUNT}",
            )
        ]
    return []


def _all_seed_safety_failures(
    experiment_id: str,
    per_seed_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
) -> list[RegressionFailure]:
    failures: list[RegressionFailure] = []

    failed_seed_ids = tuple(sorted(result.seed for result in per_seed_results if result.failed))
    if failed_seed_ids:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="failed_seed",
                violating_seeds=failed_seed_ids,
                message="failed seeds are not allowed in all-seed safety checks",
            )
        )

    collision_seed_ids = tuple(
        sorted(result.seed for result in per_seed_results if not result.failed and (result.collision_count or 0) > 0)
    )
    if collision_seed_ids:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="collision_count",
                violating_seeds=collision_seed_ids,
                message="collision_count must be 0 for every seed",
            )
        )

    safety_seed_ids = tuple(
        sorted(
            result.seed
            for result in per_seed_results
            if not result.failed and (result.safety_violation_count or 0) > 0
        )
    )
    if safety_seed_ids:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="safety_violation_count",
                violating_seeds=safety_seed_ids,
                message="safety_violation_count must be 0 for every seed",
            )
        )

    return failures


def evaluate_light_load_correctness(
    per_seed_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
) -> RegressionResult:
    experiment_id = "light_load_correctness"
    failures = _require_min_seed_count(experiment_id, per_seed_results)
    failures.extend(_all_seed_safety_failures(experiment_id, per_seed_results))

    if not failures:
        stats = aggregate_stats_view(per_seed_results)
        if stats["completion_rate_worst_seed"] < 1.0:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="completion_rate",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message="completion_rate must be 100% for every seed",
                )
            )
        if stats["abort_rate_worst_seed"] > 0.0:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="abort_rate",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message="abort_rate must be 0 for every seed",
                )
            )
        if stats.get("planned_actual_time_error_p95_s_worst_seed", 0.0) > 0.1:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="planned_actual_time_error_p95_s",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message="planned_actual_time_error_p95_s must be <= 0.1",
                )
            )
        if stats.get("planned_actual_position_error_p95_m_worst_seed", 0.0) > 1.0:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="planned_actual_position_error_p95_m",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message="planned_actual_position_error_p95_m must be <= 1.0",
                )
            )

    return RegressionResult(
        experiment_id=experiment_id,
        passed=not failures,
        failures=tuple(failures),
        summaries=_safe_summary(per_seed_results),
    )


def evaluate_medium_high_load_competition(
    *,
    fixed_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
    flexible_results: list[PerSeedResult] | tuple[PerSeedResult, ...],
) -> RegressionResult:
    experiment_id = "medium_high_load_competition"
    failures = []
    failures.extend(_require_min_seed_count(experiment_id, fixed_results))
    failures.extend(_require_min_seed_count(experiment_id, flexible_results))
    failures.extend(_all_seed_safety_failures(experiment_id, fixed_results))
    failures.extend(_all_seed_safety_failures(experiment_id, flexible_results))

    fixed_seeds = _seed_tuple(fixed_results)
    flexible_seeds = _seed_tuple(flexible_results)
    if fixed_seeds != flexible_seeds:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="seed_alignment",
                violating_seeds=flexible_seeds,
                message="fixed and flexible results must share the same seed set",
                comparison_target="fifo_fixed_anchor vs fifo_flexible_anchor",
            )
        )

    fixed_stats = aggregate_stats_view(fixed_results)
    flexible_stats = aggregate_stats_view(flexible_results)

    if flexible_stats["abort_rate_mean"] > fixed_stats["abort_rate_mean"]:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="abort_rate_mean",
                violating_seeds=flexible_seeds,
                message="flexible abort_rate_mean must be <= fixed abort_rate_mean",
                comparison_target="fifo_fixed_anchor",
            )
        )
    if flexible_stats["avg_ramp_delay_s_mean"] > fixed_stats["avg_ramp_delay_s_mean"]:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="avg_ramp_delay_s_mean",
                violating_seeds=flexible_seeds,
                message="flexible avg_ramp_delay_s_mean must be <= fixed avg_ramp_delay_s_mean",
                comparison_target="fifo_fixed_anchor",
            )
        )
    if flexible_stats["throughput_vph_mean"] < fixed_stats["throughput_vph_mean"]:
        failures.append(
            _make_failure(
                experiment_id=experiment_id,
                metric="throughput_vph_mean",
                violating_seeds=flexible_seeds,
                message="flexible throughput_vph_mean must be >= fixed throughput_vph_mean",
                comparison_target="fifo_fixed_anchor",
            )
        )

    return RegressionResult(
        experiment_id=experiment_id,
        passed=not failures,
        failures=tuple(failures),
        summaries=_safe_summary(fixed_results) + _safe_summary(flexible_results),
    )


def evaluate_cav_penetration_and_scope_ablation(
    *,
    results_by_config: dict[str, list[PerSeedResult] | tuple[PerSeedResult, ...]],
    baseline_config_key: str,
    enhanced_config_key: str,
) -> RegressionResult:
    experiment_id = "cav_penetration_and_scope_ablation"
    failures: list[RegressionFailure] = []
    summaries: list[ExperimentResultSummary] = []

    for config_key, per_seed_results in results_by_config.items():
        failures.extend(_require_min_seed_count(experiment_id, per_seed_results))
        failures.extend(_all_seed_safety_failures(experiment_id, per_seed_results))

        stats = aggregate_stats_view(per_seed_results)
        if stats["completion_rate_worst_seed"] < 0.95:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="completion_rate_worst_seed",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message=f"{config_key} completion_rate must be >= 95% for every seed",
                    comparison_target=config_key,
                )
            )
        if stats["abort_rate_worst_seed"] > 0.05:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric="abort_rate_worst_seed",
                    violating_seeds=_seed_tuple(per_seed_results),
                    message=f"{config_key} abort_rate must be <= 5% for every seed",
                    comparison_target=config_key,
                )
            )

        try:
            summaries.append(aggregate_to_summary(per_seed_results))
        except ValueError:
            pass

    baseline_stats = aggregate_stats_view(results_by_config[baseline_config_key])
    enhanced_stats = aggregate_stats_view(results_by_config[enhanced_config_key])
    enhanced_seeds = _seed_tuple(results_by_config[enhanced_config_key])

    comparisons = (
        ("completion_rate_mean", enhanced_stats["completion_rate_mean"] >= baseline_stats["completion_rate_mean"]),
        ("abort_rate_mean", enhanced_stats["abort_rate_mean"] <= baseline_stats["abort_rate_mean"]),
        ("throughput_vph_mean", enhanced_stats["throughput_vph_mean"] >= baseline_stats["throughput_vph_mean"]),
        ("avg_ramp_delay_s_mean", enhanced_stats["avg_ramp_delay_s_mean"] <= baseline_stats["avg_ramp_delay_s_mean"]),
    )
    for metric, passed in comparisons:
        if not passed:
            failures.append(
                _make_failure(
                    experiment_id=experiment_id,
                    metric=metric,
                    violating_seeds=enhanced_seeds,
                    message=f"{enhanced_config_key} must not be worse than {baseline_config_key} on {metric}",
                    comparison_target=baseline_config_key,
                )
            )

    return RegressionResult(
        experiment_id=experiment_id,
        passed=not failures,
        failures=tuple(failures),
        summaries=tuple(summaries),
    )


__all__ = [
    "MIN_SEED_COUNT",
    "RegressionFailure",
    "RegressionResult",
    "evaluate_cav_penetration_and_scope_ablation",
    "evaluate_light_load_correctness",
    "evaluate_medium_high_load_competition",
]
