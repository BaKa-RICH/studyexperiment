# Scenario Spec: 4-Lane Mainline + Aux Lane + Dual-Lane Ramp (v1)

目标：提供一份可直接用于评审的“SUMO 场景设计规范”，用于在本仓库中创建一个新的 ramp 合流场景（仅设计，不在本文档里直接写 `.net.xml/.rou.xml/.sumocfg`）。

适用代码范围：`/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/ramp`

主要参考论文：

1. 0 号论文：*Cooperative control of CAVs in the merging area of multi-lane mainline and dual-lane ramps on freeways*（本文档“paper0”）
1. 8 号论文：*Hierarchical Control Strategy for Cooperative On-Ramp Merging...*（本文档“paper8”，仅作为后续可选扩展）

---

## 1. 设计目标与边界

### 1.1 设计目标（v1 必须满足）

1. **拓扑核心**：4 车道主线 + 加速/辅助车道（aux lane）+ 单匝道双车道（dual-lane ramp），并采用 paper0 的典型长度/速度/需求口径（veh/h/lane）。
1. **保持与现有 `ramp` 代码“硬耦合”兼容**（见第 2 节），确保无需改代码也能跑通（至少 `no_control/fifo/dp` 的基线实验能启动并产出指标）。
1. **合流机制**：采用方式B（真实换道）——匝道车在 `main_h3` 内从 aux lane 换道到主线最右车道；`n_merge` 作为 aux lane 终止的 junction；`main_h4` 作为 merge 后的 `merge_edge`（默认值）。
1. **为后续扩展留接口**：后续可以逐步启用 ramp 双车道竞争（冲突点 A）、paper8 的“分车道限速/分层控制”、以及“灵活合流点（merge region）”。

### 1.2 非目标（v1 不做，但要在设计上不阻碍）

1. 不在 v1 引入 paper8 的 L1/L2/L3 分层控制与按车道速度限制（已选 B1：不引入）。
1. 不在 v1 使用 ramp 双车道同时上车（已选：`departLane="1"` 固定，另一条 ramp lane 暂时无车）。
1. v1 的方式B 已允许合流在 `main_h3` 区间内任意位置发生（由 SUMO 换道模型决定）；但算法仍以进入 `main_h4` 为“过合流点”的判定口径。

---

## 2. 与现有代码的“硬约束”（必须遵守）

这些约束来自当前代码实现，不遵守会导致指标计算错误、或调度/执行逻辑失效。

### 2.1 Scenario 文件组织

代码入口：`ramp/experiments/run.py`。

约定：

1. 新场景目录必须放在 `ramp/scenarios/<scenario_name>/`
1. `.sumocfg` 路径必须是 `ramp/scenarios/<scenario_name>/<scenario_name>.sumocfg`
3. 旧场景整理到 `ramp/scenarios/<ramp_min_v0>/` 文件夹下

### 2.2 流（stream）判别依赖 route 首边前缀

`ramp/runtime/state_collector.py` 使用 route 的第一条 edge id 来判别 stream：

1. route 第 1 条 edge id 以 `main_` 开头 -> `stream="main"`
1. route 第 1 条 edge id 以 `ramp_` 开头 -> `stream="ramp"`

因此：

1. 主线车辆 route 必须以 `main_h1`（或任何 `main_*` edge）开头
1. 匝道车辆 route 必须以 `ramp_h5`（或任何 `ramp_*` edge）开头

### 2.3 “过合流点”检测依赖 `merge_edge`

`ramp/runtime/state_collector.py` 把 `road_id == merge_edge` 视为已通过 merge（记录 `cross_time`）。

v1 强制约定：

1. `merge_edge = "main_h4"`（保持默认，减少改动面）
1. `main_h4` 必须是**最终合流之后**的第一段 edge（车辆进入 `main_h4` 即表示已完成 merge）

### 2.4 “commit” 检测依赖 `n_merge` junction id

