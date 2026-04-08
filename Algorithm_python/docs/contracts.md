<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/contracts.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 主动造 Gap 接口契约

> **所有开发 agent 必读此文档。** 本文档是跨模块共享类型、模块边界、字段锁定规则与运行时协议的权威定义。
>
> 最后更新：`2026-04-08T18:45:00+08:00`
>
> 当前契约已经升级为：`TCG` 三车协同组、`p/m/s` 三车受控、`u/f` 可选边界预测、以及 `merge slice / coordination slice / safe_wait / fail_safe_stop` 四分支执行语义。

---

## 1. 项目基本信息

- 语言：Python `3.11+`
- 当前实现形态：单机本地数值验证，不提供 HTTP / SSE API
- 契约版本：`active-gap-v2`
- 命名约定：所有带单位字段统一显式带后缀，如 `_s`、`_m`、`_mps`、`_mps2`
- 顶层 SSOT 分工：
  - `docs/design.md`：系统主线、运行时闭环、状态机与验证策略
  - `docs/contracts.md`：共享类型、锁定规则、模块协议
  - `docs/formulas.md`：状态、目标、轨迹、证书的公式定义
  - `docs/derivations.md`：关键结构与公式的推导理由

## 2. 共享枚举类型

```python
from enum import StrEnum


class PlannerTag(StrEnum):
    ACTIVE_GAP = "active_gap"
    NO_CONTROL = "no_control"


class AnchorMode(StrEnum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"


class ExecutionState(StrEnum):
    APPROACHING = "approaching"
    PLANNING = "planning"
    COMMITTED = "committed"
    EXECUTING = "executing"
    POST_MERGE = "post_merge"
    FAIL_SAFE_STOP = "fail_safe_stop"
    ABORTED = "aborted"


class SliceKind(StrEnum):
    MERGE = "merge"
    COORDINATION = "coordination"


class ExecutionDecisionTag(StrEnum):
    COMMIT_MERGE_SLICE = "commit_merge_slice"
    COMMIT_COORDINATION_SLICE = "commit_coordination_slice"
    SAFE_WAIT = "safe_wait"
    FAIL_SAFE_STOP = "fail_safe_stop"


class CertificateFailureKind(StrEnum):
    REACHABILITY = "reachability"
    DYNAMICS = "dynamics"
    SAFETY_UP = "safety_up"
    SAFETY_PM = "safety_pm"
    SAFETY_MS = "safety_ms"
    SAFETY_SF = "safety_sf"
    GROUP_INVALID = "group_invalid"
```

约束说明：

- `PlannerTag.NO_CONTROL` 只作为实验参考下界，不进入当前主算法规划链
- `AnchorMode` 表示 `fixed/flexible` 的 admissible set，不表示两套不同控制框架
- `ExecutionDecisionTag` 描述当前 tick 的执行输出，不等于执行状态
- `NO_FEASIBLE_CERTIFIED_SLICE` 不是 `CertificateFailureKind`，而是本 tick 内无可认证控制片段的 planner 结果

## 3. 核心数据模型

