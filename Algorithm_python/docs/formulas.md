<!--
Derived-From: manual
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 主动造 Gap 单匝道数值验证公式

> 本文档集中记录当前主算法的状态定义、merge target 搜索、三车 quintic、coordination slice、`SafetyCertificate` 与默认参数公式。
>
> 对应系统主线见 `docs/design.md`。
>
> 公式推导与定义理由见 `docs/derivations.md`。
>
> 最后更新：`2026-04-08T18:32:00+08:00`

## 1. 使用原则

- 本文只放定义和公式，不展开长篇推导。
- 所有对象名与字段名必须与 `docs/contracts.md` 保持一致。
- 本文定义的是当前正式主算法，不再为旧 `Step 2 / Step 3 / gate` 体系服务。

## 2. 符号、坐标与几何

设当前 planning tick 起点为 `t_k`，局部时间写为：

\[
\tau = t - t_k
\]

merge planning horizon 写为：

\[
H = t_m^* - t_k > 0
\]

当前冻结的几何与锚点基线为：

\[
ramp\_approach\_subzone = [0m, 50m)
\]

\[
legal\_merge\_zone = [x_z^s, x_z^e] = [50m, 290m]
\]

\[
emergency\_tail = [290m, 300m]
\]

\[
x_{fix} = 170m
\]

局部对象统一记为：

- `u`：`p` 的上游边界车，只做预测
- `p`：主路前车，受控车
- `m`：匝道合流车，受控车
- `s`：主路辅助车，受控车
- `f`：`s` 的下游边界车，只做预测

## 3. 纵向状态与边界车外生预测

对受控车辆 `i \in \{p,m,s\}`，定义纵向状态：

\[
\xi_i(t)=
\begin{bmatrix}
x_i(t)\\
v_i(t)\\
a_i(t)
\end{bmatrix}
\]

对边界车 `j \in \{u,f\}`，采用低复杂度外生预测：

\[
\hat x_j(\tau)=x_{j,k}+v_{j,k}\tau+\frac{1}{2}\hat a_{j,k}\tau^2
\]

默认优先使用常速预测：

\[
\hat a_{j,k}=0
\]

## 4. fixed / flexible 的统一约束

当前统一把 merge point 的物理语义冻结成 completion anchor `x_m^*`。

### 4.1 fixed

\[
x_m^* = x_{fix}
\]

### 4.2 flexible

\[
x_m^* \in \mathcal X_{flex} \subseteq [x_z^s, x_z^e]
\]

因此，`fixed/flexible` 的区别只在 `x_m^*` 的 admissible set，而不在下层控制器。

## 5. merge branch：终端安全约束与主动造 gap 量化

### 5.1 终端安全距离

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

### 5.2 自然 gap 与主动补 gap

定义受控车辆 `i` 在当前 tick 起点保持当前速度、不施加控制的自由运动位置（常速预测）：

\[
x_i^{free}(H)=x_{i,k}+v_{i,k}H
\]

注意：这里的"自由运动"固定为常速预测（`a=0`），不使用当前加速度外推，以保证 `\Delta_open` 的物理解释稳定。

定义当前在自由运动下的自然可用 gap：

\[
G_{free}(H)=x_p^{free}(H)-x_s^{free}(H)
\]

定义完成并入所需总 gap：

\[
R(v^*)=d_{pm}^*(v^*)+d_{ms}^*(v^*)
\]

则系统需要主动补出的 gap 量为：

\[
\Delta_{open}(H,v^*)
=
\max\left(0,\ R(v^*)-G_{free}(H)\right)
\]

当 `\Delta_open > 0` 时，说明算法不是在“等现成 gap”，而是在通过 `p/m/s` 协同把未来 gap 做出来。

### 5.3 coordination 的历史聚合代理与当前 pairwise virtual gap

在第一版闭环里，coordination 曾使用一个聚合版代理：

\[
\Delta_{open}^{agg}(t_k)
=
\max\left(
0,\
D_{pm}(v_{ref}^k)+D_{ms}(v_{ref}^k)-(x_p(t_k)-x_s(t_k))
\right)
\]

其中：

\[
v_{ref}^k=\frac{v_p(t_k)+v_m(t_k)+v_s(t_k)}{3}
\]

这个代理适合第一版数值闭环，但它有一个已知局限：

- 它只能回答“总 gap 是否还不够”
- 不能区分“不够的是 `p-m` 一侧”还是“不够的是 `m-s` 一侧”

为了与 2023 分层 / 时变 headway 思路对齐，当前版本已经将 coordination 目标显式拆成两侧虚拟 gap 误差。

定义 merge 进度变量（建议冻结为按期望 merge 位置归一化的位置进度）：

