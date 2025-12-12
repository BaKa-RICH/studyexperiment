from __future__ import annotations
import math
from loguru import logger

from enum import Enum

import CoordinateTransform
import Solver_multi

from dataclasses import dataclass

import traci
import sumolib
import numpy as np
from numpy import dtype, ndarray
from typing import TypeAlias

# 定义类型别名
ElementID: TypeAlias = str

#TrajectoryArray 每个元素只包含[x,y,heading，timestamp]
TrajectoryArray: TypeAlias = ndarray[tuple[int, int], dtype[np.float64]]

# 定义风险等级枚举
class RiskLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class Decision(Enum):
    LEFT_LANE_CHANGE = "left_lane_change"
    RIGHT_LANE_CHANGE = "right_lane_change"
    LANE_KEEPING = "lane_keeping"

@dataclass
class ForewarnOutput:
    timestamp: float                    # 时间戳
    all_elements: dict[ElementID, TrafficElementSimple]  # 所有交通要素
    risk_elements: list[RiskElement]    # 风险要素列表

@dataclass
class TrafficElementSimple:   # 数据不足不能用完整的 TrafficElement, 后面三个属性是根据计算得出
    element_id: ElementID               # 要素ID（str）
    location: tuple[float, float]       # 位置 (x, y)
    heading: tuple[float]               # angle 注意：sumo中，y轴正方向为0度，顺时针为递增，heading是与y轴正方向角度
    velocity: tuple[float, float]       # 速度 (vx, vy)
    acceleration: tuple[float, float]   # 加速度 (ax, ay)
    edge_id: str
    lane_id: str

@dataclass
class RiskElement:
    element_id: ElementID                   # 要素ID（str）
    risk_level: RiskLevel                   # 风险等级
    related_risk_elements: list[ElementID]  # 相关风险要素列表，不含当前ElmentID
    history_trajectory: TrajectoryArray     # 历史轨迹
    predicted_trajectory: TrajectoryArray   # 预测轨迹 轨迹点按0.1s给出
    planned_trajectory: TrajectoryArray     # 规划轨迹：按决策得出的安全轨迹（粗略的）
    decision: Decision    # 决策：高风险车辆的要换的目标车道, 向左向右换道或者减速

