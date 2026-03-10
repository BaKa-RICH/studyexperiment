from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ramp.runtime.types import Plan
from ramp.scheduler.arrival_time import minimum_arrival_time_at_on_ramp
from ramp.scheduler.dp import dp_schedule
from ramp.scheduler.dp_mixed import dp_mixed_schedule

logger = logging.getLogger(__name__)

_HDV_MIN_SPEED_MPS = 0.1


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
        vtype = raw_type if raw_type in ('cav', 'hdv') else 'hdv'
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
        [v for v in dp_candidates if str(control_zone_state[v]['stream']) == 'main'],
        key=lambda v: (eta_s[v], v),
    )
    ramp_seq = sorted(
        [v for v in dp_candidates if str(control_zone_state[v]['stream']) == 'ramp'],
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
            'dp_mixed_schedule failed (%s), falling back to all-CAV dp_schedule',
            exc,
        )
        t_min_all: dict[str, float] = {}
        for veh_id in main_seq + ramp_seq:
            t_min_all[veh_id] = eta_s[veh_id]
        return dp_schedule(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            t_min_s=t_min_all,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )


@dataclass(slots=True)
class HierarchicalScheduler:
    delta_1_s: float
    delta_2_s: float
    main_vmax_mps: float
    ramp_vmax_mps: float
    replan_interval_s: float = 0.5
    aux_vmax_mps: float | None = None
    _last_replan_time_s: float | None = None
    _cached_plan: Plan | None = None
    replanned_last_call: bool = False

    def compute_plan(
        self,
        *,
        sim_time_s: float,
        control_zone_state: dict[str, dict[str, float | str]],
        crossed_merge: set[str],
        entry_info: dict[str, dict[str, float | str]],
        vehicle_types: dict[str, str],
        traci: Any,
    ) -> Plan:
        self.replanned_last_call = False
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
