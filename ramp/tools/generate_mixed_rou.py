#!/usr/bin/env python3
"""Generate mixed CAV/HDV traffic rou.xml for SUMO ramp merging scenarios.

Produces individual <vehicle> elements (not <flow>) with deterministic
or Poisson arrivals. Each vehicle is randomly assigned as CAV or HDV
based on the specified penetration ratio.
"""

import argparse
import json
import os
import random
import xml.etree.ElementTree as ET
from pathlib import Path


VTYPE_CAV = {
    "id": "cav",
    "accel": "2.6",
    "decel": "4.5",
    "length": "5.0",
    "minGap": "2.5",
    "tau": "1.0",
    "maxSpeed": "25.0",
    "sigma": "0.0",
    "speedDev": "0.0",
}

VTYPE_HDV = {
    "id": "hdv",
    "accel": "2.6",
    "decel": "4.5",
    "length": "5.0",
    "minGap": "2.5",
    "tau": "1.0",
    "maxSpeed": "25.0",
    "sigma": "0.5",
    "speedDev": "0.1",
    "lcStrategic": "1.0",
}

ROUTE_MAIN = {"id": "main_route", "edges": "main_h1 main_h2 main_h3 main_h4"}
ROUTE_RAMP = {"id": "ramp_route", "edges": "ramp_h5 ramp_h6 main_h3 main_h4"}

MAIN_LANES = [0, 1, 2, 3]
RAMP_LANE = 1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate mixed CAV/HDV rou.xml for ramp merging scenarios."
    )
    parser.add_argument(
        "--cav-ratio", type=float, default=0.6,
        help="CAV penetration ratio (0.0-1.0, default 0.6)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for deterministic generation (default 42)"
    )
    parser.add_argument(
        "--main-vph", type=int, default=1200,
        help="Main road flow per lane in veh/h (default 1200)"
    )
    parser.add_argument(
        "--ramp-vph", type=int, default=500,
        help="Ramp R1 flow in veh/h (default 500)"
    )
    parser.add_argument(
        "--duration", type=int, default=300,
        help="Simulation duration in seconds (default 300)"
    )
    parser.add_argument(
        "--output", type=str, default="mixed.rou.xml",
        help="Output rou.xml file path (default mixed.rou.xml)"
    )
    parser.add_argument(
        "--arrival-mode", type=str, default="uniform",
        choices=["uniform", "poisson"],
        help="Vehicle arrival distribution (default uniform)"
    )
    return parser.parse_args()


def generate_departures(vph, duration_s, rng, mode="uniform"):
    """Generate departure times for a single lane/source.

    Returns a sorted list of departure times in seconds.
    """
    if vph <= 0:
        return []

    headway_s = 3600.0 / vph

    if mode == "uniform":
        n_vehicles = int(vph * duration_s / 3600.0)
        return [i * headway_s for i in range(n_vehicles)]

    departures = []
    t = rng.expovariate(1.0 / headway_s)
    while t < duration_s:
        departures.append(t)
        t += rng.expovariate(1.0 / headway_s)
    return departures


def build_vehicles(args, rng):
    """Build all vehicle entries as a list of dicts sorted by depart time."""
    vehicles = []

    for lane in MAIN_LANES:
        departures = generate_departures(
            args.main_vph, args.duration, rng, args.arrival_mode
        )
        for seq, depart in enumerate(departures):
            vtype = "cav" if rng.random() < args.cav_ratio else "hdv"
            vehicles.append({
                "id": f"main_L{lane}_{seq}",
                "type": vtype,
                "depart": f"{depart:.2f}",
                "route": "main_route",
                "departLane": str(lane),
                "departSpeed": "max",
            })

    departures = generate_departures(
        args.ramp_vph, args.duration, rng, args.arrival_mode
    )
    for seq, depart in enumerate(departures):
        vtype = "cav" if rng.random() < args.cav_ratio else "hdv"
        vehicles.append({
            "id": f"ramp_R1_{seq}",
            "type": vtype,
            "depart": f"{depart:.2f}",
            "route": "ramp_route",
            "departLane": str(RAMP_LANE),
            "departSpeed": "max",
        })

    vehicles.sort(key=lambda v: float(v["depart"]))
    return vehicles


