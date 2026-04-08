# ramp inventory 总览

> 目标：在迁移 `../ramp/` 到纯数值验证仓库之前，先把现有算法、场景、实验链和证据缺口整理清楚。
>
> 最后更新：`2026-04-05T17:16:21+08:00`

## 范围

本目录只回答 4 类问题：

1. `ramp/` 里现在到底有哪些算法和子模块。
2. 这些算法依赖哪些场景、实验入口和产物。
3. 哪些较新的文档可以作为主证据，哪些只能作为过程旁证。
4. 在正式迁移前，哪些缺口和风险必须先被看见。
5. 旧系统盘点已经提炼出哪些可直接进入新数值验证设计的输入约束。

本目录不做以下事情：

- 不把本目录当作 `docs/design.md` 或 `docs/contracts.md` 的替代 SSOT。
- 不把尚未冻结的讨论直接包装成正式设计契约。
- 不跳过旧系统证据，直接凭印象重写算法事实。

## 文档导航

- `algorithms.md`：算法族谱、代码入口、关键依赖、现有 tests、迁移切断点。
- `scenarios_and_experiments.md`：场景矩阵、实验脚本、产物链、典型实验候选。
- `evidence_and_gaps.md`：正式证据、过程旁证、偏差线索、未决问题和优先级。

当前落盘状态：

- `README.md`：已完成
- `algorithms.md`：已完成
- `scenarios_and_experiments.md`：已完成
- `evidence_and_gaps.md`：已完成
- `2026-04-05` 新增：已把若干“从旧系统盘点中提炼出的新仓库设计输入”补充归档到各子文档

## 证据优先级

统一按下面的层级使用证据：

| 等级 | 含义 | 当前来源 |
|------|------|----------|
| `A-code` | 代码与 tests 直接证明“实现存在 / 字段存在 / 运行链路存在” | `ramp/policies/`、`ramp/scheduler/`、`ramp/runtime/`、`ramp/tests/` |
| `A-doc` | 正式交付或验收口径 | `docs/STRONGA_算法交付验收文档.md` |
| `B-process` | 较新的过程讨论，可用于解释命名、分歧、待确认决议 | `Baseline_and_comparative_trials.json`、`Baseline_and_comparative_trials.html` |
| `B-support` | 补充型说明文档或 checklist | 例如 `docs/RAMP_VALIDATION.md`、`ramp/scenarios/ramp__mlane_v2/STAGEA_CONTRACT_CHECKLIST.md` |
| `C-legacy` | 历史文档或仅命名线索 | 仅作旁证，不单独承载结论 |

使用规则：

- 判断“代码里有没有”时，`A-code` 优先。
- 判断“交付口径是什么”时，`A-doc` 优先。
- `B-process` 可以解释为什么会有某个命名、参数或 TODO，但不能替代正式验收表。
- 没有 `A-code` 或 `A-doc` 支撑时，结论必须降级，并在 `evidence_and_gaps.md` 标记缺口。

## 统一元数据

本目录中的条目统一尽量带这些元数据：

- `ID`：稳定引用 ID。
- `source_path`：证据来源路径。
- `evidence_level`：上面的证据等级。
- `confidence`：`high` / `medium` / `low`。
- `updated_at`：本轮整理时间。

## 稳定 ID 规则

为避免后续迁移时文档互相漂移，约定以下前缀：

- `POL-*`：顶层策略，如 `no_control`、`fifo`、`dp`、`hierarchical`
- `MOD-*`：策略内部的纯算法或关键子模块
- `RT-*`：运行时采集、控制、仿真驱动等强 SUMO 绑定模块
- `SCN-*`：场景
- `EXP-*`：实验脚本或实验链
- `GAP-*`：偏差线索、缺口或高风险项
- `DEC-*`：由旧系统盘点提炼出的、已在当前任务讨论中确认的设计输入

其余文档优先引用这些 ID，而不是重复解释术语。

## 关键命名映射

当前已确认几个容易混淆的名字：

- `fixed` / `flexible` 不是两套顶层策略，而是 `hierarchical` 内部的 `merge_policy` 分支。
- `Strong A v1.0` 更接近一组 `hierarchical` 策略参数与验收口径，不等同于单独的新 policy 包。
- `ramp__mlane_v2` 与 `ramp__mlane_v2_mixed` 是两个不同场景目录，不应默认视为同一场景的别名。
- `Baseline_and_comparative_trials.json/html` 是较新的讨论记录，不是 `ramp` 实验脚本自动生成的最终对比结果表。

## 当前盘点边界

本轮盘点聚焦这些主题：

- 算法：上游换道、DP、混合 DP、固定/灵活合流点、FIFO、无控制。
- 场景：最小场景、多车道基础场景、mixed 标准场景、hf、stress。
- 实验：单跑、汇总、pain matrix、计划快照/不一致报告、验收文档中的典型实验。
- 缺口：命名误导、参数漂移、运行时耦合、缺失产物锚点。

## 当前新增归档层

在保持“旧系统盘点”主目标不变的前提下，本轮额外归档了一层 **设计输入提炼**，专门记录：

- 从旧 `ramp/` 里暴露出来、但必须在新仓库中重定义清楚的语义冲突。
- 已在 `forum/xiangmu_qianyi.json` 中讨论并确认、且已经足以指导 MVP 建模的约束。
- 仍未冻结、因此必须继续保留在 `OPEN-*` 队列中的下一轮问题。

这一层的使用原则是：

- 它可以解释“为什么新仓库要这样定义”。
- 它可以作为后续 `docs/design.md`、`docs/contracts.md` 的输入材料。
- 它不能替代正式设计文档本身。

当前已经补充归档的设计输入主要有：

- `fixed / flexible` 在新仓库中统一绑定 `completion anchor`，不再沿用旧 `ramp` 里容易歧义的 merge point 语义。
- MVP 的纵向分区改为绝对里程几何子区，而不是沿用旧 `Zone A/B/C` 话语体系。
- MVP 只保留 1 个 `active decision partition`，并采用 `Step 2 生成候选 + Step 3 共享验收门` 的闭环。
- `no_control` 降级为参考下界；首批 baseline 冻结为 `FIFO + fixed anchor` 与 `FIFO + flexible anchor`。
