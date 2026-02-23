from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def _first_time_by_vehicle(rows: list[dict[str, str]], event_name: str) -> dict[str, float]:
    first: dict[str, float] = {}
    for r in rows:
        if r.get("event") != event_name:
            continue
        veh_id = r.get("veh_id", "")
        if not veh_id:
            continue
        t = float(r["time"])
        if veh_id not in first:
            first[veh_id] = t
    return first


def _cross_events(rows: list[dict[str, str]]) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    for r in rows:
        if r.get("event") == "cross_merge":
            events.append((float(r["time"]), r.get("veh_id", "")))
    events.sort(key=lambda x: (x[0], x[1]))
    return events


def _plan_snapshots(
    rows: list[dict[str, str]],
) -> list[tuple[float, list[str], dict[str, dict[str, str]]]]:
    by_time: dict[float, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_time[float(r["time"])].append(r)

    snapshots: list[tuple[float, list[str], dict[str, dict[str, str]]]] = []
    for t in sorted(by_time):
        group = sorted(by_time[t], key=lambda x: int(x["order_index"]))
        order = [r["veh_id"] for r in group]
        rows_by_veh = {r["veh_id"]: r for r in group}
        snapshots.append((t, order, rows_by_veh))
    return snapshots


def _command_by_time_vehicle(rows: list[dict[str, str]]) -> dict[tuple[float, str], dict[str, str]]:
    out: dict[tuple[float, str], dict[str, str]] = {}
    for r in rows:
        if r.get("release_flag") == "1":
            continue
        out[(float(r["time"]), r["veh_id"])] = r
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate mismatch report from plans/events/commands without touching SUMO."
    )
    parser.add_argument("--dir", required=True, help="Output policy directory, e.g. output/.../dp")
    parser.add_argument("--out", required=True, help="Path to write mismatch_report.csv")
    parser.add_argument("--window-s", type=float, default=1.0, help="GUI time window suggestion")
    args = parser.parse_args()

    out_dir = Path(args.dir)
    plans_path = out_dir / "plans.csv"
    events_path = out_dir / "events.csv"
    commands_path = out_dir / "commands.csv"
    for p in (plans_path, events_path, commands_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing required file: {p}")

    plans_rows = _read_csv(plans_path)
    events_rows = _read_csv(events_path)
    commands_rows = _read_csv(commands_path)

    snapshots = _plan_snapshots(plans_rows)
    cross = _cross_events(events_rows)
    first_commit = _first_time_by_vehicle(events_rows, "commit_vehicle")
    cmd = _command_by_time_vehicle(commands_rows)

    mismatches: list[dict[str, str | float | int]] = []
    for cross_t, actual in cross:
        latest = None
        for snap in snapshots:
            if snap[0] >= cross_t - 1e-9:
                break
            latest = snap
        if latest is None:
            continue
        plan_t, order, rows_by_veh = latest
        if not order:
            continue
        head = order[0]
        if head == actual:
            continue

        actual_row = rows_by_veh.get(actual)
        head_row = rows_by_veh.get(head)

        actual_cmd = cmd.get((plan_t, actual))
        head_cmd = cmd.get((plan_t, head))

        def _get(row: dict[str, str] | None, key: str) -> str:
            return "" if row is None else row.get(key, "")

        mismatches.append(
            {
                "cross_t": cross_t,
                "plan_t": plan_t,
                "actual": actual,
                "planned_head": head,
                "queue_len": len(order),
                "actual_commit_t": first_commit.get(actual, ""),
                "head_commit_t": first_commit.get(head, ""),
                "actual_stream": _get(actual_row, "stream"),
                "head_stream": _get(head_row, "stream"),
                "actual_D_to_merge": _get(actual_row, "D_to_merge"),
                "head_D_to_merge": _get(head_row, "D_to_merge"),
                "actual_speed": _get(actual_row, "speed"),
                "head_speed": _get(head_row, "speed"),
                "actual_target_cross_time": _get(actual_row, "target_cross_time"),
                "head_target_cross_time": _get(head_row, "target_cross_time"),
                "actual_v_cmd": _get(actual_cmd, "v_cmd_mps"),
                "head_v_cmd": _get(head_cmd, "v_cmd_mps"),
                "gui_pause_t0": max(plan_t - float(args.window_s), 0.0),
                "gui_pause_t1": plan_t,
                "gui_pause_t2": cross_t,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "cross_t",
        "plan_t",
        "actual",
        "planned_head",
        "queue_len",
        "actual_commit_t",
        "head_commit_t",
        "actual_stream",
        "head_stream",
        "actual_D_to_merge",
        "head_D_to_merge",
        "actual_speed",
        "head_speed",
        "actual_target_cross_time",
        "head_target_cross_time",
        "actual_v_cmd",
        "head_v_cmd",
        "gui_pause_t0",
        "gui_pause_t1",
        "gui_pause_t2",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for row in mismatches:
            w.writerow(row)

    print(f"[dump_mismatch_report] cross_events={len(cross)} mismatches={len(mismatches)} out={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

