# `Algorithm_python` 文档导航

> 适用范围：`/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python`
>
> 最后更新：`2026-04-08T00:04:03+08:00`

## 一句话理解

这个仓库当前的正式主线，已经不是旧的 `FIFO + Step2 + gate` baseline，而是：

**`TCG=(p,m,s)` 三车可控的主动造 gap 数值验证仓库。**

如果你只记一件事，就记下面这条阅读顺序：

`README.md -> docs/design.md -> docs/contracts.md -> docs/formulas.md -> docs/derivations.md -> docs/features/active_gap_v1/`

## 当前状态

当前已经完成的不是代码实现，而是：

- 顶层正式 SSOT 已切到新主算法
- `docs/features/active_gap_v1/` 施工包已建立
- 旧 `docs/features/first_wave_mvp/` 已降级为 archive / baseline 入口

当前主算法的关键语义是：

- `TCG=(p,m,s)`：三车协同组
- `u/f`：可选边界预测车，不是 A 层首版的必要参与者
- 优先搜索 certified merge slice
- 若当前 tick 还不能 merge，则优先搜索 certified coordination slice
- 只有在两者都没有时，才 `SAFE_WAIT` 或 `FAIL_SAFE_STOP`

## 当前主线做什么

当前正式主线只覆盖最小可落地版本：

- 单主线 + 单匝道
- 单 `active decision partition`
- 每个 planning tick 只处理 1 辆 active ramp CAV
- `p/m/s` 三车受控
- `u/f` 作为可选边界预测
- 上层搜索 future merge target：`(x_m^*, t_m^*, v^*)`
- 下层对 `p/m/s` 求三车 quintic 纵向轨迹
- 主安全证书固定成：`g_up / g_pm / g_ms / g_sf`
- 当前 tick 没 merge 解时，先走 coordination slice 分支
- A0-A3 首版默认只看 `p/m/s`

## 当前主线不做什么

本轮明确不进入正式主线的内容包括：

- CBF / QP
- 多个 `active decision partition`
- 上游换道
- 多匝道、多冲突区
- 全局联合优化
- 第二波 `simple DP`

## 文档分层

这批文档不要“从上到下全读一遍”，而要按层看。

| 层级 | 路径 | 作用 | 什么时候读 |
|---|---|---|---|
| `L0` | `README.md` | 项目入口、阅读顺序、`mainline / archive` 导航 | 每次新开窗口先读 |
| `L1` | `docs/design.md` | 当前主算法的系统主线、运行时闭环、状态机、A 层优先验证 | 想知道“系统到底是什么”时读 |
| `L1` | `docs/contracts.md` | 共享对象、模块边界、字段锁定规则 | 想开始搭代码骨架时必读 |
| `L1` | `docs/formulas.md` | merge target、三车 quintic、coordination slice、证书公式、默认参数 | 想实现算法逻辑时读 |
| `L1` | `docs/derivations.md` | 为什么这样定义、为什么不能回退到旧主线 | 对结构/公式有疑问时读 |
| `L2` | `docs/features/active_gap_v1/` | 当前主算法的 feature 施工包与任务拆分 | 准备进入实现时读 |
| `L2` | `docs/active_gap_ssot_rewrite_blueprint.md` | 顶层 SSOT 重写总路由 | 想检查跨文档一致性时读 |
| `L2` | `docs/active_gap_rewrite_mapping.md` | 顶层文档与 feature 施工的回写映射 | 想继续扩展文档体系时读 |
| `L2` | `docs/active_gap_minimal_control_design.md` | 当前主算法的草案源稿 / 控制基线草图 | 想看完整草案叙事时读 |
| `L2` | `reference/ramp_inventory/README.md` | 旧 `ramp` 系统盘点总览 | 想追溯旧系统来源时读 |
| `L3` | `docs/features/first_wave_mvp/` | 旧 baseline / archive，不再代表当前主线 | 只在做对照或清点旧任务时读 |
| `L3` | `forum/` | 过程讨论归档 | 只有需要追溯对话过程时再读 |

这里最重要的原则是：

- `docs/` 是当前正式真源
- `docs/features/active_gap_v1/` 是当前主算法施工入口
- `docs/features/first_wave_mvp/` 是 archive / baseline
- `reference/ramp_inventory/` 是旧系统证据层
- `forum/` 是过程层

