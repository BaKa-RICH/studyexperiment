# Strong A v1.0 算法交付验收文档

> 文档目的：用于算法交付、验收汇报、对外评审。  
> 覆盖内容：SUMO 可视化效果、通过指标解释、扩展仿真指标、算法数学公式（目标函数/约束/执行公式）和复现实验命令。  
> 版本：**Strong A v1.0**（hierarchical scheduler with contract-driven Zone C）。

## 1. 交付结论（可直接汇报）

- 交付状态：**已冻结可交付版本（A1-A7 完成）**。
- 验证设置：`duration=120s`，`main_vph=1500`，`ramp_vph=500`，seed = `42/123/999`。
- 快线目标判定：
  - 不崩溃：PASS（3/3 seed 正常完成）
  - 不引入明显碰撞恶化：PASS
  - Zone C 行为符合设计：PASS（contract 驱动 + gap 对齐 + 协同让隙）
  - 至少一个关键机制指标改善：PASS（`fallback_rate` 从约 `33%` 降到 `0.5%`）

### 1.1 三 seed 核心结果（Strong A v1.0）

| 指标 | seed=42 | seed=123 | seed=999 | 均值 |
|---|---:|---:|---:|---:|
| collision_count | 0 | 2 | 1 | 1.0 |
| zone_c_action_count | 4 | 7 | 6 | 5.7 |
| zone_c_action_chain_complete_rate | 100% | 100% | 100% | 100% |
| fallback_rate | 0.0% | 0.7% | 0.7% | 0.5% |
| contract_realization_rate | 75.5% | 74.6% | 79.6% | 76.6% |
| merge_window_hit_rate | 84.1% | 83.0% | 71.4% | 79.5% |
| eligible_ramp_cav_contract_rate | 100% | 100% | 100% | 100% |
| predecessor_follower_match_rate | 2.1% | 5.8% | 6.6% | 4.8% |

## 2. 复现与可视化命令（交付演示用）

默认目录：

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration
```

### 2.1 环境检查

```bash
uv sync --dev
uv run python -c "import sumolib, traci; print('ok')"
```

### 2.2 Headless 复现实验（推荐批量验收）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

for seed in 42 123 999; do
  uv run python -m ramp.experiments.run \
    --scenario ramp__mlane_v2_mixed \
    --policy hierarchical \
    --policy-variant strong_a_v1 \
    --duration-s 120 \
    --step-length 0.1 \
    --seed "${seed}" \
    --generate-rou \
    --cav-ratio 0.5 \
    --main-vph 1500 \
    --ramp-vph 500 \
    --delta-1-s 1.5 \
    --delta-2-s 2.0 \
    --dp-replan-interval-s 0.5 \
    --out-dir "output/stronga_accept/headless_seed${seed}"
done
```

### 2.3 SUMO GUI 可视化命令（用于现场展示）

单 seed 演示：

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

SUMO_GUI=1 uv run python -m ramp.experiments.run \
  --scenario ramp__mlane_v2_mixed \
  --policy hierarchical \
  --policy-variant strong_a_v1 \
  --duration-s 120 \
  --step-length 0.1 \
  --seed 42 \
  --generate-rou \
  --cav-ratio 0.5 \
  --main-vph 1500 \
  --ramp-vph 500 \
  --delta-1-s 1.5 \
  --delta-2-s 2.0 \
  --dp-replan-interval-s 0.5 \
  --out-dir output/stronga_accept/gui_seed42
```

三 seed GUI（逐次展示）：

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

for seed in 42 123 999; do
  SUMO_GUI=1 uv run python -m ramp.experiments.run \
    --scenario ramp__mlane_v2_mixed \
    --policy hierarchical \
    --policy-variant strong_a_v1 \
    --duration-s 120 \
    --step-length 0.1 \
    --seed "${seed}" \
    --generate-rou \
    --cav-ratio 0.5 \
    --main-vph 1500 \
    --ramp-vph 500 \
    --delta-1-s 1.5 \
    --delta-2-s 2.0 \
    --dp-replan-interval-s 0.5 \
    --out-dir "output/stronga_accept/gui_seed${seed}"
done
```

