"""Flexible merge-point algorithm for CAV lane-changing from L0 to L1.

Mathematical model based on the time-space gap evaluation (Eq.1-6):
  G_f(t_lc) = (p_l - p_c - L) + (v_l - v_c) * t_lc   ... (Eq.1)
  G_r(t_lc) = (p_c - p_f - L) + (v_c - v_f) * t_lc   ... (Eq.2)
  S1: G_f(t_lc) >= phi * v_l + s0                      ... (Eq.3)
  S2: G_r(t_lc) >= phi * v_c + s0                      ... (Eq.4)

Search strategy: forward scan from CAV position, earliest feasible gap wins.
Fallback: forced merge when CAV position >= lane_length - fallback_buffer.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class MergeState(Enum):
    APPROACHING = auto()
    SEARCHING = auto()
    MERGING = auto()
    MERGED = auto()


@dataclass(frozen=True)
class MergePointParams:
    phi_s: float = 1.5
    t_lc_s: float = 3.0
    L_veh_m: float = 5.0
    s0_m: float = 5.0
    fallback_buffer_m: float = 50.0
    lane0_length_m: float = 309.41
    search_start_pos_m: float = 30.0
    timeout_buffer_s: float = 1.0
    max_retries: int = 3


@dataclass
class MergeEvalResult:
    feasible: bool
    merge_position_m: float | None = None
    gap_front_m: float | None = None
    gap_rear_m: float | None = None
    lead_id: str | None = None
    follow_id: str | None = None
    is_fallback: bool = False
    safety_margin: float | None = None


@dataclass
class VehicleState:
    edge_id: str
    lane_index: int
    lane_pos_m: float
    speed_mps: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass
class _MergeTracker:
    state: MergeState = field(default=MergeState.APPROACHING)
    merge_start_time_s: float | None = None
    merge_start_pos_m: float | None = None
    failure_count: int = 0
    last_eval: MergeEvalResult | None = None
    planned_lead_id: str | None = None
    planned_follow_id: str | None = None


def _evaluate_gap_safety(
    cav_pos_m: float,
    cav_speed_mps: float,
    lead: tuple[str, float, float] | None,
    follow: tuple[str, float, float] | None,
    params: MergePointParams,
) -> tuple[bool, float | None, float | None, float | None]:
    """Evaluate a single gap's safety using Eq.1-4.

    Returns (feasible, G_f_at_t_lc, G_r_at_t_lc, safety_margin).
    Gap values are None when no vehicle exists on that side.
    """
    if lead is not None:
        _, p_l, v_l = lead
        g_f: float | None = (
            (p_l - cav_pos_m - params.L_veh_m)
            + (v_l - cav_speed_mps) * params.t_lc_s
        )
        margin_f = g_f - (params.phi_s * v_l + params.s0_m)
    else:
        g_f = None
        margin_f = float('inf')

    if follow is not None:
        _, p_f, v_f = follow
        g_r: float | None = (
            (cav_pos_m - p_f - params.L_veh_m)
            + (cav_speed_mps - v_f) * params.t_lc_s
        )
        margin_r = g_r - (params.phi_s * cav_speed_mps + params.s0_m)
    else:
        g_r = None
        margin_r = float('inf')

    feasible = margin_f >= 0.0 and margin_r >= 0.0
    finite_margins = [m for m in (margin_f, margin_r) if m != float('inf')]
    safety_margin = min(finite_margins) if finite_margins else None

    return feasible, g_f, g_r, safety_margin


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate_merge_point(
    cav_pos_m: float,
    cav_speed_mps: float,
    lane1_vehicles: list[tuple[str, float, float]],
    params: MergePointParams | None = None,
) -> MergeEvalResult:
    """Evaluate the best merge point for a CAV merging from L0 to L1.

    Forward-scan strategy: checks gaps starting from the CAV's current
    longitudinal position and moving forward. Returns the first feasible gap.
    Triggers forced fallback when the CAV reaches the fallback position.

    Args:
        cav_pos_m:       CAV longitudinal position on main_h3 L0 (m).
        cav_speed_mps:   CAV speed (m/s).
        lane1_vehicles:  Vehicles on L1 as [(veh_id, lane_pos_m, speed_mps)].
        params:          Algorithm parameters (defaults used if None).

    Returns:
        MergeEvalResult with feasibility, gap metrics, and vehicle IDs.
    """
    if params is None:
        params = MergePointParams()

    fallback_pos = params.lane0_length_m - params.fallback_buffer_m
    merge_pos = cav_pos_m + cav_speed_mps * params.t_lc_s

    # ---- Fallback: forced merge near end of L0 ----
    if cav_pos_m >= fallback_pos:
        return MergeEvalResult(
            feasible=True,
            merge_position_m=merge_pos,
            is_fallback=True,
        )

    # ---- Empty L1: always feasible ----
    if not lane1_vehicles:
        return MergeEvalResult(
            feasible=True,
            merge_position_m=merge_pos,
        )

    # ---- Forward scan across gaps ----
    sorted_vehs = sorted(lane1_vehicles, key=lambda x: x[1])
    positions = [v[1] for v in sorted_vehs]
    j = bisect.bisect_right(positions, cav_pos_m)
    k = len(sorted_vehs)

    for gap_idx in range(j, k + 1):
        follow = sorted_vehs[gap_idx - 1] if gap_idx > 0 else None
        lead = sorted_vehs[gap_idx] if gap_idx < k else None

        feasible, g_f, g_r, margin = _evaluate_gap_safety(
            cav_pos_m, cav_speed_mps, lead, follow, params,
        )
        if feasible:
            return MergeEvalResult(
                feasible=True,
                merge_position_m=merge_pos,
                gap_front_m=g_f,
                gap_rear_m=g_r,
                lead_id=lead[0] if lead else None,
                follow_id=follow[0] if follow else None,
                is_fallback=False,
                safety_margin=margin,
            )

    return MergeEvalResult(feasible=False)


# ---------------------------------------------------------------------------
# State-machine manager
# ---------------------------------------------------------------------------

class MergePointManager:
    """Per-vehicle state machine manager for the merge process.

    State transitions::

      APPROACHING --> SEARCHING  (enters main_h3 L0, pos >= search_start)
      SEARCHING   --> MERGING    (feasible gap found or fallback triggered)
      MERGING     --> MERGED     (lane change complete: lane_index == 1)
      MERGING     --> SEARCHING  (timeout + retries remaining + pos < fallback)

    Emergency: if a CAV reaches lane0_length - EMERGENCY_BUFFER_M without
    merging, an emergency changeLane is forced to prevent SUMO teleportation.
    """

    EMERGENCY_BUFFER_M = 10.0

    def __init__(self, params: MergePointParams | None = None):
        self.params = params or MergePointParams()
        self._trackers: dict[str, _MergeTracker] = {}
        self.merge_history: list[dict[str, object]] = []
        self.merge_event_log: list[dict[str, object]] = []
        self._event_cursor: int = 0

    @property
    def vehicle_states(self) -> dict[str, MergeState]:
        """Current merge state of every tracked vehicle."""
        return {vid: t.state for vid, t in self._trackers.items()}

    def get_tracker(self, veh_id: str) -> _MergeTracker | None:
        return self._trackers.get(veh_id)

    def consume_events_since_cursor(self) -> list[dict[str, object]]:
        """Return events appended since the last consumption, advance cursor."""
        new_events = self.merge_event_log[self._event_cursor:]
        self._event_cursor = len(self.merge_event_log)
        return new_events

    def _emit(self, event_type: str, veh_id: str, sim_time_s: float, **kwargs):
        entry: dict[str, object] = {
            'event_type': event_type,
            'veh_id': veh_id,
            'sim_time_s': sim_time_s,
        }
        entry.update(kwargs)
        self.merge_event_log.append(entry)

    def update(
        self,
        sim_time_s: float,
        cav_states: dict[str, VehicleState],
        lane1_vehicles: list[tuple[str, float, float]],
    ) -> dict[str, tuple[int, float]]:
        """Run one step of the merge state machines for all tracked CAVs.

        Processes CAVs in descending position order so that farther-downstream
        vehicles are evaluated first (their decisions affect the gap landscape
        for upstream vehicles).

        Returns:
            Lane-change actions to issue: ``{veh_id: (target_lane, duration_s)}``.
        """
        actions: dict[str, tuple[int, float]] = {}
        emergency_pos = self.params.lane0_length_m - self.EMERGENCY_BUFFER_M

        sorted_cavs = sorted(
            cav_states.items(),
            key=lambda x: x[1].lane_pos_m,
            reverse=True,
        )

        for veh_id, vs in sorted_cavs:
            on_merge_lane = vs.edge_id == 'main_h3' and vs.lane_index == 0

            tracker = self._trackers.get(veh_id)
            if tracker is None:
                if not on_merge_lane:
                    continue
                tracker = _MergeTracker()
                self._trackers[veh_id] = tracker

            # Emergency: force merge near edge end to prevent teleportation
            if (
                on_merge_lane
                and vs.lane_pos_m >= emergency_pos
                and tracker.state not in (MergeState.MERGING, MergeState.MERGED)
            ):
                tracker.state = MergeState.MERGING
                tracker.merge_start_time_s = sim_time_s
                tracker.merge_start_pos_m = vs.lane_pos_m
                actions[veh_id] = (1, self.params.t_lc_s)
                self._emit(
                    'emergency_lc', veh_id, sim_time_s,
                    pos_m=vs.lane_pos_m, speed_mps=vs.speed_mps,
                )
                logger.warning(
                    '[MergePoint] %s EMERGENCY LC at pos=%.1fm (edge end imminent)',
                    veh_id, vs.lane_pos_m,
                )
                continue

            # Phase 1: APPROACHING -> SEARCHING
            if tracker.state == MergeState.APPROACHING:
                if on_merge_lane and vs.lane_pos_m >= self.params.search_start_pos_m:
                    tracker.state = MergeState.SEARCHING
                    self._emit(
                        'merge_search_start', veh_id, sim_time_s,
                        pos_m=vs.lane_pos_m, speed_mps=vs.speed_mps,
                    )
                    logger.info(
                        '[MergePoint] %s APPROACHING->SEARCHING pos=%.1fm speed=%.1fm/s',
                        veh_id, vs.lane_pos_m, vs.speed_mps,
                    )

            # Phase 2: MERGING -> completion / timeout
            if tracker.state == MergeState.MERGING:
                if vs.lane_index == 1:
                    tracker.state = MergeState.MERGED
                    self._emit(
                        'lc_complete', veh_id, sim_time_s,
                        pos_m=vs.lane_pos_m, speed_mps=vs.speed_mps,
                        planned_lead_id=tracker.planned_lead_id,
                        planned_follow_id=tracker.planned_follow_id,
                        is_fallback=tracker.last_eval.is_fallback if tracker.last_eval else False,
                    )
                    logger.info(
                        '[MergePoint] %s MERGED at t=%.1fs pos=%.1fm',
                        veh_id, sim_time_s, vs.lane_pos_m,
                    )
                    last_eval = tracker.last_eval
                    self.merge_history.append({
                        'veh_id': veh_id,
                        'merge_time_s': sim_time_s,
                        'merge_pos_m': vs.lane_pos_m,
                        'is_fallback': last_eval.is_fallback if last_eval else False,
                        'gap_lead_id': last_eval.lead_id if last_eval else None,
                        'gap_follow_id': last_eval.follow_id if last_eval else None,
                    })
                elif (
                    tracker.merge_start_time_s is not None
                    and sim_time_s > (
                        tracker.merge_start_time_s
                        + self.params.t_lc_s
                        + self.params.timeout_buffer_s
                    )
                ):
                    tracker.failure_count += 1
                    fallback_pos = (
                        self.params.lane0_length_m
                        - self.params.fallback_buffer_m
                    )
                    if (
                        tracker.failure_count <= self.params.max_retries
                        and vs.lane_pos_m < fallback_pos
                    ):
                        tracker.state = MergeState.SEARCHING
                        self._emit(
                            'lc_timeout_retry', veh_id, sim_time_s,
                            pos_m=vs.lane_pos_m, attempt=tracker.failure_count,
                        )
                    else:
                        actions[veh_id] = (1, self.params.t_lc_s)
                        self._emit(
                            'fallback', veh_id, sim_time_s,
                            pos_m=vs.lane_pos_m, reason='max_retries_or_fallback_pos',
                            attempt=tracker.failure_count,
                        )

            # Phase 3: SEARCHING -> evaluate gap -> potentially MERGING
            if tracker.state == MergeState.SEARCHING:
                result = evaluate_merge_point(
                    cav_pos_m=vs.lane_pos_m,
                    cav_speed_mps=vs.speed_mps,
                    lane1_vehicles=lane1_vehicles,
                    params=self.params,
                )
                tracker.last_eval = result
                if result.feasible:
                    tracker.state = MergeState.MERGING
                    tracker.merge_start_time_s = sim_time_s
                    tracker.merge_start_pos_m = vs.lane_pos_m
                    tracker.planned_lead_id = result.lead_id
                    tracker.planned_follow_id = result.follow_id
                    actions[veh_id] = (1, self.params.t_lc_s)
                    event_type = 'fallback_lc_issued' if result.is_fallback else 'lc_issued'
                    self._emit(
                        event_type, veh_id, sim_time_s,
                        pos_m=vs.lane_pos_m, speed_mps=vs.speed_mps,
                        gap_front_m=result.gap_front_m,
                        gap_rear_m=result.gap_rear_m,
                        safety_margin=result.safety_margin,
                        lead_id=result.lead_id,
                        follow_id=result.follow_id,
                        is_fallback=result.is_fallback,
                    )
                    logger.info(
                        '[MergePoint] %s SEARCHING->MERGING feasible gap_f=%.1f gap_r=%.1f '
                        'margin=%.1f fallback=%s pos=%.1fm',
                        veh_id,
                        result.gap_front_m if result.gap_front_m is not None else -1,
                        result.gap_rear_m if result.gap_rear_m is not None else -1,
                        result.safety_margin if result.safety_margin is not None else -1,
                        result.is_fallback, vs.lane_pos_m,
                    )
                else:
                    self._emit(
                        'gap_reject', veh_id, sim_time_s,
                        pos_m=vs.lane_pos_m, speed_mps=vs.speed_mps,
                        n_lane1=len(lane1_vehicles),
                    )

        return actions
