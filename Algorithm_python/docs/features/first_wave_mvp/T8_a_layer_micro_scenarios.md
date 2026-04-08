<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T8: A 层微场景诊断实验 (A-Layer Micro-Scenario Diagnostics)

> 最后更新：`2026-04-06T01:40:00+08:00`

## 前置条件

- `T1_shared_types_and_config`、`T2_snapshot_and_step2`、`T3_acceptance_gate_and_commit`、`T4_rollout_and_state_machine`、`T5_experiments_and_metrics`、`T6_validation_and_regression`、`T7_minimal_numeric_executor` 已完成。
- 必读：`README.md`、`docs/design.md`（重点看闭环主链与 8.1/8.2/8.3 目标）。
- 必读：`docs/contracts.md`（重点看 `PlanningSnapshot`、`CandidatePlan`、`CommittedPlan`、`ExperimentResultSummary`）。
- 必读：`docs/features/first_wave_mvp/T2_snapshot_and_step2.md`、`T3_acceptance_gate_and_commit.md`、`T4_rollout_and_state_machine.md`、`T7_minimal_numeric_executor.md`。

## 目标

把当前 A 层微场景实验从“概念说明”升级成一个可直接实施的 task：后续 agent 接手后，应能按文档完成场景冻结、代码实现、真实运行、输出分析和结果汇报，而不需要再二次发散讨论。

## Targets

1. **场景集合冻结**: 正式定义 `A0/A1/A2/A3` 四个微场景，明确每个场景的初始布局、预期结果、关键观察点和通过/失败判据。
2. **输出结构冻结**: 每个场景都独立输出到新的目录，至少包含 `summary.json` 与 `trace.jsonl`，且字段结构足以支撑诊断与复盘。
3. **实现闭环明确**: task 本身应覆盖“实现、跑实验、分析输出、整理汇报”的完整执行路径，而不只是写场景说明。

## Acceptance Criteria

### Step 1: 冻结 A 层场景定义（no dependencies — start here）

- [ ] `A0`、`A1`、`A2`、`A3` 的初始布局、预期结果和关键观察点都写清楚。
- [ ] `A0/A1` 第一版均采用主路 `a=5,b=11`、匝道 `d=9`、同速起步，但二者的诊断目标不同。
- [ ] `A2` 固定为主路 `a=5,b=11`、匝道 `c=1,d=9`、同速起步。
- [ ] `A3` 首版给出明确的更紧数值布局，并以“必须给出 `NO_FEASIBLE_PLAN`、不能乱撞/假成功”为硬验收目标。

### Step 2: 冻结输出结构与诊断口径（depends on Step 1）

- [ ] 每个场景的输出目录都与现有车流实验隔离。
- [ ] `summary.json` 的必填字段、类型和解释已冻结。
- [ ] `trace.jsonl` 的事件 schema、关键字段和时间语义已冻结。
- [ ] `A1` 的 fixed/flexible 差异已落成可比指标，而不是泛泛描述。

### Step 3: 冻结实现边界与执行约束（depends on Step 2）

- [ ] 本 task 明确指出后续实现只服务微场景诊断，不回到大车流优先路线。
- [ ] 本 task 明确指出采用确定性初始布局，不再围绕 seed 讨论。
- [ ] 本 task 明确指出实现完成后要真实跑场景、分析输出并整理汇报。

### Step 4: 明确后续验证闭环（depends on Step 3）

- [ ] 至少定义一套真实运行命令和验证命令。
- [ ] 至少定义一套“输出文件存在 + schema 正确 + 关键结论可复盘”的完成标准。
- [ ] 明确后续实现者交付时必须包含微场景分析汇报，而不是只给原始输出文件。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波 MVP 代码、实验和 feature 文档目录
  - `src/first_wave_mvp/snapshot.py` — 单 tick snapshot 构造
  - `src/first_wave_mvp/step2_fifo.py` — FIFO 候选生成与排序
  - `src/first_wave_mvp/gate.py` / `commit.py` — 共享验收与提交
  - `src/first_wave_mvp/rollout.py` / `state_machine.py` — 执行推进与状态机
  - `src/first_wave_mvp/experiment_runner.py` — 当前最小纯 Python 数值执行器
  - `experiments/first_wave_mvp/outputs/` — 现有真实车流实验输出目录

