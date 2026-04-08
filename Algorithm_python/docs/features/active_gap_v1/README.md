<!--
Derived-From: /home/liangyunxuan/src/.cursor/templates/docs/feature-readme.base.md
Scope: repo-instance
Drift-Allowed: true
Backport: manual
-->

# active_gap_v1 — 主算法任务索引

> 最后更新：`2026-04-08T16:00:00+08:00`
>
> 这是当前主算法的 feature 施工包，不是占位目录。
> 它的作用是把顶层 SSOT 翻译成一组**可直接驱动实现/重构**的任务文档。
>
> **Mainline Notice**
> 1. 当前主算法主线是 `TCG=(p,m,s)` 三车可控的主动造 gap。
> 2. 当前 tick 没 merge 解时，优先找 certified coordination slice，而不是默认等待。
> 3. `docs/features/first_wave_mvp/` 只保留旧 baseline / archive 角色，不再代表当前主线。

## 任务列表

| ID | 任务 | 依赖 | 产出 |
|----|------|------|------|
| `T1` | `tcg_and_snapshot` | 无 | `src/active_gap_v1/` 最小骨架、共享类型、配置、`CoordinationSnapshot`、`TCG` 识别与基础测试 |
| `T2` | `merge_target_planner` | `T1` | `predictor.py`、`merge_target_planner.py`、merge target 搜索、排序、失败分类与测试 |
| `T3` | `tcg_quintic_and_certificate` | `T1`、`T2` | 三车 quintic、`SafetyCertificate`、`g_up/g_pm/g_ms/g_sf`、闭区间验证与测试 |
| `T4` | `execution_and_state_machine` | `T1`、`T2`、`T3` | merge/coordination slice、状态机、`SAFE_WAIT` / `FAIL_SAFE_STOP` 闭环与测试 |
| `T5` | `metrics_and_trace` | `T1`、`T2`、`T3`、`T4` | `metrics.py`、trace schema、summary schema、实验 README 与测试 |
| `T6` | `micro_scenarios_and_regression` | `T1`、`T2`、`T3`、`T4`、`T5` | A0-A1 首版微场景入口、blocking gate、回归门禁与正反例测试（A2/A3 后续扩展） |

## Scout Findings

### Verified

- `docs/design.md`、`docs/contracts.md`、`docs/formulas.md`、`docs/derivations.md` 已经切到 `TCG / coordination slice / A层只看pms` 新主线。
- `docs/features/first_wave_mvp/README.md` 已明确标成 archive / baseline，不再承载当前主线。
- 当前 repo 已具备 `src/`、`tests/`、`experiments/` 顶层目录，能够承接 `src/active_gap_v1/` 的实现落点。

### Discovered

- 当前新主算法不是在旧 `step2_fifo/gate/rollout` 上打补丁，而是需要“保留外围壳层、重建核心主链”。
- `TCG=(p,m,s)` 是当前最小受控集；`u/f` 只作为可选边界，不应强行进入 A 层首版。
- 当前 tick 的执行分支已经不再是“有解就执行、没解就等”，而是“merge slice -> coordination slice -> safe_wait -> fail-safe”。
- `active_gap_v1` 的任务拆分必须同时支持“新命名空间生成实现”和“参考旧外壳做迁移重构”两种落地方式。
- `planned/actual`、trace 与证书最紧约束字段，需要在 `T5` 里一次性定义清楚，否则后续 A 层很难解释。

### Gaps

- 当前 `active_gap_v1` 目录虽然已经建立，但尚未落代码，所有任务都必须把白名单、黑名单、依赖输入和测试出口写到可直接执行的粒度。
- 旧 `first_wave_mvp` 的任务文档成熟度明显更高；如果不补齐 `active_gap_v1` 的上下文、验收与边界，新 task 无法直接驱动实现。
- 顶层 SSOT 已经明确 `u/f` 为可选边界，但具体在代码里如何“缺省为空”并保持证书逻辑不分叉，还需要在 `T1-T3` 内写成明确规则。

## Work Packages

### WP-1: 固定 TCG 底座与 snapshot（complexity: H, subagent: manual）

- Depends on: none
- Actions:
  1. 创建 `src/active_gap_v1/`、`tests/active_gap_v1/`、`experiments/active_gap_v1/` 最小骨架。
  2. 将 `docs/contracts.md` 的共享枚举/dataclass 与 `docs/formulas.md` 的默认参数翻译到 `types.py` / `config.py`。
  3. 实现 `build_coordination_snapshot()` 与 `identify_tcg()`，并明确 `u/f` 缺省为空的语义。
- Done when: `T1` 白名单文件存在，后续 task 可直接 import `CoordinationSnapshot` 与 `TCG`。

### WP-2: 实现 merge target 规划（complexity: H, subagent: manual）

- Depends on: WP-1
- Actions:
  1. 实现边界车预测与 `fixed/flexible` 的统一 merge target 搜索。
  2. 固定 `Δ_open / Δ_coop / Δ_delay / ρ_min` 的计算与字典序排序。
  3. 固化稳定排序、失败分类与 target 枚举确定性。
