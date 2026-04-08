"""第一波 MVP 实验结果聚合。"""

from __future__ import annotations

from math import ceil
from typing import Protocol, Sequence

from first_wave_mvp.types import ExperimentResultSummary


_METRIC_FIELDS = (
    "completion_rate",
    "abort_rate",
    "collision_count",
    "safety_violation_count",
    "avg_ramp_delay_s",
    "throughput_vph",
    "planned_actual_time_error_p95_s",
    "planned_actual_position_error_p95_m",
)

_WORST_DIRECTION = {
    "completion_rate": "min",
    "abort_rate": "max",
    "collision_count": "max",
    "safety_violation_count": "max",
    "avg_ramp_delay_s": "max",
    "throughput_vph": "min",
    "planned_actual_time_error_p95_s": "max",
    "planned_actual_position_error_p95_m": "max",
}


class PerSeedResultLike(Protocol):
    experiment_id: str
    policy_tag: object
    seed: int
    completion_rate: float | None
    abort_rate: float | None
    collision_count: int | None
    safety_violation_count: int | None
    avg_ramp_delay_s: float | None
    throughput_vph: float | None
    planned_actual_time_error_p95_s: float | None
    planned_actual_position_error_p95_m: float | None
    failed: bool


def _successful_results(per_seed_results: Sequence[PerSeedResultLike]) -> list[PerSeedResultLike]:
    if not per_seed_results:
        raise ValueError("per_seed_results must not be empty")

    first = per_seed_results[0]
    seen_seeds: set[int] = set()
    successful: list[PerSeedResultLike] = []
    for result in per_seed_results:
        if result.experiment_id != first.experiment_id:
            raise ValueError("all per_seed_results must share the same experiment_id")
        if result.policy_tag != first.policy_tag:
            raise ValueError("all per_seed_results must share the same policy_tag")
        if result.seed in seen_seeds:
            raise ValueError("per_seed_results must not contain duplicate seeds")
        seen_seeds.add(result.seed)
        if not result.failed:
            successful.append(result)

    if len(seen_seeds) < 3:
        raise ValueError("per_seed_results must contain at least 3 unique seeds")
    if not successful:
        raise ValueError("at least one successful per-seed result is required")

    return successful


def _numeric_values(results: list[PerSeedResultLike], field_name: str) -> list[float]:
    values = []
    for result in results:
        value = getattr(result, field_name)
        if value is not None:
            values.append(float(value))
    return values


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 10)


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def aggregate_to_summary(
    per_seed_results: Sequence[PerSeedResultLike],
) -> ExperimentResultSummary:
    successful = _successful_results(per_seed_results)
    first = per_seed_results[0]

    optional_time_values = _numeric_values(successful, "planned_actual_time_error_p95_s")
    optional_position_values = _numeric_values(successful, "planned_actual_position_error_p95_m")

    return ExperimentResultSummary(
        experiment_id=first.experiment_id,
        policy_tag=first.policy_tag,
        seed_count=len(per_seed_results),
        completion_rate=_mean(_numeric_values(successful, "completion_rate")),
        abort_rate=_mean(_numeric_values(successful, "abort_rate")),
        collision_count=int(sum(_numeric_values(successful, "collision_count"))),
        safety_violation_count=int(sum(_numeric_values(successful, "safety_violation_count"))),
        avg_ramp_delay_s=_mean(_numeric_values(successful, "avg_ramp_delay_s")),
        throughput_vph=_mean(_numeric_values(successful, "throughput_vph")),
        planned_actual_time_error_p95_s=(
            _mean(optional_time_values) if optional_time_values else None
        ),
        planned_actual_position_error_p95_m=(
            _mean(optional_position_values) if optional_position_values else None
        ),
    )


def aggregate_stats_view(
    per_seed_results: Sequence[PerSeedResultLike],
) -> dict[str, float]:
    successful = _successful_results(per_seed_results)
    failed_count = len(per_seed_results) - len(successful)
    stats: dict[str, float] = {
        "seed_count": float(len(per_seed_results)),
        "successful_seed_count": float(len(successful)),
        "failed_seed_count": float(failed_count),
    }

    for field_name in _METRIC_FIELDS:
        values = _numeric_values(successful, field_name)
        if not values:
            continue

        direction = _WORST_DIRECTION[field_name]
        worst_value = min(values) if direction == "min" else max(values)

        stats[f"{field_name}_mean"] = _mean(values)
        stats[f"{field_name}_worst_seed"] = worst_value
        stats[f"{field_name}_p95"] = _percentile_95(values)

    return stats


__all__ = [
    "aggregate_stats_view",
    "aggregate_to_summary",
]
