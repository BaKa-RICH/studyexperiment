import traci
import os
import csv
import time
import logging
import sumolib

class SumoDataRecorder:
    def __init__(self):
        # 创建输出目录
        self.output_dir = "sumo_data"
        os.makedirs(self.output_dir, exist_ok=True)

        # 创建CSV文件
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.vehicle_file = open(f"{self.output_dir}/vehicle_trace_{timestamp}.csv", "w", newline='')
        self.collision_file = open(f"{self.output_dir}/collisions_{timestamp}.csv", "w", newline='')

        # 创建CSV写入器
        self.vehicle_writer = csv.writer(self.vehicle_file)
        self.collision_writer = csv.writer(self.collision_file)

        # 写入表头
        self.vehicle_writer.writerow([
            "timestamp", "vehicle_id", "x", "y","vType", "speed", "angle",
            "acceleration", "lane_id", "edge_id"
        ])
        self.collision_writer.writerow([
            "timestamp", "collision_id", "vehicle1", "vehicle2",
            "collision_type"
        ])

        # 碰撞计数器
        self.collision_counter = 0
        self.recorded_collisions = set()

    def record_vehicle_state(self, timestamp):
        """记录所有车辆的状态"""
        for vehicle_id in traci.vehicle.getIDList():
            try:
                pos = traci.vehicle.getPosition(vehicle_id)
                speed = traci.vehicle.getSpeed(vehicle_id)
                angle = traci.vehicle.getAngle(vehicle_id)
                accel = traci.vehicle.getAcceleration(vehicle_id)
                lane_id = traci.vehicle.getLaneID(vehicle_id)
                edge_id = traci.vehicle.getRoadID(vehicle_id)
                vType = traci.vehicle.getTypeID(vehicle_id)

                self.vehicle_writer.writerow([
                    timestamp, vehicle_id, pos[0], pos[1],
                    vType,speed, angle, accel, lane_id, edge_id
                ])
            except traci.TraCIException:
                # 车辆可能已离开仿真
                continue

    def record_collisions(self, timestamp):
        """检测并记录碰撞事件"""
        collisions = traci.simulation.getCollisions()

        for collision in collisions:
            # 生成唯一的碰撞ID
            collision_id = f"collision_{self.collision_counter}"
            self.collision_counter += 1

            # 提取碰撞信息
            collider = collision.collider
            victim = collision.victim
            collision_type = collision.type

            # 避免重复记录同一碰撞
            collision_key = (collider, victim, collision_type)
            if collision_key in self.recorded_collisions:
                continue

            self.recorded_collisions.add(collision_key)

            self.collision_writer.writerow([
                timestamp, collision_id, collider, victim,
                collision_type
            ])

    def close(self):
        """关闭所有文件"""
        self.vehicle_file.close()
        self.collision_file.close()


def main():
    recorder = SumoDataRecorder()
    try:
        while True:
            start = time.time()

            # Step 一次仿真时间（不调用不会推进仿真）
            traci.simulationStep()

            for veh_id in traci.vehicle.getIDList():
                # if traci.vehicle.getVehicleClass(veh_id) == "passenger":
                # traci.vehicle.setLaneChangeMode(veh_id, 0)

                if traci.vehicle.getVehicleClass(veh_id) == "truck":
                    # traci.vehicle.setMinGap(veh_id, 0)
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    traci.vehicle.setLaneChangeMode(veh_id, 0)

                    traci.vehicle.setSpeed(veh_id, 25)
                    traci.vehicle.setColor("truck", (0, 255, 0, 255))  # 卡车绿色

                if traci.vehicle.getVehicleClass(veh_id) == "emergency":
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    # traci.vehicle.setSpeed(veh_id, 30)

            end = time.time()
            elapsed = end - start
            if elapsed < 0.05:
                time.sleep(0.05 - elapsed)

            collisions = traci.simulation.getCollisions()

            for col in collisions:
               # 如果目标车是肇事方或者受害方
               if col.collider == "emergency" or col.victim == "emergency":
                   print('emergency collision')

            if traci.simulation.getTime() > 16.7:
                print(f"目标车辆发生碰撞，停止仿真！")

                traci.vehicle.setSpeedMode("emergency", 0)
                traci.vehicle.setSpeedMode("truck", 0)
                traci.vehicle.setLaneChangeMode("truck", 0)
                traci.vehicle.setLaneChangeMode("emergency", 0)

                traci.vehicle.setSpeed("emergency", 0)
                traci.vehicle.setSpeed("truck", 0)


            if traci.simulation.getTime() > 18:
                break

            # 获取当前SUMO时间戳
            timestamp = traci.simulation.getTime()

            # 记录所有车辆状态
            recorder.record_vehicle_state(timestamp)

            # 记录碰撞事件
            recorder.record_collisions(timestamp)

    except KeyboardInterrupt:
        logging.info("Cancelled by user.")

    finally:
        logging.info("Cleaning up TraCI")
        traci.close()



if __name__ == "__main__":
    sumo_binary = sumolib.checkBinary("sumo-gui")   #
    sumocfg = "./SuZhou/SuzhouNorthStation.sumocfg" # 你的SUMO配置文件

    cmd = [sumo_binary, "-c", sumocfg]
    traci.start(cmd)

    main()
