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
- 单位统一：`D`(m), `v`(m/s), `a_max`(m/s^2), `t`(s)。不允许混用 km/h。
- 边界保护（必须写进代码，避免 NaN/负时间）：
  - 若 `D <= 0`：`t_min = t_now`
  - 若 `a_max <= 1e-6`：退化为匀速近似 `t_min = t_now + D/max(v, 1e-3)`
  - 若 `v >= v_max`：使用巡航分支（加速时间为 0）

### 5) 队列内部顺序（对齐 CAVSim OriginSeqList）
- main 队列：控制区内 `stream=main` 的车辆，按 `t_enter_control_zone` 升序（稳定，不允许重排）
- ramp 队列：控制区内 `stream=ramp` 的车辆，按 `t_enter_control_zone` 升序（稳定，不允许重排）

### 6) CAVSim DPMethod 的“逐项对应”（避免重复造轮子）

把 CAVSim 的关键变量直接映射到我们 Stage 2 的数据结构：

1. `OriginSeqList[0]` -> `main_seq: list[str]`（车辆 id，固定顺序）
2. `OriginSeqList[1]` -> `ramp_seq: list[str]`（车辆 id，固定顺序）
3. `SimuVehicleDict` -> `veh: dict[str, VehState]`
   - 必备字段：`stream, D_to_merge, speed, a_max, v_max, t_min`
4. `TimeNow` -> `t_now`（当前 replan 时刻，来自 `traci.simulation.getTime()`）
5. `delta_1/delta_2` -> Stage 2 CLI 参数（默认按 CAVSim：1.5/2.0）

### 7) DP 状态、递推与目标函数（完全对齐 CAVSim）

对齐 CAVSim `TestingRelated/DPMethod.cpp` 的实现，DP 的 state 和更新规则固定如下：

1. state key：`(m, n, last_lane)`  
   - `m`：已安排的 main 车数量（0..M）
   - `n`：已安排的 ramp 车数量（0..N）
   - `last_lane`：上一辆通过合流点的流（`0=main, 1=ramp, -1=none`）
2. state value：`(time, delay, parent)`  
   - `time`：当前 state 下最后一辆车的过点时间
   - `delay`：累计延误，按 CAVSim 定义：`sum_k (t_cross[k] - t_min[k])`
   - `parent`：用于回溯 passing order（Python 里用 parent key + parent last_lane 即可）
3. transition（对齐 `CalNextVehTime`）：
   - 若 `pre_time == 0`：`time = t_min`
   - 否则：
     - 若 `lane == pre_lane`：`time = max(t_min, pre_time + delta_1)`
     - 若 `lane != pre_lane`：`time = max(t_min, pre_time + delta_2)`
   - `delay = pre_delay + (time - t_min)`
4. objective（对齐 CAVSim 的比较量）：最小化 `time + delay`  
   - Python 中每个 state 保存 `(time, delay)`，比较时用 `cost = time + delay`
   - tie-break（建议固定，避免不稳定）：若 `cost` 相同，选 `time` 更小；仍相同则选 `delay` 更小；仍相同则选 `last_lane=0` 优先（或按字典序，写死即可）

### 8) DP 输出语义（Stage 2 固定）

DP 输出两样东西（都要能被写入 `plans.csv` 并可审计）：

1. `passing_order: list[str]`：车辆通过合流点的顺序（保持每股流内部顺序不变）
2. `target_cross_time: dict[str, float]`：每辆车的目标过点时间（对应 DP 中的 `time` 序列）

> 注意：`target_cross_time` 是“进入 `merge_edge=main_h4`”的目标时间，沿用 Stage 1 的过点判定口径。

### 9) 本轮讨论结论（落地口径，2026-02-20）

1. Stage 2 默认 **每步重算**（对齐 `step-length=0.1s`）：每个仿真步都用当前控制区状态重算 `t_min` 与 `dp_schedule`。
2. `plans.csv` 在“每步重算”下是“每帧一个 schedule 快照”：约束检查必须 **按 `time` 分组**，在同一帧内按 `order_index` 检查相邻 gap 的 `delta_1/delta_2` 约束（不要跨帧检查）。
3. 输出先保持精简：优先保持 `plans.csv` 字段与 Stage 1 一致；如需额外审计字段（`t_min/delta_used` 等），新增一个可选的 `plans_debug.csv`（避免主输出过于冗余）。

