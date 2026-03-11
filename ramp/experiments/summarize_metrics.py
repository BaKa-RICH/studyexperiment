from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

REQUIRED_BASE_FIELDS = (
    'avg_delay_at_merge_s',
    'throughput_veh_per_h',
    'ttc_any_min_s',
    'ttc_any_lt_1_5s_ratio',
)


@dataclass(slots=True, frozen=True)
class RunRecord:
    scenario: str
    policy_key: str
    seed: int | None
    metrics: dict[str, float | int | str | None]
    config: dict[str, float | int | str | None]
    metrics_path: Path


def collect_run_records(*, input_dirs: list[Path]) -> list[RunRecord]:
    records: list[RunRecord] = []
    for input_dir in input_dirs:
        if not input_dir.exists() or not input_dir.is_dir():
            raise FileNotFoundError(f'Input directory not found: {input_dir}')

        for metrics_path in sorted(input_dir.rglob('metrics.json')):
            config_path = metrics_path.with_name('config.json')
            if not config_path.exists():
                raise FileNotFoundError(f'config.json not found for {metrics_path}')

            metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
            config = json.loads(config_path.read_text(encoding='utf-8'))
            _validate_metrics(metrics=metrics, metrics_path=metrics_path)

            scenario = str(config.get('scenario', '')).strip()
            if not scenario:
                raise ValueError(f'Missing scenario in config: {config_path}')

            policy_key = _resolve_policy_key(
                metrics=metrics, config=config, fallback_path=metrics_path
            )
            seed_value = config.get('seed')
            seed = int(seed_value) if seed_value is not None else None
            records.append(
                RunRecord(
                    scenario=scenario,
                    policy_key=policy_key,
                    seed=seed,
                    metrics=metrics,
                    config=config,
                    metrics_path=metrics_path,
                )
            )

    if not records:
        raise ValueError('No metrics.json found in input directories')
    return records


def aggregate_groups(*, records: list[RunRecord]) -> list[dict[str, float | int | str | list[int]]]:
    grouped: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        grouped.setdefault((record.scenario, record.policy_key), []).append(record)

    rows: list[dict[str, float | int | str | list[int]]] = []
    for (scenario, policy_key), group_records in sorted(grouped.items()):
        seeds = sorted(
            record.seed for record in group_records if record.seed is not None
        )
        row: dict[str, float | int | str | list[int]] = {
            'scenario': scenario,
            'policy_key': policy_key,
            'run_count': len(group_records),
            'seeds': seeds,
            'median_delay_s': _median_metric(group_records, 'avg_delay_at_merge_s'),
            'median_throughput_veh_per_h': _median_metric(
                group_records, 'throughput_veh_per_h'
            ),
            'median_ttc_longitudinal_min_s': _median_metric(
                group_records, 'ttc_longitudinal_min_s'
            ),
            'median_ttc_merge_conflict_min_s': _median_metric(
                group_records, 'ttc_merge_conflict_min_s'
            ),
            'median_ttc_any_min_s': _median_metric(group_records, 'ttc_any_min_s'),
            'median_ttc_any_lt_3_0s_ratio': _median_metric(
                group_records, 'ttc_any_lt_3_0s_ratio'
            ),
            'median_ttc_any_lt_1_5s_ratio': _median_metric(
                group_records, 'ttc_any_lt_1_5s_ratio'
            ),
        }
        rows.append(row)
    return rows


def build_scenario_summary(
    *, group_rows: list[dict[str, float | int | str | list[int]]]
) -> list[dict[str, str]]:
    scenario_rows: dict[str, list[dict[str, float | int | str | list[int]]]] = {}
    for row in group_rows:
        scenario = str(row['scenario'])
        scenario_rows.setdefault(scenario, []).append(row)

    summary_rows: list[dict[str, str]] = []
    for scenario in sorted(scenario_rows):
        rows = scenario_rows[scenario]
        safety_best = _select_best_safety(rows)
        efficiency_best = _select_best_efficiency(rows)
        capacity_best = _select_best_capacity(rows)
        summary_rows.append(
            {
                'scenario': scenario,
                'best_safety_policy': str(safety_best['policy_key']),
                'best_efficiency_policy': str(efficiency_best['policy_key']),
                'best_capacity_policy': str(capacity_best['policy_key']),
            }
        )
    return summary_rows


