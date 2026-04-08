"""最小数值执行器的流式指标收集器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from first_wave_mvp.types import CommitState, CommittedPlan, ExecutionState, ScenarioConfig, VehicleState


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


@dataclass(slots=True)
class MetricsCollector:
    scenario: ScenarioConfig
    experiment_id: str
    policy_tag: object
    seed: int
    ramp_vehicle_ids: set[str]
    committed_meta_by_vehicle_id: dict[str, tuple[float, float, int]] = field(default_factory=dict)
    completed_vehicle_ids: set[str] = field(default_factory=set)
    aborted_vehicle_ids: set[str] = field(default_factory=set)
    collision_pairs: set[frozenset[str]] = field(default_factory=set)
    safety_violation_pairs: set[frozenset[str]] = field(default_factory=set)
    completion_time_errors_s: list[float] = field(default_factory=list)
    completion_position_errors_m: list[float] = field(default_factory=list)
    ramp_delays_s: list[float] = field(default_factory=list)

    def record_commit(self, veh_id: str, committed_plan: CommittedPlan) -> None:
        self.committed_meta_by_vehicle_id[veh_id] = (
            committed_plan.candidate.t_r_free_s,
            committed_plan.candidate.t_m_s,
            committed_plan.candidate.x_m_m,
        )

    def record_state_transition(
        self,
        *,
        veh_id: str,
        previous_state: VehicleState,
        current_state: VehicleState,
        sim_time_s: float,
    ) -> None:
        if veh_id not in self.ramp_vehicle_ids:
            return

        if (
            previous_state.execution_state is not ExecutionState.POST_MERGE
            and current_state.execution_state is ExecutionState.POST_MERGE
            and veh_id not in self.completed_vehicle_ids
        ):
            self.completed_vehicle_ids.add(veh_id)
            if veh_id in self.committed_meta_by_vehicle_id:
                t_r_free_s, t_m_s, x_m_m = self.committed_meta_by_vehicle_id[veh_id]
                self.ramp_delays_s.append(sim_time_s - t_r_free_s)
                self.completion_time_errors_s.append(abs(sim_time_s - t_m_s))
                self.completion_position_errors_m.append(abs(current_state.x_pos_m - x_m_m))

        if (
            previous_state.execution_state is not ExecutionState.ABORTED
            and current_state.execution_state is ExecutionState.ABORTED
        ):
            self.aborted_vehicle_ids.add(veh_id)

    def record_tick(self, world_state: dict[str, VehicleState]) -> None:
        lane_groups: dict[str, list[VehicleState]] = {}
        for state in world_state.values():
            lane_groups.setdefault(state.lane_id, []).append(state)

        for states in lane_groups.values():
            states.sort(key=lambda state: state.x_pos_m)
            for idx in range(len(states) - 1):
                follower = states[idx]
                leader = states[idx + 1]
                pair = frozenset({follower.veh_id, leader.veh_id})
                net_gap_m = leader.x_pos_m - follower.x_pos_m - leader.length_m
                if net_gap_m < 0.0:
                    self.collision_pairs.add(pair)
                safe_gap_m = self.scenario.min_gap_m + self.scenario.time_headway_s * max(follower.speed_mps, 0.0)
                if net_gap_m < safe_gap_m:
                    self.safety_violation_pairs.add(pair)

    def finalize(self, *, sim_duration_s: float) -> dict[str, object]:
        total_ramp = len(self.ramp_vehicle_ids)
        completion_rate = len(self.completed_vehicle_ids) / total_ramp if total_ramp else 0.0
        abort_rate = len(self.aborted_vehicle_ids) / total_ramp if total_ramp else 0.0
        throughput_vph = (len(self.completed_vehicle_ids) / sim_duration_s) * 3600.0 if sim_duration_s > 0 else 0.0

        return {
            "experiment_id": self.experiment_id,
            "policy_tag": self.policy_tag,
            "seed": self.seed,
            "completion_rate": round(completion_rate, 10),
            "abort_rate": round(abort_rate, 10),
            "collision_count": len(self.collision_pairs),
            "safety_violation_count": len(self.safety_violation_pairs),
            "avg_ramp_delay_s": round(sum(self.ramp_delays_s) / len(self.ramp_delays_s), 10)
            if self.ramp_delays_s
            else 0.0,
            "throughput_vph": round(throughput_vph, 10),
            "planned_actual_time_error_p95_s": _percentile_95(self.completion_time_errors_s)
            if self.completion_time_errors_s
            else None,
            "planned_actual_position_error_p95_m": _percentile_95(self.completion_position_errors_m)
            if self.completion_position_errors_m
            else None,
            "failed": False,
            "failure_reason": None,
        }


__all__ = ["MetricsCollector"]
