# coding: utf-8
import traci 
import sumolib
import sys
import os
import logging
import time
import numpy as np
from scipy.interpolate import interp1d 
import bisect 
import math
import csv
from collections import defaultdict

# --- 导入你自己的模块 ---
try:
    from CoordinateTransform import CartesianFrenetConverter
    from Solver_multi import MultiVehicleFrenetPlanner
    from trajectory_plannner_multi import RiskLevel, Decision 
    # from config import * # 通常不需要
except ImportError as e:
    print(f"错误：无法导入必要的模块。 {e}")
    sys.exit(1)

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# --- 配置参数 ---
COLLISION_CSV_PATH = "D:\BIT\code\SwarmPlanner\planning_demo_new\场景4.csv"
SUMO_NET_PATH = "D:\BIT\code\SwarmPlanner\planning_demo_new\mutil_vehicle\scene_4\\road.net.xml"
OUTPUT_CSV_PATH = "planned_trajectories_lc_offline.csv" # [修改] 新的文件名以区分

START_PLANNING_TIME = 9.5  # 保持 9.5s
END_SIMULATION_TIME = 15.0 
SEARCH_RADIUS = 50.0      
STEP_LENGTH = 0.05        
PLANNING_DURATION = 5.0   

# --- 定义Ego车辆和决策 ---
EGO_VEHICLE_ID = "subject_car_01"
# [修改] 明确指定向左变道决策
EGO_DECISION = Decision.LEFT_LANE_CHANGE 

# --- 车辆属性 ---
class EgoAttribute:
    def __init__(self):
        self.max_vel = 35.0 # 保持放宽的速度
        self.max_acc = 3.0   
        self.width = 1.7924479246139526 
        self.length = 3.7186214923858643

# ####################################################################
# ### 辅助功能函数 (大部分保持不变)
# ####################################################################

# --- load_full_trajectory_data (保持不变) ---
def load_full_trajectory_data(csv_path):
    # ... (代码与上一版本完全相同) ...
    logging.info(f"正在从 {csv_path} 加载 *完整* 轨迹数据...")
    vehicle_data = defaultdict(list)
    min_time = float('inf')
    max_time = float('-inf')
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            count = 0
            vehicles_present = set()
            has_vtype = 'vType' in reader.fieldnames if reader.fieldnames else False
            # logging.info(f"CSV header {'包含' if has_vtype else '不包含'} 'vType' 列。") # 可以简化日志

            for row in reader:
                try:
                    ts = float(row['timestamp'])
                    vid = row['vehicle_id']
                    point_data = {
                        'timestamp': ts, 'x': float(row['x']), 'y': float(row['y']),
                        'speed': float(row['speed']), 'angle': float(row['angle']),
                        'lane_id': row['lane_id'], 'edge_id': row['edge_id'],
                    }
                    point_data['vType'] = row.get('vType', 'DEFAULT_VEHTYPE') if has_vtype else 'DEFAULT_VEHTYPE'
                    vehicle_data[vid].append(point_data)
                    min_time = min(min_time, ts); max_time = max(max_time, ts)
                    vehicles_present.add(vid); count += 1
                except (ValueError, KeyError) as e: logging.warning(f"跳过格式错误的行: {row}. 错误: {e}")
        if not vehicle_data: raise ValueError("CSV 文件中未找到有效的车辆数据。")
        for vid in vehicle_data: vehicle_data[vid].sort(key=lambda p: p['timestamp'])
        logging.info(f"成功加载了 {len(vehicle_data)} 辆车 ({len(vehicles_present)} unique IDs), 共 {count} 个轨迹点。")
        logging.info(f"CSV 时间范围: [{min_time:.2f}s, {max_time:.2f}s]")
        return vehicle_data, min_time, max_time, list(vehicles_present)
    except FileNotFoundError: logging.error(f"!!!!!!!! 碰撞CSV文件未找到: {csv_path} !!!!!!!!!"); return None, 0, 0, []
    except Exception as e: logging.error(f"加载CSV时发生未知错误: {e}", exc_info=True); return None, 0, 0, []

