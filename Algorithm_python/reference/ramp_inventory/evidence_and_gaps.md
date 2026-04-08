# 证据与缺口

> 来源：`forum/xiangmu_qianyi.json` 的 Step-1 / Step-2 收敛结果
>
> 最后更新：`2026-04-05T17:54:51+08:00`

## 使用方式

本文件强制把信息分成 4 层：

1. 正式证据：可以直接支撑“当前事实是什么”
2. 过程旁证：可以解释上下文，但不能代替正式结论
3. 推测线索：当前已经看到风险，但证据还不闭合
4. 未决问题：后续迁移前需要继续补证据的项

## 正式证据

| ID | 类型 | source_path | 内容 | evidence_level | confidence | updated_at |
|----|------|-------------|------|----------------|------------|------------|
| `EVD-ACCEPT-DOC` | 验收主文档 | `docs/STRONGA_算法交付验收文档.md` | Strong A v1.0 的正式交付与验收口径，包括场景、命令、三 seed 指标表、公式与材料清单 | `A-doc` | `high` | `2026-03-30T23:19:18+08:00` |
| `EVD-RUN` | 实验主入口 | `ramp/experiments/run.py` | 单跑入口、输出结构、evidence CSV 写出链路 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `EVD-EVIDENCE-CHAIN` | 证据链实现 | `ramp/experiments/evidence_chain.py` | 各类 evidence 字段、`expected_merge_position_m()` 等逻辑 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `EVD-HIER-SCHED` | 分层调度实现 | `ramp/policies/hierarchical/scheduler.py` | fixed / flexible 分支、Zone C 协同逻辑、参数常量 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `EVD-MERGE-POINT` | 合流点实现 | `ramp/policies/hierarchical/merge_point.py` | 合流点几何参数、搜索与状态机 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `EVD-MERGE-CONTRACT` | 运行时契约类型 | `ramp/runtime/types.py` | `MergeContract` 当前字段边界 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |

## 过程旁证

| ID | source_path | 可用价值 | 不可直接承载的结论 | evidence_level |
|----|-------------|----------|--------------------|----------------|
| `PROC-BASELINE-FORUM` | `Baseline_and_comparative_trials.json` | 解释 fixed / flexible 争议、参数决议、待办和审阅分歧 | 不能替代正式实验汇总表 | `B-process` |
| `PROC-BASELINE-HTML` | `Baseline_and_comparative_trials.html` | 展示层阅读更方便 | 与 JSON 同源，不新增事实 | `B-process` |
| `PROC-RAMP-VALIDATION` | `docs/RAMP_VALIDATION.md` | 补充 mixed / hf / stress 场景的命令与汇总示例 | 不是正式验收表 | `B-support` |
| `PROC-STAGEA-CHECK` | `ramp/scenarios/ramp__mlane_v2/STAGEA_CONTRACT_CHECKLIST.md` | 帮助理解 StageA 场景和 merge edge 约定 | 不是算法实现证明 | `B-support` |

## 已确认的设计输入提炼

这一节记录的是：基于旧系统盘点、并在 `forum/xiangmu_qianyi.json` 中已经确认的设计输入。它们不是“旧系统已经这样实现”的事实，而是“新仓库必须这样重定义”的已确认提炼结论。

