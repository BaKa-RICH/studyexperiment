<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T3: 共享 Acceptance Gate 与 Commit 协议 (Acceptance Gate and Commit Protocol)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- `T1_shared_types_and_config` 已完成。
- `T2_snapshot_and_step2` 已完成。
- 必读：`docs/design.md`（重点看 “Step 3：共享 Acceptance Gate”“Commit、等待与 Fail-Safe”）。
- 必读：`docs/contracts.md`（重点看 `GateResult`、`CommittedPlan`、字段锁定规则、`NO_FEASIBLE_PLAN` 协议）。
- 必读：`docs/formulas.md`（重点看 gate 谓词和 `REJECT(reason)` 口径）。

## 目标

实现第一波 MVP 的共享验收门与 commit 协议：`accept_candidate()` 只能返回 `GateResult`，`commit_candidate()` 只能锁定语义字段，不允许 `Step 3` 变成 hidden replanner。

## Targets

1. **共享 Gate 可复盘**: 所有 `REJECT(reason)` 都有清晰谓词来源，且对 `FIFO fixed/flexible` 共用一套验收门。
2. **Commit 语义已锁定**: `commit_candidate()` 只在 `accepted=True` 时工作，并严格锁定第一波语义字段。
3. **职责边界不漂移**: `T3` 不实现 wait、fail-safe、abort 或任何 hidden replanner / `DECOMMIT` 逻辑。

## Acceptance Criteria

### Step 1: 实现共享 Gate 谓词（no dependencies — start here）

- [ ] `accept_candidate()` 只消费 `snapshot` 与 `candidate`，不会修改 `x_m`、`t_m`、gap 或 `partner_ids`。
- [ ] `REJECT_ZONE` 到 `REJECT_PARTNER_INVALID` 的失败映射完整、可追溯。
- [ ] 同一输入重复运行时 `GateResult` 保持一致。

### Step 2: 固化 Commit 协议（depends on Step 1）

- [ ] `commit_candidate()` 只接受 `accepted=True` 的 `GateResult`。
- [ ] `PLANNING -> COMMITTED` 的合法转移和非法转移处理被显式写清。
- [ ] `COMMITTED` 后只锁定 spec 规定的语义字段，不锁无关派生缓存。

### Step 3: 验证非法转移与禁止项（depends on Step 2）