# --- get_interpolated_state (保持不变) ---
def get_interpolated_state(trajectory, target_time):
    # ... (代码与上一版本完全相同) ...
    if not trajectory: return None
    timestamps = [p['timestamp'] for p in trajectory]
    idx = bisect.bisect_left(timestamps, target_time)
    if idx == 0: return trajectory[0]
    if idx == len(timestamps): return trajectory[-1]
    p0, p1 = trajectory[idx - 1], trajectory[idx]
    t0, t1 = p0['timestamp'], p1['timestamp']
    if np.isclose(t1, t0): return p0
    ratio = (target_time - t0) / (t1 - t0)
    interp_state = {
        'timestamp': target_time,
        'x': p0['x'] + ratio * (p1['x'] - p0['x']),
        'y': p0['y'] + ratio * (p1['y'] - p0['y']),
        'speed': p0['speed'] + ratio * (p1['speed'] - p0['speed']), # 修正: p1['speed'] - p0['speed']
        'lane_id': p0['lane_id'], 'edge_id': p0['edge_id'],
        'vType': p0.get('vType', 'DEFAULT_VEHTYPE')
    }
    interp_state['angle'] = p0['angle'] if abs(target_time - t0) < abs(target_time - t1) else p1['angle']
    return interp_state

# --- estimate_acceleration (保持不变) ---
def estimate_acceleration(trajectory, target_time, dt=0.1):
    # ... (代码与上一版本完全相同) ...
    state_now = get_interpolated_state(trajectory, target_time)
    state_prev = get_interpolated_state(trajectory, target_time - dt)
    if not state_now or not state_prev: return 0.0, 0.0
    angle_now_rad = np.deg2rad(90 - state_now['angle'])
    vx_now, vy_now = state_now['speed'] * np.cos(angle_now_rad), state_now['speed'] * np.sin(angle_now_rad)
    angle_prev_rad = np.deg2rad(90 - state_prev['angle'])
    vx_prev, vy_prev = state_prev['speed'] * np.cos(angle_prev_rad), state_prev['speed'] * np.sin(angle_prev_rad)
    time_diff = state_now['timestamp'] - state_prev['timestamp']
    if np.isclose(time_diff, 0): return 0.0, 0.0
    ax = (vx_now - vx_prev) / time_diff
    ay = (vy_now - vy_prev) / time_diff
    return ax, ay

# --- get_lane_waypoints (保持不变) ---
def get_lane_waypoints(net, lane_id):
    # ... (代码与上一版本完全相同) ...
    try:
        lane = net.getLane(lane_id)
        waypoints = lane.getShape(includeJunctions=True) 
        if not waypoints: logging.error(f"车道 {lane_id} 的 shape 为空！"); return None
        return waypoints
    except KeyError: logging.error(f"在路网文件中找不到车道 ID: {lane_id}"); return None

# --- [重新引入] get_target_lane_id ---
def get_target_lane_id(net, current_lane_id, decision):
    """根据当前车道和决策获取目标车道ID"""
    if decision == Decision.LANE_KEEPING:
        return current_lane_id
    try:
        current_lane = net.getLane(current_lane_id)
        current_edge = current_lane.getEdge()
        current_index = current_lane.getIndex()
        num_lanes = current_edge.getLaneNumber()
        target_index = -1
        if decision == Decision.LEFT_LANE_CHANGE: target_index = current_index + 1
        elif decision == Decision.RIGHT_LANE_CHANGE: target_index = current_index - 1
        if 0 <= target_index < num_lanes:
            target_lane_id = f"{current_edge.getID()}_{target_index}"
            try:
                net.getLane(target_lane_id); return target_lane_id # 确认目标车道存在
            except KeyError: logging.warning(f"目标车道 {target_lane_id} 不存在，保持原车道。"); return current_lane_id
        else:
            logging.warning(f"无法执行变道，目标索引 {target_index} 超范围 [0, {num_lanes-1}]，保持原车道。"); return current_lane_id
    except KeyError: logging.error(f"获取车道信息失败: {current_lane_id}"); return current_lane_id

