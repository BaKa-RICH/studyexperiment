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

            current_time = traci.simulation.getTime()

            all_vehicles = traci.vehicle.getIDList()

            for vel in all_vehicles:
                traci.vehicle.setSpeedMode(vel, 0)
                traci.vehicle.setLaneChangeMode(vel, 0)
                traci.vehicle.setSpeed(vel, 28)

            if "hdv_3_0" in all_vehicles and current_time>=5:

                traci.vehicle.setLaneChangeMode("hdv_3_0", 0)
                traci.vehicle.setSpeedMode("hdv_3_0", 0)
                traci.vehicle.setSpeed("hdv_3_0", 10)

                traci.vehicle.setLaneChangeMode("cav_3_0", 0)
                traci.vehicle.setSpeedMode("cav_3_0", 0)
                traci.vehicle.setSpeed("cav_3_0", 28)

            # 控制仿真步长
            elapsed = time.time() - start
            if elapsed < 0.05:
                time.sleep(0.05 - elapsed)

    except KeyboardInterrupt:
        logging.info("Cancelled by user.")

    finally:
        logging.info("Cleaning up TraCI")
        traci.close()


if __name__ == "__main__":
    sumo_binary = sumolib.checkBinary("sumo-gui")   #
    sumocfg = "./scene_4/scene4.sumocfg" # 你的SUMO配置文件

    cmd = [sumo_binary, "-c", sumocfg]
    traci.start(cmd)

    run()