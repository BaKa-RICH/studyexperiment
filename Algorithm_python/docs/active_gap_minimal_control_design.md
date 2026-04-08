<!--
Status: draft
Scope: repo-instance
-->

# 主动造 Gap 最小控制方案设计稿

> 最后更新：`2026-04-08T18:32:00+08:00`
>
> 本稿是独立设计稿，不替代当前正式 SSOT；目的只有一个：把当前已经拍板的 `TCG / coordination slice / A层只看pms` 版本完整讲清楚，作为后续继续扩展文档与实现时的总草案。

## 1. 这份设计稿要解决什么问题

当前仓库已经明确：旧的

```text
snapshot -> FIFO candidate -> gate -> commit -> rollout
```

主链只能回答一类问题：

- 当前有没有现成可插入 gap

但它回答不了更重要的问题：

- 如果当前 gap 还不够，系统能不能通过未来若干个 `0.1s` tick 的协同控制，把 gap 主动调成可行

因此，这份设计稿不再把问题定义成：

- 在现有 gap 里挑一个可行候选

而是重新定义成：

1. 先识别当前局部三车协同组 `TCG = (p,m,s)`
2. 再规划未来 merge target：`(x_m^*, t_m^*, v^*)`
3. 若当前 tick 还不能正式 merge，则优先执行一段能继续造 gap 的 coordination slice
4. 对整段控制轨迹出具 `SafetyCertificate`

这就是当前版本“主动造 gap”的最小主线。

## 2. 范围与不做项

本稿只覆盖当前最小可落地版本：

- 单主线 + 单匝道
- 单 `active decision partition`
- 每个 planning tick 只处理 1 辆最靠前的 active ramp CAV
- 受控核心车辆：`p / m / s`
- 可选边界预测车辆：`u / f`
- 上层规划 `completion anchor`
- 下层对 `p/m/s` 求三车 quintic 纵向轨迹
- 当前 tick 无 merge 解时优先走 coordination slice
- 横向保留模板化执行层
- 不引入 CBF / QP
- 不做全局联合优化
- 不做多匝道、多目标车道、多 partition 联动

这份最小方案的目标不是一步做到论文最终形态，而是先把下面这件事做对：

- 在初始 gap 明显不合规时，仍能通过 `TCG=(p,m,s)` 协同，让未来出现合规 merge 条件

本稿当前明确不做：

- 上游换道
- 多 `active decision partition`
- 全局协同
- 第二波 `simple DP`

## 3. 坐标、区域与对象

### 3.1 纵向坐标

延续当前仓库已经冻结的几何语义：

- `x`：沿道路主参考线的纵向坐标，越大越靠下游
- `ramp_approach_subzone = [0m, 50m)`
- `legal_merge_zone = [x_z^s, x_z^e] = [50m, 290m]`
- `emergency_tail = [290m, 300m]`
- `completion anchor`：匝道车完成并入目标车道时的纵向位置，记为 `x_m^*`
- `lane-change start`：匝道车开始横向侵入目标车道的纵向位置，记为 `x_{lc}^*`

### 3.2 `TCG` 与可选边界车

每个 planning tick 只处理一个局部三车协同组：

- `p`：匝道车合流后位于其前方的主路前车，受控
- `m`：当前被规划的匝道车，受控
- `s`：匝道车合流后位于其后方的主路辅助车，受控

在这三车组两侧，允许再接入可选边界车：

- `u`：`p` 的上游边界车，只做预测与安全检查
- `f`：`s` 的下游边界车，只做预测与安全检查

这里最关键的变化是：

- 旧体系里前后车只是被动 gap 身份
- 当前体系里 `p/m/s` 共同参与造 gap
- `u/f` 不属于 `TCG` 内核，只在存在时才进入边界安全证书

### 3.3 A 层场景为什么只看 `p/m/s`

在最小诊断场景里，`u/f` 不是必须角色。

理由很简单：

- A 层的目的是先判断算法核心有没有“主动造 gap 的脑子”
- 如果一开始就把 `u/f` 也塞进去，很容易把边界压缩效应和主算法能力混在一起