# --- find_csv_waypoint_for_time (保持不变) ---
def find_csv_waypoint_for_time(trajectory_list, current_time):
    # ... (代码与上一版本完全相同) ...
    if not trajectory_list: return None
    closest_point, min_diff = None, float('inf')
    timestamps = [p['timestamp'] for p in trajectory_list]
    idx = bisect.bisect_left(timestamps, current_time)
    if idx == 0: closest_point = trajectory_list[0]
    elif idx == len(timestamps): closest_point = trajectory_list[-1]
    else:
        prev_point, next_point = trajectory_list[idx-1], trajectory_list[idx]
        closest_point = prev_point if abs(current_time - prev_point['timestamp']) <= abs(current_time - next_point['timestamp']) else next_point
    min_diff = abs(closest_point['timestamp'] - current_time)
    if min_diff < (STEP_LENGTH * 1.5): return closest_point
    else: return None

# --- find_planned_waypoint_for_time (保持不变) ---
def find_planned_waypoint_for_time(plan_trajectory, current_time_relative):
    # ... (代码与上一版本完全相同) ...
    if plan_trajectory is None or len(plan_trajectory) == 0: return None
    closest_point_raw, min_diff = None, float('inf')
    timestamps_relative = [p[3] for p in plan_trajectory]
    idx = bisect.bisect_left(timestamps_relative, current_time_relative) 
    if idx == 0: closest_point_raw = plan_trajectory[0]
    elif idx == len(timestamps_relative): closest_point_raw = plan_trajectory[-1]
    else:
        prev_point, next_point = plan_trajectory[idx-1], plan_trajectory[idx]
        closest_point_raw = prev_point if abs(current_time_relative - prev_point[3]) <= abs(current_time_relative - next_point[3]) else next_point
    min_diff = abs(closest_point_raw[3] - current_time_relative)
    if min_diff < (STEP_LENGTH * 1.5):
        return {'x': closest_point_raw[0], 'y': closest_point_raw[1], 'angle': closest_point_raw[2], 'speed': -1}
    return None

# ####################################################################
# ### 主程序
# ####################################################################

