import traci 
import sumolib
from run_synchronization import *
import logging
import time
from config import *    
import carla

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

    location = vehicle_transform.location + carla.Location(x=0.9, y=0, z=1.3)

    rotation = carla.Rotation(0,0,0)

    # 5. 获取观察者对象，并应用新的位姿
    spectator = world.get_spectator()
    spectator.set_transform(carla.Transform(location, rotation))


sumo_simulation = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                     sumo_port, sumo_gui, client_order)
carla_simulation = CarlaSimulation(carla_host, carla_port, step_length)

synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, tls_manager,
                                                sync_vehicle_color, sync_vehicle_lights)

client = carla_simulation.client
world = carla_simulation.world
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
            #if traci.vehicle.getVehicleClass(veh_id) == "passenger":
                #traci.vehicle.setLaneChangeMode(veh_id, 0)

            if traci.vehicle.getVehicleClass(veh_id) == "truck" :
                #traci.vehicle.setMinGap(veh_id, 0)
                traci.vehicle.setSpeedMode(veh_id, 0)
                traci.vehicle.setLaneChangeMode(veh_id,0)

                traci.vehicle.setSpeed(veh_id, 24)
                traci.vehicle.setColor("truck", (0, 255, 0, 255))  # 卡车绿色

            if traci.vehicle.getVehicleClass(veh_id) == "emergency" :
                traci.vehicle.setSpeedMode(veh_id, 0)
                #traci.vehicle.setSpeed(veh_id, 30)


        end = time.time()
        elapsed = end - start
        if elapsed < step_length:
            time.sleep(step_length - elapsed)

        collisions = traci.simulation.getCollisions()

        #for col in collisions:
        #    # 如果目标车是肇事方或者受害方
        #    if col.collider == "emergency" or col.victim == "emergency":

        if traci.simulation.getTime() > 16.7:
            print(f"目标车辆发生碰撞，停止仿真！")

            traci.vehicle.setSpeedMode("emergency", 0)
            traci.vehicle.setSpeedMode("truck", 0)
            traci.vehicle.setLaneChangeMode("truck", 0)
            traci.vehicle.setLaneChangeMode("emergency", 0)

            traci.vehicle.setSpeed("emergency", 0)
            traci.vehicle.setSpeed("truck", 0)



except KeyboardInterrupt:
    logging.info('Cancelled by user.')

finally:
    logging.info('Cleaning synchronization')
    synchronization.close()


