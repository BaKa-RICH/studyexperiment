<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T4: Execution 与状态机（Execution, Coordination Branch, and State Machine）

> 最后更新：`2026-04-08T17:00:00+08:00`

## 前置条件

- `T1_tcg_and_snapshot` 已完成。
- `T2_merge_target_planner` 已完成。
- `T3_tcg_quintic_and_certificate` 已完成。
- 必读：`docs/design.md`（重点看 “当前 tick 算不出 merge 时怎么办”“运行时主循环”“状态机与 fail-safe”）。
- 必读：`docs/contracts.md`（重点看 `ExecutionState`、`SliceKind`、`RollingPlanSlice`、`ExecutionDecision`）。
- 必读：`docs/features/active_gap_v1/design.md` 的状态流转与运行时规则。

## 目标

把当前算法主线真正装起来：实现 merge branch、coordination branch、`SAFE_WAIT`、`FAIL_SAFE_STOP` 与状态机，让系统在不 hidden re-TCG、不 post-lc retarget 的前提下，正确处理当前 tick 无 merge 解时的短时协调控制。

## Targets

1. **执行分支显式化**: merge slice、coordination slice、`SAFE_WAIT`、`FAIL_SAFE_STOP` 都有独立入口与显式原因码。
2. **状态流转可复盘**: `APPROACHING -> PLANNING -> COMMITTED/EXECUTING/POST_MERGE/FAIL_SAFE_STOP/ABORTED` 被写成可实现、可测试的转移规则。
3. **当前 tick 不会直接回旧逻辑**: 无 merge 解时优先走 coordination branch，而不是直接等待。
4. **Rollout 不越界**: `rollout_step()` 只消费当前状态与 `RollingPlanSlice`，不重入 target 搜索层。

## Acceptance Criteria

### Step 1: 固化执行状态流转（depends on Step 4 of T3）

- [ ] `APPROACHING`、`PLANNING`、`COMMITTED`、`EXECUTING`、`POST_MERGE`、`FAIL_SAFE_STOP`、`ABORTED` 的合法转移被显式写清（参照 `docs/design.md` §6.5 完整转移表）。
- [ ] 非法转移返回显式错误或原因码，而不是静默忽略。
- [ ] `COMMITTED -> EXECUTING -> POST_MERGE` 主链可被独立验证。
- [ ] `COMMITTED` 状态下增加 TCG 有效性持续检查：如果 `p/m/s` 中任一车辆离开 `control_zone`（纵坐标超出 `[0, control_zone_length_m]`），则判定 TCG 不可恢复，转入 `FAIL_SAFE_STOP`。
- [ ] `POST_MERGE` 状态在 `post_merge_guard_s`（1.0s）结束后退出为终态，本次合流任务结束。

### Step 2: 实现 merge / coordination 双分支（depends on Step 1）

- [ ] 先遍历 `MergeTarget` 列表尝试 certified merge slice（遇到第一个证书通过的就提交，不要只试 rank #1）。
- [ ] merge 全部失败后才尝试 certified coordination slice。
- [ ] coordination slice 只有在能降低 `Δ_open` 或速度错配且证书通过时才可提交。
- [ ] coordination 连续 tick 上限：同一 `TCG` 下连续 coordination slice 不超过 `N_coord_max = 50` 个 tick（即 5.0s）。超过后强制进入 `SAFE_WAIT`。
- [ ] coordination 最小改善阈值：`Δ_open` 或 `Δ_v` 至少下降 `ε_progress = 0.01`，否则视为无效推进，进入 `SAFE_WAIT`。
- [ ] 当前 tick 无 merge 解时，不会直接跳到 `SAFE_WAIT`。

### Step 3: 实现等待与 fail-safe 分支（depends on Step 2）

