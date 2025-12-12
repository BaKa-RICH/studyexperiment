#!/usr/bin/env python3
"""
SUMO-CARLA 联合碰撞场景 → 第三人称跟随 agg_6
"""

import traci
import sumolib
import carla
import time

# ------------------ 参数 ------------------
SUMO_CFG = r"D:\桌面\sumo_random\suzhou\Suzhou.sumocfg"
STEP_LENGTH = 0.1
CARLA_HOST = "127.0.0.1"
CARLA_PORT = 2000

# 跟随参数
FOLLOW_ID = "agg_6"          # 要盯的车
VIEW_SCALE_FACTOR = 0.1      # SUMO→CARLA 坐标缩放
OFFSET = carla.Location(x=0, y=-15, z=12)  # 第三人称相对偏移（车后方 15 m，上方 12 m）
PITCH = -25                  # 俯视角度

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

# ------------------ 主循环 ------------------
try:
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()

        # 1. SUMO 端：行为控制（保持你原来的）
        for vid in traci.vehicle.getIDList():
            cls = traci.vehicle.getVehicleClass(vid)
            if cls == "truck":
                traci.vehicle.setMinGap(vid, 0)
                traci.vehicle.setSpeedMode(vid, 0)
                traci.vehicle.setLaneChangeMode(vid, 0)
                traci.vehicle.setColor(vid, (255, 0, 0))
            if vid == "agg_6":
                traci.vehicle.setSpeedMode(vid, 0)
                traci.vehicle.setColor(vid, (0, 0, 255))
                traci.vehicle.setSpeed(vid, 20)  # 72 km/h

        # 2. CARLA 端：第三人称跟随 agg_6
        if FOLLOW_ID in traci.vehicle.getIDList():
            x, y = traci.vehicle.getPosition(FOLLOW_ID)
            angle = traci.vehicle.getAngle(FOLLOW_ID)  # 车头方向（度）
            # SUMO → CARLA 坐标
            carla_x = x * VIEW_SCALE_FACTOR
            carla_y = -y * VIEW_SCALE_FACTOR
            # 计算世界坐标下的相机位置
            loc = carla.Location(x=carla_x, y=carla_y, z=0).transform(
                carla.Transform(
                    carla.Rotation(yaw=angle)
                ).transform(OFFSET)
            )
            spectator.set_transform(carla.Transform(
                loc,
                carla.Rotation(pitch=PITCH, yaw=angle, roll=0)
            ))

        time.sleep(STEP_LENGTH)

except KeyboardInterrupt:
    print("用户中断")
finally:
    traci.close()