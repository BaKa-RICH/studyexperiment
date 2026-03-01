---
name: 阶段B Runtime适配
overview: 在 StateCollector/Controller/command_builder 中实现 lane 过滤（E-ctrl-1）、laneChangeMode 分角色设置、aux lane stream_vmax 切换为 25.0，并跑通三策略验证。所有改动参数化，Policy/Core Algorithm 层零改动。
todos:
  - id: B1-cli-params
    content: Step1：在 run.py 新增 --control-mode / --ramp-lc-target-lane / --aux-vmax-mps 并透传
    status: completed
  - id: B2-lane-filter
    content: Step2：在 StateCollector.collect() 实现 E-ctrl-1 lane 过滤（核心）
    status: completed
  - id: B3-lanechange-mode
    content: Step3：在 Controller 实现 laneChangeMode 分角色设置（主线禁换道、匣道只到lane1）
    status: completed
  - id: B4-aux-vmax
    content: Step4：改造 _stream_vmax 感知 aux lane，4份副本统一增加 aux_vmax_mps 参数
    status: completed
  - id: B5-verify
    content: Step5：集成验证 + 三策略基线矩阵（lane过滤/换道限制/指标对比）
    status: completed
isProject: false
---

# 阶段B（L1）Runtime 适配计划（带验证点）

参考格式：阶段A计划的 "Step-by-step TODOLIST（每个 TODO 都有验证点）"。

## 阶段B范围

- **只改 Runtime 层**：[state_collector.py](ramp/runtime/state_collector.py)、[controller.py](ramp/runtime/controller.py)、[run.py](ramp/experiments/run.py)
- **Policy/Core Algorithm 层零改动**：`scheduler/dp.py`、`scheduler/arrival_time.py`、`fifo/scheduler.py` 不动
- **command_builder 需要传参变化**：`fifo/command_builder.py` 和 `dp/command_builder.py` 的 `_stream_vmax()` 需要感知 aux_vmax（B3）

场景：`ramp__mlane_v2`（阶段A已完成落地与 L0 验证）

规格来源：[docs/SCENARIO_RAMP_PAPER0_MLANE_V1_SPEC.md](docs/SCENARIO_RAMP_PAPER0_MLANE_V1_SPEC.md) 第 6.1 / 6.2 / 5.4 / 11.3 节

---

## Step 1：新增 CLI 参数并透传到各组件

### 1.1 在 run.py 的 argparse 中新增 3 个参数

- TODO 1.1：在 [run.py](ramp/experiments/run.py) 的 `main()` 中 argparse 部分（L654-676）新增：
  - `--control-mode`（choices=`["E-ctrl-1", "E-ctrl-2"]`，default=`"E-ctrl-1"`）
  - `--ramp-lc-target-lane`（type=int，default=`1`，`-1` 表示不限制）
  - `--aux-vmax-mps`（type=float，default=`25.0`）
- 在 `run_experiment()` 函数签名（L130-146）同步新增这 3 个参数
- 在 `run_experiment()` 调用 `StateCollector(...)` 处（L253-260）传入 `control_mode` 和 `aux_vmax_mps`
- 在构造 `Controller(...)` 处（L272）传入 `ramp_lc_target_lane`
- 在调用 `build_fifo_command(...)` 和 `build_dp_command(...)` 处传入 `aux_vmax_mps`
- 在 `config` 字典（L626-643）中记录这 3 个新参数
- 验证点：`uv run python3 -m ramp.experiments.run --help` 能看到 `--control-mode`、`--ramp-lc-target-lane`、`--aux-vmax-mps` 三个新选项及其默认值。

---

## Step 2：实现 lane 过滤（B1 核心）

### 2.1 在 StateCollector 中加 control_mode 字段和过滤逻辑

- TODO 2.1：在 [state_collector.py](ramp/runtime/state_collector.py) 的 `StateCollector` dataclass（L78-95）中新增字段 `control_mode: str`（默认 `"E-ctrl-1"`）
- TODO 2.2：在 `collect()` 方法的循环中（L110-114 距离过滤之后），插入 lane 过滤逻辑。实现规格 6.1 的伪代码：

```python
if self.control_mode == "E-ctrl-1":
    lane_id = traci.vehicle.getLaneID(veh_id)
    edge_id = road_id
    lane_index = int(lane_id.split("_")[-1]) if "_" in lane_id else -1
    is_conflict_lane = (
        (stream == "ramp" and edge_id in {"ramp_h6", "main_h3"} and lane_index in {0, 1}) or
        (stream == "main" and ((edge_id == "main_h2" and lane_index == 0) or (edge_id == "main_h3" and lane_index == 1)))
    )
    if not is_conflict_lane:
        continue
```

