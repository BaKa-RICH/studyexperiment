from __future__ import annotations

from dataclasses import dataclass
from math import ceil

TTC_CALC_VERSION = 'v1'
TTC_SCOPE = 'longitudinal+merge_conflict'
TTC_THRESHOLD_WARNING_S = 3.0
TTC_THRESHOLD_CRITICAL_S = 1.5
DEFAULT_VEHICLE_LENGTH_M = 5.0

_MIN_APPROACH_SPEED_MPS = 0.1
_P05_Q = 0.05


ObservationState = dict[str, dict[str, float | str]]


@dataclass(slots=True, frozen=True)
class TTCStats:
    min_s: float | None
    p05_s: float | None
    sample_count: int
    sample_exposure_s: float
    lt_3_0s_count: int
    lt_1_5s_count: int
    lt_3_0s_ratio: float | None
    lt_1_5s_ratio: float | None


@dataclass(slots=True, frozen=True)
class _MergeCandidate:
    d_to_merge_m: float
    speed_mps: float
    length_m: float


def collect_ttc_samples(ttc_observation_state: ObservationState) -> tuple[list[float], list[float]]:
    """Collect per-step TTC samples under the v1 metric definition."""
    longitudinal = _collect_longitudinal_samples(ttc_observation_state=ttc_observation_state)
    merge_conflict = _collect_merge_conflict_samples(ttc_observation_state=ttc_observation_state)
    return longitudinal, merge_conflict


def build_ttc_metrics(
    *,
    longitudinal_samples: list[float],
    merge_conflict_samples: list[float],
    step_length_s: float,
) -> dict[str, float | int | str | None]:
    """Build stable metric fields for metrics.json."""
    long_stats = summarize_ttc_samples(samples=longitudinal_samples, step_length_s=step_length_s)
    merge_stats = summarize_ttc_samples(samples=merge_conflict_samples, step_length_s=step_length_s)
    any_stats = summarize_ttc_samples(
        samples=longitudinal_samples + merge_conflict_samples,
        step_length_s=step_length_s,
    )

    metrics: dict[str, float | int | str | None] = {
        'ttc_calc_version': TTC_CALC_VERSION,
        'ttc_scope': TTC_SCOPE,
    }
    metrics.update(_stats_to_metric_fields(prefix='ttc_longitudinal', stats=long_stats))
    metrics.update(_stats_to_metric_fields(prefix='ttc_merge_conflict', stats=merge_stats))
    metrics.update(_stats_to_metric_fields(prefix='ttc_any', stats=any_stats))
    return metrics


def summarize_ttc_samples(*, samples: list[float], step_length_s: float) -> TTCStats:
    if step_length_s <= 0:
        raise ValueError('step_length_s must be > 0')

    sample_count = len(samples)
    if sample_count == 0:
        return TTCStats(
            min_s=None,
            p05_s=None,
            sample_count=0,
            sample_exposure_s=0.0,
            lt_3_0s_count=0,
            lt_1_5s_count=0,
            lt_3_0s_ratio=None,
            lt_1_5s_ratio=None,
        )

    sorted_samples = sorted(samples)
    min_s = sorted_samples[0]
    p05_s = _nearest_rank_percentile(sorted_samples=sorted_samples, q=_P05_Q)
    lt_3_0s_count = sum(1 for value in sorted_samples if value < TTC_THRESHOLD_WARNING_S)
    lt_1_5s_count = sum(1 for value in sorted_samples if value < TTC_THRESHOLD_CRITICAL_S)
    sample_exposure_s = float(sample_count) * step_length_s

    return TTCStats(
        min_s=min_s,
        p05_s=p05_s,
        sample_count=sample_count,
        sample_exposure_s=sample_exposure_s,
        lt_3_0s_count=lt_3_0s_count,
        lt_1_5s_count=lt_1_5s_count,
        lt_3_0s_ratio=lt_3_0s_count / sample_count,
        lt_1_5s_ratio=lt_1_5s_count / sample_count,
    )


def _collect_longitudinal_samples(*, ttc_observation_state: ObservationState) -> list[float]:
    lane_groups: dict[str, list[tuple[float, float, float]]] = {}
    for vehicle_state in ttc_observation_state.values():
        lane_id = str(vehicle_state['lane_id'])
        lane_pos_m = float(vehicle_state['lane_pos'])
        speed_mps = float(vehicle_state['speed'])
        length_m = float(vehicle_state.get('length', DEFAULT_VEHICLE_LENGTH_M))
        lane_groups.setdefault(lane_id, []).append((lane_pos_m, speed_mps, length_m))

    samples: list[float] = []
    for vehicles in lane_groups.values():
        vehicles.sort(key=lambda item: item[0])
        for index in range(len(vehicles) - 1):
            follow_pos_m, follow_speed_mps, _ = vehicles[index]
            lead_pos_m, lead_speed_mps, lead_length_m = vehicles[index + 1]
            gap_m = lead_pos_m - follow_pos_m - lead_length_m
            if gap_m <= 0:
                samples.append(0.0)
                continue

            closing_speed_mps = follow_speed_mps - lead_speed_mps
            if closing_speed_mps <= 0:
                continue

            samples.append(gap_m / closing_speed_mps)
    return samples