### Docs:

**Formal Specs:**

- `README.md`: 第一波 MVP 的范围与最自然的实现顺序
- `docs/design.md`: 三类实验目标、闭环协议与门禁
- `docs/contracts.md`: 共享对象和字段锁定规则

**Feature Package:**

- `docs/features/first_wave_mvp/T2_snapshot_and_step2.md`: Step 2 的候选和排序语义
- `docs/features/first_wave_mvp/T3_acceptance_gate_and_commit.md`: gate 与 commit 边界
- `docs/features/first_wave_mvp/T4_rollout_and_state_machine.md`: 执行语义与失败分支
- `docs/features/first_wave_mvp/T7_minimal_numeric_executor.md`: 当前真实数值执行器的最小结构

### Developer insights:

- **微场景优先**: `T8` 的目的不是再做大车流压力测试，而是把算法本体剥出来看清楚。
- **场景数少但信息密度高**: 4 个场景应覆盖“能工作、看差异、连续 FIFO、明确无解”四类问题。
- **A0/A1 可同布局不同目标**: 当前重点是先比较“同一初始局面下不同策略/观察目标”，而不是堆更多布局。
- **输出要能复盘**: `summary.json` 用来给结论，`trace.jsonl` 用来解释为什么出现这个结论。
- **与车流实验隔离**: A 层输出要放到新的目录里，避免和现有车流实验混在一起。

### Editable Paths

- `src/first_wave_mvp/scenario_initializer.py`
- `src/first_wave_mvp/experiment_runner.py`
- `src/first_wave_mvp/metrics_collector.py`
- `experiments/first_wave_mvp/a_layer_micro_scenarios.py`
- `tests/first_wave_mvp/test_a_layer_micro_scenarios.py`
- `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/**`
- `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/analysis_report.md`

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **实现型 task**: 该文档要足够细，后续 agent 能直接照着做，不再补二次需求。
- **真实运行要求**: 后续必须真实跑 `A0-A3`，不允许只生成占位输出或 mock 结果。
- **诊断优先**: 先回答“算法是否有效、哪里不对齐”，不先追求车流吞吐结论。

## Skills

### Open URL

用于核对 formal spec 与现有 task 文档中的闭环定义、实验目标和门禁口径。

### Code Exploration

用于将 `T8` 与 `T2/T3/T4/T7` 的现有能力对齐，避免文档要求脱离当前代码现实。

### Parallel Subagent

用于从“算法诊断价值”“输出可复盘性”“实现边界”三个角度并行审阅 `T8` 任务文档。

## Scout Findings

### Verified

- 现有 `T2/T3/T4/T7` 已提供微场景实现所需的最小能力：候选生成、gate、rollout 和执行器主循环。
- 现有真实车流实验已经能写出 `summary.json`，说明 `T8` 无需重建实验框架，只需增补确定性微场景入口与更细的 trace。
- 当前仓库中还不存在独立的 `a_layer_micro_scenarios.py` 与 `test_a_layer_micro_scenarios.py`，因此 `T8` 必须明确新增它们。

### Discovered

- 当前 `T8` 的核心不足不在“场景方向”，而在“后续实现步骤和输出 schema 太粗”。
- 现有 `summary.json` 结构偏向车流实验，不足以直接回答微场景里的“哪一步 accept/reject、gap 何时变合规”。
- 微场景实现最需要的是确定性布局与 trace，而不是更多随机性或更大流量。

### Gaps

