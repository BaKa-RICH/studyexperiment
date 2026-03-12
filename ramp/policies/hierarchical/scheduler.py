from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ramp.common.vehicle_defs import is_hdv
from ramp.policies.hierarchical.merge_point import MergePointManager, MergePointParams, VehicleState
from ramp.policies.hierarchical.state_collector_ext import ZoneAInfo
from ramp.policies.hierarchical.zone_a import ZoneAEvacuator
from ramp.runtime.types import Plan
from ramp.scheduler.arrival_time import minimum_arrival_time_at_on_ramp
from ramp.scheduler.dp import dp_schedule
from ramp.scheduler.dp_mixed import dp_mixed_schedule

MERGE_POLICY_FIXED = 'fixed'
MERGE_POLICY_FLEXIBLE = 'flexible'

logger = logging.getLogger(__name__)

_HDV_MIN_SPEED_MPS = 0.1


def _on_conflict_lane(stream: str, edge_id: str, lane_id: str) -> bool:
    """DP scheduling only considers vehicles on conflict lanes."""
    lane_index = int(lane_id.rsplit('_', 1)[-1])
    if stream == 'ramp':
        return edge_id in {'ramp_h6', 'main_h3'} and lane_index in {0, 1}
    if stream == 'main':
        return (
            (edge_id == 'main_h2' and lane_index == 0)
            or (edge_id == 'main_h3' and lane_index == 1)
        )
    return False


def _stream_vmax(
    stream: str,
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    *,
    aux_vmax_mps: float | None = None,
    lane_id: str = '',
) -> float:
    if stream == 'main':
        return main_vmax_mps
    if stream == 'ramp':
        if aux_vmax_mps is not None and lane_id.startswith('main_h3_'):
            return aux_vmax_mps
        return ramp_vmax_mps
    return max(main_vmax_mps, ramp_vmax_mps)


def _compute_plan_once(
    *,
    sim_time_s: float,
    control_zone_state: dict[str, dict[str, float | str]],
    crossed_merge: set[str],
    entry_info: dict[str, dict[str, float | str]],
    vehicle_types: dict[str, str],
    traci: Any,
    delta_1_s: float,
    delta_2_s: float,
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    aux_vmax_mps: float | None = None,
) -> Plan:
    dp_candidates = [
        veh_id for veh_id in control_zone_state if veh_id not in crossed_merge
    ]

    veh_type_by_id: dict[str, str] = {}
    t_min_cav_s: dict[str, float] = {}
    hdv_predicted_time_s: dict[str, float] = {}
    eta_s: dict[str, float] = {}

    for veh_id in dp_candidates:
        vehicle_state = control_zone_state[veh_id]
        stream = str(vehicle_state['stream'])
        d_to_merge = float(vehicle_state['d_to_merge'])
        speed = float(vehicle_state['speed'])
        lane_id = str(vehicle_state.get('lane_id', ''))

        raw_type = vehicle_types.get(veh_id, 'hdv')
        vtype = 'cav' if raw_type == 'cav' else 'hdv'
        veh_type_by_id[veh_id] = vtype

        stream_vmax = _stream_vmax(
            stream, main_vmax_mps, ramp_vmax_mps,
            aux_vmax_mps=aux_vmax_mps, lane_id=lane_id,
        )

        if vtype == 'cav':
            accel = float(traci.vehicle.getAccel(veh_id))
            t_min = minimum_arrival_time_at_on_ramp(
                t_now_s=sim_time_s,
                distance_m=d_to_merge,
                speed_mps=speed,
                a_max_mps2=accel,
                v_max_mps=stream_vmax,
            )
            t_min_cav_s[veh_id] = t_min
            eta_s[veh_id] = t_min
        else:
            effective_speed = max(speed, _HDV_MIN_SPEED_MPS)
            t_pred = sim_time_s + d_to_merge / effective_speed
            hdv_predicted_time_s[veh_id] = t_pred
            eta_s[veh_id] = t_pred

    main_seq = sorted(
        [v for v in dp_candidates
         if str(control_zone_state[v]['stream']) == 'main'
         and _on_conflict_lane('main',
                               str(control_zone_state[v]['edge_id']),
                               str(control_zone_state[v]['lane_id']))],
        key=lambda v: (eta_s[v], v),
    )
    ramp_seq = sorted(
        [v for v in dp_candidates
         if str(control_zone_state[v]['stream']) == 'ramp'
         and _on_conflict_lane('ramp',
                               str(control_zone_state[v]['edge_id']),
                               str(control_zone_state[v]['lane_id']))],
        key=lambda v: (eta_s[v], v),
    )

    dp_result = _try_dp_mixed_with_fallback(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        veh_type_by_id=veh_type_by_id,
        t_min_cav_s=t_min_cav_s,
        hdv_predicted_time_s=hdv_predicted_time_s,
        eta_s=eta_s,
        delta_1_s=delta_1_s,
        delta_2_s=delta_2_s,
    )

    plan_eta: dict[str, float] = {}
    for veh_id in dp_result.passing_order:
        if veh_id in eta_s:
            plan_eta[veh_id] = eta_s[veh_id]

    return Plan(
        plan_time_s=sim_time_s,
        policy_name='hierarchical',
        order=dp_result.passing_order,
        target_cross_time_s=dict(dp_result.target_cross_time_s),
        eta_s=plan_eta,
    )


