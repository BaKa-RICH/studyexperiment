<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T1: TCG、共享类型与 Snapshot 骨架 (TCG Types, Snapshot, and Skeleton)

> 最后更新：`2026-04-08T16:00:00+08:00`

## 前置条件

- 无前置 task。
- 必读：`README.md`（项目当前主线、阅读顺序、archive 关系）。
- 必读：`docs/design.md`（重点看“对象定义”“当前 tick 算不出 merge 时怎么办”“状态机与 fail-safe”）。
- 必读：`docs/contracts.md`（重点看共享枚举、`TCG`、`CoordinationSnapshot`、字段锁定规则和模块接口签名）。
- 必读：`docs/formulas.md`（重点看几何、时离散、`u/f` 外生预测和默认参数）。
- 必读：`docs/features/active_gap_v1/design.md`。

## 目标

在当前空目录仓库中创建 `active_gap_v1` 的最小可引用骨架，把共享枚举、dataclass、`ScenarioConfig` 默认值、`CoordinationSnapshot`、`TCG` 识别入口和 `u/f` 缺省语义一次性冻结到代码层，不引入任何 merge target、quintic、certificate 或 execution 分支逻辑。

## Targets

1. **目录骨架可落地**: 创建 `src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/` 的最小骨架，后续 task 白名单可以直接落位。
2. **共享契约已落代码**: `types.py` / `config.py` 承接当前主算法的共享枚举、dataclass、默认参数与统一时离散，且不预埋第二波字段。
3. **TCG 与 snapshot 入口稳定**: `build_coordination_snapshot()` 与 `identify_tcg()` 能在 A0/A1 首版场景下稳定工作，并允许 `u/f` 缺省为空。
4. **下游可直接消费**: `T2-T6` 无需回写 `T1` 文件即可 import 共享对象并开始实现。

## Acceptance Criteria

### Step 1: 建立最小目录骨架（no dependencies — start here）

- [ ] 已创建 `src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/` 的最小落点。
- [ ] 第一波必要占位文件已存在，后续 task 的白名单文件都有可挂载的目录。
- [ ] 没有预创建第二波目录或多余扩展模块。

### Step 2: 固化共享类型与参数（depends on Step 1）

- [ ] `types.py` 包含 `PlannerTag`、`AnchorMode`、`ExecutionState`、`SliceKind`、`ExecutionDecisionTag`、`CertificateFailureKind` 以及 `ScenarioConfig`、`VehicleState`、`TCG`、`CoordinationSnapshot` 等 dataclass，字段与 `docs/contracts.md` 一致。
- [ ] `config.py` 中的默认参数、几何边界和时离散与 `docs/formulas.md` / `docs/contracts.md` 一致。
- [ ] 未出现 `simple DP`、CBF/QP、多 partition 等第二波字段。

### Step 3: 实现 snapshot 与 TCG 识别入口（depends on Step 2）

- [ ] `build_coordination_snapshot()` 会冻结当前 tick 的时间、车辆状态、已锁定 `TCG` 和 `AnchorMode`。
- [ ] `identify_tcg()` 只负责选择 active ego、识别 `p/m/s`，并把 `u/f` 作为可选边界输出，不会把 `u/f` 设为必填。
- [ ] A0/A1 首版场景下，即使没有 `u/f`，也能正常生成 `TCG`。

### Step 4: 完成基础验证与可消费性（depends on Step 3）

- [ ] `pytest tests/active_gap_v1/test_tcg_and_snapshot.py` 通过。
- [ ] 共享对象可以被后续 task 直接 import，不产生循环依赖。
- [ ] 同一输入至少重复运行 3 次，`TCG` 识别结果稳定一致。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 当前主算法的正式 spec 与实现目录
  - `docs/design.md` — `TCG`、状态机、无 merge 解时的执行优先级
  - `docs/contracts.md` — 共享枚举、dataclass、模块接口和字段锁定规则
  - `docs/formulas.md` — 几何、时离散、`u/f` 外生预测、默认参数
  - `docs/features/active_gap_v1/design.md` — 模块落点和任务切口

