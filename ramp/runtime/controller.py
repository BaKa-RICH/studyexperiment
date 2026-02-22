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
    controlled_vehicle_ids: set[str] = field(default_factory=set)
    original_speed_mode_by_vehicle: dict[str, int] = field(default_factory=dict)

    def _is_commit_vehicle(self, veh_id: str) -> bool:
        road_id = str(self.traci.vehicle.getRoadID(veh_id))
        return road_id.startswith(':n_merge')

    def _takeover(self, veh_id: str) -> bool:
        if veh_id in self.original_speed_mode_by_vehicle:
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

    def apply(
        self, *, command: ControlCommand, active_vehicle_ids: set[str]
    ) -> ControllerApplyResult:
        result = ControllerApplyResult()
        current_controlled = set(command.set_speed_mps)
        for veh_id, speed_mps in command.set_speed_mps.items():
            if veh_id not in active_vehicle_ids:
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
