<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/feature-design.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# active_gap_v1 Feature 设计

> 最后更新：`2026-04-08T00:19:40+08:00`
>
> 本文档只做一件事：把顶层 `design / contracts / formulas / derivations` 翻译成可实现的模块落点、运行时数据流、状态流转和任务切口。

## 背景与动机

顶层正式 SSOT 已经把主算法从旧的 `FIFO + Step2 + gate` 切换成了：

- `TCG=(p,m,s)` 三车可控
- `u/f` 可选边界预测
- merge branch + coordination branch 双分支控制
- `SafetyCertificate` 四条主安全函数
- A0-A3 先于大车流恢复

但如果 repo 内没有一套面向实现者的 feature/task 分发层，后续实现仍然很容易：

- 回到旧 baseline 的命名和拆法
- 在“当前 tick 无 merge 解”时默认等待
- 把 `u/f` 提前引入 A 层，模糊算法核心能力判断

因此，`active_gap_v1` feature 包的作用不是改写 SSOT，而是把它们翻译成一条**可执行、可重构、可回归**的实现路线。

## 设计方案

### 架构变更

- 新增 `docs/features/active_gap_v1/`，作为“正式 SSOT -> 实现 task”的中间层。
- 不改动 `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` 的 SSOT 地位。
- 推荐实现落点固定为：`src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/`。
- 当前 feature 只围绕 `TCG` 三车可控、merge/coordination 两分支、A 层首版不带 `u/f` 展开。

### 新增模块 / 修改模块

| Task | 目标文件 | 责任 |
|------|----------|------|
| `T1` | `src/active_gap_v1/types.py`、`config.py`、`snapshot.py`、`tcg_selector.py` | 冻结共享枚举、dataclass、`ScenarioConfig` 默认值、`CoordinationSnapshot`、`TCG` 与最小目录骨架 |
| `T2` | `src/active_gap_v1/predictor.py`、`merge_target_planner.py` | `u/f` 预测、`fixed/flexible` 统一、merge target 搜索、排序与失败分类 |
| `T3` | `src/active_gap_v1/quintic.py`、`certificate.py` | 三车 quintic、动力学检查、`g_up/g_pm/g_ms/g_sf`、`SafetyCertificate` |
| `T4` | `src/active_gap_v1/executor.py`、`state_machine.py` | merge slice、coordination slice、`SAFE_WAIT`、`FAIL_SAFE_STOP`、状态流转 |
| `T5` | `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/README.md`、`common.py` | trace schema、summary schema、`planned/actual`、实验输出约定 |
| `T6` | `experiments/active_gap_v1/a_layer_micro_scenarios.py`、`regression_gate.py` | A0-A3、blocking gate、正反例回归与后续大车流恢复边界 |

### 数据流

1. `T1` 把顶层 SSOT 中已冻结的共享对象、参数和时离散映射到 `src/active_gap_v1/`。
2. `T1` 在单个 `CoordinationSnapshot` 上完成 active ego 选择和 `TCG` 识别，并明确 `u/f` 缺省为空的语义。
3. `T2` 基于 `TCG`、`fixed/flexible` 和邻车预测，枚举 `(x_m^*, t_m^*, v^*)`，计算 `Δ_open / Δ_coop / Δ_delay / ρ_min` 并做稳定排序。
4. `T3` 对 merge branch 的候选求三车 quintic、做动力学检查、构建 `SafetyCertificate`。
5. `T4` 先尝试 certified merge slice；若失败，则尝试 certified coordination slice；若仍失败，再进入 `SAFE_WAIT / FAIL_SAFE_STOP`。
6. `T5` 为主链输出 trace、summary 和 `planned/actual` 指标，保证 A 层能解释“为什么这一 tick 没 merge 但仍是有效推进”。
7. `T6` 用 A0-A3 做第一门禁，冻结布局、期望结果和回归断言，之后才允许恢复大车流与多 seed 扩展。

### 运行时状态流转

| 当前状态 | 触发条件 | 下一状态 | 负责 Task |
|----------|----------|----------|-----------|
| `APPROACHING` | ego 进入 control zone 并满足 planning 触发条件 | `PLANNING` | `T4` |
| `PLANNING` | 存在 certified merge slice 或 certified coordination slice | `COMMITTED` | `T4` |
| `PLANNING` | 当前 tick 无任何 certified slice，且仍可安全等待 | `PLANNING` | `T4` |
| `PLANNING` | 当前 tick 无任何 certified slice，且 ego 已逼近 `emergency_tail` | `FAIL_SAFE_STOP` | `T4` |
| `COMMITTED` | rollout 开始消费当前 slice | `EXECUTING` | `T4` |
| `EXECUTING` | ego 完成并入并通过 `post_merge_guard` | `POST_MERGE` | `T4` |
| `FAIL_SAFE_STOP` | 车辆完成最大制动停车并记录 abort | `ABORTED` | `T4` |