### Docs:

**Formal Specs:**

- `docs/design.md`: 当前主线、`TCG` 对象语义、coordination branch 优先级
- `docs/contracts.md`: `TCG`、`CoordinationSnapshot`、模块接口和字段锁定
- `docs/formulas.md`: 时间步长、默认参数、边界车预测形式

**Feature Package:**

- `docs/features/active_gap_v1/README.md`: 执行顺序、工作包和风险
- `docs/features/active_gap_v1/design.md`: 模块映射和运行时数据流

### Developer insights:

- **空仓起步**: 当前 `src/active_gap_v1/` 尚未建立，`T1` 是所有后续 task 的前置底座。
- **SSOT 优先**: 共享字段只能来自顶层 `docs/`，不能从旧 `first_wave_mvp` 反推。
- **TCG 是新核心对象**: 后续所有 task 都依赖 `TCG` 的字段稳定，`T1` 必须一次性锁好。
- **u/f 是可选边界**: `u/f` 缺省为空是当前 A 层首版的硬要求，不能在 `T1` 中偷变成必填。
- **测试下沉**: 基础类型、默认参数、`TCG` 识别和 snapshot 构造验证必须在 `T1` 内完成，不能全部留给 `T6`。

### Editable Paths

- `src/active_gap_v1/__init__.py` — 包入口
- `src/active_gap_v1/types.py` — 共享枚举与 dataclass
- `src/active_gap_v1/config.py` — 参数与默认值
- `src/active_gap_v1/snapshot.py` — `build_coordination_snapshot()`
- `src/active_gap_v1/tcg_selector.py` — `identify_tcg()`
- `tests/active_gap_v1/test_tcg_and_snapshot.py` — 基础类型与入口测试
- `experiments/active_gap_v1/.gitkeep` — 实验目录占位

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **第一波限定**: 只落 `docs/contracts.md` / `docs/formulas.md` 已冻结字段。
- **不要抢后续任务**: 不在 `T1` 中提前定义 merge target 搜索、证书、coordination branch 细节。
- **u/f 可选**: 边界车只能作为可选字段，不能在 `T1` 中偷偷变成强依赖。

## Skills

### Open URL

用于打开 formal spec 与 feature 设计文档，核对 `TCG`、snapshot 与 `u/f` 缺省语义。

### Code Exploration

用于检查 `snapshot.py`、`tcg_selector.py` 与 `docs/contracts.md` / `docs/formulas.md` 的对象映射。

### Parallel Subagent

仅在后续需要并行核对类型层与测试层时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 建立目录与占位文件（Step 1, no dependencies — start here）

- [ ] 1.1 创建 `src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/`
- [ ] 1.2 创建 `__init__.py`、`.gitkeep` 和基础测试文件

### Phase 2: 落共享类型与参数（Step 2, depends on Phase 1）

- [ ] 2.1 将共享枚举和 dataclass 翻译到 `types.py`
- [ ] 2.2 将 `ScenarioConfig` 默认值与时离散翻译到 `config.py`

### Phase 3: 落 snapshot 与 TCG 识别（Step 3, depends on Phase 2）

- [ ] 3.1 实现 `build_coordination_snapshot()`
- [ ] 3.2 实现 `identify_tcg()`，并明确 `u/f` 缺省语义

### Phase 4: 完成基础可消费验证（Step 4, depends on Phase 3）

- [ ] 4.1 为默认值、命名与实例化补单测
- [ ] 4.2 验证后续 task 可直接 import `types.py` / `config.py` / `snapshot.py` / `tcg_selector.py`

## 你负责的文件（白名单）

```text
src/active_gap_v1/__init__.py
src/active_gap_v1/types.py
src/active_gap_v1/config.py
src/active_gap_v1/snapshot.py
src/active_gap_v1/tcg_selector.py
tests/active_gap_v1/__init__.py
tests/active_gap_v1/test_tcg_and_snapshot.py
experiments/active_gap_v1/.gitkeep
```

## 禁止修改的文件（黑名单）

