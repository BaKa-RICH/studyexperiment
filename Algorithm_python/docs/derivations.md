<!--
Derived-From: manual
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 主动造 Gap 单匝道数值验证推导

> 本文档集中解释 `docs/formulas.md` 中关键定义的由来、理由与证明责任。
>
> 系统主线见 `docs/design.md`，公式定义见 `docs/formulas.md`。
>
> 最后更新：`2026-04-07T22:48:56+08:00`

## 1. 使用原则

- 本文档解释“为什么这样定义”，不再重复写系统主循环。
- 本文档服务于当前主算法，不再为旧 `Step 2 / Step 3 / gate` 主叙事辩护。
- 若某条理由与 `docs/design.md`、`docs/contracts.md`、`docs/formulas.md` 冲突，以那三份正式 SSOT 为准。

## 2. 本文当前负责回答的问题

1. 为什么必须从“找现成 gap”切换到“规划未来 merge target”
2. 为什么对象要从 `TargetPair` 升级成 `TCG`
3. 为什么当前应把 `p/m/s` 作为受控车，而把 `u/f` 当可选边界
4. 为什么当前 tick 没 merge 解时，不应该默认等待
5. 为什么 `fixed / flexible` 只是不同 admissible set
6. 为什么三车 quintic 在给定边界条件下唯一可解
7. 为什么 `SafetyCertificate` 优于旧 gate
8. 为什么 `COMMITTED` 先锁 `TCG`、`EXECUTING` 再锁 target
9. 为什么只 commit 第一段 slice
10. 为什么 A 场景首版应该只看 `p/m/s`

## 3. 为什么必须从“找现成 gap”切换到“规划未来 merge target”

旧主线真正做的事情是：

1. 在当前 snapshot 下预测到某个 `x_m`
2. 看是否存在现成可插入 gap
3. 若没有，则等待

这条链无法回答一个更关键的问题：

> 如果当前 gap 不够，但在未来 `1s ~ 3s` 内通过车辆协同可以把 gap 调开，系统该怎么办？

这正是 `A0/A1` 的三车场景 `p=11,m=9,s=5` 暴露出来的问题。

因此，问题必须从：

\[
\text{enumerate current gap}
\]

切换到：

\[
\text{plan future merge target } (x_m^*, t_m^*, v^*)
\]

这是当前 SSOT 换脑子的第一原则。

## 4. 为什么对象要从 `TargetPair` 升级成 `TCG`

在“`m/s` 双车受控”版本里，`TargetPair` 这个名字还勉强说得过去，因为真正被控制的核心关系是一个前后对。

但在你现在拍板的版本里，真正参与协同控制的是：

- `p`
- `m`
- `s`

这时如果继续用 `TargetPair`，会产生两个问题：

1. 名称会误导实现者，以为只有两个核心受控对象。
2. 锁定语义会变得别扭，因为 `COMMITTED` 锁的其实已经不是 pair，而是整个局部三车组。

因此对象必须升级成：

\[
TCG = (p,m,s)
\]

也就是三车协同组。

`u/f` 仍然不是 TCG 内核的一部分，它们只是：

- 三车组的上游边界
- 三车组的下游边界

## 5. 为什么当前应把 `p/m/s` 作为受控车，而把 `u/f` 当可选边界

### 5.1 为什么 `p` 应该进入受控集

如果只控制 `m/s`，那意味着：

- `m` 负责调自己的到达时机
- `s` 负责在后面让出空间
- `p` 只能被动运动

这会人为压缩“主动造 gap”的可控自由度。

而在你当前认可的控制语义里，`p` 也完全可以：

- 感知 `m` 的运动
- 通过轻微加速/减速配合形成更好的前向空间

因此，真正自然的最小受控集应当是：

\[
\{p,m,s\}
\]

### 5.2 为什么 `u/f` 仍然不进入受控内核

一旦把 `p` 和 `s` 都放进受控集，就自然会出现边界安全问题：

