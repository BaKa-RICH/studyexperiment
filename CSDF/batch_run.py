import argparse
import csv
import os
import sys
import time
from pathlib import Path
import xml.etree.ElementTree as ET


def _ensure_sumo_tools_on_path() -> None:
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        return
    tools_dir = Path(sumo_home) / "tools"
    if tools_dir.exists():
        sys.path.insert(0, str(tools_dir))


def _pick_sumo_binary(prefer_gui: bool) -> str:
    import sumolib

    # Use GUI only when a display is available; default to headless for batch runs.
    if prefer_gui and os.environ.get("DISPLAY"):
        return sumolib.checkBinary("sumo-gui")
    return sumolib.checkBinary("sumo")


def _default_sumocfg() -> str:
    return str((Path(__file__).parent / "scene_4" / "scene4.sumocfg").resolve())


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


def _collision_to_row(sim_time: float, collision) -> dict:
    # SUMO's traci Collision object shape varies slightly by version; be defensive.
    row = {"time": sim_time}
    for key in [
        "collider",
        "victim",
        "colliderType",
        "victimType",
        "colliderSpeed",
        "victimSpeed",
        "collisionType",
        "lane",
        "pos",
    ]:
        if hasattr(collision, key):
            row[key] = getattr(collision, key)
    return row


_UNSUPPORTED_VCLASSES = {
    # SUMO 1.18.0 doesn't recognize these vehicle classes but some exported nets include them.
    "container",
    "cable_car",
    "subway",
    "aircraft",
    "wheelchair",
    "scooter",
    "drone",
}


def _strip_unsupported_vclasses(value: str) -> str:
    parts = [p for p in value.split() if p and p not in _UNSUPPORTED_VCLASSES]
    return " ".join(parts)