## 推荐阅读路径

### 1. 我只想 5 分钟知道这个项目现在在干什么

按这个顺序读：

1. `README.md`
2. `docs/design.md`
3. `docs/contracts.md` 的 `核心数据模型`、`字段锁定规则`、`Planning Cycle 协议`

读完后你应该能回答：

- 当前主算法是不是 `TCG` 三车可控
- 当前 tick 没 merge 解时会不会直接等待
- 代码骨架大概要围绕哪些对象搭

### 2. 我准备开始搭当前主算法代码骨架

按这个顺序读：

1. `docs/design.md`
2. `docs/contracts.md`
3. `docs/formulas.md`
4. `docs/derivations.md`
5. `docs/features/active_gap_v1/README.md`
6. `docs/features/active_gap_v1/design.md`

其中：

- `design.md` 回答“系统边界和闭环怎么走”
- `contracts.md` 回答“代码里先定义哪些对象”
- `formulas.md` 回答“merge target、三车轨迹、coordination slice、证书怎么算”
- `derivations.md` 回答“为什么这么写不是拍脑袋”
- `active_gap_v1` 回答“具体任务怎么拆”

### 3. 我想看当前草案是怎么一步步长成正式 SSOT 的

按这个顺序读：

1. `docs/active_gap_minimal_control_design.md`
2. `docs/active_gap_ssot_rewrite_blueprint.md`
3. `docs/active_gap_rewrite_mapping.md`

### 4. 我想查旧系统证据，不想直接看代码

按这个顺序读：

1. `reference/ramp_inventory/README.md`
2. `reference/ramp_inventory/algorithms.md`
3. `reference/ramp_inventory/scenarios_and_experiments.md`
4. `reference/ramp_inventory/evidence_and_gaps.md`

### 5. 我想看旧 baseline，而不是当前主算法

按这个顺序读：

1. `docs/features/first_wave_mvp/README.md`
2. `docs/features/first_wave_mvp/design.md`
3. 相关 `T*.md`

但要记住：

- 它们只代表旧 baseline / archive
- 不再代表当前正式主线

## 每份正式文档回答什么问题

### `docs/design.md`

这份文档主要回答：

- 当前主算法的主线是什么
- `TCG`、`COMMITTED`、`EXECUTING`、coordination slice 分别是什么意思
- merge branch / coordination branch / wait / fail-safe 怎么切换
- A0-A3 为什么先于大车流

### `docs/contracts.md`

这份文档主要回答：

- `CoordinationSnapshot`、`TCG`、`MergeTarget`、`SafetyCertificate`、`RollingPlanSlice` 应该长什么样
- `COMMITTED` 后锁什么
- `EXECUTING` 后锁什么
- 模块之间怎么传对象

### `docs/formulas.md`

这份文档主要回答：

- `x_m^*` 的可行域怎么定义
- `fixed / flexible` 怎么统一
- `Δ_open` 怎么算
- 三车 quintic 怎么写
- coordination slice 的推进条件怎么定义
- `g_up / g_pm / g_ms / g_sf` 怎么检查

### `docs/derivations.md`

这份文档主要回答：

- 为什么现在要从“找现成 gap”切到“规划未来 merge target”
- 为什么对象从 `TargetPair` 升级到 `TCG`
- 为什么 `p` 也进入受控集
- 为什么当前 tick 没 merge 解时不能默认等待
- 为什么 A 场景首版不带 `u/f`

## 当前最值得优先关心的文件

如果你只想保留一个最小阅读集，那就是：

1. `docs/design.md`
2. `docs/contracts.md`
3. `docs/formulas.md`
4. `docs/features/active_gap_v1/README.md`

其中：

- `design.md` 告诉你做什么
- `contracts.md` 告诉你对象长什么样
- `formulas.md` 告诉你怎么算
- `active_gap_v1/README.md` 告诉你怎么落实现

## 后续如何继续演化

当前最自然的继续方向是：

1. 保持顶层 SSOT 稳定
2. 继续细化 `docs/features/active_gap_v1/`
3. 再进入 `src/active_gap_v1/` 的实现

如果后续文档继续变多，可以再演化成两层入口：

- `README.md`：项目入口
- `docs/README.md`：只负责 `docs/` 目录内的正式 spec 导航

但在当前阶段，一个入口更清楚。
