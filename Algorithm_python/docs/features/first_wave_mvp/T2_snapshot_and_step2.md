<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T2: Snapshot 与 Step 2 候选生成 (Snapshot and Step-2 Candidate Generation)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- `T1_shared_types_and_config` 已完成。
- 必读：`docs/design.md`（重点看 “Planning Snapshot”“Step 2：候选生成”）。
- 必读：`docs/contracts.md`（重点看 `PlanningSnapshot`、`CandidatePlan`、Planning Cycle 协议）。
- 必读：`docs/formulas.md`（重点看 `X_fixed/X_flex`、FIFO gap、`L/U` 粗时间窗、tie-break）。
- 必读：`docs/features/first_wave_mvp/design.md`。

## 目标

实现第一波 MVP 的 `build_snapshot()` 与 `generate_candidates()`：固定“每个 planning tick 只服务 1 个 active decision partition、只处理 1 辆 ramp CAV”的入口语义，在单个 snapshot 上一次性生成完整有序候选列表。

## Targets

1. **单 partition 入口稳定**: 每个 planning tick 只选 1 个 ramp ego，且只构造 1 个 `active decision partition`。
2. **候选列表一次性生成**: `build_snapshot()` 和 `generate_candidates()` 在单个 snapshot 上完成 FIFO 候选枚举、gap 导出与排序。
3. **回归可复现**: 同一输入下的候选顺序、`objective_key` 和 `candidate_id` 完全稳定。

## Acceptance Criteria

### Step 1: 固定单 ego 与 snapshot 构造（no dependencies — start here）

- [ ] 只会选取“匝道最靠前、且未 `COMMITTED/EXECUTING` 的 ramp CAV”作为本 tick 规划对象。
- [ ] `PlanningSnapshot` 包含当前 tick 所需的控制区状态、target-lane ordered objects 和已 `COMMITTED` 计划。
- [ ] `snapshot_id` 会被 `T3` 复用，而不是在 gate 阶段重新生成世界状态。

### Step 2: 生成 FIFO fixed/flexible 候选（depends on Step 1）

- [ ] `fixed anchor` 只尝试 `x_m = 170m`，`flexible anchor` 只在 legal merge zone 内枚举整数 `x_m`。
- [ ] 每个 `x_m` 只导出唯一 FIFO gap，不会在同一 `x_m` 下向后回退搜更晚 gap。
- [ ] 候选使用 `(t_m, Δdelay, x_m)` 排序，并遵守 spec 中的 tie-break 规则。

### Step 3: 固定确定性枚举与验证（depends on Step 2）