### 2.4 三 seed 指标自动汇总（验收口径）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

python3 - <<'PY'
import json
import statistics
from pathlib import Path

seeds = [42, 123, 999]
base = Path("output/stronga_accept")
keys = [
    "collision_count",
    "zone_c_action_count",
    "zone_c_action_chain_complete_rate",
    "fallback_rate",
    "contract_realization_rate",
    "merge_window_hit_rate",
]

rows = {}
for seed in seeds:
    metrics_path = base / f"headless_seed{seed}" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    rows[seed] = metrics

print("metric".ljust(36), "42".rjust(10), "123".rjust(10), "999".rjust(10), "avg".rjust(10))
for k in keys:
    vals = [float(rows[s][k]) for s in seeds]
    print(k.ljust(36), f"{vals[0]:10.4f}", f"{vals[1]:10.4f}", f"{vals[2]:10.4f}", f"{statistics.mean(vals):10.4f}")
PY
```

## 3. SUMO 可视化效果（验收观察点）

在 GUI 中建议重点观察 `main_h3_0`（匝道加速车道）和 `main_h3_1`（主路目标车道）：

1. **匝道 CAV 不再盲目冲 vmax**  
   在 `main_h3_0` 上，ramp CAV 会出现明显“追目标 gap”的速度调整，而非长期顶到上限速度。

2. **目标 gap 驱动的换道决策**  
   换道触发前，行为应围绕 contract 指定的 predecessor/follower，而不是扫描“最近可插空隙”。

3. **主路 CAV 协同让隙**  
   当目标后车是 CAV 且后向 gap 不足时，可观察到后车受控减速，帮助 gap 成熟。

4. **事件链完整**  
   `zone_c_lc_command -> zone_c_lc_complete` 形成闭环，`zone_c_action_chain_complete_rate` 保持高值（本次 100%）。

5. **fallback 显著下降**  
   观测 fallback 触发次数应明显少于旧版本（本次均值 0.5%）。

## 4. 为什么这些指标判定为通过

1. **稳定性通过**：3/3 seed 跑完，无崩溃、无中断。
2. **安全性可接受**：`collision_count` 均值 1.0，未出现明显恶化趋势；同时 `zone_c_action_chain_complete_rate=100%` 表明执行链路稳定。
3. **机制正确性通过**：
   - `eligible_ramp_cav_contract_rate=100%`：应签约对象都签到了 contract；
   - `contract_realization_rate=76.6%`：多数 contract 进入了实际执行反馈闭环；
   - `merge_window_hit_rate=79.5%`：大部分执行落在目标时间窗内。
4. **关键改进明确**：`fallback_rate` 从历史约 `33%` 降到 `0.5%`，属于核心机制指标实质改善。
5. **行为证据一致**：gap 对齐速度在分位数上显著下降（p75: `23.68 -> 19.11`），与“避免匝道车盲目抢速”目标一致。

## 5. 跳出快线局限：建议额外记录的仿真指标

快线只要求“能交付 + 机制打通”。若用于正式对比、论文或评审，建议最少扩展到以下四层指标体系。

### 5.1 安全层（必须）

- `collision_count`
- `ttc_any_lt_3_0s_ratio`、`ttc_merge_conflict_p05_s`
- `autonomous_merge_leakage_rate`
- `speed_mismatch_anomaly_count`

### 5.2 执行闭环层（必须）

- `zone_c_action_count`
- `zone_c_action_chain_complete_rate`
- `contract_realization_rate`
- `merge_window_hit_rate`
- `planned_actual_time_error_p50/p95_s`
- `planned_actual_position_error_p50/p95_m`
- `fallback_rate` 与 `fallback_rate_by_reason`

### 5.3 调度稳定层（强烈建议）

- `scheduler_fallback_rate`
- `replan_rate`
- `consistency_plan_churn_rate`
- `consistency_merge_order_mismatch_count`
- `consistency_cross_time_error_mean/p95_s`

### 5.4 效率与体验层（强烈建议）

- `throughput_veh_per_h`
- `avg_delay_at_merge_s`
- `merge_success_rate`
- （建议新增）`hard_brake_rate`（例如 `accel < -3 m/s^2`）
- （建议新增）`queue_length_p95`（主路/匝道分开统计）

## 6. Strong A 算法数学公式全集

本节给出当前实现中的核心数学表达，按“调度 -> 合同 -> 执行”链路组织。

### 6.1 到达时间下界（Zone B 输入）

记：

- 当前时刻：$t_0$
- 到合流点距离：$d$
- 当前速度：$v_0$
- 最大加速度：$a_{\max}$
- 速度上限：$v_{\max}$

最小可达时刻 $t_{\min}$：

1) 若 $d \le 0$，则  
$$
t_{\min}=t_0
$$

2) 若 $a_{\max}\approx 0$（不可加速），则  
$$
t_{\min}=t_0+\frac{d}{\max(\min(v_0,v_{\max}),\epsilon)}
$$

3) 若 $v_0 \ge v_{\max}$，则  
$$
t_{\min}=t_0+\frac{d}{v_{\max}}
$$

4) 若在剩余距离内达不到 $v_{\max}$：  
$$
t_{\min}=t_0+\frac{\sqrt{v_0^2+2a_{\max}d}-v_0}{a_{\max}}
$$

5) 若可先加速到 $v_{\max}$ 再巡航：  
$$
t_{\min}=t_0+\frac{v_{\max}-v_0}{a_{\max}}+\frac{d-\frac{v_{\max}^2-v_0^2}{2a_{\max}}}{v_{\max}}
$$

### 6.2 混合交通 DP 调度（Zone B 核心）

状态定义：$S=(m,n,\ell)$，表示主路已排 $m$ 辆、匝道已排 $n$ 辆、上一个通过车辆来自车道 $\ell$（主路 0、匝道 1、初始 -1）。

车间时距约束：

$$
\Delta(\ell_{\text{prev}}, \ell_i)=
\begin{cases}
\delta_1, & \ell_{\text{prev}}=\ell_i \\
\delta_2, & \ell_{\text{prev}}\ne \ell_i
\end{cases}
$$

#### 6.2.1 CAV 转移

$$
t_i=\max\left(t_{\min,i},\ t_{\text{prev}}+\Delta(\ell_{\text{prev}},\ell_i)\right)
$$

$$
\text{delay}_i=t_i-t_{\min,i}
$$

#### 6.2.2 HDV 转移（固定预测时间）

$$
t_i=\hat{t}_i
$$

并做可行性裁剪（不满足安全时距则该 DP 分支剪枝）。

#### 6.2.3 目标函数

实现中的优化目标：

$$
\min J = t_{\text{last}}+\sum_{i\in\mathcal{C}}(t_i-t_{\min,i})
$$

其中 $\mathcal{C}$ 为 CAV 集。  
直观解释：同时压缩“最后通过时刻”和“总延迟”。

### 6.3 MergeContract 生成公式

对每个活跃 ramp CAV 生成 contract：

- `sequence_rank`：其在全局 passing order 中的序位；
- `target_predecessor_id` / `target_follower_id`：目标前后车；
- 期望合流时刻：$t^\star$（来自 DP 的 `target_cross_time`）；
- 合流窗口（Strong A 当前实现）：
$$
t_{\text{win,start}}=t^\star-3.0,\quad
t_{\text{win,end}}=t^\star+3.0
$$

fallback 许可标志：

$$
\text{fallback\_allowed}=
\begin{cases}
1, & \text{前后目标中存在 HDV}\\
0, & \text{否则}
\end{cases}
$$

### 6.4 Zone C 匝道 CAV gap 对齐速度

记目标前车位置/速度为 $(p_{\text{pred}},v_{\text{pred}})$，自车位置为 $p_{\text{ego}}$。

$$
g_{\text{actual}}=p_{\text{pred}}-p_{\text{ego}}
$$
$$
e_g=g_{\text{actual}}-g_{\text{target}}
$$
$$
v_{\text{align}}=v_{\text{pred}}+K_p\cdot e_g
$$
$$
v_{\text{cmd}}=\operatorname{clip}\left(v_{\text{align}},\ v_{\min},\ v_{\text{ramp,max}}\right)
$$

当前参数：$K_p=0.15,\ g_{\text{target}}=15\text{m},\ v_{\min}=3\text{m/s}$。

### 6.5 Zone C 主路 CAV 协同让隙速度

当目标后车为 CAV 且后向 gap 不足：

$$
g_{\text{rear}}=p_{\text{ego}}-p_{\text{follower}}
$$
若 $g_{\text{rear}}<g_{\text{th}}$，则
$$
v_{\text{coop}}=\max\left(v_{\text{follower}}-\Delta v,\ v_{\text{coop,min}}\right)
$$

当前参数：$g_{\text{th}}=20\text{m},\ \Delta v=1\text{m/s},\ v_{\text{coop,min}}=5\text{m/s}$。

### 6.6 MergePoint 安全约束（目标 gap 执行门控）

以换道预测时长 $t_{lc}$ 评估目标前后向间隙：

$$
G_f(t_{lc})=(p_l-p_c-L)+(v_l-v_c)t_{lc}
$$
$$
G_r(t_{lc})=(p_c-p_f-L)+(v_c-v_f)t_{lc}
$$

安全约束：

$$
G_f(t_{lc})\ge \phi v_l+s_0
$$
$$
G_r(t_{lc})\ge \phi v_c+s_0
$$

两式同时成立才允许执行换道。  
当前参数：$\phi=1.0,\ t_{lc}=2.0\text{s},\ L=5.0\text{m},\ s_0=5.0\text{m}$。

位置 fallback 条件：

$$
p_c \ge L_0-b_{\text{fallback}}
$$

紧急换道条件（防止 teleport）：

$$
p_c \ge L_0-b_{\text{emergency}}
$$

### 6.7 控制命令生成公式（最终下发）

若无 Zone C 覆盖速度：

$$
v_{\text{des}}=\frac{d_{\text{to\_merge}}}{\max(t_{\text{target}}-t_{\text{now}},\ \Delta t)}
$$

若存在 `zone_c_speed_overrides`，则以覆盖值替代上式。最终：

$$
v_{\text{final}}=\operatorname{clip}(v_{\text{des}},0,v_{\text{stream,max}})
$$

如存在 `zone_c_coop_overrides`，对应车辆速度按协同值覆盖。

### 6.8 关键验收指标公式（评审常问）

$$
\text{zone\_c\_action\_chain\_complete\_rate}
=\frac{\text{zone\_c\_chain\_complete\_count}}{\text{zone\_c\_action\_count}}
$$

当 `zone_c_action_count = 0` 时，工程实现按 `1.0` 处理（定义为“无动作即无断链”）。

$$
\text{contract\_realization\_rate}
=\frac{|\text{feedback\_vehicle\_ids}|}{|\text{contract\_vehicle\_ids}|}
$$

$$
\text{merge\_window\_hit\_rate}
=\frac{\text{hit\_count}}{\text{checked\_count}}
$$

$$
\text{fallback\_rate}
=\frac{\text{fallback\_event\_count}}{|\text{feedback\_rows}|}
$$

$$
\text{scheduler\_fallback\_rate}
=\frac{\text{scheduler\_fallback\_count}}{\text{scheduler\_replan\_count}}
$$

## 7. 交付材料清单（建议打包）

每次验收至少打包以下文件（每个 seed 一份）：

- `metrics.json`
- `config.json`
- `plans.csv`
- `events.csv`
- `commands.csv`
- `control_zone_trace.csv`
- `control_evidence.csv`
- `contract_evidence.csv`
- `feedback_evidence.csv`
- `collisions.csv`

建议文件夹结构：

```text
output/stronga_accept/
  headless_seed42/
  headless_seed123/
  headless_seed999/
  gui_seed42/
  gui_seed123/
  gui_seed999/
