from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
EXPERIMENTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "first_wave_mvp"
for path in (SRC_ROOT, EXPERIMENTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from cav_penetration_and_scope_ablation import build_experiment_bundle as build_ablation_bundle  # noqa: E402
from common import ExperimentBundle, ExperimentSpec, PerSeedResult, bundle_to_manifest  # noqa: E402
from light_load_correctness import build_experiment_bundle as build_light_load_bundle  # noqa: E402
from medium_high_load_competition import build_experiment_bundle as build_competition_bundle  # noqa: E402
from first_wave_mvp.metrics import aggregate_stats_view, aggregate_to_summary  # noqa: E402
from first_wave_mvp.types import ExperimentResultSummary, PolicyTag  # noqa: E402


def _make_result(
    *,
    experiment_id: str,
    policy_tag: PolicyTag = PolicyTag.FIFO_FIXED_ANCHOR,
    seed: int,
    completion_rate: float = 1.0,
    abort_rate: float = 0.0,
    collision_count: int = 0,
    safety_violation_count: int = 0,
    avg_ramp_delay_s: float = 1.0,
    throughput_vph: float = 1200.0,
    planned_actual_time_error_p95_s: float | None = 0.1,
    planned_actual_position_error_p95_m: float | None = 0.5,
    failed: bool = False,
    failure_reason: str | None = None,
) -> PerSeedResult:
    return PerSeedResult(
        experiment_id=experiment_id,
        policy_tag=policy_tag,
        seed=seed,
        completion_rate=None if failed else completion_rate,
        abort_rate=None if failed else abort_rate,
        collision_count=None if failed else collision_count,
        safety_violation_count=None if failed else safety_violation_count,
        avg_ramp_delay_s=None if failed else avg_ramp_delay_s,
        throughput_vph=None if failed else throughput_vph,
        planned_actual_time_error_p95_s=None if failed else planned_actual_time_error_p95_s,
        planned_actual_position_error_p95_m=None if failed else planned_actual_position_error_p95_m,
        failed=failed,
        failure_reason=failure_reason,
    )


def test_experiment_bundles_exist_and_manifest_keys_are_snake_case() -> None:
    bundles = [
        build_light_load_bundle(),
        build_competition_bundle(),
        build_ablation_bundle(),
    ]

    assert all(isinstance(bundle, ExperimentBundle) for bundle in bundles)
    assert all(isinstance(bundle.spec, ExperimentSpec) for bundle in bundles)
    assert {bundle.spec.experiment_id for bundle in bundles} == {
        "light_load_correctness",
        "medium_high_load_competition",
        "cav_penetration_and_scope_ablation",
    }

    for bundle in bundles:
        manifest = bundle_to_manifest(bundle)
        assert manifest["seed_count"] >= 3
        assert manifest["output_path"].endswith("summary.json")
        for key in manifest:
            assert re.fullmatch(r"[a-z0-9_]+", key)


def test_aggregate_to_summary_matches_contract_fields() -> None:
    per_seed_results = [
        _make_result(experiment_id="light_load_correctness", seed=42, avg_ramp_delay_s=1.0, throughput_vph=1200.0),
        _make_result(experiment_id="light_load_correctness", seed=123, avg_ramp_delay_s=2.0, throughput_vph=1100.0),
        _make_result(experiment_id="light_load_correctness", seed=999, avg_ramp_delay_s=3.0, throughput_vph=1300.0),
    ]

    summary = aggregate_to_summary(per_seed_results)

    assert isinstance(summary, ExperimentResultSummary)
    assert summary.seed_count == 3
    assert summary.avg_ramp_delay_s == 2.0
    assert summary.throughput_vph == 1200.0
    assert summary.collision_count == 0
    assert summary.planned_actual_time_error_p95_s == 0.1


def test_aggregate_stats_view_supports_mean_worst_seed_and_p95() -> None:
    per_seed_results = [
        _make_result(experiment_id="medium_high_load_competition", seed=42, abort_rate=0.0, throughput_vph=1200.0),
        _make_result(experiment_id="medium_high_load_competition", seed=123, abort_rate=0.1, throughput_vph=1100.0),
        _make_result(experiment_id="medium_high_load_competition", seed=999, abort_rate=0.2, throughput_vph=1300.0),
    ]

    stats = aggregate_stats_view(per_seed_results)

    assert stats["seed_count"] == 3.0
    assert stats["abort_rate_mean"] == 0.1
    assert stats["abort_rate_worst_seed"] == 0.2
    assert stats["abort_rate_p95"] == 0.2
    assert stats["throughput_vph_worst_seed"] == 1100.0


def test_partial_seed_failures_are_aggregated_without_gate_logic() -> None:
    per_seed_results = [
        _make_result(experiment_id="cav_penetration_and_scope_ablation", seed=42, completion_rate=1.0),
        _make_result(
            experiment_id="cav_penetration_and_scope_ablation",
            seed=123,
            failed=True,
            failure_reason="mock_engine_timeout",
        ),
        _make_result(experiment_id="cav_penetration_and_scope_ablation", seed=999, completion_rate=0.9),
    ]

    summary = aggregate_to_summary(per_seed_results)
    stats = aggregate_stats_view(per_seed_results)

    assert summary.seed_count == 3
    assert summary.completion_rate == 0.95
    assert stats["failed_seed_count"] == 1.0
    assert "pass" not in stats
    assert "failed_gate" not in stats


def test_ablation_bundle_exposes_zero_penetration_edge_case() -> None:
    bundle = build_ablation_bundle()

    assert 0.0 in bundle.spec.default_parameters["cav_ratio_grid"]
    assert bundle.spec.default_parameters["seed_count"] >= 3


def test_experiment_modules_do_not_depend_on_regression_gate() -> None:
    modules = [
        build_light_load_bundle.__module__,
        build_competition_bundle.__module__,
        build_ablation_bundle.__module__,
    ]

    for module_name in modules:
        module = sys.modules[module_name]
        source = inspect.getsource(module)
        assert "regression_gate" not in source
        assert "traci" not in source.lower()
        assert "carla" not in source.lower()
