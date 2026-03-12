#!/usr/bin/env python3
"""Small-matrix Pain screening for heterogeneous HDV worlds.

Runs a 3×3 experiment grid (worlds × seeds) and computes PainScore
for each H1 world relative to H0 (baseline).

Architecture note (Sonnet REVIEW):
    Each matrix cell runs as an **isolated subprocess** because SUMO's
    traci connection is not re-entrant within a single process.

Usage:
    python -m ramp.tools.run_pain_matrix --scenario ramp__mlane_v2_mixed
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ramp.experiments.pain_score import (
    PAIN_INDICATORS,
    compute_pain_score_from_metrics,
    extract_pain_indicators,
)

WORLDS: dict[str, dict[str, float]] = {
    'H0_normal': {'hdv_normal': 1.0},
    'H1a_distracted': {'hdv_normal': 0.5, 'hdv_distracted': 0.5},
    'H1b_aggressive': {'hdv_normal': 0.5, 'hdv_aggressive': 0.5},
    'H1c_hesitant': {'hdv_hesitant': 1.0},
    'H1d_stress_mix': {'hdv_distracted': 0.5, 'hdv_hesitant': 0.5},
}

DEFAULT_SEEDS: list[int] = [1, 2, 3]

DEFAULT_PARAMS: dict[str, Any] = {
    'scenario': 'ramp__mlane_v2_mixed',
    'policy': 'hierarchical',
    'duration_s': 300.0,
    'step_length': 0.1,
    'control_zone_length_m': 300.0,
    'merge_edge': 'main_h3',
    'main_vmax_mps': 25.0,
    'ramp_vmax_mps': 25.0,
    'fifo_gap_s': 2.0,
    'delta_1_s': 1.5,
    'delta_2_s': 2.0,
    'dp_replan_interval_s': 1.0,
    'cav_ratio': 0.5,
    'generate_rou': True,
    'main_vph': 1500,
    'ramp_vph': 600,
    'rou_duration': 300,
    'arrival_mode': 'uniform',
    'use_profiles': True,
}


def _build_cmd(
    *,
    world_name: str,
    weights: dict[str, float],
    seed: int,
    out_dir: Path,
    params: dict[str, Any],
) -> list[str]:
    """Build the CLI command list for a single matrix cell."""
    cmd = [
        sys.executable, '-m', 'ramp.experiments.run',
        '--scenario', str(params['scenario']),
        '--policy', str(params['policy']),
        '--duration-s', str(params['duration_s']),
        '--step-length', str(params['step_length']),
        '--seed', str(seed),
        '--out-dir', str(out_dir),
        '--control-zone-length-m', str(params['control_zone_length_m']),
        '--merge-edge', str(params['merge_edge']),
        '--main-vmax-mps', str(params['main_vmax_mps']),
        '--ramp-vmax-mps', str(params['ramp_vmax_mps']),
        '--fifo-gap-s', str(params['fifo_gap_s']),
        '--delta-1-s', str(params['delta_1_s']),
        '--delta-2-s', str(params['delta_2_s']),
        '--dp-replan-interval-s', str(params['dp_replan_interval_s']),
        '--cav-ratio', str(params['cav_ratio']),
        '--main-vph', str(params['main_vph']),
        '--ramp-vph', str(params['ramp_vph']),
        '--rou-duration', str(params['rou_duration']),
        '--arrival-mode', str(params['arrival_mode']),
    ]
    if params.get('generate_rou'):
        cmd.append('--generate-rou')
    if params.get('use_profiles'):
        cmd.append('--use-profiles')
    weight_str = ','.join(f'{k}:{v}' for k, v in weights.items())
    cmd.extend(['--hdv-profile-weights', weight_str])
    return cmd


def _load_metrics(out_dir: Path) -> dict[str, Any] | None:
    metrics_path = out_dir / 'metrics.json'
    if not metrics_path.exists():
        return None
    return json.loads(metrics_path.read_text(encoding='utf-8'))


def run_matrix(
    *,
    worlds: dict[str, dict[str, float]] | None = None,
    seeds: list[int] | None = None,
    params: dict[str, Any] | None = None,
    base_out_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the full pain matrix and return summary results."""
    w = worlds or WORLDS
    s = seeds or DEFAULT_SEEDS
    p = {**DEFAULT_PARAMS, **(params or {})}
    base = base_out_dir or (Path(_REPO_ROOT) / 'output' / 'pain_matrix')
    base.mkdir(parents=True, exist_ok=True)

    cell_results: list[dict[str, Any]] = []
    all_metrics: dict[str, list[dict[str, Any]]] = {}

    for world_name, weights in w.items():
        all_metrics[world_name] = []
        for seed in s:
            cell_dir = base / world_name / f'seed_{seed}'
            cell_dir.mkdir(parents=True, exist_ok=True)

            cmd = _build_cmd(
                world_name=world_name,
                weights=weights,
                seed=seed,
                out_dir=cell_dir,
                params=p,
            )
            print(f'[MATRIX] Running {world_name} seed={seed} ...')
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(_REPO_ROOT), timeout=600,
            )

            metrics = _load_metrics(cell_dir)
            success = result.returncode == 0 and metrics is not None

            cell_entry = {
                'world': world_name,
                'seed': seed,
                'returncode': result.returncode,
                'success': success,
                'out_dir': str(cell_dir),
            }
            if not success:
                cell_entry['stderr_tail'] = (result.stderr or '')[-500:]
            cell_results.append(cell_entry)

            if metrics is not None:
                all_metrics[world_name].append(metrics)

    h0_name = 'H0_normal'
    h0_metrics_list = all_metrics.get(h0_name, [])

    pain_summary: list[dict[str, Any]] = []
    if h0_metrics_list:
        h0_avg = _average_indicators(h0_metrics_list)
        for world_name, metrics_list in all_metrics.items():
            if world_name == h0_name or not metrics_list:
                continue
            h1_avg = _average_indicators(metrics_list)
            from ramp.experiments.pain_score import compute_pain_score
            score = compute_pain_score(h1_avg, h0_avg)
            pain_summary.append({
                'world': world_name,
                'pain_score': round(score, 4),
                'passes_gate3': score >= 0.25,
                'h0_indicators': {k: round(v, 6) for k, v in h0_avg.items()},
                'h1_indicators': {k: round(v, 6) for k, v in h1_avg.items()},
            })

    summary = {
        'matrix_config': {
            'worlds': list(w.keys()),
            'seeds': s,
            'params': p,
        },
        'cell_results': cell_results,
        'pain_summary': pain_summary,
        'gate1_all_runnable': all(c['success'] for c in cell_results),
        'gate3_any_passes': any(ps['passes_gate3'] for ps in pain_summary),
    }

    summary_path = base / 'pain_matrix_summary.json'
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding='utf-8')
    print(f'[MATRIX] Summary written to {summary_path}')

    _write_csv_summary(base / 'pain_matrix_summary.csv', cell_results, pain_summary)

    return summary


