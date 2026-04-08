# 主动造 Gap 文献对齐与下一轮优化记录

> 本文档记录当前 `active_gap_v1` 与代表性论文的对比、已确认的设计差距、coordination 控制器下一轮重构方向，以及后续文档同步要求。
>
> 本文档**不是**详细数学推导真源；详细定义与推导仍分别以 `docs/design.md`、`docs/formulas.md`、`docs/derivations.md` 为准。
>
> 最后更新：`2026-04-08T18:32:00+08:00`

---

## 1. 目的与使用方式

这份记录服务两个目标：

1. 把这次论文阅读后确认的关键结论固定下来，避免后续重复讨论。
2. 给下一轮算法优化提供统一路线，确保实现、实验和正式文档朝同一个方向收敛。

使用原则：

- 本文档允许记录“当前实现”和“下一轮目标”的差异。
- 本文档不重复展开详细证明；推导责任放在 `docs/derivations.md`。
- 当下一轮控制律真正落码时，必须同步更新：
  - `docs/design.md`
  - `docs/formulas.md`
  - `docs/derivations.md`
  - `docs/active_gap_minimal_control_design.md`
  - `docs/contracts.md`
  - `docs/features/active_gap_v1/T2_*.md`
  - `docs/features/active_gap_v1/T4_*.md`
  - `docs/features/active_gap_v1/T5_*.md`
  - `docs/features/active_gap_v1/T6_*.md`

---

## 2. 本次参考论文

### 2.1 2017：固定 merge 点 + 闭式最优控制

论文：

- `docs/Automated_and_Cooperative_Vehicle_Merging_at_Highway_On-Ramps.pdf`

本次抽取到的核心结论：

- 使用 FIFO 队列和固定 merge zone。
- 通过为车辆分配通过 merge zone 的时序，再用闭式最优控制求每辆车的纵向加速度。
- 主线车**可以主动加速**为后方创造空间；当容量逼近时，后车再减速。
- 该工作证明了“主动造 gap”并不要求主线前车先减速。

这篇论文对我们的启发主要是：

- `p` 完全可以作为主动控制对象。
- “主线前车先加速拉空间”是合理且有文献支持的。

### 2.2 2023：分层 + 灵活 merge 位置 + 时变安全约束

论文：

- `docs/Safety-Critical_and_Flexible_Cooperative_On-Ramp_Merging_Control_of_Connected_and_Automated_Vehicles_in_Mixed_Traffic.pdf`

本次抽取到的核心结论：

- 使用三车协同组（leading / merging / assisted），与当前 `TCG=(p,m,s)` 思路高度接近。
- 上层先规划 **expected merging position**，不是死盯固定 merge 点。
- 下层不是直接拿最终 merge 安全距离硬卡整个 coordination 过程，而是构造**时变 headway**，让安全要求随 merge 进度逐步收紧。
- 真正触发 merge 前，同时看：
  - 两侧 gap 偏差是否进入阈值
  - 相对速度偏差是否进入阈值

这篇论文对我们的核心启发是：

- `g_pm / g_ms` 在 coordination 阶段不应直接扮演“当前硬安全证书”。
- 它们应先以“虚拟 gap / 时变 headway / pairwise 误差”的形式驱动调速。
- 到真正进入 merge 阶段时，再恢复成硬证书。

---

## 3. 当前算法状态（2026-04-08）

已经具备的能力：

- `TCG=(p,m,s)` 三车协同组
- `fixed / flexible` merge target
- `merge -> coordination -> safe_wait -> fail_safe` 执行主线
- 整段轨迹级 `SafetyCertificate`
- `p` 可主动加速、`s` 可主动减速、`m` 可保持或微调
- 滚动重规划和第一段 slice 提交
- coordination 已切到 `e_{pm}^{virt} / e_{ms}^{virt}` 双误差控制
- merge gate 已显式检查 pairwise virtual gap readiness 与 relative-speed readiness

当前已确认的简化或不足：

