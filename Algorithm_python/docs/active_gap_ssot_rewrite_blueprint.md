<!--
Status: draft
Scope: repo-instance
-->

# 主动造 Gap 顶层 SSOT 重写施工图

> 最后更新：`2026-04-07T22:48:56+08:00`
>
> 本文不是新的正式 SSOT，而是本轮重写 `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` 以及后续 `docs/features/active_gap_v1/` 时必须遵守的总路由。

## 1. 这份施工图是什么

它不是单独的一份算法设计稿，而是以下材料之间的“主线路由总表”：

1. `forum/cursor_gap_adjustment_algorithm_discuss.md`
2. `docs/active_gap_minimal_control_design.md`
3. `docs/active_gap_rewrite_mapping.md`
4. `.cursor/plans/主动造gap重构_0c45a69c.plan.md`

它要固定的是：

- 当前问题到底怎么定义
- 四份顶层 SSOT 各自负责什么
- 跨文档必须保持一致的不变量是什么
- feature 层应该怎么拆

## 2. 当前主线问题定义

当前顶层 SSOT 的主问题，必须统一写成下面这句话：

> 当当前 gap 还不满足合流要求时，系统应在未来若干个 `0.1s` tick 内，通过 `TCG=(p,m,s)` 三车协同主动把 gap 做成可行；若当前 tick 还不能正式 merge，则优先执行一段可认证的 gap-opening coordination slice，而不是默认等待。

这意味着旧主线必须退出 SSOT：

- 同一 `x_m` 下找现成 FIFO gap
- 共享 `Step 3` gate 被动验收候选
- 当前 tick 没 merge 解就直接等待自然 gap

新主线必须进入 SSOT：

- `TCG` 三车协同组
- `p/m/s` 三车受控
- `u/f` 作为可选边界预测
- 上层搜索未来 merge target：`(x_m^*, t_m^*, v^*)`
- 当前 tick 无 merge 解时优先找 certified coordination slice
- `SafetyCertificate` 负责整段安全证明

## 3. 跨文档必须保持的总不变量

### 3.1 几何与时间基线

- `ramp_approach_subzone = [0m, 50m)`
- `legal_merge_zone = [50m, 290m]`
- `emergency_tail = [290m, 300m]`
- `fixed_anchor = 170m`
- `planning_tick = 0.1s`
- `rollout_tick = 0.1s`
- `certificate_sampling_dt = 0.1s`
- `T_lc^{MVP} = 3.0s`

### 3.2 对象与顺序语义

- `TCG = (p,m,s)` 是当前核心受控组
- `u/f` 是可选边界车，不是核心受控组成员
- 每个 planning tick 只处理 1 个 active ego 与 1 个 `TCG`

### 3.3 fixed / flexible 统一语义

- `fixed` 与 `flexible` 都绑定 `completion anchor`
- 区别只在 `x_m^*` 的 admissible set
- 绝不能再写成两套不同控制框架

### 3.4 锁定语义

- `COMMITTED`：先锁 `TCG`
- 在同一 `TCG` 下，`MergeTarget`、三车 quintic、`SafetyCertificate`、`RollingPlanSlice` 允许每 tick 刷新
- `EXECUTING`：一旦横向动作开始，锁定当前 target 与 slice 家族，不再允许 re-TCG / re-target

### 3.5 安全验证语义

- 旧 `GateResult` 不再是主对象
- 新主对象是 `SafetyCertificate`
- 主安全函数固定成：`g_up`、`g_pm`、`g_ms`、`g_sf`
- `g_up/g_sf` 只在 `u/f` 存在时启用

### 3.6 当前 tick 无 merge 解时的处理语义

- 第一优先：certified merge slice
- 第二优先：certified gap-opening coordination slice
- 第三优先：`SAFE_WAIT`
- 最后：`FAIL_SAFE_STOP`

### 3.7 A 层验证语义

