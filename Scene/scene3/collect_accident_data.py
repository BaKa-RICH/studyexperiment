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
    last_accident_time = 0  # 上次触发事故的时间
    decelerating_vehicles = {}  # 正在减速的车辆 {vehicle_id: decel_end_time}

    client = carla_simulation.client
    world =carla_simulation.world


    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)


    while True:
        try:
            current_time = traci.simulation.getTime()

            # 同步仿真
            synchronization.tick()

            for veh_id in traci.vehicle.getIDList():
                try:
                    # 设置速度模式为0: 完全忽略安全规则
                    traci.vehicle.setSpeedMode(veh_id, 00000)

                    # 设置换道模式为0: 禁止所有换道行为
                    traci.vehicle.setLaneChangeMode(veh_id, 0)
                except traci.TraCIException:
                    pass  # 车辆可能已离开仿

            # 1. 处理正在减速的车辆
            completed_decel = []
            for veh_id, end_time in decelerating_vehicles.items():
                if current_time >= end_time:
                    # 减速结束，恢复正常行驶
                    try:
                        traci.vehicle.setSpeed(veh_id, -1)  # -1表示恢复默认速度
                        completed_decel.append(veh_id)
                    except traci.TraCIException:
                        pass  # 车辆可能已离开仿真

            # 移除已完成减速的车辆
            for veh_id in completed_decel:
                decelerating_vehicles.pop(veh_id, None)

            # 2. 每50秒触发新的事故
            if current_time - last_accident_time >= 30:
                last_accident_time = current_time

                # 获取目标路段上的车辆
                target_edges = ["1#0", "16#0"]
                target_vehicles = []
                for edge in target_edges:
                    try:
                        target_vehicles.extend(traci.edge.getLastStepVehicleIDs(edge))
                    except traci.TraCIException:
                        continue

                if target_vehicles:
                    # 随机选择70%的车辆进行减速
                    num_to_decel = int(len(target_vehicles) * 0.9)
                    vehicles_to_decel = random.sample(target_vehicles, num_to_decel)

                    for veh_id in vehicles_to_decel:
                        try:
                            # 设置车辆以5m/s²减速，持续5秒
                            current_speed = traci.vehicle.getSpeed(veh_id)
                            traci.vehicle.slowDown(veh_id, max(0, current_speed - 20), 10)  # 5秒减速25m/s
                            decelerating_vehicles[veh_id] = current_time + 10
                        except traci.TraCIException:
                            pass  # 车辆可能已离开仿真

            # 3. 记录数据
            recorder.record_vehicle_state(current_time)
            recorder.record_collisions(current_time)
        except:
            all_actors = world.get_actors()
            vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
            sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
            client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
            settings.synchronous_mode = False
            world.apply_settings(settings)


if __name__ == "__main__":
    main()