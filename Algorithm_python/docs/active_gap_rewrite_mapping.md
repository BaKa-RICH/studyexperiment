<!--
Status: draft
Scope: repo-instance
Source: docs/active_gap_minimal_control_design.md
-->

# 主动造 Gap 正式文档回写映射表

> 最后更新：`2026-04-07T22:48:56+08:00`
>
> 本文档不是正式 SSOT，而是一个“回写施工图”。
> 它回答的问题不是“新算法是什么”，而是“如何把主动造 gap 的三车可控版系统地揉回 `README.md`、`docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md`，并落成新的 `docs/features/active_gap_v1/` feature 包；与此同时，把旧 `docs/features/first_wave_mvp/` 明确降级为 baseline / archive”。

## 1. 使用方式

使用顺序固定为：

1. 先读 `docs/active_gap_ssot_rewrite_blueprint.md`
2. 再读 `docs/design.md / contracts.md / formulas.md / derivations.md`
3. 再读本映射表
4. 最后才落到 `docs/features/active_gap_v1/`

原因只有一个：

- 如果顶层 SSOT 还在讲旧 `TargetPair / 双车 quintic / 没解就等`
- 但 feature 层已经开始讲 `TCG / 三车控制 / coordination slice`

那么后续实现者看到的一定还是两套互相冲突的规范。

## 2. 回写总原则

### 2.1 先换顶层 SSOT，再换 feature

回写优先级必须是：

1. `docs/design.md`
2. `docs/contracts.md`
3. `docs/formulas.md`
4. `docs/derivations.md`
5. `README.md`
6. `docs/features/first_wave_mvp/README.md` 的 archive 声明
7. `docs/features/active_gap_v1/README.md`
8. `docs/features/active_gap_v1/design.md`
9. `docs/features/active_gap_v1/T*.md`

### 2.2 旧路径只允许 archive，不允许承载新主线

当前可以暂时保留旧路径：

- `docs/features/first_wave_mvp/`

但它只能保留为 baseline / archive，不能继续承载新主算法语义。也就是说：

- legacy 路径可以暂时不搬目录
- 旧目录内容必须明确声明“只读 baseline，不再代表当前主线”
- 新算法 feature 必须进入新路径：`docs/features/active_gap_v1/`

### 2.3 当前回写后的核心变化

必须统一替换成下面这组新主线：

- `TargetPair` -> `TCG`
- `m/s` 双车受控 -> `p/m/s` 三车受控
- `u/f` 变成可选边界预测
- `g_pm/g_ms/g_sf` -> `g_up/g_pm/g_ms/g_sf`
- “没 merge 解就等” -> “先找 coordination slice，再 safe_wait，再 fail-safe”

### 2.4 A 层场景的收缩原则

A 层微场景应直接进入新 `active_gap_v1` feature 包的主门禁，并采用下面的默认口径：

- 先用 `A0/A1/A2/A3` 验证算法本体
- A0-A3 首版只看 `p/m/s`
- `u/f` 只进入后续边界应力测试，不进入首版 A 场景定义

## 3. 顶层正式文档回写表

### 3.1 `README.md`

`README.md` 只负责：

- 项目当前主线
- 阅读顺序
- `mainline / archive` 关系

应明确改成：

- 当前主线是 `TCG` 三车协同的主动造 gap 算法
- 旧 `first_wave_mvp` 只是 archive / baseline
- 新 feature 施工包在 `docs/features/active_gap_v1/`

### 3.2 `docs/design.md`

`design.md` 必须从旧的被动 `Step 2 / Step 3` 系统设计，重写成：

- `TCG=(p,m,s)` 三车协同
- merge target branch
- coordination slice branch
- `COMMITTED` 锁 `TCG`
- `EXECUTING` 锁 target
- `A0-A3` 先于大车流

必须删除或重写的旧内容：

- “同一 `x_m` 下找现成 FIFO gap”
- “共享 gate 是主脑”
- “当前时刻没解就 safe_wait”

### 3.3 `docs/contracts.md`

`contracts.md` 必须从“候选/验收/提交”的旧对象，切换到：

- `CoordinationSnapshot`
- `TCG`
- `MergeTarget`
- `QuinticLongitudinalProfile`
- `SafetyCertificate`
- `RollingPlanSlice`
- `ExecutionDecision`

并写清：

- `COMMITTED` 锁 `TCG`
- `EXECUTING` 锁 target
- `RollingPlanSlice.slice_kind ∈ {merge, coordination}`

### 3.4 `docs/formulas.md`

`formulas.md` 必须从旧 `Step 2 / Step 3` 公式主体，重写成：

- `p/m/s` 三车状态
- `u/f` 外生预测
- `Δ_open`
- 三车 quintic
- coordination slice 的推进条件
- `g_up / g_pm / g_ms / g_sf`

### 3.5 `docs/derivations.md`

`derivations.md` 不应再为旧 `Step 2 / Step 3` 辩护，而要回答：

