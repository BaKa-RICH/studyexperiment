import os
import math
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# SUMO/TraCI 导入（要求已正确安装 SUMO 并配置环境变量 SUMO_HOME）
try:
    import traci
    import sumolib
except ImportError as e:
    raise ImportError("需要安装并配置 SUMO/TraCI。请确保已设置 SUMO_HOME 并可 import traci、sumolib。") from e

from config import *
from run_synchronization import *

sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                     sumo_port, sumo_gui, client_order)
carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager,
                                                sync_vehicle_color, sync_vehicle_lights)


class TrajectoryExecutor:
    """
    多车轨迹执行器：从 CSV 读取 (vehicle_id, x, y, heading[rad], timestamp[s])，
    按时间推进 SUMO 仿真，并在每个时间步将车辆移动到对应位置与朝向。
    """

    def __init__(
        self,
        csv_path: str = "./planned_trajectories_multi_vehicle.csv",
        sumo_cfg: str = None,
        net_path: str = None,
        use_gui: bool = None,
        step_length: float = None,
        start_delay: float = 0.0,
    ):
        """
        Args:
            csv_path: 轨迹 CSV 路径（默认当前目录文件）
            sumo_cfg: SUMO 配置文件路径（默认使用 config.sumo_cfg_file）
            net_path: SUMO 路网文件（用于最近边查询与动态加车）。默认 ./scene_4/road.net.xml
            use_gui: 是否使用 GUI（默认使用 config.sumo_gui）
            step_length: TraCI 步长，秒（默认使用 config.step_length）
            start_delay: 启动 SUMO 后等待秒数，确保 TraCI 就绪
        """
        self.csv_path = csv_path
        self.sumo_cfg = sumo_cfg if sumo_cfg is not None else sumo_cfg_file
        self.use_gui = sumo_gui if use_gui is None else use_gui
        self.step_length = step_length if step_length is None else step_length
        self.start_delay = start_delay

        # network 文件默认与场景一致
        self.net_path = net_path if net_path is not None else "./scene_4/road.net.xml"

        # 数据结构
        self.df = None
        self.timeline: List[float] = []
        self.groups: Dict[float, List[Tuple[str, float, float, float]]] = {}

        # sumolib.net
        self.net = None

    # -------------------- 公共 API --------------------

    def load(self):
        """加载 CSV，构建时间轴与分组；加载路网。"""
        if not os.path.isfile(self.csv_path):
            raise FileNotFoundError(f"未找到 CSV: {self.csv_path}")

        self.df = pd.read_csv(self.csv_path)
        required_cols = {"vehicle_id", "x", "y", "heading", "timestamp"}
        if not required_cols.issubset(self.df.columns):
            raise ValueError(f"CSV 列缺失，需包含: {required_cols}")

        # 排序并构建时间序列（浮点精度做适度规整）
        self.df["timestamp"] = self.df["timestamp"].astype(float)
        self.df.sort_values(["timestamp", "vehicle_id"], inplace=True)

        # 规整时间戳到 1e-6 精度，避免浮点累积误差影响分组与对齐
        self.df["ts_round"] = self.df["timestamp"].apply(lambda t: float(f"{t:.6f}"))
        self.timeline = sorted(self.df["ts_round"].unique().tolist())

        # 构建每个时间戳的车辆目标列表
        self.groups.clear()
        for ts, g in self.df.groupby("ts_round"):
            # 每条为 (veh_id, x, y, heading_rad)
            records = list(zip(g["vehicle_id"], g["x"], g["y"], g["heading"]))
            self.groups[ts] = records

        # 加载路网（用于最近边与动态加车）
        if not os.path.isfile(self.net_path):
            raise FileNotFoundError(f"未找到路网: {self.net_path}")
        self.net = sumolib.net.readNet(self.net_path)

    # def start_sumo(self):
    #     """启动 SUMO/TraCI。"""
    #     sumo_binary = sumolib.checkBinary("sumo-gui" if self.use_gui else "sumo")
    #     traci.start([sumo_binary, "-c", self.sumo_cfg, "--step-length", str(self.step_length)])
    #     if self.start_delay > 0:
    #         time.sleep(self.start_delay)

    def close(self):
        """关闭 TraCI 连接。"""
        # if traci.isLoaded() and traci.getConnection() is not None:
        #     traci.close(False)

        settings = carla_simulation.world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        carla_simulation.world.apply_settings(settings)

        # Destroying synchronized actors.
        for carla_actor_id in synchronization.sumo2carla_ids.values():
            carla_simulation.destroy_actor(carla_actor_id)

        for sumo_actor_id in synchronization.carla2sumo_ids.values():
            sumo_simulation.destroy_actor(sumo_actor_id)

        # Closing sumo and carla client.
        carla_simulation.close()
        sumo_simulation.close()



    def run(self):
        """
        执行全流程：
        - 启动 SUMO
        - 按时间轴重放轨迹：在对应时间戳设置所有车辆位置与角度，然后推进一个仿真步
        - 结束关闭
        """
        self.load()
        #self.start_sumo()

        try:
            # 将仿真推进至时间轴起点（若需要）
            sim_time = traci.simulation.getTime()
            first_ts = self.timeline[0]
            while sim_time + 1e-6 < first_ts:
                synchronization.tick()
                sim_time = traci.simulation.getTime()

            for ts in self.timeline:
                # 对齐仿真时间到 ts（允许 CSV 时间粒度大于 step_length）
                sim_time = traci.simulation.getTime()
                while sim_time + 1e-6 < ts:
                    synchronization.tick()
                    sim_time = traci.simulation.getTime()

                # 当前时间戳下移动所有车辆
                for veh_id, x, y, heading_rad in self.groups[ts]:

                    #heading_rad = 90 - np.rad2deg(heading_rad)
                    self._ensure_vehicle_exists(veh_id, float(x), float(y), float(heading_rad))
                    self._move_vehicle_xy(veh_id, float(x), float(y), float(heading_rad))

                # 推进一步让位置生效并可视化
                synchronization.tick()
                #traci.simulationStep()

        finally:
            self.close()

    # -------------------- 内部方法 --------------------

    def _ensure_vehicle_exists(self, veh_id: str, x: float, y: float, heading_rad: float):
        """
        确保车辆在仿真中存在：
        - 若不存在，则在最近 edge 上创建临时路线并加入车辆
        - 添加后立刻 moveToXY 到目标位置（避免 spawn 点偏差）
        """
        if veh_id in traci.vehicle.getIDList():
            return

        # 寻找最近边及其朝向，用于创建最短路线
        edge, dist = self._get_closest_edge(x, y)
        edge_id = edge.getID()

        # 准备车辆与路线 ID
        route_id = f"route__{edge_id}"
        if route_id not in traci.route.getIDList():
            traci.route.add(route_id, [edge_id])

        # 创建车辆（使用默认车型）
        # 为避免被 SUMO 行车逻辑影响，设置速度为 0，随后用 moveToXY 控制
        if veh_id not in traci.vehicle.getIDList():
            traci.vehicle.add(
                veh_id=veh_id,
                routeID=route_id,
                typeID="DEFAULT_VEHTYPE"
            )
            # 将车辆设为可被外部控制（可必要时保持 0 期望速度）
            try:
                traci.vehicle.setSpeed(veh_id, 0.0)
            except Exception:
                pass

        # 初始放置到目标附近
        self._move_vehicle_xy(veh_id, x, y, heading_rad)

    def _get_closest_edge(self, x: float, y: float):
        """返回 (edge, distance)。"""
        # sumolib: getNeighboringEdges((x,y), radius) 或 getClosestEdge()
        # 使用 getClosestEdge
        try:
            edge = self.net.getClosestEdge((x, y))[0]
            # getClosestEdge 可能返回 (edge, lanePos, dist) 的不同实现，统一取 edge
        except Exception:
            # 回退：从邻近边集合中选最近
            candidates = self.net.getNeighboringEdges(x, y, r=50)
            if not candidates:
                raise RuntimeError("在附近 50m 未找到任何道路边，无法添加车辆。")
            # candidates: List[(edge, distance)]
            edge = min(candidates, key=lambda it: it[1])[0]
        # 估算距离
        try:
            dist = edge.getFromNode().getCoord().distance2D((x, y))
        except Exception:
            dist = 0.0
        return edge, dist

    def _move_vehicle_xy(self, veh_id: str, x: float, y: float, heading_rad: float):
        """
        使用 TraCI 将车辆移动到 (x,y) 并设置角度。
        注意：SUMO 使用角度单位为度，0 度朝向 +X，逆时针为正。
        """
        angle_deg = 90 - math.degrees(heading_rad)
        # keepRoute=2 表示尽量保持当前路线，允许偏离匹配
        # 使用 edgeID="" 和 laneIndex=0 进行基于坐标的定位（SUMO 会自动匹配最近车道）
        try:
            traci.vehicle.moveToXY(veh_id, edgeID="", laneIndex=0, x=x, y=y, angle=angle_deg, keepRoute=2)
        except TypeError:
            # 兼容旧 TraCI 签名 (无命名参数)
            traci.vehicle.moveToXY(veh_id, "", 0, x, y, angle_deg, 2)


if __name__ == "__main__":
    """
    直接运行：回放 CSV 轨迹
    """
    executor = TrajectoryExecutor(
        csv_path="./planned_trajectories_multi_vehicle.csv",
        sumo_cfg=sumo_cfg_file,
        net_path="./scene_4/road.net.xml",
        use_gui=sumo_gui,
        step_length=step_length,
        start_delay=0.2,
    )
    executor.run()