def _average_indicators(metrics_list: list[dict[str, Any]]) -> dict[str, float]:
    """Average Pain indicators across multiple seed runs."""
    if not metrics_list:
        return {name: 0.0 for name in PAIN_INDICATORS}
    indicator_lists: dict[str, list[float]] = {name: [] for name in PAIN_INDICATORS}
    for m in metrics_list:
        indicators = extract_pain_indicators(m)
        for name in PAIN_INDICATORS:
            indicator_lists[name].append(indicators[name])
    return {
        name: sum(vals) / len(vals) if vals else 0.0
        for name, vals in indicator_lists.items()
    }


def _write_csv_summary(
    path: Path,
    cell_results: list[dict[str, Any]],
    pain_summary: list[dict[str, Any]],
) -> None:
    fields = ['world', 'seed', 'success', 'returncode']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in cell_results:
            writer.writerow(row)
    print(f'[MATRIX] CSV written to {path}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run HDV Pain screening matrix')
    parser.add_argument('--scenario', default='ramp__mlane_v2_mixed')
    parser.add_argument('--policy', default='hierarchical')
    parser.add_argument('--seeds', type=str, default='1,2,3',
                        help='Comma-separated seeds')
    parser.add_argument('--out-dir', type=str, default=None)
    parser.add_argument('--cav-ratio', type=float, default=0.5)
    parser.add_argument('--main-vph', type=int, default=1500)
    parser.add_argument('--ramp-vph', type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = [int(s.strip()) for s in args.seeds.split(',')]
    params = {**DEFAULT_PARAMS}
    params['scenario'] = args.scenario
    params['policy'] = args.policy
    params['cav_ratio'] = args.cav_ratio
    params['main_vph'] = args.main_vph
    params['ramp_vph'] = args.ramp_vph

    base_out = Path(args.out_dir) if args.out_dir else None
    summary = run_matrix(seeds=seeds, params=params, base_out_dir=base_out)

    print('\n' + '=' * 60)
    print('PAIN MATRIX RESULTS')
    print('=' * 60)
    print(f"Gate 1 (all runnable): {'PASS' if summary['gate1_all_runnable'] else 'FAIL'}")
    print(f"Gate 3 (any PainScore >= 25%): {'PASS' if summary['gate3_any_passes'] else 'FAIL'}")
    for ps in summary.get('pain_summary', []):
        marker = '***' if ps['passes_gate3'] else ''
        print(f"  {ps['world']}: PainScore = {ps['pain_score']:.2%} {marker}")
    print('=' * 60)


if __name__ == '__main__':
    main()
