<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T5: Metrics 与 Trace（Metrics, Trace, and Experiment Output Contract）

> 最后更新：`2026-04-08T18:45:00+08:00`

## 前置条件

- `T1_tcg_and_snapshot`、`T2_merge_target_planner`、`T3_tcg_quintic_and_certificate`、`T4_execution_and_state_machine` 已完成。
- 必读：`docs/design.md`（重点看 “验证策略”“A 层微场景”“状态机与 fail-safe”）。
- 必读：`docs/contracts.md`（重点看 `ExperimentResultSummary`、`RollingPlanSlice`、`SafetyCertificate`）。
- 必读：`docs/formulas.md`（重点看 `e_pm^{virt}`、`e_ms^{virt}`、coordination slice 推进条件和证书字段）。
- 必读：`docs/features/active_gap_v1/design.md`。

## 目标

建立当前主算法的诊断层：重新定义 `planned/actual`，固定 trace schema、summary schema 和 slice 类型统计，使 A 层能够直接回答“算法是否真的在主动造 gap、为什么这一 tick 没 merge 但仍然有效推进”。

## Targets

1. **trace 可解释**: trace 能区分 `merge slice` 与 `coordination slice`，并记录 pairwise virtual gap 误差、速度错配和最紧证书约束。
2. **planned/actual 对齐**: 统计口径能解释滚动刷新 target 但执行仍按计划推进的情况。
3. **输出契约统一**: per-run `trace.jsonl`、`summary.json` 与 `ExperimentResultSummary` 字段一致，可被 `T6` 直接消费。
4. **实验外壳不越界**: `T5` 只负责产出和解释，不重写 planner / certificate / rollout 逻辑。

## Acceptance Criteria

### Step 1: 固定 trace schema（depends on Step 4 of T4）

- [ ] trace 至少记录 `tcg_ids`、`slice_kind`、`replan_index`、`x_m_star`、`t_m_star`、`v_star`、`delta_open_before/after`、`virt_e_pm`、`virt_e_ms`、`pairwise_gap_ready`、`relative_speed_ready`、`binding_constraint`、`min_margin_*`。
- [ ] trace 能明确区分 `merge` 与 `coordination` 两类 slice。
- [ ] A0/A1 首版场景下，即使 `u/f` 缺省，trace 仍能稳定输出。

### Step 2: 固定 planned/actual 与 summary 结构（depends on Step 1）

- [ ] `planned` 能记录最近一次有效 `TCG`、`MergeTarget` 与 `RollingPlanSlice`。
- [ ] `actual` 能记录实际 merge 完成 tick、实际 completion anchor、实际 gaps 与 slice 序列。
- [ ] `summary.json` 足以支持后续 `A0-A3` blocking gate 和更大流量实验汇总。
- [ ] `evaluate_experiment()` 函数已实现，能接受 `experiment_id` 和 `list[ExperimentResultSummary]`，输出聚合后的 `ExperimentResultSummary`。

### Step 3: 完成实验 README 与验证（depends on Step 2）

- [ ] `experiments/active_gap_v1/README.md` 写清输入参数、输出目录和关键字段解释。
- [ ] `pytest tests/active_gap_v1/test_metrics_and_trace.py` 通过。
- [ ] `T6` 可在不改实验脚本的前提下直接消费 `T5` 产物。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法实验层与结果汇总的正式 spec
  - `docs/design.md` — A 层优先验证与当前执行优先级
  - `docs/contracts.md` — `ExperimentResultSummary`、`RollingPlanSlice`、`SafetyCertificate`
  - `docs/features/active_gap_v1/design.md` — feature 级 metrics / regression 落点

### Docs:

**Formal Specs:**

- `docs/design.md`: A0-A3 先于大车流，当前 tick 无 merge 解时先 coordination
- `docs/contracts.md`: `ExperimentResultSummary`、slice 类型和证书字段
- `docs/formulas.md`: pairwise virtual gap、推进条件和证书最小裕度

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: `WP-5` 的执行说明
- `docs/features/active_gap_v1/design.md`: `T5` 在 feature 闭环中的位置

### Developer insights:

- **T5 是解释层，不是算法层**: 它负责把行为说清楚，不负责改行为。
- **slice 类型必须入 trace**: 否则你看不到“没 merge 但仍在造 gap”的过程。
- **planned/actual 必须适配滚动刷新**: 不能继续沿用旧 baseline 的静态计划记账方式。
- **A 层优先**: 输出结构必须首先服务 A0-A3，而不是先服务大车流统计。
- **u/f 缺省要可落盘**: 首版 A 场景默认没有 `u/f`，但 trace schema 不能因此失稳。

### Editable Paths

- `src/active_gap_v1/metrics.py` — 指标与 summary 聚合
- `experiments/active_gap_v1/README.md` — 实验入口与输出格式说明
- `experiments/active_gap_v1/common.py` — trace / summary 公用壳层
- `tests/active_gap_v1/test_metrics_and_trace.py` — 输出契约测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **结果层不改算法层**: `T5` 不能修改 planner、certificate 或 rollout 的核心语义。
- **A 层优先**: 输出字段必须首先服务 A0-A3 诊断，而不是先服务大车流汇总。
- **保留过程信息**: 不要把 “当前没 merge 但在造 gap” 压成一个模糊的等待状态。

