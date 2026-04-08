# 场景与实验清单

> 来源：`forum/xiangmu_qianyi.json` 的 Step-1 / Step-2 收敛结果
>
> 最后更新：`2026-04-05T17:16:21+08:00`

## 总览

当前 `ramp/` 的实验主链可以先理解成 3 层：

1. 场景层：`ramp/scenarios/` 提供路网、路由、sumocfg 和部分元数据。
2. 运行层：`ramp/experiments/run.py` 是统一单跑入口。
3. 汇总层：`summarize_metrics.py`、`run_pain_matrix.py`、`check_plans.py` 等脚本对输出做聚合、诊断或复盘。

本文件的重点不是列目录，而是把“场景 -> 实验脚本 -> 产物 -> 引用文档”的链条串起来。

## 场景矩阵

| ID | 场景目录 | 定位 | 关键差异 | 典型产物 | 相关文档 | evidence_level | confidence | updated_at |
|----|----------|------|----------|----------|----------|----------------|------------|------------|
| `SCN-MIN` | `ramp/scenarios/ramp_min_v1` | 最小可复现基础场景 | 最小网络、静态路由 | `output/ramp_min_v1/<policy>/metrics.json` | `README.md` 中的示例命令 | `A-code` | `high` | `2026-03-30T23:19:18+08:00` |
| `SCN-MLANE-V2` | `ramp/scenarios/ramp__mlane_v2` | 多车道基础场景 | StageA 多车道拓扑；带 checklist | `output/ramp__mlane_v2/<policy>/metrics.json` | `ramp/scenarios/ramp__mlane_v2/STAGEA_CONTRACT_CHECKLIST.md` | `A-code` + `B-support` | `high` | `2026-03-30T23:19:18+08:00` |
| `SCN-MIXED` | `ramp/scenarios/ramp__mlane_v2_mixed` | mixed 标准强度基准场景 | `rou_meta.json` 记录标准流量与渗透率 | `output/ramp__mlane_v2_mixed/<policy>/metrics.json` | `docs/RAMP_VALIDATION.md`、验收文档 | `A-code` + `B-support` | `high` | `2026-03-30T23:19:18+08:00` |
| `SCN-MIXED-HF` | `ramp/scenarios/ramp__mlane_v2_mixed_hf` | 高流量扩展场景 | 比 `SCN-MIXED` 更高主路与匝道流量 | `output/ramp__mlane_v2_mixed_hf/<policy>/metrics.json` | `docs/RAMP_VALIDATION.md` | `A-code` + `B-support` | `high` | `2026-03-30T23:19:18+08:00` |
| `SCN-MIXED-STRESS` | `ramp/scenarios/ramp__mlane_v2_mixed_stress` | 高压压力场景 | 流量进一步上探，偏 stress 对比 | `output/ramp__mlane_v2_mixed_stress/<policy>/metrics.json` | `docs/RAMP_VALIDATION.md` | `A-code` + `B-support` | `high` | `2026-03-30T23:19:18+08:00` |

## 统一实验入口

| ID | 脚本 | 作用 | 主要输入 | 主要输出 | confidence |
|----|------|------|----------|----------|------------|
| `EXP-RUN` | `ramp/experiments/run.py` | 单次仿真实验主入口 | `--scenario`、`--policy`、seed、流量参数等 | `metrics.json`、`config.json`、多份 evidence CSV | `high` |
| `EXP-GEN-ROU` | `ramp/tools/generate_mixed_rou.py` | 生成混合流路由 | 路由参数、渗透率、seed | 动态生成的 mixed 路由 | `high` |
| `EXP-SUMMARY` | `ramp/experiments/summarize_metrics.py` | 递归汇总多次实验结果 | 输出目录树 | `summary.json`、`summary.md` | `high` |
| `EXP-PAIN` | `ramp/tools/run_pain_matrix.py` | 批量 pain matrix 实验 | 世界设定、seed、主实验参数 | `output/pain_matrix/pain_matrix_summary.json` 等 | `medium` |
| `EXP-CHECK-PLANS` | `ramp/experiments/check_plans.py` | 离线核对计划一致性 | 已跑输出目录 | 控制台结果或人工判读结果 | `high` |
| `EXP-SNAPSHOT` | `ramp/experiments/dump_plans_snapshot.py` | 导出计划快照 | 已跑输出目录 | 快照文件 | `high` |
| `EXP-MISMATCH` | `ramp/experiments/dump_mismatch_report.py` | 导出不一致报告 | 已跑输出目录 | `mismatch_report.csv` 等 | `high` |

## 关系链

### 最小回归链

- `SCN-MIN` -> `EXP-RUN` -> `output/ramp_min_v1/<policy>/metrics.json`
- 常见用途：跑 `no_control` / `fifo` / `dp` 的最小回归
- 适合后续做迁移后的数值验证门禁

### mixed 基准链

- `SCN-MIXED` -> `EXP-RUN`
- 可搭配 `EXP-GEN-ROU` 生成 mixed 路由
- 输出再进入 `EXP-SUMMARY` 做对比汇总
- 当前最像“基准 / 对比实验”的是 `no_control / fifo / dp / hierarchical` 同场景对比

