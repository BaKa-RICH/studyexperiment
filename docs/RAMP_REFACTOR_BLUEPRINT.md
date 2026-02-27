# RAMP 架构与重构记录（已落地）

目标：只围绕 `ramp/`，把现有的“仿真推进 + 状态采集 + 调度 + 控制 + 记录/指标”梳理成清晰模块边界，方便你接下来读代码、定位问题、扩展算法（先聚焦 `fifo/dp`，不超前做 Stage 3 的大系统）。

本文件原本是“重构蓝图”；目前已按蓝图落地实现，并多轮回归验证。本文作为：
- `ramp/` 架构说明（方便你读代码/定位问题）
- 关键口径冻结（避免上下文压缩导致遗忘）
- 重构与调试的记录入口（回归命令与历史结果统一指向 `docs/RAMP_VALIDATION.md`）

---

## 0. 现状快照（当前实现在哪里）

### 0.1 入口与运行闭环
- 入口：`python -m ramp.experiments.run`（文件 `ramp/experiments/run.py`）
- 场景：`ramp/scenarios/<scenario>/<scenario>.sumocfg`
- 车流：`ramp/scenarios/<scenario>/<scenario>.rou.xml`
- 路网：`ramp/scenarios/<scenario>/<scenario>.net.xml`

### 0.2 算法实现位置
- `no_control`：`ramp/policies/no_control/`（不生成计划，仅输出表头/记录）
- `fifo`：
  - scheduler：`ramp/policies/fifo/scheduler.py`（入控制区时冻结 `target_cross_time`）
  - command builder：`ramp/policies/fifo/command_builder.py`
- `dp`：
  - 调度核心：`ramp/scheduler/dp.py`
  - `t_min`：`ramp/scheduler/arrival_time.py`
  - scheduler 封装：`ramp/policies/dp/scheduler.py`（含 `dp_replan_interval_s=0.5` 冻结）
  - command builder：`ramp/policies/dp/command_builder.py`

### 0.3 输出目录（已调整）
- 默认输出：`output/<scenario>/<policy>/`（同 policy 覆盖；不同 policy 不覆盖）
- 文件：`control_zone_trace.csv`、`plans.csv`、`commands.csv`、`events.csv`、`metrics.json`、`config.json`、`collisions.csv`

### 0.4 已拍板的关键默认口径（防止上下文压缩导致遗忘）
- 仿真步长：`step-length=0.1s`
- 合流点口径：`merge_edge=main_h4`（进入该 edge 视为“过点/过 merge”）
- 控制区口径：只对 `0 < D_to_merge <= control_zone_length_m` 的车辆接管
  - 当前默认：`control_zone_length_m=600m`（更接近“提前调速 + 合流”整段接管范围；也可通过 CLI 覆盖）
- `fifo`：
  - `fifo_gap_s=1.5`
  - 入控制区时一次分配并冻结 `target_cross_time`
- `dp`：
  - `delta_1_s=1.5`，`delta_2_s=2.0`
  - `t_min` 用 CAVSim ArrivalTime（两段式）公式 + 边界保护
  - `dp_replan_interval_s=0.5`：`0.5s` 内冻结 schedule，但仍每步（`0.1s`）下发控制命令
- `D_to_merge`：优先用 `traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)`（避免 internal edge `:n_merge*` 导致的跳大值）
- 强制顺序（你的要求）：`fifo/dp` 算出的 passing order 就是最终通行顺序，SUMO 不能再用“主线优先/匝道让行”改写
  - 强制范围：只在控制区内接管
  - 接管手段：控制区内车辆切 `speedMode=23`，关闭 SUMO 的“路口让行/优先级裁决”；释放控制时恢复车辆进入控制区前的 speedMode
  - 边界允许：若车辆已进入合流路口内部（internal edge）或已近到这一步根本刹不住，则视为它“已经出手/已承诺要先过”，先让它通过，再严格执行后续顺序

---

## 1. 现阶段暴露的问题（我们要用重构解决什么）

