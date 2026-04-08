<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/design.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 主动造 Gap 单匝道数值验证设计

> **所有开发 agent 必读此文档。** 本文档是当前主算法的顶层 SSOT，负责定义系统主线、运行时闭环、状态机和验证策略。
>
> 最后更新：`2026-04-08T16:00:00+08:00`
>
> 当前设计已升级为：`p/m/s` 三车受控、`u/f` 可选边界预测、`TCG` 三车协同组、`g_up/g_pm/g_ms/g_sf` 四条主安全证书、以及“先协调、再等待、最后 fail-safe”的滚动控制语义。

---

## 1. 背景与主线切换

旧 `first_wave_mvp` 的主线本质上是：

`snapshot -> Step 2 候选生成 -> Step 3 共享 gate -> commit -> rollout`

这条链只能回答：

- 当前有没有现成可插入 gap

但无法回答：

- 如果当前 gap 不够，能否通过未来若干个 `0.1s` tick 的协同控制，把 gap 主动调成可行

因此，当前顶层 SSOT 不再把问题定义成“找现成 gap”，而是重新定义成：

1. 识别当前局部三车协同组 `TCG = (p,m,s)`
2. 先尝试规划未来 merge target
3. 若当前还不能正式 merge，则优先执行“继续造 gap”的短时协调控制
4. 对整段控制轨迹出具 `SafetyCertificate`

## 2. 当前范围与不做项

### 2.1 当前范围

本轮顶层 SSOT 只覆盖最小可落地版本：

- 单主线 + 单匝道
- 单 `active decision partition`
- 每个 planning tick 只处理 1 辆 active ramp CAV
- 核心受控车：`p / m / s`
- 可选边界预测车：`u / f`
- 上层规划未来 merge target：`(x_m^*, t_m^*, v^*)`
- 若 merge target 不可认证，则回退到 gap-opening coordination slice
- 下层对 `p/m/s` 求三车 quintic 纵向轨迹
- 横向保留模板化执行映射，不做 full 2D 联合优化
- 每 tick 只提交第一段 `0.1s` control slice
- 用 `SafetyCertificate` 替代旧 gate 主叙事

### 2.2 当前不做项

本轮明确不进入正式主线的内容包括：

- CBF / QP
- 多个 `active decision partition`
- 多匝道、多冲突区
- 上游换道
- 全局联合优化
- 第二波的 `simple DP`

### 2.3 baseline 与 archive 的关系

- 顶层 `docs/*.md` 代表当前主算法真源
- 旧 `docs/features/first_wave_mvp/` 只保留 baseline / archive 角色
- 新 feature 包后续进入 `docs/features/active_gap_v1/`

## 3. 几何、对象与冻结语义

### 3.1 几何冻结

当前几何与时间基线冻结为：

- `ramp_approach_subzone = [0m, 50m)`
- `legal_merge_zone = [50m, 290m]`
- `emergency_tail = [290m, 300m]`
- `fixed_anchor = 170m`
- `planning_tick = 0.1s`
- `rollout_tick = 0.1s`
- `certificate_sampling_dt = 0.1s`
- `T_lc^{MVP} = 3.0s`

其中：

- `x = 290m` 仍视为 `legal_merge_zone` 的最后一个合法 completion anchor
- `x > 290m` 才进入 `emergency_tail`

### 3.2 对象定义

每个 planning tick 只处理一个 `TCG`：

- `p`：匝道车合流后的主路前车，受控车
- `m`：当前匝道合流车，受控车
- `s`：匝道车合流后的主路辅助车，受控车
- `u`：`p` 前方的边界车，只做预测与安全检查
- `f`：`s` 后方的边界车，只做预测与安全检查

这里最关键的变化是：

- 旧体系里前后车只是被动 gap 身份
- 当前体系里 `p/m/s` 共同参与造 gap
- `u/f` 只在存在时才进入边界安全证书

### 3.3 completion anchor 统一语义

当前统一把 merge point 的物理语义冻结成 **completion anchor** `x_m^*`。

这意味着：