- `p` 调速时，不能撞到它前面的车 `u`
- `s` 调速时，不能被它后面的车 `f` 顶上来

所以 `u/f` 必须进入安全验证，但它们不一定需要进入主动协同控制。

把它们作为：

- 可选边界预测车

而不是：

- 核心受控车

是当前最稳妥的结构收缩。

## 6. 为什么当前 tick 没 merge 解时，不应该默认等待

这一点是你当前设计里最重要的新拍板之一。

如果“当前 tick 没 merge 解”就直接等价于：

\[
safe\_wait
\]

那么系统很容易重新退回旧逻辑：

- 先看当前能不能 merge
- 不能就等

这和主动造 gap 的目标是矛盾的。

因此，当前 tick 的正确优先级必须是：

1. 先问：有没有 certified merge slice
2. 若没有，再问：有没有 certified gap-opening coordination slice
3. 还没有，再问：能不能安全等待 `0.1s`
4. 连等都不安全，才 fail-safe

这背后的控制逻辑是：

- “当前还不能合流”
- 不等于“当前没有控制动作”

在滚动优化语义里，当前 tick 仍然可以做一件重要的事：

- 继续把 gap 调开

因此 coordination slice 不是补丁，而是主算法的一部分。

## 7. 为什么 `fixed / flexible` 只是不同 admissible set

旧叙事里，`fixed` 与 `flexible` 容易被误解成两套不同算法。

但在当前 completion-anchor 语义下，两者真正的差别只有：

\[
fixed:\quad x_m^*=x_{fix}
\]

\[
flexible:\quad x_m^* \in \mathcal X_{flex}
\]

而其余部分完全相同：

- 都要搜索 `t_m^*`
- 都要搜索 `v^*`
- 都要满足同一组终端安全距离
- 都要走同一个三车 quintic 求解器
- 都要通过同一套 `SafetyCertificate`

所以，`fixed / flexible` 的正确理解是：

- 同一个控制框架
- 不同的 `x_m^*` admissible set

## 8. 为什么三车 quintic 唯一可解

对任意受控车辆 `i \in \{p,m,s\}`，轨迹写成：

\[
x_i(\tau)=c_{i,0}+c_{i,1}\tau+c_{i,2}\tau^2+c_{i,3}\tau^3+c_{i,4}\tau^4+c_{i,5}\tau^5
\]

给定起点边界：

\[
x_i(0),\ \dot x_i(0),\ \ddot x_i(0)
\]

和终点边界：

\[
x_i(H),\ \dot x_i(H),\ \ddot x_i(H)
\]

低阶系数先由起点确定：

\[
c_{i,0}=x_i(0),\qquad
c_{i,1}=\dot x_i(0),\qquad
c_{i,2}=\frac{1}{2}\ddot x_i(0)
\]

剩下未知量只有：

\[
(c_{i,3}, c_{i,4}, c_{i,5})
\]

它们满足的线性系统写成：

\[
\begin{bmatrix}
H^3 & H^4 & H^5\\
3H^2 & 4H^3 & 5H^4\\
6H & 12H^2 & 20H^3
\end{bmatrix}
\begin{bmatrix}
c_{i,3}\\
c_{i,4}\\
c_{i,5}
\end{bmatrix}
=
\begin{bmatrix}
\Delta x_i\\
\Delta v_i\\
\Delta a_i
\end{bmatrix}
\]

记该矩阵为 `M(H)`，则：

\[
\det(M(H)) = 2H^9
\]

只要：

\[
H>0
\]

就有：

\[
\det(M(H)) \neq 0
\]

因此三车里每一辆车的 quintic 边值问题都唯一可解。

## 9. 为什么 `SafetyCertificate` 优于旧 gate

旧 gate 的责任链是：

- 候选已经生成完毕
- gate 只负责抽查并验收

它的问题在于：

1. 它默认候选本身已经是“差不多可行”的对象。
2. 它更适合离散抽查点，而不适合解释整段连续轨迹。
3. 它很难回答“到底哪条约束最紧、为什么失败”。