class MultiVehicleTrajectoryPlanner():
    """基于Frenet坐标系的多车协同轨迹规划器"""
    
    def __init__(self):
        self._trajectories = {}
    
    def plan_trajectories(self, planning_input: ForewarnOutput) -> dict[ElementID, TrajectoryArray]:
        """
        为多辆车进行协同轨迹规划
        
        Args:
            planning_input: ForewarnOutput类型的输入数据
            
        Returns:
            dict[ElementID, TrajectoryArray]: 规划的轨迹字典
        """
        # 获取输入数据
        timestamp = planning_input.timestamp
        all_elements = planning_input.all_elements
        risk_elements = planning_input.risk_elements
        transformers = {}
        logger.info(f"开始多车协同轨迹规划，时间戳: {timestamp}")
        
        # 筛选需要规划的车辆（高风险车辆）只能有一个高风险
        planning_vehicles = []
        for risk_element in risk_elements:
            if risk_element.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                planning_vehicles.append(risk_element.element_id)
                decision = risk_element.decision
                reference_path = self._get_reference_path(all_elements.get(risk_element.element_id), decision)
                transformer = CoordinateTransform.CartesianFrenetConverter(reference_path)
                transformers[risk_element.element_id] = transformer
                for veh in risk_element.related_risk_elements:
                    planning_vehicles.append(veh)
        
        if not planning_vehicles:
            logger.info("没有需要规划的高风险车辆")
            return {}
        
        logger.info(f"需要协同规划的车辆: {planning_vehicles}")
        
        # 准备多车规划数据
        vehicle_states = {}
        vehicle_targets = {}
        vehicle_attributes = {}
        #transformers = {}
        
        for vehicle_id in planning_vehicles:
            # 获取车辆状态
            ego_element = all_elements.get(vehicle_id)
            if not ego_element:
                logger.warning(f"未找到车辆 {vehicle_id} 的状态信息")
                continue
            
            # 获取决策信息
            veh_decision = None
            for risk_element in risk_elements:
                 if risk_element.element_id == vehicle_id:
                     veh_decision = risk_element.decision
                     break
            #
            if not veh_decision:
                 logger.warning(f"车辆 {vehicle_id} 无决策信息")
                 continue
            #
            # # 根据决策确定参考路径
            # reference_path = self._get_reference_path(ego_element, decision)
            # if not reference_path:
            #     logger.warning(f"无法获取车辆 {vehicle_id} 的参考路径")
            #     continue

            # # 创建坐标转换器
            # transformer = CoordinateTransform.CartesianFrenetConverter(reference_path)
            # transformers[vehicle_id] = transformer
            
            # 转换当前状态到Frenet坐标系
            s_start, d_start = transformer.cartesian_to_frenet(
                ego_element.location[0], ego_element.location[1]
            )
            
            # 计算速度分量
            vx = ego_element.velocity[0]
            vy = ego_element.velocity[1]
            vs_start, vd_start = transformer.velocity_cartesian_to_frenet(
                ego_element.location[0], ego_element.location[1], vx, vy
            )
            
            # 计算加速度分量
            ax = ego_element.acceleration[0]
            ay = ego_element.acceleration[1]
            as_start, ad_start = transformer.acceleration_cartesian_to_frenet(
                ego_element.location[0], ego_element.location[1], vx, vy, ax, ay
            )
            
            # 设置目标状态
            if veh_decision in [Decision.LEFT_LANE_CHANGE, Decision.RIGHT_LANE_CHANGE]:
                d_end = 0.0  # 变道到目标车道中心
                s_end = s_start + 50.0  # 向前规划50米
            else:  # 保持车道
                d_end = d_start  # 保持当前横向位置
                s_end = s_start + 30.0  # 向前规划30米
            
            # 存储车辆状态和目标
            vehicle_states[vehicle_id] = {
                's_start': s_start, 'd_start': d_start,
                'vs_start': vs_start, 'vd_start': vd_start,
                'as_start': as_start, 'ad_start': ad_start
            }
            
            vehicle_targets[vehicle_id] = {
                's_end': s_end, 'd_end': d_end
            }
            
            vehicle_attributes[vehicle_id] = self._create_ego_attribute()
        
        # 如果没有有效的规划车辆，返回空结果
        if not vehicle_states:
            logger.warning("没有有效的车辆状态数据")
            return {}
        
        # 获取车道宽度（使用第一辆车的车道宽度）
        try:
            first_vehicle_id = list(planning_vehicles)[0]
            first_element = all_elements[first_vehicle_id]
            lane_width = traci.lane.getWidth(first_element.lane_id)
        except:
            lane_width = 3.5  # 默认车道宽度
        
        # 创建多车协同规划器
        planner = Solver_multi.MultiVehicleFrenetPlanner(list(vehicle_states.keys()))
        
        # 设置规划问题
        planner.set_problem(
            vehicle_states, vehicle_targets, vehicle_attributes,
            lane_width, transformer
        )
        
        # 求解轨迹
        all_waypoints = planner.solve_problem(transformer)
        
        if all_waypoints:
            # 转换为TrajectoryArray格式
            planned_trajectories = {}
            for vehicle_id, waypoints in all_waypoints.items():
                trajectory_array = self._convert_to_trajectory_array(waypoints, timestamp)
                planned_trajectories[vehicle_id] = trajectory_array
                logger.debug(f'为车辆 {vehicle_id} 规划了轨迹，包含 {len(waypoints)} 个点')
            
            logger.info(f'成功协同规划了 {len(planned_trajectories)} 条轨迹')
            return planned_trajectories
        else:
            logger.warning('多车协同轨迹规划失败')
            return {}
    
    def _get_reference_path(self, ego_element: TrafficElementSimple, maneuver_type: Decision):
        """根据决策获取参考路径"""
        try:
            current_lane_id = ego_element.lane_id
            current_edge_id = ego_element.edge_id
            
            if maneuver_type == Decision.LANE_KEEPING:
                # 保持车道时使用当前车道
                return traci.lane.getShape(current_lane_id)
            elif maneuver_type == Decision.LEFT_LANE_CHANGE:
                # 向左变道
                lane_parts = current_lane_id.split('_')
                if len(lane_parts) > 1:
                    lane_index = int(lane_parts[-1])
                    target_lane_id = f"{current_edge_id}_{lane_index + 1}"
                else:
                    target_lane_id = f"{current_lane_id}_1"
                return traci.lane.getShape(target_lane_id)
            elif maneuver_type == Decision.RIGHT_LANE_CHANGE:
                # 向右变道
                lane_parts = current_lane_id.split('_')
                if len(lane_parts) > 1:
                    lane_index = int(lane_parts[-1])
                    if lane_index > 0:
                        target_lane_id = f"{current_edge_id}_{lane_index - 1}"
                    else:
                        return traci.lane.getShape(current_lane_id)  # 无法向右变道
                else:
                    return traci.lane.getShape(current_lane_id)
                return traci.lane.getShape(target_lane_id)
            else:
                return traci.lane.getShape(current_lane_id)
        except Exception as e:
            logger.error(f"获取参考路径失败: {e}")
            return None
    
    def _extract_relative_data(self, relative_element_ids, all_elements, risk_elements):
        """提取相关车辆的预测和历史轨迹数据"""
        relative_pred_traj = {}
        relative_history_traj = {}
        
        for element_id in relative_element_ids:
            # 查找对应的风险要素
            for risk_element in risk_elements:
                if risk_element.element_id == element_id:
                    relative_pred_traj[element_id] = risk_element.predicted_trajectory
                    relative_history_traj[element_id] = risk_element.history_trajectory
                    break
        
        return relative_pred_traj, relative_history_traj
    
    def _create_ego_attribute(self):
        """创建简化的车辆属性"""
        class EgoAttribute:
            def __init__(self):
                self.max_vel = 30.0  # 最大速度 m/s
                self.max_acc = 3.0   # 最大加速度 m/s²
                self.width = 1.7924479246139526     # 车辆宽度 m
                self.length = 3.7186214923858643    # 车辆长度 m
        
        return EgoAttribute()
    
    def _convert_to_trajectory_array(self, waypoints, base_timestamp) -> TrajectoryArray:
        """将waypoints转换为TrajectoryArray格式"""
        # TrajectoryArray 是 ndarray[tuple[int, int], dtype[np.float64]]
        # 创建二维数组，每行代表一个轨迹点，列包含 [x, y, heading]
        trajectory_data = []
        
        for waypoint in waypoints:

            x, y = waypoint[0], waypoint[1]
            heading = waypoint[2]
            timestamp = base_timestamp + waypoint[3]

            # 创建轨迹点数据 [x, y, heading]
            point_data = [x, y, heading, timestamp]
            trajectory_data.append(point_data)
        
        # 转换为numpy数组
        return np.array(trajectory_data, dtype=np.float64)