- `fixed` 固定的是 `x_m^* = x_fix`
- `flexible` 搜索的是 `x_m^*` 在 `legal_merge_zone` 内的可行集合
- 开始变道时刻与开始变道位置由 `x_m^*` 和 `T_lc(v)` 反推
- `fixed` 与 `flexible` 不是两套不同控制器，只是 admissible set 不同

### 3.4 FIFO 新语义

当前仍保留 FIFO，但 FIFO 的含义变成：

- 先识别未来合流拓扑中的三车协同组 `TCG = (p,m,s)`
- 之后允许通过控制 `p/m/s` 去实现这个顺序下的未来合流
- 不允许在同一 tick 内把 `m` 改插到别的三车组

因此，现在锁的是：

- `TCG`

而不是：

- 当前自然出现的某个静态 gap

## 4. 两层控制架构

### 4.1 主对象链

当前主线按下面这组对象推进：

1. `CoordinationSnapshot`
2. `TCG`
3. `MergeTarget`
4. `QuinticLongitudinalProfile`
5. `SafetyCertificate`
6. `RollingPlanSlice`

每个对象只回答一个问题：

- `CoordinationSnapshot`：本 tick 看到的世界是什么
- `TCG`：当前要服务的三车协同组是谁
- `MergeTarget`：未来何处、何时、何速完成合流
- `QuinticLongitudinalProfile`：`p/m/s` 怎样纵向运动到目标
- `SafetyCertificate`：整段过程是否安全、最紧约束是什么
- `RollingPlanSlice`：这一 tick 真正允许执行的短时间片段是什么

### 4.2 上层：merge target 规划

上层每个 tick 都优先解同一类问题：

- `x_m^*`：未来 completion anchor
- `t_m^*`：未来完成并入时刻
- `v^*`：完成并入时三车共同目标速度

上层不是在问：

- “当前有没有现成 gap”

而是在问：

- “能否让 `p/m/s` 在未来 horizon 内协同运动，并在 `x_m^*, t_m^*` 处形成可认证的 merge 条件”

### 4.3 下层：三车 quintic 协同

下层对 `p`、`m`、`s` 分别求闭式 quintic 纵向轨迹，并满足：

- 起点 `(x,v,a)` 对齐当前状态
- 终点 `(x,v,a)` 对齐上层目标与终端安全约束
- 动力学边界满足速度、加速度限制

### 4.4 `SafetyCertificate`

当前主线要求对整段轨迹出具 `SafetyCertificate`，并至少检查：

- `g_up`
- `g_pm`
- `g_ms`
- `g_sf`

其中：

- `g_up` 只在 `u` 存在时启用
- `g_sf` 只在 `f` 存在时启用

### 4.5 当前 tick 算不出 merge 时怎么办

当前正式语义不是“没解就等”，而是按下面的优先级：

1. 先找 **certified merge slice**
2. 若没有，再找 **certified gap-opening coordination slice**
3. 若还没有，但继续等待 `0.1s` 仍安全，则 `SAFE_WAIT`
4. 若连等待都不安全，则 `FAIL_SAFE_STOP`

也就是说：

- 第一优先不是“等”
- 第一优先是继续造 gap

## 5. 运行时主循环

当前推荐的唯一装配链是：

```text
observe snapshot
-> choose active ego m
-> identify TCG (p, m, s) with optional boundaries (u, f)
-> try certified merge slice
-> if none: try certified gap-opening coordination slice
-> if none: safe_wait or fail_safe_stop
-> rollout one tick
-> next planning tick
```

### 5.1 `PLANNING`

- 尚未找到可认证的控制片段
- 允许重新识别 active ego 与 `TCG`
- 允许重新搜索 merge target
- 允许尝试 gap-opening coordination slice

### 5.2 `COMMITTED`

- 已找到第一个可认证控制片段
- `TCG` 被锁定
- 在同一 `TCG` 下，`MergeTarget`、三车 quintic、`SafetyCertificate`、`RollingPlanSlice` 允许每 tick 刷新
- 这种刷新不是 `DECOMMIT`

### 5.3 `EXECUTING`

- 一旦横向动作开始，当前 target 与 slice 家族被锁定
- 不再允许 re-TCG
- 不再允许 post-lc retarget
- 若后续常规重算失败，只允许在同一 `TCG` 上求应急 continuation

