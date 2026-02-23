# 工作记录（2026-02-17）：SUMO/uv 环境闭环（用 CSDF 验证）

定位：本文记录主要聚焦“依赖/环境/TraCI 兼容性”的闭环；后续在 `ramp/` 路线中也直接复用了这些结论。

## 1. 发生了什么（按时间）

### 1.1 `uv sync` 失败：找不到本地 CARLA wheel

症状：
- `uv sync` 报错：`Distribution not found at: ... assets/carla-0.10.0-...-win_amd64.whl`

原因：
- `pyproject.toml` 的 `[tool.uv.sources]` 把 `carla` 强制指向一个 Windows wheel 路径，但仓库里并没有这个文件。
- `uv.lock` 也锁定了这个本地路径依赖，导致即使你不打算用 CARLA，也会被解析阶段卡住。

修复：
- 移除了 `pyproject.toml` 中 `carla` 的本地 wheel source，并从 `dependency-groups.full` 移除 `carla==0.9.15`：
  - `pyproject.toml:26`
  - `pyproject.toml:88`
- 同步调整 `uv.lock`，让 `swarmplanner` 的 base deps 不再要求 `carla`：
  - `uv.lock:1595`
- 当时 README 补充说明：CARLA Python API 需要按平台单独安装，不随 `uv sync` 自动装（后续 README 已重构为 `ramp/` 主线，不再维护 CARLA 相关说明）。

结果：
- 你手动重新运行 `uv sync` 成功安装依赖。

### 1.2 纯 SUMO 下一步：跑 CSDF 并导出 CSV

你的目标：
- 批量跑一个场景并导出轨迹/碰撞 CSV（纯 SUMO，不用 CARLA）。

实际过程与修复点：
1. `CSDF/` README 明确说明“没有与 CARLA 联合仿真，直接运行 main.py”。
2. 我新增 `CSDF/batch_run.py`：把 CSDF 的逻辑封装成可批跑的入口，并导出 CSV。
3. 跑起来后遇到 SUMO 直接退出：
   - `Unknown vehicle class 'drone' ...`
   - 原因：`CSDF/scene_4/road.net.xml` 的 lane allow/disallow 包含 SUMO 1.18.0 不认识的 vClass。
   - 解决：`CSDF/batch_run.py` 在运行时生成兼容版 net+cfg 到 `CSDF/sumo_data/sumo_cfg/`，不改原始路网文件。
4. 再跑遇到 TraCI 参数不兼容：
   - `moveToXY() got an unexpected keyword argument 'laneIndex'`
   - 原因：SUMO 1.18.0 的 TraCI `moveToXY(vehID, edgeID, lane, x, y, ...)` 参数名是 `lane`。
   - 修复：`CSDF/modules/TrajectoryExecutor/TrajectoryExecutor.py:101`

结果：
- 批跑成功产出 CSV：
  - `CSDF/sumo_data/vehicle_trace_20260217-154610.csv`
  - `CSDF/sumo_data/collisions_20260217-154610.csv`（该次仿真未发生碰撞，所以只有表头）

## 2. 我们能学到什么（可复用的工程经验）

### 2.1 明确“默认路线”

你明确要求：在你没说要 CARLA 之前，默认完全不用 CARLA。

落地做法：
- 将 CARLA 相关依赖从默认安装/锁文件中剥离，避免“只想跑 SUMO 却被 CARLA wheel 卡死”。

### 2.2 先跑通最短闭环，再做增强

闭环定义（纯 SUMO）：
- 能启动 SUMO（headless）
- TraCI 循环能推进
- 能导出可分析的数据（CSV）

我们先把 `CSDF` 的批跑跑通，再讨论更高阶内容（参数扫、指标计算、可视化等）。

### 2.3 遇到兼容性问题，用“生成兼容副本”替代“改原始数据”

路网 `.net.xml` 很大、来源可能是导出/转换，直接改容易引入不可追踪差异。

我们选择：
- 在 `CSDF/sumo_data/sumo_cfg/` 里生成“兼容副本”
- 保留原文件不动，便于回溯与对比

### 2.4 快速定位问题的套路

- 依赖安装失败：先查 `pyproject.toml` 的 sources 和 `uv.lock` 是否有“本地路径/平台限定”的硬引用。
- SUMO 启动失败：优先看 SUMO stderr 的第一条致命错误（通常原因很直接）。
- TraCI 报 TypeError：直接对照 `SUMO_HOME/tools/traci/_vehicle.py` 的函数签名。

## 3. 后续建议（纯 SUMO 路线）

你可以按优先级推进：
1. 固定 seed 批跑多次，确认结果可复现（CSV 规模、风险触发时刻）
2. 加一个简单的后处理脚本：统计每辆车的最小 TTC/最小间距、是否发生碰撞、规划触发次数
3. 把你真正关心的“预期效果”定义成可量化指标（否则很难判断“跑得对不对”）

## 4. 后续补充（2026-02-23）：这些经验如何复用到 RAMP

`ramp/` 已成为当前主线；但本文件里的“环境/兼容”结论在 RAMP 上同样成立：

1. 统一用 `uv run python ...` 跑实验入口（避免系统 Python/虚拟环境混用）。
2. 遇到 TraCI API 签名差异，优先对照 `SUMO_HOME/tools` 下的实现（而不是只看 PyPI 的 `traci` 文档）。
3. SUMO 报错/直接退出时，先看 stderr 第一条致命错误（通常就是真因）。
4. RAMP 的“必跑回归命令/约束检查”集中在 `docs/RAMP_VALIDATION.md`，不要把命令散落到临时笔记里。