因此当前冻结为：

- `A0-A3` 首版默认只看 `p/m/s`
- `u/f` 只在后续边界应力测试再单独引入

### 3.4 FIFO 语义如何保留

这份最小方案仍然保留 FIFO，但 FIFO 的含义冻结成：

- **FIFO 约束的是局部相对顺序**
- **不是要求系统只能等待自然 gap**

具体地：

1. 用当前 tick 的观测和短时预测，识别 `m` 对应的三车协同组 `TCG=(p,m,s)`
2. 之后允许通过控制 `p/m/s` 去实现这个顺序下的未来合流
3. 不允许在同一 tick 内把 `m` 改插到别的 `TCG`

也就是说：

- 顺序还是 FIFO
- 能力从“被动等 gap”升级成“主动实现这个顺序”

## 4. 状态、决策变量与预测模型

### 4.1 控制状态

对受控车辆 `i ∈ {p,m,s}`，定义纵向状态为：

\[
\xi_i(t)=
\begin{bmatrix}
x_i(t)\\
v_i(t)\\
a_i(t)
\end{bmatrix}
\]

其中：

- `x_i(t)`：纵向位置
- `v_i(t)`：纵向速度
- `a_i(t)`：纵向加速度

这份最小方案不显式优化横向自由度；横向只保留模板化执行层。

### 4.2 上层决策变量

上层不直接优化完整轨迹，而是只规划终端 merge target：

\[
z=
\left(x_m^*,\ t_m^*,\ v^*\right)
\]

其中：

- `x_m^*`：匝道车完成并入时的 `completion anchor`
- `t_m^*`：匝道车完成并入时刻
- `v^*`：三车在 `t_m^*` 处希望对齐的目标速度

对应地，前后两车的终端位置不是独立变量，而是由终端安全间距导出：

\[
x_p^* = x_m^* + d_{pm}^*(v^*)
\]

\[
x_s^* = x_m^* - d_{ms}^*(v^*)
\]

### 4.3 可选边界车的外生预测

对不直接控制的边界车 `j ∈ {u,f}`，最小版采用低复杂度预测：

\[
\hat x_j(\tau)=x_{j,k}+v_{j,k}\tau+\frac{1}{2}\hat a_{j,k}\tau^2
\]

其中 `\tau = t-t_k`，`t_k` 是当前 planning tick 起点。

最小版允许两种冻结实现：

- 常速预测：`\hat a_{j,k}=0`
- 常加速度预测：`\hat a_{j,k}=a_{j,k}`

本稿默认优先使用常速预测，因为它更稳定、也更容易把安全函数保持为低阶多项式。

## 5. fixed / flexible 的统一方式

旧设计里 `fixed` 和 `flexible` 常被理解成两套不同逻辑。

在这份方案里，它们只是对 `x_m^*` 的不同约束：

### 5.1 fixed anchor

\[
x_m^* = x_{\mathrm{fix}}
\]

上层只需要搜索：

\[
\left(t_m^*, v^*\right)
\]

### 5.2 flexible anchor

\[
x_m^* \in [x_{\min}^{\mathrm{merge}},\ x_{\max}^{\mathrm{merge}}]
\]

上层搜索：

\[
\left(x_m^*, t_m^*, v^*\right)
\]

因此，fixed / flexible 的差别不在下层控制器，而只在上层 admissible set。

## 6. merge branch：未来合流终端目标规划

### 6.1 终端安全间距

在完成并入时刻 `t_m^*`，要求三车形成终端队形：

\[
x_p^* = x_m^* + d_{pm}^*(v^*)
\]

\[
x_s^* = x_m^* - d_{ms}^*(v^*)
\]

最小版采用线性头距形式：

\[
d_{pm}^*(v)=L+s_0+h_{pr}v
\]

\[
d_{ms}^*(v)=L+s_0+h_{rf}v
\]

其中：

- `L`：车辆长度
- `s_0`：最小静态间距
- `h_pr`：前向终端头距
- `h_rf`：后向终端头距