`ramp/runtime/controller.py` 认为 `road_id.startswith(":n_merge")` 的车辆已经进入 merge junction 的 internal edge，进入 commit 状态（不再对其施加刹车速度命令）。

v1 强制约定：

1. 最终 merge junction 的 id 必须是 `n_merge`
1. net.xml 必须存在 internal edge 形如 `:n_merge_*`

### 2.5 控制区距离（distance-to-merge）的含义

`ramp/runtime/state_collector.py` 计算 `d_to_merge` 时优先使用：

`traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)`

含义：

1. `d_to_merge` 是沿车辆可行驶路径到 `merge_edge`（`main_h4` 起点）的**绝对距离**（单位 m）
1. 这个距离包含 junction internal edge 的影响（比纯 route edge 累加更稳）

结论：

1. 路网几何形状（匝道是否斜）不会改变“距离是绝对长度”的定义，但会改变实际路径长度与 internal edge 的形状与速度限制
1. 需要避免非常急的转角导致 internal edge 速度被 SUMO 限到很低（见 5.3）

---

## 3. 关键设计选择（你已确认的选项）

本节把对话里已确认的分歧项固化为 v1 的决策记录，便于评审时追溯。

1. A1（长度）：采用 paper0 的长度口径（见第 4 节）
1. B1（限速）：主线所有 lane 同速 `25.0 m/s`；匝道同速 `16.7 m/s`；不引入按车道限速（paper8 的做法留到后续）
1. C1（交通组成）：100% CAV（单一 vType）
1. D1（换道）：在 `main_h3` 主线车辆（lane1-4）禁止自由换道；匝道车辆（lane0/aux）允许且必须换道到 lane1 完成合流（方式B，见 6.2）
1. Demand 建模：显式 per-lane flow（veh/h/lane），不使用 `departLane="random"`
1. 匝道双车道：路网上保留 2 条 ramp lane，但 v1 出流固定 `departLane="1"`，另一条暂空
1. 合流机制（方式B）：匝道车在 `main_h3` 内真实换道合流；aux lane 在 `n_merge` 终止（无下游连接）；算法仍以进入 `main_h4`（`merge_edge`）为“过合流点”

---

## 4. 路网拓扑与命名规范（v1）

### 4.1 Edge 命名与语义

主线（paper0：H1-H4）：

1. `main_h1`: 主线段 H1（上游）
1. `main_h2`: 主线段 H2（速度控制区/上游控制区的一部分）
1. `main_h3`: 主线段 H3（合流区/加速车道并行区）
1. `main_h4`: 主线段 H4（合流后下游段，`merge_edge`）

匝道（paper0：H5-H6）：

1. `ramp_h5`: 匝道段 H5（上游自由段）
1. `ramp_h6`: 匝道段 H6（匝道速度控制段，连接至合流区入口）

Junction（关键）：

1. `n_merge`: 最终合流 junction（必须保留该 id）

### 4.1.1 各段语义、车道数与控制区关系总结

下表汇总了 paper0 区域命名、SUMO edge 命名、功能语义和控制状态的对应关系：

| 段 | edge id | 论文区域 | 功能 | 车道数 | speed (m/s) | 算法控制？ |
|---|---|---|---|---:|---:|---|
| H1 | `main_h1` | L1 上游自由区 | 主线车辆正常行驶，无控制 | 4 | 25.0 | 否 |
| H2 | `main_h2` | L2 速控/变道区 | 进入控制区（d_to_merge ≤ 600m），算法开始接管主线冲突车道 | 4 | 25.0 | 是（lane0 为冲突车道） |
| H3 | `main_h3` | L3 协同合流区 | aux lane（lane0）并行存在；匝道车在此区间内从 lane0 换道到 lane1 完成合流 | 5 | 25.0 | 是（lane0 aux + lane1 冲突车道） |
| H4 | `main_h4` | L4 下游自由区 | `merge_edge`；车辆进入此 edge 即视为“过合流点” | 4 | 25.0 | 否 |
| H5 | `ramp_h5` | L5 匝道自由区 | 匝道车辆正常行驶，无控制 | 2 | 16.7 | 否 |
| H6 | `ramp_h6` | L6 匝道速控区 | 进入控制区（d_to_merge ≤ 600m），算法开始接管匝道车辆 | 2 | 16.7 | 是 |

