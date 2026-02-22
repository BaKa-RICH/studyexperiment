from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class VehicleObs:
    veh_id: str
    stream: str
    road_id: str
    lane_id: str
    lane_pos_m: float
    speed_mps: float
    accel_mps2: float
    d_to_merge_m: float


@dataclass(slots=True)
class WorldState:
    sim_time_s: float
    active_vehicle_ids: set[str] = field(default_factory=set)
    control_zone: dict[str, VehicleObs] = field(default_factory=dict)
    entered_control: set[str] = field(default_factory=set)
    crossed_merge: set[str] = field(default_factory=set)
    entry_info: dict[str, dict[str, float | str]] = field(default_factory=dict)


@dataclass(slots=True)
class Plan:
    plan_time_s: float
    policy_name: str
    order: list[str] = field(default_factory=list)
    target_cross_time_s: dict[str, float] = field(default_factory=dict)
    eta_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ControlCommand:
    set_speed_mps: dict[str, float] = field(default_factory=dict)
    release_ids: set[str] = field(default_factory=set)
    takeover_speed_mode_by_id: dict[str, int] = field(default_factory=dict)
    restore_speed_mode_ids: set[str] = field(default_factory=set)

