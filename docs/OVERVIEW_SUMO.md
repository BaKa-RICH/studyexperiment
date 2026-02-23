# 项目概览（RAMP 纯 SUMO 路线）

本仓库包含多种原型代码；当前维护的主线是 `ramp/`：基于 **SUMO + TraCI + Python(uv)** 的匝道合流实验框架（`no_control / fifo / dp`）。

## 你现在应该看什么（最短路径）

1. `ramp/`：代码主线（实验入口、场景、策略实现、运行时框架）
2. `docs/RAMP_VALIDATION.md`：必跑回归命令 + 历史关键结果
3. `docs/PLAN_RAMP_STAGE1.md`、`docs/PLAN_RAMP_STAGE2.md`：Stage 1/2 冻结口径（输出/指标/约束/参数）
4. `docs/RAMP_REFACTOR_BLUEPRINT.md`：当前 `ramp/` 的架构与数据流

## 目录结构（只列 ramp 相关）

- `ramp/experiments/`
  - 运行入口：`uv run python -m ramp.experiments.run`
  - 分析小工具：`dump_plans_snapshot.py`、`dump_mismatch_report.py` 等
- `ramp/scenarios/`
  - SUMO 场景文件：`*.net.xml/*.rou.xml/*.sumocfg`
  - 最小场景：`ramp/scenarios/ramp_min_v1/`
- `ramp/policies/`
  - 策略实现（按 policy 分目录）：`no_control/ fifo/ dp`
- `ramp/runtime/`
  - 仿真推进、状态采集、命令下发、记录/指标（通用层）

## 纯 SUMO 的“运行形态”（ramp 也是同样结构）

纯 SUMO 通常分两层：
1. `*.sumocfg`/`*.net.xml`/`*.rou.xml`：SUMO 原生输入（路网 + 车流/车辆）。
2. Python + TraCI：在仿真循环里 `traci.simulationStep()` 推进，并实时读取/控制车辆状态（速度、位置等）。

## 关键配置文件类型（SUMO）

- `.sumocfg`：SUMO 主配置。指定路网(`net-file`)、车流(`route-files`)、step-length 等。
- `.net.xml`：路网（lane/edge/junction）。
- `.rou.xml`：route/flow/vehicle/vType 定义。
- `*.gui.xml`：GUI 显示设置（仅 `sumo-gui` 时有用）。

## 依赖与环境（RAMP）

- 需要本机安装 SUMO（`sumo`、`sumo-gui` 可用；建议 `SUMO_HOME` 正确）。
- Python 依赖由 `uv` 管理：`uv sync` 后用 `uv run ...` 运行。

## 其他目录（当前不作为主线）

以下目录仍在仓库中，但当前文档与回归不以它们为主：
- `CSDF/`：论文复现与 TraCI 轨迹执行原型（见 `docs/CSDF.md`）
- `Scene/`：历史场景集合
- `mutil_vehicle/`：CARLA-SUMO 联合仿真背景下的多车规划原型
