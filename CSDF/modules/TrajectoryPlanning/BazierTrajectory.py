import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math
from CSDF.core.DataTypes import (ElementID, Decision, RiskLevel, TrajectoryPoint, TrafficElementBase, CAVElementSimple,
                       CAVDecisionInfo, BehaviorPlanningOutput, TrajectoryPlanningOutput)
from CSDF.core.CoordinateTransform import CartesianFrenetConverter



class TrajectoryGenerator:
    """基于三阶贝塞尔曲线的轨迹生成器"""

    def __init__(self,
                 frenet_to_cartesian_converter,
                 delta_t: float = 5.0,
                 dt: float = 0.05):
        """
        初始化轨迹生成器

        Args:
            frenet_to_cartesian_converter: Frenet到笛卡尔坐标系的转换器
            delta_t: 规划时域（秒），默认5.0秒
            dt: 时间间隔（秒），默认0.05秒
        """
        self.converter = frenet_to_cartesian_converter
        self.delta_t = delta_t
        self.dt = dt
        self.num_points = int(delta_t / dt) + 1  # 101个点

    def bezier_curve_3rd_order(self,
                               control_points: List[Tuple[float, float]],
                               num_samples: int = 101) -> np.ndarray:
        """
        生成三阶贝塞尔曲线

        Args:
            control_points: 4个控制点 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
            num_samples: 采样点数量

        Returns:
            采样点数组，形状为 (num_samples, 2)
        """
        # 确保有4个控制点
        assert len(control_points) == 4, "三阶贝塞尔曲线需要4个控制点"

        # 转换为numpy数组
        P = np.array(control_points)  # shape: (4, 2)

        # 生成参数tau的值，从0到1
        tau = np.linspace(0, 1, num_samples)

        # 计算贝塞尔曲线的坐标
        # 使用公式44中的贝塞尔曲线方程
        curves = np.zeros((num_samples, 2))

        for i in range(num_samples):
            t = tau[i]
            # 三阶贝塞尔曲线的基函数
            B = np.array([
                (1 - t) ** 3,  # B_0^3(t)
                3 * (1 - t) ** 2 * t,  # B_1^3(t)
                3 * (1 - t) * t ** 2,  # B_2^3(t)
                t ** 3  # B_3^3(t)
            ])

            # 计算该点的坐标
            curves[i] = np.dot(B, P)

        return curves

    def generate_control_points(self,
                                start_s: float,
                                start_d: float,
                                target_s: float,
                                target_d: float,
                                region_length: float) -> List[Tuple[float, float]]:
        """
        根据公式45生成4个控制点

        Args:
            start_s: 起始点纵向距离
            start_d: 起始点横向距离
            target_s: 目标点纵向距离
            target_d: 目标点横向距离
            region_length: 区域长度 l

        Returns:
            4个控制点列表
        """
        # 根据公式45生成控制点
        control_points = [
            (start_s, start_d),  # P1
            (start_s + region_length / 4, start_d),  # P2
            (target_s - region_length / 4, target_d),  # P3
            (target_s, target_d)  # P4
        ]

        return control_points

    def calculate_velocity_acceleration(self,
                                        trajectory: np.ndarray,
                                        dt: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        计算轨迹点的速度和加速度

        Args:
            trajectory: 轨迹点数组，形状为 (n, 2)
            dt: 时间间隔

        Returns:
            速度数组和加速度数组
        """
        n = len(trajectory)
        velocities = np.zeros(n)
        accelerations = np.zeros(n)

        # 计算速度（使用中心差分，边界使用前向/后向差分）
        for i in range(n):
            if i == 0:
                # 前向差分
                dx = trajectory[i + 1] - trajectory[i]
                velocities[i] = np.linalg.norm(dx) / dt
            elif i == n - 1:
                # 后向差分
                dx = trajectory[i] - trajectory[i - 1]
                velocities[i] = np.linalg.norm(dx) / dt
            else:
                # 中心差分
                dx = trajectory[i + 1] - trajectory[i - 1]
                velocities[i] = np.linalg.norm(dx) / (2 * dt)

        # 计算加速度
        for i in range(n):
            if i == 0:
                accelerations[i] = (velocities[i + 1] - velocities[i]) / dt
            elif i == n - 1:
                accelerations[i] = (velocities[i] - velocities[i - 1]) / dt
            else:
                accelerations[i] = (velocities[i + 1] - velocities[i - 1]) / (2 * dt)

        return velocities, accelerations

    def calculate_heading(self, trajectory: np.ndarray) -> np.ndarray:
        """
        计算轨迹点的航向角

        Args:
            trajectory: Cartesian轨迹点数组xy，形状为 (n, 2)

        Returns:
            航向角数组,SUMO坐标系的角度
        """
        n = len(trajectory)
        headings = np.zeros(n)

        for i in range(n):
            if i < n - 1:
                dx = trajectory[i + 1, 0] - trajectory[i, 0]
                dy = trajectory[i + 1, 1] - trajectory[i, 1]
                headings[i] = math.atan2(dy, dx)
                headings[i] = math.degrees(headings[i])
                headings[i] = 90 - headings[i]
            else:
                # 最后一个点使用前一个点的航向
                headings[i] = headings[i - 1]

        return headings

    def generate_trajectory(self,
                            cav_id: str,
                            current_s: float,
                            current_d: float,
                            target_s: float,
                            target_d: float,
                            base_timestamp: float) -> List[TrajectoryPoint]:
        """
        为单个CAV生成轨迹

        Args:
            cav_id: CAV标识
            current_s: 当前纵向距离
            current_d: 当前横向距离
            target_s: 目标纵向距离
            target_d: 目标横向距离
            base_timestamp: 基准时间戳

        Returns:
            轨迹点列表
        """
        # 计算区域长度
        region_length = abs(target_s - current_s)

        # 生成控制点（Frenet坐标系）
        control_points = self.generate_control_points(
            current_s, current_d,
            target_s, target_d,
            region_length
        )

        # 生成贝塞尔曲线（Frenet坐标系）
        frenet_trajectory = self.bezier_curve_3rd_order(
            control_points,
            self.num_points
        )

        # 转换到笛卡尔坐标系
        cartesian_trajectory = np.zeros_like(frenet_trajectory)
        for i, (s, d) in enumerate(frenet_trajectory):
            x, y = self.converter.frenet_to_cartesian(s, d)
            cartesian_trajectory[i] = [x, y]

        # 计算速度和加速度
        velocities, accelerations = self.calculate_velocity_acceleration(
            cartesian_trajectory,
            self.dt
        )

        # 计算航向角
        headings = self.calculate_heading(cartesian_trajectory)

        # 构建轨迹点列表
        trajectory_points = []
        for i in range(self.num_points):
            point = TrajectoryPoint(
                timestamp=base_timestamp + i * self.dt,
                location=(cartesian_trajectory[i, 0], cartesian_trajectory[i, 1]),
                heading=headings[i],
                velocity=velocities[i],
                acceleration=accelerations[i]
            )
            trajectory_points.append(point)

        return trajectory_points

    def generate_trajectories(self,
                              behavior_output,
                              cav_vehicles: Dict[ElementID, CAVElementSimple],
                              base_timestamp: float) -> TrajectoryPlanningOutput:
        """
        为所有CAV生成轨迹

        Args:
            behavior_output: BehaviorPlanningOutput对象
            current_states: 每个CAV的当前状态 {cav_id: (current_s, current_d)}
            base_timestamp: 基准时间戳

        Returns:
            TrajectoryPlanningOutput对象
        """
        all_trajectories = {}

        # 遍历每个CAV
        for cav_id, decision_info in behavior_output.CAV_elements.items():
            # 检查是否有目标点
            if decision_info.target_point is None:
                print(f"Warning: CAV {cav_id} 没有目标点，跳过轨迹生成")
                continue

            # 检查是否有当前状态
            if cav_id not in cav_vehicles:
                print(f"Warning: CAV {cav_id} 没有当前状态信息，跳过轨迹生成")
                continue

            #检查是否已有规划好的轨迹
            if cav_vehicles.get(cav_id).planned_trajectory:
                continue


            # 获取当前状态和目标点
            current_x, current_y = cav_vehicles[cav_id].location

            current_s, current_d = self.converter.cartesian_to_frenet(current_x,current_y)

            target_s, target_d = decision_info.target_point

            # 生成轨迹
            trajectory = self.generate_trajectory(
                cav_id,
                current_s,
                current_d,
                target_s,
                target_d,
                base_timestamp
            )

            cav_vehicles[cav_id].planned_trajectory = trajectory
            all_trajectories[cav_id] = trajectory

        # 构建输出
        output = TrajectoryPlanningOutput(
            timestamp=base_timestamp,
            CAV_elements=all_trajectories,
            planning_horizon=self.delta_t
        )

        return output


# 使用示例
if __name__ == "__main__":
    # 假设您已有Frenet到笛卡尔坐标系的转换器
    # converter = YourFrenetToCartesianConverter()

    # 创建轨迹生成器
    # generator = TrajectoryGenerator(
    #     frenet_to_cartesian_converter=converter,
    #     delta_t=5.0,
    #     dt=0.05
    # )

    # 假设您有行为规划的输出
    # behavior_output = BehaviorPlanningOutput(...)

    # 每个CAV的当前状态
    # current_states = {
    #     "CAV_1": (10.0, 0.0),  # (current_s, current_d)
    #     "CAV_2": (15.0, 3.5),
    # }

    # 生成轨迹
    # trajectory_output = generator.generate_trajectories(
    #     behavior_output,
    #     current_states,
    #     base_timestamp=0.0
    # )

    pass