```python
from dataclasses import dataclass, field


@dataclass(slots=True)
class ScenarioConfig:
    scenario_id: str
    lane_width_m: float = 3.2
    control_zone_length_m: float = 600.0
    ramp_approach_subzone_m: tuple[int, int] = (0, 50)
    legal_merge_zone_m: tuple[int, int] = (50, 290)
    emergency_tail_m: tuple[int, int] = (290, 300)
    planning_tick_s: float = 0.1
    rollout_tick_s: float = 0.1
    certificate_sampling_dt_s: float = 0.1
    post_merge_guard_s: float = 1.0
    epsilon_t_s: float = 0.05
    a_max_mps2: float = 2.6
    b_safe_mps2: float = 4.5
    fail_safe_brake_mps2: float = 4.5
    comfortable_brake_mps2: float = 2.0
    min_gap_m: float = 2.5
    time_headway_s: float = 1.0
    h_pr_s: float = 1.5
    h_rf_s: float = 2.0
    fixed_anchor_m: int = 170
    lane_change_duration_s: float = 3.0
    mainline_vmax_mps: float = 25.0
    ramp_vmax_mps: float = 16.7
    vehicle_length_m: float = 5.0


@dataclass(slots=True)
class VehicleState:
    veh_id: str
    stream: str
    lane_id: str
    x_pos_m: float
    speed_mps: float
    accel_mps2: float
    length_m: float
    is_cav: bool
    execution_state: ExecutionState


@dataclass(slots=True)
class TCG:
    snapshot_id: str
    p_id: str
    m_id: str
    s_id: str
    u_id: str | None
    f_id: str | None
    anchor_mode: AnchorMode
    sequence_relation: str


@dataclass(slots=True)
class CoordinationSnapshot:
    snapshot_id: str
    sim_time_s: float
    planner_tag: PlannerTag
    anchor_mode: AnchorMode
    ego_id: str
    ego_state: VehicleState
    control_zone_states: dict[str, VehicleState]
    locked_tcgs: dict[str, TCG]
    scenario: ScenarioConfig


@dataclass(slots=True)
class MergeTarget:
    snapshot_id: str
    m_id: str
    x_m_star_m: float
    t_m_star_s: float
    horizon_s: float
    v_star_mps: float
    x_p_star_m: float
    x_s_star_m: float
    delta_open_m: float
    delta_coop_m: float
    delta_delay_s: float
    rho_min_m: float
    ranking_key: tuple[float, float, float, float, float]


@dataclass(slots=True)
class QuinticBoundaryState:
    x_m: float
    v_mps: float
    a_mps2: float


@dataclass(slots=True)
class QuinticLongitudinalProfile:
    vehicle_id: str
    t0_s: float
    horizon_s: float
    coefficients: tuple[float, float, float, float, float, float]
    start_state: QuinticBoundaryState
    terminal_state: QuinticBoundaryState


@dataclass(slots=True)
class SafetyCertificate:
    snapshot_id: str
    m_id: str
    tcg_ids: tuple[str | None, str, str, str, str | None]
    slice_kind: SliceKind
    valid_from_s: float
    valid_until_s: float
    min_margin_up_m: float | None
    min_margin_pm_m: float
    min_margin_ms_m: float
    min_margin_sf_m: float | None
    binding_constraint: str
    failure_kind: CertificateFailureKind | None
    checked_time_candidates_s: tuple[float, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class RollingPlanSlice:
    snapshot_id: str
    m_id: str
    slice_kind: SliceKind
    tcg: TCG
    merge_target: MergeTarget | None
    certificate: SafetyCertificate
    exec_start_s: float
    exec_end_s: float
    profile_p: QuinticLongitudinalProfile
    profile_m: QuinticLongitudinalProfile
    profile_s: QuinticLongitudinalProfile
    delta_open_before_m: float | None = None
    delta_open_after_m: float | None = None
    speed_alignment_before_mps: float | None = None
    speed_alignment_after_mps: float | None = None


@dataclass(slots=True)
class ExecutionDecision:
    decision_tag: ExecutionDecisionTag
    state_after: ExecutionState
    reason: str
    tcg_locked: bool
    target_locked: bool
    plan_slice: RollingPlanSlice | None = None


@dataclass(slots=True)
class ExperimentResultSummary:
    experiment_id: str
    planner_tag: PlannerTag
    anchor_mode: AnchorMode | None
    seed_count: int
    completion_rate: float
    abort_rate: float
    collision_count: int
    safety_violation_count: int
    avg_ramp_delay_s: float
    throughput_vph: float
    delta_open_positive_rate: float | None = None
    planned_actual_time_error_p95_s: float | None = None
    planned_actual_position_error_p95_m: float | None = None
```

字段语义补充：

- `RollingPlanSlice.delta_open_before_m / delta_open_after_m`
  - 当前版本中，表示 coordination 阶段的**聚合 virtual gap 误差**
  - 具体实现口径为 `e_pm^{virt} + e_ms^{virt}`
  - 它不再表示“原始 `p-s` 总 gap 距离差”
- `RollingPlanSlice.speed_alignment_before_mps / speed_alignment_after_mps`
  - 当前版本中，表示 pairwise 相对速度偏差总和
  - 具体实现口径为 `|v_p-v_m| + |v_m-v_s|`
