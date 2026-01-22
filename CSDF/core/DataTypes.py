from typing import TypeAlias,Optional
from enum import Enum
import numpy as np
from dataclasses import dataclass

ElementID: TypeAlias = str
Decision: TypeAlias = int               #决策的格子

class RiskLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class TrajectoryPoint:       # 笛卡尔坐标系
    """轨迹点详细信息"""
    timestamp: float
    location: tuple[float, float]
    heading: float
    velocity: float          # 速度大小
    acceleration: float      # 加速度大小

@dataclass
class TrafficElementBase:               # 笛卡尔坐标系
    element_id: ElementID               # 要素ID（str）
    location: tuple[float, float]       # 位置 (x, y)
    heading: float               # angle 注意：sumo中，y轴正方向为0度，顺时针为递增，heading是与y轴正方向角度
    velocity: float
    acceleration: float
    edge_id: str
    lane_id: str

@dataclass
class CAVElementSimple(TrafficElementBase):

    isPlanned: bool
    risk_level: RiskLevel                                           # 风险等级（暂时先根据TTC检测）
    communication_range: float = 100                              # 通信范围（米）
    planned_trajectory: Optional[list[TrajectoryPoint]] = None      # 规划的轨迹


@dataclass
class CAVDecisionInfo:
    potential_decision: list[Decision]                              # 可行的格子（根据静态障碍物和交通规则排除）
    related_cav: list[ElementID]                                    # 相关cav列表，不含当前cav
    risk_level: RiskLevel                                           # 风险等级（暂时先根据TTC检测）
    decision: Optional[Decision] = None                             # 决策结果的格子
    target_point: Optional[tuple[float, float]] = None              # 由决策结果格子得到的目标点 (frenet坐标系，（s,d）)

@dataclass
class BehaviorPlanningOutput:

    timestamp: float                                            # 时间戳
    CAV_elements: dict[ElementID, CAVDecisionInfo]             # CAV决策


@dataclass
class TrajectoryPlanningOutput:

    timestamp: float                                             # 时间戳
    CAV_elements: dict[ElementID, list[TrajectoryPoint]]         # 规划的CAV轨迹，笛卡尔坐标系
    planning_horizon: float = 5.0  # 规划时域（秒）