### 6.2 “主动造 gap”的量化定义

定义在 horizon `H=t_m^*-t_k` 下，自由运动时的自然可用 gap 为：

\[
G_{\mathrm{free}}(H)
=
x_p^{\mathrm{free}}(H)-x_s^{\mathrm{free}}(H)
\]

完成合流所需总 gap 为：

\[
R(v^*)
=
d_{pm}^*(v^*)+d_{ms}^*(v^*)
\]

则需要主动创造的 gap 量为：

\[
\Delta_{\mathrm{open}}(H,v^*)
=
\max\left(0,\ R(v^*)-G_{\mathrm{free}}(H)\right)
\]

解释如下：

- 若 `\Delta_open = 0`，说明自然 gap 已够，主动协同不是必须
- 若 `\Delta_open > 0`，说明系统必须通过控制 `p/m/s` 去补出这部分 gap

这就是“主动造 gap”的数学定义。

### 6.3 上层可行域

对任意候选 `z=(x_m^*, t_m^*, v^*)`，必须同时满足：

#### 1. 时间可行

\[
H=t_m^*-t_k > 0
\]

\[
H \in \mathcal T_H
=
\{H_{\min}, H_{\min}+\Delta t,\dots,H_{\max}\}
\]

#### 2. 合流位置可行

对于 `fixed`：

\[
x_m^* = x_{\mathrm{fix}}
\]

对于 `flexible`：

\[
x_m^* \in \mathcal X_{\mathrm{flex}}
\subseteq [x_z^s,\ x_z^e]
\]

#### 3. 速度可行

\[
v^* \in \mathcal V
\subseteq [0,\ \min(v_{\max}^{\mathrm{ramp}}, v_{\max}^{\mathrm{main}})]
\]

#### 4. 终端 reachability

对 `p`、`m`、`s` 先做快速可达性预筛：

\[
x_i^* \in \mathcal R_i(H)
\]

一个最小可用的 reachability 包络可写成：

\[
\mathcal R_i(H)=
\left[
x_{i,k}+v_{i,k}H-\frac{1}{2}b_i^{\max}H^2,\
x_{i,k}+v_{i,k}H+\frac{1}{2}a_i^{\max}H^2
\right]
\]

其中：

- 对 `p`，终端位置是 `x_p^*`
- 对 `m`，终端位置是 `x_m^*`
- 对 `s`，终端位置是 `x_s^*`

#### 5. merge-zone 几何可行

设 `T_lc(v^*)` 为横向动作持续时间，则变道开始的局部时间为：

\[
\tau_{lc}^* = H - T_{lc}(v^*)
\]

要求：

\[
\tau_{lc}^* \ge 0
\]

并且 lane-change start 位置必须落在合法区间内：

\[
x_{lc}^* \ge x_z^s
\]

\[
x_m^* \le x_z^e
\]

### 6.4 上层目标函数

最小版不需要一上来就做连续优化器；使用确定性有限搜索即可。

建议用固定网格枚举：

- `x_m^*` 网格
- `H` 网格
- `v^*` 网格

再按以下字典序选择最优可行目标：

\[
J(z)=
\left(
t_m^*,\
\Delta_{\mathrm{coop}}(z),\
\Delta_{\mathrm{delay}}(z),\
-\rho_{\min}(z),\
x_m^*
\right)
\]

其中：

\[
\Delta_{\mathrm{coop}}(z)
=
\left|
x_p^{\mathrm{free}}(H)-x_p^*
\right|
+
\left|
x_s^{\mathrm{free}}(H)-x_s^*
\right|
\]

\[
\Delta_{\mathrm{delay}}(z)
=
t_m^*-t_m^{\mathrm{free}}(x_m^*)
\]

\[
\rho_{\min}(z)
=
\min\Big(
x_p^*-x_m^*-d_{pm}^*(v^*),\
x_m^*-x_s^*-d_{ms}^*(v^*)
\Big)
\]

解释：

