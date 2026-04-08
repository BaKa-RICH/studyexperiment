"""为 pytest 提供真实 src 包导入路径的测试 shim。"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path


_SRC_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "first_wave_mvp"
__path__ = [str(_SRC_PACKAGE), *list(__path__)]  # type: ignore[name-defined]

from first_wave_mvp.config import (  # noqa: E402,F401
    A_MAX_MPS2,
    B_SAFE_MPS2,
    COMFORTABLE_BRAKE_MPS2,
    CONTROL_ZONE_LENGTH_M,
    EMERGENCY_TAIL_M,
    EPSILON_T_S,
    FAIL_SAFE_BRAKE_MPS2,
    FIXED_ANCHOR_M,
    GATE_SAMPLING_DT_S,
    H_PR_S,
    H_RF_S,
    LANE_CHANGE_DURATION_S,
    LANE_WIDTH_M,
    LEGAL_MERGE_ZONE_M,
    MAINLINE_VMAX_MPS,
    MIN_GAP_M,
    PLANNING_TICK_S,
    POST_MERGE_GUARD_S,
    RAMP_APPROACH_SUBZONE_M,
    RAMP_VMAX_MPS,
    ROLLOUT_TICK_S,
    TIME_HEADWAY_S,
)
from first_wave_mvp.types import (  # noqa: E402,F401
    CandidatePlan,
    CommitState,
    CommittedPlan,
    ExecutionState,
    ExperimentResultSummary,
    GapRef,
    GateResult,
    PlanningSnapshot,
    PolicyTag,
    RejectReason,
    ScenarioConfig,
    TrajectoryPoint,
    VehicleState,
)

import_module("first_wave_mvp.config")
import_module("first_wave_mvp.types")

__all__ = [
    "A_MAX_MPS2",
    "B_SAFE_MPS2",
    "COMFORTABLE_BRAKE_MPS2",
    "CONTROL_ZONE_LENGTH_M",
    "CandidatePlan",
    "CommitState",
    "CommittedPlan",
    "EMERGENCY_TAIL_M",
    "EPSILON_T_S",
    "ExecutionState",
    "ExperimentResultSummary",
    "FAIL_SAFE_BRAKE_MPS2",
    "FIXED_ANCHOR_M",
    "GATE_SAMPLING_DT_S",
    "GapRef",
    "GateResult",
    "H_PR_S",
    "H_RF_S",
    "LANE_CHANGE_DURATION_S",
    "LANE_WIDTH_M",
    "LEGAL_MERGE_ZONE_M",
    "MAINLINE_VMAX_MPS",
    "MIN_GAP_M",
    "PLANNING_TICK_S",
    "POST_MERGE_GUARD_S",
    "PlanningSnapshot",
    "PolicyTag",
    "RAMP_APPROACH_SUBZONE_M",
    "RAMP_VMAX_MPS",
    "ROLLOUT_TICK_S",
    "RejectReason",
    "ScenarioConfig",
    "TIME_HEADWAY_S",
    "TrajectoryPoint",
    "VehicleState",
]
