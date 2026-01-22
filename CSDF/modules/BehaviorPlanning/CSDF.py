import numpy as np
from typing import Tuple, List, Dict, Optional, Set
from dataclasses import dataclass
from CSDF.core.DataTypes import (ElementID, Decision, RiskLevel, TrajectoryPoint, TrafficElementBase, CAVElementSimple,
                       CAVDecisionInfo, BehaviorPlanningOutput, TrajectoryPlanningOutput)
from CSDF.core.CoordinateTransform import CartesianFrenetConverter
import time


@dataclass
class RiskFieldParams:  #TODO：check
    """风险场参数"""

    a: float = 1.566e-14
    b: float = 0.335
    c: float = 6.667
    k1: float = 6.65
    k2: float = 1
    k3: float = 6.2


@dataclass
class PlanningParams:
    """规划参数"""
    delta_t: float = 1.0
    d_default: float = 10.0
    lane_width: float = 4.0
    w_e: float = 1.0
    w_r: float = 1.0
    w_c: float = 1.0
    risk_threshold: float = 0.1  # 风险阈值
    n_samples: int = 10  # 积分采样点数
    communication_range: float = 200.0


class RiskField:
    """风险场计算器"""

    def __init__(self, params: RiskFieldParams):
        self.params = params

    def calculate_hdv_static_risk(self, pos_target: Tuple[float, float],
                                  pos_hdv: Tuple[float, float],
                                  velocity_hdv: Tuple[float, float],
                                  heading_hdv: float) -> float:
        """计算HDV静态风险"""
        s, d = pos_target
        s_hdv, d_hdv = pos_hdv

        vs_hdv , vd_hdv = velocity_hdv

        v_hdv = np.sqrt(vs_hdv ** 2 + vd_hdv ** 2)

        m = 1.0
        M_eq = m * (self.params.a * v_hdv + self.params.b)

        r_hdv = np.sqrt((s_hdv - s) ** 2 + (d_hdv - d) ** 2)
        if r_hdv < 1e-6:
            return 1e10

        theta_hdv = heading_hdv
        r_eq = np.sqrt((r_hdv * np.sin(theta_hdv)) ** 2 + (self.params.k2 * r_hdv * np.cos(theta_hdv)) ** 2)

        if r_eq < 1e-6:
            return 1e10

        R_static = (self.params.k1 * M_eq) / r_eq

        return R_static

    def calculate_hdv_dynamic_risk(self, pos_target: Tuple[float, float],
                                   pos_hdv: Tuple[float, float],
                                   vel_target: Tuple[float, float],
                                   vel_hdv: Tuple[float, float],
                                   heading_hdv) -> float:
        """计算HDV动态风险"""
        s, d = pos_target
        s_hdv, d_hdv = pos_hdv
        v_s, v_d = vel_target
        v_hdv_s, v_hdv_d = vel_hdv

        delta_v_s = v_s - v_hdv_s
        delta_v_d = v_d - v_hdv_d
        delta_v = np.sqrt(delta_v_s ** 2 + delta_v_d ** 2)

        delta_r_s = s - s_hdv
        delta_r_d = d - d_hdv
        r_hdv = np.sqrt(delta_r_s ** 2 + delta_r_d ** 2)
        r_eq = np.sqrt((r_hdv * np.sin(heading_hdv)) ** 2 + (self.params.k2 * r_hdv * np.cos(heading_hdv)) ** 2)

        if r_eq < 1e-6:
            return 1e10

        dot_product = delta_v_s * delta_r_s + delta_v_d * delta_r_d
        R_dynamic = self.params.k3 * (delta_v ** 2) * np.exp(dot_product) / r_eq

        return R_dynamic

    def calculate_point_risk(self, pos: Tuple[float, float],
                             regular_vehicles: Dict[ElementID, TrafficElementBase],
                             cav_vehicles: Dict[ElementID, CAVElementSimple],
                             related_cavs_id,
                             converter,
                             exclude_id: ElementID) -> float:
        """计算某点的总风险值"""

        ego_cav = cav_vehicles.get(exclude_id)
        ego_cav_location_cartesian = (ego_cav.location[0], ego_cav.location[1])
        ego_cav_vel_cartesian = (ego_cav.velocity * np.sin(np.deg2rad(ego_cav.heading)), ego_cav.velocity * np.cos(np.deg2rad(ego_cav.heading)))
        ego_cav_vel_frenet = converter.velocity_cartesian_to_frenet(ego_cav.location[0], ego_cav.location[1] ,      #vs, vd
                                                                    ego_cav_vel_cartesian[0] , ego_cav_vel_cartesian[1])


        total_risk = 0.0
        vel_target_frenet = (ego_cav_vel_frenet[0], ego_cav_vel_frenet[1])

        # HDV风险, 仅考虑附近一定80m内的CAV
        for veh_id, hdv in regular_vehicles.items():

            hdv_location_cartesian = (hdv.location[0], hdv.location[1])
            if np.sqrt( (hdv_location_cartesian[0] - ego_cav_location_cartesian[0]) ** 2 +
                        (hdv_location_cartesian[1] - ego_cav_location_cartesian[1])**2 ) >= 80:
                continue

            hdv_location_frenet = converter.cartesian_to_frenet(hdv.location[0], hdv.location[1])

            hdv_vel_cartesian = (hdv.velocity * np.sin(np.deg2rad(hdv.heading)) ,  hdv.velocity * np.cos(np.deg2rad(hdv.heading)))  #vx,vy
            hdv_vel_frenet = converter.velocity_cartesian_to_frenet(hdv.location[0], hdv.location[1] ,      #vs, vd
                                                                    hdv_vel_cartesian[0] , hdv_vel_cartesian[1])

            hdv_heading_frenet = converter.heading_cartesian_to_frenet(hdv.location[0], hdv.location[1] , np.deg2rad(90-hdv.heading))


            R_static = self.calculate_hdv_static_risk(
                pos, hdv_location_frenet, hdv_vel_frenet, hdv_heading_frenet)

            #TODO: 仅考虑静态场，动态场原文公式有问题
            #R_dynamic = self.calculate_hdv_dynamic_risk(
            #    pos, hdv_location_frenet, vel_target_frenet, hdv_vel_frenet, hdv_heading_frenet)

            #total_risk += (R_static + R_dynamic)
            total_risk += R_static

        # CAV风险
        for veh_id, cav in cav_vehicles.items():
            if veh_id == exclude_id or veh_id not in related_cavs_id:
                continue

            cav_location_frenet = converter.cartesian_to_frenet(cav.location[0], cav.location[1])

            cav_vel_cartesian = (cav.velocity * np.sin(np.deg2rad(cav.heading)) ,  cav.velocity * np.cos(np.deg2rad(cav.heading)))  #vx,vy

            cav_vel_frenet = converter.velocity_cartesian_to_frenet(cav.location[0], cav.location[1] ,      #vs, vd
                                                                    cav_vel_cartesian[0] , cav_vel_cartesian[1])

            cav_heading_frenet = converter.heading_cartesian_to_frenet(cav.location[0], cav.location[1] , np.deg2rad(90-cav.heading))

            R_static = self.calculate_hdv_static_risk(
                pos, cav_location_frenet, cav_vel_frenet, cav_heading_frenet)
            total_risk += R_static

        return total_risk


