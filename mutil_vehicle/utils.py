import numpy as np
import casadi as ca

# def rotation_translation(pos, theta, h, w):
#     """
#     构造车辆多面体约束 A, b (CasADi 风格)
#     x0: [x, y]车辆中心
#     theta: 航向角
#     h: 车辆长度
#     w: 车辆宽度
#     """
#     R = ca.DM([[ca.cos(theta), -ca.sin(theta)],
#                [ca.sin(theta),  ca.cos(theta)]])
#
#     b_vec = ca.DM([h/2, w/2, h/2, w/2])
#     A = ca.vertcat(R.T, -R.T)
#     b = b_vec + A @ ca.DM(pos)
#     return A, b

# def rotation_translation(pos, theta, h, w):
#     """
#     构造车辆多面体约束 A, b (数值版)
#     pos: (x, y)，数值
#     theta: 航向角 (弧度)，数值
#     h, w: 车辆长宽
#     返回: A, b (numpy 数组)
#     """
#     R = np.array([[np.cos(theta), -np.sin(theta)],
#                   [np.sin(theta), np.cos(theta)]])
#
#     b_vec = np.array([h / 2, w / 2, h / 2, w / 2])
#     A = np.vstack([R.T, -R.T])
#     b = b_vec + A @ np.array(pos)
#     return A, b


def rotation_translation(pos, theta, h, w):
    """
    构造车辆多面体约束 A, b (CasADi 符号版本，可与 Opti 混用)
    pos: (x, y)，可以是数值或符号变量
    theta: 航向角（弧度），可以是数值或符号变量
    h, w: 车辆长宽
    """
    R = ca.vertcat(
        ca.horzcat(ca.cos(theta), -ca.sin(theta)),
        ca.horzcat(ca.sin(theta), ca.cos(theta))
    )

    b_vec = ca.vertcat(h / 2, w / 2, h / 2, w / 2)  # 这里是常量，DM/SX 都行
    A = ca.vertcat(R.T, -R.T)
    b = b_vec + A @ ca.vertcat(*pos)  # 确保 pos 支持符号
    return A, b

def calculate_vehicle_oriented_collision(ego_x , ego_y , ego_yaw , obs_x , obs_y , car_length ,car_width ):
    """
    基于车辆实际朝向的椭圆碰撞检测
    """
    # 车辆间的相对位置
    dx = obs_x - ego_x
    dy = obs_y - ego_y
    
    # 将相对位置转换到ego车辆的车身坐标系
    cos_yaw = ca.cos(ego_yaw)
    sin_yaw = ca.sin(ego_yaw)
    
    # 车辆坐标系下的相对位置
    longitudinal = dx * cos_yaw + dy * sin_yaw
    lateral = -dx * sin_yaw + dy * cos_yaw
    
    # 安全距离（基于车辆朝向的椭圆）
    safe_dist_longitudinal = car_length * 1.5
    safe_dist_lateral = car_width * 1.8
    
    # 椭圆碰撞项
    collision_term = 1 - ((longitudinal / safe_dist_longitudinal)**2 + 
                         (lateral / safe_dist_lateral)**2)
    
    return collision_term