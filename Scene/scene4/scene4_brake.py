import carla
import argparse
import traci
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
import os
import csv
import time

# SumoDataRecorder 类
class SumoDataRecorder:
    def __init__(self):
        self.output_dir = "sumo_data"
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.vehicle_file = open(f"{self.output_dir}/vehicle_trace_{timestamp}.csv", "w", newline='')
        self.collision_file = open(f"{self.output_dir}/collisions_{timestamp}.csv", "w", newline='')
        self.vehicle_writer = csv.writer(self.vehicle_file)
        self.collision_writer = csv.writer(self.collision_file)
        self.vehicle_writer.writerow(["timestamp", "vehicle_id", "x", "y","vType", "speed", "angle", "acceleration", "lane_id", "edge_id"])
        self.collision_writer.writerow(["timestamp", "collision_id", "vehicle1", "vehicle2", "collision_type"])
        self.collision_counter = 0

        # 记录已经发生过碰撞的车辆对，确保每对车辆只记录一次碰撞
        self.recorded_collision_pairs = set()

    def record_vehicle_state(self, timestamp):
        for vehicle_id in traci.vehicle.getIDList():
            try:
                pos = traci.vehicle.getPosition(vehicle_id)
                speed = traci.vehicle.getSpeed(vehicle_id)
                angle = traci.vehicle.getAngle(vehicle_id)
                accel = traci.vehicle.getAcceleration(vehicle_id)
                lane_id = traci.vehicle.getLaneID(vehicle_id)
                edge_id = traci.vehicle.getRoadID(vehicle_id)
                vType = traci.vehicle.getTypeID(vehicle_id)
                self.vehicle_writer.writerow([timestamp, vehicle_id, pos[0], pos[1], vType, speed, angle, accel, lane_id, edge_id])
            except traci.TraCIException:
                continue

    def record_collisions(self, timestamp):
        try:
            for collision in traci.simulation.getCollisions():
                collider = getattr(collision, 'collider', 'N/A')
                victim = getattr(collision, 'victim', 'N/A')
                
                # 跳过无效的碰撞数据
                if collider == 'N/A' or victim == 'N/A':
                    continue
                
                # 创建标准化的车辆对（按字典序排列，确保唯一性）
                vehicle_pair = tuple(sorted([collider, victim]))
                
                # 检查这对车辆是否已经记录过碰撞
                if vehicle_pair not in self.recorded_collision_pairs:
                    # 首次发生碰撞，记录它
                    self.recorded_collision_pairs.add(vehicle_pair)
                    
                    collision_id = f"collision_{self.collision_counter}"
                    self.collision_counter += 1
                    
                    self.collision_writer.writerow([
                        timestamp, 
                        collision_id, 
                        vehicle_pair[0], 
                        vehicle_pair[1], 
                        collision.type
                    ])
                    
                    print(f"记录新碰撞: {collision_id} - {vehicle_pair[0]} vs {vehicle_pair[1]} at {timestamp:.2f}s")
                    self.collision_file.flush()
                # 如果已经记录过，直接跳过，不再记录
                    
        except traci.TraCIException as e:
            print(f"记录碰撞时发生TraCI异常: {e}")
        except Exception as e:
            print(f"记录碰撞时发生未知异常: {e}")

    def close(self):
        self.vehicle_file.close()
        self.collision_file.close()

def update_spectator_to_follow_vehicle(world, synchronization, vehicle_id_to_follow):
    """
    将CARLA观察者视角更新到指定车辆的后上方，形成追车视角。

    :param world: carla.World 对象
    :param synchronization: SimulationSynchronization 对象，用于ID映射
    :param vehicle_id_to_follow: 要跟随的SUMO车辆ID (str)
    """
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

    location = vehicle_transform.location + carla.Location(z=50)


    rotation = carla.Rotation(pitch=-90)
    
    # 5. 获取观察者对象，并应用新的位姿
    spectator = world.get_spectator()
    spectator.set_transform(carla.Transform(location, rotation))

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

    location = vehicle_transform.location + carla.Location(x=1.2, y=-0.5, z=1.4)

    rotation = carla.Rotation(0,0,0)

    # 5. 获取观察者对象，并应用新的位姿
    spectator = world.get_spectator()
    spectator.set_transform(carla.Transform(location, rotation))