- `A3` 若不把布局冻结成明确数值，后续实现者无法判断什么叫“无解”。
- 当前 task 还没写“跑实验、分析结果、整理汇报”的明确工作包。
- `trace.jsonl` 只有字段清单还不够，需要至少冻结事件类型和一份最小样例口径。

## Work Packages

### WP-1: 冻结四个微场景与验收口径（complexity: M, subagent: manual）

- Depends on: none
- Actions:
  1. 写清 `A0/A1/A2/A3` 的初始布局与诊断目标。
  2. 为每个场景补通过/失败判据。
  3. 冻结 `A3` 的无解定义。
- Done when: 后续实现者不再需要猜“场景怎么摆、成功算什么、失败算什么”。

### WP-2: 冻结输出契约与目录结构（complexity: M, subagent: manual）

- Depends on: WP-1
- Actions:
  1. 定义 `summary.json` 必填字段、类型和解释。
  2. 定义 `trace.jsonl` 事件 schema 和字段。
  3. 固定与现有车流实验隔离的输出路径。
- Done when: 输出结构可以被复用、比较和复盘。

### WP-3: 冻结后续实现白名单与运行命令（complexity: M, subagent: manual）

- Depends on: WP-2
- Actions:
  1. 指定最小实现文件集合。
  2. 写清运行命令、验证命令和完成定义。
  3. 约束不做项，防止又回到大车流或大规模实验。
- Done when: 后续 agent 能直接开始实现与运行。

### WP-4: 冻结结果分析与汇报要求（complexity: M, subagent: manual)

- Depends on: WP-3
- Actions:
  1. 明确要产出的分析报告。
  2. 指定报告里必须回答的问题。
  3. 规定对比表和 trace 证据的引用要求。
- Done when: 后续交付不只是原始文件，还包含可读的诊断结论。

## Execution Waves

### Wave 1（串行）

- `WP-1`

### Wave 2（依赖 Wave 1）

- `WP-2`

### Wave 3（依赖 Wave 2）

- `WP-3`

### Wave 4（依赖 Wave 3）

- `WP-4`

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| A3 数值布局不明确，后续实现时又回到临时拍脑袋 | High | 在任务文档里先冻结首版数值与必要的收紧规则 |
| `trace.jsonl` 字段不统一，后续很难做时序诊断 | High | 在 T8 里提前冻结事件 schema |
| 微场景实现中又偷偷回到大车流或随机扰动 | Medium | 在白名单和不做项中明确排除 |
| 只生成输出文件，不整理分析结论 | Medium | 把“分析报告”写进目标、TODO 和验收标准 |

## TODOs

### Phase 1: 冻结场景与验收目标（Step 1, no dependencies — start here）

- [ ] 1.1 写清 `A0/A1/A2/A3` 的初始布局、车辆角色与预期结果
- [ ] 1.2 为每个场景补关键观察点与通过/失败判据
- [ ] 1.3 冻结 `A3` 的无解布局或收紧规则

### Phase 2: 冻结输出 schema 与目录结构（Step 2, depends on Phase 1）

- [ ] 2.1 固定 `summary.json` 必填字段、类型与解释
- [ ] 2.2 固定 `trace.jsonl` 事件类型、关键字段与时间语义
- [ ] 2.3 固定 `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/<scenario_id>/` 目录约定

### Phase 3: 冻结实现白名单与运行命令（Step 3, depends on Phase 2）

- [ ] 3.1 指定微场景实现最小白名单
- [ ] 3.2 指定后续运行命令、验证命令与 DoD
- [ ] 3.3 明确不做项，防止回到大车流/seed/论文级实验

### Phase 4: 固定实验执行工作包（Step 4, depends on Phase 3）

- [ ] 4.1 明确后续实现必须真实运行 `A0-A3`
- [ ] 4.2 明确每个场景至少输出 `summary.json` 与 `trace.jsonl`
- [ ] 4.3 明确 A1 必须同时跑 `fixed/flexible` 并生成对比结果

