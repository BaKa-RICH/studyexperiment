"""第一波 MVP 实验公共结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import sys
from typing import Any

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from first_wave_mvp.types import PolicyTag


DEFAULT_SEEDS = (42, 123, 999)
OUTPUT_ROOT = Path("experiments/first_wave_mvp/outputs")


def build_output_path(experiment_id: str) -> str:
    return str(OUTPUT_ROOT / experiment_id / "summary.json")


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    title: str
    objective: str
    default_seeds: tuple[int, ...] = DEFAULT_SEEDS
    supported_policies: tuple[PolicyTag, ...] = (
        PolicyTag.FIFO_FIXED_ANCHOR,
        PolicyTag.FIFO_FLEXIBLE_ANCHOR,
    )
    default_parameters: dict[str, Any] = field(default_factory=dict)
    output_path: str = ""

    def __post_init__(self) -> None:
        if not self.output_path:
            object.__setattr__(self, "output_path", build_output_path(self.experiment_id))
        if len(self.default_seeds) < 3:
            raise ValueError("default_seeds must contain at least 3 seeds")


@dataclass(frozen=True, slots=True)
class PerSeedResult:
    experiment_id: str
    policy_tag: PolicyTag
    seed: int
    completion_rate: float | None
    abort_rate: float | None
    collision_count: int | None
    safety_violation_count: int | None
    avg_ramp_delay_s: float | None
    throughput_vph: float | None
    planned_actual_time_error_p95_s: float | None = None
    planned_actual_position_error_p95_m: float | None = None
    failed: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.failed and not self.failure_reason:
            raise ValueError("failed per-seed results must include failure_reason")
        if not self.failed and self.failure_reason is not None:
            raise ValueError("successful per-seed results must not include failure_reason")


@dataclass(frozen=True, slots=True)
class ExperimentBundle:
    spec: ExperimentSpec
    per_seed_results: tuple[PerSeedResult, ...] = ()

    def __post_init__(self) -> None:
        for result in self.per_seed_results:
            if result.experiment_id != self.spec.experiment_id:
                raise ValueError("per_seed_results experiment_id must match spec.experiment_id")
            if result.policy_tag not in self.spec.supported_policies:
                raise ValueError("per_seed_results policy_tag must be supported by spec")


def to_serializable(value: Any) -> Any:
    if isinstance(value, PolicyTag):
        return value.value
    if isinstance(value, tuple):
        return [to_serializable(item) for item in value]
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    return value


def bundle_to_manifest(bundle: ExperimentBundle) -> dict[str, Any]:
    return {
        "experiment_id": bundle.spec.experiment_id,
        "title": bundle.spec.title,
        "objective": bundle.spec.objective,
        "default_seeds": list(bundle.spec.default_seeds),
        "supported_policies": [policy.value for policy in bundle.spec.supported_policies],
        "default_parameters": to_serializable(bundle.spec.default_parameters),
        "output_path": bundle.spec.output_path,
        "seed_count": len(bundle.spec.default_seeds),
        "per_seed_results": [
            to_serializable(asdict(result))
            for result in bundle.per_seed_results
        ],
    }


__all__ = [
    "DEFAULT_SEEDS",
    "OUTPUT_ROOT",
    "ExperimentBundle",
    "ExperimentSpec",
    "PerSeedResult",
    "build_output_path",
    "bundle_to_manifest",
    "to_serializable",
]
