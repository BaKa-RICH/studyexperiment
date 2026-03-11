from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ramp.experiments.summarize_metrics import (
    aggregate_groups,
    build_scenario_summary,
    collect_run_records,
)


def _write_run(
    *,
    base_dir: Path,
    rel_dir: str,
    scenario: str,
    policy: str,
    seed: int,
    policy_variant: str | None,
    delay_s: float,
    throughput: float,
    ttc_any_min_s: float,
    ttc_any_lt_1_5s_ratio: float,
) -> Path:
    run_dir = base_dir / rel_dir
    run_dir.mkdir(parents=True, exist_ok=True)

    config = {
        'scenario': scenario,
        'policy': policy,
        'seed': seed,
        'policy_variant': policy_variant if policy_variant is not None else policy,
    }
    metrics = {
        'policy_name': policy,
        'policy_variant': policy_variant,
        'avg_delay_at_merge_s': delay_s,
        'throughput_veh_per_h': throughput,
        'ttc_any_min_s': ttc_any_min_s,
        'ttc_any_lt_1_5s_ratio': ttc_any_lt_1_5s_ratio,
    }

    (run_dir / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    (run_dir / 'metrics.json').write_text(json.dumps(metrics), encoding='utf-8')
    return run_dir


def test_collect_and_aggregate_groups(tmp_path: Path) -> None:
    temp_root = tmp_path / 'summary_metrics_collect'
    temp_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        base_dir=temp_root,
        rel_dir='r1',
        scenario='scene_a',
        policy='hierarchical',
        seed=1,
        policy_variant='proposed_full',
        delay_s=2.0,
        throughput=5000.0,
        ttc_any_min_s=1.2,
        ttc_any_lt_1_5s_ratio=0.10,
    )
    _write_run(
        base_dir=temp_root,
        rel_dir='r2',
        scenario='scene_a',
        policy='hierarchical',
        seed=2,
        policy_variant='proposed_full',
        delay_s=1.0,
        throughput=5200.0,
        ttc_any_min_s=1.8,
        ttc_any_lt_1_5s_ratio=0.05,
    )
    _write_run(
        base_dir=temp_root,
        rel_dir='r3',
        scenario='scene_a',
        policy='no_control',
        seed=1,
        policy_variant='no_control',
        delay_s=0.7,
        throughput=5300.0,
        ttc_any_min_s=0.8,
        ttc_any_lt_1_5s_ratio=0.20,
    )

    records = collect_run_records(input_dirs=[temp_root])
    rows = aggregate_groups(records=records)
    assert len(rows) == 2

    proposed_row = next(row for row in rows if row['policy_key'] == 'proposed_full')
    assert proposed_row['run_count'] == 2
    assert proposed_row['median_delay_s'] == pytest.approx(1.5)
    assert proposed_row['median_throughput_veh_per_h'] == pytest.approx(5100.0)
    assert proposed_row['median_ttc_any_min_s'] == pytest.approx(1.5)

    summary = build_scenario_summary(group_rows=rows)
    assert len(summary) == 1
    assert summary[0]['best_safety_policy'] == 'proposed_full'
    assert summary[0]['best_efficiency_policy'] == 'no_control'
    assert summary[0]['best_capacity_policy'] == 'no_control'


def test_collect_records_policy_key_fallback(tmp_path: Path) -> None:
    temp_root = tmp_path / 'summary_metrics_policy_fallback'
    temp_root.mkdir(parents=True, exist_ok=True)
    _write_run(
        base_dir=temp_root,
        rel_dir='r1',
        scenario='scene_b',
        policy='dp',
        seed=1,
        policy_variant=None,
        delay_s=1.1,
        throughput=6000.0,
        ttc_any_min_s=1.0,
        ttc_any_lt_1_5s_ratio=0.30,
    )
    records = collect_run_records(input_dirs=[temp_root])
    assert len(records) == 1
    assert records[0].policy_key == 'dp'


def test_collect_records_missing_ttc_field_raises(tmp_path: Path) -> None:
    temp_root = tmp_path / 'summary_metrics_missing_field'
    temp_root.mkdir(parents=True, exist_ok=True)
    run_dir = temp_root / 'broken'
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'config.json').write_text(
        json.dumps({'scenario': 'scene_c', 'policy': 'fifo', 'seed': 1}),
        encoding='utf-8',
    )
    (run_dir / 'metrics.json').write_text(
        json.dumps({'policy_name': 'fifo', 'avg_delay_at_merge_s': 2.0}),
        encoding='utf-8',
    )

    with pytest.raises(ValueError):
        collect_run_records(input_dirs=[temp_root])