- [ ] gate 失败不会自动改候选或回退到另一个隐藏方案。
- [ ] `DECOMMIT` 和第二波软解锁能力没有被提前实现。
- [ ] `pytest tests/first_wave_mvp/test_acceptance_gate_and_commit.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波 Step 3 的正式 spec 与实现目录
  - `docs/design.md` — Step 3、commit、wait 与 fail-safe 的职责边界
  - `docs/contracts.md` — `GateResult`、`CommittedPlan`、字段锁定规则
  - `docs/formulas.md` — gate 谓词与 `REJECT(reason)` 口径

### Docs:

**Formal Specs:**

- `docs/design.md`: `Step 3` 只做共享验收，不是重规划器
- `docs/contracts.md`: `GateResult` / `CommittedPlan` 和 `NO_FEASIBLE_PLAN` 协议
- `docs/formulas.md`: zone / timing / gap / interval / post / dyn / partner 谓词

**Feature Package:**

- `docs/features/first_wave_mvp/design.md`: `T3/T4` 状态切口与状态流转表
- `docs/features/first_wave_mvp/README.md`: `WP-3` 的执行范围和 Done-when

### Developer insights:

- **纯验收原则**: `Step 3` 必须消费 `T2` 的排序结果，而不是重新组织候选。
- **字段锁定原则**: `COMMITTED` 锁的是语义字段，不是所有派生缓存。
- **非法转移要显式失败**: 不能通过静默回退掩盖错误状态。
- **NO_FEASIBLE_PLAN 不属于 T3**: 它是 planner 结果，等待与 fail-safe 由 `T4` 负责。
- **禁止第二波能力**: `DECOMMIT`、软解锁和 hidden replanner 都不在第一波范围内。

### Editable Paths

- `src/first_wave_mvp/gate.py` — 共享 gate 谓词和 `GateResult`
- `src/first_wave_mvp/commit.py` — commit 协议和字段锁定
- `tests/first_wave_mvp/test_acceptance_gate_and_commit.py` — gate/commit 边界测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **纯验收，不改方案**: `accept_candidate()` 绝不修改候选语义字段。
- **Commit 锁语义，不锁缓存**: 只锁 spec 冻结的语义字段，派生缓存允许重算。
- **禁止软解锁**: `DECOMMIT` 与任何 hidden replanner 都必须留在黑名单中。

## Skills

### Open URL

用于核对 `docs/design.md`、`docs/contracts.md` 和 `docs/formulas.md` 中对 Step 3 的正式定义。

### Code Exploration

用于比对 `gate.py` / `commit.py` 与 `CandidatePlan`、`GateResult`、`CommittedPlan` 的字段边界。

### Parallel Subagent

仅在后续需要并行审查 gate 谓词实现和状态锁定测试时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 落共享 Gate 谓词（Step 1, depends on Phase 3 of T2）

- [ ] 1.1 实现共享 gate 谓词与 `REJECT(reason)` 映射
- [ ] 1.2 保证 gate 只消费 snapshot/candidate，不改写候选语义字段

### Phase 2: 落 Commit 协议（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `commit_candidate()` 与 `accepted=True` 约束
- [ ] 2.2 写清合法转移、非法转移和 `COMMITTED` 字段锁定

### Phase 3: 完成边界测试（Step 3, depends on Phase 2）

- [ ] 3.1 为 ACCEPT / REJECT、非法转移和字段锁定补测试
- [ ] 3.2 验证 `DECOMMIT` / hidden replanner 未被引入

## 你负责的文件（白名单）

```text
src/first_wave_mvp/gate.py
src/first_wave_mvp/commit.py
tests/first_wave_mvp/test_acceptance_gate_and_commit.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py`（由 `T1` 负责）
- `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py`（由 `T4` 负责）
- `experiments/first_wave_mvp/*.py`、`src/first_wave_mvp/metrics.py`（由 `T5/T6` 负责）
- 所有与 `DECOMMIT`、第二波算法相关的文件和字段

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/types.py`
- `src/first_wave_mvp/config.py`
- `src/first_wave_mvp/snapshot.py`
- `src/first_wave_mvp/step2_fifo.py`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`

## 实现步骤

### 1. 实现共享 gate 谓词

- 依次落 `REJECT_ZONE`、`REJECT_TIMING`、`REJECT_GAP_IDENTITY`、`REJECT_INTERVAL_SAFETY`、`REJECT_POST_MERGE_SAFETY`、`REJECT_DYNAMIC_LIMIT`、`REJECT_PARTNER_INVALID`。
- `accept_candidate()` 只消费 `snapshot` 与 `candidate`，绝不修改 `x_m`、`t_m`、目标 gap 或 `partner_ids`。

### 2. 固化 commit 协议

- `commit_candidate()` 只接受 `accepted=True` 的 `GateResult`。
- 明确 `PLANNING -> COMMITTED` 的合法转移，以及非法转移时的显式错误/返回状态。
- `COMMITTED` 后只锁 `ego_id`、gap 身份、`x_m_m`、`t_m_s`、`partner_ids`、`sequence_relation` 等语义字段。

### 3. 写清非法转移与禁止项

- 显式禁止 `DECOMMIT`、禁止在 `T3` 内做 hidden replanner、禁止在 gate 失败时自动改候选。
- `NO_FEASIBLE_PLAN` 是 planner 结果，不是 `RejectReason`；本 task 只负责 gate/commit，不负责等待与 fail-safe 副作用。

### 4. 补单测

- 覆盖 ACCEPT / REJECT、字段锁定、非法 commit、非法状态转移和 hidden replanner 禁令。
- 验证被拒候选不会改变 `CandidatePlan` 的语义字段。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_acceptance_gate_and_commit.py` 通过。
- 任一 `REJECT(reason)` 都有确定的失败谓词映射。
- 被拒候选在进入和退出 `accept_candidate()` 后，其 `x_m_m`、`t_m_s`、`target_gap`、`partner_ids` 保持不变。

### 组装验证（产出运行时依赖的 task，可选）

- `T4` 可直接消费 `CommittedPlan`，无需回写 `T2` 的候选生成逻辑。
- `commit_candidate()` 对非法转移返回显式错误，而不是静默降级到别的状态。

### 环境验证（涉及配置加载的 task，可选）

- gate 只依赖 `snapshot`、`candidate` 与 `ScenarioConfig`，不读取外部隐式配置。
- 不存在随机行为；同一输入得到相同 `GateResult`。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 排序后的候选列表 | `T2` | `objective_key`、`candidate_id` 已稳定可复现 |
| 共享类型与参数 | `T1` | `GateResult`、`CommittedPlan` 等对象已稳定 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `GateResult` | `T4/T5/T6` | 验收结果可复盘、可统计 |
| `CommittedPlan` | `T4/T5/T6` | 语义字段锁定规则稳定，不被 rollout 回写 |

### 不要做

- 不要实现 `rollout_step()`、`NO_FEASIBLE_PLAN` 等待副作用、fail-safe 或 abort。
- 不要新增 `DECOMMIT` 或任何软解锁能力。
- 不要在 gate 失败时自动改 `x_m`、改 gap、改 `t_m`、改 `partner_ids`。