def build_markdown_report(
    *,
    group_rows: list[dict[str, float | int | str | list[int]]],
    scenario_summary: list[dict[str, str]],
) -> str:
    lines: list[str] = []
    lines.append('# TTC + Delay + Throughput 联合重评')
    lines.append('')

    scenario_index: dict[str, list[dict[str, float | int | str | list[int]]]] = {}
    for row in group_rows:
        scenario_index.setdefault(str(row['scenario']), []).append(row)

    for scenario in sorted(scenario_index):
        lines.append(f'## 场景: {scenario}')
        lines.append('')
        lines.append(
            '| policy | runs | median_delay_s | median_throughput_veh_per_h | '
            'median_ttc_any_min_s | median_ttc_any_lt_1_5s_ratio |'
        )
        lines.append('|---|---:|---:|---:|---:|---:|')
        for row in sorted(scenario_index[scenario], key=lambda item: str(item['policy_key'])):
            lines.append(
                '| '
                f"{row['policy_key']} | {row['run_count']} | "
                f"{_fmt_float(row['median_delay_s'])} | "
                f"{_fmt_float(row['median_throughput_veh_per_h'])} | "
                f"{_fmt_float(row['median_ttc_any_min_s'])} | "
                f"{_fmt_float(row['median_ttc_any_lt_1_5s_ratio'])} |"
            )
        summary = next(item for item in scenario_summary if item['scenario'] == scenario)
        lines.append('')
        lines.append(
            '- 联合结论：'
            f"安全最优 `{summary['best_safety_policy']}`，"
            f"效率最优 `{summary['best_efficiency_policy']}`，"
            f"通行能力最优 `{summary['best_capacity_policy']}`。"
        )
        lines.append('')
    return '\n'.join(lines)


def _validate_metrics(*, metrics: dict[str, float | int | str | None], metrics_path: Path) -> None:
    for key in REQUIRED_BASE_FIELDS:
        if key not in metrics:
            raise ValueError(f'Missing `{key}` in {metrics_path}')


def _resolve_policy_key(
    *,
    metrics: dict[str, float | int | str | None],
    config: dict[str, float | int | str | None],
    fallback_path: Path,
) -> str:
    for key in ('policy_variant', 'policy_name', 'policy'):
        value = metrics.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback_path.parent.name


def _median_metric(records: list[RunRecord], metric_key: str) -> float | None:
    values: list[float] = []
    for record in records:
        value = record.metrics.get(metric_key)
        if value is None:
            continue
        values.append(float(value))
    if not values:
        return None
    return float(statistics.median(values))


def _select_best_safety(
    rows: list[dict[str, float | int | str | list[int]]]
) -> dict[str, float | int | str | list[int]]:
    def _safety_key(row: dict[str, float | int | str | list[int]]) -> tuple[float, float]:
        min_ttc = row['median_ttc_any_min_s']
        risk_ratio = row['median_ttc_any_lt_1_5s_ratio']
        min_ttc_value = float(min_ttc) if isinstance(min_ttc, (float, int)) else float('-inf')
        risk_ratio_value = (
            float(risk_ratio) if isinstance(risk_ratio, (float, int)) else float('inf')
        )
        return (min_ttc_value, -risk_ratio_value)

    return max(rows, key=_safety_key)


def _select_best_efficiency(
    rows: list[dict[str, float | int | str | list[int]]]
) -> dict[str, float | int | str | list[int]]:
    def _efficiency_key(row: dict[str, float | int | str | list[int]]) -> float:
        delay = row['median_delay_s']
        if not isinstance(delay, (float, int)):
            return float('inf')
        return float(delay)

    return min(rows, key=_efficiency_key)


def _select_best_capacity(
    rows: list[dict[str, float | int | str | list[int]]]
) -> dict[str, float | int | str | list[int]]:
    def _capacity_key(row: dict[str, float | int | str | list[int]]) -> float:
        throughput = row['median_throughput_veh_per_h']
        if not isinstance(throughput, (float, int)):
            return float('-inf')
        return float(throughput)

    return max(rows, key=_capacity_key)


def _fmt_float(value: object) -> str:
    if value is None:
        return 'null'
    if isinstance(value, float):
        return f'{value:.4f}'
    if isinstance(value, int):
        return str(value)
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Aggregate TTC + delay + throughput metrics across experiment outputs.'
    )
    parser.add_argument(
        '--input-dir',
        action='append',
        required=True,
        help='Directory to recursively scan for metrics.json (can be repeated).',
    )
    parser.add_argument('--out-json', default=None, help='Optional JSON output path.')
    parser.add_argument('--out-md', default=None, help='Optional Markdown output path.')
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Do not print markdown report to stdout.',
    )
    args = parser.parse_args()

    input_dirs = [Path(path).resolve() for path in args.input_dir]
    records = collect_run_records(input_dirs=input_dirs)
    group_rows = aggregate_groups(records=records)
    scenario_summary = build_scenario_summary(group_rows=group_rows)
    markdown_report = build_markdown_report(
        group_rows=group_rows,
        scenario_summary=scenario_summary,
    )

    payload = {
        'schema_version': 'ttc_reeval_v1',
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        'input_dirs': [str(path) for path in input_dirs],
        'groups': group_rows,
        'scenario_summary': scenario_summary,
    }

    if args.out_json:
        out_json = Path(args.out_json).resolve()
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    if args.out_md:
        out_md = Path(args.out_md).resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(markdown_report + '\n', encoding='utf-8')
    if not args.quiet:
        print(markdown_report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
