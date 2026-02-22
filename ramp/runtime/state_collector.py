from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _stream_from_route(route_edges: tuple[str, ...] | list[str]) -> str:
    if not route_edges:
        return 'unknown'
    first = route_edges[0]
    if first.startswith('main_'):
        return 'main'
    if first.startswith('ramp_'):
        return 'ramp'
    return 'unknown'


def _stream_vmax(stream: str, main_vmax_mps: float, ramp_vmax_mps: float) -> float:
    if stream == 'main':
        return main_vmax_mps
    if stream == 'ramp':
        return ramp_vmax_mps
    return max(main_vmax_mps, ramp_vmax_mps)


def _build_edge_length_cache(route_edges: tuple[str, ...], traci) -> dict[str, float]:
    lengths: dict[str, float] = {}
    for edge_id in route_edges:
        if edge_id not in lengths:
            lane_count = int(traci.edge.getLaneNumber(edge_id))
            if lane_count <= 0:
                lengths[edge_id] = 0.0
            else:
                lengths[edge_id] = float(traci.lane.getLength(f'{edge_id}_0'))
    return lengths


def _distance_to_merge(veh_id: str, merge_edge: str, traci) -> float | None:
    route_edges = tuple(traci.vehicle.getRoute(veh_id))
    if not route_edges or merge_edge not in route_edges:
        return None

    merge_idx = route_edges.index(merge_edge)
    route_idx = traci.vehicle.getRouteIndex(veh_id)
    if route_idx < 0:
        return None
    if route_idx >= merge_idx:
        return 0.0

    edge_lengths = _build_edge_length_cache(route_edges, traci)
    current_edge = route_edges[route_idx]
    lane_pos = float(traci.vehicle.getLanePosition(veh_id))
    dist = max(edge_lengths[current_edge] - lane_pos, 0.0)
    for edge_id in route_edges[route_idx + 1 : merge_idx]:
        dist += edge_lengths[edge_id]
    return dist


@dataclass(slots=True)
class CollectedState:
    active_vehicle_ids: set[str]
    control_zone_state: dict[str, dict[str, float | str]]


@dataclass(slots=True)
class StateCollector:
    control_zone_length_m: float
    merge_edge: str
    policy: str
    main_vmax_mps: float
    ramp_vmax_mps: float
    fifo_gap_s: float
    entered_control: set[str] = field(default_factory=set)
    crossed_merge: set[str] = field(default_factory=set)
    entry_info: dict[str, dict[str, float | str]] = field(default_factory=dict)
    cross_time: dict[str, float] = field(default_factory=dict)
    prev_stopped: dict[str, bool] = field(default_factory=dict)
    stop_count: int = 0
    entry_order: list[str] = field(default_factory=list)
    entry_rank: dict[str, int] = field(default_factory=dict)
    fifo_natural_eta: dict[str, float] = field(default_factory=dict)
    fifo_target_time: dict[str, float] = field(default_factory=dict)
    fifo_last_assigned_target: float | None = None

    def collect(self, *, sim_time: float, traci: Any) -> CollectedState:
        active_vehicle_ids = set(traci.vehicle.getIDList())
        control_zone_state: dict[str, dict[str, float | str]] = {}

        for veh_id in sorted(active_vehicle_ids):
            route_edges = tuple(traci.vehicle.getRoute(veh_id))
            stream = _stream_from_route(route_edges)
            road_id = traci.vehicle.getRoadID(veh_id)

            if road_id == self.merge_edge and veh_id not in self.crossed_merge:
                self.crossed_merge.add(veh_id)
                self.cross_time[veh_id] = sim_time

            d_to_merge = _distance_to_merge(veh_id, self.merge_edge, traci)
            if d_to_merge is None or d_to_merge <= 0:
                continue
            if d_to_merge > self.control_zone_length_m:
                continue

            if veh_id not in self.entered_control:
                self.entered_control.add(veh_id)
                self.entry_order.append(veh_id)
                self.entry_rank[veh_id] = len(self.entry_order)
                self.entry_info[veh_id] = {
                    't_entry': sim_time,
                    'd_entry': d_to_merge,
                    'stream': stream,
                }
                if self.policy == 'fifo':
                    stream_vmax = _stream_vmax(stream, self.main_vmax_mps, self.ramp_vmax_mps)
                    natural_eta_at_entry = sim_time + d_to_merge / stream_vmax
                    if self.fifo_last_assigned_target is None:
                        target_cross_time = max(natural_eta_at_entry, sim_time + self.fifo_gap_s)
                    else:
                        target_cross_time = max(
                            natural_eta_at_entry,
                            self.fifo_last_assigned_target + self.fifo_gap_s,
                        )
                    self.fifo_natural_eta[veh_id] = natural_eta_at_entry
                    self.fifo_target_time[veh_id] = target_cross_time
                    self.fifo_last_assigned_target = target_cross_time

            speed = float(traci.vehicle.getSpeed(veh_id))
            is_stopped = speed < 0.1
            if is_stopped and not self.prev_stopped.get(veh_id, False):
                self.stop_count += 1
            self.prev_stopped[veh_id] = is_stopped

            control_zone_state[veh_id] = {
                'stream': stream,
                'edge_id': road_id,
                'lane_id': traci.vehicle.getLaneID(veh_id),
                'lane_pos': float(traci.vehicle.getLanePosition(veh_id)),
                'd_to_merge': d_to_merge,
                'speed': speed,
                'accel': float(traci.vehicle.getAcceleration(veh_id)),
            }

        return CollectedState(
            active_vehicle_ids=active_vehicle_ids,
            control_zone_state=control_zone_state,
        )

