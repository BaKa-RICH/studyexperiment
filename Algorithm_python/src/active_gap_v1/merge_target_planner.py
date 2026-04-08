"""Merge target enumeration and deterministic ranking for active_gap_v1."""

from __future__ import annotations

import math

from .predictor import predict_free_position, predict_optional_free_position
from .types import AnchorMode, CoordinationSnapshot, MergeTarget, TCG, VehicleState

_EPS = 1e-9

_H_MIN_S = 1.0
_H_MAX_S = 10.0
_H_STEP_S = 0.5
_V_STEP_MPS = 1.0
_V_MIN_STAR_MPS = 5.0
_FLEX_X_STEP_M = 20.0


def _float_grid(*, start: float, end: float, step: float) -> list[float]:
    if step <= 0.0:
        raise ValueError("step must be positive")
    if end < start:
        return []
    count = int(math.floor((end - start) / step + _EPS))
    values = [round(start + idx * step, 10) for idx in range(count + 1)]
    if values and values[-1] < end - _EPS:
        values.append(round(end, 10))
    return values


def _terminal_distance_pm(*, vehicle_length_m: float, min_gap_m: float, h_pr_s: float, v_star_mps: float) -> float:
    return vehicle_length_m + min_gap_m + h_pr_s * v_star_mps


def _terminal_distance_ms(*, vehicle_length_m: float, min_gap_m: float, h_rf_s: float, v_star_mps: float) -> float:
    return vehicle_length_m + min_gap_m + h_rf_s * v_star_mps


def _is_terminal_reachable(
    *,
    vehicle: VehicleState,
    x_target_m: float,
    v_target_mps: float,
    horizon_s: float,
    a_max_mps2: float,
    b_max_mps2: float,
    v_max_mps: float,
) -> bool:
    x_free_m = predict_free_position(vehicle=vehicle, horizon_s=horizon_s)
    lower_m = x_free_m - 0.5 * b_max_mps2 * horizon_s * horizon_s
    upper_m = x_free_m + 0.5 * a_max_mps2 * horizon_s * horizon_s
    if not (lower_m - _EPS <= x_target_m <= upper_m + _EPS):
        return False

    v0 = vehicle.speed_mps
    dv = v_target_mps - v0
    if dv > 0 and dv > a_max_mps2 * horizon_s + _EPS:
        return False
    if dv < 0 and -dv > b_max_mps2 * horizon_s + _EPS:
        return False

    avg_v = (x_target_m - vehicle.x_pos_m) / horizon_s if horizon_s > _EPS else 0.0
    if avg_v < -_EPS or avg_v > v_max_mps + 0.5 * a_max_mps2 * horizon_s + _EPS:
        return False

    return True


def _admissible_x_m_values(*, tcg: TCG, snapshot: CoordinationSnapshot) -> list[float]:
    scenario = snapshot.scenario
    if tcg.anchor_mode == AnchorMode.FIXED:
        return [float(scenario.fixed_anchor_m)]

    zone_start_m, zone_end_m = scenario.legal_merge_zone_m
    return _float_grid(
        start=float(zone_start_m),
        end=float(zone_end_m),
        step=_FLEX_X_STEP_M,
    )


