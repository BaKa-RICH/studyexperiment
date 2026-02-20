# Stage 2 实施计划：复现/移植 CAVSim 的 DP 调度（固定合流点）

本文件是 `RAMP_SUMO_PLAN.md` 的 **Stage 2** 具体落地清单，目标是：

1. 在同一条最小路网 `ramp_min_v1` 上，把 CAVSim 的 DP（Dynamic Programming）调度思想移植到 Python
2. 合流点固定（冲突点），DP 围绕该点做“谁先过”的最优交织（main/ramp 两股流）
3. 在相同车流与随机种子下，对比 `no_control / fifo / dp` 的 delay/成功率/吞吐等指标

> 前置条件：Stage 1 已完成并冻结输出口径（见 `PLAN_RAMP_STAGE1.md` 的 “Stage 1 执行记录”）。

---

## Stage 2 Definition of Done（DoD）

满足以下条件即 Stage 2 完成：

1. 新增 policy：`dp` 能运行完成（>= 120s），且输出目录格式与 Stage 1 一致：
   - `control_zone_trace.csv`
   - `collisions.csv`
   - `metrics.json`
   - `config.json`
   - `plans.csv`（建议 dp/fifo 都有；no_control 可只有表头）
2. `dp` 的 `plans.csv` 可验证安全时间间隔约束：
   - 相邻两车若同流：`t_{k} - t_{k-1} >= delta_1`
   - 相邻两车若异流：`t_{k} - t_{k-1} >= delta_2`
3. `dp` 调度核心（纯算法层）通过“小规模暴力枚举对照测试”（确保 DP 输出是最优）
4. 对比实验可复现：同 `seed`、同 `flow` 下 `no_control / fifo / dp` 三组都跑通并生成可解析的 `metrics.json`

---

## Stage 2 固定约定（避免歧义）

### 1) 调度模块归属
- DP 属于 **调度/序列模块（Scheduler）**：输入是两股流的队列与车辆 `t_min`，输出是 passing order + 期望过合流点时间（target cross time）。

### 2) 合流点与控制区
- 固定合流点（冲突点）：`merge_edge = "main_h4"`（进入该 edge 视为“过合流点”）
- 控制区定义：`D_to_merge <= control_zone_length_m`（Stage 1 默认 `150m`）
- `D_to_merge` 的实现继续沿用 Stage 1（route edges 剩余长度累加）

### 3) 时间间隔参数（来自 CAVSim）
对齐 CAVSim `TestingRelated/DPMethod.h`：
- `delta_1 = 1.5s`（同一股流连续通过）
- `delta_2 = 2.0s`（不同股流交替通过）

### 4) 最小可达时间 t_min（来自 CAVSim）
对齐 CAVSim `TestingRelated/ArrivalTime.cpp` 的 `CalculMinimumArrivalTimeAtOnRamp()`：
- 输入：当前时刻 `t_now`，距合流点距离 `D`，当前速度 `v`，最大加速度 `a_max`，最大速度 `v_max`
- 输出：最小可达时间 `t_min`
- 公式（两段式）：
  1. 若加速不到 `v_max`：`t_min = t_now + (sqrt(v^2 + 2 a_max D) - v) / a_max`
  2. 若能加速到 `v_max` 后巡航：`t_min = t_now + (v_max - v)/a_max + (D - (v_max^2 - v^2)/(2 a_max))/v_max`

实现细节建议（Stage 2 先固定，后续可扩展）：
- `a_max` 从 SUMO vType 读取（`traci.vehicle.getAccel(veh_id)`），避免写死
- `v_max` 仍用 Stage 1 的流上限（main/ramp 分别 `25.0/16.7 m/s`），便于对齐论文与后续扫参

### 5) 队列内部顺序（对齐 CAVSim OriginSeqList）
- main 队列：控制区内 `stream=main` 的车辆，按 `t_enter_control_zone` 升序（稳定，不允许重排）
- ramp 队列：控制区内 `stream=ramp` 的车辆，按 `t_enter_control_zone` 升序（稳定，不允许重排）

---

## Step-by-step TODOLIST（每个 TODO 都有验证点）

### Step 1：抽取 CAVSim 参考实现并写成“可移植规格”

- [ ] TODO 1.1：把 CAVSim 的 DP 变量定义与递推写成 Python 伪代码（存放在本文档或单独 notes）
  - 参考文件：
    - `/home/liangyunxuan/src/CAVSim/TestingRelated/DPMethod.cpp`
    - `/home/liangyunxuan/src/CAVSim/TestingRelated/DPMethod.h`
  - 验证点：能明确回答三个问题
    - DP 的 state 是什么（`(m, n, last_lane)`）
    - transition 怎么算（`t = max(t_min, pre_t + delta)` + cost 累积）
    - objective 是什么（CAVSim 实际用 `time + delay` 作为比较量）

- [ ] TODO 1.2：把 `t_min` 公式确认无歧义（并确定 Python 实现的输入来自 SUMO 哪些字段）
  - 参考文件：`/home/liangyunxuan/src/CAVSim/TestingRelated/ArrivalTime.cpp`
  - 验证点：写出 3 个边界情况的期望行为
    - `D=0` 时 `t_min == t_now`
    - `a_max` 很大时 `t_min` 接近 `t_now + D/max(v,eps)`（极限情况）
    - `v >= v_max` 时进入“巡航”分支应合理（不出现负时间）

