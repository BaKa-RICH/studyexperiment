from __future__ import annotations

from ramp.runtime.types import ControlCommand, Plan


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


def build_command(
    *,
    sim_time_s: float,
    step_length_s: float,
    plan: Plan,
    control_zone_state: dict[str, dict[str, float | str]],
    vehicle_types: dict[str, str],
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    aux_vmax_mps: float | None = None,
    zone_a_actions: dict[str, tuple[int, float]] | None = None,
    zone_c_actions: dict[str, tuple[int, float]] | None = None,
) -> ControlCommand:
    set_speed_mps: dict[str, float] = {}
    for veh_id in plan.order:
        raw_type = vehicle_types.get(veh_id, 'hdv')
        veh_type = raw_type if raw_type in ('cav', 'hdv') else 'hdv'
        if veh_type != 'cav':
            continue

        vehicle_state = control_zone_state[veh_id]
        stream = str(vehicle_state['stream'])
        lane_id = str(vehicle_state.get('lane_id', ''))
        d_to_merge = float(vehicle_state['d_to_merge'])
        target_cross_time = float(plan.target_cross_time_s[veh_id])
        time_to_target = max(target_cross_time - sim_time_s, step_length_s)
        stream_vmax = _stream_vmax(
            stream, main_vmax_mps, ramp_vmax_mps,
            aux_vmax_mps=aux_vmax_mps, lane_id=lane_id,
        )
        v_des = d_to_merge / time_to_target
        set_speed_mps[veh_id] = max(0.0, min(v_des, stream_vmax))

    lane_change_targets: dict[str, tuple[int, float]] = {}
    if zone_a_actions:
        lane_change_targets.update(zone_a_actions)
    if zone_c_actions:
        lane_change_targets.update(zone_c_actions)

    return ControlCommand(
        set_speed_mps=set_speed_mps,
        lane_change_targets=lane_change_targets,
    )