| ID | source_path | 提炼结论 | evidence_level | confidence | updated_at |
|----|-------------|----------|----------------|------------|------------|
| `DEC-COMP-ANCHOR` | `forum/xiangmu_qianyi.json` | 新仓库中 `fixed / flexible` 统一绑定 `completion anchor`，不再绑定开始变道点 | `B-process` | `high` | `2026-04-05T17:16:21+08:00` |
| `DEC-MVP-ZONES` | `forum/xiangmu_qianyi.json` | MVP 采用按绝对里程定义的匝道子区：`[0,50)`、`[50,290]`、`[290,300]`，并保留更大的 `control zone` 概念 | `B-process` | `high` | `2026-04-05T17:16:21+08:00` |
| `DEC-MVP-CLOSED-LOOP` | `forum/xiangmu_qianyi.json` | MVP 只允许 1 个 `active decision partition`，并采用 `Step 2 生成候选 + Step 3 共享验收门` 的闭环 | `B-process` | `high` | `2026-04-05T17:16:21+08:00` |
| `DEC-MVP-BASELINES` | `forum/xiangmu_qianyi.json` | `no_control` 降为参考下界；首批 baseline 冻结为 `FIFO + fixed anchor` 与 `FIFO + flexible anchor` | `B-process` | `high` | `2026-04-05T17:16:21+08:00` |
| `DEC-MVP-COMMIT` | `forum/xiangmu_qianyi.json` | MVP 中一旦通过 acceptance gate 即进入 `COMMITTED`；`DECOMMIT` 不进入 MVP，但需作为 future extension 保留 | `B-process` | `high` | `2026-04-05T17:16:21+08:00` |
| `DEC-FIFO-CANDIDATES` | `forum/xiangmu_qianyi.json` | `Step 2` 当前冻结为：按 `x_m` 枚举、按 `t_r^free` 导出唯一 FIFO gap、按 `t_m -> delay -> x_m` 做字典序排序 | `B-process` | `medium` | `2026-04-05T17:16:21+08:00` |

## 已关闭的 MVP 文档问题

以下问题已经不再停留在 `OPEN-*` 状态，而是已经被正式写入顶层文档：

| ID | 关闭方式 | 正式落点 | closed_at |
|----|----------|----------|-----------|
| `OPEN-CONTRACT-MVP` | 已冻结第一波 `common I/O contract` | `docs/contracts.md` | `2026-04-05T17:54:51+08:00` |
| `OPEN-TIME-DISCRETIZATION` | 已冻结 `planning / rollout / gate` 的统一时离散口径 | `docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` | `2026-04-05T17:54:51+08:00` |
| `OPEN-PARAM-FREEZE` | 已冻结 `T_lc^{MVP}`、`h_pr`、`h_rf`、fail-safe 最大制动等默认参数 | `docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` | `2026-04-05T17:54:51+08:00` |
| `OPEN-EXPERIMENT-GATES` | 已冻结首轮 3 个实验的指标与通过条件 | `docs/design.md`、`docs/contracts.md` | `2026-04-05T17:54:51+08:00` |

## 已确认偏差线索

### `GAP-FIXED-SEMANTICS`

- 优先级：`P0`
- 类型：`flow_gap`
- 结论：`fixed` 当前更像“调整搜索起点的 `merge_policy` 分支”，而不是独立固定锚点算法。
- 主证据：
  - `Baseline_and_comparative_trials.json`
  - `ramp/policies/hierarchical/scheduler.py`
  - `ramp/policies/hierarchical/merge_point.py`
- 当前影响：
  - 会影响 inventory 中“算法族谱”和“典型实验命名”
  - 后续迁移时不能把 `fixed` 误拆成一套完全独立策略

### `GAP-CONTRACT-POSITION`

- 优先级：`P0`
- 类型：`flow_gap`
- 结论：`MergeContract` 运行时类型当前不包含 `expected_merge_position_m`，而实验层又需要记录“期望合流位置”。
- 主证据：
  - `Baseline_and_comparative_trials.json`
  - `ramp/runtime/types.py`
  - `ramp/experiments/run.py`
  - `ramp/experiments/evidence_chain.py`
- 当前影响：
  - 契约语义与 evidence 语义分裂
  - 后续抽离纯数值验证时，数据模型边界会不稳定

### `GAP-FLEXIBLE-OFFSET`

- 优先级：`P1`
- 类型：`parameter_drift`
- 结论：`evidence_chain.py` 当前把 flexible 的期望合流位置硬编码为 `20.0m`。
- 主证据：
  - `Baseline_and_comparative_trials.json`
  - `ramp/experiments/evidence_chain.py`
- 当前影响：
  - 若真实合流位置不是该常量，相关指标会偏向“统计层默认值”

### `GAP-COOP-DELTA-V`

- 优先级：`P0`
- 类型：`parameter_drift`
- 结论：论坛里曾投票建议把协同 `Δv` 改为动态，但验收文档与代码里当前仍是 `1.0 m/s`。
- 主证据：
  - `Baseline_and_comparative_trials.json`
  - `docs/STRONGA_算法交付验收文档.md`
  - `ramp/policies/hierarchical/scheduler.py`