### 5.4 不允许的隐藏逻辑

- gate 内部顺手改 `x_m^*` / `t_m^*`
- rollout 中静默切换到另一个 `TCG`
- lane change 已开始后重新解释顺序
- 失败后跳到未记录的“备用 planner”

## 6. 状态机与 fail-safe

### 6.1 执行状态

当前正式状态机冻结为：

- `APPROACHING`
- `PLANNING`
- `COMMITTED`
- `EXECUTING`
- `POST_MERGE`
- `FAIL_SAFE_STOP`
- `ABORTED`

### 6.2 状态语义

| 状态 | 含义 | 允许的关键动作 |
|---|---|---|
| `APPROACHING` | 进入控制区前或刚进入控制区 | 纯观测与基础推进 |
| `PLANNING` | 正在为当前 ego 搜索可认证控制片段 | 识别 `TCG`、搜索 target、构建证书 |
| `COMMITTED` | 已锁定 `TCG`，slice 可滚动刷新 | 每 tick 刷新局部计划 |
| `EXECUTING` | 横向动作已开始，target 已锁定 | 只允许同 `TCG` continuation |
| `POST_MERGE` | 已完成并入后的短时保护段 | 常规跟驰与统计 |
| `FAIL_SAFE_STOP` | 无法安全继续规划或执行 | 最大允许制动、保持本车道 |
| `ABORTED` | fail-safe 已终止本次合流任务 | 只记录结果，不再尝试本次合流 |

### 6.3 无解处理

若当前 tick 上：

- 所有 merge slice 候选都失败
- 且所有 coordination slice 候选也失败

则输出：

- `NO_FEASIBLE_CERTIFIED_SLICE`

如果 `m` 仍在安全等待区，则：

- 保持 `PLANNING`
- 执行 `SAFE_WAIT`
- 下一 tick 继续重算

### 6.4 末端 fail-safe

若连续多个 tick 无可认证 slice，且：

- `m` 已逼近 `emergency_tail`
- 或剩余可用距离已不足以完成最小横向动作

则进入：

- `FAIL_SAFE_STOP`

执行要求：

- 匝道车最大允许制动
- 保持本车道
- 明确记录一次 `ABORTED`

### 6.5 完整状态转移表

| 当前状态 | 触发条件 | 下一状态 | 备注 |
|---|---|---|---|
| `APPROACHING` | ego 进入 control zone 并满足 planning 触发条件 | `PLANNING` | |
| `PLANNING` | 存在 certified merge slice 或 certified coordination slice | `COMMITTED` | |
| `PLANNING` | 当前 tick 无任何 certified slice，且仍可安全等待 | `PLANNING` | `SAFE_WAIT` |
| `PLANNING` | 当前 tick 无任何 certified slice，且 ego 已逼近 `emergency_tail` | `FAIL_SAFE_STOP` | |
| `COMMITTED` | 找到 certified merge slice 且横向动作开始 | `EXECUTING` | `MergeTarget` 被锁定 |
| `COMMITTED` | 当前 tick 无 certified slice，但仍可安全等待 | `COMMITTED` | 保持 TCG 锁定，继续尝试 |
| `COMMITTED` | 连续多 tick 无 certified slice，且 ego 逼近 `emergency_tail` | `FAIL_SAFE_STOP` | TCG 锁定失效 |
| `COMMITTED` | TCG 成员离开 control zone 导致 TCG 物理无效 | `FAIL_SAFE_STOP` | TCG 不可恢复 |
| `EXECUTING` | ego 完成并入并通过 `post_merge_guard` | `POST_MERGE` | |
| `EXECUTING` | 常规重算失败，应急 continuation 也失败 | `FAIL_SAFE_STOP` | 最大制动、保持本车道 |
| `POST_MERGE` | `post_merge_guard_s` 时间结束且 ego 稳定 | 终态（本次合流任务结束） | 下一辆 active ego 进入新的 `APPROACHING` |
| `FAIL_SAFE_STOP` | 车辆完成最大制动停车 | `ABORTED` | 记录 abort 原因 |