控制区范围（`control_zone_length_m = 600m`）：

1. 主线：`main_h2`(300m) + `main_h3`(300m) = 600m
1. 匝道：`ramp_h6`(300m) + `main_h3` aux lane(300m) = 600m

aux lane（加速车道）的角色：

1. 几何上是 `main_h3` 的 lane0，属于主线 edge
1. 功能上只有匝道车使用（主线车不会进入 lane0，见 4.4.1 的连接约束）
1. 速度上限与主线相同（25.0 m/s），使匝道车能在此加速至主线速度
1. 匝道车的 stream 判定仍为 `ramp`（由 route 首边 `ramp_h5` 决定，见 2.2）

### 4.2 节点与长度（A1：paper0 长度）

目标长度（单位 m）：

主线：

1. `len(main_h1)=200`
1. `len(main_h2)=300`
1. `len(main_h3)=300`
1. `len(main_h4)=200`

匝道：

1. `len(ramp_h5)=100`
1. `len(ramp_h6)=300`

备注：

1. `control_zone_length_m` 默认 `600m` 与上述长度自然对齐：主线覆盖 `H2+H3=600`；匝道覆盖 `H6+H3=600`（匝道进入 aux 后到 merge 的距离包含 `main_h3`）

### 4.2.1 Node 命名与推荐坐标（便于直接建网）

约定：坐标单位为 m；右侧通行；主线沿 +x 方向。

主线 nodes（沿 x 轴放置，精确满足 200/300/300/200 长度）：

| node id | x | y | 说明 |
|---|---:|---:|---|
| `n_main_0` | 0 | 0 | 主线上游起点 |
| `n_main_1` | 200 | 0 | H1 终点 / H2 起点 |
| `n_main_2` | 500 | 0 | H2 终点 / H3 起点（合流区入口；冲突点 A 所在） |
| `n_merge` | 800 | 0 | H3 终点 / H4 起点（aux lane 终止点；必须叫这个 id） |
| `n_main_3` | 1000 | 0 | 主线下游终点 |

匝道 nodes（保证 `ramp_h5=100`、`ramp_h6=300`，且尽量避免急转弯导致 internal edge 限速过低）：

本规范给出一组“无中间急转弯”的推荐坐标（`ramp_h5` 与 `ramp_h6` 共线，入合流区时转角约 30 度）：

| node id | x | y | 说明 |
|---|---:|---:|---|
| `n_ramp_0` | 153.5898 | -200.0 | 匝道上游起点 |
| `n_ramp_1` | 240.1924 | -150.0 | H5/H6 分界点（仅用于区分 H5/H6 语义，不引入额外转角） |

并约定 `ramp_h6` 的终点直接接到 `n_main_2`（即 `ramp_h6 to="n_main_2"`）。

说明：

1. 该坐标严格满足：`dist(n_ramp_0,n_ramp_1)=100`、`dist(n_ramp_1,n_main_2)=300`
1. 如果你希望匝道更“从下方并行进入”，可整体平移/旋转匝道形状，但必须保持两段长度与转角平滑性，并按 5.3 的准则检查 internal edge speed

### 4.2.2 Edge 规格表（用于 `.edg.xml` 直译）

下表是“设计意图”的规格（netconvert 生成后以 `.net.xml` 为准，需要做一次验收检查）。

