# Stage 1 实施计划：最小路网 + 基线（Baseline）

本文件是 `RAMP_SUMO_PLAN.md` 的 **Stage 1** 具体落地清单，目标是：

1. 在“自建最小匝道路网”上把仿真闭环跑通
2. 固定输出口径（trace + metrics + collisions）
3. 跑通两套基线 policy：
   - `no_control`：SUMO 默认行为（不干预）
   - `fifo`：最简单的“先到先过合流点”的协同控制（先全 CAV，便于跑通）

> Stage 0（CSDF batch_run）已验证环境 OK，不在此文件重复。

---

> 说明（2026-02-23）：Stage 1 已实现并作为基线冻结；本文件保留“实施计划”段落作为历史参考。实际验收/回归命令以 `docs/RAMP_VALIDATION.md` 为准。

## Stage 1 Definition of Done（DoD）

满足以下条件即 Stage 1 完成：

1. 自建场景 `ramp_min_v1` 能用 `sumo`（无 GUI）跑通 300s，不报错。
2. `uv run python -m ramp.experiments.run ...` 能跑通（建议回归用 `duration=120s`），输出目录里至少包含：
   - `control_zone_trace.csv`（控制区车辆轨迹）
   - `plans.csv`（每步计划快照；`no_control` 也会写表头）
   - `commands.csv`（每步命令快照）
   - `events.csv`（稀疏事件流）
   - `metrics.json`
   - `collisions.csv`（即使为空也要有表头）
   - `config.json`
3. `--policy no_control` 与 `--policy fifo` 都能跑通，并生成同样格式的输出。
4. `metrics.json` 至少包含：
   - `merge_success_rate`
   - `avg_delay_at_merge_s`
   - `throughput_veh_per_h`（或 `veh_per_s`，但要写清楚单位）
   - `collision_count`
   - `stop_count`

---

## 约定（Stage 1 固定下来，避免歧义）

### 1) 路网语义
- 两股流：
  - 主线 Main：`main_*`
  - 匝道 Ramp：`ramp_*`
- 固定合流点（冲突点）：`n_merge`
- 过点口径：进入 `merge_edge=main_h4` 视为 cross merge

### 2) 仿真参数（默认值）
- `step-length = 0.1s`
- `duration = 120s`（回归默认；调试时可先跑 20~60s）
- 控制区长度（到合流点剩余距离）：`control_zone_length_m = 600`
- 流上限（用于自由流 ETA 与 `v_des` 上限，不等同于 `.net.xml` lane speed）：
  - `main_vmax_mps=25.0`
  - `ramp_vmax_mps=16.7`（若希望与当前 `ramp_min_v1.net.xml` 的 `25.00` 对齐，可运行时传 `--ramp-vmax-mps 25.0`）
- 规划更新策略：
  - `no_control`：不生成计划
  - `fifo`：车辆入控制区时分配并冻结 `target_cross_time`（后续不重排）
  - `dp`：属于 Stage 2，默认 `dp_replan_interval_s=0.5`（详见 `PLAN_RAMP_STAGE2.md`）

### 3) 车流（起步低流量）
建议起步流量（便于稳定跑通）：
- `flow_main = 600 veh/h`
- `flow_ramp = 300 veh/h`

---

## Step-by-step TODOLIST（每个 TODO 都有验证点）

### Step 1：在主仓库建立 Stage 1 的目录骨架

- [ ] TODO 1.1：创建场景目录 `ramp/scenarios/ramp_min_v1/`
  - 验证点：目录结构如下（至少存在这些路径）
    - `ramp/scenarios/ramp_min_v1/`
    - `docs/PLAN_RAMP_STAGE1.md`（本文件）

- [ ] TODO 1.2：决定并记录“最小路网”的文件命名
  - 约定文件名：
    - `ramp_min_v1.net.xml`
    - `ramp_min_v1.rou.xml`
    - `ramp_min_v1.sumocfg`
  - 验证点：目录内能看到上述 3 个文件（可以先空文件占位，后续补内容）。

