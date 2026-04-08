from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from active_gap_v1.config import default_scenario_config
from active_gap_v1.snapshot import build_coordination_snapshot
from active_gap_v1.tcg_selector import identify_tcg
from active_gap_v1.types import (
    AnchorMode,
    CertificateFailureKind,
    CoordinationSnapshot,
    ExecutionDecisionTag,
    ExecutionState,
    PlannerTag,
    ScenarioConfig,
    SliceKind,
    TCG,
    VehicleState,
)


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


def _make_snapshot(world_state: dict[str, VehicleState]) -> CoordinationSnapshot:
    return build_coordination_snapshot(
        sim_time_s=1.2,
        scenario=default_scenario_config(scenario_id="unit"),
        world_state=world_state,
        locked_tcgs={},
        planner_tag=PlannerTag.ACTIVE_GAP,
        anchor_mode=AnchorMode.FIXED,
    )


def test_all_enums_are_instantiable() -> None:
    enum_values = {
        PlannerTag: [member.value for member in PlannerTag],
        AnchorMode: [member.value for member in AnchorMode],
        ExecutionState: [member.value for member in ExecutionState],
        SliceKind: [member.value for member in SliceKind],
        ExecutionDecisionTag: [member.value for member in ExecutionDecisionTag],
        CertificateFailureKind: [member.value for member in CertificateFailureKind],
    }
    for enum_cls, values in enum_values.items():
        for value in values:
            assert enum_cls(value).value == value


def test_scenario_config_defaults_match_formulas() -> None:
    config = default_scenario_config(scenario_id="cfg")
    assert isinstance(config, ScenarioConfig)
    assert config.planning_tick_s == 0.1
    assert config.rollout_tick_s == 0.1
    assert config.certificate_sampling_dt_s == 0.1
    assert config.a_max_mps2 == 2.6
    assert config.b_safe_mps2 == 4.5
    assert config.fail_safe_brake_mps2 == 4.5
    assert config.comfortable_brake_mps2 == 2.0
    assert config.min_gap_m == 2.5
    assert config.time_headway_s == 1.0
    assert config.h_pr_s == 1.5
    assert config.h_rf_s == 2.0
    assert config.fixed_anchor_m == 170
    assert config.lane_change_duration_s == 3.0
    assert config.mainline_vmax_mps == 25.0
    assert config.ramp_vmax_mps == 16.7
    assert config.vehicle_length_m == 5.0
    assert config.lane_width_m == 3.2


def test_dataclasses_are_instantiable() -> None:
    ego = _make_vehicle(veh_id="m", stream="ramp", lane_id="ramp_0", x_pos_m=9.0)
    tcg = TCG(
        snapshot_id="snap_0.100",
        p_id="p",
        m_id="m",
        s_id="s",
        u_id=None,
        f_id=None,
        anchor_mode=AnchorMode.FIXED,
        sequence_relation="p>m>s",
    )
    snapshot = CoordinationSnapshot(
        snapshot_id="snap_0.100",
        sim_time_s=0.1,
        planner_tag=PlannerTag.ACTIVE_GAP,
        anchor_mode=AnchorMode.FIXED,
        ego_id="m",
        ego_state=ego,
        control_zone_states={"m": ego},
        locked_tcgs={"m": tcg},
        scenario=default_scenario_config(scenario_id="inst"),
    )
    assert snapshot.ego_state.veh_id == "m"
    assert snapshot.locked_tcgs["m"].m_id == "m"


def test_build_coordination_snapshot_freezes_current_tick() -> None:
    world_state = _make_a0_world()
    locked_tcgs = {
        "m": TCG(
            snapshot_id="snap_0.000",
            p_id="p",
            m_id="m",
            s_id="s",
            u_id=None,
            f_id=None,
            anchor_mode=AnchorMode.FIXED,
            sequence_relation="p>m>s",
        )
    }
    snapshot = build_coordination_snapshot(
        sim_time_s=2.3,
        scenario=default_scenario_config(scenario_id="freeze"),
        world_state=world_state,
        locked_tcgs=locked_tcgs,
        planner_tag=PlannerTag.ACTIVE_GAP,
        anchor_mode=AnchorMode.FIXED,
    )
    world_state["m"].x_pos_m = 999.0
    locked_tcgs["m"].p_id = "changed"

    assert snapshot.snapshot_id == "snap_2.300"
    assert snapshot.control_zone_states["m"].x_pos_m == 9.0
    assert snapshot.locked_tcgs["m"].p_id == "p"


def test_identify_tcg_finds_a0_layout() -> None:
    snapshot = _make_snapshot(_make_a0_world())
    tcg = identify_tcg(snapshot=snapshot)
    assert tcg is not None
    assert tcg.p_id == "p"
    assert tcg.m_id == "m"
    assert tcg.s_id == "s"
    assert tcg.anchor_mode == AnchorMode.FIXED


def test_identify_tcg_handles_missing_u_f() -> None:
    snapshot = _make_snapshot(_make_a0_world())
    tcg = identify_tcg(snapshot=snapshot)
    assert tcg is not None
    assert tcg.u_id is None
    assert tcg.f_id is None


def test_identify_tcg_is_deterministic_for_same_input() -> None:
    snapshot = _make_snapshot(_make_a0_world())
    results = [identify_tcg(snapshot=snapshot) for _ in range(3)]
    assert all(result is not None for result in results)

    first = results[0]
    assert first is not None
    for result in results[1:]:
        assert result is not None
        assert result.p_id == first.p_id
        assert result.m_id == first.m_id
        assert result.s_id == first.s_id
        assert result.u_id == first.u_id
        assert result.f_id == first.f_id
        assert result.sequence_relation == first.sequence_relation
