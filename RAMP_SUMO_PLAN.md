# RAMP SUMO Plan（SUMO + Python + VSCode）

本计划文件是你“匝道合流算法开发”的主线 roadmap。它以 **实现最小可跑闭环** 为第一目标，并且明确区分：

1. 基线（Baseline）：SUMO 默认 + FIFO
2. 复现/移植（Reference Impl）：CAVSim 的 DP 调度（固定合流点）
3. 你的贡献（Your Method）：灵活合流点 + 三体分区/造隙 + 后续分区集群/滚动优化
4. 拓展（Scale Up）：多车道主线 + 双车道匝道 + 多匝道 + 混行

你已经确认的关键选择：
1. 仿真系统：SUMO + Python(TraCI) + VSCode
2. 起步路网：**自建最小“单主线单匝道”**（便于命名与对齐论文结构）
3. DP 阶段：先用 **固定合流点（冲突点）**
4. step-length：`0.1s`
5. 输出：控制区车辆全轨迹（第一阶段按控制区输出，不输出全网全车）

> 更新（2026-02-23）：Stage 1/2（`no_control/fifo/dp`）已落地并作为基线冻结。回归命令与历史关键结果以主仓库 `docs/RAMP_VALIDATION.md` 为准；Stage 1/2 的冻结口径分别见 `docs/PLAN_RAMP_STAGE1.md`、`docs/PLAN_RAMP_STAGE2.md`；当前 `ramp/` 架构见 `docs/RAMP_REFACTOR_BLUEPRINT.md`。

---

## 0) 三个仓库的角色

1. 主仓库（代码 base）：`/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration`
2. CAVSim（知识库）：给我们“调度/序列优化”的可运行参考（DP/Group/Rule、t_min 计算等），但不直接编译复用 C++。
3. ahuandao（知识库）：给我们“换道造隙（MOBIL）/IDM 预测”的实现参考，后续移植成 Python 模块。

---

## 1) 主线阶段划分（写清楚 1/2/3，不歧义）

### Stage 0：环境闭环（已验证）
目标：证明 `uv + TraCI + SUMO` 可用，能导出 CSV。
1. 命令：`cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration && SUMO_GUI=0 uv run python -m CSDF.batch_run --duration-s 30`
2. 验收：生成 `vehicle_trace_*.csv` 与 `collisions_*.csv`

备注：这一步的排障经验已整理在主仓库 `docs/WORKLOG_2026-02-17_CSDF_ENV.md`，后续 `ramp/` 也复用同一套 `uv + SUMO_HOME/tools` 的兼容策略。

### Stage 1：最小路网 + 基线（Baseline）
目标：在“自建最小匝道路网”上跑通并固定输出口径。
1. 基线 policy：
   - `SUMO 默认（no_control）`：不干预，直接用 SUMO 自带跟驰/让行
   - `FIFO`：实现一个最简单的“先到先过合流点”的协同控制（全 CAV，便于先跑通）
2. 核心产出：可重复实验输出目录 + metrics 指标闭环

### Stage 2：复现/移植 CAVSim 的 DP 调度（固定合流点）
目标：在同一条最小路网上，把 CAVSim 的 DP 思想移植到 Python，并与 Stage 1 基线对比。
1. 这一步才是“DP 属于哪一步”的答案：DP 属于 **调度/序列模块（Scheduler）**。
2. 合流点：固定 merge point（冲突点），DP 就是围绕这个点做“谁先过”的最优交织。
3. 输出：在同样的车流/随机种子下，对比 SUMO 默认、FIFO、DP 的 delay/成功率/吞吐。

### Stage 3：你的贡献（灵活合流点 + 规则/优化）
目标：在 Stage 2 之上，加入你 thesis 的核心创新点。
1. 把固定合流点扩展为合流区间（merge zone），允许灵活合流点 `s_c`
2. 实现 ETA 三体分区 `{M, L, F}` + 造隙分摊规则 +（可选）轨迹生成
3. 再引入混行、时滞补偿等（对应第 3 章）

---

## 2) DP 是什么（面向匝道合流的解释）

DP = Dynamic Programming（动态规划），不是深度学习。

