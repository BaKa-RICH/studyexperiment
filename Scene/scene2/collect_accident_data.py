import carla
import argparse
import traci
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
import os
import csv
import time
import random

# 在循环前添加时间格式化函数
def format_time(t):
    """保留4位小数的浮点数格式化"""
    return round(t, 4)

class SumoDataRecorder:
    def __init__(self):
        # 创建输出目录
        self.output_dir = "sumo_data"
        os.makedirs(self.output_dir, exist_ok=True)

        # 创建CSV文件
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.vehicle_file = open(f"{self.output_dir}/vehicle_trace_{timestamp}.csv", "w", newline='')
        self.collision_file = open(f"{self.output_dir}/collisions_{timestamp}.csv", "w", newline='')

        # 创建CSV写入器
        self.vehicle_writer = csv.writer(self.vehicle_file)
        self.collision_writer = csv.writer(self.collision_file)

        # 写入表头
        self.vehicle_writer.writerow([
            "timestamp", "vehicle_id", "x", "y","vType", "speed", "angle",
            "acceleration", "lane_id", "edge_id"
        ])
        self.collision_writer.writerow([
            "timestamp", "collision_id", "vehicle1", "vehicle2",
            "collision_type"
        ])

        # 碰撞计数器
        self.collision_counter = 0
        self.recorded_collisions = set()

    def record_vehicle_state(self, timestamp):
        """记录所有车辆的状态"""
        for vehicle_id in traci.vehicle.getIDList():
            try:
                pos = traci.vehicle.getPosition(vehicle_id)
                speed = traci.vehicle.getSpeed(vehicle_id)
                angle = traci.vehicle.getAngle(vehicle_id)
                accel = traci.vehicle.getAcceleration(vehicle_id)
                lane_id = traci.vehicle.getLaneID(vehicle_id)
                edge_id = traci.vehicle.getRoadID(vehicle_id)
                vType = traci.vehicle.getTypeID(vehicle_id)

                self.vehicle_writer.writerow([
                    timestamp, vehicle_id, pos[0], pos[1],
                    vType,speed, angle, accel, lane_id, edge_id
                ])
            except traci.TraCIException:
                # 车辆可能已离开仿真
                continue

    def record_collisions(self, timestamp):
        """检测并记录碰撞事件"""
        collisions = traci.simulation.getCollisions()

        for collision in collisions:
            # 生成唯一的碰撞ID
            collision_id = f"collision_{self.collision_counter}"
            self.collision_counter += 1

            # 提取碰撞信息
            collider = collision.collider
            victim = collision.victim
            collision_type = collision.type

            # 避免重复记录同一碰撞
            collision_key = (collider, victim, collision_type)
            if collision_key in self.recorded_collisions:
                continue

            self.recorded_collisions.add(collision_key)

            self.collision_writer.writerow([
                timestamp, collision_id, collider, victim,
                collision_type
            ])

    def close(self):
        """关闭所有文件"""
        self.vehicle_file.close()
        self.collision_file.close()
