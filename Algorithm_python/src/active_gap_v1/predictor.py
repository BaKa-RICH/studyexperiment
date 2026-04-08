"""Exogenous constant-speed predictors for active_gap_v1."""

from __future__ import annotations

from .types import VehicleState


def predict_free_position(*, vehicle: VehicleState, horizon_s: float) -> float:
    """Predict free-motion position with constant-speed assumption."""
    return vehicle.x_pos_m + vehicle.speed_mps * horizon_s


def predict_optional_free_position(
    *,
    vehicle: VehicleState | None,
    horizon_s: float,
) -> float | None:
    """Predict optional boundary vehicle; keep None as None."""
    if vehicle is None:
        return None
    return predict_free_position(vehicle=vehicle, horizon_s=horizon_s)