在匝道合流里，最常见的抽象是“两个队列交织通过一个冲突点”：
1. 主线车辆保持车道内顺序（不超车）形成队列 `M1, M2, ...`
2. 匝道车辆保持顺序形成队列 `R1, R2, ...`
3. 冲突点一次只能通过一辆车，且相邻两车需要安全时间间隔：
   - `delta_1`：同一股流连续通过的间隔（通常较小）
   - `delta_2`：不同股流交替通过的间隔（通常较大）
4. 目标：找一个交织顺序（例如 `M1, R1, M2, M3, R2...`）使“总延误/总通过时间”最小。

CAVSim 的 `DPMethod` 就是在固定合流点下解这个问题。我们会把它移植成 Python 版本，作为 Stage 2 的“参考算法”。

---

## 3) 自建最小路网（单主线单匝道，固定合流点）

### 3.1 路网目标（最小但对齐论文语义）
路网要满足：
1. 只有 2 股流：主线（Main）与匝道（Ramp）
2. 在一个固定 merge node 处汇入一个下游主线
3. 便于定义固定合流点（冲突点）与控制区长度
4. 命名可读：不用 `-10_2/-3_2` 这种自动生成 id

### 3.2 推荐的节点/边命名（可读性优先）
节点（node id）：
1. `n_main_0`：主线起点
2. `n_main_1`：主线 H1 末端
3. `n_main_2`：主线 H2 末端
4. `n_merge`：固定合流点（冲突点）
5. `n_main_3`：下游终点
6. `n_ramp_0`：匝道起点
7. `n_ramp_1`：匝道 H5 末端（可选）

边（edge id）：
1. `main_h1`: `n_main_0 -> n_main_1`
2. `main_h2`: `n_main_1 -> n_main_2`
3. `main_h3`: `n_main_2 -> n_merge`（到合流点前的最后一段主线）
4. `main_h4`: `n_merge -> n_main_3`（合流点后下游）
5. `ramp_h5`: `n_ramp_0 -> n_ramp_1`（匝道速度控制区，可选）
6. `ramp_h3`: `n_ramp_1 -> n_merge`（匝道进入冲突点）

路线（route edges）命名：
1. `main_route_edges = "main_h1 main_h2 main_h3 main_h4"`
2. `ramp_route_edges = "ramp_h5 ramp_h3 main_h4"`

### 3.3 长度与限速（初值直接取你场景设计文档）
参考：`D:\A学畜区\obsidian库\匝道仿真设计\代码设计\场景设计：多车道主线 + 双车道匝道 + L3 择机并入 + ... .md`
1. H1=200m, H2=300m, H3=300m, H4=200m, H5=300m（可按需要微调）
2. 主线限速 `v_max_main = 25 m/s`
3. 匝道限速 `v_max_ramp = 16.7 m/s`（论文/对照口径）
4. 车道宽度 `3.75m`

补充（A/B 场景变更，已发生）：
- `ramp_min_v1.net.xml` 中曾把 ramp 相关 lane（含 internal edge）speed 抬到 `25.00` 用于验证一致性与吞吐问题；xml 内有注释说明原值。
- 调度/控制里用于 `t_min` 与 `v_des` 上限的 `--main-vmax-mps/--ramp-vmax-mps` 是“算法自由流上限”，不等同于 `.net.xml` 的 lane speed（需要对齐时可显式传参）。

### 3.4 netedit 画图步骤（你不需要写代码）
1. 打开：`netedit`
2. 新建网络，选择“创建 nodes/edges”模式
3. 按 3.2 的命名建节点（建议主线沿 x 轴，匝道从下方斜接到 `n_merge`）
4. 创建 edges，并在 edge 属性里设置：lane 数（1）、speed、length（或用节点间距控制）
5. 保存：`ramp_min_v1.net.xml`
6. 再创建 routes：
   - `ramp_min_v1.rou.xml`（定义 route + flow）
   - `ramp_min_v1.sumocfg`（引用 net+rou）
7. 用 `sumo-gui -c ramp_min_v1.sumocfg` 先可视化检查：两股流都能正确汇入下游