def _try_dp_mixed_with_fallback(
    *,
    main_seq: list[str],
    ramp_seq: list[str],
    veh_type_by_id: dict[str, str],
    t_min_cav_s: dict[str, float],
    hdv_predicted_time_s: dict[str, float],
    eta_s: dict[str, float],
    delta_1_s: float,
    delta_2_s: float,
):
    """Try dp_mixed_schedule; on infeasible HDV constraints fall back to all-CAV dp_schedule."""
    try:
        return dp_mixed_schedule(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            veh_type_by_id=veh_type_by_id,
            t_min_cav_s=t_min_cav_s,
            hdv_predicted_time_s=hdv_predicted_time_s,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )
    except (ValueError, KeyError) as exc:
        logger.warning(
            'dp_mixed_schedule failed (%s), falling back to CAV-only dp_schedule',
            exc,
        )
        cav_main = [v for v in main_seq if veh_type_by_id.get(v) == 'cav']
        cav_ramp = [v for v in ramp_seq if veh_type_by_id.get(v) == 'cav']
        t_min_cav_only: dict[str, float] = {}
        for veh_id in cav_main + cav_ramp:
            t_min_cav_only[veh_id] = eta_s.get(veh_id, 0.0)
        if not cav_main and not cav_ramp:
            from ramp.scheduler.dp import ScheduleResult
            return ScheduleResult([], {}, 0.0, 0.0, 0.0)
        return dp_schedule(
            main_seq=cav_main,
            ramp_seq=cav_ramp,
            t_min_s=t_min_cav_only,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )


@dataclass
class HierarchicalScheduler:
    delta_1_s: float
    delta_2_s: float
    main_vmax_mps: float
    ramp_vmax_mps: float
    merge_policy: str = MERGE_POLICY_FLEXIBLE
    replan_interval_s: float = 0.5
    aux_vmax_mps: float | None = None
    zone_a_interval_s: float = 1.0
    _last_replan_time_s: float | None = None
    _cached_plan: Plan | None = None
    replanned_last_call: bool = False
    _merge_point_mgr: MergePointManager | None = None
    _zone_a_evacuator: ZoneAEvacuator | None = None
    _last_zone_a_time_s: float | None = None
    zone_a_actions: dict[str, tuple[int, float]] = field(default_factory=dict)
    zone_c_actions: dict[str, tuple[int, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.merge_policy not in (MERGE_POLICY_FIXED, MERGE_POLICY_FLEXIBLE):
            raise ValueError(f'Unknown merge_policy: {self.merge_policy!r}')
        if self._merge_point_mgr is None:
            if self.merge_policy == MERGE_POLICY_FIXED:
                default_params = MergePointParams()
                fixed_params = MergePointParams(
                    search_start_pos_m=default_params.lane0_length_m - default_params.fallback_buffer_m,
                )
                self._merge_point_mgr = MergePointManager(params=fixed_params)
            else:
                self._merge_point_mgr = MergePointManager()
        if self._zone_a_evacuator is None:
            self._zone_a_evacuator = ZoneAEvacuator(
                v_limit_mps=self.main_vmax_mps,
            )

    def compute_plan(
        self,
        *,
        sim_time_s: float,
        control_zone_state: dict[str, dict[str, float | str]],
        crossed_merge: set[str],
        entry_info: dict[str, dict[str, float | str]],
        vehicle_types: dict[str, str],
        traci: Any,
        zone_a_info: ZoneAInfo | None = None,
        zone_c_lane1_vehicles: list[tuple[str, float, float]] | None = None,
    ) -> Plan:
        self.replanned_last_call = False

        # --- Zone A: upstream evacuation (every zone_a_interval_s) ---
        need_zone_a = (
            self._last_zone_a_time_s is None
            or sim_time_s - self._last_zone_a_time_s
            >= self.zone_a_interval_s - 1e-9
        )
        if need_zone_a and self._zone_a_evacuator is not None:
            self.zone_a_actions = self._zone_a_evacuator.evaluate(
                sim_time_s=sim_time_s,
                zone_a_info=zone_a_info,
                vehicle_types=vehicle_types,
                traci=traci,
            )
            self._last_zone_a_time_s = sim_time_s

        # --- Zone B: DP scheduling (every replan_interval_s) ---
        need_replan = (
            self.replan_interval_s <= 0
            or self._cached_plan is None
            or self._last_replan_time_s is None
            or sim_time_s - self._last_replan_time_s >= self.replan_interval_s - 1e-9
        )

        if need_replan:
            self._cached_plan = _compute_plan_once(
                sim_time_s=sim_time_s,
                control_zone_state=control_zone_state,
                crossed_merge=crossed_merge,
                entry_info=entry_info,
                vehicle_types=vehicle_types,
                traci=traci,
                delta_1_s=self.delta_1_s,
                delta_2_s=self.delta_2_s,
                main_vmax_mps=self.main_vmax_mps,
                ramp_vmax_mps=self.ramp_vmax_mps,
                aux_vmax_mps=self.aux_vmax_mps,
            )
            self._last_replan_time_s = sim_time_s
            self.replanned_last_call = True

        # --- Zone C: merge point management (every step) ---
        if self._merge_point_mgr is not None and zone_c_lane1_vehicles is not None:
            cav_states = _collect_zone_c_cav_states(
                vehicle_types=vehicle_types, traci=traci,
            )
            self.zone_c_actions = self._merge_point_mgr.update(
                sim_time_s=sim_time_s,
                cav_states=cav_states,
                lane1_vehicles=zone_c_lane1_vehicles,
            )
            if self.zone_c_actions:
                logger.info(
                    '[ZoneC] t=%.1f actions=%s merge_history_len=%d',
                    sim_time_s,
                    {vid: f'lane={a[0]},dur={a[1]:.1f}s' for vid, a in self.zone_c_actions.items()},
                    len(self._merge_point_mgr.merge_history),
                )

        return self._project_cached_plan(
            sim_time_s=sim_time_s,
            control_zone_state=control_zone_state,
            crossed_merge=crossed_merge,
        )

    def _project_cached_plan(
        self,
        *,
        sim_time_s: float,
        control_zone_state: dict[str, dict[str, float | str]],
        crossed_merge: set[str],
    ) -> Plan:
        if self._cached_plan is None:
            return Plan(plan_time_s=sim_time_s, policy_name='hierarchical')

        active_ids = {
            veh_id for veh_id in control_zone_state if veh_id not in crossed_merge
        }
        order = [veh_id for veh_id in self._cached_plan.order if veh_id in active_ids]
        target_cross_time_s = {
            veh_id: self._cached_plan.target_cross_time_s[veh_id]
            for veh_id in order
            if veh_id in self._cached_plan.target_cross_time_s
        }
        eta_s = {
            veh_id: self._cached_plan.eta_s[veh_id]
            for veh_id in order
            if veh_id in self._cached_plan.eta_s
        }
        return Plan(
            plan_time_s=self._cached_plan.plan_time_s,
            policy_name='hierarchical',
            order=order,
            target_cross_time_s=target_cross_time_s,
            eta_s=eta_s,
        )


def _collect_zone_c_cav_states(
    *,
    vehicle_types: dict[str, str],
    traci: Any,
) -> dict[str, VehicleState]:
    """Collect ramp-stream CAV states on main_h3 lane 0 for Zone C merge evaluation."""
    cav_states: dict[str, VehicleState] = {}
    lane_id = 'main_h3_0'
    veh_ids = traci.lane.getLastStepVehicleIDs(lane_id)
    for veh_id in veh_ids:
        vtype = vehicle_types.get(veh_id, '')
        if not vtype:
            vtype = traci.vehicle.getTypeID(veh_id)
        if vtype != 'cav':
            continue
        pos = float(traci.vehicle.getLanePosition(veh_id))
        speed = float(traci.vehicle.getSpeed(veh_id))
        cav_states[veh_id] = VehicleState(
            edge_id='main_h3',
            lane_index=0,
            lane_pos_m=pos,
            speed_mps=speed,
        )
    return cav_states
