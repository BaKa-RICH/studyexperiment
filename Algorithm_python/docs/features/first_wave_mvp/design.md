<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/feature-design.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 第一波 MVP Feature 设计

> 最后更新：`2026-04-05T19:13:53+08:00`

## 背景与动机

顶层正式 spec 已经把第一波 MVP 的边界、共享契约、公式和推导冻结到了“可进入实现”的粒度，但 repo 内还没有一套面向后续 agent 的 feature/task 分发层。这个 feature 包的作用不是改写 `docs/`，而是把既有正式文档翻译成一条可执行的实现顺序，确保后续实现不会把第二波能力混入第一波 MVP。

## 设计方案

### 架构变更（如有）

- 新增 `docs/features/first_wave_mvp/`，作为“正式 spec -> 实现 task”的中间层。
- 不改动 `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` 的 SSOT 地位。
- 推荐实现落点固定为：`src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/`。
- 第一波只围绕 `FIFO + fixed anchor`、`FIFO + flexible anchor`、共享 `acceptance gate`、统一 I/O、统一时离散/参数层与首轮 3 个实验门禁展开，不新增第二波算法入口。

### 新增模块 / 修改模块

| Task | 目标文件 | 责任 |
|------|----------|------|
| `T1` | `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py` | 冻结共享枚举、dataclass、`ScenarioConfig` 默认值和最小目录骨架 |
| `T2` | `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py` | 单 partition / 单 ego 选取、`PlanningSnapshot`、target-lane ordered objects、候选生成与排序 |
| `T3` | `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py` | 共享 `acceptance gate`、`GateResult`、`commit_candidate()`、字段锁定 |
| `T4` | `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py` | `rollout_step()`、状态迁移、等待分支、fail-safe / abort |
| `T5` | `src/first_wave_mvp/metrics.py`、`experiments/first_wave_mvp/*.py` | 三类实验入口、指标产出、summary 结构 |
| `T6` | `experiments/first_wave_mvp/regression_gate.py`、`tests/first_wave_mvp/test_validation_and_regression.py` | L1/L2/L3 验证矩阵、多 seed 门禁、回归断言 |
| `T7` | `src/first_wave_mvp/scenario_initializer.py`、`src/first_wave_mvp/experiment_runner.py`、`src/first_wave_mvp/metrics_collector.py`、`experiments/first_wave_mvp/*.py` | 最小纯 Python 数值执行器、seed 驱动实验运行与真实 `summary.json` 落盘 |
| `T7` | `src/first_wave_mvp/scenario_initializer.py`、`src/first_wave_mvp/experiment_runner.py`、`src/first_wave_mvp/metrics_collector.py`、`experiments/first_wave_mvp/*.py` | 最小纯 Python 数值执行器、seed 驱动实验运行与真实 `summary.json` 落盘 |

### 数据流

1. `T1` 把 `docs/contracts.md` 和 `docs/formulas.md` 中已冻结的共享对象、参数和时离散映射到代码骨架。
2. `T2` 在单个 `PlanningSnapshot` 上完成单 partition / 单 ramp CAV 选取、`X_fixed/X_flex` 枚举、FIFO gap 导出和 `(t_m, Δdelay, x_m)` 排序。
3. `T3` 按 `T2` 给出的有序候选列表逐个验收，输出 `GateResult`，若通过则生成 `CommittedPlan`；`Step 3` 绝不重排候选，也不改写候选语义字段。
4. `T4` 只消费 `CommittedPlan` 与当前世界状态，推进 `COMMITTED -> EXECUTING -> POST_MERGE`，并处理 `NO_FEASIBLE_PLAN`、wait、fail-safe、abort。
5. `T5` 跑轻负荷正确性、中高负荷竞争、CAV 渗透率 / 协同范围消融三类实验，输出 per-seed 结果和聚合 summary。
6. `T6` 对 `T1-T5` 的结果执行 L1/L2/L3 门禁，统一报告 `mean / worst-seed / p95`，并要求 all-seed 安全项全部通过。
7. `T7` 将 `T1-T4` 的算法闭环与 `T5/T6` 的实验/门禁结构接成真实时间推进式数值执行器，并写出 `outputs/<experiment_id>/summary.json`。
7. `T7` 将 `T1-T4` 的算法闭环与 `T5/T6` 的实验/门禁结构接成真实时间推进式数值执行器，并写出 `outputs/<experiment_id>/summary.json`。

### 运行时状态流转

| 当前状态 | 触发条件 | 下一状态 | 负责 Task |
|----------|----------|----------|-----------|
| `APPROACHING` | ego 进入 control zone 并满足 planning 触发条件 | `PLANNING` | `T4` |
| `PLANNING` | 某候选通过共享 gate 并完成 commit | `COMMITTED` | `T3` |
| `PLANNING` | 当前 tick `NO_FEASIBLE_PLAN` 且未进入 `emergency_tail` | `PLANNING` | `T4` |
| `PLANNING` | 当前 tick `NO_FEASIBLE_PLAN` 且 ego 已进入 `emergency_tail` | `FAIL_SAFE_STOP` | `T4` |
| `COMMITTED` | rollout 开始消费 `CommittedPlan` | `EXECUTING` | `T4` |
| `EXECUTING` | ego 完成并入并通过 `post_merge_guard` | `POST_MERGE` | `T4` |
| `FAIL_SAFE_STOP` | 车辆完成最大制动停车并记录 abort | `ABORTED` | `T4` |

