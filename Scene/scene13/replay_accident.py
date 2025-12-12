#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUMO×CARLA 事故复现（改进版）：
- 为每个原始 SUMO 车辆分配稳定的唯一“回放ID”，彻底避免重复 ID 冲突
- 只在首次出现时 add()，之后仅 moveToXY()/setSpeed() 驱动
- spectator 自动跟随第一辆事故车（通过回放ID映射）
"""

import os
import csv
import time
import math
from collections import defaultdict

import traci
import carla

from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
from config import *  # 复用你的 sumo/carla 同步配置

# ---- 全局参数 ----
SIMULATION_STEP = 0.05     # 必须与 SUMO 步长一致
BUFFER_TIME     = 2.0      # 事故后缓冲时间（秒）

# ---------- 工具函数 ----------
def calculate_distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def load_accident_data(collision_file):
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

def get_accident_center(vehicle_file, accident, tol=SIMULATION_STEP):
    vid1, vid2 = accident['vehicle1'], accident['vehicle2']
    t0 = accident['timestamp']
    pos = {vid1: None, vid2: None}
    with open(vehicle_file, 'r') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            vid = row['vehicle_id']
            if vid in pos:
                ts = float(row['timestamp'])
                if abs(ts - t0) < tol:
                    pos[vid] = (float(row['x']), float(row['y']))
            if pos[vid1] and pos[vid2]:
                break
    if pos[vid1] and pos[vid2]:
        return ((pos[vid1][0] + pos[vid2][0]) / 2.0,
                (pos[vid1][1] + pos[vid2][1]) / 2.0)
    return None

def determine_time_window(vehicle_file, accident, accident_center):
    vid1, vid2 = accident['vehicle1'], accident['vehicle2']
    t_acc = accident['timestamp']
    trajs = defaultdict(list)
    min_start = float('inf')

    with open(vehicle_file, 'r') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            vid = row['vehicle_id']
            if vid in (vid1, vid2):
                ts = float(row['timestamp'])
                x, y = float(row['x']), float(row['y'])
                trajs[vid].append((ts, x, y))

    for traj in trajs.values():
        traj.sort(key=lambda z: z[0])
        for ts, x, y in traj:
            if ts > t_acc: break
            if calculate_distance(x, y, accident_center[0], accident_center[1]) <= 100:
                min_start = min(min_start, ts)
                break

    if min_start == float('inf'):
        min_start = t_acc - 10.0
    return min_start, t_acc + BUFFER_TIME

def filter_vehicles(vehicle_file, accident, accident_center, start_time, end_time):
    target = {accident['vehicle1'], accident['vehicle2']}
    relevant = set()
    data = defaultdict(list)

    # 先确定相关车辆集合
    with open(vehicle_file, 'r') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            ts = float(row['timestamp'])
            if start_time <= ts <= end_time:
                vid = row['vehicle_id']
                x, y = float(row['x']), float(row['y'])
                if vid in target or calculate_distance(x, y, accident_center[0], accident_center[1]) <= 100:
                    relevant.add(vid)

    # 收集其轨迹
    with open(vehicle_file, 'r') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            vid = row['vehicle_id']
            if vid in relevant:
                ts = float(row['timestamp'])
                if start_time <= ts <= end_time:
                    data[vid].append({
                        'timestamp': ts,
                        'x': float(row['x']),
                        'y': float(row['y']),
                        'speed': float(row['speed']),
                        'angle': float(row['angle']),
                        'lane_id': row['lane_id'],
                        'edge_id': row['edge_id'],
                        'vType': row['vType']
                    })

    for traj in data.values():
        traj.sort(key=lambda p: p['timestamp'])
    return data

# ---------- ID 映射管理：原始ID -> 唯一回放ID ----------
class ReplayIdMapper:
    """
    为每个原始 SUMO 车辆 ID 分配一个稳定的唯一“回放ID”，
    避免在 add() 时与 SUMO 内部 ID 生命周期冲突。
    """
    def __init__(self, suffix="__r"):
        self._map = {}          # orig_id -> replay_id
        self._counter = defaultdict(int)
        self._suffix = suffix

    def get(self, orig_id):
        """获取（或创建）该原始ID对应的唯一回放ID（稳定且不复用）"""
        if orig_id not in self._map:
            idx = self._counter[orig_id]
            self._counter[orig_id] += 1
            self._map[orig_id] = f"{orig_id}{self._suffix}{idx}"
        return self._map[orig_id]

    def to_replay_id(self, orig_id):
        return self.get(orig_id)

# ---------- 回放主逻辑 ----------
def replay_accident(vehicle_data, start_time, end_time, synchronization, accident, carla_simulation):
    print(f"[replay] from {start_time:.2f}s to {end_time:.2f}s")

    world  = carla_simulation.world
    client = carla_simulation.client
    spectator = world.get_spectator()

    accident_orig_ids = {accident['vehicle1'], accident['vehicle2']}

    # 1) 构建一条“虚拟路线”，便于 add()（后续 moveToXY 可自由脱网）
    try:
        edges = traci.edge.getIDList()
        if not edges:
            print("[init] WARNING: no edges found in net!")
        else:
            if "dummy_route" not in traci.route.getIDList():
                traci.route.add("dummy_route", [edges[0]])
    except traci.TraCIException as e:
        print(f"[init] route add error: {e}")

    # 2) ID 映射与创建状态
    id_mapper = ReplayIdMapper()
    created   = set()  # 存储“回放ID”层面的创建情况（只 add 一次）

    current_time = start_time
    first_accident_replay_id = id_mapper.to_replay_id(accident['vehicle1'])

    while current_time <= end_time:
        # 同步一步（内部推进 SUMO/CARLA）
        synchronization.tick()
        time.sleep(SIMULATION_STEP)

        # 3) 首次命中时 add()，之后 move
        for orig_id, traj in vehicle_data.items():
            replay_id = id_mapper.to_replay_id(orig_id)

            # 3.1 add（只做一次）
            if replay_id not in created:
                pt = next((p for p in traj if abs(p['timestamp'] - current_time) < SIMULATION_STEP), None)
                if pt:
                    try:
                        traci.vehicle.add(
                            vehID=replay_id,
                            routeID="dummy_route",
                            depart="now",
                            departPos=0,
                            departSpeed=0,
                            departLane="best",
                            typeID=pt['vType']
                        )
                        created.add(replay_id)
                        if orig_id in accident_orig_ids:
                            traci.vehicle.setColor(replay_id, (255, 0, 0))
                        # print(f"[add] {replay_id} (from {orig_id}) at t={current_time:.2f}")
                    except traci.TraCIException as e:
                        # 若这里仍旧失败，极大概率是 ID 冲突被外部代码或其他地方复用；但在本方案中不会复用
                        print(f"[add] failed: {replay_id} <- {orig_id} : {e}")

            # 3.2 move（只要已创建，就在每步找最近点进行 moveToXY + setSpeed）
            if replay_id in created:
                # 找到与当前时间最接近的点
                # 也可做成二分查找，当前量级直接 min 即可
                closest = min(traj, key=lambda p: abs(p['timestamp'] - current_time))
                if abs(closest['timestamp'] - current_time) < SIMULATION_STEP:
                    try:
                        # lane_id 形如 edge_laneIndex（可能有不同分隔符），我们只需要 edge 与 laneIndex
                        lane_parts = closest['lane_id'].split('_')
                        edge_id = lane_parts[0]
                        lane_index = int(lane_parts[-1]) if len(lane_parts) > 1 and lane_parts[-1].isdigit() else 0

                        traci.vehicle.moveToXY(
                            replay_id,
                            edge_id,
                            lane_index,
                            closest['x'],
                            closest['y'],
                            closest['angle'],
                            keepRoute=2,
                            matchThreshold=100
                        )
                        traci.vehicle.setSpeed(replay_id, closest['speed'])
                    except traci.TraCIException as e:
                        print(f"[move] {replay_id} err: {e}")

        # 4) 让 spectator 跟随第一辆事故车
        #    注意：同步器的 sumo2carla_ids 用的是 SUMO 侧“当前存在的 ID”
        try:
            carla_id = synchronization.sumo2carla_ids.get(first_accident_replay_id)
            if carla_id:
                vehicle_actor = world.get_actor(carla_id)
                if vehicle_actor:
                    tf = vehicle_actor.get_transform()
                    loc = tf.location
                    spectator.set_transform(
                        carla.Transform(loc + carla.Location(z=45.0),
                                        carla.Rotation(pitch=-90))
                    )
        except Exception:
            pass

        current_time += SIMULATION_STEP


# ---------- 主程序 ----------
def main():
    # === 按需替换为你的记录文件 ===
    vehicle_trace   = "sumo_data/vehicle_trace_20250813-161235.csv"
    collisions_file = "sumo_data/collisions_20250813-161235.csv"
    accident_index  = 0   # 回放第几起事故

    sumo_sim = None
    carla_sim = None
    try:
        # 1) 启动 SUMO×CARLA 同步
        sumo_sim  = SumoSimulation(sumo_cfg_file, step_length, sumo_host, sumo_port, sumo_gui, client_order)
        carla_sim = CarlaSimulation(carla_host, carla_port, step_length)
        sync = SimulationSynchronization(sumo_sim, carla_sim, tls_manager, sync_vehicle_color, sync_vehicle_lights)

        # 2) 载入事故并计算回放窗口
        accidents = load_accident_data(collisions_file)
        if not accidents:
            print("[main] No accidents found.")
            return
        accident = accidents[accident_index]
        center = get_accident_center(vehicle_trace, accident)
        if center is None:
            print("[main] Cannot determine accident center.")
            return
        start_t, end_t = determine_time_window(vehicle_trace, accident, center)
        print(f"[main] accident @ {accident['timestamp']:.2f}s, window: [{start_t:.2f}, {end_t:.2f}]")

        # 3) 过滤相关车辆并回放
        vdata = filter_vehicles(vehicle_trace, accident, center, start_t, end_t)
        if not vdata:
            print("[main] No relevant vehicles found.")
            return

        replay_accident(vdata, start_t, end_t, sync, accident, carla_sim)

    finally:
        # 4) 资源清理
        try:
            if carla_sim:
                world = carla_sim.world
                client = carla_sim.client
                actors = world.get_actors()
                to_destroy = [a for a in actors if 'vehicle' in a.type_id or 'sensor' in a.type_id]
                client.apply_batch([carla.command.DestroyActor(a) for a in to_destroy])

                settings = world.get_settings()
                settings.synchronous_mode = False
                world.apply_settings(settings)
        except Exception:
            pass

        try:
            if sumo_sim:
                sumo_sim.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