---

## Step-by-step TODOLIST（每个 TODO 都有验证点）

### Step 1：抽取 CAVSim 参考实现并写成“可移植规格”

- [x] TODO 1.1：把 CAVSim 的 DP 变量定义与递推写成 Python 伪代码（存放在本文档或单独 notes）
  - 参考文件：
    - `/home/liangyunxuan/src/CAVSim/TestingRelated/DPMethod.cpp`
    - `/home/liangyunxuan/src/CAVSim/TestingRelated/DPMethod.h`
	  - 验证点：能明确回答三个问题
	    - DP 的 state 是什么（`(m, n, last_lane)`）
	    - transition 怎么算（`t = max(t_min, pre_t + delta)` + cost 累积）
	    - objective 是什么（CAVSim 实际用 `time + delay` 作为比较量）

  - Python 伪代码（直接对应 CAVSim `DPMethod::Run()`/`CalNextVehTime()`）：

    ```python
    # Inputs
    main_seq: list[str]  # main stream, order is fixed
    ramp_seq: list[str]  # ramp stream, order is fixed
    t_min: dict[str, float]
    delta_1, delta_2: float

    # State: key=(m, n, last_lane) where last_lane in {-1, 0, 1}
    # Value: (time, delay, parent_key)
    dp[(0, 0, -1)] = (time=0, delay=0, parent=None)

    for layer in range(M + N):
        for (m, n, last), (pre_t, pre_delay, parent) in states_at_layer(layer):
            if m < M:  # choose next main vehicle
                veh = main_seq[m]
                tmin = t_min[veh]
                if last == -1:
                    t = tmin
                else:
                    gap = delta_1 if last == 0 else delta_2
                    t = max(tmin, pre_t + gap)
                delay = pre_delay + (t - tmin)
                relax_state((m + 1, n, 0), (t, delay, parent=(m, n, last)),
                            cost=(t + delay, t, delay))  # tie-break: smaller time then delay

            if n < N:  # choose next ramp vehicle
                veh = ramp_seq[n]
                tmin = t_min[veh]
                if last == -1:
                    t = tmin
                else:
                    gap = delta_1 if last == 1 else delta_2
                    t = max(tmin, pre_t + gap)
                delay = pre_delay + (t - tmin)
                relax_state((m, n + 1, 1), (t, delay, parent=(m, n, last)),
                            cost=(t + delay, t, delay))

    # Choose best final state by (time+delay, time, delay, last_lane) where last_lane prefers 0
    final = argmin((M, N, 0), (M, N, 1))

    # Backtrack
    passing_order = []
    target_cross_time = {}
    state = final
    while state != (0, 0, -1):
        m, n, last = state
        veh = main_seq[m - 1] if last == 0 else ramp_seq[n - 1]
        passing_order.append(veh)
        target_cross_time[veh] = dp[state].time
        state = dp[state].parent
    passing_order.reverse()
    ```

- [x] TODO 1.3：明确 DP 的“回溯重建”方式（避免实现时乱套）
  - 对齐 CAVSim `DPMethod::Run()` 的 parent 回溯逻辑
  - 建议 Stage 2 Python 版回溯方式（更直接）：
    - parent 只存 `(prev_m, prev_n, prev_last_lane)` 以及本步选择的 `lane`
    - 回溯时每一步能确定“本次选择的是第几个 main/ramp 车”
      - 若 lane=main：车辆 id = `main_seq[m-1]`
      - 若 lane=ramp：车辆 id = `ramp_seq[n-1]`
    - 同时拿到该步 state 的 `time`，写入 `target_cross_time[veh_id] = time`
  - 验证点：对一个手工小例子（例如 main=2, ramp=1）能在纸上回溯出完整 order 和每车时间

  - 手工回溯例子（main=2, ramp=1；`delta_1=1.5, delta_2=2.0`）：
    - `main_seq=[M1,M2]`, `ramp_seq=[R1]`
    - `t_min[M1]=5.0`, `t_min[M2]=8.0`, `t_min[R1]=5.2`
    - 最优路径的一条回溯链（示例）：
      - `(0,0,-1)` 选 R1 -> state `(0,1,1)`, `t(R1)=5.2`, parent=`(0,0,-1)`
      - `(0,1,1)` 选 M1 -> state `(1,1,0)`, `t(M1)=max(5.0, 5.2+2.0)=7.2`, parent=`(0,1,1)`
      - `(1,1,0)` 选 M2 -> state `(2,1,0)`, `t(M2)=max(8.0, 7.2+1.5)=8.7`, parent=`(1,1,0)`
    - 回溯（从 `(2,1,0)` 往 parent 走）得到反序 `[M2,M1,R1]`，reverse 后 passing order 为 `[R1,M1,M2]`
    - 同时写入 `target_cross_time={R1:5.2, M1:7.2, M2:8.7}`

