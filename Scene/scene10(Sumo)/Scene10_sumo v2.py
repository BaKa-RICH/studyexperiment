import os
import sys
import time
import logging
from pathlib import Path

# Prefer the SUMO-bundled Python tools when available to avoid version skew between
# the system SUMO binary and PyPI `traci`/`sumolib`.
_sumo_home = os.environ.get("SUMO_HOME")
if _sumo_home:
    _sumo_tools = Path(_sumo_home) / "tools"
    if _sumo_tools.exists():
        sys.path.insert(0, str(_sumo_tools))

import traci
import sumolib

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
    # Prefer GUI when a display is available; otherwise fall back to headless SUMO.
    use_gui = bool(os.environ.get("DISPLAY")) and os.environ.get("SUMO_GUI", "1") != "0"
    sumo_binary = sumolib.checkBinary("sumo-gui" if use_gui else "sumo")

    # Resolve config relative to this script, so it works regardless of CWD.
    sumocfg = str((Path(__file__).parent / "SuZhou" / "SuzhouNorthStation.sumocfg").resolve())

    cmd = [sumo_binary, "-c", sumocfg, "--start"]
    traci.start(cmd)

    run()
