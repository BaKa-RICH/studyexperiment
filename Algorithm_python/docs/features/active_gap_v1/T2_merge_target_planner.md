<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T2: Merge Target Planner（Merge Target Planning and Ranking）

> 最后更新：`2026-04-08T00:19:40+08:00`

## 前置条件

- `T1_tcg_and_snapshot` 已完成。
- 必读：`docs/design.md`（重点看 “merge target 规划”“当前 tick 算不出 merge 时怎么办”）。
- 必读：`docs/contracts.md`（重点看 `TCG`、`MergeTarget` 和 Planning Cycle 协议）。
- 必读：`docs/formulas.md`（重点看 `fixed/flexible` 统一、终端安全距离、`Δ_open`、可行域与字典序目标）。
- 必读：`docs/features/active_gap_v1/design.md`。

## 目标

实现当前主算法的上层 merge target 搜索：在给定 `TCG=(p,m,s)` 和可选边界 `u/f` 的情况下，统一支持 `fixed/flexible` 两种 `AnchorMode`，稳定输出可重复、可解释、可直接被 `T3` 消费的 `MergeTarget` 列表。

## Targets

1. **merge target 搜索稳定**: `fixed/flexible` 使用同一套搜索框架，只在 `x_m^*` 的 admissible set 上不同。
2. **排序规则可复盘**: `Δ_open / Δ_coop / Δ_delay / ρ_min` 的计算与字典序排序结果稳定可重复。
3. **失败分类清晰**: 能区分几何不可行、终端不可达、速度越界和 ranking tie-break，不把失败原因留到 `T3` 再猜。
4. **可直接驱动后续模块**: 输出的 `MergeTarget` 能被 `T3` 直接消费，无需回写 `T1` 或重建 `TCG`。

## Acceptance Criteria

### Step 1: 固定 `fixed/flexible` 的统一搜索框架（depends on Step 4 of T1）

- [ ] `fixed` 与 `flexible` 共用一套 target 搜索函数，而不是两套不同 planner。
- [ ] `fixed` 只在 `x_m^* = x_fix` 处搜索；`flexible` 只改变 `x_m^*` 的 admissible set。
- [ ] 搜索输入只依赖 `CoordinationSnapshot` 与 `TCG`，不会偷偷回到旧 gap candidate 语义。

### Step 2: 实现目标可行域、终端约束与 `Δ_open`（depends on Step 1）

- [ ] 能计算 `x_p^*`、`x_s^*`、`Δ_open`、`Δ_coop`、`Δ_delay`、`ρ_min`。
- [ ] 能显式检查时间可行、几何可行、速度可行和终端 reachability。
- [ ] A0/A1 首版下，`u/f` 缺省为空不会阻止 merge target 搜索。

### Step 3: 固化字典序排序与失败分类（depends on Step 2）

- [ ] `ranking_key = (t_m^*, Δ_coop, Δ_delay, -ρ_min, x_m^*)` 被稳定实现。
- [ ] 同一输入至少重复运行 3 次，target 列表顺序完全一致。
- [ ] 失败原因可追溯到具体可行域检查，而不是返回模糊“无解”。

### Step 4: 完成单测与可消费性验证（depends on Step 3）

- [ ] `pytest tests/active_gap_v1/test_merge_target_planner.py` 通过。
- [ ] `T3` 可以直接消费 `MergeTarget`，无需重新解释 `fixed/flexible`、`Δ_open` 或排序规则。
- [ ] A1 可以直接比较 `fixed/flexible` 的输出差异。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法上层规划的正式 spec 与实现目录
  - `docs/design.md` — merge target 主线和 coordination branch 优先级
  - `docs/contracts.md` — `TCG`、`MergeTarget`、Planning Cycle 协议
  - `docs/formulas.md` — `fixed/flexible`、`Δ_open`、终端约束和字典序目标
  - `docs/features/active_gap_v1/design.md` — 当前 feature 的模块切口和数据流

### Docs:

**Formal Specs:**

- `docs/design.md`: 上层 merge target 规划与两分支控制
- `docs/contracts.md`: `MergeTarget` 字段和 Planning Cycle 协议
- `docs/formulas.md`: `Δ_open`、`Δ_coop`、`Δ_delay`、`ρ_min`、admissible set 与排序规则

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: 执行顺序与工作包
- `docs/features/active_gap_v1/design.md`: `T1 -> T2 -> T3` 的主链关系

### Developer insights:

- **上层只定终点**: `T2` 只负责 `(x_m^*, t_m^*, v^*)`，不在这里求轨迹。
- **固定与灵活统一**: `fixed/flexible` 的差别只能体现在 `x_m^*` 的 admissible set，不能演化成两套逻辑。
- **Δ_open 是主信号**: 当前主算法是否真的在“主动造 gap”，首先要看 `Δ_open` 是否被正确定义并可被后续降低。
- **确定性优先**: target 枚举、排序和 tie-break 的稳定性直接决定后续 A 层可回归性。
- **失败分类前移**: 终端不可达、几何越界、速度越界要在 `T2` 内就明确，不要把本该在上层暴露的问题推给 `T3`。

### Editable Paths