- per-tick trace 若需要解释 coordination 收敛过程，除上述聚合字段外，建议额外记录：
  - `virt_e_pm`
  - `virt_e_ms`
  - `pairwise_gap_ready`
  - `relative_speed_ready`

## 4. Producer / Consumer 约定

- `ScenarioConfig`
  - Producer：场景定义层
  - Consumer：快照构造、target 搜索、证书检查、rollout、实验评估
- `VehicleState`
  - Producer：状态更新层 / rollout
  - Consumer：快照构造、TCG 识别、轨迹求解、指标统计
- `CoordinationSnapshot`
  - Producer：`build_coordination_snapshot()`
  - Consumer：`identify_tcg()`、`enumerate_merge_targets()`
- `TCG`
  - Producer：`identify_tcg()`
  - Consumer：target 搜索、轨迹、证书、rollout
- `MergeTarget`
  - Producer：`enumerate_merge_targets()`
  - Consumer：merge 轨迹求解、证书构建
- `QuinticLongitudinalProfile`
  - Producer：`solve_tcg_quintics()`
  - Consumer：证书构建、slice 提交、rollout
- `SafetyCertificate`
  - Producer：`build_safety_certificate()`
  - Consumer：`commit_first_slice()`、实验日志、trace
- `RollingPlanSlice`
  - Producer：`commit_first_slice()`
  - Consumer：`rollout_step()`、下一个 tick 的锁定上下文
- `ExperimentResultSummary`
  - Producer：`evaluate_experiment()`
  - Consumer：门禁判断、报告生成、对比实验

## 5. 字段锁定规则

### 5.1 `COMMITTED` 锁定内容

进入 `COMMITTED` 后，必须锁定以下语义字段：

- `TCG.p_id`
- `TCG.m_id`
- `TCG.s_id`
- `TCG.u_id`
- `TCG.f_id`
- `TCG.anchor_mode`
- `TCG.sequence_relation`

进入 `COMMITTED` 后，允许每 tick 刷新但不视为语义重决策的对象：

- `MergeTarget`
- 三车 `QuinticLongitudinalProfile`
- `SafetyCertificate`
- `RollingPlanSlice`

### 5.2 `EXECUTING` 锁定内容

一旦横向动作开始，必须额外锁定：

- 当前 `MergeTarget`
- 当前 `RollingPlanSlice` 家族
- 当前 `SafetyCertificate` 所对应的 `TCG / target / slice_kind` 解释

进入 `EXECUTING` 后不允许：

- re-TCG
- post-lc retarget
- 改写 merge order

### 5.3 允许的应急 continuation

若 `EXECUTING` 期间常规重算失败，只允许：

- 在同一 `TCG` 下
- 生成同一 target 解释下的应急 continuation

不允许把这类 continuation 伪装成新的语义决策。

## 6. 关键设计原则

1. **先锁 TCG，再滚动刷新 target**
   `COMMITTED` 锁三车协同组，`EXECUTING` 再锁 target。
2. **证书是主对象，不是被动 gate**
   `SafetyCertificate` 必须能表达最紧约束与失败原因，而不是只有 pass/fail。
3. **当前 tick 没 merge 解时，优先找 coordination slice**
   不能直接默认等待。
4. **所有时间与距离字段显式带单位**
   禁止在契约里出现无单位数字。
5. **对外序列化统一使用 snake_case**
   便于 JSON / CSV / pandas / pytest fixture 复用。

## 7. Planning Cycle 协议

每个 planning tick 必须遵守同一顺序：

1. `build_coordination_snapshot()`
2. `identify_tcg()`
3. `enumerate_merge_targets()`
4. 若存在 certified merge slice，则 `commit_first_slice()`
5. 否则尝试 `synthesize_coordination_slice()`
   注意：`synthesize_coordination_slice()` 内部负责生成 coordination 分支的短时轨迹、安全证书和推进性判据。如果返回非 `None`，说明已找到 certified coordination slice。此时外层仍应调用 `commit_first_slice()` 来正式提交——`commit_first_slice()` 可以从返回的 `RollingPlanSlice` 中提取 `profiles`、`certificate`、`slice_kind` 等字段作为输入参数。这保证了 merge 分支和 coordination 分支共用同一个提交入口。