def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('--sumo_cfg_file', type=str, help='sumo configuration file', default="scene_4_data_rou/scene4.sumocfg")
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

    # 初始化
    sumo_simulation = SumoSimulation(args.sumo_cfg_file, 0.05, None, None, True, 1)
    carla_simulation = CarlaSimulation(args.carla_host, args.carla_port, 0.05)
    synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, 'sumo', True, True)
    recorder = SumoDataRecorder()

    client = carla_simulation.client
    world = carla_simulation.world
    world.set_weather(carla.WeatherParameters.ClearNoon)
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)

    # 我们在.rou.xml中定义的车辆ID
    lead_vehicle_id = "lead_truck_01"
    subject_vehicle_id = "subject_car_01"
    #surrounding_vehicle_1 = "subject_car_02"
    #surrounding_vehicle_2 = "subject_car_03"

    # ambush_vehicle_id = "lead_truck_02"

    # counter = 0 
    
    event_started = False
    event_collision = False
    initial_setup_done = False


    try:
        while True:
            synchronization.tick()
            timestamp = traci.simulation.getTime()

            for vehicle in traci.vehicle.getIDList():
                traci.vehicle.setLaneChangeMode(vehicle, 0)
            
            # --- 仿真开始时的初始化设置 ---
            if not initial_setup_done and timestamp > 0:
                all_vehicles = traci.vehicle.getIDList()
                # 确保我们的主角车辆已经出现
                #if lead_vehicle_id in all_vehicles and subject_vehicle_id in all_vehicles and surrounding_vehicle_1 in all_vehicles and surrounding_vehicle_2 in all_vehicles:
                if lead_vehicle_id in all_vehicles and subject_vehicle_id in all_vehicles:
                    print("--- 主角车辆已生成，进行初始化设置... ---")
                    # 1. 设置颜色

                    traci.vehicle.setColor(lead_vehicle_id, (0, 255, 0, 255))      # 前车绿色
                    #traci.vehicle.setColor(surrounding_vehicle_1, (0, 255, 0, 255))  # 前车绿色

                    #traci.vehicle.setColor(surrounding_vehicle_1, (0, 255, 0, 255))  # 前车绿色
                    #traci.vehicle.setColor(surrounding_vehicle_2, (0, 255, 0, 255))  # 前车绿色

                    #traci.vehicle.setColor(surrounding_vehicle_2, (255, 0, 0, 255))  # 前车绿色
                    traci.vehicle.setColor(subject_vehicle_id, (255, 0, 0, 255)) # 主车红色

                    initial_setup_done = True


            # 观察者视角: 跟随主车
            update_spectator_to_follow_vehicle(world, synchronization, subject_vehicle_id)

            all_vehicles = traci.vehicle.getIDList()
            if subject_vehicle_id in all_vehicles:
                leader_info = traci.vehicle.getLeader(subject_vehicle_id, 0)
                if leader_info and leader_info[0] == lead_vehicle_id and not event_collision:
                # if leader_info and leader_info[0] == lead_vehicle_id:
                    gap = leader_info[1]
                    lead_speed = traci.vehicle.getSpeed(lead_vehicle_id)
                    subject_speed = traci.vehicle.getSpeed(subject_vehicle_id)
                    print(f"Time: {timestamp:.2f}s | Gap: {gap:.2f}m | Truck Spd: {lead_speed:.2f}m/s | Car Spd: {subject_speed:.2f}m/s")


                    # 备用碰撞检测

                    if gap < -0.1 and subject_vehicle_id in all_vehicles and lead_vehicle_id in all_vehicles and not event_collision:

                            traci.vehicle.setSpeedMode(subject_vehicle_id, 31)

                            traci.vehicle.setSpeedMode(lead_vehicle_id, 31)
                            # traci.vehicle.setSpeed(subject_vehicle_id, 0.1)
                            traci.vehicle.setSpeed(subject_vehicle_id, 1)
                            # traci.vehicle.setSpeed(lead_vehicle_id, 0)
                            print(f"\n[碰撞发生!] 时间: {timestamp:.2f}s | 间距: {gap:.2f}m")
                            event_collision = True



            # 记录数据
            recorder.record_vehicle_state(timestamp)
            recorder.record_collisions(timestamp)


            # --- 在第5秒，触发前车减速事件 ---

            if timestamp > 5 and not event_started:
                if lead_vehicle_id in traci.vehicle.getIDList():
                    print(f"\n--- {timestamp:.2f}s: 事件触发！稳定的前车开始常规减速... ---")
                    traci.vehicle.setLaneChangeMode(lead_vehicle_id, 0) # 禁止前车在减速时变道
                    # traci.vehicle.slowDown(lead_vehicle_id, 15, 8.0)
                    traci.vehicle.setSpeed(lead_vehicle_id, 0)
                    event_started = True
                    traci.vehicle.setSpeedMode(subject_vehicle_id, 0)

                    traci.vehicle.setLaneChangeMode(subject_vehicle_id, 0)  # 禁止主车变道
            if timestamp > 19:
                traci.vehicle.setSpeedMode(subject_vehicle_id, 0)
                traci.vehicle.setSpeed(subject_vehicle_id, 8.75)

    except traci.exceptions.TraCIException as e:
        print(f"\n[SUMO连接错误] 仿真可能已结束或发生碰撞: {e}")
    except KeyboardInterrupt:
        print("\n仿真被用户中断。")
    finally:
        # 清理资源
        print("正在关闭仿真...")
        #recorder.close()
        world.set_weather(carla.WeatherParameters.ClearNoon)
        settings.synchronous_mode = False
        world.apply_settings(settings)
        # 销毁所有actor
        all_actors = world.get_actors()
        vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles])


if __name__ == "__main__":
    main()