### 额外执行约束

- `T2` 必须写入“候选枚举顺序与 `candidate_id` 生成确定性稳定”的要求，禁止使用随机 UUID 破坏回归一致性。
- `T3` 必须把 `PLANNING -> COMMITTED` 的合法转移、非法转移处理和 `COMMITTED` 字段锁定规则写成显式表格或断言，不得让 gate 变成 hidden replanner。
- `T4` 必须明确 `NO_FEASIBLE_PLAN`、wait、fail-safe、abort 的触发条件、状态副作用和原因码，不得静默吞掉失败分支。
- `T5/T6` 必须统一多 seed 报告口径：至少输出 `mean`、`worst-seed`、`p95`，并以 all-seed 安全项通过为硬门禁。
- `T7` 必须使用纯 Python、`0.1s` tick 和确定性 seed RNG；不得引入 SUMO/CARLA/TraCI、第二波算法或多 partition。
- `T7` 必须让同 seed 两次运行结果一致、不同 seed 至少在初始 `world_state` 或最终 `summary.json` 上出现差异。
- `T7` 写出的 `summary.json` 需要保持 `snake_case` 键名，并与 `T5/T6` 的 `PerSeedResult` / `ExperimentResultSummary` / stats view 契约兼容。
- `T7` 必须使用纯 Python、`0.1s` tick 和确定性 seed RNG；不得引入 SUMO/CARLA/TraCI、第二波算法或多 partition。
- `T7` 必须让同 seed 两次运行结果一致、不同 seed 至少在初始 `world_state` 或最终 `summary.json` 上出现差异。
- `T7` 写出的 `summary.json` 需要保持 `snake_case` 键名，并与 `T5/T6` 的 `PerSeedResult` / `ExperimentResultSummary` / stats view 契约兼容。

### API 变更

- 第一波不引入 HTTP / RPC / SSE 接口。
- 进程内接口继续对齐 `docs/contracts.md`，按模块映射如下：
  - `build_snapshot()` -> `src/first_wave_mvp/snapshot.py`
  - `generate_candidates()` -> `src/first_wave_mvp/step2_fifo.py`
  - `accept_candidate()` -> `src/first_wave_mvp/gate.py`
  - `commit_candidate()` -> `src/first_wave_mvp/commit.py`
  - `rollout_step()` -> `src/first_wave_mvp/rollout.py`
  - `evaluate_experiment()` -> `src/first_wave_mvp/metrics.py`

### 数据库变更（如有，完整 DDL）

- 无。第一波只做本地 Python 数值验证，不引入数据库。

## 影响范围

- 涉及的现有模块：`README.md`、`docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md`。
- 新增的实现落点：`src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/`。
- 追加的执行层实现落点：`src/first_wave_mvp/scenario_initializer.py`、`src/first_wave_mvp/experiment_runner.py`、`src/first_wave_mvp/metrics_collector.py`。
- 追加的执行层实现落点：`src/first_wave_mvp/scenario_initializer.py`、`src/first_wave_mvp/experiment_runner.py`、`src/first_wave_mvp/metrics_collector.py`。
- 不涉及 / 不做的事：`simple DP`、两层分层算法、上游换道、多 `active decision partition`、更大范围协同对象和全局联合优化。
- 不修改的过程层：`reference/ramp_inventory/`、`forum/`、`.cursor/plans/...`。

## 新增接口（归档时合并回 contracts.md）

```python
def build_snapshot(
    *,
    sim_time_s: float,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    committed_plans: dict[str, CommittedPlan],
    policy_tag: PolicyTag,
) -> PlanningSnapshot: ...


def generate_candidates(
    *,
    snapshot: PlanningSnapshot,
) -> list[CandidatePlan]: ...


def accept_candidate(
    *,
    snapshot: PlanningSnapshot,
    candidate: CandidatePlan,
) -> GateResult: ...


def commit_candidate(
    *,
    snapshot: PlanningSnapshot,
    candidate: CandidatePlan,
    gate_result: GateResult,
) -> CommittedPlan: ...


def rollout_step(
    *,
    scenario: ScenarioConfig,
    world_state: dict[str, VehicleState],
    committed_plans: dict[str, CommittedPlan],
) -> dict[str, VehicleState]: ...


def evaluate_experiment(
    *,
    experiment_id: str,
    results: list[ExperimentResultSummary],
) -> ExperimentResultSummary: ...
```

补充要求：

- `candidate_id` 必须可重复生成，建议基于 `snapshot_id + policy_tag + x_m + gap_ref` 组装。
- `accept_candidate()` 只返回 `GateResult`，不得返回“修补后的 candidate”。
- `rollout_step()` 只消费当前状态和 `CommittedPlan`，不直接介入 `Step 2/Step 3` 逻辑。
