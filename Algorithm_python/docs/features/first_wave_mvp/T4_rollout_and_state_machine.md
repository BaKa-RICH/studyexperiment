<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T4: Rollout 与执行状态机 (Rollout and Execution State Machine)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- `T1_shared_types_and_config` 已完成。
- `T2_snapshot_and_step2` 已完成。
- `T3_acceptance_gate_and_commit` 已完成。
- 必读：`docs/design.md`（重点看 “Commit、等待与 Fail-Safe”）。
- 必读：`docs/contracts.md`（重点看 `ExecutionState`、`CommittedPlan`、`NO_FEASIBLE_PLAN` 协议）。
- 必读：`docs/features/first_wave_mvp/design.md` 的状态流转表。

## 目标

实现第一波 MVP 的 `rollout_step()` 与执行状态机：让系统在不重新选 gap、不隐藏重规划的前提下，正确处理 `COMMITTED` 执行、普通等待、`FAIL_SAFE_STOP` 和 `ABORTED`。

## Targets

1. **状态流转显式化**: 第一波执行状态表被明确写成可实现、可测试的转移规则。
2. **等待与降级可复盘**: `NO_FEASIBLE_PLAN`、wait、fail-safe、abort 都有清晰触发条件、状态副作用与原因码。
3. **Rollout 不越界**: `rollout_step()` 只消费当前状态和 `CommittedPlan`，不重入 `Step 2/Step 3`。

## Acceptance Criteria

### Step 1: 固化执行状态流转（no dependencies — start here）

- [ ] `APPROACHING`、`PLANNING`、`COMMITTED`、`EXECUTING`、`POST_MERGE`、`FAIL_SAFE_STOP`、`ABORTED` 的合法转移被显式写清。
- [ ] 非法转移返回显式错误或原因码，而不是静默忽略。
- [ ] `COMMITTED -> EXECUTING -> POST_MERGE` 主链可被独立验证。

### Step 2: 实现等待与降级分支（depends on Step 1）

- [ ] `NO_FEASIBLE_PLAN` 在非 `emergency_tail` 条件下保持 `PLANNING`，不触发隐藏 planner。
- [ ] ego 进入 `emergency_tail` 且持续无计划时，会进入 `FAIL_SAFE_STOP` 并最终记录 `ABORTED`。
- [ ] wait / fail-safe / abort 的状态副作用和原因码格式被固定。

### Step 3: 验证 Rollout 闭环（depends on Step 2）

