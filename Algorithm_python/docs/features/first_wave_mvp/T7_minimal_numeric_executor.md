<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T7: 最小纯 Python 数值执行器 (Minimal Numeric Executor)

> 最后更新：`2026-04-06T01:05:00+08:00`

## 前置条件

- `T1_shared_types_and_config`、`T2_snapshot_and_step2`、`T3_acceptance_gate_and_commit`、`T4_rollout_and_state_machine`、`T5_experiments_and_metrics`、`T6_validation_and_regression` 已完成。
- 必读：`README.md`、`docs/design.md`（重点看 8.1/8.2/8.3/8.4 与闭环主链）。
- 必读：`docs/contracts.md`（重点看 `PlanningSnapshot`、`CommittedPlan`、`ExperimentResultSummary`）。
- 必读：`docs/features/first_wave_mvp/README.md` 与 `design.md`。

## 目标

把现有的算法闭环、实验定义和回归门禁接成一个最小纯 Python 数值执行器，使三类实验入口能够真正按 seed 和 tick 推进系统，并自动写出 `experiments/first_wave_mvp/outputs/<experiment_id>/summary.json`。

## Targets

1. **执行器闭环落地**: 基于 seed 初始化 `world_state`，按 `0.1s` tick 推进 `snapshot -> step2 -> gate/commit -> rollout`。
2. **真实实验结果产出**: 三类实验入口真正运行并生成 `PerSeedResult`，再落盘 `summary.json`。
3. **结果可复现**: 同 seed 两次运行结果一致；不同 seed 至少在初始状态或最终 summary 上出现差异。

## Acceptance Criteria

### Step 1: 同步 T7 文档与最小模块边界（no dependencies — start here）

- [ ] `docs/features/first_wave_mvp/README.md`、`design.md` 已加入 `T7`。
- [ ] `T7` 白名单、黑名单和验证闭环已在 feature 文档中冻结。
- [ ] `T7` 明确只做纯 Python 数值执行，不引入 SUMO/CARLA/TraCI 或第二波能力。

### Step 2: 实现最小执行器闭环（depends on Step 1）

- [ ] 已实现 `ScenarioInitializer`、`ExperimentRunner`、`MetricsCollector` 三个最小模块。
- [ ] `ExperimentRunner` 以 `0.1s` tick 驱动 `build_snapshot -> generate_candidates -> accept/commit -> rollout`，并有 `sim_duration_s / max_ticks` 硬终止。
- [ ] 三类实验入口可以真实运行并写出 `outputs/<experiment_id>/summary.json`。

### Step 3: 完成真实性与落盘验证（depends on Step 2）

- [ ] 同 seed 两次运行结果一致。
- [ ] 不同 seed 至少在初始 `world_state` 或最终 `summary.json` 上有差异。
- [ ] 端到端测试会真实写出 `summary.json`，且 schema 与 `T5/T6` 契约兼容。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波 MVP 代码与实验目录
  - `src/first_wave_mvp/snapshot.py` — 快照构造
  - `src/first_wave_mvp/step2_fifo.py` — 候选生成
  - `src/first_wave_mvp/gate.py` / `commit.py` — 共享验收与提交
  - `src/first_wave_mvp/rollout.py` / `state_machine.py` — 执行推进
  - `experiments/first_wave_mvp/common.py` — 实验定义与 `PerSeedResult`
  - `src/first_wave_mvp/metrics.py` — 汇总与统计视图

### Docs:

**Formal Specs:**

- `docs/design.md`: MVP 边界、三类实验目标和闭环协议
- `docs/contracts.md`: 共享对象与结果契约

**Feature Package:**

- `docs/features/first_wave_mvp/README.md`: 执行顺序与新增 `T7`
- `docs/features/first_wave_mvp/design.md`: `T7` 在 feature 闭环中的位置
- `docs/features/first_wave_mvp/T5_experiments_and_metrics.md`: 实验定义与结果结构
- `docs/features/first_wave_mvp/T6_validation_and_regression.md`: 门禁消费方式

### Developer insights:

- **这是执行层，不是实验定义层**: `T7` 负责把 `T1-T6` 接成真实运行器，不重新设计实验口径。
- **纯 Python 即可算数值仿真**: 关键是时间推进、自动生成结果，而不是是否接 SUMO/CARLA。
- **复用优先**: 优先复用 `T1-T6` 已有实现，不另起一套算法闭环。
- **流式统计优先**: 为避免内存膨胀，优先做流式指标收集，而不是缓存完整轨迹。
- **结果必须来自运行，不再是 mock fixture**: `summary.json` 的数据必须源自真实 tick 推进。

### Editable Paths

- `docs/features/first_wave_mvp/README.md`
- `docs/features/first_wave_mvp/design.md`
- `docs/features/first_wave_mvp/T7_minimal_numeric_executor.md`
- `src/first_wave_mvp/scenario_initializer.py`
- `src/first_wave_mvp/experiment_runner.py`
- `src/first_wave_mvp/metrics_collector.py`
- `experiments/first_wave_mvp/common.py`
- `experiments/first_wave_mvp/light_load_correctness.py`
- `experiments/first_wave_mvp/medium_high_load_competition.py`
- `experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py`
- `tests/first_wave_mvp/test_numeric_executor.py`

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **纯 Python 限定**: 不引入 SUMO/CARLA/TraCI 或其他外部仿真平台。
- **不改算法主语义**: `T7` 只驱动 `T1-T4`，不回写候选/gate/rollout 规则。
- **结果来源真实**: `summary.json` 必须由 tick 推进自动生成，而不是 fixture 填充。

