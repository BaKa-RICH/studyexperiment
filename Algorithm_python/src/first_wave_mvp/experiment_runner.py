"""最小纯 Python 数值实验执行器。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from first_wave_mvp.commit import commit_candidate
from first_wave_mvp.gate import accept_candidate
from first_wave_mvp.metrics_collector import MetricsCollector
from first_wave_mvp.rollout import rollout_step
from first_wave_mvp.scenario_initializer import initialize_scenario
from first_wave_mvp.snapshot import build_snapshot, select_planning_ego
from first_wave_mvp.step2_fifo import generate_candidates
from first_wave_mvp.types import ExecutionState, PolicyTag, VehicleState


def _advance_mainline_states(world_state: dict[str, VehicleState], tick_s: float) -> None:
    for state in world_state.values():
        if state.stream != "ramp":
            state.x_pos_m += state.speed_mps * tick_s


def _active_ramp_state(world_state: dict[str, VehicleState]) -> dict[str, VehicleState]:
    return {
        veh_id: state
        for veh_id, state in world_state.items()
        if state.stream == "ramp"
    }


def _normalize_completed_ramp(world_state: dict[str, VehicleState], veh_id: str) -> None:
    state = world_state[veh_id]
    state.stream = "mainline"
    state.lane_id = "main_0"


def run_seed_experiment(
    *,
    experiment_id: str,
    policy_tag: PolicyTag,
    seed: int,
    parameters: dict[str, Any],
) -> dict[str, object]:
    initialized = initialize_scenario(
        experiment_id=experiment_id,
        seed=seed,
        parameters=parameters,
    )
    world_state = deepcopy(initialized.world_state)
    committed_plans = deepcopy(initialized.committed_plans)
    scenario = initialized.scenario
    ramp_vehicle_ids = {veh_id for veh_id, state in world_state.items() if state.stream == "ramp"}
    collector = MetricsCollector(
        scenario=scenario,
        experiment_id=experiment_id,
        policy_tag=policy_tag,
        seed=seed,
        ramp_vehicle_ids=ramp_vehicle_ids,
    )

    sim_time_s = 0.0
    for tick_index in range(initialized.max_ticks):
        sim_time_s = tick_index * scenario.rollout_tick_s
        previous_world_state = deepcopy(world_state)

        planning_ego = select_planning_ego(world_state)
        if planning_ego is not None:
            snapshot = build_snapshot(
                sim_time_s=sim_time_s,
                scenario=scenario,
                world_state=world_state,
                committed_plans=committed_plans,
                policy_tag=policy_tag,
            )
            candidates = generate_candidates(snapshot=snapshot)
            for candidate in candidates:
                gate_result = accept_candidate(snapshot=snapshot, candidate=candidate)
                if gate_result.accepted:
                    committed_plan = commit_candidate(
                        snapshot=snapshot,
                        candidate=candidate,
                        gate_result=gate_result,
                    )
                    committed_plans[candidate.ego_id] = committed_plan
                    collector.record_commit(candidate.ego_id, committed_plan)
                    break

        _advance_mainline_states(world_state, scenario.rollout_tick_s)
        ramp_world_state = _active_ramp_state(world_state)
        if ramp_world_state:
            active_committed_plans = {
                veh_id: plan
                for veh_id, plan in committed_plans.items()
                if veh_id in ramp_world_state
            }
            next_ramp_state = rollout_step(
                scenario=scenario,
                world_state=ramp_world_state,
                committed_plans=active_committed_plans,
            )
            world_state.update(next_ramp_state)

        sim_time_after_tick_s = sim_time_s + scenario.rollout_tick_s
        for veh_id in ramp_vehicle_ids:
            previous_state = previous_world_state[veh_id]
            current_state = world_state[veh_id]
            collector.record_state_transition(
                veh_id=veh_id,
                previous_state=previous_state,
                current_state=current_state,
                sim_time_s=sim_time_after_tick_s,
            )
            if (
                previous_state.execution_state is not ExecutionState.POST_MERGE
                and current_state.execution_state is ExecutionState.POST_MERGE
            ):
                _normalize_completed_ramp(world_state, veh_id)
                committed_plans.pop(veh_id, None)
            if current_state.execution_state is ExecutionState.ABORTED:
                committed_plans.pop(veh_id, None)

        collector.record_tick(world_state)

        unresolved_ids = [
            veh_id
            for veh_id in ramp_vehicle_ids
            if world_state[veh_id].execution_state not in {ExecutionState.POST_MERGE, ExecutionState.ABORTED}
        ]
        if not unresolved_ids:
            break

        if sim_time_after_tick_s >= initialized.sim_duration_s:
            break

    result = collector.finalize(sim_duration_s=max(sim_time_s + scenario.rollout_tick_s, scenario.rollout_tick_s))
    unresolved_ids = [
        veh_id
        for veh_id in ramp_vehicle_ids
        if world_state[veh_id].execution_state not in {ExecutionState.POST_MERGE, ExecutionState.ABORTED}
    ]
    if unresolved_ids:
        result["failed"] = True
        result["failure_reason"] = "max_ticks_exhausted"
    return result


def run_policy_experiment(
    *,
    experiment_id: str,
    policy_tag: PolicyTag,
    seeds: tuple[int, ...],
    parameters: dict[str, Any],
) -> list[dict[str, object]]:
    return [
        run_seed_experiment(
            experiment_id=experiment_id,
            policy_tag=policy_tag,
            seed=seed,
            parameters=parameters,
        )
        for seed in seeds
    ]


def ensure_output_directory(output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "ensure_output_directory",
    "run_policy_experiment",
    "run_seed_experiment",
]