- `A0` 与 `A1` 共用 `p=11,m=9,s=5` 的三车基准布局
- `A0` 验证主动造 gap 是否真的发生
- `A1` 验证 `fixed/flexible` 差异是否可解释
- `A2` 验证连续三车组 / 连续匝道车时状态残留是否正确
- `A3` 验证物理上真不可行时是否明确失败且 fail-safe
- A0-A3 首版默认不引入 `u/f`

## 4. 四份正式文档各自回答什么问题

### 4.1 `docs/design.md`

负责回答：

- 系统主线是什么
- 当前 tick 的控制分支怎么走
- 状态机和 fail-safe 是什么
- A 层为什么先于大车流

### 4.2 `docs/contracts.md`

负责回答：

- 代码里的共享对象是什么
- `TCG` 怎么定义
- `COMMITTED / EXECUTING` 锁什么
- `merge slice / coordination slice / safe_wait / fail_safe_stop` 在契约里怎么落位

### 4.3 `docs/formulas.md`

负责回答：

- 上层 merge target 怎么搜
- `Δ_open` 怎么定义
- 三车 quintic 怎么写
- coordination slice 的“推进性”怎么定义
- `SafetyCertificate` 四条主安全函数怎么定义

### 4.4 `docs/derivations.md`

负责回答：

- 为什么要从 `TargetPair` 升级到 `TCG`
- 为什么 `p` 也应进入受控集
- 为什么当前 tick 没 merge 解时不能默认等待
- 为什么 A 场景首版不带 `u/f`

## 5. 正式 SSOT 的推荐重写顺序

必须按这个顺序改：

1. `docs/design.md`
2. `docs/contracts.md`
3. `docs/formulas.md`
4. `docs/derivations.md`
5. `docs/features/active_gap_v1/`

原因：

- `design.md` 先把主线换掉
- `contracts.md` 再把对象名和执行语义固定
- `formulas.md` 再写“怎么算”
- `derivations.md` 最后补“为什么”
- feature 包在这些都稳定后再拆任务

## 6. 写作时必须遵守的删改规则

### 6.1 必须保留

- `completion anchor`
- `legal merge zone`
- `single active decision partition`
- `0.1s` rolling
- `FAIL_SAFE_STOP`
- `COMMITTED / EXECUTING` 的双层锁定思想

### 6.2 必须删除或退出主线

- “同一 `x_m` 下找现成 FIFO gap”
- “共享 `Step 3` gate 是主脑”
- “当前时刻没 merge 解就直接等”
- “`first_wave_mvp` 是当前正式主线”

### 6.3 只允许在 archive 层保留

- 旧 `docs/features/first_wave_mvp/` 的任务拆法
- 旧 `CandidatePlan / GateResult / CommittedPlan` 对象体系
- 旧三类大车流实验先于 A 层的验证顺序

## 7. 当前这轮重写完成的判定条件

只有当下面条件同时成立，才算“顶层 SSOT 已切到新主算法”：

- `design.md` 不再把旧 `Step 2 / Step 3` 当主脑
- `contracts.md` 已定义 `TCG / MergeTarget / SafetyCertificate / RollingPlanSlice`
- `contracts.md` 写清 `COMMITTED` 锁 `TCG`、`EXECUTING` 锁 target
- `formulas.md` 已写清 `Δ_open`
- `formulas.md` 已写清三车 quintic 与 coordination slice 推进条件
- `formulas.md` 已写清 `g_up / g_pm / g_ms / g_sf`
- `derivations.md` 已解释为什么当前 tick 没 merge 解时不能默认等待
- 四份文档对 `A0/A1/A2/A3` 的定义完全一致

## 8. 一句话总结

这份施工图的本质是：

> 用一份“跨文档总路由”把问题定义、对象命名、控制分支、公式职责、证明职责和 feature 拆分顺序全部冻结住，确保顶层 SSOT 真正切到“`TCG` 三车协同 + coordination slice + `SafetyCertificate`”的新主算法。
