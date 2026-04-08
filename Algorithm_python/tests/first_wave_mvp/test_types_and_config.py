from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from first_wave_mvp import (  # noqa: E402
    FIXED_ANCHOR_M,
    GATE_SAMPLING_DT_S,
    H_PR_S,
    H_RF_S,
    LEGAL_MERGE_ZONE_M,
    PLANNING_TICK_S,
    ROLLOUT_TICK_S,
    CommitState,
    ExecutionState,
    PolicyTag,
    ScenarioConfig,
)
from first_wave_mvp.types import ExperimentResultSummary, GapRef, VehicleState  # noqa: E402


def test_package_exports_can_be_imported() -> None:
    module = import_module("first_wave_mvp")
    exported = set(module.__all__)

    assert "ScenarioConfig" in exported
    assert "PolicyTag" in exported
    assert "ROLLOUT_TICK_S" in exported
    assert module.ScenarioConfig is ScenarioConfig


def test_default_scenario_config_matches_formal_defaults() -> None:
    config = ScenarioConfig(scenario_id="baseline")

    assert config.rollout_tick_s == pytest.approx(ROLLOUT_TICK_S)
    assert config.planning_tick_s == pytest.approx(PLANNING_TICK_S)
    assert config.gate_sampling_dt_s == pytest.approx(GATE_SAMPLING_DT_S)
    assert config.h_pr_s == pytest.approx(H_PR_S)
    assert config.h_rf_s == pytest.approx(H_RF_S)
    assert config.fixed_anchor_m == FIXED_ANCHOR_M
    assert config.legal_merge_zone_m == LEGAL_MERGE_ZONE_M


def test_core_objects_can_be_instantiated_for_downstream_tasks() -> None:
    config = ScenarioConfig(scenario_id="smoke")
    vehicle = VehicleState(
        veh_id="r0",
        stream="ramp",
        lane_id="ramp_0",
        x_pos_m=10.0,
        speed_mps=8.0,
        accel_mps2=0.0,
        length_m=5.0,
        is_cav=True,
        execution_state=ExecutionState.PLANNING,
        commit_state=CommitState.UNCOMMITTED,
    )
    gap = GapRef(pred_id="p0", foll_id="f0")
    summary = ExperimentResultSummary(
        experiment_id="exp-1",
        policy_tag=PolicyTag.FIFO_FIXED_ANCHOR,
        seed_count=3,
        completion_rate=1.0,
        abort_rate=0.0,
        collision_count=0,
        safety_violation_count=0,
        avg_ramp_delay_s=0.5,
        throughput_vph=1200.0,
    )

    assert vehicle.execution_state is ExecutionState.PLANNING
    assert gap.pred_id == "p0"
    assert summary.seed_count == 3
    assert config.mainline_vmax_mps > config.ramp_vmax_mps


def test_invalid_ticks_are_rejected() -> None:
    with pytest.raises(ValueError, match="planning_tick_s must be positive"):
        ScenarioConfig(scenario_id="bad", planning_tick_s=0.0)


def test_fixed_anchor_must_stay_inside_legal_merge_zone() -> None:
    with pytest.raises(ValueError, match="fixed_anchor_m must lie inside legal_merge_zone_m"):
        ScenarioConfig(scenario_id="bad", fixed_anchor_m=999)


def test_invalid_zone_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="legal_merge_zone_m must satisfy start < end"):
        ScenarioConfig(scenario_id="bad", legal_merge_zone_m=(290, 50))


def test_types_and_config_modules_do_not_create_import_cycles() -> None:
    config_module = import_module("first_wave_mvp.config")
    types_module = import_module("first_wave_mvp.types")

    assert hasattr(config_module, "ROLLOUT_TICK_S")
    assert hasattr(types_module, "ScenarioConfig")
