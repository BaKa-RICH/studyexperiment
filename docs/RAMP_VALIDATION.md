# RAMP 验证记录（必跑回归与历史结果）

目的：把“必须跑的验证命令”和“从 Step 0 到现在跑过哪些验证、结果如何”集中记录，避免信息散落在对话/临时输出里。

## 0. Stage 2.5 v1 基线（ramp=16.7m/s）

这份基线用于进入 Stage 3 前的“防退化锚点”：后续无论你怎么重构/换算法/换路网，都能用它判断是“算法变了”还是“世界变了”。

**基线版本号（git commit）**
- `dcd3386442662aaf8ee6eaff183247a2f027e364`（`ramp_min_v1.net.xml` 已回退到 ramp=16.7m/s 基线；此 commit 对应下面的矩阵口径）

**固定口径（v1）**
- `scenario=ramp_min_v1`
- `duration_s=120`，`step_length=0.1`
- `control_zone_length_m=600`，`merge_edge=main_h4`
- 控制区接管：`speedMode=23`（关闭路口通行权裁决位；离开控制区/释放时恢复）
- 三策略：`no_control` / `fifo` / `dp`
- FIFO：`fifo_gap_s=1.5`（入区一次分配 target 并冻结）
- DP：`delta_1_s=1.5`，`delta_2_s=2.0`，`dp_replan_interval_s=0.5`
- 算法侧限速：`main_vmax_mps=25`，`ramp_vmax_mps=16.7`

**验收阈值（Stage 2.5 冻结）**
- `dp`（硬门槛，seeds=1..5 全部满足）：`collision_count == 0`；`check_plans` 的 `gap_bad == 0` 且 `target_mono_bad == 0`；`consistency_merge_order_mismatch_count == 0`
- `fifo`（弱基线，不作为“顺序严格一致”的门槛）：`collision_count == 0`；`check_plans` 的 `gap_bad == 0` 且 `target_mono_bad == 0`；`consistency_merge_order_mismatch_count` 仅记录，不作为硬门槛（原因：main/ramp 物理速度上限不同，FIFO 作为弱基线不追求严格一致）

## 1. 必跑验证（每次改动都要过）

### 1.1 单测（只跑 ramp）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration
uv run pytest -q ramp/tests
```

### 1.2 Headless 回归（同 seed）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 1.3 plans.csv 约束检查（fifo/dp 口径不同）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

# dp：按 delta_1/delta_2 检查（同帧按 order_index）
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/dp/plans.csv --delta-1-s 1.5 --delta-2-s 2.0

# fifo：只保证 fifo_gap_s；用 delta_2=delta_1=fifo_gap_s 来查
uv run python -m ramp.experiments.check_plans --plans output/ramp_min_v1/fifo/plans.csv --delta-1-s 1.5 --delta-2-s 1.5
```

### 1.4 GUI 回归（重构前能跑，重构后也必须能跑）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

注意：GUI 调试如果你手动关闭 `sumo-gui` 窗口，脚本可能会异常退出，导致 `metrics.json/config.json` 等“仿真结束时写入”的文件缺失。需要完整输出时建议让仿真按 `--duration-s` 自然跑完。

### 1.5 输出完整性（最低要求）
每组输出目录至少包含：
- `control_zone_trace.csv`
- `collisions.csv`
- `metrics.json`
- `config.json`
- `plans.csv`
- `commands.csv`
- `events.csv`

### 1.6 Stage 2.5 基线矩阵（v1, ramp=16.7m/s, seeds=1..5）

说明：
- 这是“冻结基线”的矩阵回归：用于进入 Stage 3 前，或进行大重构/更改执行层/更改状态采集/更改 DP 口径后做一次全量复验。
- 输出目录按 seed 隔离：避免 `run.py` 发现目录存在就 `rmtree` 覆盖掉你想保留的结果。

#### 1.6.1 运行命令（policy x seed）
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

BASE=output/baseline_matrix/ramp_min_v1_ramp16p7

for seed in 1 2 3 4 5; do
  uv run python -m ramp.experiments.run \
    --scenario ramp_min_v1 \
    --policy no_control \
    --duration-s 120 \
    --step-length 0.1 \
    --seed "${seed}" \
    --control-zone-length-m 600 \
    --merge-edge main_h4 \
    --main-vmax-mps 25 \
    --ramp-vmax-mps 16.7 \
    --out-dir "${BASE}/seed${seed}/no_control"

  uv run python -m ramp.experiments.run \
    --scenario ramp_min_v1 \
    --policy fifo \
    --fifo-gap-s 1.5 \
    --duration-s 120 \
    --step-length 0.1 \
    --seed "${seed}" \
    --control-zone-length-m 600 \
    --merge-edge main_h4 \
    --main-vmax-mps 25 \
    --ramp-vmax-mps 16.7 \
    --out-dir "${BASE}/seed${seed}/fifo"

  uv run python -m ramp.experiments.run \
    --scenario ramp_min_v1 \
    --policy dp \
    --delta-1-s 1.5 \
    --delta-2-s 2.0 \
    --dp-replan-interval-s 0.5 \
    --duration-s 120 \
    --step-length 0.1 \
    --seed "${seed}" \
    --control-zone-length-m 600 \
    --merge-edge main_h4 \
    --main-vmax-mps 25 \
    --ramp-vmax-mps 16.7 \
    --out-dir "${BASE}/seed${seed}/dp"

  # 约束检查（注意 fifo/dp 口径不同）
  uv run python -m ramp.experiments.check_plans \
    --plans "${BASE}/seed${seed}/fifo/plans.csv" \
    --delta-1-s 1.5 \
    --delta-2-s 1.5 \
    > "${BASE}/seed${seed}/check_plans_fifo.json"

  uv run python -m ramp.experiments.check_plans \
    --plans "${BASE}/seed${seed}/dp/plans.csv" \
    --delta-1-s 1.5 \
    --delta-2-s 2.0 \
    > "${BASE}/seed${seed}/check_plans_dp.json"