## 7. 验证策略

### 7.1 验证层次

当前验证层固定为 5 层：

- `L1`：公式与参数正确性
- `L2`：单 tick 的 `TCG` 识别、slice 搜索、证书验证
- `L3`：滚动闭环执行与 planned/actual 对齐
- `L4`：A 层微场景
- `L5`：更大流量、多 seed、消融实验

执行顺序必须是：

- 先过 `L1-L4`
- 再恢复 `L5`

### 7.2 A 层微场景

当前 A 层的原则是：

- 先只看 `p/m/s` 核心三车关系
- `u/f` 默认缺省，不进入 A0-A1 的首版定义
- 只有后续边界应力测试才单独引入 `u/f`

| 场景 | 布局 | 目标 |
|---|---|---|
| `A0` | 主路 `p=11,s=5`；匝道 `m=9`；`v_0=16.7 m/s` 同速起步 | 验证三车主动造 gap 是否真的发生 |
| `A1` | 与 `A0` 同布局；`v_0=16.7 m/s` 同速起步 | 比较 `fixed/flexible` 差异是否可解释 |
| `A2` | 主路 `p=11,s=5`；匝道 `c=1,m=9`；同速起步 | 验证连续三车组 / 连续匝道车时状态残留 |
| `A3` | 主路 `p=11,s=5`；匝道 `m=10.5`；同速起步 | 验证物理上真不可行时是否明确失败并进入 fail-safe |

### 7.2.1 首版场景收缩

A 层首版只冻结 A0 与 A1。A2 与 A3 保留定义但降级为后续扩展：

- **A2 前置条件**：需先定义匝道后车 `c` 在 `m` 的 coordination 阶段的行为约束（IDM 跟驰/常速/其他）以及 `c-m` 安全距离保证机制。当前 `SafetyCertificate` 四条安全函数不覆盖 `c-m` pair。
- **A3 前置条件**：需先补充完整的可达性数值论证，证明在当前冻结参数（`a_max=2.6, b_safe=4.5`）下，布局 `p=11, m=10.5, s=5` 确实不可行。初步审阅的粗略可达性估算表明该布局可能是可行的。

首版只过 A0+A1 门禁后，方可进入大车流恢复与后续场景扩展。

### 7.3 大车流与门禁

大车流、多 seed、渗透率/协同范围消融仍然重要，但不再是第一入口。

顺序必须改成：

1. 先确认 `A0/A1` 首版门禁通过，并完成 `A2/A3` 扩展前置条件评审
2. 再恢复轻负荷、中高负荷和消融实验
3. 最后再做多 seed 门禁与更大规模对照

## 8. 保留项与淘汰项

### 8.1 仍然保留的旧语义

- `completion anchor`
- `legal_merge_zone`
- `single active decision partition`
- `0.1s` rolling
- `FAIL_SAFE_STOP`
- `COMMITTED / EXECUTING` 的锁定思想

### 8.2 必须退出顶层主线的旧叙事

- “同一 `x_m` 下找现成 FIFO gap”
- “共享 `Step 3` gate 是系统主脑”
- “无候选时继续等待自然 gap”
- “旧 `first_wave_mvp` 是当前正式主线”

## 9. 其它正式文档各自承担什么

- `docs/contracts.md`
  负责定义 `CoordinationSnapshot`、`TCG`、`MergeTarget`、`SafetyCertificate`、`RollingPlanSlice` 以及字段锁定规则。
- `docs/formulas.md`
  负责定义状态、预测、`Δ_open`、三车 quintic、横向映射和安全证书公式。
- `docs/derivations.md`
  负责解释为什么要从“找现成 gap”切换到“规划未来 merge target + coordination slice”，以及为什么当前锁定语义和公式定义合理。

## 10. 一句话结论

当前顶层 SSOT 已经不再把“被动找 gap”视为主算法，而是把：

- **上层未来 merge target 规划**
- **无 merge 解时优先执行 gap-opening coordination slice**
- **下层 `p/m/s` 三车纵向协同**
- **整段 `SafetyCertificate` 验证**
- **first-slice rolling execution**

冻结为正式主线。
