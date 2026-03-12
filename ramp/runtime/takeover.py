"""Takeover mode configuration for CAV control authority levels.

Defines a four-level escalation ladder controlling how aggressively the
Controller overrides SUMO's built-in vehicle behaviour.  Each level
progressively removes more of SUMO's autonomous safety mechanisms so
that the upstream scheduling algorithm has greater authority.

SUMO speedMode bits (low-5-bit bitmask, SUMO 1.18+):
    bit 0 (1)  – regard safe speed (car-following gap)
    bit 1 (2)  – regard maximum acceleration
    bit 2 (4)  – regard maximum deceleration
    bit 3 (8)  – regard right of way at intersections
    bit 4 (16) – brake hard to avoid passing a red light
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

COMFORTABLE_DECEL_MPS2 = 2.0
SLOWDOWN_DURATION_MIN_S = 1.0


class TakeoverMode(Enum):
    T0_CURRENT = 'current'
    T1_SEMI = 'semi'
    T2_STRICT = 'strict'
    T3_DEBUG_UPPER_BOUND = 'debug_upper_bound'


@dataclass(frozen=True, slots=True)
class TakeoverConfig:
    speed_mode: int
    prohibit_lc_all_cav_on_merge_edge: bool
    prohibit_lc_all_cav_in_control_zone: bool
    use_slow_down_for_decel: bool
    label: str


TAKEOVER_CONFIGS: dict[TakeoverMode, TakeoverConfig] = {
    TakeoverMode.T0_CURRENT: TakeoverConfig(
        speed_mode=23,
        prohibit_lc_all_cav_on_merge_edge=False,
        prohibit_lc_all_cav_in_control_zone=False,
        use_slow_down_for_decel=False,
        label='T0_current',
    ),
    TakeoverMode.T1_SEMI: TakeoverConfig(
        speed_mode=23,
        prohibit_lc_all_cav_on_merge_edge=True,
        prohibit_lc_all_cav_in_control_zone=False,
        use_slow_down_for_decel=False,
        label='T1_semi',
    ),
    TakeoverMode.T2_STRICT: TakeoverConfig(
        speed_mode=22,
        prohibit_lc_all_cav_on_merge_edge=True,
        prohibit_lc_all_cav_in_control_zone=True,
        use_slow_down_for_decel=True,
        label='T2_strict',
    ),
    TakeoverMode.T3_DEBUG_UPPER_BOUND: TakeoverConfig(
        speed_mode=0,
        prohibit_lc_all_cav_on_merge_edge=True,
        prohibit_lc_all_cav_in_control_zone=True,
        use_slow_down_for_decel=False,
        label='T3_debug_upper_bound',
    ),
}


def get_takeover_config(mode: TakeoverMode) -> TakeoverConfig:
    return TAKEOVER_CONFIGS[mode]


def parse_takeover_mode(value: str) -> TakeoverMode:
    for member in TakeoverMode:
        if member.value == value:
            return member
    valid = ', '.join(m.value for m in TakeoverMode)
    raise ValueError(f'Unknown takeover mode {value!r}. Valid: {valid}')


def slowdown_duration_s(actual_speed_mps: float, target_speed_mps: float) -> float:
    """Compute a smooth slowDown duration based on comfortable deceleration."""
    delta = actual_speed_mps - target_speed_mps
    if delta <= 0:
        return SLOWDOWN_DURATION_MIN_S
    return max(SLOWDOWN_DURATION_MIN_S, delta / COMFORTABLE_DECEL_MPS2)


def log_mode_warning(mode: TakeoverMode) -> None:
    if mode == TakeoverMode.T3_DEBUG_UPPER_BOUND:
        logger.warning(
            '[UNSAFE] T3_debug_upper_bound: ALL SUMO safety checks disabled. '
            'Use ONLY for mechanism verification, NOT for paper results.'
        )
    elif mode == TakeoverMode.T2_STRICT:
        logger.warning(
            '[CAUTION] T2_strict: SUMO safe-speed check disabled (speedMode=22). '
            'Algorithm is responsible for collision avoidance.'
        )