done
```

#### 1.6.2 结果表（ramp=16.7m/s, seeds=1..5）

聚合（seed=1..5 的均值）：

|policy|throughput_avg (veh/h)|avg_delay_avg (s)|collision_count|dp/fifo check_plans|merge_order_mismatch_avg|cross_time_error_mean_avg (s)|cross_time_error_p95_avg (s)|备注|
|---|---:|---:|---:|---|---:|---:|---:|---|
|no_control|528.0|7.06|0|N/A|N/A|N/A|N/A|无计划；consistency 指标不适用|
|fifo|600.0|7.40|0|gap_bad=0, mono_bad=0|12.0|1.95|6.63|弱基线：mismatch 不作为门槛；seed=1..5 仅记录|
|dp|660.0|2.88|0|gap_bad=0, mono_bad=0|0.0|0.04|0.09|硬门槛：mismatch 必须为 0|

逐 seed（直接来自各目录 `metrics.json`；FIFO 的 emergency braking 次数来自控制台 warning 日志统计）：

|seed|policy|throughput (veh/h)|avg_delay_at_merge (s)|collision_count|merge_order_mismatch|cross_time_error_mean (s)|cross_time_error_p95 (s)|fifo emergency braking warnings|
|---:|---|---:|---:|---:|---:|---:|---:|---:|
|1|no_control|540|7.735|0|N/A|N/A|N/A|N/A|
|1|fifo|600|8.045|0|12|2.554|7.828|4|
|1|dp|660|3.152|0|0|0.038|0.094|0|
|2|no_control|510|9.432|0|N/A|N/A|N/A|N/A|
|2|fifo|600|7.390|0|13|2.034|6.428|1|
|2|dp|660|3.595|0|0|0.051|0.099|0|
|3|no_control|570|8.435|0|N/A|N/A|N/A|N/A|
|3|fifo|600|7.304|0|11|1.959|9.228|4|
|3|dp|660|3.229|0|0|0.045|0.099|0|
|4|no_control|540|8.498|0|N/A|N/A|N/A|N/A|
|4|fifo|600|6.788|0|12|1.366|4.028|3|
|4|dp|660|2.203|0|0|0.039|0.075|0|
|5|no_control|480|1.224|0|N/A|N/A|N/A|N/A|
|5|fifo|600|7.456|0|12|1.861|5.628|2|
|5|dp|660|2.244|0|0|0.038|0.099|0|

## 2. 额外验证（从 0 到现在都做过什么）

除了 “1. 必跑验证” 之外，实践中额外做过：
- `plans.csv` 快照查看工具验证：`uv run python -m ramp.experiments.dump_plans_snapshot --plans ... --time 40.1`
- mismatch 定点排查报告生成验证：`uv run python -m ramp.experiments.dump_mismatch_report ...`
- A/B 实验对照：通过备份 `output/ramp_min_v1/*_before_*` 保留“改动前输出”，再跑同 seed 对比指标变化
- 运行期信号检查：关注控制台 `emergency braking` warning 与 `collision_count`

## 3. 历史结果（可追溯）

说明：
- Step 0~Step 10 的完整“重构里程碑回归表”在 `docs/RAMP_REFACTOR_BLUEPRINT.md` 第 10 节。
- 下面只额外记录“与行为/假设直接相关的关键实验与修复”。

|时间|实验/修复|场景变化|fifo mismatch|dp mismatch|fifo throughput|dp throughput|备注|
|---|---|---|---:|---:|---:|---:|---|
|2026-02-23 00:25 CST|Step 9：一致性指标落盘|无|12|20|600/h|660/h|开始可量化“计划-执行一致性”|
|2026-02-23 16:28 CST|A/B：匝道限速抬到 25|`ramp_min_v1.net.xml` 中 ramp lane speed `16.70->25.00`（含 internal）|0（原 12）|20（原 20）|630/h（原 600/h）|660/h（不变）|证明 FIFO mismatch 主要来自 main/ramp 速度差导致的“先到先 commit”|
|2026-02-23 16:28 CST|修复：`D_to_merge` 用 `getDrivingDistance`|代码修复（见 `ramp/runtime/state_collector.py`）|0|0（原 20/22）|630/h|660/h|修复后 internal edge 上 `D_to_merge` 回到合理量级，DP mismatch 归零|
|2026-02-23|Stage 2.5 基线矩阵（ramp=16.7，seeds=1..5）|`ramp_min_v1.net.xml` 回退到 16.70（基线）|≈12（11..13）|0（硬门槛）|600/h|660/h|见上方 1.6：用于进入 Stage 3 前的冻结基线|