### 高流量 / 高压扩展链

- `SCN-MIXED-HF` / `SCN-MIXED-STRESS` -> `EXP-RUN`
- 当前资料更偏向比较 `no_control` 与 `hierarchical`
- 用途更像压力测试或扩展验证，而不是最小基准

### pain matrix 链

- 默认以 `SCN-MIXED` 为基础 -> `EXP-PAIN`
- `EXP-PAIN` 内部再批量调用 `EXP-RUN`
- 输出为 `pain_matrix_summary.json` 等聚合产物

## 提炼后的新仓库场景骨架

这一节归档的是：从旧 `ramp` 场景与实验链里抽出来、已经足以指导新仓库 MVP 建模的场景语义。

### `DEC-SCN-MVP-GEOMETRY`

当前已经确认，新仓库第一版不再沿用旧 `Zone A/B/C` 语义，而是改成：

- 单主线 + 单匝道 + 单冲突区
- `control zone` 保留，但按子区理解
- 匝道显式拆成：
  - `ramp_approach_subzone = [0, 50m)`
  - `legal_merge_zone = [50m, 290m]`
  - `emergency_tail = [290m, 300m]`

这样做的目的不是否认旧场景，而是把“哪一段允许开始并完成变道”明确写死。

### `DEC-SCN-MVP-CONTROL-SCOPE`

- MVP 阶段只主动求解匝道 merge 问题。
- 上游换道区在语义上仍属于更大的 `control zone`，但当前只保留 observe-only 地位，先不纳入主动控制。
- 每个时刻最多只存在 1 个 `active decision partition`。

### 从旧实验链到新实验骨架的映射

当前已经确认，旧实验链中最值得迁移为新仓库第一波数值验证的，不再是“照搬所有场景目录”，而是提炼成 3 类实验骨架：

1. 轻负荷正确性
2. 中高负荷竞争
3. CAV 渗透率 / 协同范围消融

它们与旧链路的关系可先理解为：

- `SCN-MIN` 更接近“轻负荷正确性”的原型。
- `SCN-MIXED` 更接近“中高负荷竞争”的原型。
- `SCN-MIXED` 配合渗透率参数与协同对象范围裁剪，可转成“CAV 渗透率 / 协同范围消融”的原型。
- `SCN-MIXED-HF`、`SCN-MIXED-STRESS`、`EXP-PAIN` 仍很有价值，但更适合作为 post-MVP 扩展，而不是第一波强制门禁。

## 典型实验候选

当前最值得作为后续迁移样本的“典型实验”有 4 类：

1. `SCN-MIN` 上的最小回归实验
2. `SCN-MIXED` 上的四策略基准对比
3. `SCN-MIXED-HF` / `SCN-MIXED-STRESS` 上的高负载扩展对比
4. `EXP-PAIN` 对应的 pain score 矩阵实验

但若只看新仓库 MVP 的第一波门禁，当前建议把优先级收敛成：

1. 轻负荷正确性
2. 中高负荷竞争
3. CAV 渗透率 / 协同范围消融

之所以把它们列为候选，是因为它们分别覆盖：

- 最小正确性
- 同场景策略差异
- 高负载行为
- 衍生指标体系

## 产物清单

当前已经明确的核心产物包括：

- `metrics.json`
- `config.json`
- `control_evidence.csv`
- `contract_evidence.csv`
- `feedback_evidence.csv`
- `summary.json`
- `summary.md`
- `pain_matrix_summary.json`
- `mismatch_report.csv`

其中：

- `metrics.json` 是大多数实验链的最小汇总单元。
- 多份 evidence CSV 是验收和复盘的重要桥梁。
- `summary.json` / `summary.md` 更像横向汇总层。

## 命名别名与断裂点

### `SCN-MLANE-V2` 内部的 mixed 配置命名

`ramp/scenarios/ramp__mlane_v2` 目录里同时存在：

- `ramp__mlane_v2.sumocfg`
- `ramp__mlane_v2_mixed.sumocfg`

但 `EXP-RUN` 当前按 `--scenario <name>` 只会自动找 `<name>/<name>.sumocfg`。这意味着：

- 当 `--scenario ramp__mlane_v2` 时，不会自动命中 `ramp__mlane_v2_mixed.sumocfg`
- 这个文件在当前主链路里更像未自然接入的配置

这会在 `evidence_and_gaps.md` 中作为 `GAP-UNREACHABLE-SUMOCFG` 跟踪。

### `merge_edge` 默认值不一致

- `EXP-RUN` 默认 `merge_edge` 是 `main_h4`
- `EXP-PAIN` 默认 `merge_edge` 是 `main_h3`

如果不显式对齐参数，不同实验之间的结论会混入场景配置差异。这个问题在 `evidence_and_gaps.md` 里记为 `GAP-MERGE-EDGE-MISMATCH`。

### 根目录的 `Baseline_and_comparative_trials.*`

仓库根的 `Baseline_and_comparative_trials.json/html` 不是 `EXP-SUMMARY` 自动生成的实验结果产物，而是较新的讨论记录。它可以解释过程，但不应该直接拿来当作 `ramp` 实验链的最终产物。
