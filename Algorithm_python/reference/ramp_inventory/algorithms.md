# 算法清单

> 来源：`forum/xiangmu_qianyi.json` 的 Step-1 / Step-2 收敛结果
>
> 最后更新：`2026-04-05T17:16:21+08:00`

## 总览

当前 `ramp/` 里的主策略可以先按 4 类顶层 policy 理解：

- `POL-NC`：`no_control`，空控制基线。
- `POL-FIFO`：FIFO 合流排序策略。
- `POL-DP`：纯 CAV 双流 DP。
- `POL-HIER`：分层策略，内部再拆成上游换道、混合 DP、合流点管理等子模块。

这 4 类策略的统一编排入口是 `ramp/experiments/run.py`。主链路是：

1. `StateCollector` / `HierarchicalStateCollector` 采集 SUMO 状态。
2. `policies/*/scheduler.py` 生成 `Plan`。
3. `policies/*/command_builder.py` 把 `Plan` 转成 `ControlCommand`。
4. `runtime/controller.py` 通过 TraCI 下发速度和换道命令。

对迁移到纯数值验证最有价值的，主要是第 2 层的调度内核与第 3 层里可被保留的决策映射；最需要切断的是第 1 层和第 4 层的 SUMO 运行时耦合。

## 顶层策略

| ID | 名称 | 主要入口 | 关键依赖 | 现有 tests | evidence_level | confidence | updated_at |
|----|------|----------|----------|------------|----------------|------------|------------|
| `POL-NC` | `no_control` 基线 | `ramp/policies/no_control/scheduler.py`、`ramp/policies/no_control/command_builder.py` | 不生成实质控制；返回空命令 | 未见专属单测 | `A-code` | `medium` | `2026-03-30T23:19:18+08:00` |
| `POL-FIFO` | FIFO 合流排序 | `ramp/policies/fifo/scheduler.py`、`ramp/policies/fifo/command_builder.py` | 依赖 `entry_order`、`fifo_target_time`、`fifo_natural_eta` 等采集字段 | 未见专属调度或命令构建单测 | `A-code` | `medium` | `2026-03-30T23:19:18+08:00` |
| `POL-DP` | 纯 CAV 双流 DP | `ramp/policies/dp/scheduler.py`、`ramp/policies/dp/command_builder.py` | 依赖 `ramp/scheduler/dp.py` 与 `ramp/scheduler/arrival_time.py` | `ramp/tests/test_dp_schedule.py` | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `POL-HIER` | 分层策略 | `ramp/policies/hierarchical/scheduler.py`、`ramp/policies/hierarchical/command_builder.py` | 依赖 `MOD-ZA`、`MOD-DPMIX`、`MOD-MP` 与扩展状态采集 | `ramp/tests/test_hierarchical_scheduler.py`（偏构造/参数） | `A-code` | `medium` | `2026-03-30T23:19:18+08:00` |

## 关键子模块

| ID | 名称 | 角色 | 代码入口 | 说明 | evidence_level | confidence | updated_at |
|----|------|------|----------|------|----------------|------------|------------|
| `MOD-ZA` | Zone A 上游换道疏散 | `POL-HIER` 子模块 | `ramp/policies/hierarchical/zone_a.py` | 负责上游不对称换道与疏散，强依赖车道与边名 | `A-code` | `medium` | `2026-03-30T23:19:18+08:00` |
| `MOD-DPMIX` | 混合 CAV/HDV DP | `POL-HIER` 子模块 | `ramp/scheduler/dp_mixed.py` | 用于混合交通下的时序决策 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `MOD-MP` | MergePointManager | `POL-HIER` 子模块 | `ramp/policies/hierarchical/merge_point.py` | 负责 fixed / flexible 合流点搜索与状态机 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `MOD-ARRIVAL` | 到达时间闭式计算 | `POL-DP` / `MOD-DPMIX` 支撑模块 | `ramp/scheduler/arrival_time.py` | 纯数值逻辑，可优先迁移 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |

## fixed / flexible 的定位

目前确认：

- `fixed` / `flexible` 不是两套顶层策略。
- 它们是 `POL-HIER` 内部的 `merge_policy` 分支。
- 当前实现差异主要落在 `MergePointParams.search_start_pos_m` 的设置，而不是完全不同的一套合流点算法。

这件事后续在 `evidence_and_gaps.md` 里会作为 `GAP-FIXED-SEMANTICS` 跟踪，因为它影响“基线”应该如何命名。

## 提炼后的新仓库 MVP 算法口径

这一节不是在描述旧 `ramp/` 代码“已经如何实现”，而是在归档：旧系统盘点完成后，当前任务已经确认的新仓库算法口径。

### `DEC-MVP-BASELINES`

- `no_control` 不再作为核心 baseline，只保留为参考下界。
- 首批 baseline 冻结为：
  - `FIFO + fixed anchor`
  - `FIFO + flexible anchor`
- 这样做的目的是先把 `completion anchor` 语义、FIFO 顺序语义和共享验收门闭环跑通，再决定是否把简单 `DP` 提升到第一波实现。

### `DEC-ACTIVE-PARTITION`

- MVP 只允许 1 个 `active decision partition`。
- 它服务 1 辆 ramp CAV，而不是同时服务多个匝道车。
- 它包含：
  - 当前正在求解的 ramp CAV
  - 目标 gap 的前车 `p`
  - 目标 gap 的后车 `f`
  - 必要时最多再加 1 辆协同 CAV

这一定义的价值在于先把“局部决策单元”说清楚，而不是一开始就做全局多车联合优化。

### `DEC-STEP2-STEP3-SPLIT`

- `Step 2` 负责生成与排序候选。
- `Step 3` 负责共享 feasibility checker 与 acceptance gate。
- `Step 3` 绝不修改 `Step 2` 的方案；若被拒绝，只能试下一个候选，或者输出 `NO_FEASIBLE_PLAN`。

这条边界是对旧系统里“planner 和兜底修补混在一起”的反向提炼。

### `DEC-FIFO-ANCHOR-SEMANTICS`

- 新仓库中的 `fixed / flexible` 统一绑定 `completion anchor` `x_m`，而不是开始变道点。
- `fixed anchor` 当前冻结为 `X_fixed = {170}`。
- `flexible anchor` 当前冻结为整数枚举：
  \[
  X_{flex} = \{x_m \in \mathbb{Z} \mid \lceil x_{lb}(v_r) \rceil \le x_m \le 290\}
  \]
- 其中 `x_lb(v_r)` 来自 lane-change 纵向扫掠距离约束，即 `50 + \Delta x_{lc}(v_r)`。

### `DEC-FIFO-CANDIDATE-GENERATION`

当前已经确认的 FIFO 候选生成口径是：

1. 每个 planning tick 只处理“匝道最靠前、且未 `COMMITTED/EXECUTING` 的 ramp CAV”。
2. 对每个 `x_m` 先计算 ramp 车的自由完成时刻 `t_r^free(x_m)`。
3. 再把 `t_r^free(x_m)` 插入目标车道有序对象的到达时刻序列，导出该 `x_m` 下唯一的 FIFO gap。
4. 这里的目标车道有序对象不仅包含主路车，也包含已经 `COMMITTED`、会在目标车道形成先后约束的已锁定对象。
5. FIFO 的语义冻结为“按自由到达优先级排队”，不在同一 `x_m` 下向后回退搜更晚 gap。

对应的粗时间窗是：

\[
L(x_m)=\max(t_r^{free}(x_m), t_p(x_m)+h_{pr}), \quad U(x_m)=t_f(x_m)-h_{rf}
\]

仅当 `L \le U` 时生成候选，并取 `t_m = L`。

### `DEC-CANDIDATE-ORDER`