### Phase 5: 冻结分析与汇报要求（Step 5, depends on Phase 4）

- [ ] 5.1 明确需要产出 `analysis_report.md`
- [ ] 5.2 明确报告至少回答：算法是否有效、哪一步不对齐、A1 fixed/flexible 差异、A3 为什么无解
- [ ] 5.3 明确报告要引用 `summary.json` 与 `trace.jsonl` 证据

## 你负责的文件（白名单）

```text
src/first_wave_mvp/scenario_initializer.py
src/first_wave_mvp/experiment_runner.py
src/first_wave_mvp/metrics_collector.py
experiments/first_wave_mvp/a_layer_micro_scenarios.py
tests/first_wave_mvp/test_a_layer_micro_scenarios.py
experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/**
experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/analysis_report.md
```

## 禁止修改的文件（黑名单）

- `docs/features/first_wave_mvp/README.md`
- `docs/features/first_wave_mvp/design.md`
- `src/first_wave_mvp/types.py`
- `src/first_wave_mvp/config.py`
- `src/first_wave_mvp/snapshot.py`
- `src/first_wave_mvp/step2_fifo.py`
- `src/first_wave_mvp/gate.py`
- `src/first_wave_mvp/commit.py`
- `src/first_wave_mvp/rollout.py`
- `src/first_wave_mvp/state_machine.py`
- `src/first_wave_mvp/metrics.py`
- `experiments/first_wave_mvp/common.py`
- `experiments/first_wave_mvp/light_load_correctness.py`
- `experiments/first_wave_mvp/medium_high_load_competition.py`
- `experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py`
- `experiments/first_wave_mvp/regression_gate.py`
- `tests/first_wave_mvp/__init__.py`
- `tests/first_wave_mvp/conftest.py`
- `tests/first_wave_mvp/test_types_and_config.py`
- `tests/first_wave_mvp/test_snapshot_and_step2.py`
- `tests/first_wave_mvp/test_acceptance_gate_and_commit.py`
- `tests/first_wave_mvp/test_rollout_and_state_machine.py`
- `tests/first_wave_mvp/test_experiments_and_metrics.py`
- `tests/first_wave_mvp/test_validation_and_regression.py`

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/snapshot.py`
- `src/first_wave_mvp/step2_fifo.py`
- `src/first_wave_mvp/gate.py`
- `src/first_wave_mvp/rollout.py`
- `src/first_wave_mvp/experiment_runner.py`
- `experiments/first_wave_mvp/common.py`

## 实现步骤

### 1. 固定 A 层场景

- `A0`：3 车主链可工作场景  
  主路 `a=5,b=11`；匝道 `d=9`；同速起步  
  预期：至少一种策略能逐步形成合规 gap，并无碰撞通过  
  关键观察：是否能从不合规起始局面逐步变成合规

- `A1`：3 车策略差异场景  
  主路 `a=5,b=11`；匝道 `d=9`；同速起步  
  预期：`fixed` 与 `flexible` 在至少一个可比指标上表现出差异  
  对比指标：首次 ACCEPT 时刻、总延迟、最终是否通过、reject 次数

- `A2`：4 车连续 FIFO 场景  
  主路 `a=5,b=11`；匝道 `c=1,d=9`；同速起步  
  预期：前一辆匝道车处理后，后一辆匝道车仍按 FIFO 被正确处理  
  关键观察：第二辆匝道车的处理顺序和状态是否被前车影响

- `A3`：故意无解场景  
  首版冻结为：主路 `a=5,b=11`；匝道 `d=10.5`；同速起步  
  若后续实现验证该布局仍可解，则只允许在 `d ∈ [10.5, 10.9]` 内单向向前收紧一次，并把最终冻结值写入分析报告  
  预期：必须给出 `NO_FEASIBLE_PLAN`，不能乱撞、不能假成功

### 2. 固定输出格式

- 每个场景都单独输出到：
  - `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/<scenario_id>/summary.json`
  - `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/<scenario_id>/trace.jsonl`

- `summary.json` 必填字段至少包括：
  - `scenario_id`
  - `policy_tag`
  - `initial_vehicle_states`
  - `final_status`
  - `accepted_candidate_count`
  - `rejected_candidate_count`
  - `first_accept_time_s`
  - `completion_rate`
  - `abort_rate`
  - `collision_count`
  - `safety_violation_count`
  - `planned_actual_time_error_p95_s`
  - `planned_actual_position_error_p95_m`
  - `analysis_notes`

- `trace.jsonl` 每行至少包含：
  - `event_type`
  - `tick`
  - `sim_time_s`
  - `planning_ego_id`
  - `vehicle_states`
  - `candidate_summary`
  - `decision`
  - `reject_reason`
  - `execution_event`

### 3. 固定后续实现约束

- 后续实现必须采用确定性初始布局，不靠随机扰动制造差异。
- `A0-A3` 的结果先用于诊断，不直接拿来下论文级性能结论。
- 先优先回答“算法是否有效、planned/actual 是否对齐、A3 为什么无解”，再谈扩展场景。

### 4. 固定实验运行与汇报要求

- 后续实现完成后，必须真实运行 `A0-A3`。
- 后续实现完成后，必须生成：
  - 每个场景的 `summary.json`
  - 每个场景的 `trace.jsonl`
  - 一份汇总的 `analysis_report.md`
- `analysis_report.md` 至少回答：
  - 哪个场景主链有效
  - `A1` 里 `fixed/flexible` 的差异是什么
  - `A2` 里连续 FIFO 是否正常
  - `A3` 是否正确给出 `NO_FEASIBLE_PLAN`
  - planned/actual 指标是否仍存在统计定义错位
- 建议统一运行命令：
  - `python experiments/first_wave_mvp/a_layer_micro_scenarios.py --scenario A0`
  - `python experiments/first_wave_mvp/a_layer_micro_scenarios.py --scenario A1 --policy both`
  - `python experiments/first_wave_mvp/a_layer_micro_scenarios.py --all`
- 建议统一验证命令：
  - `pytest tests/first_wave_mvp/test_a_layer_micro_scenarios.py`

## 验收标准

### 零件验证（每个 task 必须）

- 后续实现必须真实运行 `A0-A3`，而不是只生成占位输出或 fixture 结果。
- `experiments/first_wave_mvp/outputs/a_layer_micro_scenarios/<scenario_id>/summary.json` 与 `trace.jsonl` 都必须真实存在。
- `pytest tests/first_wave_mvp/test_a_layer_micro_scenarios.py` 通过。
- `analysis_report.md` 完成并能解释每个场景的核心观察结果。

### 组装验证（产出运行时依赖的 task，可选）

- `T8` 的输出字段与 `T5/T6` 现有契约兼容，不要求重写现有 summary / gate 结构。
- `T8` 的目标与 `T2/T3/T4/T7` 已有能力对应得上，不会要求后续实现去发明全新算法层。
- 后续实现完成后，应能直接根据 `T8` 文档跑实验、写结果、做分析汇报。

### 环境验证（涉及配置加载的 task，可选）

- `T8` 明确指出 A 层微场景采用确定性初始布局，不再围绕 seed 做讨论。
- `T8` 明确指出新的输出目录与现有车流实验物理隔离。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 算法主链 | `T2/T3/T4` | 可在小场景中被直接诊断 |
| 最小执行器 | `T7` | 已能真实跑出 `summary.json`，可复用为微场景实现基础 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `T8_a_layer_micro_scenarios.md` | 后续实现 | 场景、输出、步骤与汇报要求已冻结，可直接实施 |

### 不要做

- 不要回填 `README.md` 或 `design.md`。
- 不要把微场景重新拉回大车流、论文级大规模实验或新的策略扩张。