def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('--sumo_cfg_file', type=str, help='sumo configuration file', default="collect_accident_data_rou/simulation.sumocfg")
    argparser.add_argument('--carla-host',metavar='H',default='127.0.0.1',help='IP of the carla host server (default: 127.0.0.1)')
    argparser.add_argument('--carla-port',metavar='P',default=2000,type=int,help='TCP port to listen to (default: 2000)')
    argparser.add_argument('--sumo-host',metavar='H',default=None,help='IP of the sumo host server (default: 127.0.0.1)')
    argparser.add_argument('--sumo-port',metavar='P',default=None,type=int,help='TCP port to listen to (default: 8813)')
    argparser.add_argument('--sumo-gui', default=True, action='store_true', help='run the gui version of sumo')
    argparser.add_argument('--step-length',default=0.05,type=float,help='set fixed delta seconds (default: 0.05s)')
    argparser.add_argument('--client-order',metavar='TRACI_CLIENT_ORDER',default=1,type=int,help='client order number for the co-simulation TraCI connection (default: 1)')
    argparser.add_argument('--sync-vehicle-lights',action='store_true',help='synchronize vehicle lights state (default: False)')
    argparser.add_argument('--sync-vehicle-color',action='store_true',help='synchronize vehicle color (default: False)')
    argparser.add_argument('--sync-vehicle-all',action='store_true',help='synchronize all vehicle properties (default: False)')
    argparser.add_argument('--tls-manager',type=str,choices=['none', 'sumo', 'carla'],help="select traffic light manager (default: none)",default='none')
    argparser.add_argument('--debug', action='store_true', help='enable debug messages')
    args = argparser.parse_args()

    # 初始化联合仿真
    sumo_simulation = SumoSimulation(args.sumo_cfg_file, args.step_length, args.sumo_host,args.sumo_port, args.sumo_gui, args.client_order)
    carla_simulation = CarlaSimulation(args.carla_host, args.carla_port, args.step_length)
    synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, args.tls_manager, args.sync_vehicle_color, args.sync_vehicle_lights)

    recorder = SumoDataRecorder()

    random.seed(42)

    #端口连接 找到蓝图
    client = carla_simulation.client
    world =carla_simulation.world
    settings = world.get_settings()
    step = 0
    time = 0
    while True:
        try:
            synchronization.tick()
            step += 1
            time = format_time(time + 0.05)
            # 用于跟踪每辆车的减速开始时间
            deceleration_start_times = {}
            maintain_speed_vehicles = set()  # 存储需要维持速度的车辆


            # 在主循环中替换 time >= 40 的代码块
            if time >= 100:
                # 仅在第一次满足 time >= 40 且未选择车辆时选择车辆
                if time == 100:
                    vehicle_ids = traci.vehicle.getIDList()
                    num_vehicles_to_maintain = max(1, int(len(vehicle_ids) * 0.2))  # 20% 的车辆维持速度
                    num_vehicles_to_decelerate = len(vehicle_ids) - num_vehicles_to_maintain  # 80% 的车辆减速
                    maintain_speed_vehicles = set(random.sample(vehicle_ids, min(num_vehicles_to_maintain, len(vehicle_ids))))
                    selected_vehicles = [vid for vid in vehicle_ids if vid not in maintain_speed_vehicles]  # 其余车辆减速
                    print(f"Step {step}: Selected vehicles for maintaining speed: {maintain_speed_vehicles}")
                    print(f"Step {step}: Selected vehicles for deceleration: {selected_vehicles}")

                # 当前仿真时间
                current_time = time

                # 处理维持速度的车辆 (20%)
                for veh_id in maintain_speed_vehicles.copy():  # 使用副本以允许修改
                    if veh_id not in traci.vehicle.getIDList():  # 如果车辆已离开仿真
                        maintain_speed_vehicles.remove(veh_id)
                        print(f"Step {step}: Vehicle {veh_id} (maintain speed) has left the simulation")
                        continue
                    # 获取当前速度并维持
                    current_speed = traci.vehicle.getSpeed(veh_id)
                    traci.vehicle.setSpeed(veh_id, current_speed)
                    traci.vehicle.setLaneChangeMode(veh_id, 0b000000000000)
                    print(f"Step {step}: Vehicle {veh_id} maintains speed at {current_speed:.2f} m/s")

                # 处理减速车辆 (80%)
                for veh_id in selected_vehicles[:]:  # 使用副本以允许修改
                    if veh_id not in traci.vehicle.getIDList():  # 如果车辆已离开仿真
                        selected_vehicles.remove(veh_id)
                        deceleration_start_times.pop(veh_id, None)
                        print(f"Step {step}: Vehicle {veh_id} (decelerating) has left the simulation")
                        continue

                    # 获取车辆当前速度（单位：m/s）
                    current_speed = traci.vehicle.getSpeed(veh_id)

                    # 检查是否需要开始或继续减速
                    if veh_id not in deceleration_start_times and current_speed >= 15:
                        # 车辆速度 >= 15 m/s，开始减速并记录开始时间
                        traci.vehicle.setAcceleration(veh_id, -5.0, 1)  # 减速度 -5 m/s²，持续当前时间步（0.05s）
                        traci.vehicle.setLaneChangeMode(veh_id, 0b000000000000)
                        deceleration_start_times[veh_id] = current_time
                        print(f"Step {step}: Vehicle {veh_id} set acceleration to -5.00 m/s²")
                    elif veh_id in deceleration_start_times:
                        # 检查减速持续时间是否超过 10 秒
                        if current_time - deceleration_start_times[veh_id] >= 10:
                            # 超过 10 秒，停止减速
                            traci.vehicle.setAcceleration(veh_id, 0.0, 1)
                            selected_vehicles.remove(veh_id)
                            deceleration_start_times.pop(veh_id)
                            print(f"Step {step}: Vehicle {veh_id} stopped deceleration (duration exceeded)")
                        # 检查速度是否低于 15 m/s
                        elif current_speed < 15:
                            # 速度低于 15 m/s，停止减速
                            traci.vehicle.setAcceleration(veh_id, 0.0, 1)
                            selected_vehicles.remove(veh_id)
                            deceleration_start_times.pop(veh_id)
                            print(f"Step {step}: Vehicle {veh_id} stopped deceleration (speed < 15 m/s)")
                        else:
                            # 继续施加减速度
                            traci.vehicle.setAcceleration(veh_id, -5.0, 1)
                            print(f"Step {step}: Vehicle {veh_id} continues deceleration at -5.00 m/s²")

            # 获取当前SUMO时间戳
            timestamp = traci.simulation.getTime()

            # 记录所有车辆状态
            #recorder.record_vehicle_state(timestamp)

            # 记录碰撞事件
            #recorder.record_collisions(timestamp)

        # 获取当前SUMO时间戳
            timestamp = traci.simulation.getTime()

        # 记录所有车辆状态
            #recorder.record_vehicle_state(timestamp)

        # 记录碰撞事件
            #recorder.record_collisions(timestamp)
        except:
            all_actors = world.get_actors()
            vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
            sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
            client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
            settings.synchronous_mode = False
            world.apply_settings(settings)

if __name__ == "__main__":
    main()