建议文件落地位置（在主仓库里，便于统一管理）：
1. `Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/ramp/scenarios/ramp_min_v1/`
2. 里面包含：`ramp_min_v1.net.xml`, `ramp_min_v1.rou.xml`, `ramp_min_v1.sumocfg`, `ramp_min_v1.gui.xml`（可选）

---

## 4) SUMO 里 edge / lane / route 是什么（你提到“我不了解路网文件”）

1. edge：一段有向路（例如 `main_h3`）
2. lane：edge 里的车道，SUMO 的默认命名通常是 `edgeID_0`, `edgeID_1`…
   - 例如 `main_h3_0` 是 `main_h3` 的第 0 条车道
3. route：车辆走过的一串 edges
   - 例如 `main_h1 main_h2 main_h3 main_h4`

我们自建路网后，就能用可读的 id 代替之前 scene8 那种 `-10_2/-3_2`（自动导出的 id）。

---

## 5) 实验代码结构（当前实现，仍以主仓库为 base）

在 `Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/` 下 `ramp/` 已落地为主线实验框架。当前目录结构：
1. `ramp/experiments/`：运行入口与分析小工具（`python -m ramp.experiments.run`）
2. `ramp/scenarios/`：SUMO 场景（`*.net.xml/*.rou.xml/*.sumocfg`）
3. `ramp/runtime/`：仿真推进、状态采集、控制下发、数据结构（通用层）
4. `ramp/policies/`：按策略拆分的 `scheduler/command_builder`（`no_control/fifo/dp`）
5. `ramp/scheduler/`：Stage 2 DP 的纯算法层（`arrival_time.py` + `dp.py`）

注意：由于我们自建 net，不再强依赖“strip vClass 兼容补丁”，但仍保留“优先使用 `SUMO_HOME/tools` 的 traci”的做法以防版本漂移。

---

## 6) 重规划频率（你提出要和 step-length 一致）

1. `step-length = 0.1s`：仿真推进步长
2. `dp_replan_interval_s = 0.5s`：DP 调度多久重算一次（`0.5s` 内冻结 schedule，但每个仿真步仍下发控制命令）

备注：`fifo` 的目标时刻是“车辆入控制区时冻结”；`dp` 的目标时刻是“按 `dp_replan_interval_s` 周期冻结”。

---

## 7) 输出与验收（Stage 1/2 共用）

输出目录（默认，同 policy 覆盖；不同 policy 不覆盖）：
- `output/<scenario>/<policy>/`

每次 run 至少输出：
1. `control_zone_trace.csv`（控制区车辆全轨迹）
2. `plans.csv`（每步计划快照）
3. `commands.csv`（每步控制命令快照）
4. `events.csv`（稀疏事件流，用于和 GUI 对齐）
5. `metrics.json`
6. `collisions.csv`
7. `config.json`

Stage 1 DoD：
1. `no_control` 能跑完，输出齐全
2. `fifo` 能跑完，输出齐全
3. metrics 字段固定（平均速度、延误、成功率、吞吐、碰撞数、停车数）

Stage 2 DoD：
1. `dp` 能跑完，输出齐全
2. 与 `fifo` 对比，有明确差异（至少在总延误或吞吐中体现）

---

## 8) Scene8 的使用方式（现在不是起步路网，而是参考标准）

`Scene/scene8` 的价值：
1. 给你“真实风格匝道”的结构参考（几何、连接、导出格式）
2. 给后续多车道/更真实网络搭建提供对照

计划：Stage 1/2 在自建最小路网上把算法跑通；Stage 3/4 再考虑把“同一套算法模块”迁移到更真实/更复杂的路网（可以参考 scene8 或直接按论文画 L1–L6）。

---

## 9) 实现细化（代码与接口，方便你之后读代码/我之后写代码）

这一节把“要写哪些 Python 文件、各自干什么、数据怎么流动”写清楚，避免 Stage 2/3 做的时候又重新讨论。

### 9.1 代码落地位置（放在主仓库里）
已落地位置（主仓库）：
1. `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/ramp/`
2. `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/ramp/scenarios/ramp_min_v1/`
3. `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/docs/`（`PLAN_RAMP_STAGE1.md`、`PLAN_RAMP_STAGE2.md`、`RAMP_VALIDATION.md`、`RAMP_REFACTOR_BLUEPRINT.md`、`RUNBOOK_SUMO.md`）