### 1.1 “FIFO 看起来不 FIFO”
结论：当前 `fifo` 的“计划 FIFO”（按入控制区先后）与“实际过 merge 顺序”不保证一致。

根因（现状解释，不代表我们接受这种行为）：
- SUMO 的优先级/让行规则会影响实际通行（主线优先于匝道：`main` priority=2，`ramp` priority=1）
- 仅用 `setSpeed` 做“速度追踪”，无法表达“谁拥有通行权/谁必须停住让行”
- `fifo` 目标时刻在入区时冻结，后续不重排；遇到让行阻塞时就会出现“计划顺序正确但实际顺序偏离”

讨论结论（你的要求）：我们是规则制定者，`fifo/dp` 给出的 passing order 就应该被强制执行；SUMO 不能再用“主线优先/匝道让行”改写最终通行顺序。

最小落地口径（你已确认）：
- 强制顺序只在控制区内接管（`D_to_merge <= control_zone_length_m`）
- 控制区内车辆切 `speedMode=23`，关闭 SUMO 的“路口让行/优先级裁决”（释放控制时恢复原 speedMode）
- 允许边界：如果车辆已经“进门”（进入路口内部 edge）或这一步已经来不及刹住，那么视为它已经承诺要先过点，让它先完成通过；后续再严格按计划顺序

因此我们需要两件事：
1. 补“计划-命令-实际”的对齐数据与一致性指标（让 GUI 现象可量化）
2. 把“控制区内接管通行裁决（speedMode takeover + restore）”作为 Controller 的一等能力（保证实际过点顺序尽量等于计划顺序）

### 1.2 DP 每步重算导致计划抖动
现状：`dp` 每步重算会让 `target_cross_time` 经常变化，执行层在追逐移动目标，吞吐可能被拉低。

讨论结论（你已确认）：保持 `step-length=0.1s`，但把 `dp` 的 **replan interval 扩展到 0.5s**（`0.5s` 内冻结 schedule；控制仍每步下发）。

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
4. `CommandBuilder`：把 `Plan` 变成“可执行的控制目标”（当前是目标到达时间 -> `v_des` + 通行权接管规则）
5. `Controller`：把控制目标下发成 TraCI 命令（当前主要 `setSpeed` / release）
6. `Recorder/Metrics`：落盘与指标计算；同时记录“计划-命令-实际”的对齐数据

目录结构建议（你提出的要求，先按可读性优先，不用继承）：
- 通用层（1/2/5/6）：放在 `ramp/core/` 或 `ramp/runtime/`（名字以后再定）
- 算法层（3/4）：按 policy 分目录，例如：
  - `ramp/policies/fifo/{scheduler.py,command_builder.py}`
  - `ramp/policies/dp/{scheduler.py,command_builder.py}`
  - `ramp/policies/no_control/{scheduler.py,command_builder.py}`（可为空实现）

说明：即使 `fifo` 与 `dp` 复用某些 helper，也建议通过 `ramp/policies/*` 的薄封装暴露出来，保证“每个算法的 3/4 在自己目录里”，阅读时不会跳来跳去。

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
- `takeover_speed_mode_by_id: dict[veh_id, int]`（用于控制区内接管路口裁决；通常对受控车辆设为 23）
- `restore_speed_mode_ids: set[veh_id]`（离开控制区/释放控制时恢复原 speedMode；原值由 Controller 在首次 takeover 时缓存）

注意：Controller 不需要知道 dp/fifo，它只执行命令与“通行权接管/恢复”。

---

## 4. 主循环时序（把混乱的部分画清楚）

每个仿真步（`dt=0.1s`）：
1. `SimulationDriver.step()` -> 推进 SUMO 一步
2. `StateCollector.collect()` -> 得到 `WorldState`
3. `Scheduler.maybe_replan(world_state)` -> 得到 `Plan | None`
   - `no_control`：永远 None
   - `fifo`：仅在“新车入区事件”更新内部计划缓存；每步返回当前缓存对应控制区的子集
   - `dp`：仅当 `sim_time - last_replan_time >= 0.5s` 才重算并更新缓存；`0.5s` 内冻结 schedule；每步返回缓存对应控制区的子集