而在当前主算法里，系统的核心对象已经变成：

- 上层给出的未来 merge target
- 或者当前 tick 的 coordination slice
- 下层主动生成的整段三车轨迹

因此，安全检查的自然形式就不该再是：

\[
\text{sampled gate}
\]

而应该是：

\[
\text{trajectory-level safety certificate}
\]

这就是为什么当前主安全函数固定成：

- `g_up`
- `g_pm`
- `g_ms`
- `g_sf`

## 10. 为什么 `COMMITTED` 先锁 `TCG`、`EXECUTING` 再锁 target

如果系统一找到可行方案，就立刻把：

- `TCG`
- `MergeTarget`
- 整段轨迹

全部一起锁死，会有两个问题：

1. 在横向动作还没开始时，系统无法利用新的观测继续微调 `t_m^*` 与 `v^*`。
2. 滚动规划会被错误理解成“每次刷新都是 decommit”。

但如果什么都不锁，又会出现：

- 三车组抖动
- lane change 开始后仍重定 target

因此，最合理的双层锁定语义是：

### 10.1 `COMMITTED`

- 锁定 `TCG`
- 保持局部顺序解释稳定
- 允许在同一 `TCG` 下刷新 `MergeTarget`、轨迹、证书和 slice

### 10.2 `EXECUTING`

- 一旦横向动作开始
- 锁定当前 target 与 slice 家族
- 不再允许 re-TCG / re-target

## 11. 为什么只 commit 第一段 slice

若系统一次性把 `0 \to H` 的整条轨迹全锁死，会产生 3 个问题：

1. 预测误差会累积，但系统中途无法吸收。
2. `u/p/m/s/f` 的短时扰动无法反馈到当前控制。
3. 你会得到一条名义上平滑、但实际执行越来越偏的长时盲执行轨迹。

因此，rolling horizon 的合理执行方式必须是：

\[
\text{plan over } [t_k, t_k+H]
\]

但只 commit：

\[
[t_k,\ t_k+\Delta t_{exec}]
\]

这说明：

- 长时规划用于看未来
- 短时提交用于吸收现实

## 12. 为什么 A 场景首版应该只看 `p/m/s`

你这次关于场景的判断，我认为是对的。

在最小诊断场景里，如果一开始就把 `u/f` 也塞进去，会带来两个问题：

1. 你很难分辨算法是否真的具备“主动造 gap”的核心能力。
2. 你看到的失败可能其实来自边界压缩，而不是来自 `p/m/s` 协同本身。

因此，A 场景首版更合理的做法是：

- 只实例化 `p/m/s` 核心三车
- 让三车自由发挥
- `u/f` 只在后续边界应力测试里单独引入

这并不意味着算法层不需要 `u/f`。

它只意味着：

- **算法定义** 要支持 `u/f` 作为可选边界
- **A 层最小诊断** 不应默认把 `u/f` 当成必要参与者

这两件事并不矛盾。

## 13. 为什么当前 first slice 分成 merge / coordination 两类

这是本轮设计和旧主线最大的行为差异之一。

若所有控制片段都被当成“merge slice”，那只要当前还不满足真正 merge 条件，就只能：

- 等
- 或 fail-safe

这又会退回旧逻辑。

把 slice 明确分成：

- `merge slice`
- `coordination slice`

之后，系统才有能力表达：

- 当前不能正式并入
- 但当前这 `0.1s` 仍然有意义，因为它能继续造 gap

这正是你认可的滚动优化语义。

## 14. 一句话结论

当前 `derivations.md` 要为顶层 SSOT 解释的核心只有一句：

> 这次重写不是把旧 baseline 修得更聪明一点，而是把问题从“找现成 gap”重新定义成“围绕 `TCG=(p,m,s)` 规划未来 merge target，并在当前不能 merge 时优先执行 coordination slice”，再用四条主安全证书把这件事严谨地证明出来。
