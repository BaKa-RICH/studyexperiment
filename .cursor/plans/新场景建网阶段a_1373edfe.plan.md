---
name: 新场景建网阶段A
overview: 按 SCENARIO_RAMP_PAPER0_MLANE_V1_SPEC.md 的 L0 门槛完成新多车道场景的 SUMO 文件落地与零代码可运行验证（含 net/rou/sumocfg 结构验收 + 纯 SUMO 冒烟 + no_control 产出验收）。
todos:
  - id: A0-freeze-naming
    content: Step0：冻结阶段A唯一口径（场景名/文件名/硬约束）
    status: completed
  - id: A1-nod-edg-con
    content: Step1：落地 .nod/.edg/.con 源文件（三组连接约束）
    status: completed
  - id: A2-netconvert-verify
    content: Step2：netconvert 生成 net.xml 并按规范 10.1 验收（含 internal speed 检查）
    status: completed
  - id: A3-rou-verify
    content: Step3：编写 rou.xml（per-lane flow）并按规范 10.2 验收
    status: completed
  - id: A4-sumocfg-smoke
    content: Step4：编写 sumocfg 并完成纯 SUMO 冒烟（GUI + headless）
    status: completed
  - id: A5-L0-nocontrol
    content: Step5：L0 门槛：零代码 no_control 跑通并产出完整输出 + aux d_to_merge 抽样验收
    status: completed
isProject: false
---

# 阶段A（L0）新场景建网落地计划（带验证点）

参考格式：[docs/PLAN_RAMP_STAGE1.md](docs/PLAN_RAMP_STAGE1.md) 的 “Step-by-step TODOLIST（每个 TODO 都有验证点）”。

## 阶段A范围

- **只做 L0（纯 SUMO 层 + 零代码运行）**：先把路网/车流/配置落盘并可跑通。
- **不进入 L1**：不做任何 runtime 适配（`laneChangeMode` 角色化、lane 过滤、`d_to_merge` 兜底）——这些留到阶段B。

场景规范来源：[docs/SCENARIO_RAMP_PAPER0_MLANE_V1_SPEC.md](docs/SCENARIO_RAMP_PAPER0_MLANE_V1_SPEC.md)

目标场景名（建议固定）：`ramp__mlane_v2`

目标目录：`ramp/scenarios/ramp__mlane_v2/`

---

## Step 0：冻结阶段A“唯一口径”（避免做到一半再改名）

- TODO 0.1：冻结场景名与文件名
  - 约定：目录与 `.sumocfg` 同名（规范 2.1）
    - `ramp/scenarios/ramp__mlane_v2/ramp__mlane_v2.sumocfg`
  - 约定：中间产物也同前缀（便于追溯）
    - `ramp__mlane_v2.nod.xml / .edg.xml / .con.xml / .net.xml / .rou.xml`
  - 验证点：目录下能看到上述文件名（允许先占位，后续补内容）。
- TODO 0.2：冻结“硬约束”清单（来自规范第2节）
  - 必须包含：`main_h1 main_h2 main_h3 main_h4 ramp_h5 ramp_h6`、`n_merge`、`merge_edge=main_h4`、route 首边前缀 `main`*/`ramp`*。
  - 验证点：这 4 条硬约束被写进你本次评审用的 checklist（后续验收直接逐条勾）。

---

## Step 1：落地 nodes/edges/connects 源文件（可重复生成 net.xml）

### 1.1 节点 `.nod.xml`

- TODO 1.1：编写 `ramp__mlane_v2.nod.xml`
  - 节点（规范 4.2.1）：
    - 主线：`n_main_0(0,0) n_main_1(200,0) n_main_2(500,0) n_merge(800,0) n_main_3(1000,0)`
    - 匝道：`n_ramp_0(153.5898,-200) n_ramp_1(240.1924,-150)`
  - 验证点：用任意方式查看节点坐标，满足主线长度分段 200/300/300/200，匝道 H5=100、H6=300。