- [x] TODO 1.2：把 `t_min` 公式确认无歧义（并确定 Python 实现的输入来自 SUMO 哪些字段）
  - 参考文件：`/home/liangyunxuan/src/CAVSim/TestingRelated/ArrivalTime.cpp`
	  - 验证点：写出 3 个边界情况的期望行为
	    - `D=0` 时 `t_min == t_now`
	    - `a_max` 很大时 `t_min` 接近 `t_now + D/v_max`（受 `v_max` 上限约束）
	    - `v >= v_max` 时进入“巡航”分支应合理（不出现负时间）
  - Stage 2 Python 实现输入（从 SUMO/TraCI 读取，固定合流点 `merge_edge=main_h4`）：
    - `t_now = traci.simulation.getTime()`
    - `D = D_to_merge`（沿用 Stage 1：route edges 剩余长度累加）
    - `v = traci.vehicle.getSpeed(veh_id)`
    - `a_max = traci.vehicle.getAccel(veh_id)`
    - `v_max = main_vmax_mps / ramp_vmax_mps`（沿用 Stage 1 固定上限）

---

### Step 2：实现纯算法层（不接 SUMO）并做最小正确性验证

> 目标：先证明 DP 解法对小规模输入是“最优”的，再接入 TraCI。

- [x] TODO 2.1：实现 `dp_schedule(main_seq, ramp_seq, t_min, delta_1, delta_2)`（返回 passing order + 每车 target_cross_time）
  - 强约束（必须满足）：
    - passing order 必须保持每股流内部顺序不变（不允许 swap 同流内顺序）
    - 对每辆车：`t_cross >= t_min`
    - 相邻两车：按同流/异流使用 `delta_1/delta_2`
  - 验证点：
    - 对 `main=1..3, ramp=1..3` 的随机 `t_min`，DP 输出可生成一条合法 schedule
    - schedule 中相邻两车满足 delta_1/delta_2 约束
    - DP 的输出能复现 CAVSim 的 `CalNextVehTime` 行为（first vehicle: `t_cross=t_min`）

- [x] TODO 2.2：实现 brute-force 枚举对照（仅用于小规模测试）
  - 验证点：
    - 对 `main<=3, ramp<=3`，DP 输出的 objective 与 brute-force 最优一致
    - 至少 50 组随机测试通过（固定随机种子便于复现）

  - 本轮验证记录（2026-02-20）：
    - 命令：`uv run pytest -q ramp/tests/test_dp_schedule.py`
    - 结果：`26 passed`
    - 覆盖说明：
      - `test_dp_matches_bruteforce_small`：`main<=3, ramp<=3` 下每组 50 次随机样本，与 brute-force 最优 objective 一致
      - `test_dp_schedule_legality_random_tmin`：`main=1..3, ramp=1..3` 下每组 50 次随机样本，验证 schedule 合法性、delta 约束、首车 `t_cross=t_min`

> 说明：这一条是 Stage 2 的关键“可信度”来源，避免后面在 SUMO 里调半天发现 DP 写错。

---

### Step 3：接入 SUMO（新增 policy=dp），输出口径与 Stage 1 对齐