def _prepare_compat_sumocfg(sumocfg: str, work_dir: Path, *, keep_gui_files: bool) -> Path:
    """
    SUMO fails hard on unknown vehicle classes used in lane allow/disallow lists.
    Some nets in this repo contain classes that are not available in SUMO 1.18.0.

    To keep the original net intact, write a patched net + sumocfg into work_dir and run that.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    sumocfg_path = Path(sumocfg).resolve()
    tree = ET.parse(sumocfg_path)
    root = tree.getroot()

    # Rewrite input file paths to absolute, because we're writing a new config in work_dir.
    for tag_name in ("route-files", "additional-files"):
        tag = root.find(f".//{tag_name}")
        if tag is not None and tag.get("value"):
            # SUMO allows comma-separated lists.
            parts = [p.strip() for p in tag.get("value").split(",") if p.strip()]
            abs_parts = [str((sumocfg_path.parent / p).resolve()) for p in parts]
            tag.set("value", ",".join(abs_parts))

    gui_only = root.find(".//gui_only")
    if gui_only is not None:
        if keep_gui_files:
            gui_settings = gui_only.find(".//gui-settings-file")
            if gui_settings is not None and gui_settings.get("value"):
                gui_settings.set(
                    "value", str((sumocfg_path.parent / gui_settings.get("value")).resolve())
                )
        else:
            # Avoid SUMO validating gui-only file paths in headless/batch runs.
            root.remove(gui_only)

    net_tag = root.find(".//net-file")
    if net_tag is None or not net_tag.get("value"):
        raise RuntimeError(f"Could not find <net-file> in {sumocfg_path}")

    net_path = (sumocfg_path.parent / net_tag.get("value")).resolve()
    patched_net_path = work_dir / f"{net_path.stem}.compat{net_path.suffix}"

    # Patch allow/disallow vClass lists.
    net_xml = net_path.read_text(encoding="utf-8", errors="replace")
    net_xml_patched = net_xml
    for attr in (" allow=", " disallow="):
        # Very lightweight string patching: replace only inside quoted values.
        # This avoids parsing the whole (potentially large) net XML.
        needle = f'{attr}"'
        start = 0
        while True:
            idx = net_xml_patched.find(needle, start)
            if idx == -1:
                break
            q1 = idx + len(needle)
            q2 = net_xml_patched.find('"', q1)
            if q2 == -1:
                break
            original = net_xml_patched[q1:q2]
            stripped = _strip_unsupported_vclasses(original)
            if stripped != original:
                net_xml_patched = net_xml_patched[:q1] + stripped + net_xml_patched[q2:]
                start = q1 + len(stripped) + 1
            else:
                start = q2 + 1

    patched_net_path.write_text(net_xml_patched, encoding="utf-8")

    # Write a patched sumocfg that points at the patched net via absolute path.
    net_tag.set("value", str(patched_net_path))
    patched_cfg_path = work_dir / f"{sumocfg_path.stem}.compat{sumocfg_path.suffix}"
    tree.write(patched_cfg_path, encoding="utf-8", xml_declaration=False)
    return patched_cfg_path


def run_csdf_sumo(
    *,
    sumocfg: str,
    out_dir: str,
    duration_s: float,
    step_length: float,
    seed: int | None,
    gui: bool,
) -> tuple[Path, Path]:
    _ensure_sumo_tools_on_path()

    import traci
    import sumolib

    # Import CSDF modules after SUMO tools are available.
    from CSDF.core.CoordinateTransform import CartesianFrenetConverter
    from CSDF.modules.BehaviorPlanning.CSDF import BehaviorPlanningSystem
    from CSDF.modules.CavMonitor.monitor import SceneMonitor
    from CSDF.modules.TrajectoryExecutor.TrajectoryExecutor import TrajectoryExecutor
    from CSDF.modules.TrajectoryPlanning.BazierTrajectory import TrajectoryGenerator

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    vehicle_csv = out_path / f"vehicle_trace_{ts}.csv"
    collisions_csv = out_path / f"collisions_{ts}.csv"

    sumo_binary = _pick_sumo_binary(gui)

    # Generate SUMO-compat config (patched net) under the output directory.
    compat_cfg = _prepare_compat_sumocfg(
        sumocfg, out_path / "sumo_cfg", keep_gui_files=gui and bool(os.environ.get("DISPLAY"))
    )

    cmd = [
        sumo_binary,
        "--configuration-file",
        str(compat_cfg),
        "--step-length",
        str(step_length),
        "--start",
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]

    # Start SUMO and connect via TraCI.
    traci.start(cmd)

    # Scene and planner setup. Scene 4 uses lane "-2_3" as reference in original code.
    converter = CartesianFrenetConverter(traci.lane.getShape("-2_3"))
    cav_ids = ["cav_3_0", "cav_2_0", "cav_2_1"]
    scene_monitor = SceneMonitor(cav_ids)
    behavior_planner = BehaviorPlanningSystem(converter)
    traj_planner = TrajectoryGenerator(converter, delta_t=2.0, dt=step_length)
    traj_executor = TrajectoryExecutor()

    vehicle_fields = [
        "time",
        "veh_id",
        "type_id",
        "vclass",
        "lane_id",
        "route_id",
        "x",
        "y",
        "speed",
        "angle",
    ]
    collision_fields = [
        "time",
        "collider",
        "victim",
        "colliderType",
        "victimType",
        "colliderSpeed",
        "victimSpeed",
        "collisionType",
        "lane",
        "pos",
    ]

    t_end = None if duration_s <= 0 else duration_s

    try:
        with vehicle_csv.open("w", newline="", encoding="utf-8") as vf, collisions_csv.open(
            "w", newline="", encoding="utf-8"
        ) as cf:
            vw = csv.DictWriter(vf, fieldnames=vehicle_fields)
            cw = csv.DictWriter(cf, fieldnames=collision_fields)
            vw.writeheader()
            cw.writeheader()

            while True:
                sim_time = float(traci.simulation.getTime())
                if t_end is not None and sim_time >= t_end:
                    break

                step_start = time.time()
                traci.simulationStep()

                # Induce aggressive behavior as in CSDF/main.py.
                if sim_time > 3:
                    for cav_id in cav_ids:
                        if cav_id in traci.vehicle.getIDList():
                            traci.vehicle.setSpeedMode(cav_id, 0)
                            traci.vehicle.setLaneChangeMode(cav_id, 0)

                if sim_time >= 5 and "hdv_3_0" in traci.vehicle.getIDList():
                    traci.vehicle.setLaneChangeMode("hdv_3_0", 0)
                    traci.vehicle.setSpeedMode("hdv_3_0", 0)
                    traci.vehicle.setSpeed("hdv_3_0", 10)

                if 5 <= sim_time <= 10 and "cav_3_0" in traci.vehicle.getIDList():
                    traci.vehicle.setSpeed("cav_3_0", 28)

                # Update monitor and run CSDF when risk is detected.
                scene_monitor.update()
                hdvs = scene_monitor.regular_vehicles
                cavs = scene_monitor.cav_vehicles
                potential_decisions = scene_monitor.potential_region

                if sim_time > 5 and "cav_3_0" in cavs and cavs["cav_3_0"].lane_id == "-2_3":
                    potential_decisions["cav_3_0"] = [2, 5]

                for cav in cavs.values():
                    if getattr(cav, "risk_level", None) and cav.risk_level.value in (3, 4):
                        start_compute = time.time()
                        behavior_out = behavior_planner.plan_behavior(
                            sim_time, hdvs, cavs, potential_decisions
                        )
                        traj_planner.generate_trajectories(
                            behavior_output=behavior_out, cav_vehicles=cavs, base_timestamp=sim_time
                        )
                        # TrajectoryExecutor reads planned state from CAV objects.
                        traj_executor.execute(cavs)
                        _ = time.time() - start_compute
                        break
                else:
                    # Still execute any previously planned trajectories.
                    traj_executor.execute(cavs)

                # Sync planned data back into monitor state (mirrors CSDF/main.py).
                for cav_id in cavs.keys():
                    cav = cavs[cav_id]
                    scene_monitor.set_cav_planned(cav_id, cav.isPlanned)
                    scene_monitor.set_cav_trajectory(cav_id, cav.planned_trajectory)

                # Export per-vehicle state.
                for veh_id in traci.vehicle.getIDList():
                    x, y = traci.vehicle.getPosition(veh_id)
                    vw.writerow(
                        {
                            "time": sim_time,
                            "veh_id": veh_id,
                            "type_id": traci.vehicle.getTypeID(veh_id),
                            "vclass": traci.vehicle.getVehicleClass(veh_id),
                            "lane_id": traci.vehicle.getLaneID(veh_id),
                            "route_id": traci.vehicle.getRouteID(veh_id),
                            "x": x,
                            "y": y,
                            "speed": traci.vehicle.getSpeed(veh_id),
                            "angle": traci.vehicle.getAngle(veh_id),
                        }
                    )

                # Export collisions.
                for col in traci.simulation.getCollisions():
                    cw.writerow(_collision_to_row(sim_time, col))

                # Keep wall-clock in sync for more stable behavior.
                elapsed = time.time() - step_start
                if elapsed < step_length:
                    time.sleep(step_length - elapsed)
    finally:
        traci.close()

    return vehicle_csv, collisions_csv


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Batch-run CSDF (pure SUMO) and export CSV traces.")
    p.add_argument("--sumocfg", default=_default_sumocfg(), help="Path to .sumocfg file")
    p.add_argument("--out-dir", default=str((Path(__file__).parent / "sumo_data").resolve()))
    p.add_argument(
        "--duration-s",
        type=float,
        default=30.0,
        help="Simulation duration to run (seconds). <=0 runs indefinitely.",
    )
    p.add_argument("--step-length", type=float, default=0.05, help="Simulation step length (s)")
    p.add_argument("--seed", type=int, default=None, help="SUMO random seed (optional)")
    p.add_argument("--gui", action="store_true", help="Use sumo-gui when DISPLAY is available")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    vehicle_csv, collisions_csv = run_csdf_sumo(
        sumocfg=args.sumocfg,
        out_dir=args.out_dir,
        duration_s=args.duration_s,
        step_length=args.step_length,
        seed=args.seed,
        gui=args.gui,
    )
    print(f"Wrote {vehicle_csv}")
    print(f"Wrote {collisions_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
