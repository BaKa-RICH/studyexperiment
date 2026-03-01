from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ramp.runtime.types import Plan
from ramp.scheduler.arrival_time import minimum_arrival_time_at_on_ramp
from ramp.scheduler.dp import dp_schedule


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
    traci: Any,
    delta_1_s: float,
    delta_2_s: float,
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    aux_vmax_mps: float | None = None,
) -> Plan:
    dp_candidates = [veh_id for veh_id in control_zone_state if veh_id not in crossed_merge]
    main_seq = sorted(
        [
            veh_id
            for veh_id in dp_candidates
            if str(control_zone_state[veh_id]['stream']) == 'main'
        ],
        key=lambda vehicle_id: (
            float(entry_info[vehicle_id]['t_entry']),
            vehicle_id,
        ),
    )
    ramp_seq = sorted(
        [
            veh_id
            for veh_id in dp_candidates
            if str(control_zone_state[veh_id]['stream']) == 'ramp'
        ],
        key=lambda vehicle_id: (
            float(entry_info[vehicle_id]['t_entry']),
            vehicle_id,
        ),
    )

    t_min_s: dict[str, float] = {}
    for veh_id in main_seq + ramp_seq:
        vehicle_state = control_zone_state[veh_id]
        stream = str(vehicle_state['stream'])
        d_to_merge = float(vehicle_state['d_to_merge'])
        speed = float(vehicle_state['speed'])
        accel = float(traci.vehicle.getAccel(veh_id))
        lane_id = str(vehicle_state.get('lane_id', ''))
        stream_vmax = _stream_vmax(
            stream, main_vmax_mps, ramp_vmax_mps,
            aux_vmax_mps=aux_vmax_mps, lane_id=lane_id,
        )
        t_min_s[veh_id] = minimum_arrival_time_at_on_ramp(
            t_now_s=sim_time_s,
            distance_m=d_to_merge,
            speed_mps=speed,
            a_max_mps2=accel,
            v_max_mps=stream_vmax,
        )

    dp_result = dp_schedule(
        main_seq=main_seq,
        ramp_seq=ramp_seq,
        t_min_s=t_min_s,
        delta_1_s=delta_1_s,
        delta_2_s=delta_2_s,
    )
    return Plan(
        plan_time_s=sim_time_s,
        policy_name='dp',
        order=dp_result.passing_order,
        target_cross_time_s=dict(dp_result.target_cross_time_s),
        # Reuse Stage 1 plans.csv field name `natural_eta`; for dp this is t_min.
        eta_s=dict(t_min_s),
    )


@dataclass(slots=True)
class DPScheduler:
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
        traci: Any,
    ) -> Plan:
        self.replanned_last_call = False
        if self.replan_interval_s <= 0:
            self._cached_plan = _compute_plan_once(
                sim_time_s=sim_time_s,
                control_zone_state=control_zone_state,
                crossed_merge=crossed_merge,
                entry_info=entry_info,
                traci=traci,
                delta_1_s=self.delta_1_s,
                delta_2_s=self.delta_2_s,
                main_vmax_mps=self.main_vmax_mps,
                ramp_vmax_mps=self.ramp_vmax_mps,
                aux_vmax_mps=self.aux_vmax_mps,
            )
            self._last_replan_time_s = sim_time_s
            self.replanned_last_call = True
        elif self._cached_plan is None or self._last_replan_time_s is None:
            self._cached_plan = _compute_plan_once(
                sim_time_s=sim_time_s,
                control_zone_state=control_zone_state,
                crossed_merge=crossed_merge,
                entry_info=entry_info,
                traci=traci,
                delta_1_s=self.delta_1_s,
                delta_2_s=self.delta_2_s,
                main_vmax_mps=self.main_vmax_mps,
                ramp_vmax_mps=self.ramp_vmax_mps,
                aux_vmax_mps=self.aux_vmax_mps,
            )
            self._last_replan_time_s = sim_time_s
            self.replanned_last_call = True
        elif sim_time_s - self._last_replan_time_s >= self.replan_interval_s - 1e-9:
            self._cached_plan = _compute_plan_once(
                sim_time_s=sim_time_s,
                control_zone_state=control_zone_state,
                crossed_merge=crossed_merge,
                entry_info=entry_info,
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
            return Plan(plan_time_s=sim_time_s, policy_name='dp')

        active_ids = {
            veh_id for veh_id in control_zone_state if veh_id not in crossed_merge
        }
        order = [veh_id for veh_id in self._cached_plan.order if veh_id in active_ids]
        target_cross_time_s = {
            veh_id: self._cached_plan.target_cross_time_s[veh_id] for veh_id in order
        }
        eta_s = {veh_id: self._cached_plan.eta_s[veh_id] for veh_id in order}
        return Plan(
            plan_time_s=self._cached_plan.plan_time_s,
            policy_name='dp',
            order=order,
            target_cross_time_s=target_cross_time_s,
            eta_s=eta_s,
        )