if __name__ == "__main__":
    
    # --- 1. 加载数据 ---
    full_trajectories, csv_min_time, csv_max_time, all_vehicle_ids = load_full_trajectory_data(COLLISION_CSV_PATH)
    if full_trajectories is None: sys.exit(1)
    logging.info(f"正在加载 SUMO 路网文件: {SUMO_NET_PATH}")
    try:
        net = sumolib.net.readNet(SUMO_NET_PATH)
    except Exception as e:
        logging.error(f"加载 SUMO 路网文件失败: {e}", exc_info=True); sys.exit(1)

    # --- 2. 获取规划起点状态 ---
    logging.info(f"正在计算 t={START_PLANNING_TIME:.2f}s 时的车辆状态...")
    planning_start_states, ego_state_cartesian = {}, None
    vehicles_to_plan = set() 
    if EGO_VEHICLE_ID not in full_trajectories:
        logging.error(f"Ego 车辆 '{EGO_VEHICLE_ID}' 不在 CSV 文件中！"); sys.exit(1)
    ego_trajectory = full_trajectories[EGO_VEHICLE_ID]
    ego_state_cartesian = get_interpolated_state(ego_trajectory, START_PLANNING_TIME)
    if not ego_state_cartesian:
         logging.error(f"无法获取 Ego 车辆在 t={START_PLANNING_TIME:.2f}s 的状态！"); sys.exit(1)
    ego_ax, ego_ay = estimate_acceleration(ego_trajectory, START_PLANNING_TIME)
    ego_state_cartesian['ax'], ego_state_cartesian['ay'] = ego_ax, ego_ay
    vehicles_to_plan.add(EGO_VEHICLE_ID)
    logging.info(f"Ego 车辆 ({EGO_VEHICLE_ID}) 状态 @{START_PLANNING_TIME:.2f}s: "
                 f"x={ego_state_cartesian['x']:.2f}, y={ego_state_cartesian['y']:.2f}, "
                 f"v={ego_state_cartesian['speed']:.2f}, ang={ego_state_cartesian['angle']:.2f}, "
                 f"ax={ego_ax:.2f}, ay={ego_ay:.2f}, lane={ego_state_cartesian['lane_id']}")
    
    critical_obstacle_ids = {"lead_truck_01", "lead_truck_02"} 
    logging.info(f"查找并添加关键障碍车辆: {critical_obstacle_ids}")
    for other_vid in critical_obstacle_ids:
        if other_vid in full_trajectories:
            trajectory = full_trajectories[other_vid]
            other_state = get_interpolated_state(trajectory, START_PLANNING_TIME)
            if other_state:
                 other_ax, other_ay = estimate_acceleration(trajectory, START_PLANNING_TIME)
                 other_state['ax'], other_state['ay'] = other_ax, other_ay
                 planning_start_states[other_vid] = other_state 
                 vehicles_to_plan.add(other_vid) 
                 logging.info(f"  -> 添加关键车辆到规划: {other_vid}")
            else: logging.warning(f"无法获取关键车辆 {other_vid} 状态，将不参与规划。")
        else: logging.warning(f"关键车辆 {other_vid} 未在 CSV 数据中找到。")
    planning_start_states[EGO_VEHICLE_ID] = ego_state_cartesian 
    vehicles_to_plan_list = list(vehicles_to_plan) 
    logging.info(f"总共有 {len(vehicles_to_plan_list)} 辆车将参与协同规划: {vehicles_to_plan_list}")

    # --- 3. [修改] 构建 Frenet 坐标系 (基于目标车道) ---
    logging.info("构建 Frenet 坐标系...")
    ego_current_lane_id = ego_state_cartesian['lane_id']
    # [修改] 使用 EGO_DECISION 获取目标车道
    target_lane_id = get_target_lane_id(net, ego_current_lane_id, EGO_DECISION) 
    logging.info(f"Ego 决策: {EGO_DECISION}, 目标车道: {target_lane_id}")
    if target_lane_id == ego_current_lane_id and EGO_DECISION != Decision.LANE_KEEPING:
         logging.warning("获取目标车道失败或目标与当前车道相同，但决策不是 LANE_KEEPING。继续使用当前车道作为参考。")
         # reference_lane_id = ego_current_lane_id # 如果获取失败，可以回退
    
    reference_lane_id = target_lane_id # 参考路径现在是目标车道
    logging.info(f"使用目标车道 {reference_lane_id} 作为参考路径。")
    
    reference_waypoints = get_lane_waypoints(net, reference_lane_id)
    if reference_waypoints is None: sys.exit(1)
    try:
        transformer = CartesianFrenetConverter(reference_waypoints, smooth=True) 
    except Exception as e:
         logging.error(f"初始化 Frenet 转换器失败: {e}", exc_info=True); sys.exit(1)

    # --- 4. 转换状态到 Frenet (相对于目标车道) 并移除钳制 ---
    logging.info("转换车辆状态到 Frenet 坐标系 (相对于目标车道)...")
    vehicle_states_frenet, vehicle_targets_frenet, vehicle_attributes = {}, {}, {}
    MAX_ACCEL_CONSTRAINT, MAX_DECEL_CONSTRAINT = 3.0, -3.0 # 仍然用于日志警告
    for vid in vehicles_to_plan_list:
        state_c = planning_start_states[vid]
        angle_rad_math = np.deg2rad(90 - state_c['angle']) 
        vx, vy = state_c['speed'] * np.cos(angle_rad_math), state_c['speed'] * np.sin(angle_rad_math)
        ax, ay = state_c['ax'], state_c['ay']
        try:
            s, d = transformer.cartesian_to_frenet(state_c['x'], state_c['y'])
            vs, vd = transformer.velocity_cartesian_to_frenet(state_c['x'], state_c['y'], vx, vy)
            as_raw, ad_raw = transformer.acceleration_cartesian_to_frenet(state_c['x'], state_c['y'], vx, vy, ax, ay)
            
            logging.info(f"--- Frenet Debug for {vid} @ t={START_PLANNING_TIME:.2f}s ---")
            logging.info(f"  Input Cartesian: x={state_c['x']:.3f}, y={state_c['y']:.3f}, vx={vx:.3f}, vy={vy:.3f}, ax={ax:.3f}, ay={ay:.3f}")
            logging.info(f"  Output Frenet Raw (rel to {reference_lane_id}): s={s:.3f}, d={d:.3f}, vs={vs:.3f}, vd={vd:.3f}, as_raw={as_raw:.3f}, ad_raw={ad_raw:.3f}")

            if not all(np.isfinite([s, d, vs, vd, as_raw, ad_raw])):
                 raise ValueError(f"Frenet 转换产生无效值 (NaN/Inf)！")
            
            # 移除钳制，但保留警告
            if as_raw < MAX_DECEL_CONSTRAINT - 0.1 or as_raw > MAX_ACCEL_CONSTRAINT + 0.1 or ad_raw < -2.0 - 0.1 or ad_raw > 2.0 + 0.1: 
                logging.warning(f"车辆 {vid} 初始 Frenet 加速度超出约束范围! Raw=({as_raw:.3f}, {ad_raw:.3f})")

            vehicle_states_frenet[vid] = {'s_start': s, 'd_start': d, 'vs_start': vs, 'vd_start': vd, 'as_start': as_raw, 'ad_start': ad_raw}
            
            # [修改] 目标设置
            if vid == EGO_VEHICLE_ID:
                 # Ego 的目标是 d=0 (目标车道中心)
                 vehicle_targets_frenet[vid] = {'s_end': s + 50.0, 'd_end': 0.0} 
            else:
                 # 其他车的目标是保持它们相对于 *目标车道* 的横向位置 d 不变
                 # 这可能不是最优的，也许应该让它们保持在 *自己* 的车道中心？
                 # 简化处理：保持计算出的 d 不变
                 vehicle_targets_frenet[vid] = {'s_end': s + 30.0, 'd_end': d} 
            vehicle_attributes[vid] = EgoAttribute()
        except Exception as e:
            logging.error(f"处理车辆 {vid} 状态转换时出错: {e}", exc_info=True); sys.exit(1)
            
    # --- 5. 运行离线求解器 ---
    logging.info("初始化并运行多车协同规划器...")
    planner = MultiVehicleFrenetPlanner(vehicles_to_plan_list) 
    all_waypoints_planned_relative = None 
    planning_succeeded = False # [新] 标记规划是否成功
    try:
        lane_width = 3.5 
        try:
             # [修改] 获取 *参考车道* (目标车道) 的宽度
             lane_width = net.getLane(reference_lane_id).getWidth() 
             logging.info(f"从路网获取参考车道 {reference_lane_id} 宽度: {lane_width:.2f}m")
        except Exception: logging.warning(f"无法获取车道 {reference_lane_id} 宽度, 使用默认值 {lane_width}m。")

        planner.set_problem(
            vehicle_states_frenet, vehicle_targets_frenet, vehicle_attributes,
            lane_width, transformer 
        )
        all_waypoints_planned_relative = planner.solve_problem(transformer) 
        
        # [新] 检查是否成功
        if all_waypoints_planned_relative is not None:
             planning_succeeded = True

    except Exception as e:
        logging.error(f"运行规划求解器时发生严重错误: {e}", exc_info=True)

    # --- 6. 处理规划结果 & 构建最终 CSV ---
    logging.info("开始构建最终的输出 CSV 文件...")
    output_filename = OUTPUT_CSV_PATH
    
    try:
        with open(output_filename, 'w', newline='') as outfile:
            fieldnames = ['timestamp', 'vehicle_id', 'x', 'y', 'speed', 'angle', 'lane_id', 'edge_id', 'vType'] 
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            plan_interp_funcs = {}
            # [修改] 使用 planning_succeeded 标志
            if planning_succeeded: 
                logging.info("为规划轨迹创建插值函数...")
                planned_vehicle_ids = set(all_waypoints_planned_relative.keys()) 
                for vid, waypoints_relative in all_waypoints_planned_relative.items():
                    # ... (插值函数创建代码与上一版本相同) ...
                    if not waypoints_relative or len(waypoints_relative) < 2: continue
                    times_rel = np.array([p[3] for p in waypoints_relative])
                    if not np.all(np.diff(times_rel) > -1e-6): continue
                    unique_times_rel, unique_indices = np.unique(times_rel, return_index=True)
                    if len(unique_times_rel) < 2: continue
                    waypoints_unique = [waypoints_relative[i] for i in unique_indices]
                    times_abs = np.array([START_PLANNING_TIME + p[3] for p in waypoints_unique])
                    x_coords = np.array([p[0] for p in waypoints_unique])
                    y_coords = np.array([p[1] for p in waypoints_unique])
                    angles_rad = np.unwrap([p[2] for p in waypoints_unique]) 
                    try:
                        interp_x = interp1d(times_abs, x_coords, kind='linear', bounds_error=False, fill_value="extrapolate")
                        interp_y = interp1d(times_abs, y_coords, kind='linear', bounds_error=False, fill_value="extrapolate")
                        interp_angle = interp1d(times_abs, angles_rad, kind='linear', bounds_error=False, fill_value="extrapolate")
                        plan_interp_funcs[vid] = (interp_x, interp_y, interp_angle)
                    except ValueError as e:
                         logging.error(f"为车辆 {vid} 创建规划插值时出错: {e}. 该车辆将继续跟踪CSV。")
                         if vid in planned_vehicle_ids: planned_vehicle_ids.remove(vid)
            else:
                 logging.warning("规划失败或未生成有效路径，所有车辆将跟踪原始CSV。")
                 planned_vehicle_ids = set() 

            csv_interp_funcs = {}
            logging.info("为原始CSV轨迹创建插值函数...")
            # ... (CSV 插值函数创建代码与上一版本相同) ...
            for vid, trajectory in full_trajectories.items():
                 if not trajectory or len(trajectory) < 2: continue 
                 times = np.array([p['timestamp'] for p in trajectory])
                 if not np.all(np.diff(times) > -1e-6): continue
                 unique_times, unique_indices = np.unique(times, return_index=True)
                 if len(unique_times) < 2: continue
                 trajectory_unique = [trajectory[i] for i in unique_indices]
                 x_coords = np.array([p['x'] for p in trajectory_unique])
                 y_coords = np.array([p['y'] for p in trajectory_unique])
                 angles_sumo = np.unwrap([p['angle'] for p in trajectory_unique], period=360) 
                 speeds = np.array([p['speed'] for p in trajectory_unique])
                 non_numeric_lookup = {p['timestamp']: {'lane_id': p['lane_id'], 'edge_id': p['edge_id'], 'vType': p.get('vType', 'DEFAULT_VEHTYPE')} for p in trajectory_unique}
                 try:
                     interp_x = interp1d(unique_times, x_coords, kind='linear', bounds_error=False, fill_value="extrapolate")
                     interp_y = interp1d(unique_times, y_coords, kind='linear', bounds_error=False, fill_value="extrapolate")
                     interp_angle = interp1d(unique_times, angles_sumo, kind='linear', bounds_error=False, fill_value="extrapolate")
                     interp_speed = interp1d(unique_times, speeds, kind='linear', bounds_error=False, fill_value="extrapolate")
                     csv_interp_funcs[vid] = (interp_x, interp_y, interp_angle, interp_speed, non_numeric_lookup, unique_times) 
                 except ValueError as e: logging.error(f"为车辆 {vid} 创建CSV插值时出错: {e}.")

            output_time_points = np.arange(csv_min_time, END_SIMULATION_TIME + STEP_LENGTH/2, STEP_LENGTH)
            logging.info(f"生成输出CSV, 时间范围 [{output_time_points[0]:.2f}s, {output_time_points[-1]:.2f}s], 步长 {STEP_LENGTH}s")

            total_points_written = 0
            for t_abs in output_time_points: 
                for vid in all_vehicle_ids: 
                    # ... (选择 source (PLANNER or CSV) 的逻辑与上一版本相同) ...
                    final_x, final_y, final_angle, final_speed = None, None, None, None
                    lane_id, edge_id, vType = "unknown", "unknown", "DEFAULT_VEHTYPE"
                    source = "N/A"
                    if vid in planned_vehicle_ids and t_abs >= START_PLANNING_TIME: 
                         if vid in plan_interp_funcs:
                             interp_x, interp_y, interp_angle_rad = plan_interp_funcs[vid]
                             try:
                                 final_x = float(interp_x(t_abs)); final_y = float(interp_y(t_abs))
                                 angle_rad_0_east = float(interp_angle_rad(t_abs))
                                 final_angle = (90 - np.degrees(angle_rad_0_east)) % 360 
                                 source = "PLANNER"
                             except Exception as e: source = "INTERP_FAIL"; logging.warning(f"t={t_abs:.2f}s, 规划插值失败 for {vid}: {e}.")
                    if source != "PLANNER":
                        if vid in csv_interp_funcs:
                            interp_x, interp_y, interp_angle_sumo, interp_speed, lookup, csv_times = csv_interp_funcs[vid]
                            try:
                                final_x = float(interp_x(t_abs)); final_y = float(interp_y(t_abs))
                                final_angle = float(interp_angle_sumo(t_abs)) % 360 
                                final_speed = float(interp_speed(t_abs))
                                source = "CSV"
                                closest_ts_idx = bisect.bisect_left(csv_times, t_abs)
                                if closest_ts_idx == 0: closest_ts = csv_times[0]
                                elif closest_ts_idx == len(csv_times): closest_ts = csv_times[-1]
                                else:
                                    prev_ts, next_ts = csv_times[closest_ts_idx-1], csv_times[closest_ts_idx]
                                    closest_ts = prev_ts if abs(t_abs-prev_ts) <= abs(t_abs-next_ts) else next_ts
                                if closest_ts in lookup:
                                     lane_id = lookup[closest_ts]['lane_id']
                                     edge_id = lookup[closest_ts]['edge_id']
                                     vType = lookup[closest_ts].get('vType', 'DEFAULT_VEHTYPE') 
                            except Exception as e: source = "INTERP_FAIL"; logging.warning(f"t={t_abs:.2f}s, CSV 插值失败 for {vid}: {e}.")
                    
                    # ... (写入 CSV 的逻辑与上一版本相同) ...
                    if final_x is not None: 
                        if source == "PLANNER":
                             if vid in csv_interp_funcs:
                                 _, _, _, interp_speed, lookup, csv_times = csv_interp_funcs[vid]
                                 try:
                                     final_speed = float(interp_speed(t_abs))
                                     closest_ts_idx = bisect.bisect_left(csv_times, t_abs)
                                     # ... (查找 lookup 的逻辑) ...
                                     if closest_ts_idx == 0: closest_ts = csv_times[0]
                                     elif closest_ts_idx == len(csv_times): closest_ts = csv_times[-1]
                                     else:
                                         prev_ts, next_ts = csv_times[closest_ts_idx-1], csv_times[closest_ts_idx]
                                         closest_ts = prev_ts if abs(t_abs-prev_ts) <= abs(t_abs-next_ts) else next_ts
                                     if closest_ts in lookup:
                                         lane_id = lookup[closest_ts]['lane_id']
                                         edge_id = lookup[closest_ts]['edge_id']
                                         vType = lookup[closest_ts].get('vType', 'DEFAULT_VEHTYPE')
                                 except Exception: final_speed = -1 
                             else: final_speed = -1
                        
                        writer.writerow({
                            'timestamp': f"{t_abs:.2f}", 'vehicle_id': vid,
                            'x': final_x, 'y': final_y,
                            'speed': final_speed if final_speed is not None else -1,
                            'angle': final_angle if final_angle is not None else 0.0, 
                            'lane_id': lane_id, 'edge_id': edge_id, 'vType': vType
                        })
                        total_points_written += 1
            logging.info(f"成功写入 {total_points_written} 个轨迹点到 {output_filename}")

    except Exception as e:
        logging.error(f"!!!!!!!! [生成CSV时崩溃] !!!!!!!! 发生未捕获异常: {e}", exc_info=True)
    finally:
        logging.info(f"--- [任务完成] --- 离线规划结束。最终轨迹已保存到: {output_filename}")
        logging.info("现在你可以运行 'python trajectory_executor.py' 来可视化结果 (请修改其读取的文件名)。")