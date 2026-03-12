import argparse
import csv
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from ramp.policies.dp.command_builder import build_command as build_dp_command
from ramp.policies.dp.scheduler import DPScheduler
from ramp.policies.fifo.command_builder import build_command as build_fifo_command
from ramp.policies.fifo.scheduler import compute_plan as compute_fifo_plan
from ramp.policies.hierarchical.command_builder import build_command as build_hierarchical_command
from ramp.policies.hierarchical.scheduler import HierarchicalScheduler
from ramp.policies.hierarchical.state_collector_ext import HierarchicalStateCollector
from ramp.policies.no_control.command_builder import build_command as build_no_control_command
from ramp.policies.no_control.scheduler import compute_plan as compute_no_control_plan
from ramp.experiments.evidence_chain import (
    CONTRACT_FIELDS,
    CONTROL_FIELDS,
    FEEDBACK_FIELDS,
    SPEED_MISMATCH_THRESHOLD_MPS,
    attach_actual_neighbors,
    build_contract_row,
    build_evidence_metrics,
    expected_merge_position_m,
    merge_window_half_span_s,
    percentile as _percentile,
    resolve_merge_policy,
)
from ramp.runtime.controller import Controller
from ramp.runtime.simulation_driver import SimulationDriver
from ramp.runtime.state_collector import StateCollector
from ramp.runtime.takeover import (
    TakeoverMode,
    log_mode_warning,
    parse_takeover_mode,
)
from ramp.runtime.ttc import build_ttc_metrics, collect_ttc_samples


def _ensure_sumo_tools_on_path() -> None:
    sumo_home = os.environ.get('SUMO_HOME')
    if not sumo_home:
        return
    tools_dir = Path(sumo_home) / 'tools'
    if tools_dir.exists():
        tools_dir_str = str(tools_dir)
        if tools_dir_str not in sys.path:
            sys.path.insert(0, tools_dir_str)


def _pick_sumo_binary(gui: bool) -> str:
    import sumolib

    if gui:
        return sumolib.checkBinary('sumo-gui')
    return sumolib.checkBinary('sumo')


def _resolve_sumocfg(repo_root: Path, scenario: str) -> Path:
    cfg = repo_root / 'ramp' / 'scenarios' / scenario / f'{scenario}.sumocfg'
    if not cfg.exists():
        raise FileNotFoundError(f'Scenario config not found: {cfg}')
    return cfg


def _timestamp() -> str:
    return time.strftime('%Y%m%d-%H%M%S', time.localtime())


def _stream_from_route(route_edges: tuple[str, ...] | list[str]) -> str:
    if not route_edges:
        return 'unknown'
    first = route_edges[0]
    if first.startswith('main_'):
        return 'main'
    if first.startswith('ramp_'):
        return 'ramp'
    return 'unknown'


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


def _collision_to_row(sim_time: float, collision) -> dict[str, str | float]:
    row: dict[str, str | float] = {'time': sim_time}
    for key in (
        'collider',
        'victim',
        'colliderType',
        'victimType',
        'colliderSpeed',
        'victimSpeed',
        'collisionType',
        'lane',
        'pos',
    ):
        if hasattr(collision, key):
            row[key] = getattr(collision, key)
    return row



def _default_out_dir(repo_root: Path, scenario: str, policy: str) -> Path:
    return repo_root / 'output' / scenario / policy