---

### Step 2：用 netedit 自建最小“单主线单匝道”路网（固定合流点）

#### 2.1 设计目标（能跑即可，几何以后可升级）
- 主线沿 x 轴，匝道从下方斜接到 `n_merge`
- 最小只要 1 车道（Stage 1 不研究多车道/换道）

#### 2.2 推荐节点坐标（可直接照抄，长度近似 H1~H4）
主线：
- `n_main_0 = (0, 0)`
- `n_main_1 = (200, 0)`  (H1=200)
- `n_main_2 = (500, 0)`  (H2=300)
- `n_merge  = (800, 0)`  (H3=300)
- `n_main_3 = (1000, 0)` (H4=200)

匝道（保证不与主线重叠）：
- `n_ramp_0 = (500, -350)`
- `n_ramp_1 = (500, -50)`  (H5≈300)

边（edge id）：
- `main_h1: n_main_0 -> n_main_1`
- `main_h2: n_main_1 -> n_main_2`
- `main_h3: n_main_2 -> n_merge`
- `main_h4: n_merge -> n_main_3`
- `ramp_h5: n_ramp_0 -> n_ramp_1`
- `ramp_h3: n_ramp_1 -> n_merge`（斜接到合流点）

边属性建议（Stage 1 先固定）：
- lane 数：`1`
- lane width：`3.75`
- speed：
  - main：`25`
  - ramp：`25`（当前 `ramp_min_v1.net.xml` 已把 ramp 相关 lane speed 抬到 `25.00` 并在 xml 内注明原值，用于 A/B 验证）

- [ ] TODO 2.3：用 netedit 按上述节点/边命名创建网络，并保存为 `ramp_min_v1.net.xml`
  - 验证点 A（可视化）：`sumo-gui -n ramp_min_v1.net.xml` 能打开并看到合流结构。
  - 验证点 B（headless）：`sumo -n ramp_min_v1.net.xml --no-step-log true -v` 退出码为 0。

> 常见坑：如果你画出重叠/自交的 edge，SUMO 可能会报几何错误。先追求“能跑通”，几何美观放后面。

---

### Step 3：编写最小 demand（rou.xml）与 sumocfg

#### 3.1 route 定义（用可读 edge 列表）
- `main_route_edges = "main_h1 main_h2 main_h3 main_h4"`
- `ramp_route_edges = "ramp_h5 ramp_h3 main_h4"`

#### 3.2 vType（全 CAV 起步）
Stage 1 先用 1 个 vType：`cav`（参数先朴素，重点是稳定）
建议显式设置 `tau >= step-length`，避免“tau 小于步长”的警告。

- [ ] TODO 3.3：写 `ramp_min_v1.rou.xml`
  - 包含：
    - `<vType id="cav" .../>`
    - `<route id="main_route" edges="..."/>`
    - `<route id="ramp_route" edges="..."/>`
    - `<flow ... route="main_route" vehsPerHour="600" .../>`
    - `<flow ... route="ramp_route" vehsPerHour="300" .../>`
  - 验证点：`sumo -c ramp_min_v1.sumocfg --no-step-log true --quit-on-end true` 能跑完（见下一条）。

- [ ] TODO 3.4：写 `ramp_min_v1.sumocfg`
  - 必须包含：
    - `<net-file value="ramp_min_v1.net.xml"/>`
    - `<route-files value="ramp_min_v1.rou.xml"/>`
    - `<step-length value="0.1"/>`（或通过 CLI 覆盖，但 Stage 1 建议写死）
  - 验证点：
    - `sumo -c ramp_min_v1.sumocfg --no-step-log true --duration-log.statistics true --quit-on-end true` 退出码为 0
    - SUMO 输出中能看到 vehicles `TOT` 增长（说明 flow 生效）

---

### Step 4：先不用 Python，纯 SUMO 验证“路网 + 车流”基本可跑

