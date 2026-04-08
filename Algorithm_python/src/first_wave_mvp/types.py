"""第一波 MVP 共享类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from first_wave_mvp.config import (
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


class PolicyTag(StrEnum):
    NO_CONTROL = "no_control"
    FIFO_FIXED_ANCHOR = "fifo_fixed_anchor"
    FIFO_FLEXIBLE_ANCHOR = "fifo_flexible_anchor"


class ExecutionState(StrEnum):
    APPROACHING = "approaching"
    PLANNING = "planning"
    COMMITTED = "committed"
    EXECUTING = "executing"
    POST_MERGE = "post_merge"
    FAIL_SAFE_STOP = "fail_safe_stop"
    ABORTED = "aborted"


class RejectReason(StrEnum):
    REJECT_ZONE = "reject_zone"
    REJECT_TIMING = "reject_timing"
    REJECT_GAP_IDENTITY = "reject_gap_identity"
    REJECT_INTERVAL_SAFETY = "reject_interval_safety"
    REJECT_POST_MERGE_SAFETY = "reject_post_merge_safety"
    REJECT_DYNAMIC_LIMIT = "reject_dynamic_limit"
    REJECT_PARTNER_INVALID = "reject_partner_invalid"


class CommitState(StrEnum):
    UNCOMMITTED = "uncommitted"
    COMMITTED = "committed"


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value!r}")


def _validate_interval(name: str, interval: tuple[int, int]) -> None:
    if len(interval) != 2:
        raise ValueError(f"{name} must contain exactly 2 bounds")

    start, end = interval
    if start >= end:
        raise ValueError(f"{name} must satisfy start < end, got {interval!r}")


@dataclass(slots=True)
class GapRef:
    pred_id: str | None
    foll_id: str | None


@dataclass(slots=True)
class TrajectoryPoint:
    t_s: float
    x_m: float
    v_mps: float
    a_mps2: float


@dataclass(slots=True)
class ScenarioConfig:
    scenario_id: str
    lane_width_m: float = LANE_WIDTH_M
    control_zone_length_m: float = CONTROL_ZONE_LENGTH_M
    ramp_approach_subzone_m: tuple[int, int] = RAMP_APPROACH_SUBZONE_M
    legal_merge_zone_m: tuple[int, int] = LEGAL_MERGE_ZONE_M
    emergency_tail_m: tuple[int, int] = EMERGENCY_TAIL_M
    rollout_tick_s: float = ROLLOUT_TICK_S
    planning_tick_s: float = PLANNING_TICK_S
    gate_sampling_dt_s: float = GATE_SAMPLING_DT_S
    post_merge_guard_s: float = POST_MERGE_GUARD_S
    epsilon_t_s: float = EPSILON_T_S
    a_max_mps2: float = A_MAX_MPS2
    b_safe_mps2: float = B_SAFE_MPS2
    fail_safe_brake_mps2: float = FAIL_SAFE_BRAKE_MPS2
    comfortable_brake_mps2: float = COMFORTABLE_BRAKE_MPS2
    min_gap_m: float = MIN_GAP_M
    time_headway_s: float = TIME_HEADWAY_S
    h_pr_s: float = H_PR_S
    h_rf_s: float = H_RF_S
    fixed_anchor_m: int = FIXED_ANCHOR_M
    lane_change_duration_s: float = LANE_CHANGE_DURATION_S
    mainline_vmax_mps: float = MAINLINE_VMAX_MPS
    ramp_vmax_mps: float = RAMP_VMAX_MPS

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must not be empty")

        for name, interval in (
            ("ramp_approach_subzone_m", self.ramp_approach_subzone_m),
            ("legal_merge_zone_m", self.legal_merge_zone_m),
            ("emergency_tail_m", self.emergency_tail_m),
        ):
            _validate_interval(name, interval)

        for name, value in (
            ("lane_width_m", self.lane_width_m),
            ("control_zone_length_m", self.control_zone_length_m),
            ("rollout_tick_s", self.rollout_tick_s),
            ("planning_tick_s", self.planning_tick_s),
            ("gate_sampling_dt_s", self.gate_sampling_dt_s),
            ("post_merge_guard_s", self.post_merge_guard_s),
            ("epsilon_t_s", self.epsilon_t_s),
            ("a_max_mps2", self.a_max_mps2),
            ("b_safe_mps2", self.b_safe_mps2),
            ("fail_safe_brake_mps2", self.fail_safe_brake_mps2),
            ("comfortable_brake_mps2", self.comfortable_brake_mps2),
            ("min_gap_m", self.min_gap_m),
            ("time_headway_s", self.time_headway_s),
            ("h_pr_s", self.h_pr_s),
            ("h_rf_s", self.h_rf_s),
            ("lane_change_duration_s", self.lane_change_duration_s),
            ("mainline_vmax_mps", self.mainline_vmax_mps),
            ("ramp_vmax_mps", self.ramp_vmax_mps),
        ):
            _validate_positive(name, value)

        legal_start, legal_end = self.legal_merge_zone_m
        if not legal_start <= self.fixed_anchor_m <= legal_end:
            raise ValueError(
                "fixed_anchor_m must lie inside legal_merge_zone_m, "
                f"got {self.fixed_anchor_m!r}"
            )


@dataclass(slots=True)
class VehicleState:
    veh_id: str
    stream: str
    lane_id: str
    x_pos_m: float
    speed_mps: float
    accel_mps2: float
    length_m: float
    is_cav: bool
    execution_state: ExecutionState
    commit_state: CommitState


@dataclass(slots=True)
class PlanningSnapshot:
    snapshot_id: str
    sim_time_s: float
    policy_tag: PolicyTag
    ego_id: str
    ego_state: VehicleState
    control_zone_states: dict[str, VehicleState]
    target_lane_object_ids: tuple[str, ...]
    committed_plans: dict[str, "CommittedPlan"]
    scenario: ScenarioConfig


@dataclass(slots=True)
class CandidatePlan:
    snapshot_id: str
    candidate_id: str
    policy_tag: PolicyTag
    ego_id: str
    target_gap: GapRef
    x_m_m: int
    t_m_s: float
    t_r_free_s: float
    partner_ids: tuple[str, ...]
    sequence_relation: str
    tau_lc_s: float
    x_s_m: float
    objective_key: tuple[float, float, int]
    ego_reference_profile: tuple[TrajectoryPoint, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class GateResult:
    snapshot_id: str
    candidate_id: str
    accepted: bool
    reject_reason: RejectReason | None
    checked_time_grid_s: tuple[float, ...]
    min_margin_m: float | None = None
    binding_check: str | None = None


@dataclass(slots=True)
class CommittedPlan:
    snapshot_id: str
    candidate_id: str
    commit_time_s: float
    commit_state: CommitState
    execution_state: ExecutionState
    candidate: CandidatePlan
    gate_result: GateResult


@dataclass(slots=True)
class ExperimentResultSummary:
    experiment_id: str
    policy_tag: PolicyTag
    seed_count: int
    completion_rate: float
    abort_rate: float
    collision_count: int
    safety_violation_count: int
    avg_ramp_delay_s: float
    throughput_vph: float
    planned_actual_time_error_p95_s: float | None = None
    planned_actual_position_error_p95_m: float | None = None


__all__ = [
    "CandidatePlan",
    "CommitState",
    "CommittedPlan",
    "ExecutionState",
    "ExperimentResultSummary",
    "GapRef",
    "GateResult",
    "PlanningSnapshot",
    "PolicyTag",
    "RejectReason",
    "ScenarioConfig",
    "TrajectoryPoint",
    "VehicleState",
]
