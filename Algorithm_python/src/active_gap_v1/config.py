"""Scenario configuration defaults for active_gap_v1."""

from .types import ScenarioConfig


def default_scenario_config(*, scenario_id: str = "default") -> ScenarioConfig:
    """Return the frozen default ScenarioConfig from formulas/contracts."""
    return ScenarioConfig(scenario_id=scenario_id)