1. 先尽量早合流
2. 再尽量少扰动 `p` 和 `s`
3. 再尽量少增加匝道车 `m` 的延迟
4. 再尽量保留更大的终端安全裕度
5. 最后用 `x_m^*` 打破平局

## 7. 下层：`p/m/s` 三车五次多项式纵向轨迹

### 7.1 轨迹形式

对 `i ∈ {p,m,s}`，在当前 planning tick 上定义：

\[
\tau=t-t_k,\qquad \tau\in[0,H]
\]

\[
x_i(\tau)=c_{i,0}+c_{i,1}\tau+c_{i,2}\tau^2+c_{i,3}\tau^3+c_{i,4}\tau^4+c_{i,5}\tau^5
\]

### 7.2 边界条件

起点边界来自当前状态：

\[
x_i(0)=x_{i,k},\qquad
\dot x_i(0)=v_{i,k},\qquad
\ddot x_i(0)=a_{i,k}
\]

终点边界由上层目标给出。

对主路前车 `p`：

\[
x_p(H)=x_p^*,\qquad
\dot x_p(H)=v^*,\qquad
\ddot x_p(H)=0
\]

对匝道车 `m`：

\[
x_m(H)=x_m^*,\qquad
\dot x_m(H)=v^*,\qquad
\ddot x_m(H)=0
\]

对主路辅助车 `s`：

\[
x_s(H)=x_s^*,\qquad
\dot x_s(H)=v^*,\qquad
\ddot x_s(H)=0
\]

因此，`p`、`m`、`s` 在 merge 完成时速度对齐、加速度归零。

### 7.3 唯一闭式解

定义：

\[
\Delta x_i
=
x_i(H)-\left(x_{i,k}+v_{i,k}H+\frac{1}{2}a_{i,k}H^2\right)
\]

\[
\Delta v_i
=
v_i(H)-\left(v_{i,k}+a_{i,k}H\right)
\]

\[
\Delta a_i
=
a_i(H)-a_{i,k}
\]

则有：

\[
c_{i,0}=x_{i,k},\qquad
c_{i,1}=v_{i,k},\qquad
c_{i,2}=\frac{1}{2}a_{i,k}
\]

\[
c_{i,3}
=
\frac{10\Delta x_i-4H\Delta v_i+\frac{1}{2}H^2\Delta a_i}{H^3}
\]

\[
c_{i,4}
=
\frac{-15\Delta x_i+7H\Delta v_i-H^2\Delta a_i}{H^4}
\]

\[
c_{i,5}
=
\frac{6\Delta x_i-3H\Delta v_i+\frac{1}{2}H^2\Delta a_i}{H^5}
\]

因为 `H>0` 时该边值问题对应的线性系统非奇异，所以闭式解唯一存在。

### 7.4 动力学可行性检查

生成 quintic 轨迹之后，必须检查：

\[
0 \le v_i(\tau)\le v_{i,\max}
\]

\[
-b_i^{\max}\le a_i(\tau)\le a_i^{\max}
\]

其中：

\[
v_i(\tau)=\dot x_i(\tau)
\]

\[
a_i(\tau)=\ddot x_i(\tau)
\]

检查方法不需要密集采样；因为：

- `v_i(\tau)` 是四次多项式，极值发生在端点或 `a_i(\tau)=0` 处
- `a_i(\tau)` 是三次多项式，极值发生在端点或 `j_i(\tau)=0` 处

因此，只需检查有限个候选点。

## 8. 当前 tick 没 merge 解时的 coordination slice

### 8.1 coordination slice 的作用

coordination slice 的目标不是立即完成合流，而是：

- 继续减小 `\Delta_open`
- 继续减小三车速度错配
- 同时保持顺序与整段安全

它是一段短时纵向协调片段，长度冻结为：

\[
\Delta t_{\mathrm{exec}} = 0.1\ \mathrm{s}
\]

### 8.2 coordination slice 的推进性判据

定义当前时刻的速度错配指标：

\[
\Delta_v^k
=
|v_p(t_k)-v_m(t_k)|
+
|v_m(t_k)-v_s(t_k)|
\]