- 为什么 `p` 也应进入受控集
- 为什么当前 tick 没 merge 解时不能默认等待
- 为什么 `TCG` 比 `TargetPair` 更合理
- 为什么 A 场景首版不带 `u/f`

## 4. 顶层对象迁移表

| 旧对象/概念 | 新对象/概念 | 迁移说明 |
|---|---|---|
| `PlanningSnapshot` | `CoordinationSnapshot` | 不再只服务旧 `Step 2` |
| `GapRef` | 退出主对象体系 | 当前主线锁 `TCG`，不锁静态 gap |
| `TargetPair` | `TCG` | 从“二元关系”升级成“三车协同组” |
| `CandidatePlan` | `MergeTarget` + `RollingPlanSlice` | 不再先枚举静态 gap candidate |
| `GateResult` | `SafetyCertificate` | 不再只是 pass/fail |
| `CommittedPlan` | `TCG` 锁定 + 当前 slice 刷新 | 保留 `COMMITTED` 思想，但不再锁死整条轨迹 |

## 5. feature 层回写表

### 5.1 旧 `docs/features/first_wave_mvp/`

这套文件不该再被改写成主动造 gap 主算法，而应明确降级为 baseline / archive。

建议处理方式：

- `README.md`：改成 archive 导航与警示说明
- `design.md`、`T*.md`：停止继续注入新算法语义
- 整个目录：可后续迁到 `docs/archive/first_wave_fifo/`

### 5.2 `docs/features/active_gap_v1/README.md`

这个文件负责把顶层 SSOT 翻译成“当前 feature 包怎么读、怎么拆、怎么验收”。

必须写清：

- 当前 feature 是 `TCG` 三车可控版
- `first_wave_mvp` 只是 baseline/archive
- A0-A3 首版只看 `p/m/s`
- `u/f` 作为可选边界压力测试另行引入

### 5.3 `docs/features/active_gap_v1/design.md`

feature `design.md` 的职责是把顶层 SSOT 翻译成可实现的模块落点。

必须写清的数据流：

```text
snapshot
-> tcg
-> merge-target branch
-> if none: coordination-slice branch
-> safety certificate
-> first 0.1s slice
-> rollout
```

## 6. 推荐的新 task 拆分

| 新文件 | 新职责 |
|---|---|
| `T1_tcg_and_snapshot.md` | active ego 选择、`TCG` 识别、快照构造 |
| `T2_merge_target_planner.md` | `fixed/flexible` 统一、merge target 搜索 |
| `T3_tcg_quintic_and_certificate.md` | 三车 quintic、`g_up/g_pm/g_ms/g_sf` 证书 |
| `T4_execution_and_state_machine.md` | merge/coodination slice、`COMMITTED/EXECUTING` 语义、fail-safe |
| `T5_metrics_and_trace.md` | `planned/actual`、trace schema、A 层诊断输出 |
| `T6_micro_scenarios_and_regression.md` | `A0/A1/A2/A3` 微场景、blocking gate、后续大车流恢复门槛 |

## 7. 推荐的实际回写顺序

### Phase 1: 先换顶层 SSOT

1. `docs/design.md`
2. `docs/contracts.md`
3. `docs/formulas.md`
4. `docs/derivations.md`

### Phase 2: 再换项目入口与 archive 边界

5. `README.md`
6. `docs/features/first_wave_mvp/README.md`

### Phase 3: 建立新的 feature 包

7. `docs/features/active_gap_v1/README.md`
8. `docs/features/active_gap_v1/design.md`

### Phase 4: 最后逐个回写新 task

9. `T1_tcg_and_snapshot.md`
10. `T2_merge_target_planner.md`
11. `T3_tcg_quintic_and_certificate.md`
12. `T4_execution_and_state_machine.md`
13. `T5_metrics_and_trace.md`
14. `T6_micro_scenarios_and_regression.md`

## 8. 回写完成后的检查清单

- [ ] `README.md` 不再把旧 `FIFO + gate` 当作项目当前主线
- [ ] `docs/design.md` 已写清 merge branch + coordination slice branch
- [ ] `docs/contracts.md` 已定义 `TCG`
- [ ] `docs/formulas.md` 已写清 `g_up / g_pm / g_ms / g_sf`
- [ ] `docs/derivations.md` 已解释为什么当前 tick 没 merge 解时不能默认等待
- [ ] `docs/features/first_wave_mvp/` 已明确标成 archive / baseline
- [ ] `docs/features/active_gap_v1/` 已建立并与顶层 SSOT 一致
- [ ] `T6_micro_scenarios_and_regression.md` 已把 A0-A3 放在大车流恢复之前

## 9. 一句话结论

这份回写映射表的核心判断是：

- **不是把新稿塞进旧 `first_wave_mvp`**
- **而是把顶层真源与后续 feature 拆分一起切到 `TCG` 三车可控 + coordination slice + `SafetyCertificate` 这条新主线**
