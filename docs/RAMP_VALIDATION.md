# RAMP 验证记录（必跑回归与历史结果）

目的：把“必须跑的验证命令”和“从 Step 0 到现在跑过哪些验证、结果如何”集中记录，避免信息散落在对话/临时输出里。

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