def _collect_merge_conflict_samples(*, ttc_observation_state: ObservationState) -> list[float]:
    main_candidates: list[_MergeCandidate] = []
    ramp_candidates: list[_MergeCandidate] = []
    for vehicle_state in ttc_observation_state.values():
        stream = str(vehicle_state['stream'])
        edge_id = str(vehicle_state['edge_id'])
        lane_id = str(vehicle_state['lane_id'])
        lane_index = _lane_index_from_lane_id(lane_id=lane_id)
        if not _is_conflict_lane(stream=stream, edge_id=edge_id, lane_index=lane_index):
            continue

        speed_mps = float(vehicle_state['speed'])
        d_to_merge_m = float(vehicle_state['d_to_merge'])
        if speed_mps <= 0 or d_to_merge_m <= 0:
            continue

        candidate = _MergeCandidate(
            d_to_merge_m=d_to_merge_m,
            speed_mps=speed_mps,
            length_m=float(vehicle_state.get('length', DEFAULT_VEHICLE_LENGTH_M)),
        )
        if stream == 'main':
            main_candidates.append(candidate)
        elif stream == 'ramp':
            ramp_candidates.append(candidate)

    samples: list[float] = []
    for ramp_vehicle in ramp_candidates:
        best_ttc_s: float | None = None
        for main_vehicle in main_candidates:
            ttc_s = _pair_merge_ttc_s(main_vehicle=main_vehicle, ramp_vehicle=ramp_vehicle)
            if ttc_s is None:
                continue
            if best_ttc_s is None or ttc_s < best_ttc_s:
                best_ttc_s = ttc_s
        if best_ttc_s is not None:
            samples.append(best_ttc_s)
    return samples


def _pair_merge_ttc_s(
    *, main_vehicle: _MergeCandidate, ramp_vehicle: _MergeCandidate
) -> float | None:
    main_speed_mps = max(main_vehicle.speed_mps, _MIN_APPROACH_SPEED_MPS)
    ramp_speed_mps = max(ramp_vehicle.speed_mps, _MIN_APPROACH_SPEED_MPS)

    main_enter_s = main_vehicle.d_to_merge_m / main_speed_mps
    ramp_enter_s = ramp_vehicle.d_to_merge_m / ramp_speed_mps
    main_exit_s = main_enter_s + main_vehicle.length_m / main_speed_mps
    ramp_exit_s = ramp_enter_s + ramp_vehicle.length_m / ramp_speed_mps

    overlap_start_s = max(main_enter_s, ramp_enter_s)
    overlap_end_s = min(main_exit_s, ramp_exit_s)
    if overlap_start_s > overlap_end_s:
        return None

    return max(overlap_start_s, 0.0)


def _stats_to_metric_fields(
    *, prefix: str, stats: TTCStats
) -> dict[str, float | int | None]:
    return {
        f'{prefix}_min_s': stats.min_s,
        f'{prefix}_p05_s': stats.p05_s,
        f'{prefix}_sample_count': stats.sample_count,
        f'{prefix}_sample_exposure_s': stats.sample_exposure_s,
        f'{prefix}_lt_3_0s_count': stats.lt_3_0s_count,
        f'{prefix}_lt_1_5s_count': stats.lt_1_5s_count,
        f'{prefix}_lt_3_0s_ratio': stats.lt_3_0s_ratio,
        f'{prefix}_lt_1_5s_ratio': stats.lt_1_5s_ratio,
    }


def _nearest_rank_percentile(*, sorted_samples: list[float], q: float) -> float:
    if not sorted_samples:
        raise ValueError('sorted_samples must not be empty')
    if q <= 0:
        return sorted_samples[0]
    if q >= 1:
        return sorted_samples[-1]

    rank = int(ceil(q * len(sorted_samples)))
    rank = max(1, min(rank, len(sorted_samples)))
    return sorted_samples[rank - 1]


def _lane_index_from_lane_id(*, lane_id: str) -> int:
    if '_' not in lane_id:
        return -1
    suffix = lane_id.rsplit('_', 1)[1]
    if not suffix.isdigit():
        return -1
    return int(suffix)


def _is_conflict_lane(*, stream: str, edge_id: str, lane_index: int) -> bool:
    if stream == 'ramp':
        return edge_id in {'ramp_h6', 'main_h3'} and lane_index in {0, 1}
    if stream == 'main':
        return (edge_id == 'main_h2' and lane_index == 0) or (
            edge_id == 'main_h3' and lane_index == 1
        )
    return False