注意：`lane_id` 在后面 L148 也要用到，提前获取避免重复调 TraCI。internal edge（以 `:` 开头的 road_id）上的车辆可以直接放行——它们正在通过 junction，不应被过滤掉。因此 `is_conflict_lane` 判断应只在非 internal edge 时生效。

- 验证点 A：跑 `--policy no_control --control-mode E-ctrl-1 --seed 1 --duration-s 300`，从 `control_zone_trace.csv` 统计 `(stream, lane_id)` 分布，确认 `main_h3_2/3/4` 上的 `stream=main` 行**为 0**。
- 验证点 B：同上命令改 `--control-mode E-ctrl-2`，确认 `main_h3_2/3/4` 上的 `stream=main` 行**恢复存在**（与阶段A行为一致）。

---

## Step 3：实现 laneChangeMode 分角色设置（B2）

### 3.1 在 Controller 中增加 laneChangeMode 管理

- TODO 3.1：在 [controller.py](ramp/runtime/controller.py) 的 `Controller` dataclass（L18-22）新增字段 `ramp_lc_target_lane: int`（默认 `1`）
- TODO 3.2：在 `Controller` 中新增方法 `apply_lane_change_modes(self, *, control_zone_state, traci)`，在每个仿真步调用。逻辑：
  - 遍历 `control_zone_state` 中的车辆
  - 对 `stream=main` 且 `edge_id` 为 `main_h3` 的车：设 `traci.vehicle.setLaneChangeMode(veh_id, 0)`（禁止所有换道）
  - 对 `stream=ramp` 且 `lane_id` 为 `main_h3_0` 的车：保持默认（允许向右侧 lane1 换道）
  - 对 `stream=ramp` 且 `lane_id` 为 `main_h3_1`（已完成换道）且 `ramp_lc_target_lane != -1` 的车：设 `traci.vehicle.setLaneChangeMode(veh_id, 0)`（到达目标 lane 后禁止继续换道）
  - 对 `stream=ramp` 且 `lane_id` 为 `main_h3_1` 且 `ramp_lc_target_lane == -1` 的车：不做限制
- TODO 3.3：在 [run.py](ramp/experiments/run.py) 的主循环中（L303 `state_collector.collect()` 之后），调用 `controller.apply_lane_change_modes(control_zone_state=..., traci=traci)`
- 验证点 A：跑 `--policy no_control --ramp-lc-target-lane 1 --seed 1 --duration-s 300`，从 trace 统计确认 `(stream=ramp, lane_id=main_h3_2)` 和 `(stream=ramp, lane_id=main_h3_3)` 行数**为 0 或极少**（对比阶段A的 212/93 行）。
- 验证点 B：跑 `--ramp-lc-target-lane -1`，确认匝道车仍出现在 lane2/3 上（参数生效、限制解除）。

---

## Step 4：实现 aux lane stream_vmax 切换（B3）

### 4.1 改造 _stream_vmax 为感知 lane 的版本

当前代码中有 4 份 `_stream_vmax()` 副本（[state_collector.py](ramp/runtime/state_collector.py) L18-23、[dp/scheduler.py](ramp/policies/dp/scheduler.py) L11-16、[fifo/command_builder.py](ramp/policies/fifo/command_builder.py) L6-11、[dp/command_builder.py](ramp/policies/dp/command_builder.py) L6-11）。

- TODO 4.1：为 `_stream_vmax()` 增加两个可选参数 `aux_vmax_mps` 和 `lane_id`。当 `stream == "ramp"` 且 `lane_id` 以 `main_h3`_ 开头时，返回 `aux_vmax_mps`；否则返回 `ramp_vmax_mps`。4 个副本都需改动，签名统一为：

```python
def _stream_vmax(
    stream: str,
    main_vmax_mps: float,
    ramp_vmax_mps: float,
    *,
    aux_vmax_mps: float | None = None,
    lane_id: str = "",
) -> float:
    if stream == "main":
        return main_vmax_mps
    if stream == "ramp":
        if aux_vmax_mps is not None and lane_id.startswith("main_h3_"):
            return aux_vmax_mps
        return ramp_vmax_mps
    return max(main_vmax_mps, ramp_vmax_mps)
```

- TODO 4.2：在所有调用 `_stream_vmax()` 的地方传入 `aux_vmax_mps` 和 `lane_id`：
  - [state_collector.py](ramp/runtime/state_collector.py) L126：fifo natural_eta 计算时（此处 `lane_id` 需要从 traci 获取，注意此时车辆刚进入控制区，lane_id 可能还在 ramp_h6 上，此时应用 ramp_vmax）
  - [dp/scheduler.py](ramp/policies/dp/scheduler.py) L62：t_min 计算时（`lane_id` 从 `control_zone_state[veh_id]['lane_id']` 获取）
  - [fifo/command_builder.py](ramp/policies/fifo/command_builder.py) L30：v_des 上限（同上）
  - [dp/command_builder.py](ramp/policies/dp/command_builder.py) L30：v_des 上限（同上）
