<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T6: A 层微场景与回归门禁（A-Layer Micro-Scenarios and Regression Gate）

> 最后更新：`2026-04-08T16:00:00+08:00`

## 前置条件

- `T1_tcg_and_snapshot`、`T2_merge_target_planner`、`T3_tcg_quintic_and_certificate`、`T4_execution_and_state_machine`、`T5_metrics_and_trace` 已完成。
- 必读：`docs/design.md`（重点看 “A 层微场景”“验证层次”“当前 tick 算不出 merge 时怎么办”）。
- 必读：`docs/formulas.md`（重点看 `Δ_open`、coordination slice 推进条件、四条证书函数）。
- 必读：`docs/features/active_gap_v1/design.md` 与 `README.md`。

## 目标

把 `A0-A1`（首版）提升成第一门禁，`A2/A3` 降级为后续扩展，而不是附加实验。  
本 task 要把场景布局、期望结果、blocking gate、正反例测试和后续大车流恢复边界全部写成可执行回归入口。

## Targets

1. **A 层场景冻结**: `A0-A1` 首版冻结，`A2/A3` 保留为后续扩展。
2. **A 层首版只看 `p/m/s`**: `u/f` 明确不进入首版定义，只在后续边界应力测试中单独引入。
3. **blocking gate 可执行**: 回归入口可以直接给出 pass/fail，而不是只输出日志供人工判断。
4. **失败原因可定位**: 失败时能指出是 `TCG` 识别、merge target、证书、coordination branch 还是状态机问题。

## Acceptance Criteria

### Step 1: 冻结 A0-A1 场景定义（depends on Step 3 of T5）

- [ ] `A0-A1` 的初始布局、角色解释、预期结果和关键观察点都写清。`A2/A3` 保留为后续扩展方向，但不进入首版门禁。
- [ ] A 层首版明确只看 `p/m/s`，`u/f` 不进入首版定义。

### Step 2: 固定 blocking gate 与失败分类（depends on Step 1）

- [ ] `A0-A1` 每个场景都有明确 pass/fail 规则，而不是“看起来差不多”。
- [ ] 能区分 merge branch 成功、coordination branch 成功、等待成功、fail-safe 正确触发与假成功。
- [ ] 失败时能定位到具体指标或阶段，而不是只返回模糊异常。

### Step 3: 完成回归入口与正反例测试（depends on Step 2）

- [ ] `experiments/active_gap_v1/a_layer_micro_scenarios.py` 可直接运行 `A0-A1`。
- [ ] `experiments/active_gap_v1/regression_gate.py` 可直接消费 `T5` 产物做 blocking gate。
- [ ] `pytest tests/active_gap_v1/test_micro_scenarios_and_regression.py` 通过。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法 A 层验证与回归门禁目录
- `docs/design.md` — A0-A1 的首版验证地位与 A2/A3 扩展前置条件
  - `docs/formulas.md` — `Δ_open`、coordination slice 推进条件、主安全函数
  - `experiments/active_gap_v1/` — `T5` 产出的实验外壳与结果契约

### Docs:

**Formal Specs:**

- `docs/design.md`: A0-A1 先于大车流、A 层首版只看 `p/m/s`
- `docs/formulas.md`: `Δ_open` 与证书最小裕度解释

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: `WP-6` 的执行说明与风险
- `docs/features/active_gap_v1/design.md`: `T6` 在 feature 闭环中的位置

### Developer insights:

- **T6 是第一门禁**: 如果 A0-A1 过不了，就不应进入后续场景扩展。
- **A 层首版必须收缩**: 先只看 `p/m/s`，否则 `u/f` 会稀释对算法核心能力的判断。
- **A0 和 A1 不要分裂成两套布局**: 两者应共用同一三车基准布局，差别只在验证目标。
- **coordination branch 必须进门禁**: 当前 tick 没 merge 但 coordination 成功，是通过而不是失败。
- **A2/A3 降级为后续扩展**: A2 需要先定义 c-m 安全约束，A3 需要先补数值可达性论证。

### Editable Paths

- `experiments/active_gap_v1/a_layer_micro_scenarios.py` — A0-A1 首版运行入口
- `experiments/active_gap_v1/regression_gate.py` — blocking gate
- `tests/active_gap_v1/conftest.py` — A 层 fixture
- `tests/active_gap_v1/test_micro_scenarios_and_regression.py` — pass/fail 正反例

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **A 层首版只看 p/m/s**: 不要把 `u/f` 混进 A0-A1 首版定义。
- **coordination 也算成功路径**: 不能把“当前没 merge 但在造 gap”误记成失败。
- **门禁必须可执行**: 不接受“人工看图再判断”的模糊标准。

## Skills

### Open URL

用于核对正式文档中的 A0-A1 首版目标、`Δ_open` 解释和 fail-safe 口径。

### Code Exploration

