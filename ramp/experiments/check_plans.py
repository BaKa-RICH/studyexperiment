from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def check_plans(
    plans_path: Path,
    *,
    delta_1_s: float,
    delta_2_s: float,
    epsilon_s: float = 1e-9,
) -> dict[str, int | float | str]:
    with plans_path.open('r', newline='', encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        rows = list(reader)

    by_time: dict[float, list[dict[str, str]]] = defaultdict(list)
    parse_error_count = 0
    for row in rows:
        try:
            sim_time = float(row['time'])
        except (KeyError, TypeError, ValueError):
            parse_error_count += 1
            continue
        by_time[sim_time].append(row)

    snapshot_count = 0
    gap_bad_count = 0
    mono_bad_count = 0
    duplicate_order_index_count = 0

    for sim_time in sorted(by_time):
        snapshot_rows = by_time[sim_time]
        if not snapshot_rows:
            continue
        snapshot_count += 1
        order_index_set: set[int] = set()
        parsed_rows: list[tuple[int, str, float]] = []
        for row in snapshot_rows:
            try:
                order_index = int(row['order_index'])
                stream = str(row['stream'])
                target_cross_time = float(row['target_cross_time'])
            except (KeyError, TypeError, ValueError):
                parse_error_count += 1
                continue
            if order_index in order_index_set:
                duplicate_order_index_count += 1
            order_index_set.add(order_index)
            parsed_rows.append((order_index, stream, target_cross_time))

        parsed_rows.sort(key=lambda item: item[0])
        prev_stream: str | None = None
        prev_target: float | None = None
        for _order_index, stream, target in parsed_rows:
            if prev_target is not None:
                gap_s = target - prev_target
                required_gap_s = delta_1_s if stream == prev_stream else delta_2_s
                if gap_s + epsilon_s < required_gap_s:
                    gap_bad_count += 1
                if target + epsilon_s < prev_target:
                    mono_bad_count += 1
            prev_stream = stream
            prev_target = target

    return {
        'plans_file': str(plans_path),
        'row_count': len(rows),
        'snapshot_count': snapshot_count,
        'parse_error_count': parse_error_count,
        'duplicate_order_index_count': duplicate_order_index_count,
        'target_mono_bad': mono_bad_count,
        'gap_bad': gap_bad_count,
        'delta_1_s': delta_1_s,
        'delta_2_s': delta_2_s,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Check safety-gap constraints in plans.csv.')
    parser.add_argument('--plans', required=True, help='Path to plans.csv')
    parser.add_argument('--delta-1-s', type=float, default=1.5)
    parser.add_argument('--delta-2-s', type=float, default=2.0)
    parser.add_argument('--epsilon-s', type=float, default=1e-9)
    args = parser.parse_args()

    summary = check_plans(
        Path(args.plans),
        delta_1_s=args.delta_1_s,
        delta_2_s=args.delta_2_s,
        epsilon_s=args.epsilon_s,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
