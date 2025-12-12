#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CARLA-SUMO 联合仿真示例
规则：一旦发生碰撞，仿真立即终止，并自动清理所有资源。
"""

import carla
import argparse
import traci
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from run_synchronization import SimulationSynchronization
import os
import csv
import time
from config import *       # 你的全局配置（sumo_cfg_file / step_length 等）


# --------------------------------------------------------------------------
# 数据记录器：车辆轨迹 + 碰撞事件
# --------------------------------------------------------------------------
class SumoDataRecorder:
    def __init__(self):
        self.output_dir = "sumo_data"
        os.makedirs(self.output_dir, exist_ok=True)

        ts = time.strftime("%Y%m%d-%H%M%S")
        self.vehicle_file   = open(f"{self.output_dir}/vehicle_trace_{ts}.csv", "w", newline='')
        self.collision_file = open(f"{self.output_dir}/collisions_{ts}.csv", "w", newline='')

        self.vehicle_writer   = csv.writer(self.vehicle_file)
        self.collision_writer = csv.writer(self.collision_file)

        # 表头
        self.vehicle_writer.writerow(
            ["timestamp", "vehicle_id", "x", "y", "vType", "speed", "angle",
             "acceleration", "lane_id", "edge_id"]
        )
        self.collision_writer.writerow(
            ["timestamp", "collision_id", "vehicle1", "vehicle2", "collision_type"]
        )

        self.collision_counter   = 0
        self.recorded_collisions = set()

    # ---------------- 记录车辆状态 ----------------
    def record_vehicle_state(self, timestamp):
        for veh_id in traci.vehicle.getIDList():
            try:
                pos   = traci.vehicle.getPosition(veh_id)
                speed = traci.vehicle.getSpeed(veh_id)
                angle = traci.vehicle.getAngle(veh_id)
                accel = traci.vehicle.getAcceleration(veh_id)
                lane_id = traci.vehicle.getLaneID(veh_id)
                edge_id = traci.vehicle.getRoadID(veh_id)
                vtype   = traci.vehicle.getTypeID(veh_id)

                self.vehicle_writer.writerow(
                    [timestamp, veh_id, pos[0], pos[1], vtype,
                     speed, angle, accel, lane_id, edge_id]
                )
            except traci.TraCIException:
                continue

    # ---------------- 记录碰撞 ----------------
    def record_collisions(self, timestamp):
        """
        返回 True  -> 本次步长检测到新碰撞，要求停止仿真
               False -> 无碰撞或碰撞已记录过
        """
        collisions = traci.simulation.getCollisions()
        stop_flag  = False

        for col in collisions:
            cid  = f"collision_{self.collision_counter}"
            self.collision_counter += 1

            key = (col.collider, col.victim, col.type)
            if key in self.recorded_collisions:
                continue

            self.recorded_collisions.add(key)
            stop_flag = True        # 只要有一个新碰撞就停

            self.collision_writer.writerow(
                [timestamp, cid, col.collider, col.victim, col.type]
            )

        return stop_flag

    # ---------------- 清理 ----------------
    def close(self):
        self.vehicle_file.close()
        self.collision_file.close()


# --------------------------------------------------------------------------
# 主函数
# --------------------------------------------------------------------------
def main():
    # 初始化 SUMO 与 CARLA 端
    sumo_sim = SumoSimulation(sumo_cfg_file, step_length, sumo_host,
                                sumo_port, sumo_gui, client_order)
    carla_sim = CarlaSimulation(carla_host, carla_port, step_length)
    sync = SimulationSynchronization(sumo_sim, carla_sim, tls_manager,
                                     sync_vehicle_color, sync_vehicle_lights)
    recorder = SumoDataRecorder()

    client = carla_sim.client
    world  = carla_sim.world

    # 设置 CARLA 同步模式
    settings = world.get_settings()
    settings.synchronous_mode    = True
    settings.fixed_delta_seconds = 0.05
    world.apply_settings(settings)

    try:
        while True:
            sync.tick()          # 推进一个步长

            # 特殊车辆设置
            for veh_id in traci.vehicle.getIDList():
                if traci.vehicle.getVehicleClass(veh_id) == "truck":
                    traci.vehicle.setMinGap(veh_id, 0)
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    traci.vehicle.setLaneChangeMode(veh_id, 0)
                if traci.vehicle.getVehicleClass(veh_id) == "emergency":
                    traci.vehicle.setSpeedMode(veh_id, 0)

            timestamp = traci.simulation.getTime()

            # 记录车辆状态
            recorder.record_vehicle_state(timestamp)

            # 碰撞检测：一旦有新碰撞立即终止
            if recorder.record_collisions(timestamp):
                print(f"[{timestamp:.1f}s] 检测到碰撞，仿真立即终止！")
                raise KeyboardInterrupt

    except KeyboardInterrupt:
        print("用户/碰撞中断，开始清理资源...")
    finally:
        # 清理 CARLA 侧所有车辆与传感器
        all_actors = world.get_actors()
        vehicles = [a for a in all_actors if 'vehicle' in a.type_id]
        sensors  = [a for a in all_actors if 'sensor' in a.type_id]
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles + sensors])

        # 关闭 SUMO 与记录器
        traci.close()
        recorder.close()

        # 退出同步模式
        settings.synchronous_mode = False
        world.apply_settings(settings)
        print("资源清理完成，仿真结束。")


if __name__ == "__main__":
    main()