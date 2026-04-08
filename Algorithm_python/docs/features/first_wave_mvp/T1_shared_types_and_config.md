<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/task.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# T1: 共享类型、配置与目录骨架 (Shared Types, Config, and Skeleton)

> 最后更新：`2026-04-05T19:13:53+08:00`

## 前置条件

- 无前置 task。
- 必读：`docs/contracts.md`（重点看“共享类型”“核心数据模型”“字段锁定规则”“模块接口签名”）。
- 必读：`docs/formulas.md`（重点看“时离散与第一波默认参数”）。
- 必读：`docs/features/first_wave_mvp/design.md`。

## 目标

在当前空目录仓库中创建第一波 MVP 的最小可引用骨架，把共享枚举、dataclass、`ScenarioConfig` 默认值和时间/参数常量一次性冻结到代码层，不引入任何 `Step 2/Step 3/rollout` 逻辑。

## Targets

1. **目录骨架可落地**: 创建 `src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/` 的最小骨架，后续 task 白名单可以直接落位。
2. **共享契约已落代码**: `types.py` / `config.py` 承接第一波共享枚举、dataclass、默认参数与统一时离散，且不预埋第二波字段。
3. **下游可直接消费**: `T2-T6` 无需回写 `T1` 文件即可 import 共享对象并开始实现。

## Acceptance Criteria

### Step 1: 建立最小目录骨架（no dependencies — start here）

- [ ] 已创建 `src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/` 的最小落点。
- [ ] 第一波必要占位文件已存在，后续 task 的白名单文件都有可挂载的目录。
- [ ] 没有预创建第二波目录或多余扩展模块。

### Step 2: 固化共享类型与参数（depends on Step 1）

- [ ] `types.py` 包含第一波共享枚举和 dataclass，字段与 `docs/contracts.md` 一致。
- [ ] `config.py` 中的默认参数、几何边界和时离散与 `docs/formulas.md` / `docs/contracts.md` 一致。
- [ ] 未出现 `simple DP`、`DECOMMIT`、多 partition 等第二波字段。

### Step 3: 完成基础验证与可消费性（depends on Step 2）

- [ ] `pytest tests/first_wave_mvp/test_types_and_config.py` 通过。
- [ ] 共享对象可以被后续 task 直接 import，不产生循环依赖。
- [ ] 默认值、单位后缀和对象实例化均有可重复验证。

## Context

### Repos:

- `/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration/Algorithm_python` — 第一波 MVP 的正式 spec 与后续实现落点
  - `docs/contracts.md` — 共享类型、字段锁定规则和模块接口 SSOT
  - `docs/formulas.md` — 时离散、默认参数和公式层 SSOT
  - `docs/features/first_wave_mvp/design.md` — task 到实现目录的映射说明

### Docs:

**Formal Specs:**

- `docs/design.md`: 第一波范围、闭环与状态语义
- `docs/contracts.md`: 共享枚举、dataclass、模块接口
- `docs/formulas.md`: 时间步长、默认参数、几何边界

**Feature Package:**

- `docs/features/first_wave_mvp/README.md`: 执行顺序与工作包
- `docs/features/first_wave_mvp/design.md`: 推荐实现落点和状态约束

### Developer insights:

- **空仓起步**: 当前 `src/first_wave_mvp/` 尚未建立，`T1` 是所有后续 task 的前置底座。
- **SSOT 优先**: 第一波共享字段只能来自 `docs/contracts.md` 和 `docs/formulas.md`，不能从旁证文档反推。
- **单向依赖**: `T1` 只提供底座，不承担 `snapshot`、`gate`、`rollout` 逻辑。
- **冻结优先**: 第一波只落已冻结的字段和默认值，避免“先预留再说”的扩 scope。
- **测试下沉**: 基础类型和配置验证必须在 `T1` 内完成，不能全部留给 `T6` 兜底。

### Editable Paths

- `src/first_wave_mvp/` — 共享类型与参数底座
- `tests/first_wave_mvp/` — 基础单测
- `experiments/first_wave_mvp/.gitkeep` — 实验目录占位

### Agent Rules

- Use plan mode first to create a plan before implementation.
- Ask the user when in doubt.
- Write tests before implementation.
- Set up `.cursor/` hooks for develop-test-debug loops.
- Use subagent to dive into separated tasks.
- **第一波限定**: 只落 `docs/contracts.md` / `docs/formulas.md` 已冻结字段。
- **不要抢后续任务**: 不在 `T1` 中提前定义 `snapshot`、`gate`、`rollout` 细节。
- **空仓优先**: 先保证目录和可 import 骨架成立，再补类型与参数细节。

## Skills

### Open URL

用于打开本地或远程规范链接，核对正式 spec 的原始表述。

### Code Exploration

用于检查 `docs/contracts.md`、`docs/formulas.md` 与 `src/first_wave_mvp/` 之间的字段映射是否一致。

### Parallel Subagent