| edge id | from | to | 目标长度 (m) | lanes | speed (m/s) | priority | 说明 |
|---|---|---|---:|---:|---:|---:|---|
| `main_h1` | `n_main_0` | `n_main_1` | 200 | 4 | 25.0 | 2 | 主线 H1 |
| `main_h2` | `n_main_1` | `n_main_2` | 300 | 4 | 25.0 | 2 | 主线 H2（控制区上游段） |
| `main_h3` | `n_main_2` | `n_merge` | 300 | 5 | 25.0 | 2 | 主线 H3（含 aux lane0） |
| `main_h4` | `n_merge` | `n_main_3` | 200 | 4 | 25.0 | 2 | 主线 H4（merge_edge） |
| `ramp_h5` | `n_ramp_0` | `n_ramp_1` | 100 | 2 | 16.7 | 1 | 匝道 H5 |
| `ramp_h6` | `n_ramp_1` | `n_main_2` | 300 | 2 | 16.7 | 1 | 匝道 H6（进入合流区入口） |

### 4.3 车道数与车道索引语义（关键）

#### 4.3.1 车道数（按你最新澄清）

1. `main_h1/main_h2/main_h4`：**4 车道**
1. `main_h3`：**5 车道**（在合流区额外增加 1 条辅助/加速车道，使该段为 5 车道）
1. `ramp_h5/ramp_h6`：**2 车道**（dual-lane ramp）

#### 4.3.2 SUMO lane index 映射（右侧通行）

SUMO 约定：lane index `0` 是该 edge 的**最右车道**。

为了同时满足：

1. “四车道主线”口径
1. 合流区引入 1 条“最右侧辅助/加速车道”

本设计定义如下 lane 语义：

对于 4-lane 主线 edge（`main_h1/main_h2/main_h4`）：

1. `lane 0`：主线最右侧车道（冲突车道候选；进入 `main_h3` 后对应 `lane 1`）
1. `lane 1`：主线中间靠右车道
1. `lane 2`：主线中间靠左侧车道
1. `lane 3`：主线最左侧车道

对于 5-lane 合流区 edge（`main_h3`）：

1. `lane 0`：辅助/加速车道（仅在合流区存在）
1. `lane 1`：主线最右侧车道
1. `lane 2`：主线中间靠右车道
1. `lane 3`：主线中间靠左侧车道
1. `lane 4`：主线最左侧车道

对于 2-lane 匝道 edge（`ramp_h5/ramp_h6`）：

1. `lane 0`：远离主线侧的 ramp lane（v1 暂空；为后续“双匝道两车道竞争进入加速车道”预留）
1. `lane 1`：靠近主线侧的 ramp lane（v1 出流固定在此 lane）

注意（建网时需验证）：

1. SUMO 的 lane 1 是否在几何上确实“更靠近主线”取决于匝道方向。当前推荐坐标下（匝道从左下方接入主线），lane 1（左侧车道）更靠近主线。如果 netedit 里发现相反，需把出流改成 `departLane="0"`，或调整匝道几何方向。

### 4.4 连接关系（connection）与两处冲突点

#### 4.4.1 主线 4→5 车道“加一条 aux”连接（在 `main_h2 -> main_h3`）

目标：主线原有 4 条车道**不进入** aux lane，aux lane 只由匝道注入。

强制连接映射：

1. `main_h2 lane0 -> main_h3 lane1`
1. `main_h2 lane1 -> main_h3 lane2`
1. `main_h2 lane2 -> main_h3 lane3`
1. `main_h2 lane3 -> main_h3 lane4`

约束：

1. 不允许 `main_h2` 的任何 lane 连接到 `main_h3 lane0`（aux lane 只由匝道注入）

#### 4.4.2 冲突点 A：匝道 2->1 进入 aux lane（在 `ramp_h6 -> main_h3`）

位置：合流区入口节点（v1 推荐固定在 `n_main_2`，即 `main_h3` 起点、`main_h2` 终点）。

连接规则（按你给的定义）：

1. `ramp_h6 lane0 -> main_h3 lane0`
1. `ramp_h6 lane1 -> main_h3 lane0`

v1 简化（已确认）：

