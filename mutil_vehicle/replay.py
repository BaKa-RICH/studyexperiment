# coding: utf-8
import os
import math
import time
from typing import Dict, List, Tuple
import logging # <-- 新增导入

import numpy as np
import pandas as pd

# SUMO/TraCI 导入
try:
    import carla
    import traci
    import sumolib
except ImportError as e:
    raise ImportError("需要安装并配置 SUMO/TraCI。请确保已设置 SUMO_HOME 并可 import traci、sumolib。") from e

# --- 从你的项目导入共享的仿真实例 ---
# 假设 config.py 和 run_synchronization.py 在同一目录或父目录
try:
    # 如果 trajectory_executor.py 与 config.py 在同一目录
    from config import *
    from run_synchronization import SumoSimulation, CarlaSimulation, SimulationSynchronization
except ImportError:
    # 如果 trajectory_executor.py 在子目录 (例如 mutil_vehicle)
    import sys
    # 将父目录添加到 sys.path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from config import *
        from run_synchronization import SumoSimulation, CarlaSimulation, SimulationSynchronization
    except ImportError as e_inner:
        print(f"错误：无法从父目录导入 config 或 run_synchronization: {e_inner}")
        # 如果你没有这两个文件，或者不想用它们，
        # 你需要在这里手动配置 SUMO/CARLA 连接参数
        sys.exit(1)
# ------------------------------------

# --- [!!! 再次提醒 !!!] ---
# 你的日志显示 CARLA Client API (0.10.0) 与 Simulator API (0.9.15) 不匹配。
# 这很可能会导致 CARLA 部分的同步和可视化失败或崩溃。
# 你必须卸载 0.10.0 的库，并安装 0.9.15 模拟器自带的 .whl 文件。
# --------------------------

# --- 初始化日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# --- 初始化联合仿真 ---
# [注意] 确保 config.py 中的 sumo_cfg_file 指向正确的 SUMO 配置文件
#        并且该配置文件引用的 .rou.xml 文件应该是空的 (没有 <vehicle> 定义)
try:
    sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                     sumo_port, sumo_gui, client_order)
    carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

    synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager,
                                                sync_vehicle_color, sync_vehicle_lights)
except NameError:
    logging.error("无法初始化 SumoSimulation/CarlaSimulation/Synchronization。"
                  "请确保 config.py 和 run_synchronization.py 可访问且配置正确。")
    sys.exit(1)
except Exception as e:
    logging.error(f"初始化仿真连接时出错: {e}", exc_info=True)
    sys.exit(1)




def update_driver_spectator(world, synchronization, vehicle_id_to_follow):
    # 1. 通过SUMO ID在映射表中找到对应的CARLA ID
    carla_id = synchronization.sumo2carla_ids.get(vehicle_id_to_follow)

    # 如果车辆还没在CARLA中生成，或者已经消失，则不执行任何操作
    if carla_id is None:
        return

    # 2. 通过CARLA ID获取车辆演员对象
    vehicle_actor = world.get_actor(carla_id)
    if vehicle_actor is None:
        return

    # 3. 获取车辆的当前位姿
    vehicle_transform = vehicle_actor.get_transform()

    # 4. 计算摄像机的理想位姿

    location = vehicle_transform.location + carla.Location(z=70)

    rotation = carla.Rotation(-90,0,0)

    # 5. 获取观察者对象，并应用新的位姿
    spectator = world.get_spectator()
    spectator.set_transform(carla.Transform(location, rotation))

