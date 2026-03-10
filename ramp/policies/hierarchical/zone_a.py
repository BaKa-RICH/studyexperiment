"""Zone A: Upstream asymmetric lane-change evacuation algorithm.

Evacuation score (Eq. for lane transition k -> k+1):
  S_evac(k->k+1) = alpha * max(0, (rho_k - rho_{k+1}) / rho_max)
                  + beta  * max(0, (v_bar_{k+1} - v_bar_k) / v_limit)

Only allows lane0->1, lane1->2, lane2->3 (away from ramp direction).
Only CAV vehicles are controlled.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from typing import Any

from ramp.policies.hierarchical.state_collector_ext import ZoneAInfo

logger = logging.getLogger(__name__)

ZONE_A_EDGE = 'main_h2'


@dataclass
class ZoneAEvacuator:
    v_limit_mps: float
    alpha: float = 0.6
    beta: float = 0.4
    s_threshold: float = 0.35
    rho_max: float = 120.0
    t_cooldown_s: float = 5.0
    h_safe_s: float = 1.5
    lc_duration_s: float = 3.0
    _last_lc_time: dict[str, float] = field(default_factory=dict)

    def evaluate(
        self,
        *,
        sim_time_s: float,
        zone_a_info: ZoneAInfo | None,
        vehicle_types: dict[str, str],
        traci: Any,
    ) -> dict[str, tuple[int, float]]:
        """Evaluate which CAVs should change lanes away from the ramp.

        Returns: {veh_id: (target_lane_index, duration_s)}
        """
        if zone_a_info is None:
            return {}

        max_lane = max(zone_a_info.lane_densities.keys(), default=-1)
        if max_lane < 1:
            return {}

        feasible_transitions: dict[int, float] = {}
        for k in range(max_lane):
            rho_k = zone_a_info.lane_densities.get(k, 0.0)
            rho_k1 = zone_a_info.lane_densities.get(k + 1, 0.0)
            v_k = zone_a_info.lane_avg_speeds.get(k, 0.0)
            v_k1 = zone_a_info.lane_avg_speeds.get(k + 1, 0.0)

            density_term = (
                max(0.0, (rho_k - rho_k1) / self.rho_max)
                if self.rho_max > 0
                else 0.0
            )
            speed_term = (
                max(0.0, (v_k1 - v_k) / self.v_limit_mps)
                if self.v_limit_mps > 0
                else 0.0
            )
            score = self.alpha * density_term + self.beta * speed_term

            if score >= self.s_threshold:
                feasible_transitions[k] = score
                logger.debug(
                    'Zone A: lane %d->%d score=%.3f (density=%.3f speed=%.3f)',
                    k, k + 1, score, density_term, speed_term,
                )

        if not feasible_transitions:
            return {}

        actions: dict[str, tuple[int, float]] = {}
        active_vehs = set(traci.vehicle.getIDList())

        for src_lane in sorted(feasible_transitions.keys()):
            target_lane = src_lane + 1
            src_lane_id = f'{ZONE_A_EDGE}_{src_lane}'
            target_lane_id = f'{ZONE_A_EDGE}_{target_lane}'

            src_vehs = list(traci.lane.getLastStepVehicleIDs(src_lane_id))
            target_vehs = list(traci.lane.getLastStepVehicleIDs(target_lane_id))

            target_positions: list[float] = []
            for vid in target_vehs:
                if vid in active_vehs:
                    target_positions.append(
                        float(traci.vehicle.getLanePosition(vid))
                    )
            target_positions.sort()

            for veh_id in src_vehs:
                if veh_id not in active_vehs:
                    continue
                if veh_id in actions:
                    continue

                vtype = vehicle_types.get(veh_id, '')
                if not vtype:
                    vtype = traci.vehicle.getTypeID(veh_id)
                if vtype != 'cav':
                    continue

                last_t = self._last_lc_time.get(veh_id, -999.0)
                if sim_time_s - last_t < self.t_cooldown_s:
                    continue

                veh_pos = float(traci.vehicle.getLanePosition(veh_id))
                veh_speed = float(traci.vehicle.getSpeed(veh_id))
                required_gap = veh_speed * self.h_safe_s

                if _check_gap(veh_pos, required_gap, target_positions):
                    actions[veh_id] = (target_lane, self.lc_duration_s)
                    self._last_lc_time[veh_id] = sim_time_s
                    logger.debug(
                        'Zone A: evacuate %s lane %d->%d (pos=%.1f spd=%.1f)',
                        veh_id, src_lane, target_lane, veh_pos, veh_speed,
                    )

        return actions


def _check_gap(
    veh_pos: float,
    required_gap: float,
    sorted_positions: list[float],
) -> bool:
    """Check if a safe gap exists at veh_pos within sorted target-lane positions."""
    if not sorted_positions:
        return True
    idx = bisect.bisect_right(sorted_positions, veh_pos)
    if idx < len(sorted_positions):
        if sorted_positions[idx] - veh_pos < required_gap:
            return False
    if idx > 0:
        if veh_pos - sorted_positions[idx - 1] < required_gap:
            return False
    return True