\[
\xi_k
=
\mathrm{clip}\!\left(
\frac{x_m(t_k)-x_m(t_0)}
{x_m^{exp}-x_m(t_0)+\varepsilon_x},
0,1
\right)
\]

定义时变虚拟头距：

\[
h_{pm}^{virt}(\xi_k)=\xi_k h_{pr}
\]

\[
h_{ms}^{virt}(\xi_k)=\xi_k h_{rf}
\]

定义时变虚拟距离：

\[
D_{pm}^{virt}(\xi_k,v_m)
=
L+s_0+h_{pm}^{virt}(\xi_k)v_m
\]

\[
D_{ms}^{virt}(\xi_k,v_s)
=
L+s_0+h_{ms}^{virt}(\xi_k)v_s
\]

定义两侧虚拟 gap 误差：

\[
e_{pm}^{virt}(t_k)
=
\max\left(0,\ D_{pm}^{virt}(\xi_k,v_m(t_k))-(x_p(t_k)-x_m(t_k))\right)
\]

\[
e_{ms}^{virt}(t_k)
=
\max\left(0,\ D_{ms}^{virt}(\xi_k,v_s(t_k))-(x_m(t_k)-x_s(t_k))\right)
\]

当前 coordination 控制器优先驱动：

\[
e_{pm}^{virt}\to 0,\qquad e_{ms}^{virt}\to 0
\]

其中 `\Delta_{open}^{agg}` 仍可保留为兼容旧实验的辅助诊断量，但不再是主控制目标。

## 6. merge branch：上层可行域与字典序目标

设上层搜索变量为：

\[
z=(x_m^*, t_m^*, v^*)
\]

### 6.1 时间可行域

\[
H=t_m^*-t_k
\]

\[
H \in \mathcal T_H=\{H_{min}, H_{min}+\Delta t, \dots, H_{max}\}
\]

### 6.2 速度可行域

\[
v^* \in \mathcal V
\subseteq
[0,\ \min(v_{max}^{ramp}, v_{max}^{main})]
\]

### 6.3 终端可达性预筛

对 `i \in \{p,m,s\}`，做快速可达性包络预筛：

\[
x_i^* \in \mathcal R_i(H)
\]

其中：

\[
\mathcal R_i(H)=
\left[
x_{i,k}+v_{i,k}H-\frac{1}{2}b_i^{max}H^2,\
x_{i,k}+v_{i,k}H+\frac{1}{2}a_i^{max}H^2
\right]
\]

### 6.4 merge-zone 几何可行性

设 lane-change duration 为 `T_{lc}(v^*)`，则：

\[
\tau_{lc}^*=H-T_{lc}(v^*)
\]

\[
t_{lc}^*=t_k+\tau_{lc}^*
\]

并要求：

\[
\tau_{lc}^* \ge 0
\]

\[
x_{lc}^*=x_m(\tau_{lc}^*) \ge x_z^s
\]

\[
x_m^* \le x_z^e
\]

### 6.5 字典序目标

定义：

\[
\Delta_{coop}(z)=|x_p^{free}(H)-x_p^*|+|x_s^{free}(H)-x_s^*|
\]

\[
\Delta_{delay}(z)=t_m^*-t_m^{free}(x_m^*)
\]

\[
\rho_{min}(z)=
\min\Big(
x_p^*-x_m^*-d_{pm}^*(v^*),\
x_m^*-x_s^*-d_{ms}^*(v^*)
\Big)
\]

当前推荐的字典序目标为：

\[
J(z)=
\left(
t_m^*,\
\Delta_{coop}(z),\
\Delta_{delay}(z),\
-\rho_{min}(z),\
x_m^*
\right)
\]

## 7. 三车 quintic 纵向轨迹

### 7.1 轨迹形式

对 `i \in \{p,m,s\}`，定义：

\[
x_i(\tau)=c_{i,0}+c_{i,1}\tau+c_{i,2}\tau^2+c_{i,3}\tau^3+c_{i,4}\tau^4+c_{i,5}\tau^5
\]

\[
v_i(\tau)=\dot x_i(\tau),\qquad
a_i(\tau)=\ddot x_i(\tau),\qquad
j_i(\tau)=\dddot x_i(\tau)
\]

### 7.2 起终点边界

起点边界来自当前状态：

\[
x_i(0)=x_{i,k},\qquad
\dot x_i(0)=v_{i,k},\qquad
\ddot x_i(0)=a_{i,k}
\]

对 `p`：

\[
x_p(H)=x_p^*,\qquad
\dot x_p(H)=v^*,\qquad
\ddot x_p(H)=0
\]

