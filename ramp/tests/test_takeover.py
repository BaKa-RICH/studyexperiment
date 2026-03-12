"""Unit tests for ramp.runtime.takeover module."""
from __future__ import annotations

import pytest

from ramp.runtime.takeover import (
    COMFORTABLE_DECEL_MPS2,
    SLOWDOWN_DURATION_MIN_S,
    TAKEOVER_CONFIGS,
    TakeoverConfig,
    TakeoverMode,
    get_takeover_config,
    log_mode_warning,
    parse_takeover_mode,
    slowdown_duration_s,
)


def test_takeover_mode_enum_values() -> None:
    assert TakeoverMode.T0_CURRENT.value == 'current'
    assert TakeoverMode.T1_SEMI.value == 'semi'
    assert TakeoverMode.T2_STRICT.value == 'strict'
    assert TakeoverMode.T3_DEBUG_UPPER_BOUND.value == 'debug_upper_bound'


def test_all_modes_have_configs() -> None:
    for mode in TakeoverMode:
        cfg = get_takeover_config(mode)
        assert isinstance(cfg, TakeoverConfig)


def test_speed_mode_values() -> None:
    assert TAKEOVER_CONFIGS[TakeoverMode.T0_CURRENT].speed_mode == 23
    assert TAKEOVER_CONFIGS[TakeoverMode.T1_SEMI].speed_mode == 23
    assert TAKEOVER_CONFIGS[TakeoverMode.T2_STRICT].speed_mode == 22
    assert TAKEOVER_CONFIGS[TakeoverMode.T3_DEBUG_UPPER_BOUND].speed_mode == 0


def test_speed_mode_bit_semantics() -> None:
    t0_mode = TAKEOVER_CONFIGS[TakeoverMode.T0_CURRENT].speed_mode
    assert t0_mode & 1, 'T0 should regard safe speed'
    assert t0_mode & 2, 'T0 should regard max accel'
    assert t0_mode & 4, 'T0 should regard max decel'
    assert not (t0_mode & 8), 'T0 should NOT regard right of way'
    assert t0_mode & 16, 'T0 should brake for red light'

    t2_mode = TAKEOVER_CONFIGS[TakeoverMode.T2_STRICT].speed_mode
    assert not (t2_mode & 1), 'T2 should NOT regard safe speed'
    assert t2_mode & 2, 'T2 should regard max accel'
    assert t2_mode & 4, 'T2 should regard max decel'
    assert not (t2_mode & 8), 'T2 should NOT regard right of way'
    assert t2_mode & 16, 'T2 should brake for red light'

    t3_mode = TAKEOVER_CONFIGS[TakeoverMode.T3_DEBUG_UPPER_BOUND].speed_mode
    assert t3_mode == 0, 'T3 should have all checks off'


def test_lc_prohibition_escalation() -> None:
    t0 = TAKEOVER_CONFIGS[TakeoverMode.T0_CURRENT]
    assert not t0.prohibit_lc_all_cav_on_merge_edge
    assert not t0.prohibit_lc_all_cav_in_control_zone

    t1 = TAKEOVER_CONFIGS[TakeoverMode.T1_SEMI]
    assert t1.prohibit_lc_all_cav_on_merge_edge
    assert not t1.prohibit_lc_all_cav_in_control_zone

    t2 = TAKEOVER_CONFIGS[TakeoverMode.T2_STRICT]
    assert t2.prohibit_lc_all_cav_on_merge_edge
    assert t2.prohibit_lc_all_cav_in_control_zone

    t3 = TAKEOVER_CONFIGS[TakeoverMode.T3_DEBUG_UPPER_BOUND]
    assert t3.prohibit_lc_all_cav_on_merge_edge
    assert t3.prohibit_lc_all_cav_in_control_zone


def test_slow_down_flags() -> None:
    assert not TAKEOVER_CONFIGS[TakeoverMode.T0_CURRENT].use_slow_down_for_decel
    assert not TAKEOVER_CONFIGS[TakeoverMode.T1_SEMI].use_slow_down_for_decel
    assert TAKEOVER_CONFIGS[TakeoverMode.T2_STRICT].use_slow_down_for_decel
    assert not TAKEOVER_CONFIGS[TakeoverMode.T3_DEBUG_UPPER_BOUND].use_slow_down_for_decel


def test_parse_takeover_mode_valid() -> None:
    assert parse_takeover_mode('current') == TakeoverMode.T0_CURRENT
    assert parse_takeover_mode('semi') == TakeoverMode.T1_SEMI
    assert parse_takeover_mode('strict') == TakeoverMode.T2_STRICT
    assert parse_takeover_mode('debug_upper_bound') == TakeoverMode.T3_DEBUG_UPPER_BOUND


def test_parse_takeover_mode_invalid() -> None:
    with pytest.raises(ValueError, match='Unknown takeover mode'):
        parse_takeover_mode('invalid_mode')


def test_slowdown_duration_decel() -> None:
    dur = slowdown_duration_s(actual_speed_mps=20.0, target_speed_mps=10.0)
    expected = (20.0 - 10.0) / COMFORTABLE_DECEL_MPS2
    assert dur == expected


def test_slowdown_duration_small_delta() -> None:
    dur = slowdown_duration_s(actual_speed_mps=1.0, target_speed_mps=0.5)
    assert dur == SLOWDOWN_DURATION_MIN_S


def test_slowdown_duration_no_decel() -> None:
    dur = slowdown_duration_s(actual_speed_mps=10.0, target_speed_mps=15.0)
    assert dur == SLOWDOWN_DURATION_MIN_S


def test_log_mode_warning_t3(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('WARNING'):
        log_mode_warning(TakeoverMode.T3_DEBUG_UPPER_BOUND)
    assert 'UNSAFE' in caplog.text


def test_log_mode_warning_t2(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('WARNING'):
        log_mode_warning(TakeoverMode.T2_STRICT)
    assert 'CAUTION' in caplog.text


def test_log_mode_warning_t0_silent(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('WARNING'):
        log_mode_warning(TakeoverMode.T0_CURRENT)
    assert caplog.text == ''


def test_takeover_config_is_frozen() -> None:
    cfg = get_takeover_config(TakeoverMode.T0_CURRENT)
    with pytest.raises(AttributeError):
        cfg.speed_mode = 999  # type: ignore[misc]
