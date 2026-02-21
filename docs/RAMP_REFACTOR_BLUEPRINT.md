# RAMP 重构蓝图（讨论版）

目标：只围绕 `ramp/`，把现有的“仿真推进 + 状态采集 + 调度 + 控制 + 记录/指标”梳理成清晰模块边界，方便你接下来读代码、定位问题、扩展算法（先聚焦 `fifo/dp`，不超前做 Stage 3 的大系统）。

本蓝图不会立刻改代码；它是“要怎么拆、拆完接口长什么样、哪些输出/指标要补”的共识文档。

---

## 0. 现状快照（当前实现在哪里）

### 0.1 入口与运行闭环
- 入口：`python -m ramp.experiments.run`（文件 `ramp/experiments/run.py`）
- 场景：`ramp/scenarios/<scenario>/<scenario>.sumocfg`
- 车流：`ramp/scenarios/<scenario>/<scenario>.rou.xml`
- 路网：`ramp/scenarios/<scenario>/<scenario>.net.xml`

### 0.2 算法实现位置
- `fifo`：主要逻辑在 `ramp/experiments/run.py`（入控制区时冻结 `target_cross_time`）
- `dp`：调度核心在 `ramp/scheduler/dp.py`，`t_min` 在 `ramp/scheduler/arrival_time.py`，接入与执行在 `ramp/experiments/run.py`

### 0.3 输出目录（已调整）
- 默认输出：`output/<scenario>/<policy>/`（同 policy 覆盖；不同 policy 不覆盖）
- 文件：`control_zone_trace.csv`、`plans.csv`、`metrics.json`、`config.json`、`collisions.csv`

---

## 1. 现阶段暴露的问题（我们要用重构解决什么）

### 1.1 “FIFO 看起来不 FIFO”
结论：当前 `fifo` 的“计划 FIFO”（按入控制区先后）与“实际过 merge 顺序”不保证一致。

根因（设计层面，不是 bug）：
- SUMO 路口优先级/让行规则可能覆盖 `setSpeed` 的意图（主线优先于匝道：`main` priority=2，`ramp` priority=1）
- `setSpeed` 只能给期望速度，无法赋予通行权；被迫让行会让“计划第一的车”实际卡住很久
- `fifo` 目标时刻在入区时冻结，后续不重排

因此需要补“计划-执行一致性指标”和更清晰的日志，避免只靠 GUI 肉眼判断。

### 1.2 DP 每步重算导致计划抖动
现状：`dp` 每步重算会让 `target_cross_time` 经常变化，执行层在追逐移动目标，吞吐可能被拉低。

讨论结论：保持 `step-length=0.1s`，但把 `dp` 的 **replan interval 扩展到 0.5s**（控制仍每步下发）。

### 1.3 run.py 过于臃肿
`ramp/experiments/run.py` 同时承担了：
- 仿真驱动（start/step/close）
- 状态采集（TraCI -> dict）
- 策略逻辑（fifo/dp/no_control）
- 控制下发（setSpeed）
- 记录与指标（CSV/JSON）

这会导致你后续深入时“读一段代码就跨 5 个概念”，调试也很难对齐“计划/命令/实际”。

---

## 2. 建议的模块边界（最小可用分层）

> 你提醒得对：未来可能有轨迹规划，但现在先聚焦 `fifo/dp`。因此蓝图采用“最小分层”，并预留扩展点。

### 2.1 六层（推荐）
1. `SimulationDriver`：只管 `traci.start / simulationStep / close` 与时钟推进
2. `StateCollector`：只产出标准状态对象 `WorldState`
3. `Scheduler`：只做“状态 -> 计划”得到 `Plan`（不输出速度）
4. `CommandBuilder`：把 `Plan` 变成“可执行的控制目标”（当前是目标到达时间 -> `v_des` 规则）
5. `Controller`：把控制目标下发成 TraCI 命令（当前主要 `setSpeed` / release）
6. `Recorder/Metrics`：落盘与指标计算；同时记录“计划-命令-实际”的对齐数据

### 2.2 为什么要单独有 CommandBuilder
因为 `Scheduler` 的输出语义应该稳定（例如 `target_cross_time`、优先级、约束窗口），而“怎么从计划变成速度/轨迹/加速度”属于运动层策略。

当前实现里 `v_des = D/(target-now)` 规则是写死在 `run.py` 的；重构后它应该成为可替换组件：
- `TimeSlotToSpeedCommandBuilder`（当前实现）
- 未来可能有 `TrajectoryCommandBuilder`

---

## 3. 数据契约（这是重构后最重要的“对齐点”）

### 3.1 WorldState（StateCollector 输出）
必须包含：
- `sim_time_s`
- `active_vehicle_ids`
- `control_zone: dict[veh_id, VehicleObs]`
- `entered_control: set[veh_id]`（历史集合）
- `crossed_merge: set[veh_id]`（历史集合）
- `entry_info[veh_id] = {t_entry_s, d_entry_m, stream, entry_rank}`

`VehicleObs` 最小字段：
- `veh_id`
- `stream`（`main/ramp`）
- `road_id / lane_id / lane_pos_m`
- `speed_mps / accel_mps2`
- `d_to_merge_m`

