<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T3: TCG Quintic 与 SafetyCertificate（TCG Quintics and Safety Certificate）

> 最后更新：`2026-04-08T16:00:00+08:00`

## 前置条件

- `T1_tcg_and_snapshot` 已完成。
- `T2_merge_target_planner` 已完成。
- 必读：`docs/design.md`（重点看 “下层：三车 quintic 协同”“SafetyCertificate”“当前 tick 算不出 merge 时怎么办”）。
- 必读：`docs/contracts.md`（重点看 `QuinticLongitudinalProfile`、`SafetyCertificate`、`SliceKind`）。
- 必读：`docs/formulas.md`（重点看三车 quintic、动力学极值检查、`g_up/g_pm/g_ms/g_sf`、闭区间验证）。
- 必读：`docs/features/active_gap_v1/design.md`。

## 目标

实现当前主算法最核心的数学内核：对 `TCG=(p,m,s)` 求三车 quintic，构建 `SafetyCertificate`，让 merge branch 可以产出 certified merge slice，并且在 `u/f` 缺省与存在两种情况下都能稳定工作。

## Targets

1. **三车 quintic 可直接求解**: `solve_tcg_quintics()` 能对 `p/m/s` 给出闭式轨迹，并满足起终点边界。
2. **四条安全证书可解释**: `build_safety_certificate()` 能检查 `g_up/g_pm/g_ms/g_sf`，输出最紧约束和失败分类。
3. **边界车缺省逻辑稳定**: 当 `u/f` 缺省为空时，证书不会崩坏；当 `u/f` 存在时，边界约束会自动进入。
4. **下游分支可直接消费**: `T4` 可以直接消费 `QuinticLongitudinalProfile + SafetyCertificate`，无需回退到旧 gate 逻辑。

## Acceptance Criteria

### Step 1: 实现三车 quintic 轨迹（depends on Step 4 of T2）

- [ ] `solve_tcg_quintics()` 输入为 `snapshot + tcg + target`，输出三条 `QuinticLongitudinalProfile`。
- [ ] `p/m/s` 的终端位置、速度、加速度边界与 `docs/formulas.md` 一致。
- [ ] 同一输入重复运行时，三车系数和边界状态完全一致。

### Step 2: 实现动力学极值检查（depends on Step 1）

- [ ] 对 `p/m/s` 的速度和加速度极值检查采用端点 + 根求解，而不是只靠粗采样。
- [ ] 动力学失败能被显式分类为 `CertificateFailureKind.DYNAMICS`。
- [ ] 失败时不会偷偷修改 `MergeTarget` 或轨迹系数。

### Step 3: 实现 `SafetyCertificate`（depends on Step 2）

- [ ] merge branch 下至少检查 `g_pm`、`g_ms`，并在 `u/f` 存在时追加 `g_up`、`g_sf`。
- [ ] 证书能输出 `min_margin_*`、`binding_constraint` 和 `failure_kind`。
- [ ] 闭区间验证逻辑能复盘最紧时刻，不退回 sampled gate 主语义。

### Step 4: 完成单测与可消费性验证（depends on Step 3）

- [ ] `pytest tests/active_gap_v1/test_tcg_quintic_and_certificate.py` 通过。
- [ ] merge branch 能产出 certified merge slice 所需的轨迹与证书对象。
- [ ] `T4` 可以直接消费 `QuinticLongitudinalProfile + SafetyCertificate`，无需重新解释证书规则。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法轨迹层与证书层的正式 spec 与实现目录
  - `docs/design.md` — 三车协同、证书语义与执行优先级
  - `docs/contracts.md` — `QuinticLongitudinalProfile`、`SafetyCertificate`、`SliceKind`
  - `docs/formulas.md` — 三车 quintic、极值检查、`g_up/g_pm/g_ms/g_sf`
  - `docs/features/active_gap_v1/design.md` — 模块切口与数据流

### Docs:

**Formal Specs:**

- `docs/design.md`: 下层三车轨迹、`SafetyCertificate` 与双分支控制
- `docs/contracts.md`: 轨迹对象、证书对象、失败分类
- `docs/formulas.md`: quintic、动力学极值、四条安全函数与闭区间验证

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: 工作包顺序和风险
- `docs/features/active_gap_v1/design.md`: `T2 -> T3 -> T4` 的主链关系

### Developer insights:

- **T3 是数学内核**: 这里的对象和验证口径一旦漂移，`T4-T6` 都会失去基础。
- **不允许改 target**: 证书失败只能报告失败，不能顺手改写 `MergeTarget`。
- **u/f 只影响边界约束**: `u/f` 缺省时，`g_up/g_sf` 应自动跳过，而不是让证书对象结构变化。
- **merge branch 与 coordination branch 共用证书对象**: 只是 `slice_kind` 和检查区间不同，不应长成两套完全不同的证书体系。
- **闭区间验证优先**: 只靠固定采样点会让最紧约束解释力不足，必须在 `T3` 内就把驻点检查写清。

### Editable Paths

