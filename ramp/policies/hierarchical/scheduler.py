from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ramp.common.vehicle_defs import is_hdv
from ramp.policies.hierarchical.merge_point import MergePointManager, MergePointParams, VehicleState
from ramp.policies.hierarchical.state_collector_ext import ZoneAInfo
from ramp.policies.hierarchical.zone_a import ZoneAEvacuator
from ramp.runtime.types import MergeContract, Plan
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

    dp_result, fallback_occurred = _try_dp_mixed_with_fallback(
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
        scheduler_fallback=fallback_occurred,
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
    """Try dp_mixed_schedule; on infeasible HDV constraints fall back to all-CAV dp_schedule.

    Returns ``(schedule_result, fallback_occurred)`` so the caller can
    track how often the mixed scheduler is infeasible.
    """
    try:
        result = dp_mixed_schedule(
            main_seq=main_seq,
            ramp_seq=ramp_seq,
            veh_type_by_id=veh_type_by_id,
            t_min_cav_s=t_min_cav_s,
            hdv_predicted_time_s=hdv_predicted_time_s,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        )
        return result, False
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
            return ScheduleResult([], {}, 0.0, 0.0, 0.0), True
        return dp_schedule(
            main_seq=cav_main,
            ramp_seq=cav_ramp,
            t_min_s=t_min_cav_only,
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
        ), True


_GAP_ALIGN_KP = 0.15
_GAP_ALIGN_TARGET_GAP_M = 15.0
_GAP_ALIGN_MIN_SPEED_MPS = 3.0


def _compute_zone_c_speed_overrides(
    *,
    contracts: dict[str, MergeContract],
    control_zone_state: dict[str, dict[str, float | str]],
    zone_c_lane1_vehicles: list[tuple[str, float, float]] | None,
    ramp_vmax_mps: float,
) -> dict[str, float]:
    """Compute gap-alignment speeds for ramp CAVs on main_h3_0.

    For each ramp CAV with a contract, find the target predecessor on lane 1,
    compute longitudinal gap error, and apply P-control + speed feedforward:
        v_align = v_predecessor + k_p * (gap_actual - gap_target)
    Clamped to [_GAP_ALIGN_MIN_SPEED_MPS, ramp_vmax_mps].

    Only applies to CAVs currently on main_h3 lane 0 (the acceleration lane).
    """
    if not contracts or not zone_c_lane1_vehicles:
        return {}

    lane1_lookup: dict[str, tuple[float, float]] = {}
    for vid, pos, spd in zone_c_lane1_vehicles:
        lane1_lookup[vid] = (pos, spd)

    overrides: dict[str, float] = {}
    for veh_id, mc in contracts.items():
        state = control_zone_state.get(veh_id)
        if state is None:
            continue
        lane_id = str(state.get('lane_id', ''))
        if not lane_id.startswith('main_h3_0'):
            continue

        cav_pos = float(state.get('lane_pos', 0.0))
        cav_speed = float(state.get('speed', 0.0))

        pred_id = mc.target_predecessor_id
        if pred_id is not None and pred_id in lane1_lookup:
            pred_pos, pred_speed = lane1_lookup[pred_id]
            gap_actual = pred_pos - cav_pos
            gap_error = gap_actual - _GAP_ALIGN_TARGET_GAP_M
            v_align = pred_speed + _GAP_ALIGN_KP * gap_error
        else:
            v_align = cav_speed

        overrides[veh_id] = max(
            _GAP_ALIGN_MIN_SPEED_MPS,
            min(v_align, ramp_vmax_mps),
        )

    return overrides


_COOP_COMFORT_DECEL_MPS2 = 1.5
_COOP_MIN_SPEED_MPS = 5.0
_COOP_GAP_THRESHOLD_M = 20.0
_COOP_DELTA_V_MPS = 1.0


def _compute_zone_c_coop_overrides(
    *,
    contracts: dict[str, MergeContract],
    control_zone_state: dict[str, dict[str, float | str]],
    vehicle_types: dict[str, str],
    zone_c_lane1_vehicles: list[tuple[str, float, float]] | None,
    main_vmax_mps: float,
) -> dict[str, float]:
    """Compute cooperative speed adjustments for main-road CAVs near a merge gap.

    When a contract's target follower is a CAV on lane 1 and the rear gap is
    insufficient, gently reduce the follower's speed to widen the gap.
    """
    if not contracts or not zone_c_lane1_vehicles:
        return {}

    lane1_lookup: dict[str, tuple[float, float]] = {}
    for vid, pos, spd in zone_c_lane1_vehicles:
        lane1_lookup[vid] = (pos, spd)

    overrides: dict[str, float] = {}
    for _veh_id, mc in contracts.items():
        ego_state = control_zone_state.get(mc.vehicle_id)
        if ego_state is None:
            continue
        ego_lane_id = str(ego_state.get('lane_id', ''))
        if not ego_lane_id.startswith('main_h3_0'):
            continue
        ego_pos = float(ego_state.get('lane_pos', 0.0))

        foll_id = mc.target_follower_id
        if foll_id is None:
            continue
        foll_type = vehicle_types.get(foll_id, 'hdv')
        if foll_type != 'cav':
            continue
        if foll_id not in lane1_lookup:
            continue

        foll_pos, foll_speed = lane1_lookup[foll_id]
        rear_gap = ego_pos - foll_pos
        if rear_gap >= _COOP_GAP_THRESHOLD_M:
            continue

        coop_speed = max(
            foll_speed - _COOP_DELTA_V_MPS,
            _COOP_MIN_SPEED_MPS,
        )
        if foll_id in overrides:
            overrides[foll_id] = min(overrides[foll_id], coop_speed)
        else:
            overrides[foll_id] = coop_speed

    return overrides


def _build_contracts(
    *,
    plan: Plan,
    control_zone_state: dict[str, dict[str, float | str]],
    vehicle_types: dict[str, str],
    zone_c_lane1_vehicles: list[tuple[str, float, float]] | None,
) -> dict[str, MergeContract]:
    """Derive MergeContracts from the DP passing_order.

    For each ramp CAV in the order, identify the vehicles immediately before
    and after it in the merged sequence as its target predecessor and follower,
    then validate against physical positions on lane 1.
    """
    order = plan.order
    target_times = plan.target_cross_time_s
    if not order:
        return {}

    lane1_pos_by_id: dict[str, float] = {}
    if zone_c_lane1_vehicles:
        for vid, pos, _spd in zone_c_lane1_vehicles:
            lane1_pos_by_id[vid] = pos

    contracts: dict[str, MergeContract] = {}
    for rank, veh_id in enumerate(order):
        state = control_zone_state.get(veh_id)
        if state is None:
            continue
        if str(state.get('stream', '')) != 'ramp':
            continue
        raw_type = vehicle_types.get(veh_id, 'hdv')
        if raw_type != 'cav':
            continue

        predecessor_id: str | None = None
        follower_id: str | None = None
        for j in range(rank - 1, -1, -1):
            candidate = order[j]
            if candidate in lane1_pos_by_id or str(control_zone_state.get(candidate, {}).get('stream', '')) == 'main':
                predecessor_id = candidate
                break
        for j in range(rank + 1, len(order)):
            candidate = order[j]
            if candidate in lane1_pos_by_id or str(control_zone_state.get(candidate, {}).get('stream', '')) == 'main':
                follower_id = candidate
                break

        target_time = target_times.get(veh_id)
        if target_time is None:
            continue

        merge_window_half = 3.0
        hdv_as_partner = (
            (predecessor_id is not None and vehicle_types.get(predecessor_id, 'hdv') != 'cav')
            or (follower_id is not None and vehicle_types.get(follower_id, 'hdv') != 'cav')
        )

        contracts[veh_id] = MergeContract(
            vehicle_id=veh_id,
            sequence_rank=rank,
            target_predecessor_id=predecessor_id,
            target_follower_id=follower_id,
            merge_window_start_s=target_time - merge_window_half,
            merge_window_end_s=target_time + merge_window_half,
            expected_merge_time_s=target_time,
            fallback_allowed=hdv_as_partner,
        )

    return contracts


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
    contracts: dict[str, MergeContract] = field(default_factory=dict)
    zone_c_speed_overrides: dict[str, float] = field(default_factory=dict)
    zone_c_coop_overrides: dict[str, float] = field(default_factory=dict)
    scheduler_fallback_count: int = 0
    scheduler_replan_count: int = 0

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
            self.scheduler_replan_count += 1
            if self._cached_plan is not None and self._cached_plan.scheduler_fallback:
                self.scheduler_fallback_count += 1

        # --- Contract generation (runs on replan or when plan changes) ---
        if self._cached_plan is not None and self.replanned_last_call:
            self.contracts = _build_contracts(
                plan=self._cached_plan,
                control_zone_state=control_zone_state,
                vehicle_types=vehicle_types,
                zone_c_lane1_vehicles=zone_c_lane1_vehicles,
            )
        self._prune_stale_contracts(control_zone_state, crossed_merge)

        # --- Zone C speed overrides (every step) ---
        self.zone_c_speed_overrides = _compute_zone_c_speed_overrides(
            contracts=self.contracts,
            control_zone_state=control_zone_state,
            zone_c_lane1_vehicles=zone_c_lane1_vehicles,
            ramp_vmax_mps=self.ramp_vmax_mps,
        )
        self.zone_c_coop_overrides = _compute_zone_c_coop_overrides(
            contracts=self.contracts,
            control_zone_state=control_zone_state,
            vehicle_types=vehicle_types,
            zone_c_lane1_vehicles=zone_c_lane1_vehicles,
            main_vmax_mps=self.main_vmax_mps,
        )

        # --- Zone C: merge point management (every step) ---
        if self._merge_point_mgr is not None and zone_c_lane1_vehicles is not None:
            cav_states = _collect_zone_c_cav_states(
                vehicle_types=vehicle_types, traci=traci,
            )
            self.zone_c_actions = self._merge_point_mgr.update(
                sim_time_s=sim_time_s,
                cav_states=cav_states,
                lane1_vehicles=zone_c_lane1_vehicles,
                contracts=self.contracts,
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

    def _prune_stale_contracts(
        self,
        control_zone_state: dict[str, dict[str, float | str]],
        crossed_merge: set[str],
    ) -> None:
        """Remove contracts for vehicles that have crossed merge or left the zone."""
        stale = [
            vid for vid in self.contracts
            if vid in crossed_merge or vid not in control_zone_state
        ]
        for vid in stale:
            del self.contracts[vid]

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
    """Collect CAV states on main_h3 lanes 0 and 1 for Zone C merge evaluation.

    Lane 0 vehicles are candidates for new merge tracking.
    Lane 1 vehicles are needed to detect MERGING→MERGED completion
    (vehicles that just changed from L0 to L1).
    """
    cav_states: dict[str, VehicleState] = {}
    for lane_idx in (0, 1):
        lane_id = f'main_h3_{lane_idx}'
        veh_ids = traci.lane.getLastStepVehicleIDs(lane_id)
        for veh_id in veh_ids:
            vtype = vehicle_types.get(veh_id, '')
            if not vtype:
                vtype = traci.vehicle.getTypeID(veh_id)
            if is_hdv(vtype):
                continue
            pos = float(traci.vehicle.getLanePosition(veh_id))
            speed = float(traci.vehicle.getSpeed(veh_id))
            cav_states[veh_id] = VehicleState(
                edge_id='main_h3',
                lane_index=lane_idx,
                lane_pos_m=pos,
                speed_mps=speed,
            )
    return cav_states
