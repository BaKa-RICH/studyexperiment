"""Execution state machine for active_gap_v1.

Implements the state transition table from design.md §6.5.
"""

from __future__ import annotations

from .types import ExecutionState

_VALID_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.APPROACHING: {ExecutionState.PLANNING},
    ExecutionState.PLANNING: {
        ExecutionState.COMMITTED,
        ExecutionState.PLANNING,
        ExecutionState.FAIL_SAFE_STOP,
    },
    ExecutionState.COMMITTED: {
        ExecutionState.EXECUTING,
        ExecutionState.COMMITTED,
        ExecutionState.FAIL_SAFE_STOP,
    },
    ExecutionState.EXECUTING: {
        ExecutionState.POST_MERGE,
        ExecutionState.FAIL_SAFE_STOP,
    },
    ExecutionState.POST_MERGE: set(),
    ExecutionState.FAIL_SAFE_STOP: {ExecutionState.ABORTED},
    ExecutionState.ABORTED: set(),
}


def validate_transition(
    current: ExecutionState, target: ExecutionState,
) -> str | None:
    """Return None if transition is valid, or an error reason string."""
    allowed = _VALID_TRANSITIONS.get(current)
    if allowed is None:
        return f"unknown_state:{current}"
    if target not in allowed:
        return f"illegal_transition:{current}->{target}"
    return None


def is_terminal(state: ExecutionState) -> bool:
    return state in (ExecutionState.POST_MERGE, ExecutionState.ABORTED)


def check_tcg_validity(
    p_x: float, m_x: float, s_x: float, zone_length: float,
) -> bool:
    """Return True if all TCG members are inside [0, zone_length]."""
    for x in (p_x, m_x, s_x):
        if x < 0.0 or x > zone_length:
            return False
    return True