- TODO 4.3：`StateCollector` 新增 `aux_vmax_mps: float | None` 字段（默认 `None`，None 时保持旧行为）
- TODO 4.4：`DPScheduler`、`build_fifo_command()`、`build_dp_command()` 的函数签名增加 `aux_vmax_mps` 参数
- 验证点 A：跑 `--policy fifo --aux-vmax-mps 25.0 --seed 1 --duration-s 300`，检查 `plans.csv` 中匝道车（stream=ramp）在 `main_h3` 上的 `natural_eta` 是否比用 16.7 估算的更小。
- 验证点 B：跑 `--aux-vmax-mps 16.7`（等价于旧行为），确认 `natural_eta` 与阶段A结果一致。

---

## Step 5：集成验证 + 三策略基线矩阵（B4）

### 5.1 单 seed 冒烟

- TODO 5.1：跑以下 3 条命令（全部使用新默认参数），确认退出码均为 0：

```bash
uv run python3 -m ramp.experiments.run --scenario ramp__mlane_v2 --policy no_control --duration-s 300 --seed 1
uv run python3 -m ramp.experiments.run --scenario ramp__mlane_v2 --policy fifo --duration-s 300 --seed 1
uv run python3 -m ramp.experiments.run --scenario ramp__mlane_v2 --policy dp --duration-s 300 --seed 1
```

- 验证点：三个命令全部退出码 0，输出目录各含 7 个文件。

### 5.2 lane 过滤行为验证

- TODO 5.2：从 fifo/dp 的 `control_zone_trace.csv` 中统计 `(stream, lane_id)` 分布
- 验证点 A：`(stream=main, lane_id=main_h3_2/3/4)` 行数为 0（E-ctrl-1 过滤生效）
- 验证点 B：`(stream=main, lane_id=main_h2_0)` 和 `(stream=main, lane_id=main_h3_1)` 行数大于 0（冲突车道被控制）
- 验证点 C：`(stream=ramp, lane_id=main_h3_0)` 和 `(stream=ramp, lane_id=main_h3_1)` 行数大于 0（匝道车 aux + 已换道都被控制）

### 5.3 laneChangeMode 行为验证

- TODO 5.3：从 fifo/dp 的 `control_zone_trace.csv` 中统计
- 验证点：`(stream=ramp, lane_id=main_h3_2)` 和 `(stream=ramp, lane_id=main_h3_3)` 行数为 0 或极少（匝道车不再漂移到 lane2/3）

### 5.4 指标对比

- TODO 5.4：对比 `no_control` / `fifo` / `dp` 的 `metrics.json`
- 验证点 A：`collision_count` 三策略均为 0
- 验证点 B：`fifo` 和 `dp` 的 `avg_delay_at_merge_s` 或 `throughput_veh_per_h` 与 `no_control` 有明显差异（确认控制在起作用）

### 5.5 seeds 基线矩阵（可选，建议做）

- TODO 5.5：跑 `seed=1..5` x `no_control/fifo/dp`，共 15 次
- 验证点：dp 在所有 seed 下 `collision_count=0`

---

## 阶段B完成定义（Done）

- lane 过滤（E-ctrl-1）参数化落地，`--control-mode` 可切换
- laneChangeMode 分角色设置落地，`--ramp-lc-target-lane` 可切换
- aux lane stream_vmax=25.0 落地，`--aux-vmax-mps` 可切换
- 三策略在新场景跑通，控制行为正确（lane2/3/4 不被控速，匝道车不漂移）
- 项目可直接进入 Stage 3（算法迭代 / paper0 16 组扫参）

## 涉及改动的文件汇总

- [ramp/experiments/run.py](ramp/experiments/run.py)：新增 3 个 CLI 参数 + 透传 + config 记录
- [ramp/runtime/state_collector.py](ramp/runtime/state_collector.py)：新增 `control_mode`/`aux_vmax_mps` 字段 + lane 过滤逻辑 + `_stream_vmax` 改造
- [ramp/runtime/controller.py](ramp/runtime/controller.py)：新增 `ramp_lc_target_lane` 字段 + `apply_lane_change_modes()` 方法
- [ramp/policies/fifo/command_builder.py](ramp/policies/fifo/command_builder.py)：`_stream_vmax` 增加 aux 感知 + `build_command` 签名加 `aux_vmax_mps`
- [ramp/policies/dp/command_builder.py](ramp/policies/dp/command_builder.py)：同上
- [ramp/policies/dp/scheduler.py](ramp/policies/dp/scheduler.py)：`_stream_vmax` 增加 aux 感知 + `_compute_plan_once`/`DPScheduler` 签名加 `aux_vmax_mps`

