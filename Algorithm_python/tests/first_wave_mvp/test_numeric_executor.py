from __future__ import annotations

import json
import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
EXPERIMENTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "first_wave_mvp"
for path in (SRC_ROOT, EXPERIMENTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from common import build_output_path  # noqa: E402
from light_load_correctness import build_experiment_bundle as build_light_load_bundle, run_numeric_experiment  # noqa: E402
from first_wave_mvp.experiment_runner import run_policy_experiment  # noqa: E402
from first_wave_mvp.scenario_initializer import initialize_scenario  # noqa: E402
from first_wave_mvp.types import PolicyTag  # noqa: E402


def test_same_seed_is_reproducible() -> None:
    bundle = build_light_load_bundle()
    parameters = bundle.spec.default_parameters

    first = run_policy_experiment(
        experiment_id=bundle.spec.experiment_id,
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        seeds=(42,),
        parameters=parameters,
    )
    second = run_policy_experiment(
        experiment_id=bundle.spec.experiment_id,
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        seeds=(42,),
        parameters=parameters,
    )

    assert first == second


def test_different_seeds_produce_different_initial_world_state() -> None:
    bundle = build_light_load_bundle()
    scenario_a = initialize_scenario(
        experiment_id=bundle.spec.experiment_id,
        seed=42,
        parameters=bundle.spec.default_parameters,
    )
    scenario_b = initialize_scenario(
        experiment_id=bundle.spec.experiment_id,
        seed=123,
        parameters=bundle.spec.default_parameters,
    )

    world_signature_a = sorted((veh_id, state.x_pos_m, state.speed_mps) for veh_id, state in scenario_a.world_state.items())
    world_signature_b = sorted((veh_id, state.x_pos_m, state.speed_mps) for veh_id, state in scenario_b.world_state.items())

    assert world_signature_a != world_signature_b


def test_light_load_entry_writes_real_summary_json(tmp_path) -> None:
    output_path = tmp_path / "light_load_summary.json"

    payload = run_numeric_experiment(output_path=str(output_path))

    assert output_path.exists()
    on_disk = json.loads(output_path.read_text(encoding="utf-8"))
    assert on_disk["experiment_id"] == "light_load_correctness"
    assert on_disk["mode"] == "minimal_numeric_executor"
    assert set(on_disk["policy_results"]) == {
        "fifo_fixed_anchor",
        "fifo_flexible_anchor",
    }
    fixed = on_disk["policy_results"]["fifo_fixed_anchor"]
    assert len(fixed["per_seed_results"]) >= 3
    assert fixed["summary"]["seed_count"] >= 3
    assert fixed["stats_view"]["seed_count"] >= 3
    assert payload == on_disk


def test_default_output_path_contract_remains_summary_json() -> None:
    assert build_output_path("light_load_correctness").endswith("summary.json")