## Skills

### Open URL

用于核对正式文档中的 trace 字段、A 层输出要求和 `planned/actual` 口径。

### Code Exploration

用于检查实验入口、`metrics.py` 和 `ExperimentResultSummary` 的字段一致性。

### Parallel Subagent

仅在后续需要并行核对 trace schema 和 summary schema 时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固定 trace schema（Step 1, depends on Phase 4 of T4）

- [ ] 1.1 定义 trace 字段与 slice 类型枚举
- [ ] 1.2 定义 `u/f` 缺省时的落盘约定

### Phase 2: 固定 planned/actual 与 summary（Step 2, depends on Phase 1）

- [ ] 2.1 重新定义 `planned / actual`
- [ ] 2.2 固定 `summary.json` 字段和 `ExperimentResultSummary` 映射
- [ ] 2.3 实现 `evaluate_experiment()` 函数

### Phase 3: 完成 README 与测试（Step 3, depends on Phase 2）

- [ ] 3.1 写清实验 README、输入参数和输出格式
- [ ] 3.2 为 trace/schema 完整性和序列化格式补测试

## 你负责的文件（白名单）

```text
src/active_gap_v1/metrics.py
experiments/active_gap_v1/README.md
experiments/active_gap_v1/common.py
tests/active_gap_v1/test_metrics_and_trace.py
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/types.py`、`config.py`、`snapshot.py`、`tcg_selector.py`（由 `T1` 负责）
- `src/active_gap_v1/predictor.py`、`merge_target_planner.py`（由 `T2` 负责）
- `src/active_gap_v1/quintic.py`、`certificate.py`（由 `T3` 负责）
- `src/active_gap_v1/executor.py`、`state_machine.py`（由 `T4` 负责）
- `experiments/active_gap_v1/a_layer_micro_scenarios.py`、`regression_gate.py`（由 `T6` 负责）

## 依赖的现有代码（需要先读的文件）

- `src/active_gap_v1/types.py`
- `src/active_gap_v1/executor.py`
- `src/active_gap_v1/state_machine.py`
- `src/active_gap_v1/certificate.py`
- `docs/design.md`
- `docs/contracts.md`

## 实现步骤

### 1. 固定 trace 字段

- 为每个 tick 记录 `tcg_ids`、`slice_kind`、`delta_open_before/after`、`speed_alignment_before/after`、`virt_e_pm`、`virt_e_ms`、`pairwise_gap_ready`、`relative_speed_ready`、`binding_constraint`、`min_margin_*`。
- 明确 `u/f` 缺省时相关字段如何写 `null / None`，不要临时删字段。

### 2. 定义 `planned / actual`

- `planned` 记录最近一次有效 `TCG`、`MergeTarget`、`RollingPlanSlice`。
- `actual` 记录真实 merge 完成 tick、真实 completion anchor、真实 gaps 和 slice 序列。
- 保证滚动刷新情况下，统计仍然可解释。

### 3. 实现 summary 聚合

- 生成单次运行 `summary.json`。
- 为 `A0-A3` 预留 blocking gate 所需字段。
- 对接 `ExperimentResultSummary`，为后续大车流恢复留出扩展位。
- 实现 `evaluate_experiment()` 函数，确保它能聚合多次运行结果并映射到 `ExperimentResultSummary`。

### 4. 写清实验 README

- 说明输入参数、输出目录、trace 文件和 summary 文件含义。
- 明确 A 层首版默认只看 `p/m/s`。

### 5. 补单测

- 覆盖 trace/schema 完整性、slice 类型、`u/f` 缺省字段、planned/actual 对齐和 summary 序列化。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_metrics_and_trace.py` 通过。
- trace 能区分 `merge` 与 `coordination` 两类 slice。
- 能记录 `virt_e_pm / virt_e_ms` 与 `Δ_open` 聚合诊断的变化。
- 能解释为什么某次 tick 没 merge 但仍然是“有效推进”。

### 组装验证（产出运行时依赖的 task，可选）

- `T6` 可以直接消费 `T5` 输出执行 A0-A3 blocking gate。
- 不需要修改实验入口或主链逻辑就能完成结果解释。

### 环境验证（涉及配置加载的 task，可选）

- 输出结构只依赖顶层 spec 已冻结字段，不读取额外环境配置。
- `u/f` 缺省不会导致 trace / summary 结构分叉。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| merge / coordination 执行输出 | `T4` | slice 类型、状态流转和证书字段已稳定 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `trace.jsonl` / `summary.json` schema | `T6` | A 层门禁可直接消费 |
| `ExperimentResultSummary` 映射 | 后续更大流量实验 | 聚合口径稳定、可扩展 |

### 不要做

- 不要修改 planner、certificate 或 rollout 逻辑。
- 不要把 A 层首版的 `p/m/s` 场景扩成必须带 `u/f`。
- 不要把 `coordination slice` 压缩成模糊的“等待”统计。