仅在后续实现阶段需要并行核对类型层与测试层时使用；当前 task 以主 agent 直接落地为主。

## TODOs

### Phase 1: 建立目录与占位文件（Step 1, no dependencies — start here）

- [ ] 1.1 创建 `src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/`
- [ ] 1.2 创建 `__init__.py`、`.gitkeep` 和基础测试文件

### Phase 2: 落共享类型与参数（Step 2, depends on Phase 1）

- [ ] 2.1 将共享枚举和 dataclass 翻译到 `types.py`
- [ ] 2.2 将 `ScenarioConfig` 默认值与时离散翻译到 `config.py`

### Phase 3: 完成基础可消费验证（Step 3, depends on Phase 2）

- [ ] 3.1 为默认值、命名与实例化补单测
- [ ] 3.2 验证后续 task 可直接 import `types.py` / `config.py`

## 你负责的文件（白名单）

```text
src/first_wave_mvp/__init__.py
src/first_wave_mvp/types.py
src/first_wave_mvp/config.py
tests/first_wave_mvp/__init__.py
tests/first_wave_mvp/test_types_and_config.py
experiments/first_wave_mvp/.gitkeep
```

## 禁止修改的文件（黑名单）

- `src/first_wave_mvp/snapshot.py`、`src/first_wave_mvp/step2_fifo.py`（由 `T2` 负责）
- `src/first_wave_mvp/gate.py`、`src/first_wave_mvp/commit.py`（由 `T3` 负责）
- `src/first_wave_mvp/rollout.py`、`src/first_wave_mvp/state_machine.py`（由 `T4` 负责）
- `src/first_wave_mvp/metrics.py`、`experiments/first_wave_mvp/*.py`（由 `T5/T6` 负责）
- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md`（正式真源，不在本 task 内回写）

## 依赖的现有代码（需要先读的文件）

- `README.md`
- `docs/design.md`
- `docs/contracts.md`
- `docs/formulas.md`
- `docs/features/first_wave_mvp/design.md`

## 实现步骤

### 1. 创建最小目录骨架

- 创建 `src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/` 的最小落点。
- 保证后续 task 有稳定白名单可接，但不要提前创建第二波目录。

### 2. 固化共享类型与契约对象

- 将 `PolicyTag`、`ExecutionState`、`RejectReason`、`CommitState`、`GapRef`、`TrajectoryPoint`、`VehicleState`、`PlanningSnapshot`、`CandidatePlan`、`GateResult`、`CommittedPlan`、`ExperimentResultSummary` 翻译到 `types.py`。
- 只落 `docs/contracts.md` 已冻结字段；不要为 `simple DP`、`DECOMMIT`、多 partition 预留字段。

### 3. 固化参数层与时离散

- 在 `config.py` 中落 `ScenarioConfig` 默认值与一阶辅助常量。
- 明确 `planning_tick_s = rollout_tick_s = gate_sampling_dt_s = 0.1` 的统一口径。
- 禁止新增文档未冻结的配置项；新增配置项预算为 `0`。

### 4. 补最小单测

- 为共享类型、默认参数值、字段命名和单位后缀补单测。
- 保证后续 task 可直接 import 并实例化这些对象。

## 验收标准

### 零件验证（每个 task 必须）

- `pytest tests/first_wave_mvp/test_types_and_config.py` 通过。
- 所有 dataclass / 枚举可被后续模块直接导入，不出现循环依赖。
- `ScenarioConfig` 默认值与 `docs/contracts.md`、`docs/formulas.md` 一致。

### 组装验证（产出运行时依赖的 task，可选）

- `T2` 能在不修改 `types.py` / `config.py` 的前提下直接消费共享对象。
- 目录骨架足以承接 `T2-T6` 的文件白名单。

### 环境验证（涉及配置加载的 task，可选）

- `ScenarioConfig` 的默认值可在无外部环境变量的情况下实例化。
- 所有共享类型对外序列化命名仍保持 snake_case。

## 边界

### 消费（本 task 依赖的外部输出）

| 依赖项 | 来源 Task | 预期状态 |
|-------|----------|---------|
| 正式 spec | 无 | `docs/` 已冻结第一波 MVP 范围、契约和参数 |

### 产出（其他 Task 依赖本 task 的输出）

| 产出项 | 消费方 Task | 承诺 |
|-------|-----------|------|
| `types.py` | `T2/T3/T4/T5/T6` | 第一波共享 dataclass/枚举字段稳定，不再为后续 task 临时加字段 |
| `config.py` | `T2/T3/T4/T5/T6` | 第一波默认参数、时离散和几何边界稳定 |
| 最小目录骨架 | `T2/T3/T4/T5/T6` | 后续 task 有固定白名单可接 |

### 不要做

- 不要实现 `Step 2` 候选生成、共享 gate、rollout、实验脚本或回归门禁。
- 不要新增 `simple DP`、两层分层、上游换道、多 partition 或全局协同字段。
- 不要把 `reference/ramp_inventory/` 里的旁证反向写成正式默认值。
