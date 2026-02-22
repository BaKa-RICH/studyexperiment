from __future__ import annotations

from ramp.runtime.types import ControlCommand, Plan


def _stream_vmax(stream: str, main_vmax_mps: float, ramp_vmax_mps: float) -> float:
    if stream == 'main':
        return main_vmax_mps
    if stream == 'ramp':
        return ramp_vmax_mps
    return max(main_vmax_mps, ramp_vmax_mps)


def build_command(
    *,
    sim_time_s: float,
    step_length_s: float,
    plan: Plan,
    control_zone_state: dict[str, dict[str, float | str]],
    main_vmax_mps: float,
    ramp_vmax_mps: float,
) -> ControlCommand:
    set_speed_mps: dict[str, float] = {}
    for veh_id in plan.order:
        vehicle_state = control_zone_state[veh_id]
        stream = str(vehicle_state['stream'])
        d_to_merge = float(vehicle_state['d_to_merge'])
        target_cross_time = float(plan.target_cross_time_s[veh_id])
        time_to_target = max(target_cross_time - sim_time_s, step_length_s)
        stream_vmax = _stream_vmax(stream, main_vmax_mps, ramp_vmax_mps)
        v_des = d_to_merge / time_to_target
        set_speed_mps[veh_id] = max(0.0, min(v_des, stream_vmax))
    return ControlCommand(set_speed_mps=set_speed_mps)

