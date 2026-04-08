<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T6: 验证矩阵与回归门禁 (Validation Matrix and Regression Gate)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- `T1_shared_types_and_config`、`T2_snapshot_and_step2`、`T3_acceptance_gate_and_commit`、`T4_rollout_and_state_machine`、`T5_experiments_and_metrics` 已完成。
- 必读：`docs/design.md`（重点看 “测试策略”“8.1/8.2/8.3 实验门禁”“8.4 Seed 与统计口径”）。
- 必读：`docs/formulas.md`（重点看时离散和默认参数）。
- 必读：`docs/features/first_wave_mvp/design.md` 与 `README.md`。

## 目标

把第一波 MVP 的 L1/L2/L3 验证矩阵、多 seed 聚合和通过门禁写成可执行回归入口，确保后续实现不是“能跑就算过”，而是必须满足正式文档定义的安全和性能阈值。

## Targets

1. **验证矩阵完整**: L1/L2/L3 三层验证都被映射成可执行回归入口，而不是停留在说明文字。
2. **多 seed 门禁清晰**: `N_seed >= 3`、`mean / worst-seed / p95` 与 all-seed 安全通过规则可自动判断。
3. **失败原因可定位**: 回归失败时能指出实验类型、指标项和失败 seed，而不是只返回模糊异常。

## Acceptance Criteria

### Step 1: 固定 L1/L2/L3 验证矩阵（no dependencies — start here）

- [ ] L1、L2、L3 的覆盖范围和输入来源被明确写入回归入口。
- [ ] L2 明确覆盖 `snapshot -> Step 2 -> Step 3 -> COMMIT/WAIT/FAIL-SAFE -> rollout` 闭环。
- [ ] L3 明确覆盖轻负荷正确性、竞争实验和消融实验。

### Step 2: 实现多 seed 门禁逻辑（depends on Step 1）

- [ ] `N_seed >= 3` 被显式检查。
- [ ] 同时输出 `mean`、`worst-seed`、`p95` 三类聚合口径。
- [ ] 安全项要求 all-seed 通过，性能项按正式文档阈值判断。

### Step 3: 完成回归夹具与正反例验证（depends on Step 2）

