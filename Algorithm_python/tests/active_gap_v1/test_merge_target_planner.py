from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from active_gap_v1.config import default_scenario_config
from active_gap_v1.merge_target_planner import enumerate_merge_targets
from active_gap_v1.predictor import predict_optional_free_position
from active_gap_v1.snapshot import build_coordination_snapshot
from active_gap_v1.tcg_selector import identify_tcg
from active_gap_v1.types import AnchorMode, ExecutionState, PlannerTag, VehicleState


def _make_vehicle(
    *,
    veh_id: str,
    stream: str,
    lane_id: str,
    x_pos_m: float,
    speed_mps: float = 16.7,
    is_cav: bool = True,
) -> VehicleState:
    return VehicleState(
        veh_id=veh_id,
        stream=stream,
        lane_id=lane_id,
        x_pos_m=x_pos_m,
        speed_mps=speed_mps,
        accel_mps2=0.0,
        length_m=5.0,
        is_cav=is_cav,
        execution_state=ExecutionState.PLANNING,
    )


def _make_a0_world() -> dict[str, VehicleState]:
    return {
        "p": _make_vehicle(veh_id="p", stream="mainline", lane_id="main_0", x_pos_m=11.0),
        "m": _make_vehicle(veh_id="m", stream="ramp", lane_id="ramp_0", x_pos_m=9.0, is_cav=True),
        "s": _make_vehicle(veh_id="s", stream="mainline", lane_id="main_0", x_pos_m=5.0),
    }


def _enumerate_for_mode(anchor_mode: AnchorMode):
    snapshot = build_coordination_snapshot(
        sim_time_s=1.2,
        scenario=default_scenario_config(scenario_id="a0"),
        world_state=_make_a0_world(),
        locked_tcgs={},
        planner_tag=PlannerTag.ACTIVE_GAP,
        anchor_mode=anchor_mode,
    )
    tcg = identify_tcg(snapshot=snapshot)
    assert tcg is not None
    return tcg, enumerate_merge_targets(snapshot=snapshot, tcg=tcg)


def test_fixed_mode_a0_produces_merge_target() -> None:
    _, targets = _enumerate_for_mode(AnchorMode.FIXED)
    assert len(targets) >= 1


def test_flexible_mode_produces_at_least_fixed_candidates() -> None:
    _, fixed_targets = _enumerate_for_mode(AnchorMode.FIXED)
    _, flexible_targets = _enumerate_for_mode(AnchorMode.FLEXIBLE)
    assert len(flexible_targets) >= 1
    assert len(flexible_targets) >= len(fixed_targets)


def test_delta_open_positive_for_a0_layout() -> None:
    _, targets = _enumerate_for_mode(AnchorMode.FIXED)
    assert targets
    assert all(target.delta_open_m > 0.0 for target in targets)


def test_ranking_key_matches_contract_order() -> None:
    _, targets = _enumerate_for_mode(AnchorMode.FIXED)
    assert targets
    first = targets[0]
    assert len(first.ranking_key) == 6, f"Expected 6-element ranking key, got {len(first.ranking_key)}"
    assert first.ranking_key[0] == first.t_m_star_s
    assert first.ranking_key[2] == first.delta_coop_m
    assert first.ranking_key[3] == first.delta_delay_s
    assert first.ranking_key[4] == -first.rho_min_m
    assert first.ranking_key[5] == first.x_m_star_m


def test_enumeration_order_is_deterministic() -> None:
    sequences = []
    for _ in range(3):
        _, targets = _enumerate_for_mode(AnchorMode.FLEXIBLE)
        sequences.append(
            [
                (
                    target.ranking_key,
                    target.x_m_star_m,
                    target.horizon_s,
                    target.v_star_mps,
                )
                for target in targets
            ]
        )
    assert sequences[0] == sequences[1] == sequences[2]


def test_missing_u_f_does_not_crash_planner() -> None:
    tcg, targets = _enumerate_for_mode(AnchorMode.FIXED)
    assert tcg.u_id is None
    assert tcg.f_id is None
    assert isinstance(targets, list)


def test_predictor_returns_none_for_missing_optional_vehicle() -> None:
    assert predict_optional_free_position(vehicle=None, horizon_s=3.0) is None
