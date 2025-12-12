import carla
import argparse
import traci
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
import os
import csv
import time
from config import *

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

    location = vehicle_transform.location + carla.Location(z=70)

    rotation = carla.Rotation(pitch=-90)

    # 5. 获取观察者对象，并应用新的位姿
    spectator = world.get_spectator()
    spectator.set_transform(carla.Transform(location, rotation))

def main():

    # 初始化联合仿真
    sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                             sumo_port, sumo_gui, client_order)
    carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

    synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager, sync_vehicle_color, sync_vehicle_lights)

    recorder = SumoDataRecorder()

    #端口连接 找到蓝图
    client = carla_simulation.client
    world = carla_simulation.world

    # 生成障碍车辆
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)

    try:
        while True:
            start = time.time()
            synchronization.tick()
            update_spectator_to_follow_vehicle(world, synchronization, "emergency")
            for veh_id in traci.vehicle.getIDList():
                # if traci.vehicle.getVehicleClass(veh_id) == "passenger":
                # traci.vehicle.setLaneChangeMode(veh_id, 0)

                if traci.vehicle.getVehicleClass(veh_id) == "truck":
                    # traci.vehicle.setMinGap(veh_id, 0)
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    traci.vehicle.setLaneChangeMode(veh_id, 0)

                    traci.vehicle.setSpeed(veh_id, 24)
                    traci.vehicle.setColor("truck", (0, 255, 0, 255))  # 卡车绿色

                if traci.vehicle.getVehicleClass(veh_id) == "emergency":
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    # traci.vehicle.setSpeed(veh_id, 30)

            end = time.time()
            elapsed = end - start
            if elapsed < step_length:
                time.sleep(step_length - elapsed)

            collisions = traci.simulation.getCollisions()

            for col in collisions:
               # 如果目标车是肇事方或者受害方
               if col.collider == "emergency" or col.victim == "emergency":
                   print('emergency collision')

            if traci.simulation.getTime() > 16.7:
                print(f"目标车辆发生碰撞，停止仿真！")

                traci.vehicle.setSpeedMode("emergency", 0)
                traci.vehicle.setSpeedMode("truck", 0)
                traci.vehicle.setLaneChangeMode("truck", 0)
                traci.vehicle.setLaneChangeMode("emergency", 0)

                traci.vehicle.setSpeed("emergency", 0)
                traci.vehicle.setSpeed("truck", 0)

        # 获取当前SUMO时间戳
            timestamp = traci.simulation.getTime()

        # 记录所有车辆状态
            recorder.record_vehicle_state(timestamp)

        # 记录碰撞事件
            recorder.record_collisions(timestamp)
    except traci.exceptions.FatalTraCIError as e:
        all_actors = world.get_actors()
        vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
        sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
        settings.synchronous_mode = False
        world.apply_settings(settings)

if __name__ == "__main__":
    main()
