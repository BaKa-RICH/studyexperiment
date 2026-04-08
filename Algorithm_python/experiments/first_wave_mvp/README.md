# 第一波 MVP 实验入口

## 目标

本目录承担两层职责：

- `T5`：定义实验入口、默认参数、结果组织方式与默认输出路径
- `T7`：将实验入口接成最小纯 Python 数值执行器，真实写出 `outputs/.../summary.json`

本目录始终不负责最终门禁裁决；最终 pass/fail 仍由 `T6` 的 `regression_gate.py` 负责。

## 实验列表

| 实验 ID | 目的 | 默认输出路径 |
|---------|------|--------------|
| `light_load_correctness` | 验证低竞争场景下物理语义、候选生成、gate 与执行闭环的正确性 | `experiments/first_wave_mvp/outputs/light_load_correctness/summary.json` |
| `medium_high_load_competition` | 比较 `FIFO + fixed anchor` 与 `FIFO + flexible anchor` 的竞争表现 | `experiments/first_wave_mvp/outputs/medium_high_load_competition/summary.json` |
| `cav_penetration_and_scope_ablation` | 验证渗透率和协同范围变化时的平滑退化行为 | `experiments/first_wave_mvp/outputs/cav_penetration_and_scope_ablation/summary.json` |

## 运行方式

当前实验入口会真实运行最小纯 Python 数值执行器，并写出 `summary.json`：

```bash
python experiments/first_wave_mvp/light_load_correctness.py
python experiments/first_wave_mvp/medium_high_load_competition.py
python experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py
```

## 结果结构

- 单 seed 结果由 `PerSeedResult` 表示。
- 聚合为单次汇总时，使用 `aggregate_to_summary(per_seed_results)` 生成 `ExperimentResultSummary`。
- `mean / worst-seed / p95` 等统计视图由 `aggregate_stats_view(per_seed_results)` 单独生成，供 `T6` 消费。
- 所有 JSON 键名统一使用 `snake_case`。

## 明确不做

- 不在本目录中引入 SUMO / CARLA / TraCI。
- 不在本目录中做任何最终通过/失败门禁判定。
- 不引入 `simple DP`、两层分层算法、多 partition 或第二波实验入口。