def run_experiment(
    *,
    scenario: str,
    policy: str,
    duration_s: float,
    step_length: float,
    seed: int | None,
    gui: bool,
    out_dir: str | None,
    control_zone_length_m: float,
    merge_edge: str,
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    fifo_gap_s: float,
    delta_1_s: float,
    delta_2_s: float,
    dp_replan_interval_s: float,
    control_mode: str = 'E-ctrl-1',
    ramp_lc_target_lane: int = 1,
    aux_vmax_mps: float = 25.0,
    cav_ratio: float = 0.5,
    policy_variant: str | None = None,
    ttc_warmup_s: float = 0.0,
    takeover_mode: str = 'current',
) -> int:
    if duration_s <= 0:
        raise ValueError('duration-s must be > 0')
    if step_length <= 0:
        raise ValueError('step-length must be > 0')
    if control_zone_length_m <= 0:
        raise ValueError('control-zone-length-m must be > 0')
    if main_vmax_mps <= 0 or ramp_vmax_mps <= 0:
        raise ValueError('stream vmax must be > 0')
    if fifo_gap_s <= 0:
        raise ValueError('fifo-gap-s must be > 0')
    if delta_1_s <= 0 or delta_2_s <= 0:
        raise ValueError('delta_1_s and delta_2_s must be > 0')
    if dp_replan_interval_s <= 0:
        raise ValueError('dp-replan-interval-s must be > 0')
    if ttc_warmup_s < 0:
        raise ValueError('ttc-warmup-s must be >= 0')
    if policy not in {'no_control', 'fifo', 'dp', 'hierarchical'}:
        raise ValueError(f'Unsupported policy: {policy}')

    takeover_mode_enum = parse_takeover_mode(takeover_mode)
    log_mode_warning(takeover_mode_enum)

    _ensure_sumo_tools_on_path()

    import traci

    repo_root = Path(__file__).resolve().parents[2]
    sumocfg = _resolve_sumocfg(repo_root, scenario)
    sumo_binary = _pick_sumo_binary(gui)
    out_path = Path(out_dir).resolve() if out_dir else _default_out_dir(repo_root, scenario, policy)
    if out_path.exists():
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        sumo_binary,
        '--configuration-file',
        str(sumocfg),
        '--step-length',
        str(step_length),
        '--no-step-log',
        'true',
    ]
    if seed is not None:
        cmd += ['--seed', str(seed)]

    max_steps = int(round(duration_s / step_length))

    trace_fields = [
        'time',
        'veh_id',
        'stream',
        'edge_id',
        'lane_id',
        'lane_pos',
        'D_to_merge',
        'speed',
        'accel',
        'v_des',
    ]
    collision_fields = [
        'time',
        'collider',
        'victim',
        'colliderType',
        'victimType',
        'colliderSpeed',
        'victimSpeed',
        'collisionType',
        'lane',
        'pos',
    ]
    command_fields = [
        'time',
        'veh_id',
        'stream',
        'd_to_merge_m',
        'v_cmd_mps',
        'release_flag',
    ]
    event_fields = ['time', 'event', 'veh_id', 'detail']
    control_fields = CONTROL_FIELDS
    contract_fields = CONTRACT_FIELDS
    feedback_fields = FEEDBACK_FIELDS

    trace_path = out_path / 'control_zone_trace.csv'
    collisions_path = out_path / 'collisions.csv'
    plans_path = out_path / 'plans.csv'
    commands_path = out_path / 'commands.csv'
    events_path = out_path / 'events.csv'
    control_evidence_path = out_path / 'control_evidence.csv'
    contract_evidence_path = out_path / 'contract_evidence.csv'
    feedback_evidence_path = out_path / 'feedback_evidence.csv'
    metrics_path = out_path / 'metrics.json'
    config_path = out_path / 'config.json'
    plan_fields = [
        'time',
        'entry_rank',
        'order_index',
        'veh_id',
        'stream',
        't_enter_control_zone',
        'D_to_merge',
        'speed',
        'natural_eta',
        'target_cross_time',
        'gap_from_prev',
        'v_des',
    ]

    collision_count = 0
    active_vehicle_ids: set[str] = set()
    prev_control_zone_ids: set[str] = set()
    prev_crossed_merge: set[str] = set()
    prev_lane_id_by_vehicle: dict[str, str] = {}
    plan_snapshots: list[tuple[float, list[str], dict[str, float]]] = []
    speed_tracking_abs_errors: list[float] = []
    planned_actual_time_errors: list[float] = []
    planned_actual_position_errors: list[float] = []
    ttc_longitudinal_samples: list[float] = []
    ttc_merge_conflict_samples: list[float] = []
    control_event_index = 0
    contract_index = 0
    feedback_event_index = 0
    controlled_cav_steps = 0
    covered_control_cav_steps = 0
    autonomous_lane_change_detected_count = 0
    speed_mismatch_detected_count = 0
    zone_a_event_count = 0
    zone_c_event_count = 0
    zone_c_chain_complete_count = 0
    zone_c_chain_status: dict[str, bool] = {}
    contract_vehicle_ids: set[str] = set()
    feedback_vehicle_ids: set[str] = set()
    latest_contract_by_vehicle: dict[str, str] = {}
    contract_by_id: dict[str, dict[str, float | str]] = {}
    feedback_rows: list[dict[str, str | float | int]] = []
    cross_feedback_indices: list[int] = []
    policy_variant_name = policy_variant if policy_variant else policy
    merge_policy = resolve_merge_policy(policy=policy, policy_variant=policy_variant_name)
    merge_window_half_span_value = merge_window_half_span_s(
        policy=policy,
        step_length_s=step_length,
        fifo_gap_s=fifo_gap_s,
        delta_1_s=delta_1_s,
        delta_2_s=delta_2_s,
    )
    hier_control_mode = 'E-ctrl-2' if policy == 'hierarchical' else control_mode
    state_collector = StateCollector(
        control_zone_length_m=control_zone_length_m,
        merge_edge=merge_edge,
        policy=policy,
        main_vmax_mps=main_vmax_mps,
        ramp_vmax_mps=ramp_vmax_mps,
        fifo_gap_s=fifo_gap_s,
        control_mode=hier_control_mode,
        aux_vmax_mps=aux_vmax_mps,
    )
    dp_scheduler: DPScheduler | None = None
    hier_collector: HierarchicalStateCollector | None = None
    hier_scheduler: HierarchicalScheduler | None = None
    hier_vehicle_types: dict[str, str] = {}
    hier_state = None
    if policy == 'dp':
        dp_scheduler = DPScheduler(
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
            main_vmax_mps=main_vmax_mps,
            ramp_vmax_mps=ramp_vmax_mps,
            replan_interval_s=dp_replan_interval_s,
            aux_vmax_mps=aux_vmax_mps,
        )
    elif policy == 'hierarchical':
        hier_scheduler = HierarchicalScheduler(
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
            main_vmax_mps=main_vmax_mps,
            ramp_vmax_mps=ramp_vmax_mps,
            replan_interval_s=dp_replan_interval_s,
            aux_vmax_mps=aux_vmax_mps,
        )

    sim_driver = SimulationDriver(traci=traci, cmd=cmd)
    controller = Controller(
        traci=traci,
        takeover_mode=takeover_mode_enum,
        ramp_lc_target_lane=ramp_lc_target_lane,
    )
    sim_driver.start()
    if policy == 'hierarchical':
        hier_collector = HierarchicalStateCollector(
            base_collector=state_collector,
            traci=traci,
        )
    with trace_path.open('w', newline='', encoding='utf-8') as trace_fp, collisions_path.open(
        'w', newline='', encoding='utf-8'
    ) as collision_fp, plans_path.open('w', newline='', encoding='utf-8') as plan_fp, commands_path.open(
        'w', newline='', encoding='utf-8'
    ) as command_fp, events_path.open('w', newline='', encoding='utf-8') as event_fp, control_evidence_path.open(
        'w', newline='', encoding='utf-8'
    ) as control_fp, contract_evidence_path.open('w', newline='', encoding='utf-8') as contract_fp, feedback_evidence_path.open(
        'w', newline='', encoding='utf-8'
    ) as feedback_fp:
        trace_writer = csv.DictWriter(trace_fp, fieldnames=trace_fields, lineterminator='\n')
        collision_writer = csv.DictWriter(
            collision_fp, fieldnames=collision_fields, lineterminator='\n'
        )
        plan_writer = csv.DictWriter(plan_fp, fieldnames=plan_fields, lineterminator='\n')
        command_writer = csv.DictWriter(command_fp, fieldnames=command_fields, lineterminator='\n')
        event_writer = csv.DictWriter(event_fp, fieldnames=event_fields, lineterminator='\n')
        control_writer = csv.DictWriter(control_fp, fieldnames=control_fields, lineterminator='\n')
        contract_writer = csv.DictWriter(contract_fp, fieldnames=contract_fields, lineterminator='\n')
        feedback_writer = csv.DictWriter(feedback_fp, fieldnames=feedback_fields, lineterminator='\n')
        trace_writer.writeheader()
        collision_writer.writeheader()
        plan_writer.writeheader()
        command_writer.writeheader()
        event_writer.writeheader()
        control_writer.writeheader()
        contract_writer.writeheader()
        feedback_writer.writeheader()

        try:
            for _ in range(max_steps):
                sim_time = sim_driver.step()
                active_vehicle_ids = set(traci.vehicle.getIDList())
                control_zone_state: dict[str, dict[str, float | str]] = {}
                desired_speed_by_vehicle: dict[str, float] = {}

                for collision in traci.simulation.getCollisions():
                    collision_writer.writerow(_collision_to_row(sim_time, collision))
                    collision_count += 1

                if policy == 'hierarchical' and hier_collector is not None:
                    hier_state = hier_collector.collect(sim_time=sim_time, traci=traci)
                    collected_state = hier_state.base_state
                    hier_vehicle_types = hier_state.vehicle_types
                else:
                    collected_state = state_collector.collect(sim_time=sim_time, traci=traci)
                active_vehicle_ids = collected_state.active_vehicle_ids
                control_zone_state = collected_state.control_zone_state
                if sim_time >= ttc_warmup_s:
                    longitudinal_samples, merge_conflict_samples = collect_ttc_samples(
                        ttc_observation_state=collected_state.ttc_observation_state
                    )
                    ttc_longitudinal_samples.extend(longitudinal_samples)
                    ttc_merge_conflict_samples.extend(merge_conflict_samples)
                controller.apply_lane_change_modes(
                    control_zone_state=control_zone_state,
                    vehicle_types=hier_vehicle_types if policy == 'hierarchical' else None,
                )
                control_zone_ids = set(control_zone_state)
                entered_this_step = control_zone_ids - prev_control_zone_ids
                left_this_step = prev_control_zone_ids - control_zone_ids
                crossed_this_step = state_collector.crossed_merge - prev_crossed_merge
                lane_changed_by_vehicle: dict[str, bool] = {}
                for veh_id, vehicle_state in control_zone_state.items():
                    lane_id = str(vehicle_state['lane_id'])
                    previous_lane_id = prev_lane_id_by_vehicle.get(veh_id, lane_id)
                    lane_changed_by_vehicle[veh_id] = previous_lane_id != lane_id

                for veh_id in sorted(entered_this_step):
                    stream = str(state_collector.entry_info.get(veh_id, {}).get('stream', 'unknown'))
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'enter_control',
                            'veh_id': veh_id,
                            'detail': f'stream={stream}',
                        }
                    )
                for veh_id in sorted(crossed_this_step):
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'cross_merge',
                            'veh_id': veh_id,
                            'detail': f'merge_edge={merge_edge}',
                        }
                    )
                    feedback_event_index += 1
                    contract_id = latest_contract_by_vehicle.get(veh_id, '')
                    contract_snapshot = contract_by_id.get(contract_id, {})
                    actual_merge_position_m = 0.0
                    expected_merge_time_s = (
                        float(contract_snapshot['expected_merge_time_s'])
                        if 'expected_merge_time_s' in contract_snapshot
                        else sim_time
                    )
                    expected_merge_position_value = (
                        float(contract_snapshot['expected_merge_position_m'])
                        if 'expected_merge_position_m' in contract_snapshot
                        else actual_merge_position_m
                    )
                    planned_actual_time_error_s: float | str = ''
                    planned_actual_position_error_m: float | str = ''
                    if contract_id:
                        planned_actual_time_error_s = sim_time - expected_merge_time_s
                        planned_actual_position_error_m = (
                            actual_merge_position_m - expected_merge_position_value
                        )
                        feedback_vehicle_ids.add(veh_id)
                        planned_actual_time_errors.append(abs(planned_actual_time_error_s))
                        planned_actual_position_errors.append(
                            abs(planned_actual_position_error_m)
                        )
                    fallback_reason = ''
                    if veh_id in zone_c_chain_status and not zone_c_chain_status[veh_id]:
                        fallback_reason = 'zone_c_chain_incomplete'
                        zone_c_chain_status[veh_id] = True
                        zone_c_chain_complete_count += 1
                    feedback_rows.append(
                        {
                            'time': sim_time,
                            'event_id': f'feedback_{feedback_event_index:08d}',
                            'contract_id': contract_id,
                            'ego_vehicle_id': veh_id,
                            'execution_state': 'merge_cross',
                            'gap_found': '',
                            'gap_reject_reason': '',
                            'actual_merge_time_s': sim_time,
                            'actual_merge_position_m': actual_merge_position_m,
                            'actual_predecessor_id': '',
                            'actual_follower_id': '',
                            'planned_actual_time_error_s': planned_actual_time_error_s,
                            'planned_actual_position_error_m': planned_actual_position_error_m,
                            'fallback_reason': fallback_reason,
                            'replan_required': 0,
                        }
                    )
                    cross_feedback_indices.append(len(feedback_rows) - 1)
                for veh_id in sorted(left_this_step):
                    stream = str(state_collector.entry_info.get(veh_id, {}).get('stream', 'unknown'))
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'leave_control',
                            'veh_id': veh_id,
                            'detail': f'stream={stream}',
                        }
                    )

                plan = None
                plan_recomputed = False
                if policy == 'fifo':
                    plan = compute_fifo_plan(
                        sim_time_s=sim_time,
                        control_zone_state=control_zone_state,
                        entry_order=state_collector.entry_order,
                        crossed_merge=state_collector.crossed_merge,
                        fifo_target_time=state_collector.fifo_target_time,
                        fifo_natural_eta=state_collector.fifo_natural_eta,
                    )
                    plan_recomputed = bool(entered_this_step)
                elif policy == 'dp':
                    if dp_scheduler is None:
                        raise RuntimeError('DP scheduler is not initialized')
                    plan = dp_scheduler.compute_plan(
                        sim_time_s=sim_time,
                        control_zone_state=control_zone_state,
                        crossed_merge=state_collector.crossed_merge,
                        entry_info=state_collector.entry_info,
                        traci=traci,
                    )
                    plan_recomputed = bool(dp_scheduler.replanned_last_call)
                elif policy == 'hierarchical':
                    if hier_scheduler is None:
                        raise RuntimeError('Hierarchical scheduler is not initialized')
                    plan = hier_scheduler.compute_plan(
                        sim_time_s=sim_time,
                        control_zone_state=control_zone_state,
                        crossed_merge=state_collector.crossed_merge,
                        entry_info=state_collector.entry_info,
                        vehicle_types=hier_vehicle_types,
                        traci=traci,
                        zone_a_info=hier_state.zone_a_info if hier_state is not None else None,
                        zone_c_lane1_vehicles=hier_state.zone_c_lane1_vehicles if hier_state is not None else None,
                    )
                    plan_recomputed = bool(hier_scheduler.replanned_last_call)
                else:
                    plan = compute_no_control_plan(sim_time_s=sim_time)

                zone_a_action_ids: set[str] = set()
                zone_c_action_ids: set[str] = set()
                if policy in {'fifo', 'dp', 'hierarchical'}:
                    if plan is None:
                        raise RuntimeError(f'Policy {policy} must return a Plan')
                    schedule_order = plan.order
                    schedule_target_time = plan.target_cross_time_s
                    schedule_eta = plan.eta_s
                    plan_snapshots.append(
                        (sim_time, list(schedule_order), dict(schedule_target_time))
                    )
                    if plan_recomputed:
                        event_writer.writerow(
                            {
                                'time': sim_time,
                                'event': 'plan_recompute',
                                'veh_id': '',
                                'detail': f'policy={policy}',
                            }
                        )
                    if policy == 'fifo':
                        command = build_fifo_command(
                            sim_time_s=sim_time,
                            step_length_s=step_length,
                            plan=plan,
                            control_zone_state=control_zone_state,
                            main_vmax_mps=main_vmax_mps,
                            ramp_vmax_mps=ramp_vmax_mps,
                            aux_vmax_mps=aux_vmax_mps,
                        )
                    elif policy == 'hierarchical':
                        command = build_hierarchical_command(
                            sim_time_s=sim_time,
                            step_length_s=step_length,
                            plan=plan,
                            control_zone_state=control_zone_state,
                            vehicle_types=hier_vehicle_types,
                            main_vmax_mps=main_vmax_mps,
                            ramp_vmax_mps=ramp_vmax_mps,
                            aux_vmax_mps=aux_vmax_mps,
                            zone_a_actions=hier_scheduler.zone_a_actions,
                            zone_c_actions=hier_scheduler.zone_c_actions,
                        )
                        zone_a_action_ids = set(hier_scheduler.zone_a_actions)
                        zone_c_action_ids = set(hier_scheduler.zone_c_actions)
                    else:
                        command = build_dp_command(
                            sim_time_s=sim_time,
                            step_length_s=step_length,
                            plan=plan,
                            control_zone_state=control_zone_state,
                            main_vmax_mps=main_vmax_mps,
                            ramp_vmax_mps=ramp_vmax_mps,
                            aux_vmax_mps=aux_vmax_mps,
                        )
                    zone_a_event_count += len(zone_a_action_ids)
                    zone_c_event_count += len(zone_c_action_ids)
                    for veh_id in sorted(zone_c_action_ids):
                        if veh_id not in zone_c_chain_status:
                            zone_c_chain_status[veh_id] = False
                        feedback_event_index += 1
                        feedback_rows.append(
                            {
                                'time': sim_time,
                                'event_id': f'feedback_{feedback_event_index:08d}',
                                'contract_id': latest_contract_by_vehicle.get(veh_id, ''),
                                'ego_vehicle_id': veh_id,
                                'execution_state': 'lc_command_issued',
                                'gap_found': 1,
                                'gap_reject_reason': '',
                                'actual_merge_time_s': '',
                                'actual_merge_position_m': '',
                                'actual_predecessor_id': '',
                                'actual_follower_id': '',
                                'planned_actual_time_error_s': '',
                                'planned_actual_position_error_m': '',
                                'fallback_reason': '',
                                'replan_required': int(plan_recomputed),
                            }
                        )
                        event_writer.writerow(
                            {
                                'time': sim_time,
                                'event': 'zone_c_lc_command',
                                'veh_id': veh_id,
                                'detail': '',
                            }
                        )
                    prev_target: float | None = None
                    for order_index, veh_id in enumerate(schedule_order, start=1):
                        vehicle_state = control_zone_state[veh_id]
                        d_to_merge = float(vehicle_state['d_to_merge'])
                        speed = float(vehicle_state['speed'])
                        stream = str(vehicle_state['stream'])
                        natural_eta = schedule_eta[veh_id]
                        target_cross_time = schedule_target_time[veh_id]
                        if prev_target is None:
                            gap_from_prev = 0.0
                        else:
                            gap_from_prev = target_cross_time - prev_target
                        prev_target = target_cross_time

                        if veh_id in command.set_speed_mps:
                            v_des = float(command.set_speed_mps[veh_id])
                            desired_speed_by_vehicle[veh_id] = v_des
                        else:
                            v_des = ''

                        if plan_recomputed or veh_id not in latest_contract_by_vehicle:
                            contract_index += 1
                            target_predecessor_id = (
                                schedule_order[order_index - 2] if order_index > 1 else ''
                            )
                            target_follower_id = (
                                schedule_order[order_index] if order_index < len(schedule_order) else ''
                            )
                            expected_merge_position = expected_merge_position_m(
                                merge_policy=merge_policy,
                            )
                            desired_merge_speed = (
                                float(v_des) if isinstance(v_des, float) else speed
                            )
                            contract_id, contract_row, contract_snapshot = build_contract_row(
                                contract_index=contract_index,
                                sim_time=sim_time,
                                zoneb_algorithm=policy,
                                merge_policy=merge_policy,
                                veh_id=veh_id,
                                sequence_rank=order_index,
                                target_predecessor_id=target_predecessor_id,
                                target_follower_id=target_follower_id,
                                target_cross_time=target_cross_time,
                                merge_window_half_span_s=merge_window_half_span_value,
                                expected_merge_position_m_value=expected_merge_position,
                                desired_merge_speed_mps=desired_merge_speed,
                            )
                            contract_writer.writerow(contract_row)
                            contract_by_id[contract_id] = contract_snapshot
                            latest_contract_by_vehicle[veh_id] = contract_id
                            contract_vehicle_ids.add(veh_id)

                        plan_writer.writerow(
                            {
                                'time': sim_time,
                                'entry_rank': state_collector.entry_rank[veh_id],
                                'order_index': order_index,
                                'veh_id': veh_id,
                                'stream': stream,
                                't_enter_control_zone': float(
                                    state_collector.entry_info[veh_id]['t_entry']
                                ),
                                'D_to_merge': d_to_merge,
                                'speed': speed,
                                'natural_eta': natural_eta,
                                'target_cross_time': target_cross_time,
                                'gap_from_prev': gap_from_prev,
                                'v_des': v_des,
                            }
                        )
                    controller_result = controller.apply(
                        command=command, active_vehicle_ids=active_vehicle_ids
                    )
                else:
                    command = build_no_control_command()
                    controller_result = controller.apply(
                        command=command, active_vehicle_ids=active_vehicle_ids
                    )

                for veh_id in sorted(command.set_speed_mps):
                    vehicle_state = control_zone_state.get(veh_id, {})
                    command_writer.writerow(
                        {
                            'time': sim_time,
                            'veh_id': veh_id,
                            'stream': vehicle_state.get('stream', ''),
                            'd_to_merge_m': vehicle_state.get('d_to_merge', ''),
                            'v_cmd_mps': command.set_speed_mps[veh_id],
                            'release_flag': 0,
                        }
                    )
                for veh_id in sorted(controller_result.released_ids):
                    vehicle_state = control_zone_state.get(veh_id, {})
                    command_writer.writerow(
                        {
                            'time': sim_time,
                            'veh_id': veh_id,
                            'stream': vehicle_state.get('stream', ''),
                            'd_to_merge_m': vehicle_state.get('d_to_merge', ''),
                            'v_cmd_mps': '',
                            'release_flag': 1,
                        }
                    )
                lane_change_command_ids = set(command.lane_change_targets)
                for veh_id in sorted(command.set_speed_mps):
                    if veh_id not in control_zone_state:
                        continue
                    vehicle_state = control_zone_state[veh_id]
                    if traci.vehicle.getTypeID(veh_id) == 'hdv':
                        continue
                    controlled_cav_steps += 1
                    covered_control_cav_steps += 1
                    commanded_speed = float(command.set_speed_mps[veh_id])
                    actual_speed = float(vehicle_state['speed'])
                    speed_error = actual_speed - commanded_speed
                    speed_mode_applied = controller_result.speed_mode_by_vehicle.get(
                        veh_id, int(traci.vehicle.getSpeedMode(veh_id))
                    )
                    lane_change_command_issued = int(veh_id in lane_change_command_ids)
                    lane_change_mode_applied = int(traci.vehicle.getLaneChangeMode(veh_id))
                    autonomous_lane_change_detected = int(
                        lane_changed_by_vehicle.get(veh_id, False)
                        and lane_change_command_issued == 0
                    )
                    if autonomous_lane_change_detected == 1:
                        autonomous_lane_change_detected_count += 1
                        event_writer.writerow(
                            {
                                'time': sim_time,
                                'event': 'autonomous_lane_change_anomaly',
                                'veh_id': veh_id,
                                'detail': 'lane_changed_without_command',
                            }
                        )
                    if abs(speed_error) >= SPEED_MISMATCH_THRESHOLD_MPS:
                        speed_mismatch_detected_count += 1
                        event_writer.writerow(
                            {
                                'time': sim_time,
                                'event': 'speed_mismatch_anomaly',
                                'veh_id': veh_id,
                                'detail': (
                                    f'commanded={commanded_speed:.3f},'
                                    f'actual={actual_speed:.3f},'
                                    f'error={speed_error:.3f}'
                                ),
                            }
                        )
                    control_event_index += 1
                    control_writer.writerow(
                        {
                            'time': sim_time,
                            'event_id': f'control_{control_event_index:08d}',
                            'contract_id': latest_contract_by_vehicle.get(veh_id, ''),
                            'veh_id': veh_id,
                            'commanded_speed': commanded_speed,
                            'actual_speed': actual_speed,
                            'speed_error': speed_error,
                            'speed_mode_applied': speed_mode_applied,
                            'lane_change_command_issued': lane_change_command_issued,
                            'lane_change_mode_applied': lane_change_mode_applied,
                            'autonomous_lane_change_detected': autonomous_lane_change_detected,
                            'controlled_cav_step': 1,
                        }
                    )
                for veh_id in sorted(lane_change_command_ids - set(command.set_speed_mps)):
                    if veh_id not in control_zone_state:
                        continue
                    if traci.vehicle.getTypeID(veh_id) == 'hdv':
                        continue
                    control_event_index += 1
                    control_writer.writerow(
                        {
                            'time': sim_time,
                            'event_id': f'control_{control_event_index:08d}',
                            'contract_id': latest_contract_by_vehicle.get(veh_id, ''),
                            'veh_id': veh_id,
                            'commanded_speed': '',
                            'actual_speed': float(control_zone_state[veh_id]['speed']),
                            'speed_error': '',
                            'speed_mode_applied': int(traci.vehicle.getSpeedMode(veh_id)),
                            'lane_change_command_issued': 1,
                            'lane_change_mode_applied': int(traci.vehicle.getLaneChangeMode(veh_id)),
                            'autonomous_lane_change_detected': 0,
                            'controlled_cav_step': 0,
                        }
                    )
                for veh_id, lane_changed in lane_changed_by_vehicle.items():
                    if not lane_changed:
                        continue
                    previous_lane_id = prev_lane_id_by_vehicle.get(veh_id, '')
                    current_lane_id = str(control_zone_state[veh_id]['lane_id'])
                    if (
                        previous_lane_id.startswith('main_h3_0')
                        and current_lane_id.startswith('main_h3_1')
                        and veh_id in zone_c_chain_status
                        and not zone_c_chain_status[veh_id]
                    ):
                        zone_c_chain_status[veh_id] = True
                        zone_c_chain_complete_count += 1
                        contract_id = latest_contract_by_vehicle.get(veh_id, '')
                        contract_snapshot = contract_by_id.get(contract_id, {})
                        actual_merge_position_m = float(control_zone_state[veh_id].get('d_to_merge', 0.0))
                        planned_actual_time_error_s: float | str = ''
                        planned_actual_position_error_m: float | str = ''
                        if contract_id:
                            expected_merge_time_s = float(
                                contract_snapshot.get('expected_merge_time_s', sim_time)
                            )
                            expected_merge_position_value = float(
                                contract_snapshot.get(
                                    'expected_merge_position_m', actual_merge_position_m
                                )
                            )
                            planned_actual_time_error_s = sim_time - expected_merge_time_s
                            planned_actual_position_error_m = (
                                actual_merge_position_m - expected_merge_position_value
                            )
                            planned_actual_time_errors.append(abs(planned_actual_time_error_s))
                            planned_actual_position_errors.append(
                                abs(planned_actual_position_error_m)
                            )
                            feedback_vehicle_ids.add(veh_id)
                        feedback_event_index += 1
                        feedback_rows.append(
                            {
                                'time': sim_time,
                                'event_id': f'feedback_{feedback_event_index:08d}',
                                'contract_id': contract_id,
                                'ego_vehicle_id': veh_id,
                                'execution_state': 'lc_complete',
                                'gap_found': 1,
                                'gap_reject_reason': '',
                                'actual_merge_time_s': sim_time,
                                'actual_merge_position_m': actual_merge_position_m,
                                'actual_predecessor_id': '',
                                'actual_follower_id': '',
                                'planned_actual_time_error_s': planned_actual_time_error_s,
                                'planned_actual_position_error_m': planned_actual_position_error_m,
                                'fallback_reason': '',
                                'replan_required': int(plan_recomputed),
                            }
                        )
                        event_writer.writerow(
                            {
                                'time': sim_time,
                                'event': 'zone_c_lc_complete',
                                'veh_id': veh_id,
                                'detail': '',
                            }
                        )
                for veh_id in sorted(controller_result.takeover_ids):
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'speedmode_takeover',
                            'veh_id': veh_id,
                            'detail': f'speed_mode={controller.config.speed_mode}',
                        }
                    )
                for veh_id in sorted(controller_result.restored_ids):
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'speedmode_restore',
                            'veh_id': veh_id,
                            'detail': '',
                        }
                    )
                for veh_id in sorted(controller_result.commit_ids):
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'commit_vehicle',
                            'veh_id': veh_id,
                            'detail': 'internal_edge=:n_merge*',
                        }
                    )

                for veh_id, vehicle_state in control_zone_state.items():
                    trace_writer.writerow(
                        {
                            'time': sim_time,
                            'veh_id': veh_id,
                            'stream': vehicle_state['stream'],
                            'edge_id': vehicle_state['edge_id'],
                            'lane_id': vehicle_state['lane_id'],
                            'lane_pos': vehicle_state['lane_pos'],
                            'D_to_merge': vehicle_state['d_to_merge'],
                            'speed': vehicle_state['speed'],
                            'accel': vehicle_state['accel'],
                            'v_des': desired_speed_by_vehicle.get(veh_id, ''),
                        }
                    )
                for veh_id, v_des in desired_speed_by_vehicle.items():
                    if veh_id in control_zone_state:
                        speed_now = float(control_zone_state[veh_id]['speed'])
                        speed_tracking_abs_errors.append(abs(speed_now - v_des))

                for veh_id, vehicle_state in control_zone_state.items():
                    prev_lane_id_by_vehicle[veh_id] = str(vehicle_state['lane_id'])
                prev_control_zone_ids = control_zone_ids
                prev_crossed_merge = set(state_collector.crossed_merge)
        finally:
            controller.release_all(active_vehicle_ids=active_vehicle_ids)
            sim_driver.close()

    attach_actual_neighbors(
        feedback_rows=feedback_rows,
        cross_feedback_indices=cross_feedback_indices,
    )

    with feedback_evidence_path.open('a', newline='', encoding='utf-8') as feedback_fp:
        feedback_writer = csv.DictWriter(feedback_fp, fieldnames=feedback_fields, lineterminator='\n')
        for row in feedback_rows:
            feedback_writer.writerow(row)

    pending_unfinished = {
        veh_id
        for veh_id in state_collector.entered_control
        if veh_id not in state_collector.cross_time and veh_id in active_vehicle_ids
    }
    evaluated_entered = state_collector.entered_control - pending_unfinished
    successful_merge = [
        veh_id for veh_id in evaluated_entered if veh_id in state_collector.cross_time
    ]
    merge_success_rate = (
        len(successful_merge) / len(evaluated_entered) if evaluated_entered else 0.0
    )

    delays: list[float] = []
    for veh_id in successful_merge:
        vehicle_entry = state_collector.entry_info[veh_id]
        stream = str(vehicle_entry['stream'])
        free_flow_speed = main_vmax_mps if stream == 'main' else ramp_vmax_mps
        t_entry = float(vehicle_entry['t_entry'])
        d_entry = float(vehicle_entry['d_entry'])
        free_flow_time = d_entry / free_flow_speed
        delays.append(state_collector.cross_time[veh_id] - (t_entry + free_flow_time))

    avg_delay = sum(delays) / len(delays) if delays else 0.0
    throughput_veh_per_h = (len(state_collector.crossed_merge) / duration_s) * 3600.0
    speed_tracking_mae_mps = (
        sum(speed_tracking_abs_errors) / len(speed_tracking_abs_errors)
        if speed_tracking_abs_errors
        else 0.0
    )
    speed_error_p50_mps = _percentile(speed_tracking_abs_errors, 0.50) if speed_tracking_abs_errors else 0.0
    speed_error_p95_mps = _percentile(speed_tracking_abs_errors, 0.95) if speed_tracking_abs_errors else 0.0

    consistency_merge_order_mismatch_count = 0
    cross_time_errors: list[float] = []
    if policy in {'fifo', 'dp', 'hierarchical'} and plan_snapshots:
        actual_cross_sequence = sorted(
            state_collector.cross_time.items(),
            key=lambda item: (float(item[1]), item[0]),
        )
        for veh_id, cross_t in actual_cross_sequence:
            latest_snapshot: tuple[float, list[str], dict[str, float]] | None = None
            latest_with_vehicle: tuple[float, list[str], dict[str, float]] | None = None
            for snapshot in plan_snapshots:
                if snapshot[0] >= cross_t - 1e-9:
                    break
                latest_snapshot = snapshot
                if veh_id in snapshot[2]:
                    latest_with_vehicle = snapshot

            if latest_snapshot and latest_snapshot[1]:
                if latest_snapshot[1][0] != veh_id:
                    consistency_merge_order_mismatch_count += 1

            if latest_with_vehicle is not None:
                cross_time_errors.append(cross_t - latest_with_vehicle[2][veh_id])

    cross_time_error_mean_s = (
        sum(abs(err) for err in cross_time_errors) / len(cross_time_errors)
        if cross_time_errors
        else 0.0
    )
    cross_time_error_p95_s = (
        _percentile([abs(err) for err in cross_time_errors], 0.95)
        if cross_time_errors
        else 0.0
    )

    churn_samples: list[float] = []
    if policy in {'fifo', 'dp', 'hierarchical'} and len(plan_snapshots) >= 2:
        for prev_snapshot, cur_snapshot in zip(plan_snapshots, plan_snapshots[1:]):
            prev_order = prev_snapshot[1]
            cur_order = cur_snapshot[1]
            prev_pos = {veh_id: idx for idx, veh_id in enumerate(prev_order)}
            cur_pos = {veh_id: idx for idx, veh_id in enumerate(cur_order)}
            shared = set(prev_pos) & set(cur_pos)
            if not shared:
                continue
            changed = sum(1 for veh_id in shared if prev_pos[veh_id] != cur_pos[veh_id])
            churn_samples.append(changed / len(shared))
    consistency_plan_churn_rate = (
        sum(churn_samples) / len(churn_samples) if churn_samples else 0.0
    )
    ttc_metrics = build_ttc_metrics(
        longitudinal_samples=ttc_longitudinal_samples,
        merge_conflict_samples=ttc_merge_conflict_samples,
        step_length_s=step_length,
    )
    evidence_metrics = build_evidence_metrics(
        duration_s=duration_s,
        controlled_cav_steps=controlled_cav_steps,
        covered_control_cav_steps=covered_control_cav_steps,
        autonomous_lane_change_detected_count=autonomous_lane_change_detected_count,
        speed_mismatch_detected_count=speed_mismatch_detected_count,
        zone_a_event_count=zone_a_event_count,
        zone_c_event_count=zone_c_event_count,
        zone_c_chain_status=zone_c_chain_status,
        zone_c_chain_complete_count=zone_c_chain_complete_count,
        contract_vehicle_ids=contract_vehicle_ids,
        feedback_vehicle_ids=feedback_vehicle_ids,
        feedback_rows=feedback_rows,
        contract_by_id=contract_by_id,
        planned_actual_time_errors=planned_actual_time_errors,
        planned_actual_position_errors=planned_actual_position_errors,
    )

    metrics = {
        'policy_name': policy,
        'policy_variant': policy_variant_name,
        'metrics_schema_version': 'v3_evidence_chain',
        'ttc_warmup_s': ttc_warmup_s,
        'merge_success_rate': merge_success_rate,
        'avg_delay_at_merge_s': avg_delay,
        'throughput_veh_per_h': throughput_veh_per_h,
        'collision_count': collision_count,
        'stop_count': state_collector.stop_count,
        'entered_control_count': len(state_collector.entered_control),
        'evaluated_entered_count': len(evaluated_entered),
        'pending_unfinished_count': len(pending_unfinished),
        'crossed_merge_count': len(state_collector.crossed_merge),
        'consistency_merge_order_mismatch_count': consistency_merge_order_mismatch_count,
        'consistency_cross_time_error_mean_s': cross_time_error_mean_s,
        'consistency_cross_time_error_p95_s': cross_time_error_p95_s,
        'consistency_speed_tracking_mae_mps': speed_tracking_mae_mps,
        'consistency_speed_error_p50_mps': speed_error_p50_mps,
        'consistency_speed_error_p95_mps': speed_error_p95_mps,
        'consistency_plan_churn_rate': consistency_plan_churn_rate,
        'takeover_mode': takeover_mode,
    }
    metrics.update(ttc_metrics)
    metrics.update(evidence_metrics)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')

    config = {
        'scenario': scenario,
        'policy': policy,
        'policy_variant': policy_variant_name,
        'sumocfg': str(sumocfg),
        'duration_s': duration_s,
        'step_length': step_length,
        'seed': seed,
        'gui': gui,
        'control_zone_length_m': control_zone_length_m,
        'merge_edge': merge_edge,
        'main_vmax_mps': main_vmax_mps,
        'ramp_vmax_mps': ramp_vmax_mps,
        'fifo_gap_s': fifo_gap_s,
        'delta_1_s': delta_1_s,
        'delta_2_s': delta_2_s,
        'dp_replan_interval_s': dp_replan_interval_s,
        'control_mode': hier_control_mode,
        'ramp_lc_target_lane': ramp_lc_target_lane,
        'aux_vmax_mps': aux_vmax_mps,
        'cav_ratio': cav_ratio,
        'ttc_warmup_s': ttc_warmup_s,
        'takeover_mode': takeover_mode,
        'output_dir': str(out_path),
    }
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')

    print(f'[ramp.run] output_dir={out_path}')
    print(
        f'[ramp.run] scenario={scenario} policy={policy} '
        f'duration_s={duration_s} step_length={step_length} steps={max_steps} completed'
    )
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(name)s %(levelname)s %(message)s',
    )
    parser = argparse.ArgumentParser(description='Run SUMO-only ramp experiment skeleton.')
    parser.add_argument('--scenario', default='ramp_min_v1')
    parser.add_argument('--policy', default='no_control')
    parser.add_argument('--duration-s', type=float, default=5.0)
    parser.add_argument('--step-length', type=float, default=0.1)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--out-dir', default=None)
    # Default control zone is long enough to cover "speed control + merge" upstream area.
    parser.add_argument('--control-zone-length-m', type=float, default=600.0)
    parser.add_argument('--merge-edge', default='main_h4')
    parser.add_argument('--main-vmax-mps', type=float, default=25.0)
    parser.add_argument('--ramp-vmax-mps', type=float, default=16.7)
    parser.add_argument('--fifo-gap-s', type=float, default=1.5)
    parser.add_argument('--delta-1-s', type=float, default=1.5)
    parser.add_argument('--delta-2-s', type=float, default=2.0)
    parser.add_argument('--dp-replan-interval-s', type=float, default=0.5)
    parser.add_argument(
        '--control-mode',
        choices=['E-ctrl-1', 'E-ctrl-2'],
        default='E-ctrl-1',
        help='Lane filter mode: E-ctrl-1 (conflict lanes only) or E-ctrl-2 (all lanes).',
    )
    parser.add_argument(
        '--ramp-lc-target-lane',
        type=int,
        default=1,
        help='Target lane index for ramp vehicle lane change limit (-1 = no limit).',
    )
    parser.add_argument(
        '--aux-vmax-mps',
        type=float,
        default=25.0,
        help='stream_vmax override for ramp vehicles on aux lane (main_h3).',
    )
    parser.add_argument(
        '--cav-ratio',
        type=float,
        default=0.5,
        help='CAV penetration ratio for mixed traffic scenarios (0.0 to 1.0).',
    )
    parser.add_argument(
        '--policy-variant',
        default=None,
        help='Policy variant label used by downstream summary scripts.',
    )
    parser.add_argument(
        '--ttc-warmup-s',
        type=float,
        default=0.0,
        help='Warmup time before TTC sampling starts (seconds).',
    )
    parser.add_argument(
        '--takeover-mode',
        choices=['current', 'semi', 'strict', 'debug_upper_bound'],
        default='current',
        help=(
            'CAV takeover level: current (T0, baseline), semi (T1, LC-sealed merge edge), '
            'strict (T2, safe-speed off + slowDown), debug_upper_bound (T3, all SUMO checks off '
            '[UNSAFE - debug only]).'
        ),
    )
    parser.add_argument(
        '--gui',
        action='store_true',
        default=os.environ.get('SUMO_GUI', '0') in {'1', 'true', 'True'},
        help='Use sumo-gui (default false; can be enabled with SUMO_GUI=1).',
    )
    args = parser.parse_args()

    return run_experiment(
        scenario=args.scenario,
        policy=args.policy,
        duration_s=args.duration_s,
        step_length=args.step_length,
        seed=args.seed,
        gui=args.gui,
        out_dir=args.out_dir,
        control_zone_length_m=args.control_zone_length_m,
        merge_edge=args.merge_edge,
        main_vmax_mps=args.main_vmax_mps,
        ramp_vmax_mps=args.ramp_vmax_mps,
        fifo_gap_s=args.fifo_gap_s,
        delta_1_s=args.delta_1_s,
        delta_2_s=args.delta_2_s,
        dp_replan_interval_s=args.dp_replan_interval_s,
        control_mode=args.control_mode,
        ramp_lc_target_lane=args.ramp_lc_target_lane,
        aux_vmax_mps=args.aux_vmax_mps,
        cav_ratio=args.cav_ratio,
        policy_variant=args.policy_variant,
        ttc_warmup_s=args.ttc_warmup_s,
        takeover_mode=args.takeover_mode,
    )


if __name__ == '__main__':
    raise SystemExit(main())
