"""轻负荷正确性实验入口定义。"""

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


EXPERIMENT_ID = "light_load_correctness"


def build_experiment_bundle(
    per_seed_results: tuple[PerSeedResult, ...] = (),
) -> ExperimentBundle:
    spec = ExperimentSpec(
        experiment_id=EXPERIMENT_ID,
        title="轻负荷正确性",
        objective="验证低竞争场景下物理语义、候选生成、gate 与执行闭环是否正确闭合。",
        default_seeds=DEFAULT_SEEDS,
        supported_policies=(
            PolicyTag.FIFO_FIXED_ANCHOR,
            PolicyTag.FIFO_FLEXIBLE_ANCHOR,
        ),
        default_parameters={
            "mainline_vph": 600,
            "ramp_vph": 120,
            "seed_count": len(DEFAULT_SEEDS),
            "sim_duration_s": 20.0,
            "mainline_speed_min_mps": 11.0,
            "mainline_speed_max_mps": 14.0,
            "ramp_speed_min_mps": 8.5,
            "ramp_speed_max_mps": 11.0,
        },
        output_path=build_output_path(EXPERIMENT_ID),
    )
    return ExperimentBundle(spec=spec, per_seed_results=per_seed_results)


def run_numeric_experiment(*, output_path: str | None = None) -> dict[str, object]:
    bundle = build_experiment_bundle()
    policy_results: dict[str, object] = {}
    for policy_tag in bundle.spec.supported_policies:
        raw_results = run_policy_experiment(
            experiment_id=EXPERIMENT_ID,
            policy_tag=policy_tag,
            seeds=bundle.spec.default_seeds,
            parameters=bundle.spec.default_parameters,
        )
        per_seed_results = tuple(PerSeedResult(**raw_result) for raw_result in raw_results)
        policy_results[policy_tag.value] = {
            "per_seed_results": [to_serializable(asdict(result)) for result in per_seed_results],
            "summary": to_serializable(asdict(aggregate_to_summary(per_seed_results))),
            "stats_view": aggregate_stats_view(per_seed_results),
        }

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "mode": "minimal_numeric_executor",
        "spec": bundle_to_manifest(bundle),
        "policy_results": policy_results,
    }
    output_path = output_path or bundle.spec.output_path
    path = ensure_output_directory(output_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    print(json.dumps(run_numeric_experiment(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