### 1.2 边 `.edg.xml`

- TODO 1.2：编写 `ramp__mlane_v2.edg.xml`
  - 边（规范 4.2.2）：
    - `main_h1/main_h2/main_h4`：4 lanes，`speed=25`
    - `main_h3`：5 lanes（含 aux lane0），`speed=25`
    - `ramp_h5/ramp_h6`：2 lanes，`speed=16.7`
    - `ramp_h6 to="n_main_2"`（进入合流区入口）
  - 验证点：`edg.xml` 内每条 edge 的 `numLanes` 与 speed 与规范一致。

### 1.3 连接 `.con.xml`（阶段A最关键）

- TODO 1.3：编写 `ramp__mlane_v2.con.xml`，显式约束 3 组连接（规范 4.4）
  - **主线 4→5（main_h2 -> main_h3）**：
    - `main_h2 lane0 -> main_h3 lane1`
    - `main_h2 lane1 -> main_h3 lane2`
    - `main_h2 lane2 -> main_h3 lane3`
    - `main_h2 lane3 -> main_h3 lane4`
    - 禁止任何 `main_h2 -> main_h3 lane0`
  - **匝道 2→1（ramp_h6 -> main_h3）**：
    - `ramp_h6 lane0 -> main_h3 lane0`
    - `ramp_h6 lane1 -> main_h3 lane0`
  - **n_merge（main_h3 -> main_h4）**：
    - `main_h3 lane0` 无下游连接（aux 终止）
    - `main_h3 lane1-4 -> main_h4 lane0-3` 依次对齐
  - 验证点：`con.xml` 中能逐条找到上述映射；不存在“主线流入 aux lane0”的连接。

---

## Step 2：netconvert 生成 `net.xml` 并做结构验收（对齐规范 10.1）

- TODO 2.1：用 `netconvert` 从 `.nod/.edg/.con` 生成 `ramp__mlane_v2.net.xml`
  - 建议命令（示意）：
    - `netconvert --node-files=ramp__mlane_v2.nod.xml --edge-files=ramp__mlane_v2.edg.xml --connection-files=ramp__mlane_v2.con.xml --no-turnarounds -o ramp__mlane_v2.net.xml`
  - 验证点 A：`netconvert` 退出码为 0，无致命错误。
  - 验证点 B：`sumo -n ramp__mlane_v2.net.xml --no-step-log true -v` 退出码为 0。
- TODO 2.2：按规范 `10.1 路网检查（net.xml）` 做 checklist 验收
  - 必查项（逐条勾）：
    - edge id 包含：`main_h1 main_h2 main_h3 main_h4 ramp_h5 ramp_h6`
    - junction id 包含：`n_merge`，并存在 internal edges `:n_merge`_*
    - lane 数：`main_h1/main_h2/main_h4=4`，`main_h3=5`，`ramp_h5/ramp_h6=2`
    - 连接映射满足 1.3 的三组约束（主线不进 aux；匝道进 aux；aux 在 n_merge 终止）
  - 验证点：对照 `net.xml` 的 `<edge>/<lane>` 与 `<connection>` 能找到上述证据。
- TODO 2.3：检查 internal edge 限速异常（对齐规范 5.3 / 10.1-6）
  - 重点检查：匝道入合流区入口处 internal connector、`n_merge` 内部边。
  - 验证点：关键 internal lanes 的 `speed` 不出现明显异常低值（例如个位数 m/s），除非你明确要模拟急弯低速。

---

## Step 3：编写 `.rou.xml`（per-lane flow）并做车流验收（对齐规范 10.2）

