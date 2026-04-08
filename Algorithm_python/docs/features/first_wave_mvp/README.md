<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/feature-readme.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# 第一波 MVP Archive — 旧 baseline 任务索引

> 最后更新：`2026-04-07T22:48:56+08:00`
>
> **Archive / Baseline Notice**
> 1. 本目录只保留旧 `first_wave_mvp` baseline 的历史 task 语义。
> 2. 它不再代表当前主算法主线。
> 3. 当前主算法施工入口改为 `docs/features/active_gap_v1/`。
>
> Agent 使用说明：
> 1. 先读 `README.md`、`docs/design.md`、`docs/contracts.md`
> 2. 再读 `docs/formulas.md`、`docs/derivations.md`
> 3. 再读本目录下的 `design.md`
> 4. 最后读你被分配的 `T*.md`
> 5. 除非用户明确要求维护旧 baseline，否则不要把新主算法语义回写到本目录

## 任务列表

| ID | 任务 | 依赖 | 产出 |
|----|------|------|------|
| `T1` | `shared_types_and_config` | 无 | `src/first_wave_mvp/` 最小骨架、共享类型、参数层与基础测试 |
| `T2` | `snapshot_and_step2` | `T1` | `PlanningSnapshot`、单 partition 选取、`FIFO fixed/flexible` 候选生成与排序 |
| `T3` | `acceptance_gate_and_commit` | `T1`、`T2` | 共享 `acceptance gate`、`GateResult`、`CommittedPlan`、commit 协议 |
| `T4` | `rollout_and_state_machine` | `T1`、`T2`、`T3` | `rollout_step()`、执行状态机、等待/降级/abort 闭环 |
| `T5` | `experiments_and_metrics` | `T1`、`T2`、`T3`、`T4` | 首轮 3 个实验入口、指标产出、汇总格式 |
| `T6` | `validation_and_regression` | `T1`、`T2`、`T3`、`T4`、`T5` | L1/L2/L3 验证矩阵、多 seed 门禁与回归断言 |
| `T7` | `minimal_numeric_executor` | `T1`、`T2`、`T3`、`T4`、`T5`、`T6` | 最小纯 Python 数值执行器、真实 `outputs/.../summary.json` 与端到端实验运行 |

## Scout Findings

### Verified

- `README.md`、`docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` 已冻结第一波 MVP 正式边界。
- `docs/features/first_wave_mvp/` 已包含 `README.md`、`design.md` 和 `T1-T6` 六个 task 文档。
- repo 已具备 `src/`、`tests/`、`experiments/` 顶层目录，能承接后续实现落点。

### Discovered

- 当前 task 切分天然对应运行时主链：`类型/配置 -> Step 2 -> gate/commit -> rollout -> experiments -> regression`。
- 由于 `src/first_wave_mvp/` 还不存在，`T1` 不是“补文档”，而是真正的实现起步任务。
- 现有 task 文档已经具备白名单、黑名单、验收标准和边界，适合作为 repo 内 task 模板，再补一层 nexis 结构化评分字段即可。

### Gaps

- 当前 feature 包在执行性上已经清楚，但在 `nexis-plan-from-task` 视角下仍缺少显式的 `Scout Findings / Work Packages / Risks` 表达层。
- 六个 task 文档原先更接近 repo 内 task 模板，而不是 `nexis-create-task` 的 `Targets / Acceptance Criteria / Context / TODOs` 格式。
- 在代码未开始实现前，`T2-T6` 的 Done-when 仍依赖后续 agent 按文档约束落地，存在“文档与实现漂移”风险。

## Work Packages

### WP-1: 固定共享类型与参数底座（complexity: M, subagent: manual）

- Depends on: none
- Actions:
  1. 创建 `src/first_wave_mvp/`、`tests/first_wave_mvp/`、`experiments/first_wave_mvp/` 最小骨架。
  2. 将 `docs/contracts.md` 的共享枚举/dataclass 与 `docs/formulas.md` 的默认参数翻译到 `types.py` / `config.py`。
  3. 为共享对象和默认值补基础单测。
- Done when: `T1` 白名单文件存在，且后续 task 可直接 import。

### WP-2: 实现 Snapshot 与 Step 2（complexity: H, subagent: manual）

- Depends on: WP-1
- Actions:
  1. 固定单 partition / 单 ego 选取规则。
  2. 实现 `build_snapshot()`、target-lane ordered objects 与 `FIFO fixed/flexible` 候选生成。
  3. 固定 `(t_m, Δdelay, x_m)` 排序、tie-break 与稳定 `candidate_id`。
- Done when: 同一输入重复运行时，候选列表和 `candidate_id` 可重复。

### WP-3: 实现共享 Gate 与 Commit（complexity: H, subagent: manual）

- Depends on: WP-2
- Actions:
  1. 实现共享 `acceptance gate` 和 `REJECT(reason)` 映射。
  2. 实现 `commit_candidate()` 与 `COMMITTED` 字段锁定。
  3. 写清非法转移处理，禁止 hidden replanner 与 `DECOMMIT`。
- Done when: `GateResult` / `CommittedPlan` 可被 rollout 直接消费，且被拒候选不会改写语义字段。

### WP-4: 实现 Rollout 与状态机（complexity: H, subagent: manual）