- 当前影响：
  - 需要区分“讨论后决议”和“当前冻结交付版本”
  - inventory 里不能把动态 `Δv` 写成已实现事实

### `GAP-P75-RESULT`

- 优先级：`P1`
- 类型：`result_unverifiable`
- 结论：验收文档里提到的 p75 gap 对齐速度 `23.68 -> 19.11`，当前尚未在仓库内找到直接对应的产物锚点。
- 主证据：
  - `docs/STRONGA_算法交付验收文档.md`
- 缺失证据：
  - 对应 `metrics.json`、汇总脚本或中间产物路径
- 当前影响：
  - 该项目前只能保留为“文档声称”，不能作为已复算事实

### `GAP-UNREACHABLE-SUMOCFG`

- 优先级：`P1`
- 类型：`flow_gap`
- 结论：`ramp__mlane_v2` 目录下的 `ramp__mlane_v2_mixed.sumocfg` 在当前 `run.py` 的命名约定下不会自然命中。
- 主证据：
  - `ramp/scenarios/ramp__mlane_v2/`
  - `ramp/experiments/run.py`
- 当前影响：
  - 某些实验配置文件可能处于“存在但不在主链路上”的状态

### `GAP-MERGE-EDGE-MISMATCH`

- 优先级：`P0`
- 类型：`parameter_drift`
- 结论：`run.py` 默认 `merge_edge=main_h4`，而 `run_pain_matrix.py` 默认 `merge_edge=main_h3`。
- 主证据：
  - `ramp/experiments/run.py`
  - `ramp/tools/run_pain_matrix.py`
  - `ramp/scenarios/ramp__mlane_v2/STAGEA_CONTRACT_CHECKLIST.md`
- 当前影响：
  - 不同实验链即使名字相似，也可能混入不同 merge edge 配置

### `GAP-TEST-MISSING`

- 优先级：`P0`
- 类型：`test_gap`
- 结论：`POL-FIFO`、`POL-NC`、`RT-CTRL`、`run.py`、`HierarchicalScheduler` 的完整行为路径缺少明显专属自动化测试。
- 主证据：
  - `ramp/tests/`
  - `forum/xiangmu_qianyi.json` 的代码线盘点结果
- 当前影响：
  - 后续迁移时，最容易在“看起来简单但没被锁住”的模块上引入行为漂移

## 推测线索

这些项已经值得记住，但还不能当作闭合结论：

- `RT-HSC` 的静默异常路径可能掩盖 Zone A / Zone C 数据缺失问题
- `Strong A v1.0` 与 `hierarchical + strong_a_v1` 的参数映射还没有整理成单一表
- `Baseline_and_comparative_trials.*` 与最终验收表之间的数字一致性虽然看起来高，但仍应优先回到原始实验产物核对

## 未决问题

| ID | 问题 | 当前优先级 | 需要补什么 |
|----|------|------------|------------|
| `OPEN-P75` | p75 gap 对齐速度的原始产物在哪里 | `P1` | 找到对应的 `metrics.json` 或汇总结果路径 |
| `OPEN-Q1Q2` | 论坛里提到的 Q1 / Q2 是否已落到其他任务文档或实验记录 | `P2` | 扩展搜索更多过程文档 |
| `OPEN-STRONGA-MAP` | `strong_a_v1` 到命令行参数、运行时行为的映射是否需要单独成表 | `P1` | 精读 `run.py` 参数分支与相关配置 |
| `OPEN-PAIN-CONFIG` | pain matrix 与主实验链应统一到哪个 `merge_edge` | `P0` | 明确一份统一实验参数口径 |

## 当前结论边界

截至本文件更新时，可以安全下结论的只有：

- 哪些算法、场景、脚本和文档当前存在
- 哪些地方已经能从代码和验收文档直接对上
- 哪些地方明显存在命名、参数、测试或产物闭环缺口

还不能安全下结论的包括：

- 最终迁移方案
- 哪个实验集合将作为唯一的数值验证标准
- 哪些讨论中的改动已经真正进入冻结版本
