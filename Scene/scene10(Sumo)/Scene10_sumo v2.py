import traci
import sumolib
import time
import logging

def run():
    try:
        while True:
            start = time.time()

            # Step 一次仿真时间（不调用不会推进仿真）
            traci.simulationStep()

            for veh_id in traci.vehicle.getIDList():

                if traci.vehicle.getVehicleClass(veh_id) == "truck":
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    traci.vehicle.setLaneChangeMode(veh_id, 0)
                    traci.vehicle.setSpeed(veh_id, 24.0)
                    traci.vehicle.setColor(veh_id, (0, 255, 0, 255))

                if traci.vehicle.getVehicleClass(veh_id) == "emergency":
                    traci.vehicle.setSpeedMode(veh_id, 7)

            # 控制仿真步长
            elapsed = time.time() - start
            if elapsed < 0.05:
                time.sleep(0.05 - elapsed)

            collisions = traci.simulation.getCollisions()

            if traci.simulation.getTime() > 17:
                print("目标车辆发生碰撞，停止仿真！")

                traci.vehicle.setSpeedMode("truck", 0)
                traci.vehicle.setLaneChangeMode("truck", 0)
                traci.vehicle.setSpeed("truck", 0)

                traci.vehicle.setSpeedMode("emergency", 0)
                traci.vehicle.setLaneChangeMode("emergency", 0)
                traci.vehicle.setSpeed("emergency", 0)

            if traci.simulation.getTime() > 18:
                break

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

    run()