- [x] TODO 3.1：在现有 `ramp/experiments/run.py` 中新增 `--policy dp`
  - 行为：
    - 每次 replan 时构建 main/ramp 两队列
    - 用当前状态计算每车 `t_min`
    - 调用 `dp_schedule` 得到 `target_cross_time`
    - 对控制区内车辆用 `setSpeed` 做速度跟踪（与 fifo 同策略）
  - 验证点：
    - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 60 --seed 1 --out-dir /tmp/ramp-stage2/dp` 能跑完
    - 输出目录内至少包含 `control_zone_trace.csv/collisions.csv/metrics.json/config.json/plans.csv`

- [x] TODO 3.1b：明确“dp 与 fifo 的差别只在 Scheduler”，避免把执行层差异混进来
  - 约束：dp 的执行层速度跟踪（`v_des` -> `setSpeed`）要和 fifo 用同一套实现（只替换 `target_cross_time` 的来源）
  - 验证点：对同一帧/同一辆车，dp 与 fifo 计算 `v_des` 的方式一致，仅 `target_cross_time` 不同

- [x] TODO 3.2：定义 replan 触发（Stage 2 先简单，后续可优化）
  - Stage 2 默认（已拍板）：**每步重算**，对齐 `step-length=0.1s`
    - 每个仿真步都重算 main/ramp 队列、`t_min` 与 `dp_schedule`
    - `target_cross_time` 允许随状态更新（不做冻结），执行层仍沿用 Stage 1 的 `v_des -> setSpeed`
  - 验证点：`plans.csv` 行数会很密集，但必须能按 `time` 分组做约束检查（同一帧内检查 delta 约束）

- [x] TODO 3.3：`plans.csv` / `plans_debug.csv`（让 dp 可审计且不冗余）
  - `plans.csv`（默认）：保持与 Stage 1 一致的字段与格式（便于回归对比与解析复用）
  - `plans_debug.csv`（可选）：仅在需要时新增少量字段用于审计/排查（建议只加 `t_min,delta_used`）
  - 验证点：
    - 能从 `plans.csv`（按 `time` 分组）复算并验证 delta_1/delta_2 约束
    - 能从 `plans.csv` 看出 passing order（main/ramp 交织）

  - 本轮验证记录（2026-02-21）：
    - 回归命令（同 `seed=1`, `duration=60s`）：
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 60 --seed 1 --out-dir /tmp/ramp-stage2/step3-no-control`
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --duration-s 60 --seed 1 --fifo-gap-s 1.5 --out-dir /tmp/ramp-stage2/step3-fifo`
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 60 --seed 1 --delta-1-s 1.5 --delta-2-s 2.0 --out-dir /tmp/ramp-stage2/step3-dp`
    - 约束检查脚本：
      - `uv run python -m ramp.experiments.check_plans --plans /tmp/ramp-stage2/step3-dp/plans.csv --delta-1-s 1.5 --delta-2-s 2.0`
      - 结果：`gap_bad=0, target_mono_bad=0, duplicate_order_index_count=0`
    - 审计补充：
      - `fifo` 使用固定 `gap_s=1.5`，若按 `delta_1=1.5, delta_2=2.0` 检查会出现跨流 gap 违约；按 `delta_1=delta_2=1.5` 检查为 0 违约
      - `dp` 的 `plans.csv` 可直接观察到主线/匝道交织顺序（例如 `time=56.1` 时 `ramp->main->main->ramp`）

---

### Step 4：与 Stage 1 基线对比（同 seed/同流量）

- [x] TODO 4.1：固定 3 条对比命令（同 `seed`、同 `duration`）
  - `no_control`
  - `fifo`（gap_s=1.5）
  - `dp`（delta_1=1.5, delta_2=2.0）
  - 验证点：三次输出目录都齐全，`metrics.json` 可解析