对 `m`：

\[
x_m(H)=x_m^*,\qquad
\dot x_m(H)=v^*,\qquad
\ddot x_m(H)=0
\]

对 `s`：

\[
x_s(H)=x_s^*,\qquad
\dot x_s(H)=v^*,\qquad
\ddot x_s(H)=0
\]

### 7.3 闭式系数

定义：

\[
\Delta x_i=
x_i(H)-\left(x_{i,k}+v_{i,k}H+\frac{1}{2}a_{i,k}H^2\right)
\]

\[
\Delta v_i=
v_i(H)-\left(v_{i,k}+a_{i,k}H\right)
\]

\[
\Delta a_i=
a_i(H)-a_{i,k}
\]

则：

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

只要 `H>0`，该边值问题唯一可解。

## 8. 动力学极值检查

生成 quintic 后，必须检查：

\[
0 \le v_i(\tau)\le v_{i,max}
\]

\[
-b_i^{max}\le a_i(\tau)\le a_i^{max}
\]

其中：

- `v_i(\tau)` 是四次多项式，极值发生在端点或 `a_i(\tau)=0` 处。
- `a_i(\tau)` 是三次多项式，极值发生在端点或 `j_i(\tau)=0` 处。

因此不需要密集采样；只需检查有限个候选点：

- `\tau = 0`
- `\tau = H`
- `a_i(\tau)=0` 的区间内实根
- `j_i(\tau)=0` 的区间内实根

当前版本中，动力学约束参数与 `ScenarioConfig` 的映射关系为：

- 对所有受控车 `i ∈ {p,m,s}`：`a_i^{max} = a_{max} = 2.6` m/s²
- 对所有受控车 `i ∈ {p,m,s}`：`b_i^{max} = b_{safe} = 4.5` m/s²
- fail-safe 制动使用 `b_{fail} = b_{safe} = 4.5` m/s²

即当前版本不区分车辆个体差异，所有受控车共用同一组动力学上下界。

## 9. coordination branch：当前 tick 还不能 merge 时的短时协调控制

设 first-slice 执行长度为：

\[
\Delta t_{exec}=0.1\ \mathrm{s}
\]

在当前 tick 无 certified merge slice 时，允许搜索 **coordination slice**。  
coordination slice 的目标不是“立即完成合流”，而是：

- 继续减小 `e_{pm}^{virt}`
- 继续减小 `e_{ms}^{virt}`
- 继续减小三车速度错配
- 同时保持顺序与整段安全

说明：

- 当前实现已按两侧虚拟 gap 分开驱动 coordination
- `\Delta_{open}^{agg}` 可继续作为兼容旧 trace 的辅助统计，但不再承担主控制律角色

定义当前速度错配指标：

\[
\Delta_v^k = |v_p(t_k)-v_m(t_k)| + |v_m(t_k)-v_s(t_k)|
\]

定义执行一个候选 coordination slice 后的对应指标：

\[
\Delta_v^{k+1} = |v_p(t_k+\Delta t_{exec})-v_m(t_k+\Delta t_{exec})|
+ |v_m(t_k+\Delta t_{exec})-v_s(t_k+\Delta t_{exec})|
\]

coordination slice 被认为“有效推进”，至少满足：

\[
e_{pm}^{virt,k+1} < e_{pm}^{virt,k}
\]

或

\[
e_{ms}^{virt,k+1} < e_{ms}^{virt,k}
\]

或

\[
\Delta_v^{k+1} < \Delta_v^{k}
\]

并且同时满足：

- 相对顺序不变
- 动力学约束成立
- 当前实现下的 coordination 证书成立

若仍采用第一版聚合代理，可把推进判据近似退化为：

\[
\Delta_{open}^{agg,k+1} < \Delta_{open}^{agg,k}
\]

因此，当前 tick 的控制优先级变成：

1. certified merge slice
2. certified gap-opening coordination slice
3. `SAFE_WAIT`
4. `FAIL_SAFE_STOP`

## 10. 横向映射与 completion anchor 恢复

### 10.1 当前波次的横向持续时间

当前波次冻结为：

\[
T_{lc}(v)=T_{lc}^{MVP}=3.0\ \mathrm{s}
\]

### 10.2 开始变道时刻与位置

\[
\tau_{lc}^*=H-T_{lc}
\]

\[
t_{lc}^*=t_k+\tau_{lc}^*
\]

\[
x_{lc}^*=x_m(\tau_{lc}^*)
\]

要求：

\[
x_{lc}^* \ge x_z^s,\qquad x_m^*\le x_z^e
\]

### 10.3 横向模板

横向位移仍采用五次模板：

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

## 11. `SafetyCertificate` 公式

