import traci

from CSDF.core.DataTypes import (ElementID, Decision, RiskLevel, TrajectoryPoint, TrafficElementBase, CAVElementSimple,
                       CAVDecisionInfo, BehaviorPlanningOutput, TrajectoryPlanningOutput)
from CSDF.core.CoordinateTransform import CartesianFrenetConverter
from typing import Dict, List,Optional



class SceneMonitor:
    """SUMO场景监控器 - 从仿真获取并整理交通要素信息， 只修改车辆运行状态，不修改决策信息"""

    def __init__(self, cav_ids: Optional[List[str]] = None):
        """
        初始化监控器

        Args:
            cav_ids: CAV车辆ID列表，如果为None则所有车辆都视为普通车辆
        """
        self.cav_ids = set(cav_ids) if cav_ids else set()

        # 车辆信息存储
        self.regular_vehicles: Dict[ElementID, TrafficElementBase] = {}
        self.cav_vehicles: Dict[ElementID, CAVElementSimple] = {}

        self.potential_region: Dict[ElementID , list[Decision]] = {}

        # 当前仿真时间
        self.current_time = 0.0

        # CAV相关配置
        self.default_communication_range = 100.0
        self.cav_planned_status: Dict[ElementID, bool] = {}  # 外部设置CAV是否已规划
        self.cav_trajectories: Dict[ElementID, List[TrajectoryPoint]] = {}  # 外部设置的规划轨迹

    def set_cav_ids(self, cav_ids: List[str]):
        """设置CAV车辆ID列表"""
        self.cav_ids = set(cav_ids)

    def set_cav_planned(self, cav_id: str, is_planned: bool):
        """设置CAV是否已规划"""
        self.cav_planned_status[cav_id] = is_planned

    def set_cav_trajectory(self, cav_id: str, trajectory: List[TrajectoryPoint]):
        """设置CAV的规划轨迹"""
        self.cav_trajectories[cav_id] = trajectory

    def update(self):
        """从SUMO获取当前时刻的所有车辆信息并更新"""
        # 获取当前仿真时间
        self.current_time = traci.simulation.getTime()

        current_all_vehicles = traci.vehicle.getIDList()

        # 去掉以及离开仿真的车
        for hdv_ids in self.regular_vehicles.keys():
            if hdv_ids not in current_all_vehicles:
                self.regular_vehicles.pop(hdv_ids)

        for cav_ids in self.cav_vehicles.keys():
            if cav_ids not in current_all_vehicles:
                self.regular_vehicles.pop(cav_ids)

        # 遍历所有车辆，获取信息
        for veh_id in current_all_vehicles:
            # 获取基础信息
            position = traci.vehicle.getPosition(veh_id)  # (x, y)
            heading = traci.vehicle.getAngle(veh_id)  # SUMO中的角度
            velocity = traci.vehicle.getSpeed(veh_id)  # m/s
            acceleration = traci.vehicle.getAcceleration(veh_id)
            edge_id = traci.vehicle.getRoadID(veh_id)
            lane_id = traci.vehicle.getLaneID(veh_id)

            #如果已被记录过，修改其基础信息
            if veh_id in self.regular_vehicles.keys() or veh_id in self.cav_vehicles.keys():
                if veh_id in self.regular_vehicles.keys():
                    self.regular_vehicles[veh_id].location = position
                    self.regular_vehicles[veh_id].heading = heading
                    self.regular_vehicles[veh_id].velocity = velocity
                    self.regular_vehicles[veh_id].acceleration = acceleration
                    self.regular_vehicles[veh_id].edge_id = edge_id
                    self.regular_vehicles[veh_id].lane_id = lane_id

                if veh_id in self.cav_vehicles.keys():
                    self.cav_vehicles[veh_id].location = position
                    self.cav_vehicles[veh_id].heading = heading
                    self.cav_vehicles[veh_id].velocity = velocity
                    self.cav_vehicles[veh_id].acceleration = acceleration
                    self.cav_vehicles[veh_id].edge_id = edge_id
                    self.cav_vehicles[veh_id].lane_id = lane_id
                    self.cav_vehicles[veh_id].risk_level = self._assess_risk_level(veh_id,position,velocity)

            else:
                #如果没有被记录过，创建新的
                # 判断是CAV还是普通车辆
                if veh_id in self.cav_ids:
                    # 创建CAV对象
                    cav = self._create_cav_element(
                        veh_id, position, heading, velocity,
                        acceleration, edge_id, lane_id
                    )
                    self.cav_vehicles[veh_id] = cav
                else:
                    # 创建普通车辆对象
                    regular_veh = TrafficElementBase(
                        element_id=veh_id,
                        location=position,
                        heading=heading,
                        velocity=velocity,
                        acceleration=acceleration,
                        edge_id=edge_id,
                        lane_id=lane_id,
                    )
                    self.regular_vehicles[veh_id] = regular_veh

            #每个CAV可行的区域
            for cav_id in self.cav_vehicles.keys():
                cav = self.cav_vehicles[cav_id]
                lane_id = cav.lane_id
                parts = lane_id.rsplit('_', 1)
                edge_id, lane_index_str = parts
                lane_index = int(lane_index_str)

                if 1<= lane_index <= 2 :
                    self.potential_region[cav_id] = [0,1,2,3,4,5]
                elif lane_index == 3 :
                    self.potential_region[cav_id] = [1, 2, 4, 5]
                elif lane_index == 0 :
                    self.potential_region[cav_id] = [0,1,3,4]

    def _create_cav_element(self, veh_id: str, position: tuple, heading: float,
                            velocity: float, acceleration: float,
                            edge_id: str, lane_id: str) -> CAVElementSimple:
        """创建CAV要素对象"""

        # 计算风险等级（基于周围车辆的TTC等）
        risk_level = self._assess_risk_level(veh_id, position, velocity)

        return CAVElementSimple(
            element_id=veh_id,
            location=position,
            heading=heading,
            velocity=velocity,
            acceleration=acceleration,
            edge_id=edge_id,
            lane_id=lane_id,
            isPlanned=False,
            risk_level=risk_level,
            communication_range=self.default_communication_range,
            planned_trajectory=None
        )

    def _assess_risk_level(self, veh_id: str, position: tuple,
                           velocity: float) -> RiskLevel:
        """
        评估CAV的风险等级
        可以基于TTC、周围车辆距离等因素
        """
        # 简化版风险评估：基于与前车的距离和相对速度
        try:
            leader = traci.vehicle.getLeader(veh_id)

            if leader is None:
                return RiskLevel.LOW

            leader_id, gap = leader
            leader_vel = traci.vehicle.getSpeed(leader_id)

            vel_diff = traci.vehicle.getSpeed(veh_id) - leader_vel

            if vel_diff < 0 < gap:
                return RiskLevel.LOW
            else:
                TTC = gap / vel_diff
                if TTC > 5:
                    return RiskLevel.LOW
                if 5 > TTC > 3:
                    return  RiskLevel.MEDIUM
                if 3 > TTC > 1.5:
                    return RiskLevel.HIGH
                else:
                    return RiskLevel.CRITICAL

        except:
            return RiskLevel.LOW


    def get_all_vehicles(self) -> Dict[ElementID, TrafficElementBase]:
        """获取所有车辆"""
        all_vehicles = {}
        all_vehicles.update(self.regular_vehicles)
        all_vehicles.update(self.cav_vehicles)
        return all_vehicles

    def get_vehicles_on_edge(self, edge_id: str) -> List[TrafficElementBase]:
        """获取指定道路上的所有车辆"""
        vehicles = []
        for vehicle in self.get_all_vehicles().values():
            if vehicle.edge_id == edge_id:
                vehicles.append(vehicle)
        return vehicles

    def get_vehicles_on_lane(self, lane_id: str) -> List[TrafficElementBase]:
        """获取指定车道上的所有车辆"""
        vehicles = []
        for vehicle in self.get_all_vehicles().values():
            if vehicle.lane_id == lane_id:
                vehicles.append(vehicle)
        return vehicles

    def get_high_risk_cavs(self) -> List[CAVElementSimple]:
        """获取高风险CAV"""
        return [cav for cav in self.cav_vehicles.values()
                if cav.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]

    def get_statistics(self) -> dict:
        """获取场景统计信息"""
        risk_distribution = {level.name: 0 for level in RiskLevel}
        for cav in self.cav_vehicles.values():
            risk_distribution[cav.risk_level.name] += 1

        return {
            'simulation_time': self.current_time,
            'total_vehicles': len(self.get_all_vehicles()),
            'regular_vehicles': len(self.regular_vehicles),
            'cav_vehicles': len(self.cav_vehicles),
            'planned_cavs': sum(1 for cav in self.cav_vehicles.values() if cav.isPlanned),
            'risk_distribution': risk_distribution
        }