def enumerate_merge_targets(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> list[MergeTarget]:
    scenario = snapshot.scenario
    states = snapshot.control_zone_states

    p_state = states.get(tcg.p_id)
    m_state = states.get(tcg.m_id)
    s_state = states.get(tcg.s_id)
    if p_state is None or m_state is None or s_state is None:
        return []

    # u/f are optional boundaries; keep None semantics as-is.
    u_state = states.get(tcg.u_id) if tcg.u_id is not None else None
    f_state = states.get(tcg.f_id) if tcg.f_id is not None else None

    v_group_avg_mps = (p_state.speed_mps + m_state.speed_mps + s_state.speed_mps) / 3.0
    v_upper_mps = min(scenario.ramp_vmax_mps, scenario.mainline_vmax_mps)
    horizons_s = _float_grid(start=_H_MIN_S, end=_H_MAX_S, step=_H_STEP_S)
    v_candidates_mps = _float_grid(start=_V_MIN_STAR_MPS, end=v_upper_mps, step=_V_STEP_MPS)
    x_m_candidates_m = _admissible_x_m_values(tcg=tcg, snapshot=snapshot)

    zone_start_m, zone_end_m = scenario.legal_merge_zone_m
    targets: list[MergeTarget] = []

    for horizon_s in horizons_s:
        if horizon_s <= 0.0:
            continue

        # Keep optional boundary prediction available for downstream extensions.
        _ = predict_optional_free_position(vehicle=u_state, horizon_s=horizon_s)
        _ = predict_optional_free_position(vehicle=f_state, horizon_s=horizon_s)

        x_p_free_m = predict_free_position(vehicle=p_state, horizon_s=horizon_s)
        x_s_free_m = predict_free_position(vehicle=s_state, horizon_s=horizon_s)
        natural_gap_m = x_p_free_m - x_s_free_m

        for v_star_mps in v_candidates_mps:
            if not (0.0 <= v_star_mps <= v_upper_mps + _EPS):
                continue

            d_pm_m = _terminal_distance_pm(
                vehicle_length_m=scenario.vehicle_length_m,
                min_gap_m=scenario.min_gap_m,
                h_pr_s=scenario.h_pr_s,
                v_star_mps=v_star_mps,
            )
            d_ms_m = _terminal_distance_ms(
                vehicle_length_m=scenario.vehicle_length_m,
                min_gap_m=scenario.min_gap_m,
                h_rf_s=scenario.h_rf_s,
                v_star_mps=v_star_mps,
            )
            required_gap_m = d_pm_m + d_ms_m
            delta_open_m = max(0.0, required_gap_m - natural_gap_m)

            for x_m_star_m in x_m_candidates_m:
                tau_lc_s = horizon_s - scenario.lane_change_duration_s
                if tau_lc_s < -_EPS:
                    continue

                if x_m_star_m < zone_start_m - _EPS or x_m_star_m > zone_end_m + _EPS:
                    continue

                x_lc_star_m = m_state.x_pos_m + m_state.speed_mps * tau_lc_s
                if x_lc_star_m < zone_start_m - _EPS:
                    continue

                x_p_star_m = x_m_star_m + d_pm_m
                x_s_star_m = x_m_star_m - d_ms_m

                if not _is_terminal_reachable(
                    vehicle=p_state,
                    x_target_m=x_p_star_m,
                    v_target_mps=v_star_mps,
                    horizon_s=horizon_s,
                    a_max_mps2=scenario.a_max_mps2,
                    b_max_mps2=scenario.b_safe_mps2,
                    v_max_mps=scenario.mainline_vmax_mps,
                ):
                    continue
                if not _is_terminal_reachable(
                    vehicle=m_state,
                    x_target_m=x_m_star_m,
                    v_target_mps=v_star_mps,
                    horizon_s=horizon_s,
                    a_max_mps2=scenario.a_max_mps2,
                    b_max_mps2=scenario.b_safe_mps2,
                    v_max_mps=scenario.ramp_vmax_mps,
                ):
                    continue
                if not _is_terminal_reachable(
                    vehicle=s_state,
                    x_target_m=x_s_star_m,
                    v_target_mps=v_star_mps,
                    horizon_s=horizon_s,
                    a_max_mps2=scenario.a_max_mps2,
                    b_max_mps2=scenario.b_safe_mps2,
                    v_max_mps=scenario.mainline_vmax_mps,
                ):
                    continue

                t_m_star_s = snapshot.sim_time_s + horizon_s
                if m_state.speed_mps > _EPS:
                    t_m_free_s = (x_m_star_m - m_state.x_pos_m) / m_state.speed_mps
                    delta_delay_s = t_m_star_s - t_m_free_s
                else:
                    delta_delay_s = math.inf

                delta_coop_m = abs(x_p_free_m - x_p_star_m) + abs(x_s_free_m - x_s_star_m)
                rho_min_m = min(
                    x_p_star_m - x_m_star_m - d_pm_m,
                    x_m_star_m - x_s_star_m - d_ms_m,
                )
                if abs(rho_min_m) < _EPS:
                    rho_min_m = 0.0

                speed_deviation_mps = abs(v_star_mps - v_group_avg_mps)
                ranking_key = (
                    t_m_star_s,
                    speed_deviation_mps,
                    delta_coop_m,
                    delta_delay_s,
                    -rho_min_m,
                    x_m_star_m,
                )
                targets.append(
                    MergeTarget(
                        snapshot_id=snapshot.snapshot_id,
                        m_id=tcg.m_id,
                        x_m_star_m=x_m_star_m,
                        t_m_star_s=t_m_star_s,
                        horizon_s=horizon_s,
                        v_star_mps=v_star_mps,
                        x_p_star_m=x_p_star_m,
                        x_s_star_m=x_s_star_m,
                        delta_open_m=delta_open_m,
                        delta_coop_m=delta_coop_m,
                        delta_delay_s=delta_delay_s,
                        rho_min_m=rho_min_m,
                        ranking_key=ranking_key,
                    )
                )

    targets.sort(key=lambda target: target.ranking_key)
    return targets
