"""TCG selector for active_gap_v1."""

from __future__ import annotations

from .types import CoordinationSnapshot, TCG, VehicleState


def _select_active_ego_from_snapshot(snapshot: CoordinationSnapshot) -> VehicleState | None:
    ramp_cav_candidates = [
        state
        for state in snapshot.control_zone_states.values()
        if state.stream == "ramp" and state.is_cav
    ]
    if not ramp_cav_candidates:
        return None

    return max(ramp_cav_candidates, key=lambda state: (state.x_pos_m, state.veh_id))


def identify_tcg(
    *,
    snapshot: CoordinationSnapshot,
) -> TCG | None:
    ego_state = _select_active_ego_from_snapshot(snapshot)
    if ego_state is None:
        return None

    mainline_states = sorted(
        (
            state
            for state in snapshot.control_zone_states.values()
            if state.stream == "mainline"
        ),
        key=lambda state: (state.x_pos_m, state.veh_id),
    )

    p_state = next((state for state in mainline_states if state.x_pos_m > ego_state.x_pos_m), None)
    s_state = next((state for state in reversed(mainline_states) if state.x_pos_m < ego_state.x_pos_m), None)
    if p_state is None or s_state is None:
        return None

    u_state = next((state for state in mainline_states if state.x_pos_m > p_state.x_pos_m), None)
    f_state = next((state for state in reversed(mainline_states) if state.x_pos_m < s_state.x_pos_m), None)

    sequence_ids = [p_state.veh_id, ego_state.veh_id, s_state.veh_id]
    if u_state is not None:
        sequence_ids.insert(0, u_state.veh_id)
    if f_state is not None:
        sequence_ids.append(f_state.veh_id)

    return TCG(
        snapshot_id=snapshot.snapshot_id,
        p_id=p_state.veh_id,
        m_id=ego_state.veh_id,
        s_id=s_state.veh_id,
        u_id=u_state.veh_id if u_state is not None else None,
        f_id=f_state.veh_id if f_state is not None else None,
        anchor_mode=snapshot.anchor_mode,
        sequence_relation=">".join(sequence_ids),
    )