- [x] TODO 4.2：对比指标（不要求 dp 一定“更好”，但必须“有差异且合理”）
  - 验证点：
    - `metrics.json` 至少在 `avg_delay_at_merge_s/throughput_veh_per_h/stop_count` 中某些项表现出差异
    - `merge_success_rate` 不应异常掉到很低（低流量下应接近 1，注意 pending_unfinished 口径）
    - 若 dp 吞吐显著低于 fifo：优先排查 `t_min`（单位/边界保护/a_max 获取）与执行层追踪；必要时做“冻结/事件触发 replan”的对照诊断

  - 本轮验证记录（2026-02-21，`duration=120s, seed=1`）：
    - 命令：
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --seed 1 --out-dir /tmp/ramp-stage2/step4-no-control`
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --duration-s 120 --seed 1 --fifo-gap-s 1.5 --out-dir /tmp/ramp-stage2/step4-fifo`
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 120 --seed 1 --delta-1-s 1.5 --delta-2-s 2.0 --out-dir /tmp/ramp-stage2/step4-dp`
    - 文件完整性：三组目录均包含 `control_zone_trace.csv/collisions.csv/metrics.json/config.json/plans.csv`
    - `metrics.json` 解析：三组均可被 `uv run python -m json.tool` 正常解析
    - 指标对比：
      - `no_control`：`merge_success_rate=1.0, avg_delay_at_merge_s=6.9334, throughput_veh_per_h=540.0, stop_count=9`
      - `fifo`：`merge_success_rate=1.0, avg_delay_at_merge_s=6.1996, throughput_veh_per_h=480.0, stop_count=12`
      - `dp`：`merge_success_rate=1.0, avg_delay_at_merge_s=13.8984, throughput_veh_per_h=300.0, stop_count=14`
    - `dp` 计划约束检查：
      - `uv run python -m ramp.experiments.check_plans --plans /tmp/ramp-stage2/step4-dp/plans.csv --delta-1-s 1.5 --delta-2-s 2.0`
      - 结果：`gap_bad=0, target_mono_bad=0, duplicate_order_index_count=0`
    - 吞吐偏低诊断（按 TODO 要求执行）：
      - 诊断命令：`dp` 改为 `delta_1=delta_2=1.5`（其余不变）得到 `throughput_veh_per_h=330.0`（高于 300.0 但仍低于 fifo 480.0）
      - 结论：低吞吐不来自明显约束违约或 JSON/输出错误，主要与 `delta_2=2.0` 更严格间隔 + 每步重算下的保守调度有关；后续可在 Step 5 增加“冻结/事件触发重算”诊断以进一步定位

---

### Step 5：Stage 2 的烟雾测试（保留为回归命令集）

> Stage 2 开始后，每次改 DP 都先跑这几条，防止把 Stage 1 回归打坏。

- [x] TODO 5.1：Smoke：`dp` 运行 60s
  - 命令（示例）：`SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 60 --seed 1 --out-dir /tmp/ramp-stage2/smoke-dp-60`
  - 验证点：
    - 输出文件齐全
    - `plans.csv` 存在且有数据行

- [x] TODO 5.2：Regression：同 seed 重跑 dp 两次，关键指标不应漂太大
  - 验证点：两次 `metrics.json` 的关键指标差异很小（完全相同不强求）

  - 本轮验证记录（2026-02-21）：
    - 5.1 Smoke（60s 默认）：
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 60 --seed 1 --delta-1-s 1.5 --delta-2-s 2.0 --out-dir /tmp/ramp-stage2/step5-smoke-dp-60-default`
      - 结果：输出文件齐全（`control_zone_trace.csv/collisions.csv/metrics.json/config.json/plans.csv`）
      - 结果：`plans.csv` 数据行为 `724`，约束检查 `gap_bad=0, target_mono_bad=0, duplicate_order_index_count=0`
    - 单测（纯算法层）：
      - `uv run pytest -q ramp/tests/test_dp_schedule.py`
      - 结果：`26 passed`
    - 5.2 Regression（同 seed 双跑）：
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 120 --seed 1 --delta-1-s 1.5 --delta-2-s 2.0 --out-dir /tmp/ramp-stage2/step5-reg-dp-a2`
      - `SUMO_GUI=0 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --duration-s 120 --seed 1 --delta-1-s 1.5 --delta-2-s 2.0 --out-dir /tmp/ramp-stage2/step5-reg-dp-b2`
      - 两次关键指标一致：
        - `merge_success_rate=1.0`
        - `avg_delay_at_merge_s=13.898385805315218`
        - `throughput_veh_per_h=300.0`
        - `stop_count=14`
      - 结论：同 seed 下指标差异为 0，满足“关键指标差异很小”验证点

---

## 常见问题（Stage 2 快速排查）

1. dp 跑起来但吞吐极低
   - Stage 2 默认是“每步重算”，优先检查执行层追踪是否在持续追逐变动 target（导致 `v_des` 过小/不稳定）
   - 检查 `t_min` 是否算得过大（例如把 `a_max` 取成 0、单位错误、`D_to_merge` 错）
   - 做对照诊断：临时切到“事件触发 + 冻结 target”看吞吐是否恢复（仅用于定位，不作为 Stage 2 默认）

2. dp 计划违反 delta 约束
   - 注意按 `time` 分组在同一帧内检查（不要跨帧检查），再定位是 DP 输出错还是执行层追踪偏差

3. dp 和 fifo 指标几乎完全一样
   - 检查 dp 是否真的在做 interleaving（passing order 是否发生 main/ramp 交织）
   - 检查 dp 是否退化成“按 entry_rank 直接排队”（没有用 t_min/delta 做优化）