6. 若存在 certified coordination slice，则 `commit_first_slice()`
7. 否则输出 `SAFE_WAIT` 或 `FAIL_SAFE_STOP`
8. `rollout_step()`

这里最重要的协议约束有三条：

- 不允许在 `build_safety_certificate()` 内顺手改写 `MergeTarget`
- 不允许在 `rollout_step()` 内隐藏 re-TCG
- 不允许把 `NO_FEASIBLE_CERTIFIED_SLICE` 混进 `CertificateFailureKind`

## 8. `NO_FEASIBLE_CERTIFIED_SLICE` 协议

- 它不是 `CertificateFailureKind`
- 它表示“本 tick 内没有通过 merge branch + coordination branch 认证的控制片段”
- 在 `PLANNING` 阶段，它优先对应 `ExecutionDecisionTag.SAFE_WAIT`
- 若车辆已进入 `emergency_tail` 或剩余距离不足，则对应 `ExecutionDecisionTag.FAIL_SAFE_STOP`

**实现约束**：`NO_FEASIBLE_CERTIFIED_SLICE` 绝不能作为 `CertificateFailureKind` 的枚举值出现。它是 planner 层面的结果标志，不是证书失败分类。T3（certificate.py 的 owner）和 T4（状态机 owner）在实现时必须维护这一语义边界。

## 9. 序列化协议

- 对外落盘统一使用 snake_case
- 浮点时间统一使用秒，推荐保留到 `1e-3`
- `ranking_key` 固定定义为 `(t_m_star_s, delta_coop_m, delta_delay_s, -rho_min_m, x_m_star_m)`
- `PlannerTag.NO_CONTROL` 的实验结果可以进入 `ExperimentResultSummary`，但不能生成 `TCG / MergeTarget / SafetyCertificate`

## 10. 运行时装配矩阵

| 阶段 | Producer | 传递对象 | Consumer | 说明 |
|---|---|---|---|---|
| 场景初始化 | 场景定义层 | `ScenarioConfig` | 快照构造、target 搜索、证书、rollout | 提供几何、时间离散和参数层默认值 |
| 状态更新 | rollout / 状态更新层 | `dict[str, VehicleState]` | `build_coordination_snapshot()` | 提供控制区内观测 |
| 快照构造 | `build_coordination_snapshot()` | `CoordinationSnapshot` | `identify_tcg()`、`enumerate_merge_targets()` | 冻结本 tick 的世界 |
| TCG 识别 | `identify_tcg()` | `TCG` | target 搜索、轨迹、证书、rollout | 锁定局部三车协同组 |
| merge 搜索 | `enumerate_merge_targets()` | `list[MergeTarget]` | merge 轨迹求解、证书构建 | 按字典序排序 |
| merge 轨迹 | `solve_tcg_quintics()` | 三车 `QuinticLongitudinalProfile` | merge 证书构建、slice 提交 | 生成 `p/m/s` 轨迹 |
| 协调片段 | `synthesize_coordination_slice()` | `RollingPlanSlice` | rollout、trace | 当前不能 merge 时的短时造 gap 控制 |
| 安全证书 | `build_safety_certificate()` | `SafetyCertificate` | `commit_first_slice()`、trace | 解释最紧约束 |
| slice 提交 | `commit_first_slice()` | `RollingPlanSlice` | `rollout_step()`、下个 tick | 当前 tick 可执行时间片 |
| 执行推进 | `rollout_step()` | 新 `VehicleState` 集合 | 下一个 planning tick | 推进纵向和横向执行 |
| 实验汇总 | `evaluate_experiment()` | `ExperimentResultSummary` | 门禁判断、报告生成 | 对齐 A 层与后续大车流实验 |

## 11. 模块接口签名

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


def evaluate_experiment(
    *,
    experiment_id: str,
    results: list[ExperimentResultSummary],
) -> ExperimentResultSummary: ...
```

接口级要求：

- `enumerate_merge_targets()` 必须在返回前完成字典序排序
- `build_safety_certificate()` 必须复用同一个 `snapshot.snapshot_id`
- `commit_first_slice()` 只能消费通过认证的 `SafetyCertificate`
- `rollout_step()` 不允许直接读取旧 `ramp` 的 TraCI 运行时对象