### 3.2 Plan（Scheduler 输出）
统一输出（无论 fifo/dp）：
- `plan_time_s`：产生计划的时刻（用于一致性指标取“最近一次计划”）
- `order: list[veh_id]`（只包含当前要控制的车辆）
- `target_cross_time_s: dict[veh_id, float]`
- `eta_s: dict[veh_id, float]`：复用现有 `plans.csv` 的 `natural_eta` 字段
  - `fifo`：`eta = natural_eta_at_entry`
  - `dp`：`eta = t_min`
- `policy_name`

计划有效期（讨论结论）：
- `dp`：按 `dp_replan_interval_s=0.5` 做“短冻结”，计划在下次 replan 前有效
- `fifo`：按“入区冻结”有效（直到车辆过 merge 或离开控制区/仿真结束）

### 3.3 ControlCommand（Controller 接收）
每步输出给 Controller 的“最小命令”：
- `set_speed_mps: dict[veh_id, float]`（或 `release_ids` 表示 setSpeed(-1)）

注意：Controller 不需要知道 dp/fifo，它只执行命令。

---

## 4. 主循环时序（把混乱的部分画清楚）

每个仿真步（`dt=0.1s`）：
1. `SimulationDriver.step()` -> 推进 SUMO 一步
2. `StateCollector.collect()` -> 得到 `WorldState`
3. `Scheduler.maybe_replan(world_state)` -> 得到 `Plan | None`
   - `no_control`：永远 None
   - `fifo`：仅在“新车入区事件”更新内部计划缓存；每步返回当前缓存对应控制区的子集
   - `dp`：仅当 `sim_time - last_replan_time >= 0.5s` 才重算并更新缓存；每步返回缓存对应控制区的子集
4. `CommandBuilder.build(world_state, plan)` -> 得到每车命令（例如 `v_des`）
5. `Controller.apply(commands)` -> `traci.vehicle.setSpeed(...)`
6. `Recorder.record(world_state, plan, commands)` -> 写 CSV
7. loop

关键点：规划频率与控制频率解耦。

---

## 5. 输出与指标升级（保留旧字段 + 增量新增）

### 5.1 保留的文件与核心字段（不破坏现有口径）
- `control_zone_trace.csv`：保持现有列（含 `v_des`）
- `plans.csv`：保持现有列（含 `natural_eta/target_cross_time/order_index/entry_rank/v_des`）
- `metrics.json`：保留既有 key（`merge_success_rate/avg_delay_at_merge_s/...`）
- `config.json`、`collisions.csv`：保持

### 5.2 新增文件（建议 2 个，专门用于“计划-命令-实际”对齐）
1. `commands.csv`（每步、每车命令）
   - `time,veh_id,stream,d_to_merge_m,v_cmd_mps,release_flag`
2. `events.csv`（稀疏事件流，便于对齐）
   - `time,event,veh_id,detail`
   - 事件示例：`enter_control`, `cross_merge`, `leave_control`, `plan_recompute`

> 这两个文件能直接回答“计划第一为什么没先过”：是计划没排它、命令没下发、还是路口规则挡住了。

### 5.3 新增 metrics（全部要，但命名要规整）
在 `metrics.json` 里新增（建议统一前缀 `consistency_`，避免乱）：
1. `consistency_merge_order_mismatch_count`
2. `consistency_cross_time_error_mean_s`
3. `consistency_cross_time_error_p95_s`
4. `consistency_speed_tracking_mae_mps`
5. `consistency_plan_churn_rate`（主要用于 dp）

计算口径（建议）：
- “计划基准”取“车辆过 merge 前最近一次包含该车的 plan 的 `target_cross_time`”
- `merge_order_mismatch_count`：按实际过 merge 事件序列，对比对应时刻的计划序列
- `plan_churn_rate`：对相邻两次 plan（以 replan 时刻为准）统计“在两次都出现的车辆中，`order_index` 变化的比例”

---

## 6. 迁移步骤（按最小风险拆）

1. 定义 `WorldState/Plan/ControlCommand` 数据结构（不改行为）
2. 抽出 `StateCollector`（从 `run.py` 把采集逻辑搬走）
3. 抽出 `Scheduler` 接口并把 `fifo/dp` 适配进去（保持现有语义）
4. 抽出 `CommandBuilder + Controller`（把 `v_des` 公式从 `run.py` 拆出去）
5. 抽出 `Recorder/Metrics`，新增 `commands.csv/events.csv` 与一致性指标
6. 增加 `dp_replan_interval_s=0.5`（并写回归验证）

每一步都用现有回归命令集跑通（`no_control/fifo/dp` 同 seed），确保输出与核心指标不退化。

---

## 7. 待确认点（需要你拍板，避免实现时口径漂）

1. `dp_replan_interval_s=0.5` 的语义：是否接受“0.5s 内冻结 schedule，但每步仍用该 schedule 下发控制命令”？
2. `plans.csv` 的写入频率：仍每步写快照，还是改为“仅 replan 时刻写快照”？
   - 若改为仅 replan 写：文件更小、更可读；但需要 trace/commands 解释每步控制
3. 一致性指标的“计划基准”选取规则是否按 5.3 所述？

