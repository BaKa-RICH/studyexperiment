# RAMP（纯 SUMO）匝道合流实验框架

本仓库包含多种原型代码；当前维护的主线是 `ramp/`：基于 **SUMO + TraCI + Python(uv)** 的匝道合流实验框架，用于对比三种策略：

- `no_control`：SUMO 默认（不干预）
- `fifo`：FIFO 调度基线（入控制区冻结 target）
- `dp`：复现/移植 CAVSim 的 DP 调度（固定合流点）

## 快速开始

前置：
- 已安装 SUMO（`sumo` / `sumo-gui` 可用）
- 已安装 `uv`

安装依赖：
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration
uv sync --dev
```

## 运行（三种 policy）

Headless（推荐回归用）：
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

GUI（用于直观看行为与定点排查）：
```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

## 输出（默认）

默认输出目录为：`output/<scenario>/<policy>/`（同 policy 覆盖；不同 policy 不覆盖）。

每组至少包含：
- `control_zone_trace.csv`：每个仿真步、控制区内车辆的状态采样（字段见表头；核心包括 `D_to_merge/speed/accel/v_des`）
- `plans.csv`：每个仿真步的计划快照（passing order + 每车 `target_cross_time`；字段包括 `order_index/natural_eta/target_cross_time/gap_from_prev/v_des`）
- `commands.csv`：每个仿真步实际下发的控制命令快照（字段包括 `v_cmd_mps/release_flag`，用于核对“计划有没有真的下发到控制层”）
- `events.csv`：稀疏事件流（字段 `time,event,veh_id,detail`；用于和 GUI 做时间对齐排查）
- `metrics.json`：汇总指标（吞吐/延误/成功率/碰撞/停车次数 + 一致性指标 `consistency_*`）
- `collisions.csv`：碰撞事件（字段见表头；0 碰撞也会生成表头）
- `config.json`：本次 run 的参数快照（用于复现；包含 `scenario/policy/duration/step-length/seed/merge_edge/vmax/delta/.../output_dir`）

## 验证（必须跑）

必跑回归与 `plans.csv` 约束检查命令统一写在：`docs/RAMP_VALIDATION.md`。

## 文档索引（只维护 ramp 相关）

建议阅读顺序：
1. `../RAMP_SUMO_PLAN.md`：整体计划（仓库外，位于 `/home/liangyunxuan/src/RAMP_SUMO_PLAN.md`）
2. `docs/RAMP_VALIDATION.md`：必跑回归命令 + 历史结果（以此为准，不要在别处手抄命令）
3. `docs/RAMP_REFACTOR_BLUEPRINT.md`：当前 `ramp/` 架构与关键口径（Simulation/State/Schedule/Command/Control/Record）
4. `docs/PLAN_RAMP_STAGE1.md`：Stage 1 基线与输出/指标冻结口径
5. `docs/PLAN_RAMP_STAGE2.md`：Stage 2（DP）规格、参数与验证点

## `ramp/` 目录结构（核心）

- `ramp/experiments/`：实验入口与分析小工具
- `ramp/experiments/run.py`：主入口（驱动 SUMO + 每步采集状态 + 调度 + 下发控制 + 落盘输出）
- `ramp/experiments/check_plans.py`：对 `plans.csv` 做约束检查（按 `time` 分组、同帧按 `order_index` 检查相邻 gap）
- `ramp/experiments/dump_plans_snapshot.py`：打印某一帧的计划快照（用于快速确认 main/ramp 交织顺序）
- `ramp/experiments/dump_mismatch_report.py`：生成 mismatch 报告（用 `events/commands/plans` 定点对齐 GUI）
- `ramp/scenarios/`：SUMO 场景资源（`*.net.xml/*.rou.xml/*.sumocfg`）；最小场景在 `ramp/scenarios/ramp_min_v1/`
- `ramp/runtime/`：运行时通用层（仿真推进/状态采集/控制下发/数据结构）
- `ramp/runtime/simulation_driver.py`：只管 `traci.start/simulationStep/close` 与时钟推进
- `ramp/runtime/state_collector.py`：只管从 TraCI 采集状态并构造“控制区车辆集合 + 入口信息”等
- `ramp/runtime/controller.py`：只管把命令下发为 TraCI 调用（`setSpeed`、控制区接管 `speedMode=23`、释放恢复、commit 边界）
- `ramp/runtime/types.py`：核心数据结构（`Plan/ControlCommand/...`）
- `ramp/policies/`：策略层（按 policy 分目录：`no_control/ fifo/ dp/`）
- `ramp/policies/*/scheduler.py`：调度逻辑（状态 -> `Plan`）
- `ramp/policies/*/command_builder.py`：执行目标构造（`Plan` -> `ControlCommand`；当前是 `target_cross_time -> v_des`）
- `ramp/scheduler/`：纯算法层（与 SUMO/TraCI 解耦）
- `ramp/scheduler/arrival_time.py`：`t_min` 计算（CAVSim ArrivalTime 两段式公式 + 边界保护）
- `ramp/scheduler/dp.py`：DP 调度核心 `dp_schedule`（对应 CAVSim DPMethod 思路）
- `ramp/tests/`：单元测试（主要覆盖 DP 算法层的正确性与对照 brute-force；`uv run pytest -q ramp/tests`）
