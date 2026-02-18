# Sumo-Carla-simulation-for-Vehicle-Road-Cloud-Integeration

自主式交通系统要素集群规划器

## 项目介绍

<details>
<summary>技术栈</summary>

- Python 3.12
- CARLA (模拟环境, Python API 需要按平台单独安装)
- SUMO (交通仿真、控制)
- 依赖管理: uv
- git
- 凸优化与最优控制
- 计算几何
- 常见的横纵向控制算法

</details>

## 环境配置

## 文档

- 纯 SUMO 路线：`docs/OVERVIEW_SUMO.md`、`docs/RUNBOOK_SUMO.md`、`docs/CSDF.md`
- 过程记录：`docs/WORKLOG_2026-02-17.md`

### 安装 uv

如果尚未安装 uv 请参考[官方安装指南](https://github.com/astral-sh/uv)

如果觉得安装有点麻烦可以到 uv 的 Release 页面下载可执行文件, 放到项目根目录下直接执行即可.

```bash
./uv sync  # 根据使用的 shell, 可能需要指定相对路径
```

### 安装依赖

```bash
# 同步项目依赖
uv sync

# 同步开发依赖
uv sync --dev
```

> 说明: CARLA 的 Python API 不随 `uv sync` 自动安装, 因为它通常需要从对应 CARLA 发行版里拿到匹配平台/版本的 wheel 并手动安装。

**注意**: 如果需要使用 tuna 镜像请添加 `--default-index` 参数, 例如:

```bash
uv sync --default-index https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/
```

```bash
安装项目需要的库：
uv add xxx

uv add xxx -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 各个场景

Sumo中地图为.net.xml文件， .rou.xml文件为交通流文件, 其中定义了车流的路线和密度等


在Scene文件夹中，存放了各个场景地图

    高速公路：场景1，2，4，5（都一样的），比如在scene1文件夹下的scene_1_data_rou文件夹下，存放了地图文件.net.xml和交通流文件.rou.xml
    
    十字路口：场景10
    
    匝道：场景8
    
    隧道：场景3
    
    窄桥：场景13


在scene10（Sumo）中是一个纯Sumo的构造场景事故代码，可参考其中的README。


其他的场景文件夹是SUMO-CARLA的联合仿真，

## 多车规划部分代码，在multi_vehicle/

这部分代码是在CARLA-SUMO联合仿真环境下

部署在高速公路场景下，手动构造了预警决策模块的输出，规划算法的具体输入数据字段在multi_vehicle/trajectory_plannner_multi.py中

涉及到Cartesian 到 frenet 坐标系的相互转换 参考multi_vehicle/CoordinateTransform.py

规划算法：目前采样的是集中式规划三辆车，参考multi_vehicle/Solver_multi.py

代码只规划一次输出一系列轨迹点，通过轨迹执行器按位置移动车辆，参考multi_vehicle/trajectory_executor.py

## TODO

1. 先不用Carla，纯sumo中。
2. 实时决策和规划，而非离线计算离线执行的
3. 重规划功能（针对已经规划好轨迹的车辆）
4. 算法的求解效率和扩展性
5. 当前代码中只涉及规划部分，决策信息是手动输入的，决策方法需要自行实现