1. 仅生成 `ramp_h6 lane1` 的车流，`ramp_h6 lane0` 暂时无车，从而避免 A 点引入“匝道两车道内部排序随机性”影响现有 dp/fifo。

#### 4.4.3 合流区 B：匝道车在 `main_h3` 内换道合流（方式B：真实换道）

合流方式：匝道车在 `main_h3` 的 aux lane（lane0）上行驶，必须在到达 `n_merge` 前完成从 lane0 到 lane1（主线最右车道）的**真实换道**。SUMO 的内置换道模型自动处理换道时机——因为 lane0 在 `n_merge` 处没有下游连接（死胡同），车辆会主动寻找 lane1 上的间隙完成变道。

合流区间：**整个 `main_h3`（300m）**都是潜在的合流区域，匝道车可在此区间内任意位置完成换道。这不是一个"点"冲突，而是一个"区间"合流。

`n_merge` 连接规则（lane0 无下游连接，其余 1:1 对齐）：

1. `main_h3 lane0`（aux）→ **无下游连接**（aux lane 到此终止；车辆必须在此之前换道到 lane1）
1. `main_h3 lane1` → `main_h4 lane0`
1. `main_h3 lane2` → `main_h4 lane1`
1. `main_h3 lane3` → `main_h4 lane2`
1. `main_h3 lane4` → `main_h4 lane3`

算法控制口径：

1. 算法通过控速在 lane1 上创造间隙，使匝道车能顺利换道
1. "过合流点"仍定义为进入 `main_h4`（`merge_edge`），与现有代码兼容
1. `main_h4` 是合流后的第一段 edge，满足 `merge_edge=main_h4` 的语义

---

## 5. 速度、优先级与 SUMO 行为（B1 + 兼容性注意）

### 5.1 速度上限（lane speed）

v1 速度上限设定（单位 m/s）：

1. 主线所有 lane：`v_main_max = 25.0`
1. 匝道所有 lane：`v_ramp_max = 16.7`
1. aux lane（`main_h3 lane0`）：建议设为 `25.0`（加速车道通常与主线同速上限）

实现注意：

1. SUMO 运行时以 `.net.xml` 的 `<lane speed="...">` 为准
1. `.edg.xml` 只是 netconvert 的输入；如果你手工改过 `.net.xml`（例如把某些 lane speed 抬到 25），运行时就会体现为 25

### 5.2 right-of-way（priority）与 `speedMode=23` 的关系（概念澄清）

背景：你问过“把 main/ramp priority 都设为 1 是否等价于代码里用 `speedMode=23` 关掉 priority 裁判？”。

结论（用于评审的口径）：

1. **不等价**。`priority` 修改的是路网层面的让行规则与 junction request/foe 关系；`speedMode=23` 是对“被控制车辆”的速度决策约束开关。
1. 当前代码只对被控制车辆设置 `traci.vehicle.setSpeedMode(veh, 23)`；未被控制车辆仍按路网 priority/让行规则行驶。
1. 即使把 priority 设为相等，也只是改变 SUMO 默认让行裁判，并不会等价于“对某些车忽略 right-of-way 检查”。

建议（v1）：

1. 不要继续使用“主线 priority=2、匝道 priority=1”的传统设置，让主线和匝道priority相同，这样可以把所有通行权力都交给我们算法来决定
1. 但注意：在本设计中，关键合流行为是匝道车在 `main_h3` 内从 aux lane（lane0）换道到主线最右车道（lane1），edge priority 对此换道行为的影响有限；更关键的是合流几何与 internal edge 速度限制

### 5.3 几何与 internal edge 限速（必须规避）

经验来自当前 `ramp_min_v1`：如果某个 junction 转角过急，SUMO 可能把 internal edge 的 `lane speed` 限得很低（例如出现 `3.92 m/s` 这种“临门一脚限速”），会：

1. 破坏 paper0 的“匝道/主线速度上限差异”设定
1. 引入额外的非控制因素（车辆在 internal edge 被迫减速）
1. 干扰 dp/fifo 的“距离-时间”一致性

