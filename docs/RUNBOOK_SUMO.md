# 运行手册（RAMP / 纯 SUMO）

本文档只保证 `ramp/` 路线是最新可用的（`no_control / fifo / dp`）。其它目录（CSDF、Scene 等）不作为当前主线维护目标。

默认你在仓库根目录：`/home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration`。

## 0. 一次性环境准备

1. 安装 SUMO（确保 `sumo`/`sumo-gui` 可用；建议 `SUMO_HOME` 正确）
2. 安装/可用 `uv`
3. 同步 Python 依赖
```bash
uv sync --dev
```

可选：验证最小依赖是否可导入
```bash
uv run python -c "import sumolib, traci; print('ok')"
```

## 1. 跑 RAMP（三种 policy）

输出默认写到：`output/<scenario>/<policy>/`（同 policy 覆盖；不同 policy 不覆盖）。

### 1.1 Headless（推荐回归用）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

### 1.2 GUI（用于直观看效果/定点排查）

```bash
cd /home/liangyunxuan/src/Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy no_control --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy fifo --fifo-gap-s 1.5 --duration-s 120 --step-length 0.1 --seed 1
SUMO_GUI=1 uv run python -m ramp.experiments.run --scenario ramp_min_v1 --policy dp --delta-1-s 1.5 --delta-2-s 2.0 --dp-replan-interval-s 0.5 --duration-s 120 --step-length 0.1 --seed 1
```

注意：
- GUI 调试时如果你手动关闭 `sumo-gui` 窗口，脚本可能会异常退出，导致 `metrics.json/config.json` 等“仿真结束时写入”的文件缺失。
- 需要完整输出时，建议让仿真按 `--duration-s` 自然跑完。

## 2. 必跑回归与约束检查（不要手抄）

`ramp/` 的必跑回归、`plans.csv` 约束检查命令、以及历史关键结果统一维护在：
- `docs/RAMP_VALIDATION.md`

## 3. 常见问题与排查

### 3.1 TraCI API 不兼容

原因：
- SUMO 自带 TraCI 与 PyPI `traci`/`sumolib` 版本可能不一致；或不同 SUMO 版本的函数签名有差异。

处理建议：
- 优先使用系统 SUMO 自带的 `SUMO_HOME/tools` 里的 TraCI。

### 3.2 `uv` 缓存目录权限问题（某些受限环境）

症状：
- `uv run ...` 报 `Failed to initialize cache at ~/.cache/uv ... Permission denied`

处理：
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ...
```

## 4. 其它目录（非主线）

如果你确实需要跑：
- CSDF：见 `docs/CSDF.md`