class BehaviorPlanningSystem:
    """多CAV协同行为规划系统"""

    def __init__(self,
                 frenet_converter,
                 risk_params: Optional[RiskFieldParams] = None,
                 planning_params: Optional[PlanningParams] = None):
        """
        Args:
            frenet_converter: Frenet坐标转换器,需要实现:
                - cartesian_to_frenet(x, y) -> (s, d)
                - frenet_to_cartesian(s, d) -> (x, y)
        """
        self.risk_params = risk_params if risk_params else RiskFieldParams()
        self.planning_params = planning_params if planning_params else PlanningParams()
        self.risk_field = RiskField(self.risk_params)
        self.frenet_converter = frenet_converter

    def calculate_region_dimensions(self, velocity: float) -> Tuple[float, float]:
        """计算区域尺寸"""
        length = max(self.planning_params.delta_t * velocity,
                     self.planning_params.d_default)
        width = self.planning_params.lane_width
        return length, width

    def get_region_center_frenet(self, region_id: int,
                                 current_s: float,
                                 current_d: float,
                                 length: float,
                                 width: float) -> Tuple[float, float]:
        """
        在Frenet坐标系下获取区域中心

        Args:
            region_id: 0-5
            current_s: 当前纵向坐标
            current_d: 当前横向坐标
            length: 区域长度
            width: 区域宽度

        Returns:
            (s_center, d_center)
        """
        # 区域布局 (Frenet坐标系):
        # 第二排: 3  4  5  (s = current_s + 2*length)
        # 第一排: 0  1  2  (s = current_s + length)
        # 当前:     车      (s = current_s)

        if region_id in [0, 1, 2]:
            row = 1
        else:
            row = 2

        col = region_id % 3  # 0:左, 1:中, 2:右

        # 纵向位置
        s_center = current_s + row * length

        # 横向位置 (假设d=0是车道中心)
        # col=0 -> d = current_d - width (左车道)
        # col=1 -> d = current_d (当前车道)
        # col=2 -> d = current_d + width (右车道)
        d_center = current_d + (col - 1) * width

        return (s_center, d_center)

    def integrate_region_risk_frenet(self,
                                     region_id: int,
                                     current_s: float,
                                     current_d: float,
                                     length: float,
                                     width: float,
                                     regular_vehicles: Dict[ElementID, TrafficElementBase],
                                     cav_vehicles: Dict[ElementID, CAVElementSimple],
                                     related_cavs_id,
                                     exclude_ids: ElementID,
                                     n_samples: int = 10) -> float:
        """在Frenet坐标系下计算区域风险积分"""
        # 获取区域边界 (Frenet坐标)
        if region_id in [0, 1, 2]:
            row = 1
        else:
            row = 2
        col = region_id % 3

        s_start = current_s + 0.5 * length
        s_end = current_s + row * length + 0.5 * length
        d_start = current_d + (col - 1) * width - 0.5 * width
        d_end = current_d + col * width - 0.5 * width

        total_risk = 0.0

        # 在Frenet网格上采样
        # for i in range(n_samples):
        #     for j in range(n_samples):
        #         s_sample = s_start + (i + 0.5) * (s_end - s_start) / n_samples
        #         d_sample = d_start + (j + 0.5) * (d_end - d_start) / n_samples
        #
        #         # 计算该点风险
        #         risk = self.risk_field.calculate_point_risk(
        #             (s_sample, d_sample), regular_vehicles, cav_vehicles, related_cavs_id, self.frenet_converter, exclude_ids)
        #         total_risk += risk

        #用网格中心点代替
        center_s = (s_start + s_end) / 2
        center_d = (d_start + d_end) / 2

        risk = self.risk_field.calculate_point_risk(
                     (center_s, center_d), regular_vehicles, cav_vehicles, related_cavs_id, self.frenet_converter, exclude_ids)

        #avg_risk = total_risk / (n_samples * n_samples)
        return risk

    def calculate_region_reward(self,
                                region_id: int,
                                current_s: float,
                                current_d: float,
                                length: float,
                                width: float,
                                regular_vehicles: Dict[ElementID, TrafficElementBase],
                                cav_vehicles: Dict[ElementID, CAVElementSimple],
                                related_cavs_id,
                                exclude_ids: ElementID) -> Dict[str, float]:
        """计算区域奖励"""
        # 安全性
        R_i = self.integrate_region_risk_frenet(
            region_id, current_s, current_d, length, width,
            regular_vehicles, cav_vehicles,
            related_cavs_id,
            exclude_ids,
            self.planning_params.n_samples)

        # 效率 (鼓励向前行驶,区域越靠前效率越高)                 #简化 ： 前排 l， 后排 2*l
        if region_id in [0,1,2]:
            E_i = length
        else :
            E_i = 2 * length

        # 舒适度 (变道惩罚)                                  # 只有1，4 是保持， 模3余1
        target_lane = region_id % 3
        C_i = 1.0 if target_lane != 1 else 0.0

        # 总奖励
        reward = (self.planning_params.w_e * E_i -
                  self.planning_params.w_r * R_i -
                  self.planning_params.w_c * C_i)

        return {
            'safety': R_i,
            'efficiency': E_i,
            'comfort': C_i,
            'reward': reward
        }

    def find_best_region(self,
                         cav_id: ElementID,
                         length,width,
                         cav: CAVElementSimple,
                         potential_regions: List[Decision],
                         regular_vehicles: Dict[ElementID, TrafficElementBase],
                         cav_vehicles: Dict[ElementID, CAVElementSimple],
                         related_cav_id,
                         occupied_regions: Set[Decision],
                         exclude_ids: Set[ElementID]) -> Tuple[Decision, Dict]:


        """为当前CAV找到最优区域"""
        # 转换到Frenet坐标
        current_s, current_d = self.frenet_converter.cartesian_to_frenet(
                cav.location[0], cav.location[1])

        # 计算所有可行区域的奖励
        region_rewards = {}
        for region_id in potential_regions:
            if region_id in occupied_regions:
                continue  # 跳过已被占用的区域

            reward_info = self.calculate_region_reward(
                region_id, current_s, current_d,
                length, width,
                regular_vehicles, cav_vehicles, related_cav_id ,exclude_ids=cav_id)

            region_rewards[region_id] = reward_info

        if not region_rewards:
            # 如果没有可行区域,选择当前车道前方
            return 1, {'center': (current_s + length, current_d), 'reward': -float('inf')}

        # 选择奖励最大的区域
        best_region = max(region_rewards.keys(),
                          key=lambda k: region_rewards[k]['reward'])

        return best_region, region_rewards[best_region]

    def find_safe_point_in_region(self,
                                  region_id: int,
                                  current_s: float,
                                  current_d: float,
                                  length: float,
                                  width: float,
                                  regular_vehicles: Dict[ElementID, TrafficElementBase],
                                  cav_vehicles: Dict[ElementID, CAVElementSimple],
                                  related_cavs_id,
                                  exclude_ids: ElementID,
                                  n_samples: int = 10) -> Tuple[float, float]:
        """
        在目标区域中寻找距离CAV最远且低于风险阈值的点

        Returns:
            (s_target, d_target) in Frenet coordinates
        """
        # 区域边界
        if region_id in [0, 1, 2]:
            row = 1
        else:
            row = 2
        col = region_id % 3

        s_start = current_s + (row - 1) * length + 0.5 * length
        s_end = current_s + row * length + 0.5 * length
        d_start = current_d + (col - 1) * width - 0.5 * width
        d_end = current_d + col * width - 0.5 * width

        d_center = (d_start + d_end) / 2

        # 采样寻找最佳点
        best_point = None
        max_distance = -1

        # for i in range(n_samples):
        #     for j in range(n_samples):
        #         s_sample = s_start + (i + 0.5) * (s_end - s_start) / n_samples
        #         d_sample = d_start + (j + 0.5) * (d_end - d_start) / n_samples
        #
        #         # 计算风险
        #         risk = self.risk_field.calculate_point_risk(
        #             (s_sample, d_sample), regular_vehicles, cav_vehicles, related_cavs_id, self.frenet_converter, exclude_ids)
        #
        #         # 如果低于风险阈值
        #         if risk < self.planning_params.risk_threshold:
        #             # 计算到CAV的距离
        #             distance = np.sqrt((s_sample - current_s) ** 2 +
        #                                (d_sample - current_d) ** 2)
        #
        #             if distance > max_distance:
        #                 max_distance = distance
        #                 best_point = (s_sample, d_sample)

        for i in range(n_samples):
            s_sample = s_start + (i + 0.5) * (s_end - s_start) / n_samples
            # 计算风险
            risk = self.risk_field.calculate_point_risk(
                (s_sample, d_center), regular_vehicles, cav_vehicles, related_cavs_id, self.frenet_converter, exclude_ids)

            if risk < self.planning_params.risk_threshold:
                if s_sample > max_distance:
                    max_distance = s_sample
                    best_point = (s_sample, d_center)


        # 如果没找到安全点,返回区域中心 TODO: 异常处理
        if best_point is None:
            s_center = (s_start + s_end) / 2
            best_point = (s_center, d_center)

        return best_point

    def check_any_target_in_potential_regions(self, planned_cav_target_point, current_s, current_d, length, width):
        """
        检查目标点是否在当前车辆的6个潜在格子区域内

        参数:
            planned_cav_target_point: (s, d) 目标点的坐标
            current_s, current_d: 当前车辆的(s,d)坐标
            length: 格子的纵向长度
            width: 格子的横向宽度

        返回:
            bool: 目标点是否在任意一个潜在格子内
            int: 所在格子的编号(0-5)，如果不在返回-1
        """

        target_s, target_d = planned_cav_target_point

        # 格子的中心坐标（相对于车辆当前位置）
        grid_centers = [
            # 第一排（前方，编号0,1,2）
            (length, -width),  # 0号格子：前方左侧
            (length, 0),  # 1号格子：正前方
            (length, width),  # 2号格子：前方右侧

            # 第二排（更前方，编号3,4,5）
            (2 * length, -width),  # 3号格子：更前方左侧
            (2 * length, 0),  # 4号格子：更前方正中央
            (2 * length, width)  # 5号格子：更前方右侧
        ]

        # 检查目标点是否在任意一个格子内
        for grid_idx, (center_s_offset, center_d_offset) in enumerate(grid_centers):
            # 计算格子中心点的绝对坐标
            grid_center_s = current_s + center_s_offset
            grid_center_d = current_d + center_d_offset

            # 计算目标点与格子中心的距离
            s_distance = abs(target_s - grid_center_s)
            d_distance = abs(target_d - grid_center_d)

            # 检查是否在格子边界内（以格子中心为基准）
            # 允许的误差范围：纵向±length/2，横向±width/2
            if s_distance <= length / 2 and d_distance <= width / 2:
                return True, grid_idx

        # 不在任何格子内
        return False, -1

    def plan_behavior(self,
                      timestamp: float,
                      regular_vehicles: Dict[ElementID, TrafficElementBase],
                      cav_vehicles: Dict[ElementID, CAVElementSimple],
                      potential_decisions: Dict[ElementID, List[Decision]] = None) -> BehaviorPlanningOutput:
        """
        多CAV协同行为规划

        Args:
            timestamp: 当前时间戳
            regular_vehicles: 普通车辆字典
            cav_vehicles: CAV车辆字典
            potential_decisions: 每个CAV的可行决策区域(可选,默认所有区域可行)

        Returns:
            BehaviorPlanningOutput
        """

        # 存储决策结果
        cav_decisions = {}
        occupied_regions = set()


        # 如果没有提供可行决策,默认所有区域都可行
        if potential_decisions is None:
            potential_decisions = {cav_id: [0, 1, 2, 3, 4, 5]
                                   for cav_id in cav_vehicles.keys()}

        # 找出高风险的CAV，假设只有一个ego-cav (最高风险的)
        high_risk_cavs_id = [cav_id for cav_id, cav in cav_vehicles.items()
                          if cav.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]

        high_risk_cav_id = high_risk_cavs_id[0]

        high_risk_cav = cav_vehicles.get(high_risk_cav_id)


        if not high_risk_cav.isPlanned:

            high_risk_bp_start_time = time.time()

            current_s, current_d = self.frenet_converter.cartesian_to_frenet(high_risk_cav.location[0], high_risk_cav.location[1])

            vs, vd = self.frenet_converter.velocity_cartesian_to_frenet(high_risk_cav.location[0], high_risk_cav.location[1],
                                                                        high_risk_cav.velocity * np.sin(np.deg2rad(high_risk_cav.heading)),
                                                                        high_risk_cav.velocity * np.cos(np.deg2rad(high_risk_cav.heading)))
            convert_time = time.time()

            print(f"convert time is {convert_time - high_risk_bp_start_time}")


            # 以当前的高风险CAV划分格子，计算区域尺寸
            length, width = self.calculate_region_dimensions(vs)

            # 获取这个高风险车的可行区域
            potential_regions = potential_decisions.get(high_risk_cav_id, [0, 1, 2, 3, 4, 5])

            # 找出相关CAV (通信范围内的其他CAV)
            related_cavs_id = []
            for other_id, other_cav in cav_vehicles.items():
                if other_id == high_risk_cav_id:
                    continue
                distance = np.sqrt((high_risk_cav.location[0] - other_cav.location[0]) ** 2 +
                                   (high_risk_cav.location[1] - other_cav.location[1]) ** 2)
                if distance <= self.planning_params.communication_range:
                    related_cavs_id.append(other_id)

            # 为该CAV找最优区域 (排除自己)
            find_best_region_start_time = time.time()
            exclude_ids = high_risk_cav_id
            best_region, region_info = self.find_best_region(
                high_risk_cav_id, length, width, high_risk_cav , potential_regions,
                regular_vehicles, cav_vehicles, related_cavs_id, occupied_regions, exclude_ids)
            find_best_region_end_time = time.time()
            print(f"find best region time is {find_best_region_end_time - find_best_region_start_time}")

            # 在目标区域中寻找最安全的点
            find_safe_point_start_time = time.time()
            target_point_frenet = self.find_safe_point_in_region(
                best_region, current_s, current_d, length, width,
                regular_vehicles, cav_vehicles, related_cavs_id, exclude_ids)
            find_safe_point_start_time = time.time()
            print(f"find safe point time is {find_safe_point_start_time - find_best_region_start_time}")
            # 保存决策信息
            cav_decisions[high_risk_cav_id] = CAVDecisionInfo(
                potential_decision=potential_regions,
                related_cav=related_cavs_id,
                risk_level=high_risk_cav.risk_level,
                decision=best_region,
                target_point=target_point_frenet
            )
            high_risk_bp_end_time = time.time()
            print(f"high risk cav bp computation time is {high_risk_bp_end_time - high_risk_bp_start_time}")

            # 标记该CAV已规划
            high_risk_cav.isPlanned = True
            #occupied_regions.add(best_region)


        # 依次为每个CAV决策
        other_cav_bp_start_time = time.time()
        for cav_id in cav_vehicles.keys():

            if cav_id == high_risk_cav_id:
                continue

            cav = cav_vehicles[cav_id]
            if cav.isPlanned :
                continue

            current_s, current_d = self.frenet_converter.cartesian_to_frenet(cav.location[0],
                                                                             cav.location[1])

            vs, vd = self.frenet_converter.velocity_cartesian_to_frenet(cav.location[0],
                                                                        cav.location[1],
                                                                        cav.velocity * np.sin(
                                                                            np.deg2rad(cav.heading)),
                                                                        cav.velocity * np.cos(
                                                                            np.deg2rad(cav.heading)))

            length, width = self.calculate_region_dimensions(vs)

            # 获取可行区域
            potential_regions = potential_decisions.get(cav_id, [0, 1, 2, 3, 4, 5])

            for planned_cav in cav_decisions.values():

                flag , idx = self.check_any_target_in_potential_regions(planned_cav.target_point, current_s, current_d ,length, width)
                if flag and idx in potential_regions:
                    potential_regions.remove(idx)

            # 找出相关CAV (通信范围内的其他CAV)
            related_cavs_id = []
            for other_id, other_cav in cav_vehicles.items():
                if other_id == cav_id:
                    continue
                distance = np.sqrt((cav.location[0] - other_cav.location[0]) ** 2 +
                                   (cav.location[1] - other_cav.location[1]) ** 2)
                if distance <= self.planning_params.communication_range:
                    related_cavs_id.append(other_id)

            # 为该CAV找最优区域 (排除自己)
            exclude_ids = cav_id
            best_region, region_info = self.find_best_region(
                cav_id, length, width, cav, potential_regions,
                regular_vehicles, cav_vehicles, related_cavs_id, occupied_regions, exclude_ids)

            # 在目标区域中寻找最安全的点
            target_point_frenet = self.find_safe_point_in_region(
                best_region, current_s, current_d, length, width,
                 regular_vehicles, cav_vehicles, related_cavs_id, exclude_ids)

            # 保存决策信息
            cav_decisions[cav_id] = CAVDecisionInfo(
                potential_decision=potential_regions,
                related_cav=related_cavs_id,
                risk_level=cav.risk_level,
                decision=best_region,
                target_point=target_point_frenet
            )

            # 标记该区域已被占用
            #occupied_regions.add(best_region)

            # 标记该CAV已规划
            cav.isPlanned = True

        other_cav_bp_end_time = time.time()
        print(f"other cav bp computation time is {other_cav_bp_end_time - other_cav_bp_start_time}")
        return BehaviorPlanningOutput(
            timestamp=timestamp,
            CAV_elements=cav_decisions
        )
