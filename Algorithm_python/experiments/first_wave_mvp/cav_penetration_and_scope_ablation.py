"""CAV 渗透率与协同范围消融实验入口定义。"""

from __future__ import annotations

from dataclasses import asdict
import json

from common import (
    DEFAULT_SEEDS,
    ExperimentBundle,
    ExperimentSpec,
    PerSeedResult,
    build_output_path,
    bundle_to_manifest,
    to_serializable,
)
from first_wave_mvp.experiment_runner import ensure_output_directory, run_policy_experiment
from first_wave_mvp.metrics import aggregate_stats_view, aggregate_to_summary
from first_wave_mvp.types import PolicyTag


EXPERIMENT_ID = "cav_penetration_and_scope_ablation"


def build_experiment_bundle(
    per_seed_results: tuple[PerSeedResult, ...] = (),
) -> ExperimentBundle:
    spec = ExperimentSpec(
        experiment_id=EXPERIMENT_ID,
        title="CAV 渗透率 / 协同范围消融",
        objective="验证在协同能力被削弱时，系统行为是否平滑退化且不突然失稳。",
        default_seeds=DEFAULT_SEEDS,
        supported_policies=(
            PolicyTag.FIFO_FIXED_ANCHOR,
            PolicyTag.FIFO_FLEXIBLE_ANCHOR,
        ),
        default_parameters={
            "cav_ratio_grid": (0.0, 0.5, 1.0),
            "cooperation_scope_grid": ("minimal", "expanded"),
            "seed_count": len(DEFAULT_SEEDS),
            "sim_duration_s": 25.0,
            "mainline_vph": 1000,
            "ramp_vph": 300,
        },
        output_path=build_output_path(EXPERIMENT_ID),
    )
    return ExperimentBundle(spec=spec, per_seed_results=per_seed_results)


CONFIG_VARIANTS = {
    "low_penetration_minimal_scope": {
        "mainline_vph": 1100,
        "ramp_vph": 320,
        "mainline_cav_ratio": 0.0,
        "mainline_speed_min_mps": 8.5,
        "mainline_speed_max_mps": 10.5,
        "ramp_speed_min_mps": 8.0,
        "ramp_speed_max_mps": 9.5,
    },
    "full_cav_expanded_scope": {
        "mainline_vph": 900,
        "ramp_vph": 280,
        "mainline_cav_ratio": 1.0,
        "mainline_speed_min_mps": 10.0,
        "mainline_speed_max_mps": 12.0,
        "ramp_speed_min_mps": 9.0,
        "ramp_speed_max_mps": 11.0,
    },
}


def run_numeric_experiment(*, output_path: str | None = None) -> dict[str, object]:
    bundle = build_experiment_bundle()
    config_results: dict[str, object] = {}
    for config_key, overrides in CONFIG_VARIANTS.items():
        parameters = {**bundle.spec.default_parameters, **overrides}
        raw_results = run_policy_experiment(
            experiment_id=EXPERIMENT_ID,
            policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR,
            seeds=bundle.spec.default_seeds,
            parameters=parameters,
        )
        per_seed_results = tuple(PerSeedResult(**raw_result) for raw_result in raw_results)
        config_results[config_key] = {
            "policy_tag": PolicyTag.FIFO_FLEXIBLE_ANCHOR.value,
            "parameters": to_serializable(parameters),
            "per_seed_results": [to_serializable(asdict(result)) for result in per_seed_results],
            "summary": to_serializable(asdict(aggregate_to_summary(per_seed_results))),
            "stats_view": aggregate_stats_view(per_seed_results),
        }

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "mode": "minimal_numeric_executor",
        "spec": bundle_to_manifest(bundle),
        "config_results": config_results,
    }
    output_path = output_path or bundle.spec.output_path
    path = ensure_output_directory(output_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(run_numeric_experiment(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
