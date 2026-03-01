import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

from ramp.policies.dp.command_builder import build_command as build_dp_command
from ramp.policies.dp.scheduler import DPScheduler
from ramp.policies.fifo.command_builder import build_command as build_fifo_command
from ramp.policies.fifo.scheduler import compute_plan as compute_fifo_plan
from ramp.policies.no_control.command_builder import build_command as build_no_control_command
from ramp.policies.no_control.scheduler import compute_plan as compute_no_control_plan
from ramp.runtime.controller import Controller
from ramp.runtime.simulation_driver import SimulationDriver
from ramp.runtime.state_collector import StateCollector


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


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * q))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return float(sorted_vals[idx])


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
    if policy not in {'no_control', 'fifo', 'dp'}:
        raise ValueError(f'Unsupported policy: {policy}')

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

    trace_path = out_path / 'control_zone_trace.csv'
    collisions_path = out_path / 'collisions.csv'
    plans_path = out_path / 'plans.csv'
    commands_path = out_path / 'commands.csv'
    events_path = out_path / 'events.csv'
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
    plan_snapshots: list[tuple[float, list[str], dict[str, float]]] = []
    speed_tracking_abs_errors: list[float] = []
    state_collector = StateCollector(
        control_zone_length_m=control_zone_length_m,
        merge_edge=merge_edge,
        policy=policy,
        main_vmax_mps=main_vmax_mps,
        ramp_vmax_mps=ramp_vmax_mps,
        fifo_gap_s=fifo_gap_s,
        control_mode=control_mode,
        aux_vmax_mps=aux_vmax_mps,
    )
    dp_scheduler: DPScheduler | None = None
    if policy == 'dp':
        dp_scheduler = DPScheduler(
            delta_1_s=delta_1_s,
            delta_2_s=delta_2_s,
            main_vmax_mps=main_vmax_mps,
            ramp_vmax_mps=ramp_vmax_mps,
            replan_interval_s=dp_replan_interval_s,
            aux_vmax_mps=aux_vmax_mps,
        )

    sim_driver = SimulationDriver(traci=traci, cmd=cmd)
    controller = Controller(traci=traci, ramp_lc_target_lane=ramp_lc_target_lane)
    sim_driver.start()
    with trace_path.open('w', newline='', encoding='utf-8') as trace_fp, collisions_path.open(
        'w', newline='', encoding='utf-8'
    ) as collision_fp, plans_path.open('w', newline='', encoding='utf-8') as plan_fp, commands_path.open(
        'w', newline='', encoding='utf-8'
    ) as command_fp, events_path.open('w', newline='', encoding='utf-8') as event_fp:
        trace_writer = csv.DictWriter(trace_fp, fieldnames=trace_fields, lineterminator='\n')
        collision_writer = csv.DictWriter(
            collision_fp, fieldnames=collision_fields, lineterminator='\n'
        )
        plan_writer = csv.DictWriter(plan_fp, fieldnames=plan_fields, lineterminator='\n')
        command_writer = csv.DictWriter(command_fp, fieldnames=command_fields, lineterminator='\n')
        event_writer = csv.DictWriter(event_fp, fieldnames=event_fields, lineterminator='\n')
        trace_writer.writeheader()
        collision_writer.writeheader()
        plan_writer.writeheader()
        command_writer.writeheader()
        event_writer.writeheader()

        try:
            for _ in range(max_steps):
                sim_time = sim_driver.step()
                active_vehicle_ids = set(traci.vehicle.getIDList())
                control_zone_state: dict[str, dict[str, float | str]] = {}
                desired_speed_by_vehicle: dict[str, float] = {}

                for collision in traci.simulation.getCollisions():
                    collision_writer.writerow(_collision_to_row(sim_time, collision))
                    collision_count += 1

                collected_state = state_collector.collect(sim_time=sim_time, traci=traci)
                active_vehicle_ids = collected_state.active_vehicle_ids
                control_zone_state = collected_state.control_zone_state
                controller.apply_lane_change_modes(control_zone_state=control_zone_state)
                control_zone_ids = set(control_zone_state)
                entered_this_step = control_zone_ids - prev_control_zone_ids
                left_this_step = prev_control_zone_ids - control_zone_ids
                crossed_this_step = state_collector.crossed_merge - prev_crossed_merge

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
                else:
                    plan = compute_no_control_plan(sim_time_s=sim_time)

                if policy in {'fifo', 'dp'}:
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

                        v_des = float(command.set_speed_mps[veh_id])
                        desired_speed_by_vehicle[veh_id] = v_des

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
                for veh_id in sorted(controller_result.takeover_ids):
                    event_writer.writerow(
                        {
                            'time': sim_time,
                            'event': 'speedmode_takeover',
                            'veh_id': veh_id,
                            'detail': 'speed_mode=23',
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

                prev_control_zone_ids = control_zone_ids
                prev_crossed_merge = set(state_collector.crossed_merge)
        finally:
            controller.release_all(active_vehicle_ids=active_vehicle_ids)
            sim_driver.close()

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

    consistency_merge_order_mismatch_count = 0
    cross_time_errors: list[float] = []
    if policy in {'fifo', 'dp'} and plan_snapshots:
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
    if policy in {'fifo', 'dp'} and len(plan_snapshots) >= 2:
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

    metrics = {
        'policy_name': policy,
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
        'consistency_plan_churn_rate': consistency_plan_churn_rate,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')

    config = {
        'scenario': scenario,
        'policy': policy,
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
        'control_mode': control_mode,
        'ramp_lc_target_lane': ramp_lc_target_lane,
        'aux_vmax_mps': aux_vmax_mps,
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
    )


if __name__ == '__main__':
    raise SystemExit(main())
