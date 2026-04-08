"""第一波 MVP 的 commit 协议。"""

from __future__ import annotations

from copy import deepcopy

from first_wave_mvp.types import CommitState, CommittedPlan, ExecutionState, GateResult, PlanningSnapshot


def _validate_commit_preconditions(*, snapshot: PlanningSnapshot, candidate, gate_result: GateResult) -> None:
    if gate_result.accepted is not True:
        raise ValueError("commit_candidate requires accepted=True gate_result")

    if snapshot.snapshot_id != candidate.snapshot_id or snapshot.snapshot_id != gate_result.snapshot_id:
        raise ValueError("snapshot_id mismatch between snapshot, candidate, and gate_result")

    if candidate.candidate_id != gate_result.candidate_id:
        raise ValueError("candidate_id mismatch between candidate and gate_result")

    if snapshot.ego_state.execution_state is not ExecutionState.PLANNING:
        raise ValueError("commit_candidate requires ego execution_state=planning")

    if snapshot.ego_state.commit_state is not CommitState.UNCOMMITTED:
        raise ValueError("commit_candidate requires ego commit_state=uncommitted")


def commit_candidate(*, snapshot: PlanningSnapshot, candidate, gate_result: GateResult) -> CommittedPlan:
    _validate_commit_preconditions(
        snapshot=snapshot,
        candidate=candidate,
        gate_result=gate_result,
    )

    committed_candidate = deepcopy(candidate)
    committed_gate_result = deepcopy(gate_result)

    return CommittedPlan(
        snapshot_id=snapshot.snapshot_id,
        candidate_id=candidate.candidate_id,
        commit_time_s=snapshot.sim_time_s,
        commit_state=CommitState.COMMITTED,
        execution_state=ExecutionState.COMMITTED,
        candidate=committed_candidate,
        gate_result=committed_gate_result,
    )


__all__ = ["commit_candidate"]
