from dataclasses import dataclass
from typing import Dict, Optional
import traci
import math
from CSDF.core.DataTypes import (ElementID, Decision, RiskLevel, TrajectoryPoint, TrafficElementBase, CAVElementSimple,
                       CAVDecisionInfo, BehaviorPlanningOutput, TrajectoryPlanningOutput)
from CSDF.core.CoordinateTransform import CartesianFrenetConverter

@dataclass
class TrajectoryExecutionState:
    """轨迹执行状态"""
    current_index: int = 0  # 当前执行到的轨迹点索引
    completed: bool = False  # 是否已完成轨迹执行


class TrajectoryExecutor:
    """SUMO仿真轨迹执行器"""

    def __init__(self, position_tolerance: float = 0.5):
        """
        初始化轨迹执行器

        Args:
            position_tolerance: 位置容差（米），用于判断是否到达目标点
        """
        self.position_tolerance = position_tolerance
        # 记录每个CAV的轨迹执行状态
        self.execution_states: Dict[str, TrajectoryExecutionState] = {}

    def execute(self, cav_dict: Dict[str, CAVElementSimple]) -> None:
        """
        执行轨迹控制

        Args:
            cav_dict: CAV字典，key为ElementID，value为CAVElementSimple对象
        """
        for element_id, cav in cav_dict.items():
            # 只处理有规划轨迹的CAV
            if not cav.isPlanned or cav.planned_trajectory is None or len(cav.planned_trajectory) == 0:
                # 清理已完成或无轨迹的状态记录
                if element_id in self.execution_states:
                    del self.execution_states[element_id]
                continue

            # 初始化执行状态
            if element_id not in self.execution_states:
                self.execution_states[element_id] = TrajectoryExecutionState()

            state = self.execution_states[element_id]

            # 检查是否已完成轨迹
            if state.current_index >= len(cav.planned_trajectory):
                self._complete_trajectory(element_id, cav)
                continue

            # 获取当前目标轨迹点
            target_point = cav.planned_trajectory[state.current_index]

            # 检查是否到达当前目标点
            if self._has_reached_target(cav, target_point):
                state.current_index += 1

                # 检查是否完成整条轨迹
                if state.current_index >= len(cav.planned_trajectory):
                    self._complete_trajectory(element_id, cav)
                    continue

                # 更新到下一个目标点
                target_point = cav.planned_trajectory[state.current_index]

            # 执行轨迹控制
            self._execute_trajectory_point(element_id, target_point)

    def _has_reached_target(self, cav: CAVElementSimple, target_point) -> bool:
        """
        判断是否到达目标点

        Args:
            cav: CAV对象
            target_point: 目标轨迹点

        Returns:
            是否到达目标点
        """
        dx = cav.location[0] - target_point.location[0]
        dy = cav.location[1] - target_point.location[1]
        distance = math.sqrt(dx * dx + dy * dy)
        return distance < self.position_tolerance

    def _execute_trajectory_point(self, element_id: str, target_point) -> None:
        """
        执行单个轨迹点的控制

        Args:
            element_id: 车辆ID
            target_point: 目标轨迹点
        """
        try:
            # 使用moveToXY控制位置和朝向
            # SUMO的angle定义：北为0度，顺时针递增
            traci.vehicle.moveToXY(
                vehID=element_id,
                edgeID="",  # 空字符串表示自动选择edge
                laneIndex=-1,  # -1表示自动选择lane
                x=target_point.location[0],
                y=target_point.location[1],
                angle=target_point.heading,  # 假设TrajectoryPoint有heading属性
                keepRoute=2  # 2表示保持当前路线
            )

            # 使用setSpeed控制速度
            if hasattr(target_point, 'velocity'):
                traci.vehicle.setSpeed(element_id, target_point.velocity)

        except traci.exceptions.TraCIException as e:
            print(f"执行轨迹控制失败 - 车辆ID: {element_id}, 错误: {e}")

    def _complete_trajectory(self, element_id: str, cav: CAVElementSimple) -> None:
        """
        完成轨迹执行后的处理

        Args:
            element_id: 车辆ID
            cav: CAV对象
        """
        # 设置规划状态为False
        cav.isPlanned = False
        # 清空规划轨迹
        cav.planned_trajectory = None
        # 删除执行状态记录
        if element_id in self.execution_states:
            del self.execution_states[element_id]

        print(f"车辆 {element_id} 已完成轨迹执行")

    def get_execution_progress(self, element_id: str) -> Optional[tuple[int, int]]:
        """
        获取指定车辆的轨迹执行进度

        Args:
            element_id: 车辆ID

        Returns:
            (当前索引, 总轨迹点数) 或 None（如果车辆不在执行中）
        """
        if element_id in self.execution_states:
            return (self.execution_states[element_id].current_index,
                    len(self.execution_states[element_id]))
        return None

    def reset(self) -> None:
        """重置执行器状态"""
        self.execution_states.clear()


# 使用示例
if __name__ == "__main__":
    # 初始化执行器
    executor = TrajectoryExecutor(position_tolerance=0.5)

    # 在仿真循环中调用
    # while traci.simulation.getMinExpectedNumber() > 0:
    #     # 获取CAV字典（从你的数据结构中）
    #     cav_dict: Dict[str, CAVElementSimple] = get_cav_dict()
    #
    #     # 执行轨迹控制
    #     executor.execute(cav_dict)
    #
    #     # 推进仿真
    #     traci.simulationStep()