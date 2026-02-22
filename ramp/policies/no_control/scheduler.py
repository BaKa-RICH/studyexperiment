from __future__ import annotations

from ramp.runtime.types import Plan


def compute_plan(*, sim_time_s: float) -> Plan | None:
    """No-control policy does not produce any schedule."""

    _ = sim_time_s
    return None