v1 设计要求：

1. ramp 进入 `main_h3 lane0` 的几何转角要足够平滑（避免 90 度硬拐）
1. 生成 `.net.xml` 后必须检查 `:n_*` internal edge 的 `<lane speed>` 是否出现异常低值

评审验收准则（建议）：

1. `n_merge` 相关 internal edges（`:n_merge_*`）speed 不应明显低于 `16.7`（除非你明确要模拟低速弯道）
1. ramp 进入合流区入口处的 internal connector speed 不应低到个位数 m/s

---

## 6. 控制对象、换道与“冲突车道集合”

### 6.1 控制对象的设计意图（与你的算法目标一致）

你的明确要求：`fifo/dp` 只控“匝道 + 主线最外侧冲突车道”（而不是全主线全车道）。

但是：当前代码 `ramp/runtime/state_collector.py` 的控制区筛选条件只看 `d_to_merge`，不看 lane；`dp/fifo` 的候选集合也不按 lane 过滤。

v1 落地方式

选项 E1（推荐）：

1. 主线 4 车道都生成车流（按 veh/h/lane），模拟真实高速场景
1. 算法只控制 **冲突车道上的车辆**：
   - `main_h3 lane1`（主线最右车道，即冲突车道；对应 `main_h1/h2 lane0` 流过来的车辆）
   - `main_h3 lane0`（aux lane，匝道车辆）
1. 其余主线车辆（`main_h3 lane2/3/4`）自由行驶，不被算法接管
1. 代码侧在 `StateCollector` 或 scheduler 里按 `lane_id` 过滤，只把以上两类车辆纳入控制/调度
1. 匝道只在 `ramp_h5 lane1`（靠近主线侧）生成车流，`lane0` 不生成

### 6.2 D1：在 `main_h3` 的换道规则（方式B）

本场景采用方式B（真实换道）：匝道车在 `main_h3` 内从 aux lane（lane0）换道到主线最右车道（lane1）完成合流。因此换道规则需区分车辆角色：

**主线车辆（在 main_h3 的 lane1-4 上）**：

1. **禁止自由换道**——保持在各自车道上（例如不允许从 lane1 换到 lane2、或从 lane2 换到 lane3）
1. 目的：稳定“冲突车道集合”，确保算法只需关注 lane0 和 lane1 的交互
1. 实现方式：对主线车辆设置 `laneChangeMode` 禁止横向移动

**匝道车辆（在 main_h3 的 lane0 / aux 上）**：

1. **允许且必须换道**——从 lane0 换到 lane1（因为 lane0 在 `n_merge` 处无下游连接，不换道会卡住）
1. 实现方式：不对 aux 上的匝道车禁止换道（或仅允许 lane0→lane1 方向）
1. SUMO 的内置换道模型会自动在找到 lane1 间隙时完成变道

注意：A 点（ramp_h6 → main_h3 lane0）仍是通过 junction connection 完成的“强制路径跟随”，不属于自由换道。

---

## 7. 需求建模（per-lane flows，veh/h/lane）

### 7.1 v1 基线需求（可跑通、便于闭环验证）

目标：先把“调度-执行一致性”跑稳（你已选 C1：100% CAV）。

推荐基线（便于复用现有脚本/指标）：

1. 主线：4 条车道都有流量，但算法只控制冲突车道（见 6.1 的 E1）
1. 匝道：只在 `departLane="1"` 上出流

（如果你选择 E2，则主线 4 条车道都要给 flow，见 7.2）

### 7.2 paper0 网格扫参需求（16 组）

paper0 给出的需求口径（单位 veh/h/lane）：

1. 主线每车道：`800, 1200, 1600, 2000`
1. 匝道每车道：`400, 500, 600, 700`

组合：16 组（主线 4 档 x 匝道 4 档）。

在 SUMO `.rou.xml` 的表达（按你要求的“显式 per-lane flow”）：