4. `CommandBuilder.build(world_state, plan)` -> 得到每车命令（例如 `v_des`）
5. `Controller.apply(commands)` -> `traci.vehicle.setSpeedMode(...)`（接管/恢复）+ `traci.vehicle.setSpeed(...)`
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
   - 事件示例：`enter_control`, `cross_merge`, `leave_control`, `plan_recompute`, `speedmode_takeover`, `speedmode_restore`, `commit_vehicle`

> 这两个文件能直接回答“计划第一为什么没先过”：是计划没排它、命令没下发、还是路口规则挡住了。

### 5.3 新增 metrics（全部要，但命名要规整）
在 `metrics.json` 里新增（建议统一前缀 `consistency_`，避免乱）：
1. `consistency_merge_order_mismatch_count`
2. `consistency_cross_time_error_mean_s`
3. `consistency_cross_time_error_p95_s`
4. `consistency_speed_tracking_mae_mps`
5. `consistency_plan_churn_rate`（主要用于 dp）

计算口径（建议）：
- “计划基准”的直白解释（你说 5.3 没看懂，重点在这里）：
  - 因为我们每步都会写 `plans.csv`，同一辆车会出现很多行（尤其是 `dp` 会重排/重算）。
  - 当车辆在实际时刻 `t_cross_actual` 进入 `merge_edge`（过点）时，我们需要一个“当时它应该过点的目标时间”来算误差。
  - 规则：取 **不晚于 `t_cross_actual` 的最后一次计划**，并且这次计划里 **确实包含该车**；用这一次计划中的 `target_cross_time` 作为该车的计划基准 `t_cross_plan_baseline`。
  - 直观含义：用“车辆真正过点前，系统最后一次告诉它的目标时间”做对照，而不是用更早的、已经被覆盖的老计划。

  - 例子（伪例）：若某车在 10.0/10.1/10.2 秒都被写进 `plans.csv`，其 target 分别是 15.0/15.2/15.1；实际 15.4 秒过点：
    - 计划基准取 10.2 秒这一帧的 target=15.1（因为它是 <=15.4 的最后一帧且包含该车）
    - 该车 cross_time_error = 15.4 - 15.1 = +0.3s

- `merge_order_mismatch_count`（建议定义为“逐次过点的头车一致性”）：
  - 每发生一次过点事件（某车刚进入 `merge_edge`），取该事件时刻之前最近一次的 plan 快照（同样按上面的“最后一次计划”原则）。
  - 看当时计划里的 `order[0]`（头车）是不是这次实际过点的车辆；不是则 mismatch +1。
  - 直观含义：回答你在 GUI 里问的那句“我让 A 先过，为什么实际先过的是 B？”

- `plan_churn_rate`：对相邻两次 plan（以 replan 时刻为准）统计“在两次都出现的车辆中，`order_index` 变化的比例”

---

## 6. 迁移步骤（按最小风险拆）

1. 定义 `WorldState/Plan/ControlCommand` 数据结构（不改行为）
2. 抽出 `StateCollector`（从 `run.py` 把采集逻辑搬走）
3. 抽出 `Scheduler` 接口并把 `fifo/dp` 适配进去（保持现有语义）
4. 抽出 `CommandBuilder + Controller`（把 `v_des` 公式从 `run.py` 拆出去）
5. 抽出 `Recorder/Metrics`，新增 `commands.csv/events.csv` 与一致性指标（保留旧字段 + 增量新增）
6. 增加 `dp_replan_interval_s=0.5`（`0.5s` 内冻结 schedule；控制仍每步下发）
7. 增加“强制顺序”的接管：控制区内 `speedMode=23`，释放时恢复原 speedMode（并量化一致性指标）

每一步都用现有回归命令集跑通（`no_control/fifo/dp` 同 seed），确保输出与核心指标不退化。