## Skills

### Open URL

用于核对 formal spec 与 feature 文档中的三类实验目标、结果契约和门禁口径。

### Code Exploration

用于追踪 `snapshot -> step2 -> gate/commit -> rollout -> metrics` 的调用链是否完整闭合。

### Parallel Subagent

仅在后续需要并行校验执行器主循环与输出 schema 时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 同步文档并冻结 T7 范围（Step 1, no dependencies — start here）

- [ ] 1.1 更新 feature README 与 design
- [ ] 1.2 新增 `T7_minimal_numeric_executor.md`

### Phase 2: 实现 seed 初始化与 tick 主循环（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `scenario_initializer.py`
- [ ] 2.2 实现 `experiment_runner.py`
- [ ] 2.3 实现 `metrics_collector.py`

### Phase 3: 升级实验入口与真实落盘（Step 3, depends on Phase 2）

- [ ] 3.1 将三类实验入口升级为真实运行入口
- [ ] 3.2 写出 `outputs/<experiment_id>/summary.json`

### Phase 4: 完成端到端验证（Step 4, depends on Phase 3）

- [ ] 4.1 添加同 seed / 异 seed / 真实落盘测试
- [ ] 4.2 验证输出 schema 与 `T5/T6` 契约兼容

## 你负责的文件（白名单）

```text
docs/features/first_wave_mvp/README.md
docs/features/first_wave_mvp/design.md
docs/features/first_wave_mvp/T7_minimal_numeric_executor.md
src/first_wave_mvp/scenario_initializer.py
src/first_wave_mvp/experiment_runner.py
src/first_wave_mvp/metrics_collector.py
experiments/first_wave_mvp/common.py
experiments/first_wave_mvp/light_load_correctness.py
experiments/first_wave_mvp/medium_high_load_competition.py
experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py
tests/first_wave_mvp/test_numeric_executor.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`config.py`（由 `T1` 负责）
- `src/first_wave_mvp/snapshot.py`、`step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/gate.py`、`commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/rollout.py`、`state_machine.py`（由 `T4` 负责）
- `src/first_wave_mvp/metrics.py`、`experiments/first_wave_mvp/regression_gate.py`（分别由 `T5/T6` 负责）

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/snapshot.py`
- `src/first_wave_mvp/step2_fifo.py`
- `src/first_wave_mvp/gate.py`
- `src/first_wave_mvp/commit.py`
- `src/first_wave_mvp/rollout.py`
- `src/first_wave_mvp/metrics.py`
- `experiments/first_wave_mvp/common.py`
- `experiments/first_wave_mvp/regression_gate.py`

## 实现步骤

### 1. 同步 feature 文档

- 先把 `T7` 写入 feature README、design 和专属 task 文档。
- 保证当前新增范围不会与 `T5/T6` 既有职责打架。

### 2. 实现最小执行器三件套

- `scenario_initializer.py` 负责 seed -> 初始 `world_state`
- `experiment_runner.py` 负责 tick 主循环与硬终止
- `metrics_collector.py` 负责流式生成 `PerSeedResult`

### 3. 升级实验入口

- 让三类实验入口真正运行，而不是只打印 manifest。
- 写出真实 `summary.json`

### 4. 补端到端测试

- 同 seed 结果一致
- 不同 seed 有差异
- 真实落盘且 schema 可被 `T6` 消费

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_numeric_executor.py` 通过。
- 至少有一个实验入口会真实写出 `outputs/.../summary.json`。
- `summary.json` 中的键名保持 `snake_case`。

### 组装验证（产出运行时依赖的 task，可选）

- 三类实验入口都能在不改 `T5/T6` 结构的前提下产出真实结果。
- 真实输出可直接被 `T6` 现有门禁逻辑消费。

### 环境验证（涉及配置加载的 task，可选）

- 不依赖 SUMO/CARLA/TraCI。
- seed / 输出路径 / 仿真终止条件均来自纯 Python 本地配置。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 算法闭环 | `T1-T4` | 可被执行器真实驱动 |
| 实验结构与汇总 | `T5` | `ExperimentSpec` / `PerSeedResult` / summary 契约已稳定 |
| 门禁逻辑 | `T6` | 可消费真实执行器写出的结果 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| 真实 `summary.json` | 用户 / 后续研究 | 不再是 mock 样例，而是 tick 推进产物 |
| 最小数值执行器 | 后续实验扩展 | 可继续扩成更完整的纯 Python 仿真层 |

### 不要做

- 不要引入 SUMO/CARLA/TraCI。
- 不要引入 `simple DP`、两层分层算法、多 partition 或第二波场景。
- 不要重写 `T5/T6` 的结果契约与门禁逻辑。
