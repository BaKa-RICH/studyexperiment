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
    #端口连接 找到蓝图
    client = carla_simulation.client
    world =carla_simulation.world
    settings = world.get_settings()
    step = 0
    forced_vehicles = set()
    while True:
        try:
            synchronization.tick()
            step += 1
                # 获取当前SUMO时间戳
            vehicle_ids = traci.vehicle.getIDList()

            for veh_id in vehicle_ids :
                    # 设置换道模式为0（禁止所有换道）
                current_edge = traci.vehicle.getRoadID(veh_id)
                if current_edge == "-9":
                        traci.vehicle.setLaneChangeMode(veh_id, 0b000000000000)
                # print(f"已禁用车辆 {veh_id} 的换道功能")
                if step % 100 == 0:
                    lane0_vehicles=[]
                    lane0_vehicles = [
                        veh_id for veh_id in traci.vehicle.getIDList()
                        if traci.vehicle.getRoadID(veh_id) == "-10"
                        and traci.vehicle.getLaneIndex(veh_id) == 1
                        and veh_id not in forced_vehicles
                    ]
                    if lane0_vehicles:
                        # 计算需要变道的车辆数量（至少1辆）
                        num_to_change = max(1, int(len(lane0_vehicles) * 1))
                        selected_vehicles = random.sample(lane0_vehicles, num_to_change)

                        for veh_id in selected_vehicles:
                            try:
                                traci.vehicle.setLaneChangeMode(veh_id, 0b100000000000)
                                traci.vehicle.changeSublane(veh_id, 2)  # 立即变道
                                forced_vehicles.add(veh_id)
                                print(f"Forced {veh_id} to change from lane 0 to 1 on edge -10")
                            except traci.TraCIException as e:
                                print(f"Lane change error for {veh_id}: {e}")




            timestamp = traci.simulation.getTime()

                # 记录所有车辆状态
            recorder.record_vehicle_state(timestamp)

                # 记录碰撞事件
            recorder.record_collisions(timestamp)

            # 获取当前SUMO时间戳
            timestamp = traci.simulation.getTime()

            # 记录所有车辆状态
            recorder.record_vehicle_state(timestamp)

            # 记录碰撞事件
            recorder.record_collisions(timestamp)
        except:
            all_actors = world.get_actors()
            vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
            sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
            client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
            settings.synchronous_mode = False
            world.apply_settings(settings)

if __name__ == "__main__":
    main()