- `src/active_gap_v1/predictor.py`、`src/active_gap_v1/merge_target_planner.py`（由 `T2` 负责）
- `src/active_gap_v1/quintic.py`、`src/active_gap_v1/certificate.py`（由 `T3` 负责）
- `src/active_gap_v1/executor.py`、`src/active_gap_v1/state_machine.py`（由 `T4` 负责）
- `src/active_gap_v1/metrics.py`、`experiments/active_gap_v1/README.md`、`experiments/active_gap_v1/common.py`（由 `T5` 负责）
- `experiments/active_gap_v1/a_layer_micro_scenarios.py`、`experiments/active_gap_v1/regression_gate.py`（由 `T6` 负责）
- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md`（正式真源，不在本 task 内回写）

## 依赖的现有代码（需要先读的文件）

- `README.md`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`
- `docs/features/active_gap_v1/design.md`

## 实现步骤

### 1. 创建最小目录骨架

- 创建 `src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/` 的最小落点。
- 保证后续 task 有稳定白名单可接，但不要提前创建第二波目录。

### 2. 固化共享类型与契约对象

- 将共享枚举、`ScenarioConfig`、`VehicleState`、`TCG`、`CoordinationSnapshot`、`MergeTarget`、`QuinticBoundaryState`、`QuinticLongitudinalProfile`、`SafetyCertificate`、`RollingPlanSlice`、`ExecutionDecision`、`ExperimentResultSummary` 翻译到 `types.py`。
- 只落 `docs/contracts.md` 已冻结字段；不要为 `simple DP`、CBF/QP、多 partition 预留字段。

### 3. 固化参数层与时离散

- 在 `config.py` 中落 `ScenarioConfig` 默认值与一阶辅助常量。
- 明确 `planning_tick_s = rollout_tick_s = certificate_sampling_dt_s = 0.1` 的统一口径。
- 禁止新增文档未冻结的配置项；新增配置项预算为 `0`。

### 4. 实现 snapshot 与 TCG 识别

- `build_coordination_snapshot()` 负责冻结当前 tick 的观测，不夹带后续求解结果。
- `identify_tcg()` 只负责 active ego 选择与 `p/m/s` 识别，不负责 merge target 搜索。
- 必须明确 `u/f` 在 A 层首版中可缺省为空。

### 5. 补最小单测

- 为共享类型、默认参数值、字段命名、`TCG` 识别和 `u/f` 缺省逻辑补单测。
- 保证后续 task 可直接 import 并实例化这些对象。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/active_gap_v1/test_tcg_and_snapshot.py` 通过。
- 所有 dataclass / 枚举可被后续模块直接导入，不出现循环依赖。
- `ScenarioConfig` 默认值与 `docs/contracts.md`、`docs/formulas.md` 一致。
- A0/A1 首版输入即使缺少 `u/f`，`TCG` 也能稳定生成。

### 组装验证（产出运行时依赖的 task，可选）

- `T2` 能在不修改 `types.py` / `config.py` / `snapshot.py` / `tcg_selector.py` 的前提下直接消费共享对象。
- 目录骨架足以承接 `T2-T6` 的文件白名单。

### 环境验证（涉及配置加载的 task，可选）

- `ScenarioConfig` 的默认值可在无外部环境变量的情况下实例化。
- 所有共享类型对外序列化命名仍保持 snake_case。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 正式 spec | 无 | `docs/` 已冻结当前主算法的范围、契约和参数 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `types.py` | `T2-T6` | 当前主算法共享 dataclass/枚举字段稳定，不再临时加字段 |
| `config.py` | `T2-T6` | 当前主算法默认参数、时离散和几何边界稳定 |
| `CoordinationSnapshot` / `TCG` | `T2-T6` | active ego、三车组、`u/f` 缺省语义稳定 |

### 不要做

- 不要实现 merge target 搜索、三车 quintic、共享证书、coordination branch 或实验脚本。
- 不要新增 `simple DP`、CBF/QP、多 partition 或全局协同字段。
- 不要把 `u/f` 从“可选边界”提升成 A 层首版的必填对象。