当前冻结的候选排序目标采用字典序：

1. 最小化 `t_m`
2. 最小化 `\Delta delay = t_m - t_r^{free}(x_m)`
3. 最小化 `x_m`

这样做是为了避免 `flexible` 因仅优化相对延迟而系统性偏向更下游的 anchor。

## 运行时强耦合模块

这些模块不是“算法内核”，但当前又深度参与决策执行。迁移成纯数值验证时，需要优先切断或替换：

| ID | 模块 | 代码入口 | 强耦合点 | confidence |
|----|------|----------|----------|------------|
| `RT-SIM` | 仿真驱动 | `ramp/runtime/simulation_driver.py` | `traci.start`、`simulationStep`、`close` 生命周期 | `high` |
| `RT-SC` | 常规状态采集 | `ramp/runtime/state_collector.py` | 依赖 route、edge、lane、driving distance 等 TraCI 查询 | `high` |
| `RT-HSC` | 分层扩展状态采集 | `ramp/policies/hierarchical/state_collector_ext.py` | 依赖 `main_h2`、`main_h3_1` 等硬编码路网名；存在静默异常路径 | `high` |
| `RT-CTRL` | 控制下发 | `ramp/runtime/controller.py` | 依赖 `setSpeed`、`slowDown`、`changeLane`；强绑定 `main_h3_0`、`:n_merge` 等语义 | `high` |

## 现有测试覆盖盘点

只记录“现有覆盖在哪里”，不对测试质量做推断。

| 覆盖对象 | 相关 tests | 当前判断 |
|----------|------------|----------|
| `POL-DP` 与 `MOD-ARRIVAL` | `ramp/tests/test_dp_schedule.py` | 内核覆盖较清晰 |
| `MOD-DPMIX` | `ramp/tests/test_dp_mixed.py` | 混合 DP 纯逻辑已覆盖 |
| `MOD-MP` | `ramp/tests/test_merge_point.py` | 合流点纯逻辑已覆盖 |
| `POL-HIER` | `ramp/tests/test_hierarchical_scheduler.py` | 主要覆盖构造与 fixed/flexible 参数，不是完整行为测试 |
| 指标与辅助模块 | `test_ttc.py`、`test_takeover.py`、`test_pain_score.py`、`test_evidence_chain.py`、`test_summarize_metrics.py`、`test_vehicle_defs.py` | 辅助指标与实验支持模块已有若干覆盖 |
| `POL-FIFO`、`POL-NC`、`RT-CTRL`、`run.py` | 未见专属单测 | 当前是明显测试缺口 |

## 迁移优先级建议

如果下一轮要开始抽离纯数值验证，建议先按下面的顺序理解代码，而不是直接照搬目录：

1. 优先抽 `MOD-ARRIVAL`、`ramp/scheduler/dp.py`、`MOD-DPMIX`、`MOD-MP` 这类纯逻辑内核。
2. 再抽 `POL-DP` 与 `POL-HIER` 中“如何拼装内核”的调度层。
3. 最后再决定 `command_builder` 里哪些是策略语义，哪些只是 TraCI 执行适配。

如果目标变成“先做新仓库的数值验证 MVP”，则当前优先级还应再补一层：

1. 先实现 `FIFO + fixed anchor` 与 `FIFO + flexible anchor`。
2. 先共享同一套 `Step 3` acceptance gate。
3. 再把简单 `DP` 与两层分层算法接到同一 I/O 契约上。

这里只是整理现状，不代表最终迁移方案已经定稿。

## 当前高风险点

- `RT-HSC` 存在静默异常吞掉的路径，可能让 Zone A / Zone C 数据缺失但不显式失败。
- `POL-HIER` 的完整行为高度依赖 TraCI 获取加速度、车道车辆列表，当前缺少端到端自动化验证。
- `POL-FIFO` 与 `POL-NC` 虽然实现看起来简单，但几乎没有专属自动化测试，迁移后容易误改。
