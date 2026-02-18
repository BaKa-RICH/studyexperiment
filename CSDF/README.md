### 复现的论文：A homogeneous multi-vehicle cooperative group decision-making method in complicated mixed traffic scenarios

做了一些简化：
1. 原文中的HDV动态风险公式有问题，这里没计算
2. 没考虑CAV的定位误差和通信延迟对风险场带来的影响（涉及到二重积分，代码实现比较麻烦）
3. 还没加CAV和HDV的碰撞冲突的消解
4. 只有检测到TTC小于阈值时才触发算法

目录说明：
1. core： 包含用到的字段定义和坐标变换

2. modules： 包含四个模块，场景监控器，行为规划器， 轨迹规划器， 轨迹执行器

3. scene_4中定义了车流文件

没有与CARLA联合仿真

直接运行main.py

#### 纯 SUMO 批量跑并导出 CSV

`CSDF/batch_run.py` 会运行 `scene_4/scene4.sumocfg`，在检测到风险（TTC 触发）后执行 CSDF 的行为规划与轨迹规划，并导出：
- `vehicle_trace_*.csv`: 每个仿真步所有车辆的 (x, y, speed, lane_id, route_id, ...)
- `collisions_*.csv`: SUMO 报告的碰撞事件

默认输出目录：`CSDF/sumo_data/`

示例（无 GUI，跑 30 秒仿真）：
```bash
UV_CACHE_DIR=/tmp/uv-cache SUMO_GUI=0 uv run python -m CSDF.batch_run --duration-s 30
```
