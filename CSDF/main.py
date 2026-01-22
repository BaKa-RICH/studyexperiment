import traci
import logging
import time
from config import *
import sumolib

import sys
import os

# 获取当前文件所在目录（CSDF目录）
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取CSDF的父目录
parent_dir = os.path.dirname(current_dir)

# 将父目录添加到 Python 路径，这样CSDF就能被识别为包
sys.path.insert(0, parent_dir)

from modules.CavMonitor.monitor import SceneMonitor
from modules.BehaviorPlanning.CSDF import BehaviorPlanningSystem
from modules.TrajectoryPlanning.BazierTrajectory import TrajectoryGenerator
from modules.TrajectoryExecutor.TrajectoryExecutor import TrajectoryExecutor
from core.CoordinateTransform import CartesianFrenetConverter

#sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
#                                 sumo_port, sumo_gui, client_order)
#carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

#synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager,
#                                            sync_vehicle_color, sync_vehicle_lights)

# 初始化多车协同轨迹规划器和相关变量


sumo_binary = sumolib.checkBinary("sumo-gui")  #
sumocfg = os.path.join(os.path.dirname(__file__), "scene_4", "scene4.sumocfg")

cmd = [sumo_binary, "-c", sumocfg]
traci.start(cmd)


converter = CartesianFrenetConverter(traci.lane.getShape("-2_3"))

cav_ids = ["cav_3_0", "cav_2_0", "cav_2_1"]

SM = SceneMonitor(cav_ids)
BP = BehaviorPlanningSystem(converter)
TP = TrajectoryGenerator(converter,delta_t=2.0, dt=0.05)
TE = TrajectoryExecutor()

logging.basicConfig(level=logging.INFO)

try:
    while True:
        start = time.time()
        current_time = traci.simulation.getTime()

        #synchronization.tick()
        traci.simulationStep()


        # 制造激进行为
        if current_time > 3:
            for cav_id in cav_ids:
                traci.vehicle.setSpeedMode(cav_id , 0)
                traci.vehicle.setLaneChangeMode(cav_id, 0)

        if  current_time >= 5:
            traci.vehicle.setLaneChangeMode("hdv_3_0", 0)
            traci.vehicle.setSpeedMode("hdv_3_0", 0)
            traci.vehicle.setSpeed("hdv_3_0", 10)

        if 10 >= current_time >= 5:
            traci.vehicle.setSpeed("cav_3_0" , 28)

        # 实时检测车辆并收集数据
        SM.update()
        HDVs = SM.regular_vehicles
        CAVs = SM.cav_vehicles
        potential_decisions_dict = SM.potential_region

        if current_time > 5 and  CAVs["cav_3_0"].lane_id == "-2_3":
            potential_decisions_dict["cav_3_0"] = [2, 5]

        # 检测到TTC危险，启动算法，每个TTC危险的车和附近的CAV检测风险场。
        # 检测到风险，行为规划 和 轨迹规划, 假设只有一个高风险
        for cav in CAVs.values():
            if cav.risk_level.value == 3 or cav.risk_level.value == 4 :
                bp_tp_start_time = time.time()
                BehaviorPlanningOutput = BP.plan_behavior(current_time , HDVs , CAVs , potential_decisions_dict)
                bp_end_time = time.time()
                logging.info(f"Behavior planning computation time is {bp_end_time - bp_tp_start_time}")

                TrajectoryOutput = TP.generate_trajectories(behavior_output=BehaviorPlanningOutput,cav_vehicles=CAVs, base_timestamp=current_time)
                tp_end_time = time.time()
                logging.info(f"Trajectory Planning computation time is {tp_end_time - bp_end_time}")

        #对有规划轨迹的车，轨迹执行
        TE.execute(CAVs)

        #冲突检测与执行
        #TODO：

        #更新场景监控器中的规划信息
        for cav_id in CAVs.keys():
            cav = CAVs[cav_id]
            SM.set_cav_planned(cav_id, cav.isPlanned)
            SM.set_cav_trajectory(cav_id, cav.planned_trajectory)


        end = time.time()
        elapsed = end - start
        if elapsed < step_length:
            time.sleep(step_length - elapsed)

except KeyboardInterrupt:
    logging.info('Cancelled by user.')

finally:
    logging.info('Cleaning synchronization')
    #synchronization.close()
    traci.close()