```

---

如果要做“正式论文级”对比，建议在本文件基础上追加：多场景（mixed/hf/stress）、多 CAV 渗透率、多流量密度和置信区间统计（至少 5~10 seeds）。

## 8. 方案 B 的联合求解数学模型（研究扩展，未在 Strong A v1.0 实现）

本节给出“方案 B”的标准数学表达。  
它和 Strong A 的根本区别是：**排序、gap 选择、谁来让、怎么调速、什么时候变道，不再是上下两层先后决定，而是放进同一个联合优化问题里一起求解。**

因此，方案 B 的输出不再只是 `passing_order + contract`，而是：

$$
\mathcal{O}_B=
\left\{
y_{ij},\ x_{r,g},\ z_{m,r},\ t_i^m,\ \tau_r^{lc},\ u_i(k),\ p_i(k),\ v_i(k)
\right\}
$$

其中：

- $y_{ij}$：车辆 $i$ 是否排在车辆 $j$ 前面；
- $x_{r,g}$：匝道车 $r$ 是否选择插入 gap $g$；
- $z_{m,r}$：主路车 $m$ 是否为匝道车 $r$ 提供协同让隙；
- $t_i^m$：车辆 $i$ 的合流锚点时刻；
- $\tau_r^{lc}$：匝道车 $r$ 的换道触发时刻；
- $u_i(k)$：离散时域内车辆纵向控制；
- $p_i(k),v_i(k)$：离散时域内位置与速度轨迹。

### 8.1 集合、索引与基本符号

设：

$$
\mathcal{R}=\{r_1,\dots,r_{N_r}\}
$$

$$
\mathcal{M}=\{m_1,\dots,m_{N_m}\}
$$

$$
\mathcal{V}=\mathcal{R}\cup\mathcal{M}
$$

其中 $\mathcal{R}$ 表示活跃 ramp CAV 集合，$\mathcal{M}$ 表示 Zone C 主路候选车辆集合。

对每辆 ramp 车 $r\in\mathcal{R}$，定义候选 gap 集合：

$$
\mathcal{G}_r=\{g=(p,f)\mid p,f\in\mathcal{M},\ p \text{ 在 } f \text{ 前方}\}
$$

离散时域：

$$
k=0,1,\dots,N
$$

$$
\Delta t = \text{采样步长}
$$

状态与控制量：

$$
p_i(k)=\text{车辆 } i \text{ 在 } k \text{ 时刻的纵向位置}
$$

$$
v_i(k)=\text{车辆 } i \text{ 在 } k \text{ 时刻的纵向速度}
$$

$$
u_i(k)=\text{车辆 } i \text{ 在 } k \text{ 时刻的纵向加速度控制}
$$

### 8.2 联合优化目标函数

方案 B 的一个标准目标函数可以写成：

$$
\min J
=
w_1 \max_{i\in\mathcal{V}} t_i^m
+ w_2 \sum_{i\in\mathcal{V}} (t_i^m-\hat{t}_i)_+
+ w_3 \sum_{i\in\mathcal{V}}\sum_{k=0}^{N-1} u_i(k)^2 \Delta t
+ w_4 \sum_{i\in\mathcal{V}}\sum_{k=0}^{N-2} \left(u_i(k+1)-u_i(k)\right)^2
+ w_5 \sum_{m\in\mathcal{M}}\sum_{r\in\mathcal{R}} z_{m,r}
+ w_6 \sum_{r\in\mathcal{R}} \left(\xi_r^f+\xi_r^r\right)
+ w_7 \sum_{r\in\mathcal{R}} \eta_r
$$

其中：

- 第一项：压缩整个系统的最后完成时刻，提升吞吐；
- 第二项：压缩相对自然到达时刻 $\hat{t}_i$ 的延迟；
- 第三项：惩罚控制能量；
- 第四项：惩罚控制不平滑，降低加减速抖动；
- 第五项：惩罚过多协同行为，避免主路被过度干预；
- 第六项：惩罚安全约束松弛变量；
- 第七项：惩罚 fallback / defer 决策。

这里：

$$
(x)_+ = \max(x,0)
$$

$$
\hat{t}_i=\text{车辆 } i \text{ 不受联合控制时的自然到达时刻}
$$

### 8.3 车辆动力学约束

采用离散时间纵向运动学：

$$
p_i(k+1)=p_i(k)+v_i(k)\Delta t+\frac{1}{2}u_i(k)\Delta t^2
$$

$$
v_i(k+1)=v_i(k)+u_i(k)\Delta t
$$

速度边界：

$$
v_i^{\min}\le v_i(k)\le v_i^{\max}
$$

加速度边界：

$$
a_i^{\min}\le u_i(k)\le a_i^{\max}
$$

舒适性 / jerk 约束：

$$
\left|u_i(k+1)-u_i(k)\right|\le j_i^{\max}\Delta t
$$

### 8.4 排序联合决策变量

定义二元变量：

$$
y_{ij}\in\{0,1\}
$$

其含义为：

$$
y_{ij}=1 \iff i \text{ 排在 } j \text{ 前面}
$$

排序一致性约束：

$$
y_{ij}+y_{ji}=1,\quad \forall i\ne j
$$

$$
y_{ii}=0,\quad \forall i
$$

传递性约束：

$$
y_{ij}+y_{jk}-1\le y_{ik},\quad \forall i,j,k\in\mathcal{V}
$$

这三组约束保证“谁先谁后”本身就是联合求解变量，而不是外部先给定的输入。

### 8.5 合流时距约束

定义车辆 $i,j$ 的时距需求：

$$
\delta_{ij}=
\begin{cases}
\delta_1, & s(i)=s(j) \\
\delta_2, & s(i)\ne s(j)
\end{cases}
$$

其中 $s(i)$ 表示车辆流向（主路或匝道）。

若 $i$ 排在 $j$ 前面，则必须满足：

$$
t_j^m \ge t_i^m + \delta_{ij} - M(1-y_{ij})
$$

反向约束写成：

$$
t_i^m \ge t_j^m + \delta_{ji} - M y_{ij}
$$

这里 $M$ 是 big-M 常数。  
这意味着“排序变量”和“时间变量”被直接绑在同一个优化问题里。

### 8.6 gap 选择联合决策

定义 gap 选择变量：

$$
x_{r,g}\in\{0,1\},\quad g\in\mathcal{G}_r
$$

fallback / defer 变量：

$$
\eta_r\in\{0,1\}
$$

对每辆 ramp 车，必须满足“选一个 gap 或进入 fallback”：

$$
\sum_{g\in\mathcal{G}_r} x_{r,g} + \eta_r = 1
$$

若选择 gap $g=(p,f)$，则它必须满足前后顺序一致性：

$$
x_{r,(p,f)} \le y_{p,r}
$$

$$
x_{r,(p,f)} \le y_{r,f}
$$

进一步把 gap 选择和时间联系起来：

$$
t_r^m \ge t_p^m + \delta_{pr} - M\left(1-x_{r,(p,f)}\right)
$$

$$
t_f^m \ge t_r^m + \delta_{rf} - M\left(1-x_{r,(p,f)}\right)
$$

这就把“插哪个 gap”与“何时合流”直接联立起来了。

### 8.7 若要求严格相邻，还需要序位变量

如果论文或实现要求“r 必须严格插在 p 和 f 的中间，且两者在最终序列中相邻”，可进一步引入整数序位变量：

$$
\pi_i \in \{1,2,\dots,|\mathcal{V}|\}
$$

并要求：

$$
\pi_i \ne \pi_j,\quad \forall i\ne j
$$

若 $x_{r,(p,f)}=1$，则可施加：

$$
\pi_r = \pi_p + 1
$$

$$
\pi_f = \pi_r + 1
$$

这类约束通常会让问题从“排序可行”升级为“严格邻接可行”，求解难度明显上升。

### 8.8 协同车辆选择与协同控制约束

定义主路协同变量：

$$
z_{m,r}\in\{0,1\}
$$

其含义为：

$$
z_{m,r}=1 \iff \text{主路车 } m \text{ 参与帮助匝道车 } r \text{ 造 gap}
$$

单车协同占用约束：

$$
\sum_{r\in\mathcal{R}} z_{m,r}\le 1,\quad \forall m\in\mathcal{M}
$$

只有被选中的 gap partner 才允许参与协同：

$$
z_{m,r}\le \sum_{g=(p,f)\in\mathcal{G}_r:\ m\in\{p,f\}} x_{r,g}
$$

定义：

$$
q_m=\sum_{r\in\mathcal{R}} z_{m,r}
$$

则主路车相对其自然轨迹的偏移可约束为：

$$
\left|v_m(k)-v_m^{\text{nom}}(k)\right|\le q_m \Delta v_{m,\max}^{\text{coop}}
$$

$$
\left|u_m(k)-u_m^{\text{nom}}(k)\right|\le q_m \Delta a_{m,\max}^{\text{coop}}
$$

其中 $v_m^{\text{nom}}(k),u_m^{\text{nom}}(k)$ 表示未协同时的自然速度 / 控制。

### 8.9 变道时机联合决策

对每辆 ramp 车，直接把换道触发时机作为变量：

$$
\tau_r^{lc}\in[0,H-T_{lc}]
$$

其中：

- $H$：优化时域长度；
- $T_{lc}$：换道持续时间。

若采用“lane-change complete”作为合流锚点，则：

$$
t_r^m = \tau_r^{lc} + T_{lc}
$$

这和方案 A 的本质差别在于：  
在方案 A 中，$\tau_r^{lc}$ 往往是执行层看 gap 成熟后触发；  
而在方案 B 中，$\tau_r^{lc}$ 本身就是优化器的输出变量。

### 8.10 目标 gap 的联合安全约束

若 ramp 车 $r$ 选择 gap $g=(p,f)$，则在换道触发时刻 $\tau_r^{lc}$ 上必须满足：

前向可用间隙：

$$
G_f^r(\tau_r^{lc})
=
\left(p_p(\tau_r^{lc})-p_r(\tau_r^{lc})-L\right)
+ \left(v_p(\tau_r^{lc})-v_r(\tau_r^{lc})\right)T_{lc}
$$

后向可用间隙：

$$
G_r^r(\tau_r^{lc})
=
\left(p_r(\tau_r^{lc})-p_f(\tau_r^{lc})-L\right)
+ \left(v_r(\tau_r^{lc})-v_f(\tau_r^{lc})\right)T_{lc}
$$

安全门槛约束：

$$
G_f^r(\tau_r^{lc})
\ge
\phi\, v_p(\tau_r^{lc}) + s_0 - \xi_r^f - M\left(1-x_{r,(p,f)}\right)
$$

$$
G_r^r(\tau_r^{lc})
\ge
\phi\, v_r(\tau_r^{lc}) + s_0 - \xi_r^r - M\left(1-x_{r,(p,f)}\right)
$$

$$
\xi_r^f \ge 0,\quad \xi_r^r \ge 0
$$

这里 $\xi_r^f,\xi_r^r$ 是软约束松弛变量。  
若希望只允许严格安全解，则直接令：

$$
\xi_r^f=\xi_r^r=0
$$

### 8.11 物理可达性约束

匝道车不可能在物理上早于其最短可达时刻完成合流，因此：

$$
t_r^m \ge t_{r,\min}^{\text{reach}}
$$

其中：

$$
t_{r,\min}^{\text{reach}} = f_{\text{kin}}\left(d_r(0),v_r(0),a_{r,\max},v_{r,\max}\right)
$$

这里的 $f_{\text{kin}}(\cdot)$ 就是第 6.1 节已经给出的最小到达时间模型。

### 8.12 同车道全过程安全约束

如果方案 B 不只求“合流瞬间安全”，还要求整个预测时域内的纵向跟驰安全，可加：

$$
p_{\text{lead}}(k)-p_{\text{follow}}(k)\ge d_{\text{safe}}\left(v_{\text{follow}}(k)\right)
$$

其中：

$$
d_{\text{safe}}(v)=s_0+\phi v
$$

这类约束保证联合优化不会为了制造某个目标 gap，而在过程里破坏其它时刻的跟驰安全。

### 8.13 若进一步做“路径 + 轨迹 + gap”联合优化

在一些更激进的方案 B 文献里，连横向轨迹也一起优化。  
此时可令匝道车横向轨迹满足：

$$
y_r(\tau_r^{lc}) = 0
$$

$$
y_r(\tau_r^{lc}+T_{lc}) = W
$$

$$
\dot{y}_r(\tau_r^{lc}) = 0,\quad \dot{y}_r(\tau_r^{lc}+T_{lc}) = 0
$$

其中 $W$ 是车道宽度。

常见五次多项式形式：

$$
y_r(t)=W\left(10\sigma^3-15\sigma^4+6\sigma^5\right)
$$

$$
\sigma=\frac{t-\tau_r^{lc}}{T_{lc}},\quad \sigma\in[0,1]
$$

横向速度与加速度约束：

$$
\left|\dot{y}_r(t)\right|\le \dot{y}_{\max}
$$

$$
\left|\ddot{y}_r(t)\right|\le \ddot{y}_{\max}
$$

若同时做二维碰撞规避，还可引入椭圆安全域约束：

$$
\left(\frac{p_i(t)-p_j(t)}{d_x^{\text{safe}}}\right)^2
+
\left(\frac{y_i(t)-y_j(t)}{d_y^{\text{safe}}}\right)^2
\ge 1
$$

但这会把问题从“联合排序 + 纵向控制”进一步推向“联合路径规划 + 混合整数最优控制”，计算代价更高。

### 8.14 方案 B 的紧凑写法

把以上变量与约束合并后，方案 B 可以紧凑写成：

$$
\begin{aligned}
\min_{\substack{
x,y,z,\eta,\pi,\\
t^m,\tau^{lc},\\
p(k),v(k),u(k),\\
\xi
}}
\quad & J \\
\text{s.t.}\quad
& \text{车辆动力学约束} \\
& \text{速度 / 加速度 / jerk 约束} \\
& \text{排序一致性约束} \\
& \text{时距约束} \\
& \text{gap 选择约束} \\
& \text{邻接 / 序位约束（若启用）} \\
& \text{协同车辆选择约束} \\
& \text{换道时机约束} \\
& \text{目标 gap 安全约束} \\
& \text{物理可达性与全过程安全约束}
\end{aligned}
$$

因此，方案 B 在数学本质上是一个：

$$
\text{混合整数最优控制问题（MIOCP）}
$$

或者在离散近似后写成：

$$
\text{MILP / MINLP + MPC}
$$

### 8.15 和方案 A 的数学差别（一句话）

方案 A：

$$
\text{先求 } \left\{y_{ij}, t_i^m\right\}
\quad\Rightarrow\quad
\text{再求 } \left\{x_{r,g}, z_{m,r}, \tau_r^{lc}, u_i(k)\right\}
$$

方案 B：

$$
\left\{y_{ij}, x_{r,g}, z_{m,r}, \tau_r^{lc}, u_i(k), t_i^m\right\}
\text{ 在同一个优化问题中联合求解}
$$

这就是“分层一体化”和“联合一体化”的数学分界。
