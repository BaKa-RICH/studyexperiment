<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T5: 首轮实验入口与指标汇总 (Experiments and Metrics)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- `T1_shared_types_and_config`、`T2_snapshot_and_step2`、`T3_acceptance_gate_and_commit`、`T4_rollout_and_state_machine` 已完成。
- 必读：`docs/design.md`（重点看 “测试策略”“8.1/8.2/8.3 实验门禁”“8.4 Seed 与统计口径”）。
- 必读：`docs/contracts.md`（重点看 `ExperimentResultSummary`）。
- 必读：`docs/features/first_wave_mvp/design.md`。

## 目标

为第一波 MVP 建立三类实验入口、per-seed 指标产出和聚合 summary 结构，使 `T6` 可以在不改实验脚本的前提下执行回归门禁。

## Targets

1. **三类实验入口完备**: 轻负荷正确性、中高负荷竞争、CAV 渗透率 / 协同范围消融都有独立入口和统一 harness。
2. **指标结构统一**: per-seed 结果和聚合 summary 都对齐 `ExperimentResultSummary` 与 `T6` 的消费需求。
3. **实验脚本不越界**: `T5` 只负责实验入口、结果产出和 README，不重新定义 planner / gate / rollout 行为。

## Acceptance Criteria

### Step 1: 建立三类实验入口（no dependencies — start here）

- [ ] 已建立轻负荷正确性、中高负荷竞争、CAV 渗透率 / 协同范围消融三类实验入口。
- [ ] 所有入口只服务第一波 `FIFO fixed/flexible`，不新增第二波算法标签。
- [ ] 若引用 `no_control`，仅作为参考汇总口径，不新增其 planner 实现。

### Step 2: 固定指标与 summary 结构（depends on Step 1）

- [ ] `metrics.py` 能输出 `completion_rate`、`abort_rate`、`collision_count`、`safety_violation_count`、`avg_ramp_delay_s`、`throughput_vph` 与 planned/actual 偏差。
- [ ] per-seed 结果足以支持 `mean / worst-seed / p95` 聚合。
- [ ] 三类实验共享统一 summary 格式。

### Step 3: 完成实验 README 与验证（depends on Step 2）

- [ ] `experiments/first_wave_mvp/README.md` 写清实验目的、输入参数和输出格式。
- [ ] `pytest tests/first_wave_mvp/test_experiments_and_metrics.py` 通过。
- [ ] `T6` 可在不改实验脚本的前提下直接消费 `T5` 产物。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波实验层与结果汇总的正式 spec
  - `docs/design.md` — 三类实验定义和门禁口径
  - `docs/contracts.md` — `ExperimentResultSummary` 契约
  - `docs/features/first_wave_mvp/design.md` — feature 级实验/回归位置映射

### Docs:

**Formal Specs:**

- `docs/design.md`: 8.1/8.2/8.3 三类实验门禁、8.4 seed 统计口径
- `docs/contracts.md`: `ExperimentResultSummary` 字段定义

**Feature Package:**

- `docs/features/first_wave_mvp/README.md`: `WP-5` 的执行说明
- `docs/features/first_wave_mvp/design.md`: `metrics.py` 与实验目录落点

### Developer insights:

- **实验范围冻结**: 第一波只跑 3 类实验，不扩展到第二波策略或更大场景。
- **no_control 只是参考**: 可以进入 summary，但不是当前 feature 的核心 planner 对象。
- **结果先产出，门禁后判断**: `T5` 负责产出和汇总，pass/fail 判定留给 `T6`。
- **per-seed 必不可少**: 没有 per-seed 结果，`T6` 无法执行多 seed 门禁。
- **字段对齐契约**: 指标命名必须与 `ExperimentResultSummary` 和正式文档一致。

### Editable Paths

- `src/first_wave_mvp/metrics.py` — 指标和 summary 聚合
- `experiments/first_wave_mvp/*.py` — 三类实验入口与公用 harness
- `tests/first_wave_mvp/test_experiments_and_metrics.py` — 实验层完整性测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **结果层不改算法层**: `T5` 不能修改 planner、gate 或 rollout 的核心语义。
- **三类实验固定**: 只实现正式 spec 已冻结的三类实验入口。
- **为 T6 让路**: 产出必须包含 per-seed 与聚合输入，不在 `T5` 内做最终门禁判定。

## Skills

### Open URL

用于核对正式文档中的三类实验定义、指标字段和多 seed 统计要求。

