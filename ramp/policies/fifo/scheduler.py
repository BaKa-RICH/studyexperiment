from __future__ import annotations

from ramp.runtime.types import Plan


def compute_plan(
    *,
    sim_time_s: float,
    control_zone_state: dict[str, dict[str, float | str]],
    entry_order: list[str],
    crossed_merge: set[str],
    fifo_target_time: dict[str, float],
    fifo_natural_eta: dict[str, float],
) -> Plan:
    order = [
        veh_id
        for veh_id in entry_order
        if veh_id in control_zone_state and veh_id not in crossed_merge
    ]
    target_cross_time_s = {veh_id: fifo_target_time[veh_id] for veh_id in order}
    eta_s = {veh_id: fifo_natural_eta[veh_id] for veh_id in order}
    return Plan(
        plan_time_s=sim_time_s,
        policy_name='fifo',
        order=order,
        target_cross_time_s=target_cross_time_s,
        eta_s=eta_s,
    )