### 11.1 过程安全函数

定义：

\[
D_{up}(v)=L+s_0+\tau_h v
\]

\[
D_{pm}(v)=L+s_0+h_{pr}v
\]

\[
D_{ms}(v)=L+s_0+h_{rf}v
\]

\[
D_{sf}(v)=L+s_0+\tau_h v
\]

对 `u-p`：

\[
g_{up}(\tau)=\hat x_u(\tau)-x_p(\tau)-D_{up}(v_p(\tau))
\]

对 `p-m`：

\[
g_{pm}(\tau)=x_p(\tau)-x_m(\tau)-D_{pm}(v_m(\tau))
\]

对 `m-s`：

\[
g_{ms}(\tau)=x_m(\tau)-x_s(\tau)-D_{ms}(v_s(\tau))
\]

对 `s-f`：

\[
g_{sf}(\tau)=x_s(\tau)-\hat x_f(\tau)-D_{sf}(v_f(\tau))
\]

### 11.2 检查区间

对于 merge slice：

- `g_{pm}` 与 `g_{ms}` 至少在 `[\tau_{lc}^*, H]` 上检查
- `g_{up}` 与 `g_{sf}` 在整个 horizon 上检查

对于 coordination slice（当前实现）：

- 动力学约束在 `[\tau_{min}, \tau_{max}] = [0, \Delta t_{exec}]` 上检查
- `g_{pm}` 与 `g_{ms}` 不再作为跨车道硬安全证书；它们转入 §5.3 的 virtual gap 误差语义

对于 coordination slice（后续优化方向）：

- `g_{pm}` 与 `g_{ms}` 继续不作为当前跨车道硬证书
- 若 `u/f` 被显式建模并参与边界验证，则 `g_{up}` 与 `g_{sf}` 可继续作为边界硬约束
- merge 触发前应同时要求 pairwise virtual gap 与 relative speed 都进入阈值

并入后短时保护可选增加：

\[
\tau\in[H,\ H+T_{post}]
\]

### 11.3 闭区间精确验证

由于：

- `x_p(\tau)`、`x_m(\tau)`、`x_s(\tau)` 是 quintic。
- `\hat x_u(\tau)` 与 `\hat x_f(\tau)` 是低阶多项式。
- `D(v)` 对速度是线性的。

所以 `g_{up}`、`g_{pm}`、`g_{ms}`、`g_{sf}` 仍然是多项式函数。

对任意安全函数 `g(\tau)`，定义候选检查点集合：

\[
\Omega_g=
\{\tau_{min},\ \tau_{max}\}
\cup
\{\tau\in(\tau_{min},\tau_{max})\mid g'(\tau)=0\}
\]

只要：

\[
\min_{\tau\in\Omega_g} g(\tau)\ge -\varepsilon_g
\]

就认为该函数在该闭区间上安全成立。

### 11.4 证书输出最少字段

`SafetyCertificate` 至少要记录：

- `tcg_ids`
- `slice_kind`
- `valid_from_s`
- `valid_until_s`
- `min_margin_up_m`
- `min_margin_pm_m`
- `min_margin_ms_m`
- `min_margin_sf_m`
- `binding_constraint`
- `failure_kind`

## 12. Rolling 执行与默认参数

### 12.1 first slice 长度

当前冻结：

\[
\Delta t_{exec}=0.1\ \mathrm{s}
\]

因此每次只提交：

\[
[t_k,\ t_k+\Delta t_{exec}]
\]

### 12.2 当前默认参数

\[
\Delta t_{plan}
=
\Delta t_{rollout}
=
\Delta t_{cert}
=0.1\ \mathrm{s}
\]

\[
T_{post}=1.0\ \mathrm{s},\qquad
\varepsilon_t=0.05\ \mathrm{s}
\]

\[
h_{pr}=1.5\ \mathrm{s},\qquad
h_{rf}=2.0\ \mathrm{s}
\]

\[
W=3.2\ \mathrm{m},\quad
L=5.0\ \mathrm{m},\quad
s_0=2.5\ \mathrm{m},\quad
\tau_h=1.0\ \mathrm{s}
\]

\[
a_{max}=2.6\ \mathrm{m/s^2},\quad
b_{safe}=4.5\ \mathrm{m/s^2},\quad
b_{fail}=4.5\ \mathrm{m/s^2},\quad
b_{comf}=2.0\ \mathrm{m/s^2}
\]

\[
v_{max}^{main}=25.0\ \mathrm{m/s},\qquad
v_{max}^{ramp}=16.7\ \mathrm{m/s},\qquad
T_{lc}^{MVP}=3.0\ \mathrm{s}
\]