### Code Exploration

用于检查实验入口、`metrics.py` 和 `ExperimentResultSummary` 的字段一致性。

### Parallel Subagent

仅在后续需要并行核对实验 README、harness 与 summary 结构时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 建立三类实验入口（Step 1, depends on Phase 3 of T4）

- [ ] 1.1 创建轻负荷正确性实验入口
- [ ] 1.2 创建中高负荷竞争与消融实验入口

### Phase 2: 固定指标与汇总结构（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `metrics.py` 中的 per-seed 指标汇总
- [ ] 2.2 固定可供 `mean / worst-seed / p95` 消费的 summary 结构

### Phase 3: 完成 README 与测试（Step 3, depends on Phase 2）

- [ ] 3.1 写清实验 README、输入参数和输出格式
- [ ] 3.2 为实验 manifest、字段完整性和序列化格式补测试

## 你负责的文件（白名单）

```text
src/first_wave_mvp/metrics.py
experiments/first_wave_mvp/README.md
experiments/first_wave_mvp/common.py
experiments/first_wave_mvp/light_load_correctness.py
experiments/first_wave_mvp/medium_high_load_competition.py
experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py
tests/first_wave_mvp/test_experiments_and_metrics.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py`（由 `T1` 负责）
- `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py`（由 `T4` 负责）
- `experiments/first_wave_mvp/regression_gate.py`、`tests/first_wave_mvp/test_validation_and_regression.py`（由 `T6` 负责）

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/types.py`
- `src/first_wave_mvp/config.py`
- `src/first_wave_mvp/rollout.py`
- `src/first_wave_mvp/state_machine.py`
- `docs/design.md`
- `docs/contracts.md`

## 实现步骤

### 1. 固定实验入口骨架

- 创建 3 个实验入口：轻负荷正确性、中高负荷竞争、CAV 渗透率 / 协同范围消融。
- 每个实验入口都只服务第一波 `FIFO fixed/flexible`；若需要 `no_control` 作为参考下界，只允许消费已存在的 `PolicyTag.NO_CONTROL` 汇总，不新增其 planner 实现。

### 2. 实现指标产出与聚合 summary

- 在 `metrics.py` 中统一输出 `completion_rate`、`abort_rate`、`collision_count`、`safety_violation_count`、`avg_ramp_delay_s`、`throughput_vph`、planned/actual 偏差等字段。
- 同时支持 per-seed 结果和聚合统计，给 `T6` 留出 `mean / worst-seed / p95` 的消费口径。

### 3. 固定实验配置与日志格式

- 在 `experiments/first_wave_mvp/README.md` 中写清实验名称、目的、必填参数和输出文件格式。
- `common.py` 只做 experiment harness、公用配置和结果收集，不承载新算法逻辑。

### 4. 补单测

- 覆盖三类实验 manifest 的完整性、summary 字段完整性和指标序列化格式。
- 验证实验入口不会偷偷引入第二波算法标签或多 partition 配置。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_experiments_and_metrics.py` 通过。
- 三类实验入口都能产出 `ExperimentResultSummary` 对齐的结果结构。
- 聚合 summary 至少包含 `mean`、`worst-seed`、`p95` 所需的原始输入字段。

### 组装验证（产出运行时依赖的 task，可选）

- `T6` 可以直接消费 `T5` 输出执行门禁，不需要修改实验入口。
- 轻负荷 / 竞争 / 消融三类实验都能复用同一个结果汇总格式。

### 环境验证（涉及配置加载的 task，可选）

- 实验脚本只读取 `ScenarioConfig` 和第一波 spec 已冻结参数。
- `experiments/first_wave_mvp/README.md` 中列出的运行参数与 `docs/design.md` 的门禁口径一致。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 闭环 rollout 输出 | `T4` | 可统计完成率、abort 率和 planned/actual 偏差 |
| 共享契约与参数 | `T1` | `ExperimentResultSummary` 及默认参数已稳定 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| 三类实验入口 | `T6` | 实验脚本稳定、命名清晰、只覆盖第一波 MVP |
| 聚合 summary | `T6` | 支持 `mean / worst-seed / p95` 的门禁判断 |

### 不要做

- 不要修改核心 planner、gate、rollout 语义。
- 不要把 `simple DP`、两层分层、上游换道、多 partition 写进实验入口。
- 不要在 `T5` 中定义“通过/失败”门禁结论；门禁判定留给 `T6`。