验证门槛（你要求的回归保障）：
- 重构前能跑通的 3 条 GUI 命令，重构后也必须跑通（`no_control/fifo/dp` 同 seed、同 duration），且输出齐全、`metrics.json` 可解析。
- 每个里程碑改动都要记录“跑了哪些回归命令、结果关键指标、plans 约束检查/一致性指标结果”。

---

## 7. 必须冻结的口径（实现时不得漂）

1. 场景冻结：
   - `ramp/scenarios/ramp_min_v1/` 作为基线场景，原则上不再做结构性变更
   - 已发生的 A/B 变更：`ramp_min_v1.net.xml` 中对 ramp 相关 lane speed 做过抬速（xml 内有注释，且对照输出保存在 `output/ramp_min_v1/*_before_ramp25/`）
   - 后续如果要升级路网结构（加速车道/合流区间），新增场景目录（例如 `ramp_min_v2`），不要继续叠加到 `ramp_min_v1`
2. 控制区范围：强制顺序只在控制区内接管（`0 < D_to_merge <= control_zone_length_m`），当前默认 `600m`
3. 强制顺序目标：`fifo/dp` 的 passing order 应尽量等于实际过点顺序
   - 接管手段：控制区内车辆切 `speedMode=23`（关闭路口让行/优先级裁决），释放控制时恢复原 speedMode
   - 边界允许：车辆已进入路口内部或这一步已不可阻止时，先让它走完（视为 commit），再严格执行后续顺序
4. DP 关键参数固定：`merge_edge=main_h4`，`delta_1=1.5s`，`delta_2=2.0s`，`t_min` 用 CAVSim ArrivalTime 公式 + 边界保护
5. DP 重规划频率：`dp_replan_interval_s=0.5`，`0.5s` 内冻结 schedule，但每步仍下发控制命令（`dt=0.1s`）
6. 输出升级原则：升级字段/新增文件时保留旧核心字段（不一次性打断现有分析脚本）
7. 回归流程：先跑回归与约束检查，符合预期再改文档；不符合预期立刻停下反思/讨论

---

## 8. 必须牢记的验收/约束（每次改动都按这个过一遍）

### 8.1 必跑回归（headless，三组同 seed）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 8.2 plans.csv 约束检查（注意 fifo/dp 口径不同）
```bash
# dp：按 delta_1/delta_2 检查（同帧按 order_index）
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/dp/plans.csv --delta-1-s 1.5 --delta-2-s 2.0

# fifo：只保证 fifo_gap_s，不区分同流/异流；用 delta_2=delta_1=fifo_gap_s 来查
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/fifo/plans.csv --delta-1-s 1.5 --delta-2-s 1.5
```

### 8.3 必跑单测（只跑 ramp，避免仓库里其它测试依赖缺失）
```bash
uv run pytest -q ramp/tests
```