- [ ] `regression_gate.py` 只消费 `T5` 产物，不重写实验脚本。
- [ ] `test_validation_and_regression.py` 覆盖 pass/fail 正反例。
- [ ] `pytest tests/first_wave_mvp/test_validation_and_regression.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波验证层与回归门禁目录
  - `docs/design.md` — L1/L2/L3 测试策略和实验门禁
  - `docs/formulas.md` — 时离散和默认参数
  - `experiments/first_wave_mvp/` — `T5` 产出的实验入口和 summary

### Docs:

**Formal Specs:**

- `docs/design.md`: 8.1/8.2/8.3/8.4 的通过条件与 seed 统计口径
- `docs/formulas.md`: 时间步长和默认参数边界

**Feature Package:**

- `docs/features/first_wave_mvp/README.md`: `WP-6` 的执行说明与风险
- `docs/features/first_wave_mvp/design.md`: `T6` 在 feature 闭环中的位置

### Developer insights:

- **验证不是兜底脚本**: `T6` 是正式门禁，不是“最后看一眼有没有崩”。
- **多 seed 是硬约束**: 单 seed 成功不能代表第一波通过。
- **all-seed 安全优先**: 安全项必须每个 seed 都过，不能被均值掩盖。
- **回归只消费结果**: `T6` 不能回头改 `T5` 实验脚本或 `T1-T4` 核心逻辑。
- **第二波明确排除**: `simple DP`、两层分层、上游换道、多 partition 不进入回归集合。

### Editable Paths

- `experiments/first_wave_mvp/regression_gate.py` — 回归门禁入口
- `tests/first_wave_mvp/conftest.py` — 多 seed fixture 和 summary fixture
- `tests/first_wave_mvp/test_validation_and_regression.py` — pass/fail 正反例测试

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **回归只读结果**: `T6` 只消费 `T5` 产物，不回写实验脚本或核心逻辑。
- **安全先于性能**: all-seed 安全门禁必须先判定，再看性能阈值。
- **第一波回归限定**: 禁止把第二波策略或多 partition 场景纳入门禁。

## Skills

### Open URL

用于核对正式文档中的门禁阈值、多 seed 统计口径和 L1/L2/L3 范围。

### Code Exploration

用于检查 `regression_gate.py`、测试夹具与 `T5` 输出结构之间的对应关系。

### Parallel Subagent

仅在后续需要并行核对多 seed fixture 与正反例门禁时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 固定验证矩阵（Step 1, depends on Phase 3 of T5）

- [ ] 1.1 将 L1/L2/L3 映射到可执行回归入口
- [ ] 1.2 明确三类实验与闭环路径的覆盖范围

### Phase 2: 落多 seed 门禁（Step 2, depends on Phase 1）

- [ ] 2.1 实现 `N_seed >= 3`、`mean / worst-seed / p95` 聚合逻辑
- [ ] 2.2 实现 all-seed 安全门禁和性能阈值判断

### Phase 3: 完成夹具与正反例（Step 3, depends on Phase 2）

- [ ] 3.1 准备多 seed fixture、summary fixture 和最小负例
- [ ] 3.2 为回归门禁的 pass/fail 路径补测试

## 你负责的文件（白名单）

```text
experiments/first_wave_mvp/regression_gate.py
tests/first_wave_mvp/conftest.py
tests/first_wave_mvp/test_validation_and_regression.py
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/types.py`、`src/first_wave_mvp/config.py`（由 `T1` 负责）
- `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py`（由 `T4` 负责）
- `src/first_wave_mvp/metrics.py`、`experiments/first_wave_mvp/light_load_correctness.py`、`experiments/first_wave_mvp/medium_high_load_competition.py`、`experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py`（由 `T5` 负责）

## 依赖的现有代码（需要先读的文件）

- `src/first_wave_mvp/metrics.py`
- `experiments/first_wave_mvp/README.md`
- `experiments/first_wave_mvp/light_load_correctness.py`
- `experiments/first_wave_mvp/medium_high_load_competition.py`
- `experiments/first_wave_mvp/cav_penetration_and_scope_ablation.py`
- `docs/design.md`
- `docs/formulas.md`

## 实现步骤

### 1. 固定 L1/L2/L3 验证矩阵

- `L1`：公式与参数正确性。
- `L2`：`snapshot -> Step 2 -> Step 3 -> COMMIT/WAIT/FAIL-SAFE -> rollout` 闭环正确性。
- `L3`：三类实验门禁与回归。

### 2. 实现多 seed 门禁逻辑

- `N_seed >= 3`。
- 统一报告 `mean`、`worst-seed`、`p95`。
- 安全项（`collision_count`、`safety_violation_count` 等）必须 all-seed 通过；性能项按正式文档阈值判断。

### 3. 连接实验结果与回归入口

- `regression_gate.py` 只负责读取 `T5` 产物并做 pass/fail 分类。
- `test_validation_and_regression.py` 覆盖正例与反例，验证门禁能正确拦截超阈值结果。

### 4. 补回归测试夹具

- 在 `conftest.py` 中准备多 seed fixture、summary fixture 和最小负例。
- 保证门禁测试不依赖第二波算法或额外实验脚本。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_validation_and_regression.py` 通过。
- `regression_gate.py` 能对轻负荷、竞争、消融三类实验给出明确 pass/fail 结论。
- all-seed 安全门禁、`mean`、`worst-seed`、`p95` 三种聚合口径均被覆盖。

### 组装验证（产出运行时依赖的 task，可选）

- `T1-T5` 产物在不改动实验脚本的情况下可直接进入回归门禁。
- 回归失败时能输出具体失败实验、失败指标和失败 seed，而不是返回模糊错误。

### 环境验证（涉及配置加载的 task，可选）

- 多 seed 配置只依赖 `T5` 的实验入口与正式 spec 已冻结参数。
- 回归门禁不接受第二波算法标签、不接受多 partition 场景。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 三类实验入口与 summary | `T5` | 结果格式稳定，已能输出 per-seed 与聚合指标 |
| 闭环核心实现 | `T1-T4` | L1/L2 所需对象与日志已稳定 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `regression_gate.py` | 后续 CI / 手动验收 | 第一波 MVP 是否通过门禁可自动判断 |
| 回归测试夹具与断言 | 后续实现维护 | 失败原因清晰、可重复复现 |

### 不要做

- 不要重写 `T5` 的实验脚本或 `T1-T4` 的核心逻辑。
- 不要把 `simple DP`、两层分层、上游换道、多 partition、全局协同纳入回归集合。
- 不要把“单 seed 偶然成功”当成通过依据。
