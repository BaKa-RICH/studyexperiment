import traci 
import sumolib
from ..run_synchronization import *
import logging
import time
import numpy as np
from config import *
from trajectory_plannner_multi import MultiVehicleTrajectoryPlanner, ForewarnOutput, TrafficElementSimple, RiskElement, RiskLevel, Decision
import csv


sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                     sumo_port, sumo_gui, client_order)
carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager,
                                                sync_vehicle_color, sync_vehicle_lights)

# 初始化多车协同轨迹规划器和相关变量
trajectory_planner = MultiVehicleTrajectoryPlanner()
vehicle_history = {}  # 存储车辆历史数据
last_planning_time = 0.0
planning_interval = 1  # 每1秒调用一次轨迹规划

try:
    while True:
        start = time.time()
        current_time = traci.simulation.getTime()
        
        synchronization.tick()

        # 实时检测车辆并收集数据
        vehicle_ids = traci.vehicle.getIDList()
        all_elements = {}
        
        for vehicle_id in vehicle_ids:
            try:
                current_time = traci.simulation.getTime()
                # 获取车辆基本信息
                position = traci.vehicle.getPosition(vehicle_id)
                angle = traci.vehicle.getAngle(vehicle_id)

                angle_rad = np.deg2rad(90 - angle)
                speed = traci.vehicle.getSpeed(vehicle_id)
                acceleration = traci.vehicle.getAcceleration(vehicle_id)
                edge_id = traci.vehicle.getRoadID(vehicle_id)
                lane_id = traci.vehicle.getLaneID(vehicle_id)
                
                # 计算速度和加速度分量
                #angle_rad = np.radians(angle)
                vx = speed * np.cos(angle_rad)
                vy = speed * np.sin(angle_rad)
                ax = acceleration * np.cos(angle_rad)
                ay = acceleration * np.sin(angle_rad)
                
                # 创建交通要素
                traffic_element = TrafficElementSimple(
                    element_id=vehicle_id,
                    location=(position[0], position[1]),
                    heading=(angle,),
                    velocity=(vx, vy),
                    acceleration=(ax, ay),
                    edge_id=edge_id,
                    lane_id=lane_id
                )
                all_elements[vehicle_id] = traffic_element
                
                # 存储历史轨迹数据
                if vehicle_id not in vehicle_history:
                    vehicle_history[vehicle_id] = []
                
                vehicle_history[vehicle_id].append([position[0], position[1], angle, current_time])
                
                # 保持历史数据在合理范围内（最近50个点）
                if len(vehicle_history[vehicle_id]) > 50:
                    vehicle_history[vehicle_id] = vehicle_history[vehicle_id][-50:]
                    
            except Exception as e:
                logging.error(f"获取车辆 {vehicle_id} 数据失败: {e}")
        
        # 每0.5秒执行一次轨迹规划
        if current_time - last_planning_time >= planning_interval:
            try:
                # 多车协同风险检测逻辑
                risk_elements = []
                vehicle_list = list(all_elements.keys())
                
                # 检测车辆间的相互影响和风险
                for vehicle_id, element in all_elements.items():
                    #speed_magnitude = np.sqrt(element.velocity[0]**2 + element.velocity[1]**2)
                    #accel_magnitude = np.sqrt(element.acceleration[0]**2 + element.acceleration[1]**2)
                    
                    # 检查是否为高风险车辆
                    is_high_risk = False

                    if vehicle_id == "audi1":
                        risk_level = RiskLevel.HIGH
                        decision = Decision.LEFT_LANE_CHANGE

                    else :
                        risk_level = RiskLevel.MEDIUM
                        decision = Decision.LANE_KEEPING

                    pred_points = []
                    for i in range(50):  # 预测5秒（50个0.1s间隔的点）
                        t = (i + 1) * 0.1
                        pred_x = element.location[0] + element.velocity[0] * t
                        pred_y = element.location[1] + element.velocity[1] * t
                        pred_heading = element.heading[0]
                        pred_points.append([pred_x, pred_y, pred_heading])
                    predicted_traj = np.array(pred_points, dtype=np.float64)

                    related_vehicles = [vid for vid in vehicle_list if vid != vehicle_id]

                    risk_element = RiskElement(
                        element_id=vehicle_id,
                        risk_level=risk_level,
                        related_risk_elements=related_vehicles,
                        history_trajectory=vehicle_history[vehicle_id],
                        predicted_trajectory=predicted_traj,
                        planned_trajectory=np.array([[0, 0, 0]], dtype=np.float64),  # 占位符
                        decision=decision
                    )
                    risk_elements.append(risk_element)

                    # 基于速度和加速度的风险判断
                    # if speed_magnitude > 15.0 or accel_magnitude > 2.0:
                    #     # 检查与其他车辆的距离和相对速度
                    #     for other_id, other_element in all_elements.items():
                    #         if other_id == vehicle_id:
                    #             continue
                    #
                    #         # 计算车辆间距离
                    #         dx = element.location[0] - other_element.location[0]
                    #         dy = element.location[1] - other_element.location[1]
                    #         distance = np.sqrt(dx**2 + dy**2)
                    #
                    #         # 计算相对速度
                    #         rel_vx = element.velocity[0] - other_element.velocity[0]
                    #         rel_vy = element.velocity[1] - other_element.velocity[1]
                    #         rel_speed = np.sqrt(rel_vx**2 + rel_vy**2)
                    #
                    #         # 如果距离较近且相对速度较大，则认为是高风险
                    #         if distance < 30.0 and rel_speed > 5.0:
                    #             is_high_risk = True
                    #
                    #             # 根据车辆ID和位置关系决定变道策略
                    #             if vehicle_id == "audi1":
                    #                 decision = Decision.LEFT_LANE_CHANGE
                    #             elif vehicle_id == "audi2":
                    #                 decision = Decision.RIGHT_LANE_CHANGE
                    #             elif vehicle_id == "audi3":
                    #                 decision = Decision.LANE_KEEPING
                    #             break
                    
                    # 如果是高风险车辆，创建风险要素
                    # if is_high_risk or speed_magnitude > 20.0:
                    #     # 生成历史轨迹数组
                    #     if vehicle_id in vehicle_history and len(vehicle_history[vehicle_id]) > 0:
                    #         history_traj = np.array(vehicle_history[vehicle_id], dtype=np.float64)
                    #     else:
                    #         history_traj = np.array([[element.location[0], element.location[1], element.heading[0]]], dtype=np.float64)
                    #
                    #     # 生成预测轨迹（基于当前速度的线性预测）
                    #     pred_points = []
                    #     for i in range(50):  # 预测5秒（50个0.1s间隔的点）
                    #         t = (i + 1) * 0.1
                    #         pred_x = element.location[0] + element.velocity[0] * t
                    #         pred_y = element.location[1] + element.velocity[1] * t
                    #         pred_heading = element.heading[0]
                    #         pred_points.append([pred_x, pred_y, pred_heading])
                    #     predicted_traj = np.array(pred_points, dtype=np.float64)
                    #
                    #     # 确定风险等级
                    #     if speed_magnitude > 25.0 or accel_magnitude > 4.0:
                    #         risk_level = RiskLevel.CRITICAL
                    #     elif speed_magnitude > 20.0 or accel_magnitude > 3.0:
                    #         risk_level = RiskLevel.HIGH
                    #     else:
                    #         risk_level = RiskLevel.MEDIUM
                        
                        # # 获取相关风险车辆（除自己外的其他车辆）
                        # related_vehicles = [vid for vid in vehicle_list if vid != vehicle_id]
                        #
                        # risk_element = RiskElement(
                        #     element_id=vehicle_id,
                        #     risk_level=risk_level,
                        #     related_risk_elements=related_vehicles,
                        #     history_trajectory=history_traj,
                        #     predicted_trajectory=predicted_traj,
                        #     planned_trajectory=np.array([[0, 0, 0]], dtype=np.float64),  # 占位符
                        #     decision=decision
                        # )
                        # risk_elements.append(risk_element)
                
                # 如果有风险要素，调用轨迹规划器
                if risk_elements:
                    forewarn_output = ForewarnOutput(
                        timestamp=current_time,
                        all_elements=all_elements,
                        risk_elements=risk_elements
                    )
                    risk_num = 0
                    for element in risk_elements:
                        if element.risk_level == RiskLevel.HIGH or element.risk_level == RiskLevel.CRITICAL:
                            risk_num += 1
                    if risk_num > 0:
                        logging.info(f"检测到 {risk_num} 个风险要素，开始轨迹规划")
                        planned_trajectories = trajectory_planner.plan_trajectories(forewarn_output)
                    
                    if planned_trajectories:
                        logging.info(f"成功规划了 {len(planned_trajectories)} 条轨迹")

                        # 保存多车协同规划结果
                        with open("planned_trajectories_multi_vehicle.csv", mode="w", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow(["vehicle_id", "x", "y", "heading", "timestamp"])
                            for veh_id, traj in planned_trajectories.items():
                                for (x, y, heading, t) in traj:
                                    writer.writerow([veh_id, x, y, heading, t])

                        logging.info(f"多车协同规划结果: {planned_trajectories}")
                        
                        # 可视化多车轨迹（可选）
                        for vehicle_id, trajectory in planned_trajectories.items():
                            logging.debug(f"车辆 {vehicle_id} 的协同规划轨迹包含 {len(trajectory)} 个点")
                            
                            # 为每辆车使用不同颜色显示轨迹
                            if vehicle_id == "audi1":
                                color = (255, 0, 0, 255)  # 红色
                            elif vehicle_id == "audi2":
                                color = (0, 255, 0, 255)  # 绿色
                            elif vehicle_id == "audi3":
                                color = (0, 0, 255, 255)  # 蓝色
                            else:
                                color = (255, 255, 0, 255)  # 黄色
                            
                            # 可以取消注释以在SUMO中显示轨迹
                            # xy_points = [(x, y) for (x, y, heading, t) in trajectory]
                            # polygon_id = f"waypoints_{vehicle_id}"
                            # traci.polygon.add(polygon_id, xy_points, color=color, fill=False)
                    else:
                        logging.info("未生成任何规划轨迹")
                else:
                    logging.debug("未检测到风险要素")
                    
                last_planning_time = current_time
                
            except Exception as e:
                logging.error(f"轨迹规划过程出错: {e}")

        end = time.time()
        elapsed = end - start
        if elapsed < step_length:
            time.sleep(step_length - elapsed)

except KeyboardInterrupt:
    logging.info('Cancelled by user.')

finally:
    logging.info('Cleaning synchronization')
    synchronization.close()