执行一个候选 coordination slice 后，对应指标记为：

\[
\Delta_v^{k+1}
=
|v_p(t_k+\Delta t_{\mathrm{exec}})-v_m(t_k+\Delta t_{\mathrm{exec}})|
+
|v_m(t_k+\Delta t_{\mathrm{exec}})-v_s(t_k+\Delta t_{\mathrm{exec}})|
\]

coordination slice 被认为“有效推进”，至少满足下列之一：

\[
\Delta_{\mathrm{open}}^{k+1}<\Delta_{\mathrm{open}}^{k}
\]

或

\[
\Delta_v^{k+1}<\Delta_v^{k}
\]

并且同时满足：

- 相对顺序不变
- 动力学约束成立
- 安全证书成立

### 8.3 coordination slice 何时启用

当前 tick 的控制优先级冻结为：

1. certified merge slice
2. certified gap-opening coordination slice
3. `SAFE_WAIT`
4. `FAIL_SAFE_STOP`

也就是说，当前 tick 没有 merge 解时，不应该默认等待。

## 9. 横向映射与 completion anchor 的恢复

这份最小方案仍然保留“上层只管 `completion anchor`，执行层再恢复横向动作”的思想。

### 9.1 横向持续时间

设：

\[
T_{lc}=T_{lc}(v^*)
\]

最小版可先冻结为常值或近常值，例如：

\[
T_{lc}^{\mathrm{MVP}}=3.0\ \mathrm{s}
\]

### 9.2 开始变道时刻

\[
\tau_{lc}^* = H - T_{lc}
\]

即：

\[
t_{lc}^*=t_k+\tau_{lc}^*
\]

### 9.3 开始变道位置

由 `m` 的纵向 quintic 直接恢复：

\[
x_{lc}^*=x_m(\tau_{lc}^*)
\]

要求：

\[
x_{lc}^* \ge x_z^s,\qquad x_m^*\le x_z^e
\]

### 9.4 横向模板

横向位移仍可使用五次模板：

\[
y_m(t)=
\begin{cases}
0, & t<t_{lc}^*\\
W\phi(\sigma), & t\in[t_{lc}^*, t_m^*]\\
W, & t>t_m^*
\end{cases}
\]

其中：

\[
\phi(\sigma)=10\sigma^3-15\sigma^4+6\sigma^5,\qquad
\sigma=\frac{t-t_{lc}^*}{T_{lc}}
\]

这样，上层仍然只管 `x_m^*, t_m^*, v^*`，横向执行不成为额外自由优化变量。

## 10. 安全证书：用整段轨迹替代旧式 gate

### 10.1 为什么必须从 gate 换成证书

旧式 gate 的核心问题是：

- 它默认候选已经生成
- 它只负责验收
- 它面对的是“现成候选”

而这里的核心对象是：

- merge target branch 生成的未来终端目标
- coordination branch 生成的短时协调片段
- 下层主动生成的整段协同轨迹

因此安全检查必须升级为：

- 对整段轨迹出具 `SafetyCertificate`

### 10.2 过程安全函数

最小版采用线性安全距离模型，以保证安全函数仍然是低阶多项式。

对 `u-p`（若 `u` 存在）：

\[
g_{up}(\tau)
=
\hat x_u(\tau)-x_p(\tau)-D_{up}(v_p(\tau))
\]

\[
D_{up}(v)=L+s_0+\tau_h v
\]

对 `p-m`：

\[
g_{pm}(\tau)
=
x_p(\tau)-x_m(\tau)-D_{pm}(v_m(\tau))
\]

\[
D_{pm}(v)=L+s_0+h_{pr}v
\]

对 `m-s`：

\[
g_{ms}(\tau)
=
x_m(\tau)-x_s(\tau)-D_{ms}(v_s(\tau))
\]

\[
D_{ms}(v)=L+s_0+h_{rf}v
\]

对 `s-f`（若 `f` 存在）：

\[
g_{sf}(\tau)
=
x_s(\tau)-\hat x_f(\tau)-D_{sf}(v_f(\tau))
\]

