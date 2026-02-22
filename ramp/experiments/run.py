import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

from ramp.scheduler.arrival_time import minimum_arrival_time_at_on_ramp
from ramp.scheduler.dp import dp_schedule


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


def _stream_vmax(stream: str, main_vmax_mps: float, ramp_vmax_mps: float) -> float:
    if stream == 'main':
        return main_vmax_mps
    if stream == 'ramp':
        return ramp_vmax_mps
    return max(main_vmax_mps, ramp_vmax_mps)


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

    trace_path = out_path / 'control_zone_trace.csv'
    collisions_path = out_path / 'collisions.csv'
    plans_path = out_path / 'plans.csv'
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

    entered_control: set[str] = set()
    crossed_merge: set[str] = set()
    entry_info: dict[str, dict[str, float | str]] = {}
    cross_time: dict[str, float] = {}
    prev_stopped: dict[str, bool] = {}
    stop_count = 0
    collision_count = 0
    active_vehicle_ids: set[str] = set()
    entry_order: list[str] = []
    entry_rank: dict[str, int] = {}
    controlled_vehicle_ids: set[str] = set()
    fifo_natural_eta: dict[str, float] = {}
    fifo_target_time: dict[str, float] = {}
    fifo_last_assigned_target: float | None = None

    traci.start(cmd)
    with trace_path.open('w', newline='', encoding='utf-8') as trace_fp, collisions_path.open(
        'w', newline='', encoding='utf-8'
    ) as collision_fp, plans_path.open('w', newline='', encoding='utf-8') as plan_fp:
        trace_writer = csv.DictWriter(trace_fp, fieldnames=trace_fields, lineterminator='\n')
        collision_writer = csv.DictWriter(
            collision_fp, fieldnames=collision_fields, lineterminator='\n'
        )
        plan_writer = csv.DictWriter(plan_fp, fieldnames=plan_fields, lineterminator='\n')
        trace_writer.writeheader()
        collision_writer.writeheader()
        plan_writer.writeheader()

        try:
            for _ in range(max_steps):
                traci.simulationStep()
                sim_time = float(traci.simulation.getTime())
                active_vehicle_ids = set(traci.vehicle.getIDList())
                control_zone_state: dict[str, dict[str, float | str]] = {}
                desired_speed_by_vehicle: dict[str, float] = {}

                for collision in traci.simulation.getCollisions():
                    collision_writer.writerow(_collision_to_row(sim_time, collision))
                    collision_count += 1

                for veh_id in sorted(active_vehicle_ids):
                    route_edges = tuple(traci.vehicle.getRoute(veh_id))
                    stream = _stream_from_route(route_edges)
                    road_id = traci.vehicle.getRoadID(veh_id)

                    if road_id == merge_edge and veh_id not in crossed_merge:
                        crossed_merge.add(veh_id)
                        cross_time[veh_id] = sim_time

                    d_to_merge = _distance_to_merge(veh_id, merge_edge, traci)
                    if d_to_merge is None or d_to_merge <= 0:
                        continue
                    if d_to_merge > control_zone_length_m:
                        continue

                    if veh_id not in entered_control:
                        entered_control.add(veh_id)
                        entry_order.append(veh_id)
                        entry_rank[veh_id] = len(entry_order)
                        entry_info[veh_id] = {
                            't_entry': sim_time,
                            'd_entry': d_to_merge,
                            'stream': stream,
                        }
                        if policy == 'fifo':
                            stream_vmax = _stream_vmax(stream, main_vmax_mps, ramp_vmax_mps)
                            natural_eta_at_entry = sim_time + d_to_merge / stream_vmax
                            if fifo_last_assigned_target is None:
                                target_cross_time = max(natural_eta_at_entry, sim_time + fifo_gap_s)
                            else:
                                target_cross_time = max(
                                    natural_eta_at_entry, fifo_last_assigned_target + fifo_gap_s
                                )
                            fifo_natural_eta[veh_id] = natural_eta_at_entry
                            fifo_target_time[veh_id] = target_cross_time
                            fifo_last_assigned_target = target_cross_time

                    speed = float(traci.vehicle.getSpeed(veh_id))
                    is_stopped = speed < 0.1
                    if is_stopped and not prev_stopped.get(veh_id, False):
                        stop_count += 1
                    prev_stopped[veh_id] = is_stopped

                    control_zone_state[veh_id] = {
                        'stream': stream,
                        'edge_id': road_id,
                        'lane_id': traci.vehicle.getLaneID(veh_id),
                        'lane_pos': float(traci.vehicle.getLanePosition(veh_id)),
                        'd_to_merge': d_to_merge,
                        'speed': speed,
                        'accel': float(traci.vehicle.getAcceleration(veh_id)),
                    }

                schedule_order: list[str] = []
                schedule_target_time: dict[str, float] = {}
                schedule_eta: dict[str, float] = {}

                if policy == 'fifo':
                    schedule_order = [
                        veh_id
                        for veh_id in entry_order
                        if veh_id in control_zone_state and veh_id not in crossed_merge
                    ]
                    schedule_target_time = {
                        veh_id: fifo_target_time[veh_id] for veh_id in schedule_order
                    }
                    schedule_eta = {
                        veh_id: fifo_natural_eta[veh_id] for veh_id in schedule_order
                    }
                elif policy == 'dp':
                    dp_candidates = [
                        veh_id
                        for veh_id in control_zone_state
                        if veh_id not in crossed_merge
                    ]
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
                        stream_vmax = _stream_vmax(stream, main_vmax_mps, ramp_vmax_mps)
                        t_min_s[veh_id] = minimum_arrival_time_at_on_ramp(
                            t_now_s=sim_time,
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
                    schedule_order = dp_result.passing_order
                    schedule_target_time = dict(dp_result.target_cross_time_s)
                    # Reuse Stage 1 plans.csv field name `natural_eta`; for dp this is t_min.
                    schedule_eta = dict(t_min_s)

                if policy in {'fifo', 'dp'}:
                    prev_target: float | None = None
                    current_controlled = set(schedule_order)
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

                        time_to_target = max(target_cross_time - sim_time, step_length)
                        v_des = d_to_merge / time_to_target
                        stream_vmax = _stream_vmax(stream, main_vmax_mps, ramp_vmax_mps)
                        v_des = max(0.0, min(v_des, stream_vmax))
                        traci.vehicle.setSpeed(veh_id, v_des)
                        desired_speed_by_vehicle[veh_id] = v_des

                        plan_writer.writerow(
                            {
                                'time': sim_time,
                                'entry_rank': entry_rank[veh_id],
                                'order_index': order_index,
                                'veh_id': veh_id,
                                'stream': stream,
                                't_enter_control_zone': float(entry_info[veh_id]['t_entry']),
                                'D_to_merge': d_to_merge,
                                'speed': speed,
                                'natural_eta': natural_eta,
                                'target_cross_time': target_cross_time,
                                'gap_from_prev': gap_from_prev,
                                'v_des': v_des,
                            }
                        )

                    to_release = controlled_vehicle_ids - current_controlled
                    for veh_id in to_release:
                        if veh_id in active_vehicle_ids:
                            traci.vehicle.setSpeed(veh_id, -1)
                    controlled_vehicle_ids = current_controlled
                else:
                    if controlled_vehicle_ids:
                        for veh_id in controlled_vehicle_ids:
                            if veh_id in active_vehicle_ids:
                                traci.vehicle.setSpeed(veh_id, -1)
                        controlled_vehicle_ids = set()

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
        finally:
            for veh_id in controlled_vehicle_ids:
                if veh_id in active_vehicle_ids:
                    traci.vehicle.setSpeed(veh_id, -1)
            traci.close()

    pending_unfinished = {
        veh_id for veh_id in entered_control if veh_id not in cross_time and veh_id in active_vehicle_ids
    }
    evaluated_entered = entered_control - pending_unfinished
    successful_merge = [veh_id for veh_id in evaluated_entered if veh_id in cross_time]
    merge_success_rate = (
        len(successful_merge) / len(evaluated_entered) if evaluated_entered else 0.0
    )

    delays: list[float] = []
    for veh_id in successful_merge:
        vehicle_entry = entry_info[veh_id]
        stream = str(vehicle_entry['stream'])
        free_flow_speed = main_vmax_mps if stream == 'main' else ramp_vmax_mps
        t_entry = float(vehicle_entry['t_entry'])
        d_entry = float(vehicle_entry['d_entry'])
        free_flow_time = d_entry / free_flow_speed
        delays.append(cross_time[veh_id] - (t_entry + free_flow_time))

    avg_delay = sum(delays) / len(delays) if delays else 0.0
    throughput_veh_per_h = (len(crossed_merge) / duration_s) * 3600.0

    metrics = {
        'policy_name': policy,
        'merge_success_rate': merge_success_rate,
        'avg_delay_at_merge_s': avg_delay,
        'throughput_veh_per_h': throughput_veh_per_h,
        'collision_count': collision_count,
        'stop_count': stop_count,
        'entered_control_count': len(entered_control),
        'evaluated_entered_count': len(evaluated_entered),
        'pending_unfinished_count': len(pending_unfinished),
        'crossed_merge_count': len(crossed_merge),
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
    )


if __name__ == '__main__':
    raise SystemExit(main())
