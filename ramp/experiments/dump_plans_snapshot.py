from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _format_row(row: dict[str, str]) -> str:
    return (
        f"{int(row['order_index']):>3}  "
        f"{row['veh_id']:<20}  "
        f"{row['stream']:<5}  "
        f"{float(row['target_cross_time']):>12.3f}  "
        f"{float(row['v_des']):>8.3f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Dump one plans.csv snapshot by time.')
    parser.add_argument('--plans', required=True, help='Path to plans.csv')
    parser.add_argument('--time', required=True, type=float, help='Snapshot time to print')
    parser.add_argument('--epsilon-s', type=float, default=1e-6, help='Time match tolerance')
    args = parser.parse_args()

    plans_path = Path(args.plans)
    if not plans_path.exists():
        raise FileNotFoundError(f'plans.csv not found: {plans_path}')

    matches: list[dict[str, str]] = []
    times_seen: set[float] = set()
    with plans_path.open('r', newline='', encoding='utf-8') as fp:
        for row in csv.DictReader(fp):
            time_s = float(row['time'])
            times_seen.add(time_s)
            if abs(time_s - args.time) <= args.epsilon_s:
                matches.append(row)

    if not matches:
        if not times_seen:
            print('No rows in plans.csv.')
            return 0
        nearest = min(times_seen, key=lambda t: abs(t - args.time))
        print(
            f'No snapshot at time={args.time:.6f} (epsilon={args.epsilon_s}). '
            f'Nearest time is {nearest:.6f}.'
        )
        return 1

    matches.sort(key=lambda row: int(row['order_index']))
    print(f'time={args.time:.3f} rows={len(matches)} plans={plans_path}')
    print('idx  veh_id                stream  target_time_s  v_des')
    for row in matches:
        print(_format_row(row))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

