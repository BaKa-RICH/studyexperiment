# 多车协同轨迹规划系统

本文件夹包含了基于Frenet坐标系的多车协同轨迹规划系统，从原有的单车规划系统改进而来。

## 主要文件说明

### 1. Scene4_main_mv.py
- **功能**: 主程序入口，集成SUMO和Carla仿真环境
- **主要改进**: 
  - 使用`MultiVehicleTrajectoryPlanner`替代单车规划器
  - 支持多车协同决策（左变道、右变道、保持车道）
  - 输出文件名改为`planned_trajectories_multi_vehicle.csv`

### 2. Solver_multi.py
- **功能**: 多车协同优化求解器
- **主要特性**:
  - `MultiVehicleFrenetPlanner`类：支持多车同时优化
  - 车间避撞约束：所有车辆对之间的碰撞检测
  - 协同目标函数：平衡速度、舒适性和安全性
  - 并行求解：同时为所有车辆生成轨迹

### 3. trajectory_plannner_multi.py
- **功能**: 多车协同轨迹规划器
- **主要特性**:
  - `MultiVehicleTrajectoryPlanner`类：协调多车规划流程
  - 自动识别需要协同规划的高风险车辆
  - 为每辆车创建独立的Frenet坐标转换器
  - 统一的轨迹输出格式

### 4. CoordinateTransform.py
- **功能**: Cartesian与Frenet坐标系转换
- **说明**: 与原版相同，支持位置、速度、加速度和航向角转换

### 5. test_multi_vehicle.py
- **功能**: 系统测试脚本
- **用途**: 验证多车规划系统的基本功能

### 6. trajectory_executor.py
- **功能**: 轨迹执行脚本
- **用途**: 读取csv数据，按规划的轨迹移动车辆


## 使用方法

1. **规划：场景中设置了三辆车，其中一辆为高风险**:
   ```bash
   python Scene4_main_mv.py
   ```
生成planned_trajectories_multi_vehicle.csv

2. **执行: 读取planned_trajectories_multi_vehicle.csv**:
   ```bash
   python trajectory_executor.py
   ```



# 更新：加入了背景车流 


模块速览
--------
- ``offline_planner.py``
  离线批处理规划器，读取单个 SUMO CSV 快照（如 ``result*.csv``），
  在指定时间戳重建自车及关键障碍物，求解多车优化问题，并生成插值后的轨迹 CSV 供后续可视化。

- ``offline_planner_left.py``
  离线规划器的便捷变体，针对预设的左车道对向卡车对（``lead_truck_01`` 与 ``lead_truck_02``）。
  当无需修改主规划器即想快速复现相同 CSV 的左侧场景时使用。

- ``Solver_multi.py``
  基于 CasADi/Ipopt 的核心求解器，构建耦合的 Frenet 最优控制问题，
  施加车辆运动学与安全椭圆约束，输出每辆车的最优多项式系数。

- ``replay.py``
  轻量级可视化工具，在 SUMO 中重放规划轨迹（原始或优化版本），
  读取生成的 CSV，生成车辆实例，并在不重新运行求解器的前提下保持与 SUMO 同步。

工作流程
--------
1. 在 SUMO 中导出碰撞复现结果为 ``result*.csv``（包含车辆 ID、时间戳、x/y、速度、航向、车道、车型等）。
2. 运行 ``offline_planner.py``（或 ``offline_planner_left.py``）：
   - 加载 CSV 与 SUMO ``road.net.xml``；
   - 将自车与障碍物投影至 Frenet 坐标系；
   - 调用 ``Solver_multi.py`` 求解协调避撞方案；
   - 输出 20 Hz 插值的 ``planned_trajectories_offline.csv``。
3. 运行 ``replay.py``，在 SUMO 中同时对比原始与避撞后的轨迹表现。