### 9.2 入口脚本（统一 run）
新增 `ramp/experiments/run.py`，职责：
1. 解析参数：`scenario`, `policy`, `duration`, `step_length`, `flow_main`, `flow_ramp`, `seed`, `gui`
2. 启动 SUMO（`sumo` 或 `sumo-gui`）
3. TraCI 循环：每步 `traci.simulationStep()`
4. 每步采集控制区状态；由 policy 生成/投影计划：
   - `fifo`：车辆入控制区时分配并冻结目标时刻（每步仍会输出同一份计划的“当前投影”）
   - `dp`：按 `dp_replan_interval_s` 周期重算 schedule（冻结窗口内只做投影）
5. 每步执行控制（速度控制为主；控制区接管 `speedMode=23`，commit 边界处理，释放恢复）
6. 写输出（trace、metrics、collisions）

### 9.3 ScenarioConfig（把路网语义写成配置）
新增 `ramp/scenarios/ramp_min_v1.py`（或一个 `ScenarioConfig` dataclass），第一版只需要这些字段：
1. `sumocfg_path`
2. `net_path`
3. `routes_path`（或 run 时生成）
4. `merge_node_id = "n_merge"`（固定冲突点 node）
5. `merge_edge = "main_h4"`（过点口径：进入该 edge 视为 cross merge；`D_to_merge` 也以此为目标）
6. `control_zone_length_m = 600`
7. `step_length_s = 0.1`
8. `dp_replan_interval_s = 0.5`（仅 dp；fifo 是入区冻结）
9. `main_route_edges` 与 `ramp_route_edges`（用于我们自己算 D_to_merge）

备注：固定合流点情况下，“合流点就是 node n_merge”，所以 Stage 1/2 不需要 merge_zone。

### 9.4 State 抽象（从 TraCI 读出来的最小状态）
状态采集（当前实现见 `ramp/runtime/state_collector.py` 与 `ramp/runtime/types.py`），最小字段建议：
1. `time`
2. `veh_id`
3. `stream`: `"main"` 或 `"ramp"`（根据 route 或入口 edge 判断）
4. `edge_id`
5. `lane_id`
6. `lane_pos`
7. `speed`
8. `accel`
9. `D_to_merge`（到固定合流点的剩余距离）

`D_to_merge` 计算口径（优先 drivingDistance，必要时 fallback）：
1. 优先用 `traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)` 计算到 `merge_edge` 的沿路网距离（避免 internal edge `:n_merge*` 导致的跳大值/索引错配）
2. 必要时再 fallback 到“route edges 剩余长度累加”的做法

### 9.5 Policy（Stage 1/2/3 插拔）
新增 `ramp/policies/`（按 policy 分目录）：
1. `no_control/`：不控制（只记录/写表头）
2. `fifo/`：FIFO 调度（入控制区冻结 `target_cross_time`）
3. `dp/`：Stage 2 的 DP 调度（CAVSim 思想移植；`dp_replan_interval_s=0.5` 冻结）
4. `your_method/`：Stage 3 你的算法（后续新增）

Policy 统一输出：
1. `passing_order: list[str]`
2. `target_arrival_time: dict[str, float]`

### 9.6 Scheduler（Stage 2 的核心：CAVSim DP）
新增 `ramp/scheduler/`：
1. `arrival_time.py`
   - 移植 CAVSim `CalculMinimumArrivalTimeAtOnRamp` 的最小可达时间 `t_min`
2. `dp.py`
   - 输入：`main_queue`, `ramp_queue`, `t_min`, `delta_1`, `delta_2`
   - 输出：`passing_order` 与每辆车 `target_arrival_time`

注意：这一步明确在 **Stage 2** 才做（Stage 1 先把路网/输出/基线跑稳）。

### 9.7 Control（从 target_arrival_time 落到 setSpeed）
现状实现（已落地）：
1. `ramp/policies/*/command_builder.py`：把 `Plan` 转成“可执行命令”（当前是 `target_cross_time -> v_des`）
2. `ramp/runtime/controller.py`：把命令下发为 TraCI 调用（`setSpeed`、控制区接管 `speedMode=23`、commit 边界处理、释放恢复）
3. Stage 1/2 先不做复杂轨迹，保证“简单、稳、可评估”