---

### Step 2：实现纯算法层（不接 SUMO）并做最小正确性验证

> 目标：先证明 DP 解法对小规模输入是“最优”的，再接入 TraCI。

- [ ] TODO 2.1：实现 `dp_schedule(main_ids, ramp_ids, t_min, delta_1, delta_2)`（返回 passing order + 每车 target_cross_time）
  - 验证点：
    - 对 `main=1..3, ramp=1..3` 的随机 `t_min`，DP 输出可生成一条合法 schedule
    - schedule 中相邻两车满足 delta_1/delta_2 约束

- [ ] TODO 2.2：实现 brute-force 枚举对照（仅用于小规模测试）
  - 验证点：
    - 对 `main<=3, ramp<=3`，DP 输出的 objective 与 brute-force 最优一致
    - 至少 50 组随机测试通过（固定随机种子便于复现）

> 说明：这一条是 Stage 2 的关键“可信度”来源，避免后面在 SUMO 里调半天发现 DP 写错。

---

### Step 3：接入 SUMO（新增 policy=dp），输出口径与 Stage 1 对齐

- [ ] TODO 3.1：在现有 `ramp/experiments/run.py` 中新增 `--policy dp`
  - 行为：
    - 每次 replan 时构建 main/ramp 两队列
    - 用当前状态计算每车 `t_min`
    - 调用 `dp_schedule` 得到 `target_cross_time`
    - 对控制区内车辆用 `setSpeed` 做速度跟踪（与 fifo 同策略）
  - 验证点：
    - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 60 --seed 1 --out-dir /tmp/ramp-stage2/dp` 能跑完
    - 输出目录内至少包含 `control_zone_trace.csv/collisions.csv/metrics.json/config.json/plans.csv`

- [ ] TODO 3.2：定义 replan 触发（Stage 2 先简单，后续可优化）
  - 推荐（Stage 2 默认）：
    - “有新车进入控制区”或“有车过合流点”时触发重算
    - 仍保留 `replan_interval_s` 作为上限（例如 0.1s），但无事件不强行重算
  - 验证点：`plans.csv` 中不会出现“同一时刻对同一车辆重复写入大量相同计划”（避免日志爆炸）

- [ ] TODO 3.3：`plans.csv` 扩展字段（让 dp 可审计）
  - 建议字段（至少）：
    - `time,entry_rank,order_index,veh_id,stream,t_enter_control_zone,D_to_merge,speed,t_min,target_cross_time,gap_from_prev,v_des`
  - 验证点：
    - 能从 `plans.csv` 复算并验证 delta_1/delta_2 约束
    - 能从 `plans.csv` 看出 passing order（main/ramp 交织）

---

### Step 4：与 Stage 1 基线对比（同 seed/同流量）

- [ ] TODO 4.1：固定 3 条对比命令（同 `seed`、同 `duration`）
  - `no_control`
  - `fifo`（gap_s=1.5）
  - `dp`（delta_1=1.5, delta_2=2.0）
  - 验证点：三次输出目录都齐全，`metrics.json` 可解析

- [ ] TODO 4.2：对比指标（不要求 dp 一定“更好”，但必须“有差异且合理”）
  - 验证点：
    - `metrics.json` 至少在 `avg_delay_at_merge_s/throughput_veh_per_h/stop_count` 中某些项表现出差异
    - `merge_success_rate` 不应异常掉到很低（低流量下应接近 1，注意 pending_unfinished 口径）

---

### Step 5：Stage 2 的烟雾测试（保留为回归命令集）

> Stage 2 开始后，每次改 DP 都先跑这几条，防止把 Stage 1 回归打坏。

- [ ] TODO 5.1：Smoke：`dp` 运行 20s
  - 命令（示例）：`SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 20 --seed 1 --out-dir /tmp/ramp-stage2/smoke-dp`
  - 验证点：
    - 输出文件齐全
    - `plans.csv` 存在且有数据行

- [ ] TODO 5.2：Regression：同 seed 重跑 dp 两次，关键指标不应漂太大
  - 验证点：两次 `metrics.json` 的关键指标差异很小（完全相同不强求）

---

## 常见问题（Stage 2 快速排查）

1. dp 跑起来但吞吐极低
   - 检查是否把 `target_cross_time` 每步重算导致“追不上目标”（建议只在 replan 时更新）
   - 检查 `t_min` 是否算得过大（例如把 `a_max` 取成 0 或单位错误）

2. dp 计划违反 delta 约束
   - 优先用 `plans.csv` 复算约束，定位到底是 DP 输出错还是“执行层追踪没跟上”

3. dp 和 fifo 指标几乎完全一样
   - 检查 dp 是否真的在做 interleaving（passing order 是否发生 main/ramp 交织）
   - 检查 dp 是否退化成“按 entry_rank 直接排队”（没有用 t_min/delta 做优化）