- [ ] `rollout_step()` 只消费 `CommittedPlan` 与当前世界状态，不会改写语义字段。
- [ ] 正常路径与失败路径都有单测覆盖。
- [ ] `pytest tests/first_wave_mvp/test_rollout_and_state_machine.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波执行层与状态机的正式 spec
  - `docs/design.md` — wait / fail-safe / abort 的主线定义
  - `docs/contracts.md` — `ExecutionState`、`CommittedPlan`、`NO_FEASIBLE_PLAN` 协议
  - `docs/features/first_wave_mvp/design.md` — feature 级状态流转表

### Docs:

**Formal Specs:**

- `docs/design.md`: `Commit、等待与 Fail-Safe` 的主分支
- `docs/contracts.md`: `ExecutionState` 和 `NO_FEASIBLE_PLAN` 协议

**Feature Package:**

- `docs/features/first_wave_mvp/design.md`: `T3/T4` 边界与状态表
- `docs/features/first_wave_mvp/README.md`: `WP-4` 的执行说明和风险提示

### Developer insights:

- **Rollout 只消费，不决策**: `T4` 不能再生成 candidate 或重排 gap。
- **失败要显式**: wait、fail-safe 和 abort 不能被静默吞掉。
- **状态表优先**: 先把合法/非法转移写清，再实现运行逻辑，避免状态回环。
- **时间一致性**: rollout 时步必须与 planning/gate 时步保持 `0.1s` 一致。
- **边界清晰**: `T4` 处理执行和降级，`T3` 处理验收与 commit，二者不能交叉改语义字段。

### Editable Paths

- `src/first_wave_mvp/rollout.py` — rollout 推进逻辑
- `src/first_wave_mvp/state_machine.py` — 状态流转表与非法转移处理
- `tests/first_wave_mvp/test_rollout_and_state_machine.py` — 正常/失败路径测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **不要回到决策层**: rollout 不得重新生成 candidate、重排 FIFO 或改 gate 谓词。
- **失败必须有原因码**: wait、fail-safe、abort 的副作用必须可追踪。
- **保持第一波范围**: 禁止引入 `DECOMMIT`、多 partition、上游换道或第二波算法分支。

## Skills

### Open URL

用于核对 `docs/design.md` 与 `docs/contracts.md` 中的状态语义和失败分支口径。

### Code Exploration

用于检查 `rollout.py` / `state_machine.py` 是否只消费 `CommittedPlan` 与当前世界状态。

### Parallel Subagent

仅在后续需要并行审查状态流转与日志断言时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固化状态流转表（Step 1, depends on Phase 3 of T3）

- [ ] 1.1 写清合法转移和非法转移处理
- [ ] 1.2 固定 `COMMITTED -> EXECUTING -> POST_MERGE` 主链

### Phase 2: 落等待与降级分支（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `NO_FEASIBLE_PLAN` 下的 wait 分支
- [ ] 2.2 实现 `FAIL_SAFE_STOP -> ABORTED` 降级与原因码

### Phase 3: 完成 rollout 闭环测试（Step 3, depends on Phase 2）

- [ ] 3.1 为正常路径和失败路径补状态机测试
- [ ] 3.2 验证 rollout 不会修改 `CommittedPlan` 的语义字段

## 你负责的文件（白名单）

```text
src/first_wave_mvp/rollout.py
src/first_wave_mvp/state_machine.py
tests/first_wave_mvp/test_rollout_and_state_machine.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py`（由 `T1` 负责）
- `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/metrics.py`、`experiments/first_wave_mvp/*.py`（由 `T5/T6` 负责）
- 所有第二波算法入口和多 partition 相关文件

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/types.py`
- `src/first_wave_mvp/config.py`
- `src/first_wave_mvp/gate.py`
- `src/first_wave_mvp/commit.py`
- `docs/design.md`
- `docs/contracts.md`

## 实现步骤

### 1. 固化状态流转表

- 把 `APPROACHING`、`PLANNING`、`COMMITTED`、`EXECUTING`、`POST_MERGE`、`FAIL_SAFE_STOP`、`ABORTED` 的合法迁移写成显式状态表。
- 对非法迁移返回显式错误或原因码，不允许静默吞掉状态异常。

### 2. 实现 `rollout_step()`

- 只消费 `CommittedPlan` 与当前世界状态，推进纵向/横向执行过程。
- 禁止在 rollout 中重新选 gap、重新生成 candidate，或修改 `CommittedPlan` 的语义字段。

### 3. 明确等待与降级分支

- 写清 `NO_FEASIBLE_PLAN`、wait、fail-safe、abort 的触发条件、状态副作用和日志/原因码格式。
- 当 ego 已进入 `emergency_tail` 且连续无可行计划时，必须转入 `FAIL_SAFE_STOP` 并最终记一次 abort。

### 4. 补单测

- 覆盖正常 `COMMITTED -> EXECUTING -> POST_MERGE`。
- 覆盖 `NO_FEASIBLE_PLAN` 但未入 `emergency_tail` 时保持 `PLANNING`。
- 覆盖进入 `emergency_tail` 后的 `FAIL_SAFE_STOP -> ABORTED`。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_rollout_and_state_machine.py` 通过。
- `NO_FEASIBLE_PLAN` 在非 `emergency_tail` 条件下不会自动跳到别的隐藏 planner。
- `FAIL_SAFE_STOP` 和 `ABORTED` 触发路径可复盘、有显式原因码。

### 组装验证（产出运行时依赖的 task，可选）

- `T5` 可以基于 rollout 输出直接统计完成率、abort 率和 planned/actual 偏差。
- `T4` 不需要回写 `T2/T3` 文件即可跑通闭环状态推进。

### 环境验证（涉及配置加载的 task，可选）

- fail-safe / abort 只依赖 `ScenarioConfig` 中已冻结的几何和制动参数。
- rollout 时步与 planning/gate 时步仍保持 `0.1s` 一致。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| `CommittedPlan` / `GateResult` | `T3` | commit 协议与字段锁定已稳定 |
| 共享类型与参数 | `T1` | `ExecutionState`、`ScenarioConfig` 等对象可直接消费 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| rollout 后的世界状态 | `T5/T6` | 可统计 planned/actual 偏差、完成率与 abort 率 |
| 状态转移日志 / 原因码 | `T5/T6` | 可用于实验汇总和回归断言 |

### 不要做

- 不要重新生成 candidate、重排 FIFO gap、修改 gate 谓词。
- 不要新增 `DECOMMIT`、多 partition、上游换道、第二波算法分支。
- 不要把 wait/fail-safe 失败静默吞掉。
