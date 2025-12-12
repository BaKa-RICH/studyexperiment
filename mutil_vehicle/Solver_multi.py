import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
import math
import time
import casadi as ca

import carla

from utils import calculate_vehicle_oriented_collision
#from core.models import TrajectoryPoint, Trajectory

class MultiVehicleFrenetPlanner:
    def __init__(self, vehicle_ids):
        # 规划参数
        self.vehicle_ids = vehicle_ids
        self.num_vehicles = len(vehicle_ids)
        self.dt = 0.1  # 时间步长 [s]
        self.T = 5.0  # 规划时间范围 [s]
        self.steps = int(self.T / self.dt)
        self.time_points = np.linspace(0, self.T, int(self.T / self.dt))
        self.v_desired = 30  # 目标速度 [m/s]

        self.opti = ca.Opti()
        self.objective = 0
        
        # 为每辆车创建优化变量
        self.vehicle_coeffs_s = {}  # s方向多项式系数
        self.vehicle_coeffs_d = {}  # d方向多项式系数
        
        for vehicle_id in vehicle_ids:
            self.vehicle_coeffs_s[vehicle_id] = self.opti.variable(6)
            self.vehicle_coeffs_d[vehicle_id] = self.opti.variable(6)

        self.pred_trajs_t = []

    def set_problem(self, vehicle_states, vehicle_targets, vehicle_attributes, 
                    lane_width, transformers):
        """
        设置多车协同规划问题
        
        Args:
            vehicle_states: dict {vehicle_id: {'s_start', 'd_start', 'vs_start', 'vd_start', 'as_start', 'ad_start'}}
            vehicle_targets: dict {vehicle_id: {'s_end', 'd_end'}}
            vehicle_attributes: dict {vehicle_id: ego_attribute}
            lane_width: 车道宽度
            transformers: dict {vehicle_id: transformer}
        """
        
        # 为每辆车设置初始和终止约束
        for vehicle_id in self.vehicle_ids:
            state = vehicle_states[vehicle_id]
            target = vehicle_targets[vehicle_id]
            
            coeffs_s = self.vehicle_coeffs_s[vehicle_id]
            coeffs_d = self.vehicle_coeffs_d[vehicle_id]
            
            # 初始状态约束
            self.opti.subject_to(coeffs_s[0] == state['s_start'])  # s(0)
            self.opti.subject_to(coeffs_s[1] == state['vs_start'])  # vs(0)
            self.opti.subject_to(coeffs_d[0] == state['d_start'])  # d(0)
            self.opti.subject_to(coeffs_d[1] == state['vd_start'])  # vd(0)
            
            # 终止状态约束
            self.opti.subject_to(
                coeffs_d[0] + coeffs_d[1] * self.T + coeffs_d[2] * self.T**2 + 
                coeffs_d[3] * self.T**3 + coeffs_d[4] * self.T**4 + coeffs_d[5] * self.T**5 == target['d_end']
            )

        # 为每个时间步设置约束
        for i, t in enumerate(self.time_points):
            vehicle_positions = {}  # 存储当前时间步所有车辆位置
            
            # 计算每辆车在当前时间步的状态
            for vehicle_id in self.vehicle_ids:
                coeffs_s = self.vehicle_coeffs_s[vehicle_id]
                coeffs_d = self.vehicle_coeffs_d[vehicle_id]
                state = vehicle_states[vehicle_id]
                attr = vehicle_attributes[vehicle_id]
                
                # 计算位置、速度、加速度、jerk
                s_t = coeffs_s[0] + coeffs_s[1]*t + coeffs_s[2]*t**2 + coeffs_s[3]*t**3 + coeffs_s[4]*t**4 + coeffs_s[5]*t**5
                vs_t = coeffs_s[1] + 2*coeffs_s[2]*t + 3*coeffs_s[3]*t**2 + 4*coeffs_s[4]*t**3 + 5*coeffs_s[5]*t**4
                as_t = 2*coeffs_s[2] + 6*coeffs_s[3]*t + 12*coeffs_s[4]*t**2 + 20*coeffs_s[5]*t**3
                js_t = 6*coeffs_s[3] + 24*coeffs_s[4]*t + 60*coeffs_s[5]*t**2
                
                d_t = coeffs_d[0] + coeffs_d[1]*t + coeffs_d[2]*t**2 + coeffs_d[3]*t**3 + coeffs_d[4]*t**4 + coeffs_d[5]*t**5
                vd_t = coeffs_d[1] + 2*coeffs_d[2]*t + 3*coeffs_d[3]*t**2 + 4*coeffs_d[4]*t**3 + 5*coeffs_d[5]*t**4
                ad_t = 2*coeffs_d[2] + 6*coeffs_d[3]*t + 12*coeffs_d[4]*t**2 + 20*coeffs_d[5]*t**3
                jd_t = 6*coeffs_d[3] + 24*coeffs_d[4]*t + 60*coeffs_d[5]*t**2
                
                # 存储位置信息用于车间避撞
                vehicle_positions[vehicle_id] = {
                    's': s_t, 'd': d_t, 'vs': vs_t, 'vd': vd_t,
                    'as': as_t, 'ad': ad_t, 'js': js_t, 'jd': jd_t
                }
                
                # 车辆动力学约束
                self.opti.subject_to(0 <= vs_t)
                self.opti.subject_to(vs_t <= attr.max_vel)
                self.opti.subject_to(-3 <= vd_t)
                self.opti.subject_to(vd_t <= 3)
                self.opti.subject_to(-attr.max_acc <= as_t)
                self.opti.subject_to(as_t <= attr.max_acc)
                self.opti.subject_to(-2 <= ad_t)
                self.opti.subject_to(ad_t <= 2)
                
                # 道路边界约束
                if state['d_start'] > 0:  # 向左变道
                    self.opti.subject_to(d_t >= -lane_width/2 + attr.width/2 - 1e-3)
                    self.opti.subject_to(d_t <= lane_width * 1.5)
                else:  # 向右变道
                    self.opti.subject_to(d_t >= -lane_width * 1.5)
                    self.opti.subject_to(d_t <= lane_width - attr.width/2 + 1e-3)
                
                # 目标函数 - 速度偏差和舒适性
                self.objective += 0.5 * (vs_t - self.v_desired)**2
                self.objective += 0.5 * ((js_t**2 / 16) + (jd_t**2 / 4))
            
            # 车间避撞约束 - 所有车辆对之间
            vehicle_list = list(self.vehicle_ids)
            for i_idx in range(len(vehicle_list)):
                for j_idx in range(i_idx + 1, len(vehicle_list)):
                    veh_i = vehicle_list[i_idx]
                    veh_j = vehicle_list[j_idx]
                    
                    pos_i = vehicle_positions[veh_i]
                    pos_j = vehicle_positions[veh_j]
                    attr_i = vehicle_attributes[veh_i]
                    attr_j = vehicle_attributes[veh_j]
                    
                    # 计算车辆i的朝向
                    heading_i = ca.atan2(pos_i['vd'] + 1e-8, pos_i['vs'] + 1e-8)
                    
                    # 使用椭圆碰撞检测
                    collision_term = calculate_vehicle_oriented_collision(
                        ego_x=pos_i['s'], ego_y=pos_i['d'], ego_yaw=heading_i,
                        obs_x=pos_j['s'], obs_y=pos_j['d'],
                        car_length=max(attr_i.length, attr_j.length),
                        car_width=max(attr_i.width, attr_j.width)
                    )
                    
                    self.opti.subject_to(collision_term <= 0)


    def solve_problem(self, transformers, max_iter=3000, tol=1e-6):
        """
        求解多车协同规划问题
        
        Args:
            transformers: dict {vehicle_id: transformer}
            
        Returns:
            dict {vehicle_id: waypoints_list}
        """
        # 设置目标函数
        self.opti.minimize(self.objective)

        # 设置求解器选项
        p_opts = {"expand": True}
        s_opts = {"max_iter": max_iter, "tol": tol}
        self.opti.solver("ipopt", p_opts, s_opts)

        # 求解问题
        try:
            sol = self.opti.solve()
            
            # 提取所有车辆的轨迹
            all_waypoints = {}
            
            for vehicle_id in self.vehicle_ids:
                coeff_s = sol.value(self.vehicle_coeffs_s[vehicle_id])
                coeff_d = sol.value(self.vehicle_coeffs_d[vehicle_id])
                #transformer = transformers[vehicle_id]
                #todo:
                transformer = transformers
                s_list, d_list, vs_list, vd_list = self._evaluate_polynomial(
                    coeff_s, coeff_d, self.time_points
                )
                
                waypoints = []
                for i in range(len(s_list)):
                    # 位置转换
                    if i == 0:
                        x, y = transformer.frenet_to_cartesian(s_list[i], d_list[i])
                    else:
                        x, y = x_next, y_next
                    
                    # 计算航向角
                    if i < len(s_list) - 1:
                        x_next, y_next = transformer.frenet_to_cartesian(s_list[i + 1], d_list[i + 1])
                    else:
                        x_next, y_next = x, y
                    
                    dx = x_next - x
                    dy = y_next - y
                    heading = math.atan2(dy, dx)
                    
                    # 时间戳
                    timestamp = i * 0.1
                    tp = (x, y, heading, timestamp)
                    waypoints.append(tp)
                
                all_waypoints[vehicle_id] = waypoints
            
            return all_waypoints

        except Exception as e:
            print(f"多车协同优化求解失败: {e}")
            self.opti.debug.show_infeasibilities()
            return None


    def _evaluate_polynomial(self, coeff_s, coeff_d, time_points):
        """
        评估五次多项式轨迹在一系列时间点上的位置和速度（Frenet 坐标系）。
        参数:
            coeff_s (list or np.ndarray): s(t) 的 6 个系数 [a0, a1, ..., a5]
            coeff_d (list or np.ndarray): d(t) 的 6 个系数 [a0, a1, ..., a5]
            time_points (list or np.ndarray): 时间点序列 t（单位：秒）
        """

        # 确保为 numpy 数组
        coeff_s = np.array(coeff_s)
        coeff_d = np.array(coeff_d)
        t = np.array(time_points)

        # 构建时间的幂次矩阵
        T = np.vstack([t ** i for i in range(6)])  # 0~5 次，用于位置
        dT = np.vstack([i * t ** (i - 1) if i > 0 else np.zeros_like(t) for i in range(6)])  # 一阶导数

        # s, d 位置
        s_list = np.dot(coeff_s, T)
        d_list = np.dot(coeff_d, T)

        # s', d' 速度
        vs_list = np.dot(coeff_s, dT)
        vd_list = np.dot(coeff_d, dT)

        return s_list, d_list, vs_list, vd_list

