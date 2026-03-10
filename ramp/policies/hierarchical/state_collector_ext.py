from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ramp.runtime.state_collector import StateCollector, CollectedState


@dataclass(slots=True)
class ZoneAInfo:
    lane_densities: dict[int, float]     # lane_index -> vehicles/km
    lane_avg_speeds: dict[int, float]    # lane_index -> m/s
    lane_vehicle_counts: dict[int, int]  # lane_index -> count
    edge_length_m: float


@dataclass(slots=True)
class HierarchicalState:
    base_state: CollectedState
    vehicle_types: dict[str, str]        # veh_id -> 'cav'|'hdv'
    zone_a_info: ZoneAInfo | None
    zone_c_lane1_vehicles: list[tuple[str, float, float]]  # [(veh_id, pos, speed)]


@dataclass(slots=True)
class HierarchicalStateCollector:
    base_collector: StateCollector
    traci: Any

    def collect(self, *, sim_time: float, traci: Any) -> HierarchicalState:
        # 1. Base collection
        base_state = self.base_collector.collect(sim_time=sim_time, traci=traci)
        
        vehicle_types: dict[str, str] = {}
        
        # 3. Annotate base state vehicles with type
        for veh_id in base_state.control_zone_state:
            vehicle_types[veh_id] = traci.vehicle.getTypeID(veh_id)
            
        # 2a. Zone A Info (main_h2)
        zone_a_info = None
        try:
            edge_id = 'main_h2'
            lane_count = traci.edge.getLaneNumber(edge_id)
            if lane_count > 0:
                edge_length_m = traci.lane.getLength(f'{edge_id}_0')
                lane_densities: dict[int, float] = {}
                lane_avg_speeds: dict[int, float] = {}
                lane_vehicle_counts: dict[int, int] = {}
                
                for lane_idx in range(lane_count):
                    lane_id = f'{edge_id}_{lane_idx}'
                    veh_ids = traci.lane.getLastStepVehicleIDs(lane_id)
                    count = len(veh_ids)
                    lane_vehicle_counts[lane_idx] = count
                    
                    if edge_length_m > 0:
                        lane_densities[lane_idx] = (count / edge_length_m) * 1000.0
                    else:
                        lane_densities[lane_idx] = 0.0
                        
                    if count > 0:
                        total_speed = sum(traci.vehicle.getSpeed(vid) for vid in veh_ids)
                        lane_avg_speeds[lane_idx] = total_speed / count
                    else:
                        lane_avg_speeds[lane_idx] = 0.0
                        
                    # Also collect types for these vehicles if not already collected
                    for vid in veh_ids:
                        if vid not in vehicle_types:
                            vehicle_types[vid] = traci.vehicle.getTypeID(vid)
                            
                zone_a_info = ZoneAInfo(
                    lane_densities=lane_densities,
                    lane_avg_speeds=lane_avg_speeds,
                    lane_vehicle_counts=lane_vehicle_counts,
                    edge_length_m=edge_length_m
                )
        except Exception:
            pass

        # 2b. Zone C Info (main_h3 lane 1)
        zone_c_lane1_vehicles: list[tuple[str, float, float]] = []
        try:
            lane_id = 'main_h3_1'
            veh_ids = traci.lane.getLastStepVehicleIDs(lane_id)
            for vid in veh_ids:
                pos = traci.vehicle.getLanePosition(vid)
                speed = traci.vehicle.getSpeed(vid)
                zone_c_lane1_vehicles.append((vid, pos, speed))
                if vid not in vehicle_types:
                    vehicle_types[vid] = traci.vehicle.getTypeID(vid)
        except Exception:
            pass

        return HierarchicalState(
            base_state=base_state,
            vehicle_types=vehicle_types,
            zone_a_info=zone_a_info,
            zone_c_lane1_vehicles=zone_c_lane1_vehicles
        )
