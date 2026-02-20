from __future__ import annotations

import math


def minimum_arrival_time_at_on_ramp(
    *,
    t_now_s: float,
    distance_m: float,
    speed_mps: float,
    a_max_mps2: float,
    v_max_mps: float,
) -> float:
    """Compute the minimum feasible arrival time at the fixed merge point.

    This follows CAVSim `ArrivalTime::CalculMinimumArrivalTimeAtOnRamp` and adds
    the boundary protections required by `docs/PLAN_RAMP_STAGE2.md`.
    """

    if distance_m <= 0:
        return float(t_now_s)

    v_max_mps = float(v_max_mps)
    if v_max_mps <= 1e-6:
        # Degenerate configuration; avoid division by zero.
        return float(t_now_s)

    speed_mps = max(float(speed_mps), 0.0)
    a_max_mps2 = float(a_max_mps2)

    if a_max_mps2 <= 1e-6:
        # Cannot accelerate; fall back to constant-speed estimate.
        effective_speed = max(min(speed_mps, v_max_mps), 1e-3)
        return float(t_now_s) + float(distance_m) / effective_speed

    if speed_mps >= v_max_mps:
        # Already at/above vmax; treat as cruise at vmax for a conservative bound.
        return float(t_now_s) + float(distance_m) / v_max_mps

    dist_to_vmax = (v_max_mps * v_max_mps - speed_mps * speed_mps) / (2.0 * a_max_mps2)
    if dist_to_vmax >= distance_m:
        # Cannot reach vmax within the remaining distance.
        radicand = speed_mps * speed_mps + 2.0 * a_max_mps2 * float(distance_m)
        radicand = max(radicand, 0.0)
        dt = (math.sqrt(radicand) - speed_mps) / a_max_mps2
        return float(t_now_s) + max(dt, 0.0)

    # Accelerate to vmax, then cruise.
    accel_time = (v_max_mps - speed_mps) / a_max_mps2
    cruise_distance = float(distance_m) - dist_to_vmax
    cruise_time = cruise_distance / v_max_mps
    return float(t_now_s) + max(accel_time, 0.0) + max(cruise_time, 0.0)