### 8.4 必须通过的 GUI 回归（重构前能跑，重构后也必须能跑）
```bash
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 8.5 文件完整性检查（最低要求）
- 每组输出目录必须包含：`control_zone_trace.csv/collisions.csv/metrics.json/config.json/plans.csv`
- 若引入新增输出（如 `commands.csv/events.csv`），三组也都要生成（即使为空也要有表头）

---

## 9. 详细实施步骤（TODO + 验证点，审阅通过后开始动代码）

> 说明：重构目标是“结构变清晰，但不改变 fifo/dp 的执行层口径（`v_des -> setSpeed`、输出字段、metrics 口径）”。  
> 只有在专门的步骤里（例如 `dp_replan_interval_s=0.5`、`speedMode=23` 强制顺序、一致性指标/新文件）才允许引入可预期的行为变化。

### Step 0：建立重构前基线记录（不改代码）
- [ ] TODO 0.1：使用第 10 节的“重构执行记录表”记录每次里程碑结果：
  - 运行日期/时间
  - 回归命令（no_control/fifo/dp）
  - `metrics.json` 摘要
  - `check_plans` 摘要（dp + fifo）
  - 结论（通过/不通过 + 备注）
  - 验证点：能从表格回溯“哪一步引入了指标变化/约束失败”

### Step 1：定义数据结构（只加类型，不改行为）
- [ ] TODO 1.1：新增 `ramp/runtime/types.py`（或 `ramp/core/types.py`），定义最小数据结构：
  - `VehicleObs`
  - `WorldState`
  - `Plan`
  - `ControlCommand`
  - 验证点：只做类型/结构，不引入逻辑；现有回归与 `ramp/tests` 全部通过（见第 8 节）

### Step 2：抽出 SimulationDriver（start/step/close）
- [ ] TODO 2.1：新增 `ramp/runtime/simulation_driver.py`
  - 职责：`traci.start`、`traci.simulationStep`、`traci.close`、读取 `sim_time`
  - 验证点：`run.py` 仍能按原 CLI 跑通三组回归；输出文件齐全

### Step 3：抽出 StateCollector（TraCI -> WorldState）
- [ ] TODO 3.1：新增 `ramp/runtime/state_collector.py`
  - 迁移/封装这些现有逻辑（保持语义不变）：
    - `getIDList` 全部车辆
    - `cross_merge` 判定（`road_id == merge_edge`）
    - `_distance_to_merge`（route edges 剩余长度累加）
    - 控制区筛选（`0 < D_to_merge <= control_zone_length_m`）
    - 首次入区：记录 `t_entry/d_entry/entry_rank`（稳定）
  - 输出：`WorldState` + （可选）事件列表（enter/cross/leave）
  - 验证点：
    - `plans.csv` 行数与字段不变（重构前后同 seed 跑一遍对比行数/表头）
    - `control_zone_trace.csv` 行数与字段不变

### Step 4：按 policy 拆 Scheduler（状态 -> 计划）
- [ ] TODO 4.1：新增 `ramp/policies/no_control/scheduler.py`
  - 行为：永远返回 `None`
- [ ] TODO 4.2：新增 `ramp/policies/fifo/scheduler.py`
  - 行为完全对齐当前 `run.py`：
    - 入区一次分配并冻结 `target_cross_time`
    - `schedule_order` 按 `entry_order`，并过滤已过点车辆
- [ ] TODO 4.3：新增 `ramp/policies/dp/scheduler.py`
  - 行为完全对齐当前 `run.py`（先保持“每步重算”，先别引入 0.5s 冻结）：
    - 控制区候选拆成 `main_seq/ramp_seq`，内部按 `t_entry` 稳定排序
    - 逐车算 `t_min`（用 `traci.vehicle.getAccel` 作为 `a_max`）
    - 调 `ramp.scheduler.dp.dp_schedule()` 得到 `passing_order/target_cross_time`
  - 验证点：
    - `uv run pytest -q ramp/tests` 通过
    - `dp` 的 `check_plans` 结果 `gap_bad=0, target_mono_bad=0`

### Step 5：按 policy 拆 CommandBuilder（计划 -> 控制目标）
- [ ] TODO 5.1：新增 `ramp/policies/*/command_builder.py`
  - 第一版只做当前口径：`v_des = D_to_merge / max(target_cross_time - now, step_length)`，并 clamp 到 `[0, stream_vmax]`
  - 注意：dp 与 fifo 的执行层必须保持一致（同一套 `v_des -> setSpeed` 规则）
  - 验证点：`plans.csv` 的 `v_des` 统计分布与重构前一致（至少不出现系统性变小/抖动加剧）

### Step 6：抽出 Controller（控制下发 + release）
- [ ] TODO 6.1：新增 `ramp/runtime/controller.py`
  - 职责：对受控车辆 `setSpeed(v_des)`；对释放车辆 `setSpeed(-1)`
  - 先不引入 `speedMode=23`（保持行为不变）
  - 验证点：三组回归通过；`no_control` 不残留任何 setSpeed 控制

### Step 7：实现 dp_replan_interval_s=0.5（行为变化步骤，必须量化）
- [ ] TODO 7.1：为 dp scheduler 增加 `--dp-replan-interval-s`（默认 0.5）
  - 语义：0.5s 内冻结 schedule，但每步仍使用冻结的 schedule 下发控制命令
  - 仍保持 `plans.csv` 每步写快照
  - 验证点：
    - `dp` 仍满足 `check_plans gap_bad=0`
    - `consistency_plan_churn_rate`（后续会加）应下降；如果吞吐显著下降或 `v_des` 异常偏小，必须停下讨论

### Step 8：实现强制顺序（speedMode=23 接管，行为变化步骤）
- [ ] TODO 8.1：在 Controller 增加 speedMode 接管/恢复
  - 进入控制区并被控制时：缓存原 speedMode -> `setSpeedMode(23)`
  - 释放控制/离开控制区时：恢复原 speedMode
  - 事件写入 `events.csv`（`speedmode_takeover/speedmode_restore`）
  - 验证点：
    - GUI 下 `fifo` 的实际过点顺序应更接近计划顺序（用一致性指标量化）
    - 不允许引入碰撞（`collision_count` 仍应为 0；若出现碰撞，立刻回滚/讨论）

- [ ] TODO 8.2：处理“已进门/不可逆”的 commit 边界
  - 判定建议（先简单后精）：`road_id` 进入 junction internal edge（例如以 `:` 开头且属于 `n_merge`）时标记 commit
  - 行为：当步计划必须承认现实，先让 commit 车辆通过，再对剩余车辆严格执行 passing order
  - 验证点：`consistency_merge_order_mismatch_count` 显著下降；且不会导致死锁/吞吐断崖

### Step 9：补齐对齐数据与一致性指标（输出升级步骤）
- [ ] TODO 9.1：新增 `commands.csv/events.csv`（三组都生成）
- [ ] TODO 9.2：在 `metrics.json` 增加一致性指标（保留旧字段）
  - `consistency_merge_order_mismatch_count`
  - `consistency_cross_time_error_mean_s / p95_s`
  - `consistency_speed_tracking_mae_mps`
  - `consistency_plan_churn_rate`
  - 验证点：指标可解释、数值合理，且不会破坏现有分析脚本（旧字段仍在）

### Step 10：补一个“plans 快照”查看工具（帮助你 GUI 对照）
- [ ] TODO 10.1：新增一个小脚本（例如 `ramp/experiments/dump_plans_snapshot.py`）
  - 输入：`plans.csv` + `--time 40.0`
  - 输出：该帧 `order_index/veh_id/stream/target_cross_time/v_des`
  - 验证点：你能一条命令把某一帧的 interleaving 顺序打印出来，直接对照 GUI

---

## 10. 重构执行记录（模板）

|时间|里程碑|no_control metrics|fifo metrics|dp metrics|check_plans fifo|check_plans dp|结论/备注|
|---|---|---|---|---|---|---|---|
|2026-02-22 23:37 CST|Step 0 baseline（120s, seed=1）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|三组输出文件齐全，Step 0 验证通过；可进入 Step 1|
|2026-02-22 23:42 CST|Step 1 types（只加结构）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；行为未变，Step 1 验证通过|
|2026-02-22 23:45 CST|Step 2 SimulationDriver（结构迁移）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；三组输出文件齐全，Step 2 验证通过|
|2026-02-22 23:51 CST|Step 3 StateCollector（结构迁移）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；三组输出文件齐全，Step 3 验证通过|
|2026-02-22 23:57 CST|Step 4 policy Scheduler 拆分|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；三组输出文件齐全，Step 4 验证通过|
|2026-02-23 00:01 CST|Step 5 policy CommandBuilder 拆分|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；`v_des` 分布快照正常（fifo mean=17.53, dp mean=12.64）；Step 5 验证通过|
|2026-02-23 00:06 CST|Step 6 Controller 拆分（仅 setSpeed/release）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.5924, coll=0, stop=11|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；`no_control` 的 `control_zone_trace.csv` 中 `v_des` 非空行=0；Step 6 验证通过|
|2026-02-23 00:10 CST|Step 7 dp_replan_interval_s=0.5|thr=540.0, delay=8.7756, coll=0, stop=9|thr=510.0, delay=9.1611, coll=0, stop=3|thr=270.0, delay=14.2146, coll=0, stop=12|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；DP 吞吐未下降（270.0/h），`plans.csv` 仍每步快照（1200 帧）|
|2026-02-23 00:15 CST|Step 8 强制顺序接管（speedMode=23 + commit）|thr=540.0, delay=8.7756, coll=0, stop=9|thr=600.0, delay=9.1534, coll=0, stop=1|thr=660.0, delay=5.3090, coll=0, stop=0|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；碰撞仍为 0；出现若干 emergency braking warning（需在下一步一致性指标里继续量化）|
|2026-02-23 00:25 CST|Step 9 新增 commands/events + 一致性指标|thr=540.0, delay=8.7756, coll=0, stop=9|thr=600.0, delay=9.1534, coll=0, stop=1|thr=660.0, delay=5.3090, coll=0, stop=0|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；三组均产出 `commands.csv/events.csv`；一致性指标已写入 `metrics.json`（如 fifo mismatch=12, dp mismatch=20）|
|2026-02-23 00:29 CST|Step 10 plans 快照工具|thr=540.0, delay=8.7756, coll=0, stop=9|thr=600.0, delay=9.1534, coll=0, stop=1|thr=660.0, delay=5.3090, coll=0, stop=0|gap_bad=0, mono_bad=0（delta1=1.5, delta2=1.5）|gap_bad=0, mono_bad=0（delta1=1.5, delta2=2.0）|`uv run pytest -q ramp/tests` 26 passed；`dump_plans_snapshot` 对 `fifo/dp` 的 `time=40.1` 均能正确打印 interleaving 顺序|

## 11. 进入stage3前的准备工作

1. 把 v1 的 Stage 2.5 基线“写死到文档+版本”

  - 把你现在跑出来的 seeds=1..5 矩阵命令、结果表、阈值写进 docs/RAMP_VALIDATION.md
  - 明确验收口径：dp 的 collision=0 + check_plans=0 + mismatch=0 是硬门槛；fifo 的 mismatch 不作为门槛（因为你已接受它弱）
  - 记录一个“基线版本号”：至少写清楚 git commit hash（可选再打 tag）

  2. 明确 v2 路网的“口径合同”（不然代码会被迫大改）

  - v2 的命名/语义要先定：哪些 edge 属于 main/ramp（影响 stream 判定），哪个 edge/区域算 cross_merge（影响指标），哪个 internal edge
    前缀算 commit（影响执行不可逆边界）
  - 你让另一个 agent 画网的时候，最好把这些命名约定一起对齐，能省掉大量适配工作

  3. 把现有代码里“强耦合路网”的点做成 scenario config（为 v2 做准备）

  - 至少把这三类变成每个 scenario 的配置项，而不是写死在逻辑里：stream 判定规则、commit 判定规则、cross_merge 判定（merge_edge/
    merge_zone）
  - 目的：v2 上线时尽量“改配置不改逻辑”，避免 run.py/runtime/policies 全线返工

  4. 给 v2 建第二套 baseline matrix（Stage 3 的新世界基线）

  - v2 出来后，先跑三策略（即便 fifo 弱也跑）+ seeds=1..5，形成 v2 的 docs/RAMP_VALIDATION.md 小节
  - 这样 Stage 3 做算法时，你能同时回答两件事：在 v1 不退化、在 v2 真提升

  5. Stage 3 规格先落一页“接口不变/口径变更清单”

  - 关键是把 Stage 3 的输出语义说清楚：还是“时序调度 target_cross_time”主线，还是引入“合流区间/可变合流点”
  - 一旦口径要从“固定 merge 点”升级到“merge 区间”，要提前写清楚 D_to_merge、cross_merge、check_plans 的定义如何改