class TrajectoryExecutor:
    """
    多车轨迹执行器：从 CSV 读取 (vehicle_id, x, y, angle[度, SUMO], timestamp[s])，
    按时间推进 SUMO/CARLA 仿真，并在每个时间步将车辆移动到对应位置与朝向。
    [修改] 读取 'angle' 列，设置规划车辆颜色。
    """

    def __init__(
        self,
        # [修改] 默认读取 offline planner 生成的文件
        csv_path: str = "./planned_trajectories_lc_offline.csv",
        sumo_cfg: str = None, # 通常不需要覆盖，使用 config.py 的
        net_path: str = None, # 通常不需要覆盖，使用 config.py 或默认
        use_gui: bool = None, # 通常不需要覆盖
        step_length_override: float = None, # 通常不需要覆盖
        start_delay: float = 0.2, # 启动后短暂延迟
    ):
        self.csv_path = csv_path
        # [修改] 使用 config.py 中的全局变量 (如果存在)
        self.sumo_cfg = sumo_cfg if sumo_cfg is not None else (sumo_cfg_file if 'sumo_cfg_file' in globals() else "simulation.sumocfg")
        self.use_gui = use_gui if use_gui is not None else (sumo_gui if 'sumo_gui' in globals() else True)
        self.step_length = step_length_override if step_length_override is not None else (step_length if 'step_length' in globals() else 0.05)
        self.start_delay = start_delay

        # network 文件路径 (用于 _get_closest_edge)
        # 尝试从 sumo_cfg_file 推断，否则使用默认
        if net_path is None:
            try:
                cfg_dir = os.path.dirname(self.sumo_cfg)
                # 假设 net 文件通常在 cfg 文件旁边或子目录
                potential_net_path = os.path.join(cfg_dir, "road.net.xml") # 尝试通用名称
                if not os.path.exists(potential_net_path):
                     # 尝试从 cfg 文件名推断 (例如 scene4.sumocfg -> scene4.net.xml)
                     base_name = os.path.splitext(os.path.basename(self.sumo_cfg))[0]
                     potential_net_path = os.path.join(cfg_dir, f"{base_name}.net.xml")
                
                if os.path.exists(potential_net_path):
                     self.net_path = potential_net_path
                else:
                     # 最终回退
                     self.net_path = os.path.join(os.path.dirname(self.sumo_cfg), "scene_4", "road.net.xml") # 回退到旧的默认值
                     if not os.path.exists(self.net_path):
                         logging.warning(f"无法自动推断 net 文件路径，将使用默认值: {self.net_path} (可能不正确)")
            except Exception:
                 self.net_path = "./scene_4/road.net.xml" # 最终的回退
                 logging.warning(f"推断 net 文件路径时出错，使用默认值: {self.net_path}")
        else:
            self.net_path = net_path


        # 数据结构
        self.df = None
        self.timeline: List[float] = []
        self.groups: Dict[float, List[Tuple[str, float, float, float]]] = {}
        self.created_vehicles = set() # [新] 跟踪已创建的车辆
        self.net = None

    def load(self):
        """加载 CSV，构建时间轴与分组；加载路网。"""
        if not os.path.isfile(self.csv_path):
            logging.error(f"未找到 CSV 文件: {self.csv_path}")
            raise FileNotFoundError(f"未找到 CSV: {self.csv_path}")

        try:
            self.df = pd.read_csv(self.csv_path)
            # [修改] 检查 'angle' 列
            required_cols = {"vehicle_id", "x", "y", "angle", "timestamp"} 
            if not required_cols.issubset(self.df.columns):
                missing = required_cols - set(self.df.columns)
                logging.error(f"CSV 文件 '{self.csv_path}' 列缺失，需要包含: {missing}")
                raise ValueError(f"CSV 列缺失，需包含: {required_cols}")

            self.df["timestamp"] = self.df["timestamp"].astype(float)
            self.df.sort_values(["timestamp", "vehicle_id"], inplace=True)
            self.df["ts_round"] = self.df["timestamp"].apply(lambda t: float(f"{t:.6f}"))
            self.timeline = sorted(self.df["ts_round"].unique().tolist())

            self.groups.clear()
            for ts, g in self.df.groupby("ts_round"):
                # [修改] 读取 'angle' 列
                records = list(zip(g["vehicle_id"], g["x"], g["y"], g["angle"])) 
                self.groups[ts] = records
            logging.info(f"成功加载并处理了 {len(self.df)} 行轨迹数据。时间轴包含 {len(self.timeline)} 个唯一时间点。")

        except Exception as e:
            logging.error(f"加载或处理 CSV '{self.csv_path}' 时出错: {e}", exc_info=True)
            raise

        # 加载路网
        if not os.path.isfile(self.net_path):
            logging.error(f"未找到 SUMO 路网文件: {self.net_path}")
            raise FileNotFoundError(f"未找到路网: {self.net_path}")
        try:
            self.net = sumolib.net.readNet(self.net_path)
            logging.info(f"成功加载路网文件: {self.net_path}")
        except Exception as e:
             logging.error(f"加载路网文件 '{self.net_path}' 时出错: {e}", exc_info=True)
             raise

    # [删除] start_sumo 不再需要，由全局 synchronization 处理

    def close(self):
        """关闭 TraCI 连接并清理 CARLA。"""
        logging.info("关闭仿真和连接...")
        try:
            # 尝试恢复 CARLA 设置 (如果需要)
            settings = carla_simulation.world.get_settings()
            settings.synchronous_mode = False
            settings.fixed_delta_seconds = None
            carla_simulation.world.apply_settings(settings)
            logging.info("已恢复 CARLA 为异步模式。")
        except Exception as e:
            logging.warning(f"恢复 CARLA 设置时出错: {e}")

        # 清理同步器中的 actors (如果 synchronization 对象可用)
        if 'synchronization' in globals() and synchronization:
            try:
                logging.info("正在销毁同步的 actors...")
                # Destroying synchronized actors.
                # 使用 list() 避免在迭代时修改字典大小
                carla_ids_to_destroy = list(synchronization.sumo2carla_ids.values())
                for carla_actor_id in carla_ids_to_destroy:
                    carla_simulation.destroy_actor(carla_actor_id)
                
                sumo_ids_to_destroy = list(synchronization.carla2sumo_ids.values())
                for sumo_actor_id in sumo_ids_to_destroy:
                    sumo_simulation.destroy_actor(sumo_actor_id)
                logging.info("同步 actors 销毁完成。")
            except Exception as e:
                logging.warning(f"销毁同步 actors 时出错: {e}")

        # 关闭 SUMO 和 CARLA 客户端 (如果它们可用)
        if 'carla_simulation' in globals() and carla_simulation:
            carla_simulation.close()
        if 'sumo_simulation' in globals() and sumo_simulation:
            sumo_simulation.close() # 这会处理 traci.close()
        logging.info("仿真客户端已关闭。")


    def run(self):
        """执行全流程：加载数据，按时间轴重放轨迹。"""
        try:
            self.load()
            
            # 短暂延迟确保 TraCI 完全就绪
            if self.start_delay > 0:
                time.sleep(self.start_delay)

            # --- [修改] 确保仿真时间从 0 开始或同步到第一个轨迹点 ---
            sim_time = traci.simulation.getTime()
            first_ts = self.timeline[0] if self.timeline else 0.0
            
            # 如果仿真时间超前于第一个轨迹点 (可能由于之前的操作), 记录警告
            if sim_time > first_ts + 1e-6:
                 logging.warning(f"仿真时间 ({sim_time:.2f}s) 已超过第一个轨迹点 ({first_ts:.2f}s)。将从当前时间开始匹配。")
            
            # 如果仿真时间落后，推进到第一个轨迹点之前
            while sim_time + self.step_length < first_ts:
                logging.debug(f"推进仿真时间从 {sim_time:.2f}s 到达第一个轨迹点 {first_ts:.2f}s...")
                synchronization.tick()
                sim_time = traci.simulation.getTime()
            # ----------------------------------------------------
            
            logging.info("开始重放轨迹...")
            for ts in self.timeline:
                # 对齐仿真时间到 ts
                sim_time = traci.simulation.getTime()
                while sim_time + 1e-6 < ts: # 使用小容差比较浮点数
                    # logging.debug(f"Sim Time: {sim_time:.3f}, Target TS: {ts:.3f}. Ticking...")
                    synchronization.tick()
                    sim_time = traci.simulation.getTime()
                    # 安全检查，防止死循环
                    if sim_time > ts + self.step_length * 2:
                         logging.warning(f"仿真时间 ({sim_time:.2f}s) 大幅超过目标时间戳 ({ts:.2f}s)，可能存在同步问题。跳过对齐。")
                         break

                # 检查当前时间戳是否有数据
                if ts not in self.groups:
                    logging.warning(f"时间戳 {ts:.2f} 在 self.groups 中没有找到数据，跳过此步。")
                    synchronization.tick() # 仍然 tick 一次以推进时间
                    continue

                # 当前时间戳下移动所有车辆
                vehicles_in_this_step = set()
                for veh_id, x, y, angle_sumo in self.groups[ts]:
                    vehicles_in_this_step.add(veh_id)
                    # 确保车辆存在并设置模式/颜色 (如果首次出现)
                    self._ensure_vehicle_exists(veh_id, float(x), float(y), float(angle_sumo))
                    # 移动车辆
                    self._move_vehicle_xy(veh_id, float(x), float(y), float(angle_sumo))

                update_driver_spectator(carla_simulation.world, synchronization, 'subject_car_01')

                # [可选] 移除在此时间戳未出现的、之前创建的车辆 (如果需要精确匹配CSV中的车辆存在)
                # vehicles_to_remove = self.created_vehicles - vehicles_in_this_step
                # for vid_remove in vehicles_to_remove:
                #     try:
                #         traci.vehicle.remove(vid_remove)
                #         self.created_vehicles.remove(vid_remove)
                #         logging.info(f"t={ts:.2f}s, 移除车辆 {vid_remove} (CSV中不再出现)")
                #     except traci.TraCIException:
                #         pass # 可能已经被移除

                # 推进一步让位置生效并同步 CARLA
                synchronization.tick()

                # 简单的进度日志
                if len(self.timeline) > 10 and self.timeline.index(ts) % (len(self.timeline) // 10) == 0:
                     progress = (self.timeline.index(ts) + 1) / len(self.timeline) * 100
                     logging.info(f"重放进度: {progress:.0f}% (t={ts:.2f}s)")

            logging.info("轨迹重放完成。")

        except FileNotFoundError:
             logging.error("启动失败：必要的 CSV 或路网文件未找到。")
        except traci.TraCIException as e:
             logging.error(f"TraCI 连接错误: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"重放过程中发生未知错误: {e}", exc_info=True)
        finally:
            self.close()

    # -------------------- 内部方法 --------------------

    # [修改] _ensure_vehicle_exists 添加颜色和模式设置
    def _ensure_vehicle_exists(self, veh_id: str, x: float, y: float, angle_sumo: float):
        """
        确保车辆在仿真中存在，并设置颜色和控制模式。
        """
        if veh_id in self.created_vehicles: # 使用 self.created_vehicles 跟踪
            # 如果已创建，仍然检查一下模式，以防被意外修改
            try:
                if veh_id in traci.vehicle.getIDList(): # 再次确认它还在SUMO里
                    if traci.vehicle.getSpeedMode(veh_id) != 32:
                        traci.vehicle.setSpeedMode(veh_id, 32)
                    if traci.vehicle.getLaneChangeMode(veh_id) != 0:
                        traci.vehicle.setLaneChangeMode(veh_id, 0)
            except traci.TraCIException:
                 if veh_id in self.created_vehicles: self.created_vehicles.remove(veh_id) # 从跟踪集合中移除
                 # logging.warning(f"检查车辆 {veh_id} 模式时发现其已离开仿真。")
            return

        # --- 车辆首次创建 ---
        # 寻找最近边
        edge_id = ""
        try:
            edge, _ = self._get_closest_edge(x, y)
            edge_id = edge.getID()
        except Exception as e:
            logging.warning(f"为车辆 {veh_id} 查找最近边失败: {e}. 将尝试使用空 edgeID。")
            # 仍然可以尝试 moveToXY(edgeID="")

        # 准备路线 ID
        route_id = f"route__{veh_id}" # 使用车辆ID确保唯一性
        if route_id not in traci.route.getIDList():
            try:
                edge_to_use = edge_id if edge_id else (self.net.getEdges()[0].getID() if self.net.getEdges() else "") # 回退到第一个边
                if edge_to_use:
                     traci.route.add(route_id, [edge_to_use])
                else:
                     logging.error("路网中没有任何边，无法创建路由！")
                     return # 无法继续
            except Exception as e:
                 logging.error(f"为车辆 {veh_id} 创建路由失败: {e}")
                 return

        # --- 获取 vType ---
        vType_to_use = "DEFAULT_VEHTYPE" 
        if hasattr(self, 'df') and not self.df[self.df['vehicle_id'] == veh_id].empty:
             first_row = self.df[self.df['vehicle_id'] == veh_id].iloc[0]
             vType_to_use = first_row.get('vType', 'DEFAULT_VEHTYPE')
        
        # 确保车辆类型存在
        if vType_to_use not in traci.vehicletype.getIDList():
             logging.warning(f"车辆类型 '{vType_to_use}' 未在SUMO中预定义。尝试复制 'DEFAULT_VEHTYPE' 或 'passenger'...")
             base_type = "DEFAULT_VEHTYPE" if "DEFAULT_VEHTYPE" in traci.vehicletype.getIDList() else "passenger"
             try:
                 traci.vehicletype.copy(base_type, vType_to_use)
                 logging.info(f"已复制基础类型 '{base_type}' 创建新类型 '{vType_to_use}'")
             except traci.TraCIException as e_type:
                 logging.error(f"无法复制车辆类型 '{base_type}' 来创建 '{vType_to_use}': {e_type}。将强制使用 '{base_type}'。")
                 if base_type not in traci.vehicletype.getIDList():
                     logging.critical(f"连基础类型 '{base_type}' 都不存在！请检查SUMO配置。")
                     return # 无法创建车辆
                 vType_to_use = base_type


        # --- [新] 定义规划车辆 ID 集合 ---
        planned_ids = {"subject_car_01", "lead_truck_01", "lead_truck_02"}
        # ---------------------------------

        try:
            # 创建车辆
            traci.vehicle.add(
                vehID=veh_id, 
                routeID=route_id,
                typeID=vType_to_use 
                # depart 参数在这里不重要，因为会被 moveToXY 覆盖
            )
            self.created_vehicles.add(veh_id) # 添加到跟踪集合
            logging.info(f"在时间 {traci.simulation.getTime():.2f}s 创建车辆 {veh_id} (类型: {vType_to_use})")

            # --- [新] 设置颜色 ---
            if veh_id == "subject_car_01":
                traci.vehicle.setColor(veh_id, (0, 0, 255, 255)) # 蓝色
                logging.info(f"设置车辆 {veh_id} 颜色为蓝色 (规划主车)")
            elif veh_id in planned_ids:
                traci.vehicle.setColor(veh_id, (255, 0, 0, 255)) # 红色
                logging.info(f"设置车辆 {veh_id} 颜色为红色 (参与规划)")
            # else: 背景车辆使用默认颜色

            # --- [新] 设置控制模式 ---
            traci.vehicle.setSpeedMode(veh_id, 32)
            traci.vehicle.setLaneChangeMode(veh_id, 0)
            traci.vehicle.setSpeed(veh_id, 0.0) # 初始速度设为0，由 moveToXY 控制

        except traci.TraCIException as e:
            # 如果车辆已存在 (例如，从 state 文件加载)，add 会失败，但没关系
            if "Vehicle '" + veh_id + "' already exists" in str(e):
                 if veh_id not in self.created_vehicles: # 如果是第一次遇到已存在的车
                     self.created_vehicles.add(veh_id)
                     logging.info(f"车辆 {veh_id} 已存在于仿真中 (可能从 state 加载)。")
                     # 仍然尝试设置颜色和模式
                     try:
                         if veh_id == "subject_car_01": traci.vehicle.setColor(veh_id, (0, 0, 255, 255))
                         elif veh_id in planned_ids: traci.vehicle.setColor(veh_id, (255, 255, 0, 255))
                         traci.vehicle.setSpeedMode(veh_id, 32)
                         traci.vehicle.setLaneChangeMode(veh_id, 0)
                     except traci.TraCIException as e_set:
                          logging.warning(f"为已存在的车辆 {veh_id} 设置颜色/模式失败: {e_set}")
            else:
                 logging.error(f"创建车辆 {veh_id} 时出错: {e}")
                 return 

        # 初始放置 (理论上应该在 add 之后立即执行一次，确保位置正确)
        # self._move_vehicle_xy(veh_id, x, y, angle_sumo) # 移动操作在 run 循环的主体中进行

    # [修改] _get_closest_edge (基本保持不变)
    def _get_closest_edge(self, x: float, y: float) -> Tuple[sumolib.net.edge.Edge, float]:
        """返回 (edge, distance)。"""
        if not self.net:
             raise RuntimeError("SUMO 路网未加载 (self.net is None)")
        # 使用 net.getNeighboringEdges 更通用，因为它返回距离
        radius = 50.0 # 搜索半径
        candidates = self.net.getNeighboringEdges(x, y, r=radius)
        if not candidates:
            # 尝试扩大搜索半径
            radius = 200.0
            candidates = self.net.getNeighboringEdges(x, y, r=radius)
            if not candidates:
                 raise RuntimeError(f"在 ({x:.2f}, {y:.2f}) 附近 {radius}m 内未找到任何道路边。")
        
        # candidates 是 List[(edge, distance)]
        best_edge, min_dist = min(candidates, key=lambda item: item[1])
        return best_edge, min_dist

    # [修改] _move_vehicle_xy 使用 angle_sumo
    def _move_vehicle_xy(self, veh_id: str, x: float, y: float, angle_sumo: float):
        """
        使用 TraCI 将车辆移动到 (x,y) 并设置角度 (SUMO 角度)。
        """
        angle_deg = angle_sumo # 直接使用 SUMO 角度

        # 优先使用较新的 moveToXY (laneIndex=-1 自动匹配)
        try:
            traci.vehicle.moveToXY(veh_id, edgeID="", laneIndex=-1, x=x, y=y, angle=angle_deg, keepRoute=2)
        except TypeError: 
            # 兼容旧 TraCI 签名
            logging.warning("moveToXY 不支持命名参数或 laneIndex=-1，尝试旧版调用 (可能不太准确)")
            try:
                edge, _ = self._get_closest_edge(x, y) 
                edge_id = edge.getID()
                # 获取车道索引可能需要更复杂的几何计算，这里简化为0
                lane_index = 0 
                traci.vehicle.moveToXY(veh_id, edge_id, lane_index, x, y, angle_deg, 2)
            except Exception as e_inner:
                 logging.error(f"旧版 moveToXY 调用也失败 for {veh_id}: {e_inner}")
        except traci.TraCIException as e:
             if "is not known" not in str(e): # 忽略车辆已离开的错误
                  logging.warning(f"moveToXY 失败 {veh_id}: {e}")

# -------------------- 主程序入口 --------------------
if __name__ == "__main__":
    logging.info("启动 TrajectoryExecutor...")
    # [修改] 使用修改后的 CSV 文件名
    executor = TrajectoryExecutor(
        csv_path="D:\BIT\code\SwarmPlanner\planning_demo_new\mutil_vehicle\\planned_trajectories_lc_offline.csv",
        # 其他参数使用 config.py 或默认值
        start_delay=0.2,
    )
    executor.run()
    logging.info("TrajectoryExecutor 执行完毕。")