推荐追踪公式（够用且好 debug）：
1. `t_rem = target_time - now`
2. `v_des = clamp(D_to_merge / max(t_rem, eps), 0, v_max)`

### 9.8 输出格式（控制区全轨迹）
建议每次 run 输出：
1. `control_zone_trace.csv`
   - `time,veh_id,stream,edge_id,lane_id,lane_pos,D_to_merge,speed,accel,v_des`
2. `metrics.json`
   - `merge_success_rate`（到达 merge point 的车辆中，成功进入下游的比例）
   - `avg_delay_at_merge`（`actual_arrival_time - t_min`）
   - `throughput`（单位时间通过 merge point 的数量）
   - `collision_count`
3. `collisions.csv`（用 `traci.simulation.getCollisions()`）

补充：`plans.csv/commands.csv/events.csv/config.json` 也是当前基线输出的一部分（见第 7 节）。

---

## 10) Stage 3 路网升级（灵活合流点需要“合流区间”）

Stage 3 开始才需要 merge zone。对路网有两种选择：
1. 新建 `ramp_min_v2`：增加“加速车道/辅助车道”形成可并入区间（更真实，也更符合你文档里的 L3）
2. 维持 `ramp_min_v1`：用“时间窗/空间窗”的方式在固定合流点附近模拟灵活性（更快，但物理意义弱）
默认走 1：因为后面要做 L1–L6、4 主线 2 匝道，迟早要处理 merge zone 的几何。

---

## 11) 现状冻结口径与必跑验证（Stage 1/2 基线，2026-02-23）

> 这一节是“跨文档一致”的最低口径：你只要记住这里，其他文档/代码细节都能对上。

### 11.1 冻结口径（跨文档一致）

- 三策略：`no_control / fifo / dp`
- 统一入口：`uv run python -m ramp.experiments.run`
- 默认输出目录：`output/<scenario>/<policy>/`（同 policy 覆盖；不同 policy 不覆盖）
- 步长：`--step-length 0.1`
- 控制区：`--control-zone-length-m 600`（只在控制区内接管）
- 过点判定：进入 `--merge-edge main_h4` 视为 cross merge
- FIFO：`--fifo-gap-s 1.5`，且目标时刻“入区冻结”
- DP：`--delta-1-s 1.5`，`--delta-2-s 2.0`，`--dp-replan-interval-s 0.5`（冻结 schedule，仍每步下发命令）
- “不让 SUMO 当裁判”：控制区内车辆接管 `speedMode=23`，释放时恢复
- `D_to_merge`：优先用 `traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)`（避免 internal edge `:n_merge*` 跳大值）

### 11.2 必跑回归（headless）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 11.3 必跑回归（GUI）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 11.4 plans.csv 约束检查

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

# dp：按 delta_1/delta_2 检查（同帧按 order_index）
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/dp/plans.csv --delta-1-s 1.5 --delta-2-s 2.0

# fifo：只保证 fifo_gap_s；用 delta_2=delta_1=fifo_gap_s 来查
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/fifo/plans.csv --delta-1-s 1.5 --delta-2-s 1.5
```

### 11.5 定点排查（当 GUI 看到“顺序不对/吞吐异常”）

优先用三类落盘数据对齐“计划-命令-现实”：
- `events.csv`：时间线上发生了什么（`plan_recompute/speedmode_takeover/commit_vehicle/cross_merge/...`）
- `commands.csv`：同一时刻到底给了谁什么速度命令/是否 release
- GUI：对照该时刻真实车位关系（谁已进入 internal edge、谁先占了冲突区）

必要时用分析脚本自动生成“mismatch 报告”，再按报告给出的时刻在 GUI 暂停对齐：
```bash
uv run python -m ramp.experiments.dump_mismatch_report --dir output/ramp_min_v1/dp --out output/ramp_min_v1/dp/mismatch_report.csv --window-s 1.0
```

> 回归命令与历史关键结果的权威记录仍以主仓库 `docs/RAMP_VALIDATION.md` 为准。