- [ ] merge branch 与 coordination branch 都没有认证片段时，且仍可安全等待，系统保持 `PLANNING`（或 `COMMITTED`）并输出 `SAFE_WAIT`。
- [ ] ego 进入 `emergency_tail` 且持续无认证片段时，会进入 `FAIL_SAFE_STOP` 并最终记录 `ABORTED`。
- [ ] wait / fail-safe / abort 的状态副作用和原因码格式被固定。
- [ ] `EXECUTING` 期间常规重算失败时的应急 continuation 规则：
  - 应急 continuation 只允许在同一 `TCG` + 同一 `MergeTarget` 下生成，不允许 re-TCG 或 retarget。
  - 与常规重算的差异：应急 continuation 可以放宽终端加速度约束（允许 `a_f ≠ 0`），但速度和安全约束不放宽。
  - 连续应急 continuation 失败上限：最多 `N_emergency_max = 3` 个 tick。超过后转入 `FAIL_SAFE_STOP`。

### Step 4: 验证 rollout 闭环（depends on Step 3）

- [ ] `rollout_step()` 只消费 `RollingPlanSlice` 与当前世界状态，不会改写 `TCG` 或 `MergeTarget` 语义字段。
- [ ] 正常路径与失败路径都有单测覆盖。
- [ ] `pytest tests/active_gap_v1/test_execution_and_state_machine.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法执行层与状态机的正式 spec
  - `docs/design.md` — merge/coordination 两分支、状态机、wait/fail-safe 主线
  - `docs/contracts.md` — `ExecutionState`、`SliceKind`、`RollingPlanSlice`、`ExecutionDecision`
  - `docs/features/active_gap_v1/design.md` — feature 级状态流转表和运行时规则

### Docs:

**Formal Specs:**

- `docs/design.md`: 当前 tick 无 merge 解时优先 coordination branch
- `docs/contracts.md`: `ExecutionState`、`SliceKind`、`RollingPlanSlice`

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: `WP-4` 的执行说明与风险
- `docs/features/active_gap_v1/design.md`: `T3/T4` 边界与状态表

### Developer insights:

- **T4 决定行为像不像“主动造 gap”**: 即使上层和证书都对，如果这里退回“默认等待”，算法还是会变回旧逻辑。
- **Rollout 只消费，不重规划**: `T4` 不能在 rollout 中偷跑 `T2/T3`。
- **coordination slice 是主链，不是补丁**: 它必须成为显式分支和显式对象，而不是“等待的另一种说法”。
- **状态表优先**: 先把合法/非法转移写清，再实现运行逻辑，避免状态回环。
- **target 锁定后不能再漂移**: `EXECUTING` 后不允许 hidden re-TCG 或 post-lc retarget。
- **TCG 有效性必须持续检查**: `COMMITTED` 状态下，如果 `p/m/s` 中任一车辆离开 control zone，TCG 不可恢复，必须 fail-safe。不要假设锁定后 TCG 永远有效。
- **coordination 必须有收敛保证**: 连续 coordination tick 有上限（`N_coord_max=50`），无效推进（改善 < `ε_progress=0.01`）必须终止。否则系统会在 emergency tail 前一直微量推进。
- **应急 continuation ≠ 常规重算**: 应急模式可放宽终端加速度（允许 `a_f ≠ 0`），但不允许放宽安全和速度约束，且最多持续 3 tick。
- **遍历候选而非只试最优**: merge branch 应遍历 `MergeTarget` 列表直到找到第一个证书通过的，不要只试 rank #1（T1-T3 验证发现 rank #1 经常动力学违规）。

### Editable Paths

- `src/active_gap_v1/executor.py` — merge/coordination 分支和 rollout
- `src/active_gap_v1/state_machine.py` — 状态流转表与非法转移处理
- `tests/active_gap_v1/test_execution_and_state_machine.py` — 正常/失败路径测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **先协调再等待**: 当前 tick 无 merge 解时，必须先尝试 coordination branch。
- **不要回到搜索层**: rollout 不得重新生成 `MergeTarget` 或重新识别 `TCG`。
- **失败必须有原因码**: `SAFE_WAIT`、`FAIL_SAFE_STOP`、`ABORTED` 的副作用必须可追踪。
- **NO_FEASIBLE_CERTIFIED_SLICE 是 planner 结果，不是证书失败**: 当 merge branch 和 coordination branch 都未通过认证时，状态机应输出 `SAFE_WAIT` 或 `FAIL_SAFE_STOP`，不得在 `CertificateFailureKind` 枚举中混入此标志。

## Skills

### Open URL

用于核对 `docs/design.md` 与 `docs/contracts.md` 中的状态语义和失败分支口径。

### Code Exploration

用于检查 `executor.py` / `state_machine.py` 是否只消费 `RollingPlanSlice` 与当前世界状态。

### Parallel Subagent

仅在后续需要并行审查状态流转与日志断言时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固化状态流转表（Step 1, depends on Phase 4 of T3）

- [ ] 1.1 写清合法转移和非法转移处理（对照 design.md §6.5）
- [ ] 1.2 固定 `COMMITTED -> EXECUTING -> POST_MERGE` 主链
- [ ] 1.3 实现 `COMMITTED` 下 TCG 有效性持续检查
- [ ] 1.4 实现 `POST_MERGE` 退出条件（`post_merge_guard_s` 后终态）

### Phase 2: 落 merge / coordination 双分支（Step 2, depends on Phase 1）

- [ ] 2.1 实现 merge slice 分支（遍历候选，非只试 rank #1）
- [ ] 2.2 实现 coordination slice 分支及其推进性检查
- [ ] 2.3 实现 coordination 收敛保证（`N_coord_max=50`, `ε_progress=0.01`）

### Phase 3: 落等待与 fail-safe（Step 3, depends on Phase 2）

- [ ] 3.1 实现 `SAFE_WAIT`
- [ ] 3.2 实现 `FAIL_SAFE_STOP -> ABORTED`
- [ ] 3.3 实现 `EXECUTING` 应急 continuation（`N_emergency_max=3`）

### Phase 4: 完成闭环测试（Step 4, depends on Phase 3）

- [ ] 4.1 为正常路径、失败路径、TCG 失效、coordination 上限、应急上限补测试
- [ ] 4.2 验证 rollout 不会修改 `TCG` / `MergeTarget` 的语义字段

## 你负责的文件（白名单）

```text
src/active_gap_v1/executor.py
src/active_gap_v1/state_machine.py
tests/active_gap_v1/test_execution_and_state_machine.py
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/types.py`、`config.py`、`snapshot.py`、`tcg_selector.py`（由 `T1` 负责）
- `src/active_gap_v1/predictor.py`、`merge_target_planner.py`（由 `T2` 负责）
- `src/active_gap_v1/quintic.py`、`certificate.py`（由 `T3` 负责）
- `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/*`（由 `T5/T6` 负责）
- 顶层 `docs/`（正式真源，不在本 task 内回写）

## 依赖的现有代码（需要先读的文件）

- `src/active_gap_v1/types.py`
- `src/active_gap_v1/merge_target_planner.py`
- `src/active_gap_v1/quintic.py`
- `src/active_gap_v1/certificate.py`
- `docs/design.md`
- `docs/contracts.md`

## 实现步骤

### 1. 固化状态流转表

- 把 `APPROACHING`、`PLANNING`、`COMMITTED`、`EXECUTING`、`POST_MERGE`、`FAIL_SAFE_STOP`、`ABORTED` 的合法迁移写成显式状态表（对照 `docs/design.md` §6.5）。
- 对非法迁移返回显式错误或原因码，不允许静默吞掉状态异常。
- 在 `COMMITTED` 状态的每 tick 入口处检查 TCG 有效性：如果 `p/m/s` 中任一车辆 `x_pos_m` 超出 `[0, control_zone_length_m]`，则判定 TCG 不可恢复，转入 `FAIL_SAFE_STOP`。
- `POST_MERGE` 在 `post_merge_guard_s`（1.0s = 10 tick）结束后退出为终态。

### 2. 实现 merge branch

- **遍历** `MergeTarget` 列表（按 ranking_key 排序），对每个候选调用 `solve_tcg_quintics()` + `build_safety_certificate()`，遇到第一个 `failure_kind is None` 的就提交。不要只试 rank #1。
- merge slice 存在时，提交第一个 `0.1s` 执行片段。

### 3. 实现 coordination branch

- merge branch 全部候选都无解时，再尝试 coordination branch。
- coordination slice 必须能证明：当前 tick 虽不能 merge，但在继续减小 `Δ_open` 或速度错配。
- 收敛保证：
  - 同一 `TCG` 下连续 coordination slice 不超过 `N_coord_max = 50` tick（5.0s）。
  - `Δ_open` 或 `Δ_v` 每 tick 至少下降 `ε_progress = 0.01`，否则视为无效推进。
  - 超出上限或无效推进时，终止 coordination，进入 `SAFE_WAIT`。

### 4. 明确等待与降级分支

- 只有在 merge branch 和 coordination branch 都失败时，才允许 `SAFE_WAIT`。
- 当 ego 已进入 `emergency_tail` 且连续无任何认证片段时，必须转入 `FAIL_SAFE_STOP` 并最终记一次 abort。
- `EXECUTING` 期间应急 continuation 规则：
  - 只在同一 `TCG` + 同一 `MergeTarget` 下生成。
  - 可放宽终端加速度约束（`a_f ≠ 0`），但安全和速度约束不放宽。
  - 最多连续 `N_emergency_max = 3` tick。超过后转入 `FAIL_SAFE_STOP`。

### 5. 补单测

- 覆盖正常 `COMMITTED -> EXECUTING -> POST_MERGE`。
- 覆盖 merge 失败但 coordination 成功。
- 覆盖 merge 和 coordination 都失败但仍可等待。
- 覆盖进入 `emergency_tail` 后的 `FAIL_SAFE_STOP -> ABORTED`。
- 覆盖 `COMMITTED` 下 TCG 成员离开 control zone → `FAIL_SAFE_STOP`。
- 覆盖 coordination 连续 50 tick 上限触发 `SAFE_WAIT`。
- 覆盖 `EXECUTING` 应急 continuation 连续 3 tick 失败 → `FAIL_SAFE_STOP`。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_execution_and_state_machine.py` 通过。
- 当前 tick 无 merge 解时，不会直接默认等待。
- `SAFE_WAIT`、`FAIL_SAFE_STOP` 和 `ABORTED` 触发路径可复盘、有显式原因码。

### 组装验证（产出运行时依赖的 task，可选）

- `T5` 可以基于 rollout 输出直接统计 slice 类型、完成率、abort 率和 planned/actual 偏差。
- `T4` 不需要回写 `T1-T3` 文件即可跑通闭环状态推进。

### 环境验证（涉及配置加载的 task，可选）

- fail-safe / abort 只依赖 `ScenarioConfig` 中已冻结的几何和制动参数。
- rollout 时步与 planning/certificate 时步仍保持 `0.1s` 一致。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| `MergeTarget`、三车轨迹、`SafetyCertificate` | `T2/T3` | 已稳定可直接消费 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `RollingPlanSlice` | `T5/T6` | merge / coordination / wait / fail-safe 语义稳定 |
| rollout 后的世界状态 | `T5/T6` | 可统计 planned/actual 偏差、完成率与 abort 率 |

### 不要做

- 不要重新生成 `MergeTarget`、重识别 `TCG` 或修改证书规则。
- 不要把 coordination branch 降级成“等待的别名”。
- 不要在 `EXECUTING` 后 hidden re-TCG 或 post-lc retarget。