### 额外执行约束

- `T1` 必须明确：`u/f` 在 A 层首版可缺省，不得把它们实现成 `TCG` 的必填项。
- `T2` 必须写入 merge target 排序和失败分类的确定性规则，禁止无序遍历带来的不可复现。
- `T3` 必须把 `g_up/g_pm/g_ms/g_sf` 的启用条件、检查区间和最紧约束字段写成显式输出，而不是隐式内部日志。
- `T4` 必须把 coordination branch 作为主链硬要求，禁止在“当前 tick 没 merge 解”时直接默认等待。
- `T5` 必须区分 `merge slice` 与 `coordination slice`，并能解释 `Δ_open`、速度错配和最紧证书约束。
- `T6` 必须硬性冻结：A0-A3 首版只看 `p/m/s`，`u/f` 只进入后续边界应力测试。

### API 变更

- 当前仓库不引入 HTTP / RPC / SSE 接口。
- 进程内接口继续对齐 `docs/contracts.md`，按模块映射如下：
  - `build_coordination_snapshot()` -> `src/active_gap_v1/snapshot.py`
  - `identify_tcg()` -> `src/active_gap_v1/tcg_selector.py`
  - `enumerate_merge_targets()` -> `src/active_gap_v1/merge_target_planner.py`
  - `solve_tcg_quintics()` -> `src/active_gap_v1/quintic.py`
  - `build_safety_certificate()` -> `src/active_gap_v1/certificate.py`
  - `synthesize_coordination_slice()` -> `src/active_gap_v1/executor.py`
  - `commit_first_slice()` -> `src/active_gap_v1/executor.py`
  - `decide_execution()` -> `src/active_gap_v1/state_machine.py`
  - `rollout_step()` -> `src/active_gap_v1/executor.py`
  - `evaluate_experiment()` -> `src/active_gap_v1/metrics.py`

### 数据库变更（如有，完整 DDL）

- 无。当前主算法只做本地 Python 数值验证，不引入数据库。

## 影响范围

- 涉及的现有正式文档：`README.md`、`docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md`。
- 新增的实现落点：`src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/`。
- 对旧 baseline 的影响：`docs/features/first_wave_mvp/` 只保留 archive / 对照语义，不再被新实现消费。
- 不涉及 / 不做的事：`simple DP`、两层分层算法、上游换道、多 `active decision partition`、更大范围协同对象和全局联合优化。
- 不修改的过程层：`reference/ramp_inventory/`、`forum/`。

## 新增接口（归档时合并回 contracts.md）

```python
def build_coordination_snapshot(
    *,
    sim_time_s: float,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    locked_tcgs: dict[str, TCG],
    planner_tag: PlannerTag,
    anchor_mode: AnchorMode,
) -> CoordinationSnapshot: ...


def identify_tcg(
    *,
    snapshot: CoordinationSnapshot,
) -> TCG | None: ...


def enumerate_merge_targets(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> list[MergeTarget]: ...


def solve_tcg_quintics(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    target: MergeTarget,
) -> tuple[
    QuinticLongitudinalProfile,
    QuinticLongitudinalProfile,
    QuinticLongitudinalProfile,
]: ...


def build_safety_certificate(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    slice_kind: SliceKind,
    profiles: tuple[
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
    ],
    target: MergeTarget | None,
) -> SafetyCertificate: ...


def synthesize_coordination_slice(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
) -> RollingPlanSlice | None: ...


def commit_first_slice(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG,
    certificate: SafetyCertificate,
    profiles: tuple[
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
        QuinticLongitudinalProfile,
    ],
    target: MergeTarget | None,
    slice_kind: SliceKind,
) -> RollingPlanSlice: ...


def decide_execution(
    *,
    snapshot: CoordinationSnapshot,
    tcg: TCG | None,
    plan_slice: RollingPlanSlice | None,
    failure_reason: str | None,
) -> ExecutionDecision: ...


def rollout_step(
    *,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    active_slices: dict[str, RollingPlanSlice],
) -> dict[str, VehicleState]: ...
```

补充要求：

- `TCG` 识别必须稳定、可重复。
- `enumerate_merge_targets()` 的排序必须可重复，不依赖无序容器。
- `build_safety_certificate()` 只能消费既定 target / profiles，禁止顺手改 target。
- `synthesize_coordination_slice()` 必须输出“推进性”证据，而不是模糊的“暂时等待”。
- `rollout_step()` 只消费当前状态和 `RollingPlanSlice`，不重新回到 target 搜索层。