\[
D_{sf}(v)=L+s_0+\tau_h v
\]

这里：

- `g_{pm}`、`g_{ms}` 主要检查 lane-change interval 与并入后短时安全
- `g_{up}`、`g_{sf}` 是两侧边界约束，只在边界车存在时启用

### 10.3 检查区间

对 merge slice：

- `g_{pm}` 与 `g_{ms}` 应在 `[\tau_{lc}^*, H]` 上检查
- `g_{up}` 与 `g_{sf}` 应在整个 horizon 上检查

若保留并入后短时保护，则还需要检查：

\[
\tau\in[H,\ H+T_{\mathrm{post}}]
\]

最小版中，`[H, H+T_{post}]` 上的 `p/m/s` 可采用终端常速延拓：

\[
x_i^+(\tau)=x_i(H)+v_i(H)(\tau-H)
\]

对 coordination slice：

- 当前最小实现中，硬检查收缩为 `[\tau_{\min}, \tau_{\max}] = [0,\Delta t_{\mathrm{exec}}]` 上的动力学约束
- `g_{pm}` 与 `g_{ms}` 在 coordination 阶段不再直接作为跨车道硬证书，而是应解释为 virtual gap / pairwise error
- 详细口径以 `docs/formulas.md` 与 `docs/active_gap_literature_alignment_and_optimization.md` 为准

### 10.4 有限点精确验证

由于：

- `x_p(\tau)`、`x_m(\tau)`、`x_s(\tau)` 是 quintic
- `\hat x_u(\tau)` 与 `\hat x_f(\tau)` 是低阶多项式
- `D(v)` 对速度是线性的

所以 `g_{up}`、`g_{pm}`、`g_{ms}`、`g_{sf}` 仍然是多项式函数。

在闭区间上，多项式最小值只可能出现在：

- 区间端点
- 导数为零的驻点

因此对任意安全函数 `g(\tau)`，定义：

