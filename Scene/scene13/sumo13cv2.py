#!/usr/bin/env python3
"""
SUMO-CARLA 联合碰撞场景 + 驾驶员视角
"""

import traci
import sumolib
import carla
import time
import math

# ------------------ 参数 ------------------
SUMO_CFG = r"D:\桌面\sumo_random\suzhou\Suzhou.sumocfg"
STEP_LENGTH = 0.1
CARLA_HOST = "127.0.0.1"
CARLA_PORT = 2000

# 要跟随的目标车辆ID
TARGET_VEHICLE_ID = "agg_6"

# 驾驶员视角参数（相对于车辆位置的偏移）
DRIVER_VIEW_OFFSET = carla.Location(x=0.9, y=0, z=1.3)  # 车辆前方和上方的偏移
DRIVER_VIEW_ROTATION = carla.Rotation(pitch=-2, yaw=0, roll=0)  # 轻微低头视角

# 启动 SUMO
sumo_cmd = [
    sumolib.checkBinary("sumo-gui"),
    "-c", SUMO_CFG,
    "--collision.action", "teleport",
    "--collision-output", "collision.xml",
    "--step-length", str(STEP_LENGTH),
    "--start"
]
traci.start(sumo_cmd)

# 连接 CARLA
client = carla.Client(CARLA_HOST, CARLA_PORT)
client.set_timeout(10)
world = client.get_world()
spectator = world.get_spectator()

# 设置CARLA为同步模式
settings = world.get_settings()
settings.synchronous_mode = True
settings.fixed_delta_seconds = STEP_LENGTH
world.apply_settings(settings)

# 坐标转换参数（SUMO到CARLA）
VIEW_SCALE_FACTOR = 0.1  # 坐标缩放因子
Y_AXIS_FLIP = -1  # SUMO与CARLA的Y轴方向相反


# ------------------ 工具函数 ------------------
def get_vehicle_transform(sumo_vehicle_id):
    """
    获取SUMO车辆在CARLA中的变换（位置和旋转）
    """
    # 从SUMO获取车辆信息
    x, y = traci.vehicle.getPosition(sumo_vehicle_id)
    angle = traci.vehicle.getAngle(sumo_vehicle_id)  # 角度（度）

    # 转换到CARLA坐标系
    carla_x = x * VIEW_SCALE_FACTOR
    carla_y = y * VIEW_SCALE_FACTOR * Y_AXIS_FLIP

    # 转换角度（SUMO角度到CARLA旋转）
    # CARLA的yaw是从正X轴开始顺时针为正，需要调整
    carla_yaw = -angle + 90

    # 创建位置和旋转对象
    location = carla.Location(x=carla_x, y=carla_y, z=0.5)  # 给一个小的Z轴高度避免地面穿透
    rotation = carla.Rotation(yaw=carla_yaw)

    return carla.Transform(location, rotation)


def update_driver_view(vehicle_id):
    """
    更新CARLA观察者视角为指定车辆的驾驶员视角
    """
    # 检查车辆是否存在
    if vehicle_id not in traci.vehicle.getIDList():
        return

    # 获取车辆变换
    vehicle_transform = get_vehicle_transform(vehicle_id)

    # 计算驾驶员视角位置（基于车辆位置的偏移）
    # 先将偏移量转换到车辆本地坐标系
    driver_location = vehicle_transform.transform(DRIVER_VIEW_OFFSET)

    # 计算驾驶员视角旋转（基于车辆朝向）
    driver_rotation = carla.Rotation(
        pitch=DRIVER_VIEW_ROTATION.pitch,
        yaw=vehicle_transform.rotation.yaw + DRIVER_VIEW_ROTATION.yaw,
        roll=DRIVER_VIEW_ROTATION.roll
    )

    # 设置观察者位置
    spectator.set_transform(carla.Transform(driver_location, driver_rotation))


# ------------------ 主循环 ------------------
try:
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()

        # 1. SUMO 端：设置车辆行为
        for vid in traci.vehicle.getIDList():
            cls = traci.vehicle.getVehicleClass(vid)
            if cls == "truck":
                traci.vehicle.setMinGap(vid, 0)
                traci.vehicle.setSpeedMode(vid, 0)
                traci.vehicle.setLaneChangeMode(vid, 0)
                traci.vehicle.setColor(vid, (255, 0, 0))  # 红色
            if vid == TARGET_VEHICLE_ID:
                traci.vehicle.setSpeedMode(vid, 0)
                traci.vehicle.setColor(vid, (0, 0, 255))  # 蓝色
                traci.vehicle.setSpeed(vid, 20)  # 72 km/h

        # 2. CARLA 端：更新驾驶员视角
        update_driver_view(TARGET_VEHICLE_ID)

        # 3. 检查碰撞
        collisions = traci.simulation.getCollisions()
        for col in collisions:
            # 如果目标车是肇事方或者受害方
            if col.collider == TARGET_VEHICLE_ID or col.victim == TARGET_VEHICLE_ID:
                print(f"目标车辆 {TARGET_VEHICLE_ID} 发生碰撞，停止仿真！")
                traci.close()
                exit(0)

        # 等待CARLA同步
        world.tick()
        time.sleep(STEP_LENGTH)

except KeyboardInterrupt:
    print("用户中断")
finally:
    # 恢复CARLA设置
    settings = world.get_settings()
    settings.synchronous_mode = False
    world.apply_settings(settings)
    traci.close()