- Depends on: WP-3
- Actions:
  1. 固化 `APPROACHING -> PLANNING -> COMMITTED/EXECUTING/POST_MERGE` 主链。
  2. 明确 `NO_FEASIBLE_PLAN`、wait、fail-safe、abort 的触发条件和副作用。
  3. 为正常路径与降级路径补状态机测试。
- Done when: 闭环可推进且失败分支可复盘，不依赖隐藏 planner。

### WP-5: 建立实验入口与指标汇总（complexity: M, subagent: manual）

- Depends on: WP-4
- Actions:
  1. 创建轻负荷正确性、中高负荷竞争、CAV 渗透率 / 协同范围消融三类实验入口。
  2. 输出 per-seed 指标和统一 summary 结构。
  3. 写清实验 README、输入参数和结果格式。
- Done when: `T6` 可直接消费三类实验结果，无需改实验脚本。

### WP-6: 建立回归门禁（complexity: M, subagent: manual）

- Depends on: WP-5
- Actions:
  1. 固定 L1/L2/L3 验证矩阵。
  2. 实现多 seed `mean / worst-seed / p95` 门禁逻辑。
  3. 为 pass/fail 正反例补回归测试。
- Done when: 第一波 MVP 是否通过门禁可自动判断，失败原因可定位到实验、指标和 seed。

### WP-7: 接入最小数值执行器（complexity: H, subagent: manual）

- Depends on: WP-6
- Actions:
  1. 实现 seed 驱动的 `world_state` 初始化器、tick 主循环执行器和流式指标收集器。
  2. 将三类实验入口从 manifest 输出升级为真实运行入口，并写出 `outputs/<experiment_id>/summary.json`。
  3. 补端到端测试，验证同 seed 可复现、异 seed 可区分、真实落盘 schema 与 `T5/T6` 契约兼容。
- Done when: 三类实验入口能够直接产出真实 `summary.json`，且结果可被 `T6` 门禁逻辑消费。

## 依赖关系图

当前第一波 MVP 不建议并行切多个核心实现 task，推荐按以下顺序串行推进：

```text
T1_shared_types_and_config
  -> T2_snapshot_and_step2
    -> T3_acceptance_gate_and_commit
      -> T4_rollout_and_state_machine
        -> T5_experiments_and_metrics
          -> T6_validation_and_regression
            -> T7_minimal_numeric_executor
```

这条链路对应正式文档中的主闭环：

`共享契约 -> Step 2 候选 -> Step 3 验收/commit -> rollout/state machine -> experiments -> regression gate`

## Execution Waves

### Wave 1（串行启动）

- `WP-1 / T1`

### Wave 2（依赖 Wave 1）

- `WP-2 / T2`

### Wave 3（依赖 Wave 2）

- `WP-3 / T3`

### Wave 4（依赖 Wave 3）

- `WP-4 / T4`

### Wave 5（依赖 Wave 4）

- `WP-5 / T5`

### Wave 6（依赖 Wave 5）

- `WP-6 / T6`

### Wave 7（依赖 Wave 6）

- `WP-7 / T7`

## 并行开发分组

| 阶段 | 可并行任务 | 最大并行 agent 数 | 说明 |
|------|-----------|------------------|------|
| `S1` | `T1` | `1` | 空仓起步，必须先冻结共享类型、参数层与目录骨架 |
| `S2` | `T2` | `1` | `Step 2` 先固定单 partition、候选枚举和排序语义 |
| `S3` | `T3` | `1` | `gate/commit` 必须消费 `T2` 的稳定候选契约 |
| `S4` | `T4` | `1` | rollout 只消费 `CommittedPlan`，不能与 `T3` 交叉改状态 |
| `S5` | `T5` | `1` | 首轮实验入口依赖闭环已跑通 |
| `S6` | `T6` | `1` | 回归门禁依赖 `T1-T5` 产物全部就绪 |
| `S7` | `T7` | `1` | 真实数值执行器依赖 `T1-T6` 的算法、实验结构与门禁全部就绪 |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `T1` 未把共享字段和默认值一次性锁稳，导致 `T2-T6` 反复回写类型层 | High | 明确 `T1` 是空仓起步的唯一底座任务，禁止后续 task 随意加字段 |
| `T2` 候选枚举和 `candidate_id` 非确定，导致回归不可复现 | High | 在 `T2` 文档中强制稳定枚举顺序和稳定 ID 规则 |
| `T3/T4` 边界滑移，导致 gate 变成 hidden replanner 或 rollout 偷改语义字段 | High | 用白名单、黑名单、状态流转表和非法转移断言硬切职责 |
| `T5/T6` 的统计口径不一致，导致实验结果可看但不可验收 | Medium | 统一 `mean / worst-seed / p95` 与 all-seed 安全门禁口径 |
| 后续 agent 直接修改 `docs/` 或引入第二波能力，破坏第一波闭环范围 | Medium | 在每个 task 中重复强调 `docs/` 为 SSOT，第二波内容全部列入黑名单 |
| 若没有真实执行器，`T5/T6` 只能验证门禁样例，无法产出真正的数值实验结果 | High | 通过 `T7` 接入 seed 驱动初始化、tick 主循环和真实 `summary.json` 落盘 |

## 代码预算

预算是膨胀预警线，不是鼓励一次性写满。

| 指标 | 上限 |
|------|------|
| 新增文件数 | `<= 20` |
| 单文件最大行数 | `<= 300` |
| 新增配置项 | `0`（只允许把 `docs/contracts.md` / `docs/formulas.md` 已冻结字段落代码） |