\[
\Omega_g
=
\{ \tau_{\min},\ \tau_{\max} \}
\cup
\{ \tau\in(\tau_{\min},\tau_{\max})\mid g'(\tau)=0 \}
\]

只要：

\[
\min_{\tau\in\Omega_g} g(\tau)\ge -\varepsilon_g
\]

就认为该函数在该区间上安全成立。

其中 `\varepsilon_g` 是数值容差。

### 10.5 证书输出

最小版 `SafetyCertificate` 至少应包含：

- `tcg_ids = (u?, p, m, s, f?)`
- `slice_kind ∈ {merge, coordination}`
- `target = (x_m^*, t_m^*, v^*)` 或 `None`
- `valid_horizon = [t_k, t_k + \Delta t_{\mathrm{exec}}]`
- `min_margin_up`
- `min_margin_pm`
- `min_margin_ms`
- `min_margin_sf`
- `binding_constraint`
- `failed_check`（若失败）

旧体系里的 `GateResult` 只能表达“过/不过”；新体系里必须能回答：

- 哪个函数最紧
- 最紧点在什么时候
- 失败是 reachability、动力学、还是整段安全

## 11. 滚动更新与提交协议

### 11.1 两条分支的滚动，不是一锤子买卖

每个 planning tick 都重复：

1. 构造当前 snapshot
2. 提取当前 ego `m` 及其 `TCG=(p,m,s)`，可选边界为 `u/f`
3. 搜索 merge target branch
4. 若 merge branch 无解，则搜索 coordination branch
5. 计算安全证书
6. 若通过，只提交一个很短的执行 slice
7. 时间前进一步，再基于新状态重算

### 11.2 提交的不是整条轨迹，而是第一段 slice

设执行片段长度为：

\[
\Delta t_{\mathrm{exec}} = 0.1\ \mathrm{s}
\]

则每次只提交：

\[
[t_k,\ t_k+\Delta t_{\mathrm{exec}}]
\]

而不是把整条 `0 \to H` 的轨迹一次性锁死。

这样做的原因是：

- 可以滚动吸收预测误差
- 可以在 lane-change 开始前持续微调 `t_m^*` 与 `v^*`
- 可以在当前还不能 merge 时继续执行 coordination slice
- 可以避免一次规划、长时间盲执行

### 11.3 何时锁 `TCG`，何时锁目标

最小版建议保留旧 `COMMITTED` 思想，但改语义：

#### `PLANNING`

- 尚未找到可认证的控制片段

#### `COMMITTED`

- 已找到第一个可认证片段
- `TCG=(p,m,s)` 被锁定
- 允许在同一 `TCG` 下每 tick 刷新 merge target、轨迹、证书和 slice
- coordination slice 也可以把系统带入 `COMMITTED`

#### `EXECUTING`

- 一旦 `t \ge t_{lc}^*`，说明横向动作已经开始
- 此时锁定当前 merge target 与 slice 家族
- 不再允许切换 `TCG` 或重定 merge target

这样做可以避免：

- `TCG` 在相邻 tick 上来回跳
- 横向已开始后还重新解释顺序
- 当前还没 merge 就把整条轨迹一次性锁死

## 12. fail-safe 与无解处理

### 12.1 未开始变道前无解

若当前 tick 上：

- 所有 merge slice 候选都失败
- 且所有 coordination slice 候选也失败

则输出：

- `NO_FEASIBLE_CERTIFIED_SLICE`

若 `m` 仍在安全等待区，则进入：

- `SAFE_WAIT`

此时 `m` 继续在本车道保持安全跟驰或舒适减速，等待下一 tick 重算。

### 12.2 接近末端仍无解

若：

- 连续多个 tick 无可认证 slice
- 且 `m` 已逼近 `emergency tail`
- 或剩余可用距离已经小于最小横向执行需求

则进入：

- `FAIL_SAFE_STOP`

执行：

- 匝道车最大允许制动
- 保持本车道
- 记录一次 `ABORTED`

### 12.3 已开始变道后的证书失效

一旦进入 `EXECUTING`：

- 不允许切换 `TCG`
- 不允许重新解释顺序

若后续 tick 上常规重算失败，则：

1. 先继续执行上一个已认证 slice
2. 同时只在同一 `TCG` 上求解“应急 continuation”
3. 若应急 continuation 也失败，则执行最大制动并记 `ABORTED`

这条规则的目的是避免“半路 decommit”。

## 13. 这套最小方案为什么真的比旧算法更有“脑子”

可以把新旧两种逻辑对比成：

### 旧逻辑

- 给定 `x_m`
- 预测当前有没有现成 gap
- 没有就等待或失败

### 新逻辑

- 先识别 `TCG=(p,m,s)`
- 主动选择未来 `(x_m^*, t_m^*, v^*)`
- 主动决定 `p` 和 `s` 在未来应该到哪里
- 若当前还不能 merge，则优先执行 coordination slice
- 再生成 `p/m/s` 三车轨迹，把未来合规 gap 做出来

所以它的“脑子”体现在：

1. 不再把 gap 当外界赠品
2. 而是把 gap 当一个可被规划出来的未来目标
3. 当前还不能 merge 时，也不会立刻退回“等”

## 14. A 层微场景如何验证这套算法

### 14.1 A0：三车主动造 gap 是否真的发生

场景：

- 主路：`p=11, s=5`
- 匝道：`m=9`
- 初速相同
- 首版不引入 `u/f`

新算法要验证的不是“是否找到了现成 gap”，而是：

1. 是否识别出唯一 `TCG=(p,m,s)`
2. 是否出现了正的 `\Delta_open`
3. 是否通过控制 `p/m/s` 最终得到可认证的 merge 条件
4. 是否在整段证书上无碰撞、无安全违规

如果 A0 可行且 `\Delta_open > 0`，就说明系统真的在主动造 gap。

### 14.2 A1：fixed / flexible 差异是否可解释

仍使用：

- 主路：`p=11, s=5`
- 匝道：`m=9`
- 首版不引入 `u/f`

比较对象：

- `fixed`: `x_m^*=x_fix`
- `flexible`: `x_m^*` 可搜索

A1 不只看“能不能过”，更要看：

- 谁的 `t_m^*` 更早
- 谁的 `\Delta_coop` 更小
- 谁的 `\Delta_delay` 更小
- 谁的证书最小裕度更大

如果 `flexible` 只是“更晚等一会儿”，但并没有减少协同负担，那它不算真的更优。

### 14.3 A2：连续 FIFO 是否仍然成立

场景：

- 主路：`p=11, s=5`
- 匝道：`c=1, m=9`
- 初速相同
- 首版不引入 `u/f`

其中：

- `m` 是当前 active ramp CAV
- `c` 是其后方的下一辆 ramp CAV，不属于当前 `TCG`

验证目标：

1. 第一辆被规划的必须是更靠前的 `m`
2. `m` 完成后，`c` 才进入 active partition
3. 第二辆匝道车的 `TCG` 识别、目标规划、证书生成仍然遵守 FIFO 语义

A2 的关键不是吞吐，而是检验：

- 主动协同没有破坏“单 partition + FIFO”的顺序约束

### 14.4 A3：无解时是否能优雅失败

场景可从以下布局开始校准：

- 主路：`p=11, s=5`
- 匝道：`m=10.5`
- 初速相同
- 首版不引入 `u/f`

这个场景的目标不是“想办法挤过去”，而是验证：

1. 在当前位置、剩余距离和控制界限下
2. 若 merge branch 与 coordination branch 都无法通过
3. 系统是否会明确返回 `NO_FEASIBLE_CERTIFIED_SLICE`
4. 是否不会假成功、不会乱撞、不会偷偷换序

### 14.5 A 层输出应该新增什么

为了让这套算法可诊断，A 层 trace 至少要记录：

- 当前 tick 的 `TCG` 身份
- 当前 tick 的 `slice_kind ∈ {merge, coordination}`
- 上层枚举过的 `(x_m^*, t_m^*, v^*)`
- 每个候选失败在 reachability / dynamics / certificate 的哪一层
- `\Delta_open`
- `\Delta_coop`
- `\Delta_delay`
- `binding_constraint`
- `delta_open_before/after`
- `speed_alignment_before/after`
- 最终提交的 slice

否则，你只能知道“过了/没过”，却不知道系统有没有真的在主动造 gap。

## 15. 最小可实现版本的主循环

可以把整套最小算法压缩成下面这条链：

```text
observe snapshot
-> choose active ramp ego m
-> identify TCG (p, m, s)
-> try certified merge slice
-> if none: try certified gap-opening coordination slice
-> if still none: safe_wait / fail-safe
-> rollout one tick
-> next tick
```

与旧体系最本质的区别只有一句：

- **旧体系枚举的是现成 gap**
- **新体系枚举的是未来终端状态，并允许当前 tick 先执行 coordination slice**

## 16. 后续回写正式文档时最应该保留的东西

如果这份稿子后面要继续揉进正式 `docs/`，我建议保留这些已被证明有价值的语义：

- `completion anchor`
- `legal merge zone`
- `single active decision partition`
- `0.1s` rolling
- 明确的 `FAIL_SAFE_STOP`
- `COMMITTED` / `EXECUTING` 的锁定思想
- `TCG=(p,m,s)` 三车协同组
- `coordination slice` 的独立语义
- A0-A3 首版只看 `p/m/s`

而应被替换掉的旧主线是：

- “同一 `x_m` 下找现成 FIFO gap”
- “共享 gate 被动验收候选”
- “无候选时只能等待自然 gap”
- “`TargetPair` + `m/s` 双车控制” 这套旧草案口径

## 17. 一句话总结

这份最小方案的核心不是“更聪明地挑 gap”，而是：

- **先识别 `TCG=(p,m,s)`**
- **再规划未来的 merge target**
- **若当前还不能 merge，则优先执行一段 coordination slice**
- **最后用整段安全证书保证它不是碰运气**

这就是当前最小、但真正有“脑子”的主动造 gap 算法。
