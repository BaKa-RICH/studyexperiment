# 项目概览（纯 SUMO 视角）

本仓库包含多种交通仿真/规划相关代码。你当前路线是 **纯 SUMO**（不使用 CARLA），因此本文档只聚焦 SUMO 可直接运行的部分，并把与 CARLA 强绑定的内容标注为“可忽略”。

## 目录结构（与纯 SUMO 相关）

- `CSDF/`
  - 论文复现：*A homogeneous multi-vehicle cooperative group decision-making method in complicated mixed traffic scenarios*。
  - **纯 SUMO**：通过 TraCI 驱动 SUMO，检测风险(TTC)触发行为规划与轨迹规划，然后执行轨迹控制。
  - 入口：
    - `CSDF/main.py`：原始交互式跑法（默认 GUI）。
    - `CSDF/batch_run.py`：批量跑 + 导出 CSV（我们新增）。
  - 场景/配置：
    - `CSDF/scene_4/scene4.sumocfg`：SUMO 配置
    - `CSDF/scene_4/road.net.xml`：路网
    - `CSDF/scene_4/scene4.rou.xml`：车流/车辆定义（包含 `cav_3_0/cav_2_0/cav_2_1/hdv_3_0...`）
  - 输出：
    - `CSDF/sumo_data/vehicle_trace_*.csv`：轨迹采样
    - `CSDF/sumo_data/collisions_*.csv`：碰撞事件

- `Scene/`
  - 多个 SUMO 或 SUMO-CARLA 联合场景集合。
  - 纯 SUMO 可跑示例：
    - `Scene/scene10(Sumo)/Scene10_sumo v2.py`：TraCI 驱动的示例（可 headless）。

- `mutil_vehicle/`
  - 多车规划相关（仓库内说明为 CARLA-SUMO 联合仿真背景）。若你只做纯 SUMO，可暂时不看。

## 纯 SUMO 的“运行形态”

纯 SUMO 通常分两层：
1. `*.sumocfg`/`*.net.xml`/`*.rou.xml`：SUMO 原生输入（路网 + 车流/车辆）。
2. Python + TraCI：在仿真循环里 `traci.simulationStep()` 推进，并实时读取/控制车辆状态（速度、换道、位置等）。

本仓库的 `CSDF/` 和 `Scene/scene10(Sumo)/` 都属于这种模式。

## 关键配置文件类型

- `.sumocfg`：SUMO 主配置。指定路网(`net-file`)、车流(`route-files`)、step-length 等。
- `.net.xml`：路网（lane/edge/junction）。通常由 `netconvert` 生成。
- `.rou.xml`：route/flow/vehicle/vType 定义。
- `osm.view.xml`：GUI 显示设置（仅在 `sumo-gui` 时有用）。

## 依赖与环境（纯 SUMO）

- 你需要本机安装 SUMO（提供 `sumo`、`sumo-gui`、以及 `SUMO_HOME/tools` 里的 Python TraCI 工具）。
- Python 依赖由 `uv` 管理：`uv sync` 后使用 `uv run ...` 运行脚本。

下一步建议先看 `docs/RUNBOOK_SUMO.md`，再决定你是以 `CSDF` 论文复现为主，还是以 `Scene/*` 自定义场景为主。

