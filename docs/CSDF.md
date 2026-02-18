# CSDF（纯 SUMO 论文复现）说明

## 目标与范围

`CSDF/` 复现论文：*A homogeneous multi-vehicle cooperative group decision-making method in complicated mixed traffic scenarios*（见 `CSDF/README.md`）。

代码做了简化（原作者在 README 里已经说明）：
- 未实现原文 HDV 动态风险公式
- 未考虑定位误差/通信延迟对风险场影响
- 未加入 CAV/HDV 碰撞冲突消解
- 仅当检测到 TTC 小于阈值才触发算法

## 核心模块（代码层）

目录：
- `CSDF/core/`
  - 数据结构与坐标变换（Cartesian/Frenet）
- `CSDF/modules/`
  - `CavMonitor/`：场景监控与风险检测，产出候选决策域/风险等级等
  - `BehaviorPlanning/CSDF.py`：行为规划（基于风险场/决策域）
  - `TrajectoryPlanning/BazierTrajectory.py`：轨迹生成（Bezier）
  - `TrajectoryExecutor/TrajectoryExecutor.py`：TraCI 轨迹执行（moveToXY + setSpeed）

## 场景与输入文件

`CSDF/scene_4/`：
- `scene4.sumocfg`：仿真主配置（step-length=0.05）
- `road.net.xml`：路网
- `scene4.rou.xml`：车辆/vType/route，包含关键车辆 ID：
  - CAV：`cav_3_0`、`cav_2_0`、`cav_2_1`
  - HDV：`hdv_3_0` 等

## 运行与“预期效果”

当仿真进入危险态势（例如 `hdv_3_0` 降速后导致 TTC 风险上升），`SceneMonitor` 会把风险等级提升到高风险（通常是 level 3/4），从而触发：
1. 行为规划：选择动作/区域
2. 轨迹规划：为相关 CAV 生成轨迹点序列
3. 轨迹执行：将 CAV 移动到轨迹点（并可设速度）

直观现象：
- CAV 会出现“非跟驰的轨迹纠偏/换道/避让”式行为（取决于规划输出）
- 日志会出现若干 “bp/tp computation time ...”
- 若轨迹执行完成，会打印 “车辆 xxx 已完成轨迹执行”

## 批跑输出 CSV（`CSDF/batch_run.py`）

`vehicle_trace_*.csv` 字段：
- `time, veh_id, type_id, vclass, lane_id, route_id, x, y, speed, angle`

`collisions_*.csv` 字段：
- `time, collider, victim, ...`（字段随 SUMO 版本可能变化，脚本做了防御性导出）

## SUMO 版本兼容性

你当前环境为 SUMO 1.18.0。`road.net.xml` 里部分 lane allow/disallow 列表包含 1.18.0 不认识的 vClass（例如 `drone`），会导致 SUMO 直接退出。

`CSDF/batch_run.py` 会在 `CSDF/sumo_data/sumo_cfg/` 中生成一个兼容版 net+cfg 来运行，避免你修改原始 `CSDF/scene_4/road.net.xml`。