route 定义（建议固定，便于代码按前缀判别 stream）：

1. `main_route`: `main_h1 main_h2 main_h3 main_h4`
1. `ramp_route`: `ramp_h5 ramp_h6 main_h3 main_h4`

主线 4-lane edge（`main_h1`）建议写 4 条 flow：

1. `flow_main_L0`：`departLane="0"`（主线最右 → main_h3 lane1 冲突车道）
1. `flow_main_L1`：`departLane="1"`
1. `flow_main_L2`：`departLane="2"`
1. `flow_main_L3`：`departLane="3"`（主线最左）

匝道 2-lane edge（`ramp_h5`）建议写 2 条 flow（v1 只启用 lane1）：

1. `flow_ramp_R0`：`departLane="0"`（v1 默认 vehsPerHour=0）
1. `flow_ramp_R1`：`departLane="1"`

命名建议（用于后续自动扫参脚本一致性）：

1. `q_main_vphpl`：主线“每车道流量”（veh/h/lane）
1. `q_ramp_vphpl`：匝道“每车道流量”（veh/h/lane）

如果按 E2（主线四车道都出流），则：

1. `flow_main_L0/L1/L2/L3` 的 `vehsPerHour = q_main_vphpl`

如果按 E1（只出冲突车道），则：

1. `flow_main_L0` 的 `vehsPerHour = q_main_vphpl`（冲突车道）
1. `flow_main_L1/L2/L3` 的 `vehsPerHour = 0`

---

## 8. 车辆类型（C1：100% CAV）

v1 推荐保留与 `ramp_min_v1.rou.xml` 一致的 vType 基础参数，并补充“去随机性”以便评审复现实验稳定性：

建议 vType（示意，单位 m/s、m/s^2、m）：

1. `id="cav"`
1. `accel=2.6`
1. `decel=4.5`
1. `tau=1.0`
1. `minGap=2.5`
1. `length=5.0`
1. `maxSpeed=25.0`（车辆上限，不应低于主线 lane speed）
1. `sigma=0.0`（建议）

备注：

1. 匝道车辆的 `v_ramp_max=16.7` 主要通过 lane speed 限制实现，而不是通过 vType 的 `maxSpeed`

---

## 9. 仿真与实验参数（对齐代码入口）

代码入口参数（`ramp/experiments/run.py`）建议在评审中明确以下变量名与默认值：

1. `scenario`：新场景名称（目录名）
1. `merge_edge`：默认 `main_h4`（v1 固定）
1. `control_zone_length_m`：默认 `600.0`
1. `main_vmax_mps`：默认 `25.0`
1. `ramp_vmax_mps`：默认 `16.7`
1. `takeover_speed_mode`：默认 `23`（在 `ramp/runtime/controller.py`）
1. `step_length`：建议先用 `0.1s`（代码默认），后续若要对齐 paper0 可尝试 `1.0s`
1. `duration_s`：评审跑通可先用 `300s`，正式对齐论文建议 `3600s`

---

## 10. 迁移与评审检查清单（验收项）

### 10.1 路网检查（net.xml）

1. edge id 必须包含：`main_h1 main_h2 main_h3 main_h4 ramp_h5 ramp_h6`
1. junction id 必须包含：`n_merge`，并产生 internal edges `:n_merge_*`
1. `main_h1/main_h2/main_h4` 车道数=4；`main_h3` 车道数=5；`ramp_h5/ramp_h6` 车道数=2
1. `main_h2 -> main_h3` 的连接映射必须保证主线 4 条 lane 对齐到 `main_h3 lane1-4`，且不进入 `lane0`
1. `ramp_h6 lane0/1 -> main_h3 lane0` 的连接存在
1. `n_merge` 处：`main_h3 lane0` **无**下游连接（aux 终止）；`main_h3 lane1-4` 分别连接 `main_h4 lane0-3`
1. 检查关键 internal edges 的 `lane speed` 不出现异常低值（见 5.3）