- 还没有引入论文中的能量目标、CLF/CBF/QP 或等价的更细控制器。
- `Δ_open` 仍保留在 trace / 实验口径里，但已退化为辅助诊断量。
- 文档曾经把 coordination 阶段的 `g_pm/g_ms` 误写成硬安全证书；本轮已纠偏。

---

## 4. 当前算法与论文的比较

### 4.1 我们当前已经优于论文或更工程化的点

- **连续轨迹安全证书更明确**：当前实现会对整段轨迹做连续区间验证，而不是只依赖终点时序或优化器内部约束。
- **状态机和 fail-safe 更完整**：`coordination / safe_wait / fail_safe` 的显式语义比单一 OCP 更利于工程落地。
- **边界车语义更清楚**：`u/f` 被明确成可选边界预测对象，不和三车受控集混淆。
- **调试可解释性更强**：`slice_kind`、证书最紧约束、trace 输出都适合做数值验证和回归。

### 4.2 当前仍明显弱于论文的点

- **coordination 仍偏启发式**：虽然已经切到 pairwise virtual gap，但控制律仍是饱和比例控制，不是论文中的 FCBF / QP 最优控制。
- **merge readiness 仍需继续打磨**：当前已显式检查 pairwise virtual gap 和 relative speed，但阈值、迟滞和稳定性门槛还需要系统化冻结。
- **缺少能量最优性目标**：当前更多是可行性 + 启发式，不是优化意义上的“接近论文效果”。

### 4.3 与 2017 / 2023 两类路线的定位关系

- 相比 2017：我们已经从“固定 merge 点 + 时序调度”走向了“灵活 merge target + 局部三车协同”。
- 相比 2023：我们已经有了 `TCG`、rolling、flexible anchor 和 pairwise virtual gap 的主骨架，但还没有引入其更完整的 FCBF / QP 优化框架。

---

## 5. coordination 控制器的正式重构方向

### 5.1 `g_pm / g_ms` 的双角色

这次确认后的统一语义如下：

- **coordination 阶段**：`g_pm / g_ms` 首先是“未来 merge 条件还差多少”的**虚拟误差**。
- **merge 阶段**：`g_pm / g_ms` 才恢复为“当前 lane-change 过程必须满足”的**硬安全证书**。

也就是说，它们不是被删除了，而是被拆成了两个阶段的两种角色。

### 5.2 已替换掉的历史聚合代理

第一版实现曾使用聚合版：

\[
\Delta_{open}^{agg}
=
\max\left(0,\ D_{pm}(v_{ref})+D_{ms}(v_{ref})-(x_p-x_s)\right)
\]

它的优点是简单，但缺点也很清楚：

- 一侧富余 gap 会掩盖另一侧不足 gap
- 无法决定应该优先让 `p` 动，还是让 `s` 动，还是让 `m` 微调
- 不能自然表达“gap 已够，但 relative speed 还没对齐”的状态

### 5.3 论文对齐后的 pairwise 虚拟 gap 目标

当前版本已经把 coordination 目标显式拆成两侧误差：

\[
e_{pm}^{virt}
=
\max\left(0,\ D_{pm}^{virt}-(x_p-x_m)\right)
\]

\[
e_{ms}^{virt}
=
\max\left(0,\ D_{ms}^{virt}-(x_m-x_s)\right)
\]

其中：

- `D_{pm}^{virt}`、`D_{ms}^{virt}` 不是最终 merge 阶段的硬安全距离
- 它们应是**随 merge 进度逐步收紧**的时变虚拟距离
- 在 `m` 还远离目标 merge 位置时，它们可以显著小于最终 `D_{pm}`、`D_{ms}`
- 越接近 merge，越逐步收敛到最终硬安全距离

### 5.4 建议的控制律骨架

本轮先固定方向，不固定最终参数：

- 若 `e_{pm}^{virt}` 偏大：优先让 `p` 加速，必要时允许 `m` 轻微减速
- 若 `e_{ms}^{virt}` 偏大：优先让 `s` 减速，必要时允许 `m` 轻微加速
- 若两侧都接近收敛：优先做三车相对速度对齐

