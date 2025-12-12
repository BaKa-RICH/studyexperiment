import carla
import argparse
import traci
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
import os
import csv
import time
import math
from collections import defaultdict

# 全局常量
SIMULATION_STEP = 0.05  # 时间步长0.05秒必须与sumo中默认的时间步保持一致性
BUFFER_TIME = 2.0  # 事故后的缓冲时间


def calculate_distance(x1, y1, x2, y2):
    """计算两点之间的欧几里得距离"""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def load_accident_data(collision_file):
    """加载事故数据，返回包含事故详情的列表"""
    accidents = []
    with open(collision_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            accidents.append({
                'timestamp': float(row['timestamp']),
                'vehicle1': row['vehicle1'],
                'vehicle2': row['vehicle2']
            })
    return sorted(accidents, key=lambda x: x['timestamp'])


def get_accident_center(vehicle_file, accident):
    """获取事故发生时的中心位置"""
    vid1, vid2 = accident['vehicle1'], accident['vehicle2']
    accident_time = accident['timestamp']
    positions = {vid1: None, vid2: None}

    # 第一次读取：获取两辆车在事故时间点的位置
    with open(vehicle_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = row['vehicle_id']
            if vid in [vid1, vid2]:
                timestamp = float(row['timestamp'])
                # 寻找最接近事故时间点的位置
                if abs(timestamp - accident_time) < SIMULATION_STEP:
                    positions[vid] = (float(row['x']), float(row['y']))

            # 如果两辆车的位置都已找到，提前退出
            if positions[vid1] and positions[vid2]:
                break

    # 计算两车位置的中心点
    if positions[vid1] and positions[vid2]:
        center_x = (positions[vid1][0] + positions[vid2][0]) / 2
        center_y = (positions[vid1][1] + positions[vid2][1]) / 2
        return (center_x, center_y)
    return None


def determine_time_window(vehicle_file, accident, accident_center):
    """动态确定时间窗口：从车辆进入100米范围到事故后2秒"""
    vid1, vid2 = accident['vehicle1'], accident['vehicle2']
    accident_time = accident['timestamp']
    vehicle_trajectories = defaultdict(list)
    min_start_time = float('inf')

    # 收集事故车辆的完整轨迹
    with open(vehicle_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = row['vehicle_id']
            if vid in [vid1, vid2]:
                timestamp = float(row['timestamp'])
                x, y = float(row['x']), float(row['y'])
                vehicle_trajectories[vid].append((timestamp, x, y))

    # 分析每辆车进入100米范围的时间
    for vid, trajectory in vehicle_trajectories.items():
        # 按时间排序
        trajectory.sort(key=lambda x: x[0])

        # 寻找进入100米范围的时间点
        for i, (ts, x, y) in enumerate(trajectory):
            if ts > accident_time:
                break
            dist = calculate_distance(x, y, accident_center[0], accident_center[1])
            if dist <= 100:
                min_start_time = min(min_start_time, ts)
                break

    # 如果未找到合适时间点，使用默认值
    if min_start_time == float('inf'):
        min_start_time = accident_time - 200.0  # 默认回溯10秒

    return min_start_time, accident_time + BUFFER_TIME


def filter_vehicles(vehicle_file, accident, accident_center, start_time, end_time):
    """筛选事故车辆及附近车辆"""
    target_vehicles = set([accident['vehicle1'], accident['vehicle2']])
    all_vehicle_data = defaultdict(list)
    relevant_vehicles = set()

    # 第一次遍历：收集目标车辆信息并识别附近车辆
    with open(vehicle_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = row['vehicle_id']
            timestamp = float(row['timestamp'])

            # 只收集时间窗口内的数据
            if start_time <= timestamp <= end_time:
                x, y = float(row['x']), float(row['y'])
                # 检查是否是事故车辆或事故点附近车辆
                if (vid in target_vehicles) or (
                        calculate_distance(x, y, accident_center[0], accident_center[1]) <= 100):
                    relevant_vehicles.add(vid)

    # 第二次遍历：收集相关车辆的完整轨迹
    with open(vehicle_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = row['vehicle_id']
            if vid in relevant_vehicles:
                timestamp = float(row['timestamp'])
                if start_time <= timestamp <= end_time:
                    all_vehicle_data[vid].append({
                        'timestamp': timestamp,
                        'x': float(row['x']),
                        'y': float(row['y']),
                        'speed': float(row['speed']),
                        'angle': float(row['angle']),
                        'lane_id': row['lane_id'],
                        'edge_id': row['edge_id'],
                        'vType': row['vType']
                    })

    # 对轨迹按时间排序
    for vid in all_vehicle_data:
        all_vehicle_data[vid].sort(key=lambda p: p['timestamp'])

    return all_vehicle_data


def replay_accident(vehicle_data,start_time, end_time,synchronization,accident,carla_simulation ):
    """
    使用traci的moveToXY函数复现事故

    参数:
        vehicle_data: 车辆轨迹数据
        sumo_config: SUMO配置文件路径
        start_time: 复现开始时间
        end_time: 复现结束时间
    """
    print(f"启动SUMO仿真，时间范围: {start_time:.2f}s 到 {end_time:.2f}s")
    world = carla_simulation.world
    client = carla_simulation.client
    settings = world.get_settings()
    accident_vehicles = {accident['vehicle1'], accident['vehicle2']}

    # 创建虚拟路线
    try:
        edge_list = traci.edge.getIDList()
        if edge_list:
            dummy_edge = edge_list[0]  # 使用第一个边作为虚拟路线
            traci.route.add("dummy_route", [dummy_edge])
            print(f"创建虚拟路线: dummy_route 使用边 {dummy_edge}")
        else:
            print("警告: 没有找到可用的边来创建虚拟路线")
    except traci.TraCIException as e:
        print(f"创建虚拟路线时出错: {e}")

    # 创建车辆集合
    created_vehicles = set()

    # 初始化当前时间
    current_time = start_time
    total_steps = int((end_time - start_time) / SIMULATION_STEP) + 1

    print(f"开始复现，总步数: {total_steps}")

    # 复现循环
    step_count = 0


    while current_time <= end_time:
        try:
            synchronization.tick()
            time.sleep(0.1)
        except:
            all_actors = world.get_actors()
            vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
            sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
            client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
            settings.synchronous_mode = False
            world.apply_settings(settings)
        step_count += 1
        # 处理所有车辆
        for vehicle_id, trajectory in vehicle_data.items():
            # 如果车辆尚未创建
            if vehicle_id not in created_vehicles:
                # 找到第一个轨迹点
                first_point = None
                for point in trajectory:
                    if point['timestamp'] >= current_time - SIMULATION_STEP:
                        first_point = point
                        break

                if first_point and first_point['timestamp'] <= current_time + SIMULATION_STEP:
                    # 创建车辆
                    try:
                        # 解析车道信息
                        lane_parts = first_point['lane_id'].split('_')
                        edge_id = lane_parts[0]
                        lane_index = int(lane_parts[-1]) if len(lane_parts) > 1 else 0

                        # 添加车辆
                        traci.vehicle.add(
                            vehID=vehicle_id,
                            routeID="dummy_route",  # 使用虚拟路线
                            depart="now",
                            departPos=0,
                            departSpeed=0,
                            departLane=lane_index,
                            typeID=first_point['vType']
                        )
                        if vehicle_id in accident_vehicles:
                            # 设置车辆颜色为红色（RGB:255,0,0）
                            traci.vehicle.setColor(vehicle_id, (255, 0, 0))
                            print(f"设置事故车辆 {vehicle_id} 为红色")
                        created_vehicles.add(vehicle_id)
                        print(f"在时间 {current_time:.2f}s 创建车辆 {vehicle_id}")
                    except traci.TraCIException as e:
                        print(f"创建车辆 {vehicle_id} 时出错: {e}")

            # 如果车辆已创建，移动它
            if vehicle_id in created_vehicles:
                # 找到最接近当前时间的轨迹点
                closest_point = None
                min_diff = float('inf')

                for point in trajectory:
                    time_diff = abs(point['timestamp'] - current_time)
                    if time_diff < min_diff:
                        min_diff = time_diff
                        closest_point = point

                if closest_point and min_diff < SIMULATION_STEP:
                    try:
                        # 解析车道信息
                        lane_parts = closest_point['lane_id'].split('_')
                        edge_id = lane_parts[0]
                        lane_index = int(lane_parts[-1]) if len(lane_parts) > 1 else 0

                        # 使用moveToXY放置车辆
                        traci.vehicle.moveToXY(
                            vehicle_id,
                            edge_id,
                            lane_index,
                            closest_point['x'],
                            closest_point['y'],
                            closest_point['angle'],
                            keepRoute=2,  # 允许车辆离开路网
                            matchThreshold=100
                        )
                        traci.vehicle.setSpeed(vehicle_id,closest_point['speed'])
                    except traci.TraCIException as e:
                        print(f"移动车辆 {vehicle_id} 时出错: {e}")
            # 确保进入循环
            if step_count >= 2:
            # 获取第一个事故车辆的SUMO ID
                target_sumo_id = accident['vehicle1']
                # 通过同步器获取CARLA ID
                carla_id = synchronization.sumo2carla_ids.get(target_sumo_id)
                # 获取CARLA中的车辆对象
                carla_vehicle = world.get_actor(carla_id)
                if carla_vehicle:
                    transform = carla_vehicle.get_transform()
                    location = transform.location
                    offset = carla.Location(z=45.0)
                    spectator = world.get_spectator()
                    spectator.set_transform(carla.Transform(location + offset, carla.Rotation(pitch=-90, yaw=0)))
        current_time += SIMULATION_STEP

def main():
    try:
        argparser = argparse.ArgumentParser(description=__doc__)
        argparser.add_argument('--sumo_cfg_file', type=str, help='sumo configuration file', default="scene1_replay_accident_rou/scene1.sumocfg")
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
        argparser.add_argument('--vehicle-trace', type=str, help='车辆轨迹CSV文件',default="sumo_data/vehicle_trace_20251205-021710.csv")
        argparser.add_argument('--collision-trace', type=str, help='事故记录CSV文件',default="sumo_data/collisions_20251205-021710.csv")
        argparser.add_argument('--sumo-config', type=str, help='SUMO配置文件路径', default="simulation.sumocfg")
        argparser.add_argument('--collisions_number', type=int, help='发生的碰撞事故', default="0")
        args = argparser.parse_args()

        # 初始化联合仿真
        sumo_simulation = SumoSimulation(args.sumo_cfg_file, args.step_length, args.sumo_host,args.sumo_port, args.sumo_gui, args.client_order)
        carla_simulation = CarlaSimulation(args.carla_host, args.carla_port, args.step_length)

        synchronization = SimulationSynchronization(sumo_simulation, carla_simulation, args.tls_manager, args.sync_vehicle_color, args.sync_vehicle_lights)

        world = carla_simulation.world
        client = carla_simulation.client
        settings = world.get_settings()



        # 步骤1: 加载事故数据
        accidents = load_accident_data(args.collision_trace)

        if not accidents:
            print("未找到事故数据")


        # 使用第一个事故
        accident = accidents[args.collisions_number]
        print(f"复现事故发生在 {accident['timestamp']:.2f}秒")
        print(f"涉及车辆: {accident['vehicle1']} 和 {accident['vehicle2']}")

        # 步骤2: 动态确定事故中心点和时间窗口
        accident_center = get_accident_center(args.vehicle_trace, accident)
        if not accident_center:
            print("无法确定事故中心点")


        start_time, end_time = determine_time_window(args.vehicle_trace, accident, accident_center)
        print(f"复现时间窗口: {start_time:.2f}s 到 {end_time:.2f}s")

        # 步骤3: 筛选相关车辆
        vehicle_data = filter_vehicles(args.vehicle_trace, accident, accident_center, start_time, end_time)

        if not vehicle_data:
            print("未找到相关车辆数据")


        print(f"找到 {len(vehicle_data)} 辆相关车辆")




        # 步骤4: 复现事故
        replay_accident(
            vehicle_data,
            start_time,
            end_time,
            synchronization,
            accident,
            carla_simulation
        )
    finally:
        all_actors = world.get_actors()
        vehicles = [actor for actor in all_actors if 'vehicle' in actor.type_id]
        sensors = [actor for actor in all_actors if 'sensor' in actor.type_id]
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])
        settings.synchronous_mode = False
        world.apply_settings(settings)

if __name__ == "__main__":
    main()