- Done when: 同一输入重复运行时，merge target 列表与排序可重复，`A1` 可直接比较 `fixed/flexible`。

### WP-3: 实现三车 quintic 与证书（complexity: H, subagent: manual）

- Depends on: WP-2
- Actions:
  1. 对 `p/m/s` 求三车 quintic。
  2. 实现 `g_up / g_pm / g_ms / g_sf` 与闭区间验证。
  3. 明确 `u/f` 缺省时哪些约束自动跳过、哪些约束必须始终检查。
- Done when: merge branch 可以产生 certified merge slice，且证书可解释最紧约束与失败原因。

### WP-4: 实现执行主链与状态机（complexity: H, subagent: manual）

- Depends on: WP-3
- Actions:
  1. 实现 merge slice 分支。
  2. 实现 coordination slice 分支。
  3. 明确 `SAFE_WAIT / FAIL_SAFE_STOP / ABORTED` 触发条件与原因码。
- Done when: 当前 tick 无 merge 解时，系统优先走 coordination slice，不会直接默认等待。

### WP-5: 建立指标与 trace（complexity: M, subagent: manual）

- Depends on: WP-4
- Actions:
  1. 重新定义 `planned/actual`。
  2. 固定 trace schema、summary schema、slice 类型区分与证书字段。
  3. 写清实验 README、输入参数和输出格式。
- Done when: 单次运行结果足以支撑 A 层诊断，不需要二次推断隐藏状态。

### WP-6: 建立 A 层门禁与回归（complexity: H, subagent: manual）

- Depends on: WP-5
- Actions:
  1. 冻结 A0-A1，首版只看 `p/m/s`。
  2. 建立 blocking gate 与正反例回归。
  3. 为后续引入 `u/f` 的边界应力测试保留扩展位。
  4. 记录 A2/A3 的前置条件（c-m 安全约束、可达性论证）作为后续扩展准入。
- Done when: A0-A1 能直接判断主算法是否具备主动造 gap 能力，且失败原因可定位。

## 依赖关系图

当前不建议并行切多个核心实现 task，推荐按以下顺序串行推进：

```text
T1_tcg_and_snapshot
  -> T2_merge_target_planner
    -> T3_tcg_quintic_and_certificate
      -> T4_execution_and_state_machine
        -> T5_metrics_and_trace
          -> T6_micro_scenarios_and_regression
```

这条链路对应正式主闭环：

`共享契约 -> TCG 识别 -> merge target -> 三车轨迹/证书 -> merge/coordination 分支 -> metrics/trace -> A层门禁`

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

## 并行开发分组

| 阶段 | 可并行任务 | 最大并行 agent 数 | 说明 |
|------|-----------|------------------|------|
| `S1` | `T1` | `1` | 先锁定共享对象、`TCG` 与 snapshot 口径 |
| `S2` | `T2` | `1` | merge target 搜索必须建立在 `T1` 的稳定对象之上 |
| `S3` | `T3` | `1` | 证书逻辑必须消费 `T2` 已稳定的 target 契约 |
| `S4` | `T4` | `1` | 执行状态机要建立在 `T3` 已稳定的证书与 slice 语义之上 |
| `S5` | `T5` | `1` | trace / metrics 依赖主链已跑通 |
| `S6` | `T6` | `1` | A 层门禁必须建立在 `T1-T5` 产物之上 |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `TCG`、`u/f` 与 `active ego` 的语义在 `T1/T2` 之间不一致，导致后续模块对象漂移 | High | 在 `T1/T2` 中同时固定白名单、输入输出对象与缺省语义 |
| 当前 tick 无 merge 解时，`T4` 实现回旧逻辑，直接默认等待 | High | 在 `T4` 文档里把 coordination branch 单独作为硬验收项 |
| `u/f` 太早进入 A 层场景，导致算法能力判断被边界效应污染 | High | 在 `T6` 中硬性冻结：A0-A1 首版只看 `p/m/s` |
| A2 的 `c-m` 安全约束和 A3 的可达性论证未补齐就进入实现 | High | 首版只含 A0+A1，A2/A3 作为后续扩展 |
| 三车 quintic 与证书字段定义不稳，导致 `T5/T6` 无法解释失败原因 | High | `T3` 必须产出最紧约束、失败分类和证书边界字段 |
| 直接拿现有短 task 去生成代码，会产生“能写文件但无法闭环”的假进度 | High | 先把当前目录文档补齐到实现级，再进入代码层 |

## 代码预算

预算是膨胀预警线，不是鼓励一次性写满。

| 指标 | 上限 |
|------|------|
| 新增核心模块数 | `<= 12` |
| 单文件最大行数 | `<= 350` |
| 新增配置项 | 只允许顶层 SSOT 已冻结字段 |
| A 层首版场景数 | 首版固定为 `2`（A0+A1），A2/A3 待前置条件就绪后扩展 |
