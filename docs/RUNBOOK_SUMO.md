# 运行手册（纯 SUMO）

本文档给出“如何启动项目”的几种方式、对应目的、以及常见问题的处理方法。默认你已在仓库根目录。

## 0. 一次性环境准备

1. 安装 SUMO（确保 `sumo`/`sumo-gui` 可用，且 `SUMO_HOME` 正确指向 SUMO 的安装目录）
2. 同步 Python 依赖
```bash
uv sync
```

可选：验证最小依赖是否可导入
```bash
uv run python -c "import sumolib, traci; print('ok')"
```

## 1. 跑 CSDF（论文复现，推荐从这里开始）

### 1.1 批量跑 + 导出 CSV（推荐）

目的：
- 不依赖 GUI，适合重复实验、做参数扫、以及后处理分析。

命令（示例跑 30 秒仿真）：
```bash
PYTHONDONTWRITEBYTECODE=1 uv run python -m CSDF.batch_run --duration-s 30
```

输出（默认）：
- `CSDF/sumo_data/vehicle_trace_*.csv`
- `CSDF/sumo_data/collisions_*.csv`

常用参数：
- `--duration-s 120`：跑更久
- `--seed 1`：固定随机种子
- `--out-dir CSDF/sumo_data_run1`：输出到新目录
- `--gui`：在有显示器环境时用 GUI（一般不建议批跑用 GUI）

### 1.2 原始交互式跑法（不推荐批跑）

目的：
- 快速看“算法是否触发”、车辆行为是否如预期（更适合调试）。

```bash
uv run python CSDF/main.py
```

注意：`CSDF/main.py` 默认使用 `sumo-gui`。

## 2. 跑 Scene/scene10(Sumo)（纯 SUMO 示例）

目的：
- 看一个更简单的 TraCI 控制循环示例（速度/换道控制、碰撞采集/回放脚本在该目录也有）。

```bash
cd "Scene/scene10(Sumo)"
SUMO_GUI=0 uv run python "Scene10_sumo v2.py"
```

## 3. 运行方式对比（你在做什么）

- `uv run python ...`：在项目虚拟环境中运行脚本，依赖来自 `uv sync` 安装的包。
- `sumo` vs `sumo-gui`：
  - `sumo`：无界面，适合批跑。
  - `sumo-gui`：有界面，适合调试/演示。

## 4. 常见问题与排查

### 4.1 SUMO 报 “Unknown vehicle class ...”

原因：
- 某些 `.net.xml` 的 lane allow/disallow 列表包含 SUMO 当前版本不认识的 vClass（例如 `drone` 等）。

处理：
- `CSDF/batch_run.py` 会在运行时自动生成一个兼容版本的 `*.net.xml` 和 `*.sumocfg` 到 `CSDF/sumo_data/sumo_cfg/`，避免你修改原始文件。

### 4.2 TraCI API 不兼容（例如 moveToXY 参数名不同）

原因：
- SUMO 自带 TraCI 与 PyPI `traci`/`sumolib` 版本可能不一致；或不同 SUMO 版本的函数签名有差异。

处理建议：
- 优先使用系统 SUMO 自带的 `SUMO_HOME/tools` 里的 TraCI。

### 4.3 `uv` 缓存目录权限问题（仅在某些受限环境出现）

症状：
- `uv run ...` 报 `Failed to initialize cache at ~/.cache/uv ... Permission denied`

处理：
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ...
```