用于检查 `a_layer_micro_scenarios.py`、`regression_gate.py` 与 `T5` 输出结构之间的对应关系。

### Parallel Subagent

仅在后续需要并行核对场景入口与回归夹具时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 冻结 A0-A1 场景（Step 1, depends on Phase 3 of T5）

- [ ] 1.1 写清 A0-A1 的布局、角色与期望结果，并记录 A2/A3 的扩展前置条件
- [ ] 1.2 固定 A 层首版只看 `p/m/s`

### Phase 2: 固定 blocking gate（Step 2, depends on Phase 1）

- [ ] 2.1 为每个场景写清 pass/fail 条件
- [ ] 2.2 写清 merge / coordination / safe_wait / fail-safe 的区分规则

### Phase 3: 实现回归入口与测试（Step 3, depends on Phase 2）

- [ ] 3.1 实现 A 层实验入口
- [ ] 3.2 实现 regression gate 与正反例测试

## 你负责的文件（白名单）

```text
experiments/active_gap_v1/a_layer_micro_scenarios.py
experiments/active_gap_v1/regression_gate.py
tests/active_gap_v1/conftest.py
tests/active_gap_v1/test_micro_scenarios_and_regression.py
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/types.py`、`config.py`、`snapshot.py`、`tcg_selector.py`（由 `T1` 负责）
- `src/active_gap_v1/predictor.py`、`merge_target_planner.py`（由 `T2` 负责）
- `src/active_gap_v1/quintic.py`、`certificate.py`（由 `T3` 负责）
- `src/active_gap_v1/executor.py`、`state_machine.py`（由 `T4` 负责）
- `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/README.md`、`common.py`（由 `T5` 负责）

## 依赖的现有代码（需要先读的文件）

- `src/active_gap_v1/metrics.py`
- `experiments/active_gap_v1/README.md`
- `experiments/active_gap_v1/common.py`
- `docs/design.md`
- `docs/formulas.md`

## 实现步骤

### 1. 冻结 A0-A1 布局（A2/A3 标注为后续扩展）

- `A0`：`p=11,m=9,s=5,v_0=16.7 m/s`（同速起步），验证主动造 gap 是否真的发生。
- `A1`：与 `A0` 同布局，验证 `fixed/flexible` 差异是否可解释。
- `A2`：后续扩展。需要先定义匝道后车 `c` 的等待期行为约束与 `c-m` 安全保证，再验证连续三车组 / 连续匝道车时状态残留。
- `A3`：后续扩展。需要先补完整的可达性数值论证，证明该布局确实不可行，再验证 fail-safe 触发。

### 2. 固定 blocking gate

- `A0`：必须出现正的 `Δ_open`，且至少存在 1 个 `slice_kind=coordination` 的 committed slice 或 `p/s` 的轨迹偏离自由运动预测（`Δ_coop > 0`），且最终能形成认证的主动造 gap 过程。
- `A1`：必须能直接比较 `fixed/flexible` 的 target 与结果差异。
- `A2/A3`：不进入首版 blocking gate，仅保留扩展准入条件记录。

### 3. 连接实验结果与回归入口

- `a_layer_micro_scenarios.py` 负责真实运行 `A0-A1`。
- `regression_gate.py` 只消费 `T5` 的产物和本 task 的 blocking gate，不回写主链逻辑。

### 4. 补回归测试夹具

- 在 `conftest.py` 中准备 A0-A1 fixture、正例和最小负例。
- 保证门禁测试不依赖大车流实验或 `u/f` 边界场景。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_micro_scenarios_and_regression.py` 通过。
- `A0-A1` 都有明确布局、预期结果和 blocking gate。
- `A0/A1` 能解释算法本体。
- `A2/A3` 的扩展前置条件已记录，不进入首版门禁。

### 组装验证（产出运行时依赖的 task，可选）

- `A0-A1` 的结果可直接回答：算法是否有效、哪一步不对齐、A1 的 `fixed/flexible` 差异是什么。
- `T6` 通过后，后续更大流量与多 seed 恢复门槛已经明确。

### 环境验证（涉及配置加载的 task，可选）

- A 层首版场景不要求 `u/f` 存在。
- 回归门禁不接受把 `u/f` 边界场景混入 A0-A1 首版。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| trace / summary schema | `T5` | 输出结构稳定、可消费 |
| 主链实现 | `T1-T4` | merge/coordination/wait/fail-safe 路径已稳定 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| A0-A1 blocking gate | 后续手动验收 / CI | 主算法是否过第一门禁可直接判断 |
| 场景 fixture 与回归断言 | 后续更大流量恢复前检查 | 失败原因清晰、可重复复现 |

### 不要做

- 不要在 `T6` 之前先恢复大车流门禁。
- 不要让 `u/f` 干扰 A 层首版对算法核心能力的判断。
- 不要把“coordination 成功但当前没 merge”误判成失败。