- `src/active_gap_v1/quintic.py` — 三车 quintic 求解与动力学检查
- `src/active_gap_v1/certificate.py` — `SafetyCertificate`、安全函数与闭区间验证
- `tests/active_gap_v1/test_tcg_quintic_and_certificate.py` — 轨迹与证书测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **证书不改目标**: `build_safety_certificate()` 绝不回写 `MergeTarget`。
- **u/f 可选**: `u/f` 缺省只能影响约束启用，不得导致证书对象结构裂成两套。
- **不要回退 sampled gate**: 当前 task 不接受“只做粗采样就算通过”的实现。
- **NO_FEASIBLE_CERTIFIED_SLICE 不是 CertificateFailureKind**: 当所有候选都未通过认证时，这是 planner 层的结果，不得作为 `CertificateFailureKind` 的枚举值出现在证书内。

## Skills

### Open URL

用于核对 `docs/formulas.md` 中关于三车 quintic、证书函数和检查区间的正式定义。

### Code Exploration

用于检查 `quintic.py` / `certificate.py` 与 `docs/contracts.md` / `docs/formulas.md` 的对象映射。

### Parallel Subagent

仅在后续需要并行核对轨迹层和证书层测试夹具时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 实现三车 quintic（Step 1, depends on Phase 4 of T2）

- [ ] 1.1 实现 `p/m/s` 三车 quintic 闭式求解
- [ ] 1.2 固定起终点边界与输出对象

### Phase 2: 实现动力学极值检查（Step 2, depends on Phase 1）

- [ ] 2.1 实现速度极值检查
- [ ] 2.2 实现加速度极值检查与失败分类

### Phase 3: 实现安全证书（Step 3, depends on Phase 2）

- [ ] 3.1 实现 `g_up/g_pm/g_ms/g_sf`
- [ ] 3.2 实现闭区间验证、最紧约束输出和 `u/f` 缺省逻辑

### Phase 4: 完成可消费性验证（Step 4, depends on Phase 3）

- [ ] 4.1 验证 merge branch 可直接产出 certified merge slice 所需对象
- [ ] 4.2 为 `u/f` 缺省与存在两种情况补测试

## 你负责的文件（白名单）

```text
src/active_gap_v1/quintic.py
src/active_gap_v1/certificate.py
tests/active_gap_v1/test_tcg_quintic_and_certificate.py
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/types.py`、`config.py`、`snapshot.py`、`tcg_selector.py`（由 `T1` 负责）
- `src/active_gap_v1/predictor.py`、`merge_target_planner.py`（由 `T2` 负责）
- `src/active_gap_v1/executor.py`、`state_machine.py`（由 `T4` 负责）
- `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/*`（由 `T5/T6` 负责）
- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`（正式真源，不在本 task 内改写）

## 依赖的现有代码（需要先读的文件）

- `src/active_gap_v1/types.py`
- `src/active_gap_v1/config.py`
- `src/active_gap_v1/predictor.py`
- `src/active_gap_v1/merge_target_planner.py`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`

## 实现步骤

### 1. 实现三车 quintic 求解

- 对 `p/m/s` 统一走同一套 quintic 求解逻辑。
- 起点状态来自当前观测，终点状态来自 `MergeTarget`。
- 保证输出对象结构稳定，可直接被 `T4` 消费。

### 2. 实现动力学极值检查

- 对 `p/m/s` 分别检查速度、加速度上下界。
- 采用端点 + 根求解，不要退回粗采样近似。

### 3. 实现 `SafetyCertificate`

- merge branch 下，必须至少检查 `g_pm / g_ms`。
- `u` 存在时，启用 `g_up`。
- `f` 存在时，启用 `g_sf`。
- 输出最紧约束、最紧裕度和失败分类。

### 4. 处理 `u/f` 缺省语义

- 当 `u/f` 缺省为空时，不应构造伪边界车。
- 证书对象仍保持统一结构，只是相关 `min_margin_*` 字段可为 `None`。

### 5. 补单测

- 覆盖三车边界条件、极值检查、证书最紧约束、`u/f` 缺省与存在、merge branch 通过与失败路径。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_tcg_quintic_and_certificate.py` 通过。
- `u/f` 缺省时，`SafetyCertificate` 仍能正常工作。
- `u/f` 存在时，`g_up/g_sf` 会自动进入检查。
- 证书失败时，`failure_kind` 和 `binding_constraint` 能指出最主要失败原因。

### 组装验证（产出运行时依赖的 task，可选）

- `T4` 可以直接消费 `SafetyCertificate` 和三车轨迹，不需要重新解释安全规则。
- merge branch 可以直接产出 certified merge slice 所需对象。

### 环境验证（涉及配置加载的 task，可选）

- 所有证书检查只依赖 `ScenarioConfig` 与当前输入对象，不读取外部隐式配置。
- 轨迹与证书结果在同一输入下完全可复现。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| `MergeTarget` 列表 | `T2` | 排序与字段稳定，可直接消费 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| 三车 `QuinticLongitudinalProfile` | `T4/T5/T6` | 轨迹对象稳定、可直接执行和记录 |
| `SafetyCertificate` | `T4/T5/T6` | 证书字段稳定、可解释最紧约束 |

### 不要做

- 不要在 `T3` 内引入 execution 决策。
- 不要用 sampled gate 替代轨迹级证书。
- 不要为 `u/f` 生成伪车来“填补空值”。