建议把控制律写成“误差驱动 + 速度对齐”的组合形式，例如：

- `a_p = + open_term(e_pm^{virt}) + sync_term(v_ref-v_p)`
- `a_m = balance_term(e_ms^{virt}-e_pm^{virt}) + sync_term(v_ref-v_m)`
- `a_s = - open_term(e_ms^{virt}) + sync_term(v_ref-v_s)`

其中：

- `open_term` 负责造 gap
- `sync_term` 负责速度收敛
- `balance_term` 负责在两侧 gap 不平衡时决定 `m` 是否需要微调

本记录只固定方向，不固定具体增益和饱和值。

### 5.5 merge 触发条件的目标升级

当前 merge readiness 已至少同时检查：

- `e_{pm}^{virt}` 已进入小阈值
- `e_{ms}^{virt}` 已进入小阈值
- `|v_p-v_m|` 已进入小阈值
- `|v_m-v_s|` 已进入小阈值

也就是说，**gap 与 relative speed 要一起达标**，而不是只看单一量。

---

## 6. 文档差异与同步要求

本轮确认的文档差异主要有三类：

1. **design 差异**
当前顶层设计过去强调了 coordination 优先级，但没有把 `g_pm/g_ms` 的双角色写清楚。

2. **formulas 差异**
旧公式把 coordination 阶段也写成“四条安全函数硬检查”，这会误导实现者把跨车道 gap 当当前证书。

3. **derivations 差异**
推导文档过去解释了为什么要主动造 gap，但没有把“为什么 coordination 阶段先用虚拟 gap，再在 merge 阶段恢复硬证书”讲透。

本轮已同步更新：

- `docs/design.md`
- `docs/formulas.md`
- `docs/derivations.md`

本轮算法重构已经落地；后续若继续优化控制律或阈值策略，还必须继续同步：

- `docs/contracts.md`
- `docs/active_gap_minimal_control_design.md`
- `docs/features/active_gap_v1/T2_merge_target_planner.md`
- `docs/features/active_gap_v1/T4_execution_and_state_machine.md`
- `docs/features/active_gap_v1/T5_metrics_and_trace.md`
- `docs/features/active_gap_v1/T6_micro_scenarios_and_regression.md`

---

## 7. 待解决问题

### 7.1 控制律本身

- 进度变量如何冻结：按 `m` 的位置、按时间、还是按 expected merge position 的归一化位置
- `m` 在 coordination 中应保持中性，还是在两侧误差失衡时参与补偿
- `e_{pm}^{virt}` 与 `e_{ms}^{virt}` 的权重如何设置
- 速度对齐项与 gap 误差项如何做优先级切换

### 7.2 证书与触发条件

- coordination 阶段是否保留 `u/f` 边界硬约束
- merge readiness 的 `ε_z / ε_v` 门槛如何冻结
- merge 前是否增加“稳定若干 tick”的要求

### 7.3 目标函数与论文效果

- 是否引入能量代理项（例如 `\int a^2 dt` 或离散近似）
- 是否把当前 ranking / heuristic 升级为更接近论文的优化目标
- 如何用统一实验把当前算法与论文式策略对比：
  - merge duration
  - fuel / energy proxy
  - peak acceleration
  - relative-speed stability
  - fail-safe rate

### 7.4 后续扩展

- 混合交通（HDV）扰动
- `c-m` 匝道后车安全
- 更高密度和更高初速下的可达性边界

---

## 8. 一句话结论

这轮论文对齐并落地实现后，最重要的结论只有一句：

> 当前算法已经完成从“总 gap 启发式”到“`g_pm^virt / g_ms^virt` 双误差 + relative-speed readiness”控制体系的第一轮重构；下一轮真正要继续提升的，是 target 平滑、readiness 迟滞和更接近论文的 FCBF / QP 优化层。