- TODO 3.1：编写 `ramp__mlane_v2.rou.xml`
  - 必须包含（规范 7.2）：
    - `main_route`：`main_h1 main_h2 main_h3 main_h4`
    - `ramp_route`：`ramp_h5 ramp_h6 main_h3 main_h4`
    - vType：`cav`（建议 `sigma=0.0`，其余可沿用 `ramp_min_v1` 的参数口径）
    - 主线 per-lane flows：`flow_main_L0..L3`（`departLane="0..3"`）
    - 匝道 per-lane flows：`flow_ramp_R0`（`departLane="0"`，v1 设 0），`flow_ramp_R1`（`departLane="1"`）
  - 验证点 A（规范 10.2-1/2）：route 首 edge 前缀分别是 `main`_ 和 `ramp`_。
  - 验证点 B（规范 10.2-3/4）：flow 使用显式 `departLane`；匝道出流固定 `departLane="1"`，另一条 lane 流量为 0。
- TODO 3.2：先用“起步中低流量”做 L0 冒烟
  - 建议（便于先跑稳）：`q_main_vphpl=1200`，`q_ramp_vphpl=500`（后续再切换 paper0 的 16 组扫参）。
  - 验证点：headless 跑完不出现卡死/大量碰撞；若失败先降 `q_ramp_vphpl`。

---

## Step 4：编写 `.sumocfg` 并做纯 SUMO 冒烟（GUI + headless）

- TODO 4.1：编写 `ramp__mlane_v2.sumocfg`
  - 必须包含：
    - `<net-file value="ramp__mlane_v2.net.xml"/>`
    - `<route-files value="ramp__mlane_v2.rou.xml"/>`
  - 验证点：`sumo -c ramp__mlane_v2.sumocfg --no-step-log true --quit-on-end true` 退出码为 0。
- TODO 4.2：GUI 检查“方式B真实换道”确实发生
  - 命令示例：`sumo-gui -c ramp__mlane_v2.sumocfg --start`
  - 验证点：能观察到匝道车进入 `main_h3 lane0`（aux）后，在 `main_h3` 区间内换到 `lane1` 并进入 `main_h4`。
- TODO 4.3：headless 冒烟检查无 GUI 也可跑
  - 命令示例：`sumo -c ramp__mlane_v2.sumocfg --no-step-log true --quit-on-end true`
  - 验证点：退出码 0；若有 deadlock/大量碰撞，先回到 Step 2/3 检查连接/限速/流量。

---

## Step 5：L0 门槛：零代码 `no_control` 跑通并产出完整输出（对齐规范 10.4）

> 这里允许“运行现有 Python 实验入口”，但不允许改任何 Python 代码；其目的只是验证新场景与当前流水线兼容。

- TODO 5.1：用现有入口跑 `no_control`（不改代码）
  - 命令示例（示意）：
    - `uv run python -m ramp.experiments.run --scenario ramp__mlane_v2 --policy no_control --duration-s 300 --step-length 0.1 --seed 1`
  - 验证点 A：运行完成退出码 0。
  - 验证点 B：输出目录存在且包含完整文件集（参考现有 `output/ramp_min_v1/no_control/` 的同名文件）：
    - `control_zone_trace.csv / collisions.csv / plans.csv / commands.csv / events.csv / metrics.json / config.json`
- TODO 5.2：aux `d_to_merge` L0 抽样验收（规范 10.4-2）
  - 方法建议：从 `control_zone_trace.csv` 或运行日志里抽样检查在 `lane_id=main_h3_0`（aux）的匝道车 `D_to_merge` 字段。
  - 验证点：不得出现系统性 `-1/极大值/大量缺失`；若发现异常，只记录为阶段B的必修项（不在阶段A修）。

---

## 阶段A完成定义（Done）

- 新目录 `ramp/scenarios/ramp__mlane_v2/` 内的 `net/rou/sumocfg` 已落盘且通过 **规范 10.1/10.2** 结构验收。
- 纯 SUMO（GUI + headless）能稳定跑完。
- L0：`no_control` 零代码运行能跑完并产出完整输出文件；aux `d_to_merge` 抽样检查完成并记录结论（正常/异常）。