def write_rou_xml(vehicles, output_path):
    """Write the rou.xml file with vTypes, routes, and vehicles."""
    root = ET.Element("routes")

    cav_elem = ET.SubElement(root, "vType")
    for k, v in VTYPE_CAV.items():
        cav_elem.set(k, v)

    hdv_elem = ET.SubElement(root, "vType")
    for k, v in VTYPE_HDV.items():
        hdv_elem.set(k, v)

    main_route_elem = ET.SubElement(root, "route")
    for k, v in ROUTE_MAIN.items():
        main_route_elem.set(k, v)

    ramp_route_elem = ET.SubElement(root, "route")
    for k, v in ROUTE_RAMP.items():
        ramp_route_elem.set(k, v)

    for veh in vehicles:
        veh_elem = ET.SubElement(root, "vehicle")
        for k, v in veh.items():
            veh_elem.set(k, v)

    ET.indent(root, space="    ")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    tree = ET.ElementTree(root)
    tree.write(output_path, encoding="unicode", xml_declaration=False)

    with open(output_path, "r") as f:
        content = f.read()
    with open(output_path, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + content)


def validate_xml(output_path):
    """Parse the generated XML to verify it is well-formed."""
    ET.parse(output_path)
    print(f"[PASS] XML validation: {output_path} is well-formed.")


def write_meta(args, vehicles, output_path):
    """Write rou_meta.json alongside the rou.xml."""
    cav_count = sum(1 for v in vehicles if v["type"] == "cav")
    hdv_count = sum(1 for v in vehicles if v["type"] == "hdv")
    total = len(vehicles)

    meta = {
        "seed": args.seed,
        "cav_ratio": args.cav_ratio,
        "main_vph": args.main_vph,
        "ramp_vph": args.ramp_vph,
        "duration": args.duration,
        "arrival_mode": args.arrival_mode,
        "total_vehicles": total,
        "actual_cav_count": cav_count,
        "actual_hdv_count": hdv_count,
        "actual_cav_ratio": round(cav_count / total, 4) if total > 0 else 0.0,
    }

    meta_path = os.path.join(
        os.path.dirname(os.path.abspath(output_path)), "rou_meta.json"
    )
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"[INFO] Meta written to: {meta_path}")
    return meta


def print_summary(meta):
    """Print a human-readable summary of the generation."""
    print("=" * 50)
    print("Mixed Traffic rou.xml Generation Summary")
    print("=" * 50)
    print(f"  Seed:            {meta['seed']}")
    print(f"  Target CAV ratio:{meta['cav_ratio']:.1%}")
    print(f"  Main road flow:  {meta['main_vph']} veh/h/lane x 4 lanes")
    print(f"  Ramp R1 flow:    {meta['ramp_vph']} veh/h/lane")
    print(f"  Duration:        {meta['duration']}s")
    print(f"  Arrival mode:    {meta['arrival_mode']}")
    print("-" * 50)
    print(f"  Total vehicles:  {meta['total_vehicles']}")
    print(f"  CAV count:       {meta['actual_cav_count']}")
    print(f"  HDV count:       {meta['actual_hdv_count']}")
    print(f"  Actual CAV ratio:{meta['actual_cav_ratio']:.2%}")
    print("=" * 50)

    ratio = meta["actual_cav_ratio"]
    target = meta["cav_ratio"]
    tolerance = 0.03
    if abs(ratio - target) <= tolerance:
        print(f"[PASS] CAV ratio {ratio:.2%} is within "
              f"[{target - tolerance:.0%}, {target + tolerance:.0%}].")
    else:
        print(f"[WARN] CAV ratio {ratio:.2%} deviates from target "
              f"{target:.0%} by more than {tolerance:.0%}.")


def main():
    args = parse_args()

    rng = random.Random(args.seed)

    vehicles = build_vehicles(args, rng)

    write_rou_xml(vehicles, args.output)
    print(f"[INFO] Generated {len(vehicles)} vehicles -> {args.output}")

    validate_xml(args.output)

    meta = write_meta(args, vehicles, args.output)

    print_summary(meta)


if __name__ == "__main__":
    main()