- `src/active_gap_v1/predictor.py` — `u/f` 外生预测
- `src/active_gap_v1/merge_target_planner.py` — merge target 搜索与排序
- `tests/active_gap_v1/test_merge_target_planner.py` — 上层规划正确性测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **上层不求轨迹**: 不要在 `T2` 中提前生成 quintic。
- **确定性优先**: target 列表顺序和 ranking key 必须可重复。
- **首版不强依赖 u/f**: `u/f` 只能作为可选边界输入，不得阻塞 A0/A1 的 merge target 规划。

## Skills

### Open URL

用于打开 formal spec 与 feature 设计文档，逐条核对 `MergeTarget` 的定义、约束和排序口径。

### Code Exploration

用于检查 `merge_target_planner.py` 与 `docs/contracts.md` / `docs/formulas.md` 的对象映射。

### Parallel Subagent

仅在后续需要并行核对排序逻辑和测试夹具时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固定搜索输入与 admissible set（Step 1, depends on Phase 4 of T1）

- [ ] 1.1 明确 `CoordinationSnapshot + TCG` 是唯一输入
- [ ] 1.2 固定 `fixed/flexible` 的统一搜索框架

### Phase 2: 落 target 约束与排序字段（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `x_p^*`、`x_s^*`、`Δ_open`、`Δ_coop`、`Δ_delay`、`ρ_min`
- [ ] 2.2 实现时间、几何、速度、reachability 的可行域检查

### Phase 3: 固化排序与失败分类（Step 3, depends on Phase 2）

- [ ] 3.1 固定 `ranking_key`
- [ ] 3.2 为失败分类和稳定排序补测试

### Phase 4: 完成可消费性验证（Step 4, depends on Phase 3）

- [ ] 4.1 验证 `T3` 可直接消费 `MergeTarget`
- [ ] 4.2 验证 A1 可直接比较 `fixed/flexible`

## 你负责的文件（白名单）

```text
src/active_gap_v1/predictor.py
src/active_gap_v1/merge_target_planner.py
tests/active_gap_v1/test_merge_target_planner.py
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/types.py`、`src/active_gap_v1/config.py`、`src/active_gap_v1/snapshot.py`、`src/active_gap_v1/tcg_selector.py`（由 `T1` 负责）
- `src/active_gap_v1/quintic.py`、`src/active_gap_v1/certificate.py`（由 `T3` 负责）
- `src/active_gap_v1/executor.py`、`src/active_gap_v1/state_machine.py`（由 `T4` 负责）
- `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/*`（由 `T5/T6` 负责）
- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`（正式真源，不在本 task 内改写）

## 依赖的现有代码（需要先读的文件）

- `src/active_gap_v1/types.py`
- `src/active_gap_v1/config.py`
- `src/active_gap_v1/snapshot.py`
- `src/active_gap_v1/tcg_selector.py`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`

## 实现步骤

### 1. 固定 merge target 搜索输入

- 输入必须是 `CoordinationSnapshot + TCG`。
- 不要回到旧 `GapRef` 或静态 gap candidate 语义。

### 2. 实现邻车外生预测

- 在 `predictor.py` 中实现 `u/f` 的常速或常加速度预测。
- 明确 `u/f` 缺省为空时的返回约定，保证后续逻辑不分叉崩坏。

### 3. 实现 merge target 搜索

- 对 `fixed` 只搜索固定 `x_m^*`。
- 对 `flexible` 在 legal merge zone 内搜索 `x_m^*`。
- 枚举 `H`、`v^*` 并计算 `x_p^*`、`x_s^*`、`Δ_open` 等字段。

### 4. 实现排序与失败分类

- 按 `ranking_key` 做稳定排序。
- 对几何、速度、终端 reachability 等失败路径做显式分类。
- 不要让“无解”吞掉所有前置失败原因。

### 5. 补单测

- 覆盖 `fixed/flexible`、`Δ_open`、稳定排序、无 `u/f` 输入、失败分类和重复运行一致性。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_merge_target_planner.py` 通过。
- `fixed/flexible` 只在 admissible set 上不同，不会走成两套不同逻辑。
- 相同输入重复运行至少 3 次，target 列表顺序与 `ranking_key` 保持一致。
- `u/f` 缺省时，A0/A1 首版仍能正常规划 merge target。

### 组装验证（产出运行时依赖的 task，可选）

- `T3` 可以直接消费 `MergeTarget`，无需重建 `TCG` 或重解释排序规则。
- `A1` 中 `fixed/flexible` 的差异可直接由 `MergeTarget` 输出比较。

### 环境验证（涉及配置加载的 task，可选）

- `fixed` / `flexible` 两种 `AnchorMode` 都能使用同一 `ScenarioConfig` 与同一时间离散运行。
- 邻车预测只依赖 spec 已冻结参数，不读取额外环境配置。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| `CoordinationSnapshot` / `TCG` | `T1` | 字段稳定，可直接消费 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| 排序后的 `MergeTarget` 列表 | `T3/T4/T6` | 排序、字段和失败分类稳定可复盘 |
| `predictor.py` | `T3/T4` | `u/f` 外生预测口径稳定 |

### 不要做

- 不要生成 quintic、证书或 execution 决策。
- 不要把 coordination slice 逻辑塞进 merge target 搜索。
- 不要让 `u/f` 从“可选边界”变成 A 层首版的强依赖。