### 10.2 车流检查（rou.xml）

1. `main_route` 的首 edge 以 `main_` 开头
1. `ramp_route` 的首 edge 以 `ramp_` 开头
1. flow 使用显式 `departLane`（per-lane），并能复现 paper0 的 veh/h/lane 口径
1. v1：匝道出流固定 `departLane="1"`；另一条 ramp lane flow=0

### 10.3 与控制逻辑一致性检查

1. `merge_edge` 使用 `main_h4`（代码默认）
1. `commit` 检测能触发（车辆进入 `:n_merge*` 时日志出现 `commit_vehicle` 事件）
1. `d_to_merge` 在 `control_zone_length_m` 内的车辆被纳入控制区，并记录 `t_entry/d_entry`

---

## 11. 方式B 实现注意事项（建网与代码适配时必读）

### 11.1 `d_to_merge` 对 aux lane 车辆的计算

当前代码使用 `traci.vehicle.getDrivingDistance(veh_id, merge_edge, 0.0)` 计算 `d_to_merge`。

对于 `main_h3 lane0`（aux）上的匝道车辆，由于 lane0 在 `n_merge` 处**没有下游连接**到 `main_h4`，`getDrivingDistance` 的返回值可能异常（例如返回 -1 或极大值）。

实现时需验证：

1. 如果 `getDrivingDistance` 对 aux lane 车辆返回异常值，需要 fallback 到几何距离计算：`d_to_merge = edge_length - lane_pos`（main_h3 上的剩余距离）
1. 或者：在车辆成功换道到 lane1 之后，`getDrivingDistance` 应恢复正常（因为 lane1 有下游连接到 main_h4）

### 11.2 匝道车换道失败的边界处理

在高流量场景下，main_h3 lane1 可能没有足够间隙，导致匝道车在 aux lane 末尾（接近 n_merge）仍未完成换道。

SUMO 的默认行为：车辆会在 lane0 末端停车等待换道机会，直到找到间隙。

潜在影响：

1. 停在 lane0 末端的车辆会阻塞后方其他匝道车
1. `d_to_merge` 可能出现 0 或负值
1. 算法计算的 `target_cross_time` 可能不再有意义（车辆已到达 lane 末端但未完成换道）

建议处理方式（实现时再细化）：

1. 监控 aux lane 末端的车辆状态（`speed < 0.1 m/s` 且 `lane_id` 仍为 `main_h3_0`）
1. 如果出现频繁的换道失败，可能需要调低匝道流量或增大 main_h3 长度
1. 后续版本可引入更智能的间隙创建策略（例如对 lane1 车辆主动减速让路）

### 11.3 `laneChangeMode` 配置建议

v1 需要对不同角色的车辆设置不同的 `laneChangeMode`：

1. 主线车辆（在 `main_h3` lane1-4 上）：设置为禁止所有自由换道（保持车道）
1. 匝道车辆（在 `main_h3` lane0 上）：保持默认换道模式（允许 SUMO 自动换道到 lane1）
1. 实现方式：在 `controller.py` 中根据车辆的 `stream` 和当前 `lane_id` 分别设置

---

## 12. 后续扩展路线（明确不在 v1 做，但设计留口）

1. 启用冲突点 A 的双车道 ramp 竞争：把 ramp 两个 lane 都出流，并引入“匝道内部排序/协同”模块（你已指出当前 dp/fifo 没有该模块）
1. 引入 paper8 的分车道限速：在 `main_h3` 的不同 lane 设置不同 speed，并在代码侧把 `--main-vmax-mps` 从单值扩展为 per-lane 参数
1. 算法控制换道时机：从“SUMO 自动换道”升级为“算法决定何时换道”，需引入 TraCI 的 `changeLane` 控制
1. 主线提前变道让路：在 `main_h2`（L2）区域让主线内侧车辆提前向左变道，为 lane0/lane1 的合流腾出空间（对应论文 L2 区域的功能）
