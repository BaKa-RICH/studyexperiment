"""Shared enums and dataclasses for active_gap_v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PlannerTag(StrEnum):
    ACTIVE_GAP = "active_gap"
    NO_CONTROL = "no_control"


class AnchorMode(StrEnum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"


class ExecutionState(StrEnum):
    APPROACHING = "approaching"
    PLANNING = "planning"
    COMMITTED = "committed"
    EXECUTING = "executing"
    POST_MERGE = "post_merge"
    FAIL_SAFE_STOP = "fail_safe_stop"
    ABORTED = "aborted"


class SliceKind(StrEnum):
    MERGE = "merge"
    COORDINATION = "coordination"


class ExecutionDecisionTag(StrEnum):
    COMMIT_MERGE_SLICE = "commit_merge_slice"
    COMMIT_COORDINATION_SLICE = "commit_coordination_slice"
    SAFE_WAIT = "safe_wait"
    FAIL_SAFE_STOP = "fail_safe_stop"


class CertificateFailureKind(StrEnum):
    REACHABILITY = "reachability"
    DYNAMICS = "dynamics"
    SAFETY_UP = "safety_up"
    SAFETY_PM = "safety_pm"
    SAFETY_MS = "safety_ms"
    SAFETY_SF = "safety_sf"
    GROUP_INVALID = "group_invalid"


@dataclass(slots=True)
class ScenarioConfig:
    scenario_id: str
    lane_width_m: float = 3.2
    control_zone_length_m: float = 600.0
    ramp_approach_subzone_m: tuple[int, int] = (0, 50)
    legal_merge_zone_m: tuple[int, int] = (50, 290)
    emergency_tail_m: tuple[int, int] = (290, 300)
    planning_tick_s: float = 0.1
    rollout_tick_s: float = 0.1
    certificate_sampling_dt_s: float = 0.1
    post_merge_guard_s: float = 1.0
    epsilon_t_s: float = 0.05
    a_max_mps2: float = 2.6
    b_safe_mps2: float = 4.5
    fail_safe_brake_mps2: float = 4.5
    comfortable_brake_mps2: float = 2.0
    min_gap_m: float = 2.5
    time_headway_s: float = 1.0
    h_pr_s: float = 1.5
    h_rf_s: float = 2.0
    fixed_anchor_m: int = 170
    lane_change_duration_s: float = 3.0
    mainline_vmax_mps: float = 25.0
    ramp_vmax_mps: float = 16.7
    vehicle_length_m: float = 5.0


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


@dataclass(slots=True)
class TCG:
    snapshot_id: str
    p_id: str
    m_id: str
    s_id: str
    u_id: str | None
    f_id: str | None
    anchor_mode: AnchorMode
    sequence_relation: str


@dataclass(slots=True)
class CoordinationSnapshot:
    snapshot_id: str
    sim_time_s: float
    planner_tag: PlannerTag
    anchor_mode: AnchorMode
    ego_id: str
    ego_state: VehicleState
    control_zone_states: dict[str, VehicleState]
    locked_tcgs: dict[str, TCG]
    scenario: ScenarioConfig


@dataclass(slots=True)
class MergeTarget:
    snapshot_id: str
    m_id: str
    x_m_star_m: float
    t_m_star_s: float
    horizon_s: float
    v_star_mps: float
    x_p_star_m: float
    x_s_star_m: float
    delta_open_m: float
    delta_coop_m: float
    delta_delay_s: float
    rho_min_m: float
    ranking_key: tuple[float, float, float, float, float]


@dataclass(slots=True)
class QuinticBoundaryState:
    x_m: float
    v_mps: float
    a_mps2: float


@dataclass(slots=True)
class QuinticLongitudinalProfile:
    vehicle_id: str
    t0_s: float
    horizon_s: float
    coefficients: tuple[float, float, float, float, float, float]
    start_state: QuinticBoundaryState
    terminal_state: QuinticBoundaryState


@dataclass(slots=True)
class SafetyCertificate:
    snapshot_id: str
    m_id: str
    tcg_ids: tuple[str | None, str, str, str, str | None]
    slice_kind: SliceKind
    valid_from_s: float
    valid_until_s: float
    min_margin_up_m: float | None
    min_margin_pm_m: float
    min_margin_ms_m: float
    min_margin_sf_m: float | None
    binding_constraint: str
    failure_kind: CertificateFailureKind | None
    checked_time_candidates_s: tuple[float, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class RollingPlanSlice:
    snapshot_id: str
    m_id: str
    slice_kind: SliceKind
    tcg: TCG
    merge_target: MergeTarget | None
    certificate: SafetyCertificate
    exec_start_s: float
    exec_end_s: float
    profile_p: QuinticLongitudinalProfile
    profile_m: QuinticLongitudinalProfile
    profile_s: QuinticLongitudinalProfile
    delta_open_before_m: float | None = None
    delta_open_after_m: float | None = None
    speed_alignment_before_mps: float | None = None
    speed_alignment_after_mps: float | None = None


@dataclass(slots=True)
class ExecutionDecision:
    decision_tag: ExecutionDecisionTag
    state_after: ExecutionState
    reason: str
    tcg_locked: bool
    target_locked: bool
    plan_slice: RollingPlanSlice | None = None


@dataclass(slots=True)
class ExperimentResultSummary:
    experiment_id: str
    planner_tag: PlannerTag
    anchor_mode: AnchorMode | None
    seed_count: int
    completion_rate: float
    abort_rate: float
    collision_count: int
    safety_violation_count: int
    avg_ramp_delay_s: float
    throughput_vph: float
    delta_open_positive_rate: float | None = None
    planned_actual_time_error_p95_s: float | None = None
    planned_actual_position_error_p95_m: float | None = None
