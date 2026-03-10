from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ramp.runtime.types import ControlCommand


@dataclass(slots=True)
class ControllerApplyResult:
    takeover_ids: set[str] = field(default_factory=set)
    restored_ids: set[str] = field(default_factory=set)
    released_ids: set[str] = field(default_factory=set)
    commit_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Controller:
    traci: Any
    takeover_speed_mode: int = 23
    ramp_lc_target_lane: int = 1
    controlled_vehicle_ids: set[str] = field(default_factory=set)
    original_speed_mode_by_vehicle: dict[str, int] = field(default_factory=dict)

    def _is_commit_vehicle(self, veh_id: str) -> bool:
        road_id = str(self.traci.vehicle.getRoadID(veh_id))
        return road_id.startswith(':n_merge')

    def _takeover(self, veh_id: str) -> bool:
        if veh_id in self.original_speed_mode_by_vehicle:
            return False
        if self.traci.vehicle.getTypeID(veh_id) == 'hdv':
            return False
        original = int(self.traci.vehicle.getSpeedMode(veh_id))
        self.original_speed_mode_by_vehicle[veh_id] = original
        self.traci.vehicle.setSpeedMode(veh_id, self.takeover_speed_mode)
        return True

    def _restore(self, veh_id: str, active_vehicle_ids: set[str]) -> bool:
        original = self.original_speed_mode_by_vehicle.pop(veh_id, None)
        if original is None:
            return False
        if veh_id in active_vehicle_ids:
            self.traci.vehicle.setSpeedMode(veh_id, int(original))
        return True

    def _execute_lane_changes(
        self, command: ControlCommand, active_vehicle_ids: set[str]
    ) -> set[str]:
        executed_ids: set[str] = set()
        for veh_id, (lane_index, duration) in command.lane_change_targets.items():
            if veh_id not in active_vehicle_ids:
                continue
            self.traci.vehicle.changeLane(veh_id, int(lane_index), float(duration))
            executed_ids.add(veh_id)
        return executed_ids

    def _apply_lane_change_mode_overrides(
        self, command: ControlCommand, active_vehicle_ids: set[str]
    ) -> None:
        for veh_id, mode in command.lane_change_mode_overrides.items():
            if veh_id not in active_vehicle_ids:
                continue
            self.traci.vehicle.setLaneChangeMode(veh_id, int(mode))

    def apply(
        self, *, command: ControlCommand, active_vehicle_ids: set[str]
    ) -> ControllerApplyResult:
        result = ControllerApplyResult()
        self._apply_lane_change_mode_overrides(
            command=command, active_vehicle_ids=active_vehicle_ids
        )
        lane_change_ids = self._execute_lane_changes(
            command=command, active_vehicle_ids=active_vehicle_ids
        )
        if lane_change_ids:
            pass
        current_controlled = set(command.set_speed_mps)
        for veh_id, speed_mps in command.set_speed_mps.items():
            if veh_id not in active_vehicle_ids:
                continue
            if self.traci.vehicle.getTypeID(veh_id) == 'hdv':
                continue
            if self._takeover(veh_id):
                result.takeover_ids.add(veh_id)
            if self._is_commit_vehicle(veh_id):
                # Vehicle has entered the merge junction internal edge; do not re-brake it.
                self.traci.vehicle.setSpeed(veh_id, -1)
                result.commit_ids.add(veh_id)
            else:
                self.traci.vehicle.setSpeed(veh_id, speed_mps)

        to_release = (self.controlled_vehicle_ids - current_controlled) | set(command.release_ids)
        for veh_id in to_release:
            if veh_id in active_vehicle_ids:
                self.traci.vehicle.setSpeed(veh_id, -1)
                result.released_ids.add(veh_id)
            if self._restore(veh_id, active_vehicle_ids):
                result.restored_ids.add(veh_id)
        self.controlled_vehicle_ids = {veh_id for veh_id in current_controlled if veh_id in active_vehicle_ids}
        return result

    def apply_lane_change_modes(
        self,
        *,
        control_zone_state: dict[str, dict[str, float | str]],
    ) -> None:
        LC_MODE_PROHIBIT_ALL = 0
        for veh_id, vehicle_state in control_zone_state.items():
            stream = str(vehicle_state['stream'])
            edge_id = str(vehicle_state['edge_id'])
            lane_id = str(vehicle_state['lane_id'])
            if edge_id != 'main_h3':
                continue
            if stream == 'main':
                self.traci.vehicle.setLaneChangeMode(veh_id, LC_MODE_PROHIBIT_ALL)
            elif stream == 'ramp':
                lane_index = int(lane_id.split('_')[-1]) if '_' in lane_id else -1
                if lane_index == 0:
                    pass
                elif lane_index >= 1 and self.ramp_lc_target_lane != -1:
                    if lane_index >= self.ramp_lc_target_lane:
                        self.traci.vehicle.setLaneChangeMode(veh_id, LC_MODE_PROHIBIT_ALL)

    def release_all(self, *, active_vehicle_ids: set[str]) -> ControllerApplyResult:
        result = ControllerApplyResult()
        for veh_id in self.controlled_vehicle_ids:
            if veh_id in active_vehicle_ids:
                self.traci.vehicle.setSpeed(veh_id, -1)
                result.released_ids.add(veh_id)
            if self._restore(veh_id, active_vehicle_ids):
                result.restored_ids.add(veh_id)
        for veh_id in list(self.original_speed_mode_by_vehicle):
            if self._restore(veh_id, active_vehicle_ids):
                result.restored_ids.add(veh_id)
        self.controlled_vehicle_ids = set()
        return result
