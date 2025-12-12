import numpy as np
import math
import time
import casadi as ca
import logging # 添加日志记录

# 可以在这里初始化 logger，如果其他模块没有的话
# logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

class MultiVehicleFrenetPlanner:
    def __init__(self, vehicle_ids):
        self.vehicle_ids = vehicle_ids
        self.num_vehicles = len(vehicle_ids)
        self.dt = 0.1
        self.T = 5.0
        self.steps = int(self.T / self.dt)
        self.time_points = np.linspace(0, self.T, self.steps + 1)
        self.v_desired = 30 

        self.opti = ca.Opti()
        self.objective = 0
        
        self.vehicle_coeffs_s = {} 
        self.vehicle_coeffs_d = {} 
        
        for vehicle_id in vehicle_ids:
            self.vehicle_coeffs_s[vehicle_id] = self.opti.variable(6)
            self.vehicle_coeffs_d[vehicle_id] = self.opti.variable(6)

    def set_problem(self, vehicle_states, vehicle_targets, vehicle_attributes, 
                    lane_width, transformer): 
        """
        设置多车协同规划问题
        [修改] 移除硬终止约束 d(T), 改为目标函数惩罚项
        [修改] 添加横向位置跟踪惩罚项
        [修改] 添加终点横向速度/加速度惩罚项
        [修改] 使用简化的基于 s, d 的碰撞约束
        """
        
        # --- [新] 定义目标函数权重 (这些值需要仔细调整！) ---
        WEIGHT_VS_DESIRED = 0.5   # 速度跟踪权重
        WEIGHT_JERK_S = 0.1     # 纵向Jerk权重 (降低一点?)
        WEIGHT_JERK_D = 0.1     # 横向Jerk权重 (降低一点?)
        WEIGHT_D_END = 500.0    # [新] 终点横向位置惩罚 (较高)
        WEIGHT_VD_END = 100.0   # [新] 终点横向速度惩罚 (中等)
        WEIGHT_AD_END = 50.0    # [新] 终点横向加速度惩罚 (较低)
        WEIGHT_D_TRACKING = 10.0 # [新] 横向位置 *全程* 跟踪惩罚 (中低)
        # 碰撞约束现在是硬约束，不需要权重

        # 为每辆车设置初始约束
        for vehicle_id in self.vehicle_ids:
            state = vehicle_states[vehicle_id]
            coeffs_s = self.vehicle_coeffs_s[vehicle_id]
            coeffs_d = self.vehicle_coeffs_d[vehicle_id]
            
            # 初始状态约束 (保持不变)
            self.opti.subject_to(coeffs_s[0] == state['s_start']) 
            self.opti.subject_to(coeffs_s[1] == state['vs_start']) 
            self.opti.subject_to(coeffs_d[0] == state['d_start']) 
            self.opti.subject_to(coeffs_d[1] == state['vd_start']) 
            # [可选] 初始加速度约束 (可以加上试试)
            # self.opti.subject_to(2 * coeffs_s[2] == state['as_start']) 
            # self.opti.subject_to(2 * coeffs_d[2] == state['ad_start'])

            # [删除] 移除硬终止状态约束 d(T)

        # 为每个时间步设置约束和目标函数
        all_vehicle_positions_t = [] 
        
        for t in self.time_points:
            current_step_positions = {}
            for vehicle_id in self.vehicle_ids:
                coeffs_s = self.vehicle_coeffs_s[vehicle_id]
                coeffs_d = self.vehicle_coeffs_d[vehicle_id]
                attr = vehicle_attributes[vehicle_id]
                target = vehicle_targets[vehicle_id] # 获取该车的目标
                
                # 计算位置、速度、加速度、jerk 
                s_t = coeffs_s[0] + coeffs_s[1]*t + coeffs_s[2]*t**2 + coeffs_s[3]*t**3 + coeffs_s[4]*t**4 + coeffs_s[5]*t**5
                vs_t = coeffs_s[1] + 2*coeffs_s[2]*t + 3*coeffs_s[3]*t**2 + 4*coeffs_s[4]*t**3 + 5*coeffs_s[5]*t**4
                as_t = 2*coeffs_s[2] + 6*coeffs_s[3]*t + 12*coeffs_s[4]*t**2 + 20*coeffs_s[5]*t**3
                js_t = 6*coeffs_s[3] + 24*coeffs_s[4]*t + 60*coeffs_s[5]*t**2
                
                d_t = coeffs_d[0] + coeffs_d[1]*t + coeffs_d[2]*t**2 + coeffs_d[3]*t**3 + coeffs_d[4]*t**4 + coeffs_d[5]*t**5
                vd_t = coeffs_d[1] + 2*coeffs_d[2]*t + 3*coeffs_d[3]*t**2 + 4*coeffs_d[4]*t**3 + 5*coeffs_d[5]*t**4
                ad_t = 2*coeffs_d[2] + 6*coeffs_d[3]*t + 12*coeffs_d[4]*t**2 + 20*coeffs_d[5]*t**3
                jd_t = 6*coeffs_d[3] + 24*coeffs_d[4]*t + 60*coeffs_d[5]*t**2
                
                current_step_positions[vehicle_id] = {'s': s_t, 'd': d_t} 
                
                # 车辆动力学约束 (保持不变)
                self.opti.subject_to(0 <= vs_t)
                self.opti.subject_to(vs_t <= attr.max_vel) 
                self.opti.subject_to(-3 <= vd_t) 
                self.opti.subject_to(vd_t <= 3)
                self.opti.subject_to(-attr.max_acc <= as_t) 
                self.opti.subject_to(as_t <= attr.max_acc) 
                self.opti.subject_to(-2 <= ad_t) 
                self.opti.subject_to(ad_t <= 2)
                
                # 道路边界约束 (保持不变, 但需要重新审视逻辑)
                state_start = vehicle_states[vehicle_id] 
                # [!!!] 这里的逻辑可能需要根据 target['d_end'] 而不是 state['d_start'] 来判断
                # 简化逻辑：允许在左右各 1.5 倍车道宽度内活动 (总共 3 车道)
                half_width_buffer = attr.width / 2 + 0.1 # 车辆半宽 + buffer
                self.opti.subject_to(d_t >= -lane_width * 1.5 + half_width_buffer) 
                self.opti.subject_to(d_t <= lane_width * 1.5 - half_width_buffer)

                # --- 目标函数累加 ---
                self.objective += WEIGHT_VS_DESIRED * (vs_t - self.v_desired)**2
                self.objective += WEIGHT_JERK_S * js_t**2 
                self.objective += WEIGHT_JERK_D * jd_t**2
                
                # [新] 横向位置 *全程* 跟踪惩罚 (鼓励趋向目标 d)
                # 对 Ego 车，目标是 target['d_end'] (例如 0)
                # 对其他车，目标也是 target['d_end'] (即它们的 d_start)
                self.objective += WEIGHT_D_TRACKING * (d_t - target['d_end'])**2

            all_vehicle_positions_t.append(current_step_positions)

        # --- [新] 软化终止约束 d(T), vd(T), ad(T) ---
        t = self.T 
        for vehicle_id in self.vehicle_ids:
            coeffs_s = self.vehicle_coeffs_s[vehicle_id] # 需要 s 系数计算 vd/ad
            coeffs_d = self.vehicle_coeffs_d[vehicle_id]
            target = vehicle_targets[vehicle_id]
            
            # 计算 T 时刻的 d, vd, ad
            d_T = coeffs_d[0] + coeffs_d[1]*t + coeffs_d[2]*t**2 + coeffs_d[3]*t**3 + coeffs_d[4]*t**4 + coeffs_d[5]*t**5
            vd_T = coeffs_d[1] + 2*coeffs_d[2]*t + 3*coeffs_d[3]*t**2 + 4*coeffs_d[4]*t**3 + 5*coeffs_d[5]*t**4
            ad_T = 2*coeffs_d[2] + 6*coeffs_d[3]*t + 12*coeffs_d[4]*t**2 + 20*coeffs_d[5]*t**3
            
            # 添加惩罚项到目标函数
            self.objective += WEIGHT_D_END * (d_T - target['d_end'])**2 # 惩罚终点 d 偏差
            self.objective += WEIGHT_VD_END * vd_T**2 # 惩罚终点 vd (鼓励为 0)
            self.objective += WEIGHT_AD_END * ad_T**2 # 惩罚终点 ad (鼓励为 0)

        # --- [修改] 碰撞约束 (硬约束，保持不变) ---
        vehicle_list = list(self.vehicle_ids)
        for t_idx, current_step_positions in enumerate(all_vehicle_positions_t):
            for i_idx in range(len(vehicle_list)):
                for j_idx in range(i_idx + 1, len(vehicle_list)):
                    veh_i = vehicle_list[i_idx]
                    veh_j = vehicle_list[j_idx]
                    
                    if veh_i not in current_step_positions or veh_j not in current_step_positions:
                         continue 
                         
                    pos_i = current_step_positions[veh_i]
                    pos_j = current_step_positions[veh_j]
                    attr_i = vehicle_attributes[veh_i]
                    attr_j = vehicle_attributes[veh_j]
                    
                    ds = pos_i['s'] - pos_j['s']
                    dd = pos_i['d'] - pos_j['d']
                    
                    safe_s = (attr_i.length + attr_j.length) / 2 * 1.2 
                    safe_d = (attr_i.width + attr_j.width) / 2 * 1.5   
                    if safe_s < 1e-6: safe_s = 1.0
                    if safe_d < 1e-6: safe_d = 0.5

                    collision_constraint = (ds / safe_s)**2 + (dd / safe_d)**2
                    self.opti.subject_to(collision_constraint >= 1.0 - 1e-3) 


    def solve_problem(self, transformer, max_iter=1000, tol=1e-4): 
        """
        求解多车协同规划问题
        (函数主体与上一版相同, 只是调用修改后的 set_problem)
        """
        self.opti.minimize(self.objective)

        p_opts = {"expand": True, "print_time": 0} 
        s_opts = {
            "max_iter": max_iter, 
            "tol": tol, 
            "print_level": 5, 
            # "max_cpu_time": 10.0 
            }
        self.opti.solver("ipopt", p_opts, s_opts)

        try:
            start_solve_time = time.time()
            sol = self.opti.solve()
            end_solve_time = time.time()
            logging.info(f"IPOPT 求解耗时: {end_solve_time - start_solve_time:.3f} 秒")
            
            all_waypoints = {}
            for vehicle_id in self.vehicle_ids:
                coeff_s = sol.value(self.vehicle_coeffs_s[vehicle_id])
                coeff_d = sol.value(self.vehicle_coeffs_d[vehicle_id])
                
                s_list, d_list, vs_list, vd_list = self._evaluate_polynomial(
                    coeff_s, coeff_d, self.time_points
                )
                
                waypoints = []
                for i in range(len(s_list)):
                    s_i, d_i = s_list[i], d_list[i]
                    vs_i, vd_i = vs_list[i], vd_list[i]

                    # 位置转换 (使用传入的 transformer)
                    # [修改] 正确接收 frenet_to_cartesian 的两个返回值
                    x, y = transformer.frenet_to_cartesian(s_i, d_i) 
                    
                    # --- 计算航向角 (更鲁棒的方法) ---
                    
                    # [修改] 单独获取 ref_yaw_rad (确保这行代码在正确的位置)
                    try:
                         ref_yaw_rad = transformer.get_reference_heading(s_i) 
                    except Exception as e:
                         logging.warning(f"获取参考航向失败 s={s_i:.2f}: {e}")
                         ref_yaw_rad = 0.0 # 使用默认值或上一个值

                    # 计算笛卡尔速度 (来自 Frenet 速度)
                    # [!!] 再次确认你的 CoordinateTransform.py 中有 velocity_frenet_to_cartesian 方法！
                    try:
                        vx_i, vy_i = transformer.velocity_frenet_to_cartesian(s_i, d_i, vs_i, vd_i) 
                    except Exception as e:
                         logging.warning(f"速度转换失败 s={s_i:.2f}, d={d_i:.2f}: {e}")
                         vx_i, vy_i = 0.0, 0.0 # 使用默认值

                    # 航向角 = 速度矢量角 (弧度, 0=东)
                    # [修改] 增加对 vx_i, vy_i 同时接近 0 的保护
                    if abs(vx_i) > 1e-3 or abs(vy_i) > 1e-3: # 只有在有显著速度时才计算 atan2
                        heading_rad_0_east = math.atan2(vy_i, vx_i) 
                    else: # 速度接近零时，使用参考路径方向
                        heading_rad_0_east = ref_yaw_rad
                    # ------------------------------------

                    timestamp_relative = self.time_points[i] 
                    tp = (x, y, heading_rad_0_east, timestamp_relative) 
                    waypoints.append(tp)
                    
                all_waypoints[vehicle_id] = waypoints
            
            return all_waypoints

        except Exception as e:
            logging.error(f"多车协同优化求解失败: {e}", exc_info=True) 
            try:
                self.opti.debug.show_infeasibilities(1e-3) 
            except Exception as debug_e:
                 logging.error(f"打印不可行约束时出错: {debug_e}")
            return None 

    def _evaluate_polynomial(self, coeff_s, coeff_d, time_points):
        # (此函数保持不变)
        coeff_s = np.array(coeff_s)
        coeff_d = np.array(coeff_d)
        t = np.array(time_points)
        T = np.vstack([t ** i for i in range(6)]) 
        dT = np.vstack([i * t ** (i - 1) if i > 0 else np.zeros_like(t) for i in range(6)]) 
        s_list = np.dot(coeff_s, T)
        d_list = np.dot(coeff_d, T)
        vs_list = np.dot(coeff_s, dT)
        vd_list = np.dot(coeff_d, dT)
        return s_list, d_list, vs_list, vd_list