- [ ] TODO 4.1：用 GUI 检查是否真的发生合流
  - 命令：`sumo-gui -c ramp_min_v1.sumocfg --start`
  - 验证点：能看到匝道车进入 `n_merge` 并进入下游 `main_h4`。

- [ ] TODO 4.2：用 headless 检查无 GUI 也可跑
  - 命令：`sumo -c ramp_min_v1.sumocfg --no-step-log true --quit-on-end true`
  - 验证点：退出码 0；如果报 collision 或 deadlock，先降低流量再看 junction priority。

---

### Step 5：建立 Python 实验入口（Stage 1 的可重复运行骨架）

目标：模仿 `CSDF/batch_run.py` 的风格，做一个新的 `ramp` 实验入口。

- [ ] TODO 5.1：新增 `ramp/experiments/run.py`（只要骨架先跑起来）
  - 验证点：能运行到 `traci.start(...)` 并推进若干步后正常退出（先不做输出）
  - 最小命令示例（预期）：
    - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 5`

- [ ] TODO 5.2：复用/移植 `CSDF/batch_run.py` 的 “优先 SUMO_HOME/tools traci” 逻辑
  - 验证点：`uv run python -c "import traci, sumolib; print('ok')"` 能通过；运行脚本不出现版本签名错误。

---

### Step 6：实现输出口径（trace + collisions + metrics 框架）

#### 6.1 control_zone_trace.csv（控制区车辆轨迹）
定义控制区：`D_to_merge <= control_zone_length_m`。

- [ ] TODO 6.1：实现 `D_to_merge` 计算（固定合流点版本）
  - 当前实现：优先用 `traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)` 计算到 `merge_edge` 的沿路网距离；必要时再 fallback 到“route edges 剩余长度累加”
  - 验证点：
    - 对任意车辆，`D_to_merge` 随时间单调下降（允许数值噪声）
    - 车辆进入 `main_h4` 后不再出现在控制区 trace（或 `D_to_merge` 变为 0 并停止记录）

- [ ] TODO 6.2：实现 `control_zone_trace.csv` 写入（每步写控制区内车辆）
  - 字段建议（Stage 1 固定）：`time,veh_id,stream,edge_id,lane_id,lane_pos,D_to_merge,speed,accel,v_des`
  - 验证点：
    - 文件存在且表头存在
    - 默认参数建议用 `duration >= 60s` 再检查行数 > 0（更稳；旧默认 `150m` 时 10s 可能尚未进入控制区）
    - 若只做 10s 写出能力烟测，可临时设置更大控制区（例如 `--control-zone-length-m 1000`）再检查行数 > 0
    - 表头存在且字段齐全

#### 6.2 collisions.csv（碰撞事件）

- [ ] TODO 6.3：实现 `collisions.csv` 写入（每步读取 `traci.simulation.getCollisions()`）
  - 验证点：
    - 即使 0 碰撞也生成文件且有表头
    - 手动提高流量（例如 3000 veh/h）时应能记录到碰撞（可选压力验证）

#### 6.3 metrics.json（指标闭环）
Stage 1 指标建议（先稳定再加）：
1. `merge_success_rate`
   - 统计对象：进入控制区的车辆
   - success 定义：在仿真中“进入过下游 edge `main_h4`”
2. `avg_delay_at_merge_s`
   - 先用“自由流 ETA”做基准：车辆进入控制区时记录 `D_entry` 与 `t_entry`，定义 `t_ff = D_entry / v_max_stream`，delay = `t_cross - (t_entry + t_ff)`
3. `throughput_veh_per_h`
   - 统计窗口：整段仿真或最后 N 秒都行（先整段，稳定后再细化）
4. `collision_count`
5. `stop_count`（速度 < 0.1 m/s 的累计次数或累计秒数，先定一个口径写清楚）

- [ ] TODO 6.4：实现 `metrics.json` 的最小闭环（先别追求完美）
  - 验证点：
    - 文件生成且包含上述 key
    - `merge_success_rate` 在低流量下应接近 1（除非仿真时间太短）

---

### Step 7：实现 policy = no_control（SUMO 默认）

- [ ] TODO 7.1：`no_control` 模式下不对车辆做任何 setSpeed，只负责记录输出
  - 验证点：
    - `control_zone_trace.csv`、`metrics.json` 都能生成
    - `metrics.json.policy_name == "no_control"`

---

### Step 8：实现 policy = fifo（最简单协同调度）

这里的 FIFO 是“先到先过合流点”的**基线调度**，不是 DP 优化。

建议 Stage 1 FIFO 的最小定义（清晰、可实现、可测）：
1. 车辆进入控制区时记录 `t_enter_control_zone`
2. 以 `t_enter_control_zone` 升序作为 passing order（同一时刻可按距离/veh_id 打破平局）
3. 为 passing order 生成 `target_cross_time`：
   - 第 1 辆：`target = max(natural_eta, now + min_gap)`
   - 后续：`target_i = max(natural_eta_i, target_{i-1} + gap_s)`
   - Stage 1 的 `gap_s` 先用常数（例如 1.5s），不要引入 `delta_1/delta_2`（那是 Stage 2/DP 的内容）
   - Stage 1 实际落地口径：`target_cross_time` 在“进入控制区时”一次分配并固定，不做每步重分配
4. 执行层：每步用 `setSpeed` 追踪 `target_cross_time`

- [ ] TODO 8.1：实现 FIFO passing order（按进入控制区时间排序）
  - 验证点：
    - 在 debug log（或 plans.csv）里能看到 passing order
    - 同一辆车不会频繁在 order 中跳来跳去（否则说明“进入时间”没锁定）

- [ ] TODO 8.2：实现 `target_cross_time` 分配（常数 gap）
  - 验证点：
    - `target_cross_time` 单调不减
    - 相邻两车 target time 至少差 `gap_s`

- [ ] TODO 8.3：实现速度追踪（setSpeed）
  - 验证点：
    - trace 里有 `v_des`（可在 Stage 1 trace 增加列）
    - FIFO 模式能让车辆通过 merge 点（进入 `main_h4`）

- [ ] TODO 8.4：比较 `no_control` vs `fifo` 的指标（同 seed/同流量）
  - 验证点：
    - 两次运行输出目录都完整
    - 你能从 `metrics.json` 看出差异（至少 delay/stop/throughput 某个维度）

---

### Step 9：Stage 1 的“烟雾测试”（最重要）

把测试写成固定命令，后续你 vibe coding 每做一小步就跑一下。

- [ ] TODO 9.1：Smoke test：`no_control` 运行 20s
  - 命令（示例）：`SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 20 --out-dir output/ramp-stage1/no_control`
  - 验证点：
    - 输出文件齐全且非空
    - `metrics.json` 可解析（合法 JSON）

- [ ] TODO 9.2：Smoke test：`fifo` 运行 20s
  - 命令（示例）：`SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --duration-s 20 --out-dir output/ramp-stage1/fifo`
  - 验证点：
    - 输出文件齐全且非空
    - `metrics.json.policy_name == "fifo"`

- [ ] TODO 9.3：Regression：同 seed 重复跑两次，确认可重复性
  - 命令：`--seed 1` 重复运行两次
  - 验证点：两个 `metrics.json` 的关键指标差异很小（完全相同不强求，但不能漂太大）

---

## Stage 1 执行记录（2026-02-20，供 Stage 2 参考）

### A) 本轮已完成范围（实现与验证）
1. Step 1-8 已完成并通过对应验证点。
2. Step 9 不作为新的开发阻塞项；本轮已完成等价覆盖（`no_control/fifo` 均跑通、输出齐全、同 seed 对比完成）。

### B) 已冻结的 Stage 1 基线口径
1. `no_control`：不对车辆做控制，仅记录输出。
2. `fifo`：保持“进入控制区即入队”的强约束基线。
3. `fifo` 控制范围：控制区内所有车辆统一排队（不区分主线/匝道）。
4. `fifo` 启用方式：持续启用（进入控制区即受控）。
5. `fifo` 执行方式：继续双向速度跟踪（`setSpeed`，可加速也可减速）。
6. `fifo` 目标时刻：`target_cross_time` 在车辆进入控制区时一次分配并固定。

### C) 输出文件与字段（当前实现）
1. `control_zone_trace.csv`：`time,veh_id,stream,edge_id,lane_id,lane_pos,D_to_merge,speed,accel,v_des`
2. `collisions.csv`：碰撞事件逐步记录（0 碰撞也有表头）
3. `plans.csv`：FIFO 调度日志（`entry_rank/order_index/natural_eta/target_cross_time/gap_from_prev/v_des`）
4. `commands.csv`：每步命令快照（`time,veh_id,stream,d_to_merge_m,v_cmd_mps,release_flag`）
5. `events.csv`：稀疏事件流（`enter_control/leave_control/cross_merge/plan_recompute/...`）
6. `metrics.json`：至少包含 `merge_success_rate,avg_delay_at_merge_s,throughput_veh_per_h,collision_count,stop_count`
7. `config.json`：记录本次运行参数

### D) 关键统计口径补充
1. `merge_success_rate` 使用“已评估车辆集合”：从进入控制区车辆中剔除仿真结束时仍在控制区的 `pending_unfinished`，避免固定时长截断造成虚假失败。
2. `throughput_veh_per_h` 口径：`crossed_merge_count / duration_s * 3600`。
3. `stop_count` 口径：速度 `< 0.1 m/s` 的“停住事件次数”（进入停住状态计一次，不是累计秒）。

### E) 验证快照（`duration=120s, seed=1`）
1. 指标快照不在本文硬编码具体数值；以 `docs/RAMP_VALIDATION.md` 的历史结果表为准（同 seed/同 duration）。
2. FIFO 约束验证：`uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/fifo/plans.csv --delta-1-s 1.5 --delta-2-s 1.5`（按 `time` 分组；同帧检查）

### F) GUI 与命令行注意事项
1. `sumo-gui` 若加 `--start` 且无 `--delay`，会快速跑完，看起来像“刚打开就结束”。
2. GUI 可视化建议：`sumo-gui -c ramp_min_v1.sumocfg --breakpoints 0 --delay 200`。
3. 命令参数之间必须有空格，例如 `--no-step-log true --quit-on-end true`，不要写成 `true--quit-on-end`。

### G) Stage 2 前的最小回归命令集（保留）
1. `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 60 --seed 1 --out-dir output/ramp-stage1/reg-no-control`
2. `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --duration-s 60 --seed 1 --fifo-gap-s 1.5 --out-dir output/ramp-stage1/reg-fifo`
3. `uv run python -c "import traci, sumolib; print('ok')"`

---

## 常见问题（Stage 1 快速排查）

1. 匝道车不进入下游 `main_h4`
   - 检查 route 是否包含 `main_h4`
   - 检查 junction `n_merge` 的连接是否正确（netedit 里看 connection）

2. headless 跑不出车辆
   - 检查 `.sumocfg` 引用的 `.rou.xml` 路径
   - 检查 flow 的 `begin/end`，以及 `vehsPerHour`

3. FIFO 控制后反而更乱/碰撞
   - 先降低流量
   - 先把 `gap_s` 调大（例如 2.0~3.0）
   - FIFO 先只做“让行减速”，不要强行加速追时间

---

## Stage 1 完成后（下一步衔接）

Stage 1 稳定后再进入 Stage 2：
1. 把 FIFO 的常数 `gap_s` 替换为 DP/调度产生的 target time
2. 引入 CAVSim 的 `t_min` 与 DP state space（那是 Stage 2 的工作）