- [ ] `candidate_id` 基于稳定字段生成，不依赖无序遍历或随机值。
- [ ] 同一输入至少重复运行 3 次，候选列表顺序和 `candidate_id` 完全一致。
- [ ] `pytest tests/first_wave_mvp/test_snapshot_and_step2.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波 Step 2 的正式 spec 与实现目录
  - `docs/design.md` — `Planning Snapshot` 与 `Step 2` 的主线定义
  - `docs/contracts.md` — `PlanningSnapshot`、`CandidatePlan` 和 Planning Cycle 协议
  - `docs/formulas.md` — `X_fixed/X_flex`、FIFO gap、`L/U` 时间窗和 tie-break

### Docs:

**Formal Specs:**

- `docs/design.md`: 单 partition / 单 ego、snapshot 不可被 Step 3 改写
- `docs/contracts.md`: 候选对象、排序协议和 `objective_key`
- `docs/formulas.md`: anchor 枚举、FIFO gap、时间窗与排序目标

**Feature Package:**

- `docs/features/first_wave_mvp/design.md`: 模块映射和确定性枚举约束
- `docs/features/first_wave_mvp/README.md`: `T1 -> T2 -> T3` 的依赖链

### Developer insights:

- **单 partition 冻结**: 第一波明确只允许 1 个 `active decision partition`，不能在 `T2` 偷扩成多对象求解。
- **单 snapshot 语义**: `Step 2` 必须在一个 snapshot 上生成完整有序候选，供 `T3` 逐个消费。
- **FIFO 边界**: FIFO 是“按自由到达优先级排队”，不是“固定顺序种子 + gap 搜索器”。
- **确定性优先**: 候选枚举和 `candidate_id` 的稳定性直接决定 `T6` 回归是否可复现。
- **职责隔离**: `T2` 只负责生成和排序，不做 gate、commit、wait 或 fail-safe 判定。

### Editable Paths

- `src/first_wave_mvp/snapshot.py` — `build_snapshot()` 与 snapshot 组装
- `src/first_wave_mvp/step2_fifo.py` — FIFO fixed/flexible 候选生成
- `tests/first_wave_mvp/test_snapshot_and_step2.py` — 确定性与候选正确性测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **一个 snapshot 一份候选列表**: 不允许在 `T3` 或 rollout 中重建 Step 2 候选。
- **确定性优先**: 候选顺序和 `candidate_id` 必须可重复，不接受随机 UUID。
- **第一波限制**: 禁止引入 `simple DP`、多 partition、上游换道或更大协同范围。

## Skills

### Open URL

用于打开 formal spec 与 feature 设计文档，逐条核对 Step 2 的冻结口径。

### Code Exploration

用于检查 `snapshot.py`、`step2_fifo.py` 与 `docs/contracts.md` / `docs/formulas.md` 的对象映射。

### Parallel Subagent

仅在后续实现阶段需要并行核对排序规则和测试夹具时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固定单 ego 与 snapshot（Step 1, depends on Phase 1 of T1）

- [ ] 1.1 实现 ramp ego 选取逻辑与单 partition 入口
- [ ] 1.2 实现 `build_snapshot()` 所需字段组装

### Phase 2: 生成 FIFO 候选（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `X_fixed/X_flex` 枚举与 FIFO gap 导出
- [ ] 2.2 实现 `L/U` 时间窗与 `(t_m, Δdelay, x_m)` 排序

### Phase 3: 固化确定性与测试（Step 3, depends on Phase 2）

- [ ] 3.1 固定稳定 `candidate_id` 和候选枚举顺序
- [ ] 3.2 为候选正确性、tie-break 和重复运行一致性补测试

## 你负责的文件（白名单）

```text
src/first_wave_mvp/snapshot.py
src/first_wave_mvp/step2_fifo.py
tests/first_wave_mvp/test_snapshot_and_step2.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py`（由 `T1` 负责）
- `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py`（由 `T4` 负责）
- `experiments/first_wave_mvp/*.py`、`src/first_wave_mvp/metrics.py`（由 `T5/T6` 负责）
- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`（正式真源，不在本 task 内改写）

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/types.py`
- `src/first_wave_mvp/config.py`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`

## 实现步骤

### 1. 固定单 partition / 单 ego 入口

- 只选取“匝道最靠前、且未 `COMMITTED/EXECUTING` 的 ramp CAV”作为本 tick 规划对象。
- 明确第一波只允许 1 个 `active decision partition`；任何多 partition 逻辑都必须拒绝进入本 task。

### 2. 实现 `build_snapshot()`

- 冻结 `sim_time_s`、control zone 车辆状态、target-lane ordered objects、已 `COMMITTED` 计划和 `policy_tag`。
- 保证 `Step 2` 与 `Step 3` 共享同一个 `snapshot_id`，不得在 `T3` 里重建世界状态。

### 3. 实现 `FIFO fixed/flexible` 候选生成

- `fixed anchor` 只尝试 `x_m = 170m`；`flexible anchor` 按 legal merge zone 内整数 `x_m` 枚举。
- 依据 `t_r_free(x_m)` 与目标车道有序对象导出每个 `x_m` 下唯一 FIFO gap。
- 使用 `(t_m, Δdelay, x_m)` 排序；`T3` 只消费此排序结果，不重复解释排序逻辑。

### 4. 固定确定性枚举与稳定 ID

- 候选枚举顺序必须可重复，禁止依赖无序容器遍历。
- `candidate_id` 必须由稳定字段生成，保证同一 `snapshot` 重跑得到同一候选顺序和同一 ID。

### 5. 补单测

- 覆盖 `X_fixed/X_flex`、FIFO gap 唯一性、`L/U` 时间窗、tie-break 和稳定排序。
- 验证相同输入重复运行时，候选列表和 `candidate_id` 完全一致。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_snapshot_and_step2.py` 通过。
- 同一 `snapshot` 输入重复运行至少 3 次，候选列表顺序和 `candidate_id` 保持一致。
- 候选不得超出 legal merge zone，也不得在同一 `x_m` 下向后回退搜更晚 gap。

### 组装验证（产出运行时依赖的 task，可选）

- `T3` 可直接消费 `PlanningSnapshot` 与排序后的 `CandidatePlan` 列表，无需改 `T1` 类型定义。
- `objective_key` 与 `candidate_id` 足以支撑后续 gate 日志和回归追踪。

### 环境验证（涉及配置加载的 task，可选）

- `fixed` / `flexible` 两种 `PolicyTag` 都能使用同一 `ScenarioConfig` 与同一时间离散运行。
- tie-break 只依赖 `epsilon_t_s` 与 spec 已冻结规则，不读取额外环境配置。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 共享类型与参数层 | `T1` | `types.py` / `config.py` 已稳定可 import |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `PlanningSnapshot` | `T3/T6` | snapshot 字段稳定，`T3` 不需重建世界状态 |
| 排序后的 `CandidatePlan` 列表 | `T3/T6` | 候选顺序、`objective_key` 和 `candidate_id` 可重复、可回归 |

### 不要做

- 不要实现共享 `acceptance gate`、`commit_candidate()`、`rollout_step()` 或实验脚本。
- 不要把 FIFO 扩成“同一 `x_m` 下向后回退找更晚 gap”的搜索器。
- 不要引入 `simple DP`、两层分层、上游换道、多 partition 或全局协同能力。
