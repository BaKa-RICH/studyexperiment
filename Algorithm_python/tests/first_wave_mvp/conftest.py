from __future__ import annotations

import sys
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
EXPERIMENTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "first_wave_mvp"
for path in (SRC_ROOT, EXPERIMENTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from common import PerSeedResult  # noqa: E402
from first_wave_mvp.types import PolicyTag  # noqa: E402


def _make_result(
    *,
    experiment_id: str,
    policy_tag: PolicyTag,
    seed: int,
    completion_rate: float = 1.0,
    abort_rate: float = 0.0,
    collision_count: int = 0,
    safety_violation_count: int = 0,
    avg_ramp_delay_s: float = 1.0,
    throughput_vph: float = 1200.0,
    planned_actual_time_error_p95_s: float | None = 0.05,
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


@pytest.fixture
def light_load_pass_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42),
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=123),
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999),
    ]


@pytest.fixture
def light_load_fail_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42),
        _make_result(
            experiment_id="light_load_correctness",
            policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
            seed=123,
            planned_actual_time_error_p95_s=0.2,
        ),
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999),
    ]


@pytest.fixture
def medium_high_load_fixed_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42, abort_rate=0.1, avg_ramp_delay_s=6.0, throughput_vph=900.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=123, abort_rate=0.2, avg_ramp_delay_s=7.0, throughput_vph=950.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999, abort_rate=0.1, avg_ramp_delay_s=5.5, throughput_vph=920.0),
    ]


@pytest.fixture
def medium_high_load_flexible_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=42, abort_rate=0.05, avg_ramp_delay_s=5.0, throughput_vph=980.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=123, abort_rate=0.1, avg_ramp_delay_s=6.0, throughput_vph=990.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=999, abort_rate=0.05, avg_ramp_delay_s=5.0, throughput_vph=1000.0),
    ]


@pytest.fixture
def medium_high_load_misaligned_flexible_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=7, abort_rate=0.05, avg_ramp_delay_s=5.0, throughput_vph=980.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=8, abort_rate=0.1, avg_ramp_delay_s=6.0, throughput_vph=990.0),
        _make_result(experiment_id="medium_high_load_competition", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=9, abort_rate=0.05, avg_ramp_delay_s=5.0, throughput_vph=1000.0),
    ]


@pytest.fixture
def ablation_pass_results_by_config() -> dict[str, list[PerSeedResult]]:
    return {
        "low_penetration_minimal_scope": [
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42, completion_rate=0.96, abort_rate=0.03, avg_ramp_delay_s=6.0, throughput_vph=900.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=123, completion_rate=0.97, abort_rate=0.04, avg_ramp_delay_s=6.5, throughput_vph=910.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999, completion_rate=0.98, abort_rate=0.02, avg_ramp_delay_s=5.8, throughput_vph=905.0),
        ],
        "full_cav_expanded_scope": [
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=42, completion_rate=0.99, abort_rate=0.01, avg_ramp_delay_s=4.0, throughput_vph=980.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=123, completion_rate=0.99, abort_rate=0.02, avg_ramp_delay_s=4.5, throughput_vph=990.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=999, completion_rate=1.0, abort_rate=0.01, avg_ramp_delay_s=4.2, throughput_vph=995.0),
        ],
    }


@pytest.fixture
def ablation_fail_results_by_config() -> dict[str, list[PerSeedResult]]:
    return {
        "low_penetration_minimal_scope": [
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42, completion_rate=0.96, abort_rate=0.03, avg_ramp_delay_s=6.0, throughput_vph=900.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=123, completion_rate=0.97, abort_rate=0.04, avg_ramp_delay_s=6.5, throughput_vph=910.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999, completion_rate=0.98, abort_rate=0.02, avg_ramp_delay_s=5.8, throughput_vph=905.0),
        ],
        "full_cav_expanded_scope": [
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=42, completion_rate=0.95, abort_rate=0.03, avg_ramp_delay_s=7.0, throughput_vph=850.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=123, completion_rate=0.95, abort_rate=0.04, avg_ramp_delay_s=7.5, throughput_vph=840.0),
            _make_result(experiment_id="cav_penetration_and_scope_ablation", policy_tag=PolicyTag.FIFO_FLEXIBLE_ANCHOR, seed=999, completion_rate=0.95, abort_rate=0.05, avg_ramp_delay_s=7.2, throughput_vph=845.0),
        ],
    }


@pytest.fixture
def too_few_seed_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42),
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=123),
    ]


@pytest.fixture
def failed_seed_results() -> list[PerSeedResult]:
    return [
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=42),
        _make_result(
            experiment_id="light_load_correctness",
            policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
            seed=123,
            failed=True,
            failure_reason="mock_timeout",
        ),
        _make_result(experiment_id="light_load_correctness", policy_tag=PolicyTag.FIFO_FIXED_ANCHOR, seed=999),
    ]
