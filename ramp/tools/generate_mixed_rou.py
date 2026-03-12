#!/usr/bin/env python3
"""Generate mixed CAV/HDV traffic rou.xml for SUMO ramp merging scenarios.

Produces individual <vehicle> elements (not <flow>) with deterministic
or Poisson arrivals. Each vehicle is randomly assigned as CAV or HDV
based on the specified penetration ratio.

When ``--use-profiles`` is enabled, HDV vehicles are further assigned
to heterogeneous Krauss profiles (normal / distracted / aggressive /
hesitant) according to ``--hdv-profile-weights``.

All vType definitions are imported from ``ramp.common.vehicle_defs``
(Single Source of Truth).  This module must never define its own vType
parameters.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ramp.common.vehicle_defs import (
    HDV_PROFILES,
    MAIN_LANES,
    RAMP_LANE,
    ROUTE_MAIN,
    ROUTE_RAMP,
    VEH_TYPE_CAV,
    VEH_TYPE_HDV,
    is_hdv,
    vtype_meta_dict,
    write_vtypes_to_xml,
)

DEFAULT_HDV_PROFILE_WEIGHTS: dict[str, float] = {
    p["id"]: 1.0 for p in HDV_PROFILES
}


def parse_hdv_profile_weights(raw: str) -> dict[str, float]:
    """Parse a comma-separated ``name:weight`` string into a dict.

    Example: ``"hdv_normal:0.4,hdv_distracted:0.2,hdv_aggressive:0.2,hdv_hesitant:0.2"``
    """
    valid_ids = {p["id"] for p in HDV_PROFILES}
    weights: dict[str, float] = {}
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(f"Invalid weight token (expected name:weight): '{token}'")
        name, w_str = token.split(":", 1)
        name = name.strip()
        if name not in valid_ids:
            raise ValueError(
                f"Unknown HDV profile '{name}'. Valid: {sorted(valid_ids)}"
            )
        weights[name] = float(w_str)
    if not weights:
        raise ValueError("No valid HDV profile weights provided")
    total = sum(weights.values())
    WEIGHT_TOL = 1e-6
    if total <= 0:
        raise ValueError(f"HDV profile weights must sum to > 0, got {total}")
    if abs(total - 1.0) > WEIGHT_TOL:
        weights = {k: v / total for k, v in weights.items()}
    return weights


def _pick_hdv_profile(rng: random.Random, weights: dict[str, float]) -> str:
    """Return a random HDV profile ID based on *weights*."""
    ids = list(weights.keys())
    ws = [weights[k] for k in ids]
    return rng.choices(ids, weights=ws, k=1)[0]


def parse_args() -> argparse.Namespace:
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
    parser.add_argument(
        "--use-profiles", action="store_true", default=False,
        help="Use heterogeneous HDV profiles instead of single 'hdv' type"
    )
    parser.add_argument(
        "--hdv-profile-weights", type=str, default=None,
        help=(
            "HDV profile weights as 'name:weight,...'. "
            "Example: 'hdv_normal:0.4,hdv_distracted:0.2,hdv_aggressive:0.2,hdv_hesitant:0.2'. "
            "Weights auto-normalize to sum=1. Implies --use-profiles."
        ),
    )
    return parser.parse_args()


def generate_departures(vph: int, duration_s: int, rng: random.Random,
                        mode: str = "uniform") -> list[float]:
    """Generate departure times for a single lane/source.

    Returns a sorted list of departure times in seconds.
    """
    if vph <= 0:
        return []

    headway_s = 3600.0 / vph

    if mode == "uniform":
        n_vehicles = int(vph * duration_s / 3600.0)
        return [i * headway_s for i in range(n_vehicles)]

    departures: list[float] = []
    t = rng.expovariate(1.0 / headway_s)
    while t < duration_s:
        departures.append(t)
        t += rng.expovariate(1.0 / headway_s)
    return departures


def build_vehicles(
    *,
    cav_ratio: float,
    main_vph: int,
    ramp_vph: int,
    duration: int,
    arrival_mode: str,
    rng: random.Random,
    use_profiles: bool = False,
    hdv_profile_weights: dict[str, float] | None = None,
) -> list[dict[str, str]]:
    """Build all vehicle entries as a list of dicts sorted by depart time."""
    vehicles: list[dict[str, str]] = []
    weights = hdv_profile_weights or DEFAULT_HDV_PROFILE_WEIGHTS

    def _hdv_type() -> str:
        if use_profiles:
            return _pick_hdv_profile(rng, weights)
        return VEH_TYPE_HDV

    for lane in MAIN_LANES:
        departures = generate_departures(main_vph, duration, rng, arrival_mode)
        for seq, depart in enumerate(departures):
            vtype = VEH_TYPE_CAV if rng.random() < cav_ratio else _hdv_type()
            vehicles.append({
                "id": f"main_L{lane}_{seq}",
                "type": vtype,
                "depart": f"{depart:.2f}",
                "route": "main_route",
                "departLane": str(lane),
                "departSpeed": "max",
            })

    departures = generate_departures(ramp_vph, duration, rng, arrival_mode)
    for seq, depart in enumerate(departures):
        vtype = VEH_TYPE_CAV if rng.random() < cav_ratio else _hdv_type()
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


def write_rou_xml(
    vehicles: list[dict[str, str]],
    output_path: str | Path,
    *,
    use_profiles: bool = False,
) -> None:
    """Write the rou.xml file with vTypes, routes, and vehicles."""
    root = ET.Element("routes")

    write_vtypes_to_xml(root, use_profiles=use_profiles)

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

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.ElementTree(root)
    tree.write(str(output_path), encoding="unicode", xml_declaration=False)

    content = output_path.read_text()
    output_path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + content)


def validate_xml(output_path: str | Path) -> None:
    """Parse the generated XML to verify it is well-formed."""
    ET.parse(str(output_path))
    print(f"[PASS] XML validation: {output_path} is well-formed.")


def write_meta(
    *,
    seed: int,
    cav_ratio: float,
    main_vph: int,
    ramp_vph: int,
    duration: int,
    arrival_mode: str,
    vehicles: list[dict[str, str]],
    output_path: str | Path,
    use_profiles: bool = False,
    hdv_profile_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Write rou_meta.json alongside the rou.xml.  Returns the meta dict."""
    cav_count = sum(1 for v in vehicles if v["type"] == VEH_TYPE_CAV)
    hdv_count = sum(1 for v in vehicles if is_hdv(v["type"]))
    total = len(vehicles)

    meta: dict[str, Any] = {
        "seed": seed,
        "cav_ratio": cav_ratio,
        "main_vph": main_vph,
        "ramp_vph": ramp_vph,
        "duration": duration,
        "arrival_mode": arrival_mode,
        "total_vehicles": total,
        "actual_cav_count": cav_count,
        "actual_hdv_count": hdv_count,
        "actual_cav_ratio": round(cav_count / total, 4) if total > 0 else 0.0,
        "use_profiles": use_profiles,
    }

    if use_profiles:
        profile_counts: dict[str, int] = {}
        for v in vehicles:
            vt = v["type"]
            if is_hdv(vt):
                profile_counts[vt] = profile_counts.get(vt, 0) + 1
        meta["hdv_profile_counts"] = profile_counts
        meta["hdv_profile_weights"] = hdv_profile_weights or DEFAULT_HDV_PROFILE_WEIGHTS

    meta.update(vtype_meta_dict(use_profiles=use_profiles))

    output_path = Path(output_path)
    meta_path = output_path.parent / "rou_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[INFO] Meta written to: {meta_path}")
    return meta


def print_summary(meta: dict[str, Any]) -> None:
    """Print a human-readable summary of the generation."""
    print("=" * 50)
    print("Mixed Traffic rou.xml Generation Summary")
    print("=" * 50)
    print(f"  Seed:            {meta['seed']}")
    print(f"  Target CAV ratio:{meta['cav_ratio']:.1%}")
    print(f"  Main road flow:  {meta['main_vph']} veh/h/lane x {len(MAIN_LANES)} lanes")
    print(f"  Ramp R1 flow:    {meta['ramp_vph']} veh/h/lane")
    print(f"  Duration:        {meta['duration']}s")
    print(f"  Arrival mode:    {meta['arrival_mode']}")
    use_profiles = meta.get("use_profiles", False)
    if use_profiles:
        print(f"  HDV profiles:    ENABLED ({len(HDV_PROFILES)} profiles)")
        for pid, cnt in sorted(meta.get("hdv_profile_counts", {}).items()):
            print(f"    {pid}: {cnt}")
    else:
        print(f"  carFollowModel:  {meta.get('vtype_hdv_car_follow_model', 'Krauss')}")
        print(f"  HDV sigma:       {meta.get('vtype_hdv_sigma', '?')}")
    print("-" * 50)
    print(f"  Total vehicles:  {meta['total_vehicles']}")
    print(f"  CAV count:       {meta['actual_cav_count']}")
    print(f"  HDV count:       {meta['actual_hdv_count']}")
    print(f"  Actual CAV ratio:{meta['actual_cav_ratio']:.2%}")
    print("=" * 50)

    ratio = meta["actual_cav_ratio"]
    target = meta["cav_ratio"]
    TOLERANCE = 0.03
    if abs(ratio - target) <= TOLERANCE:
        print(f"[PASS] CAV ratio {ratio:.2%} is within "
              f"[{target - TOLERANCE:.0%}, {target + TOLERANCE:.0%}].")
    else:
        print(f"[WARN] CAV ratio {ratio:.2%} deviates from target "
              f"{target:.0%} by more than {TOLERANCE:.0%}.")


def generate_rou_xml(
    *,
    seed: int = 42,
    cav_ratio: float = 0.6,
    main_vph: int = 1200,
    ramp_vph: int = 500,
    duration: int = 300,
    arrival_mode: str = "uniform",
    output: str | Path = "mixed.rou.xml",
    use_profiles: bool = False,
    hdv_profile_weights: dict[str, float] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Programmatic API: generate rou.xml + rou_meta.json.

    Returns ``(rou_path, meta_dict)`` for downstream consumption.
    """
    rng = random.Random(seed)

    vehicles = build_vehicles(
        cav_ratio=cav_ratio,
        main_vph=main_vph,
        ramp_vph=ramp_vph,
        duration=duration,
        arrival_mode=arrival_mode,
        rng=rng,
        use_profiles=use_profiles,
        hdv_profile_weights=hdv_profile_weights,
    )

    rou_path = Path(output).resolve()
    write_rou_xml(vehicles, rou_path, use_profiles=use_profiles)
    validate_xml(rou_path)

    meta = write_meta(
        seed=seed,
        cav_ratio=cav_ratio,
        main_vph=main_vph,
        ramp_vph=ramp_vph,
        duration=duration,
        arrival_mode=arrival_mode,
        vehicles=vehicles,
        output_path=rou_path,
        use_profiles=use_profiles,
        hdv_profile_weights=hdv_profile_weights,
    )

    print_summary(meta)
    return rou_path, meta


def main() -> None:
    args = parse_args()
    use_profiles = args.use_profiles
    hdv_profile_weights: dict[str, float] | None = None
    if args.hdv_profile_weights:
        use_profiles = True
        hdv_profile_weights = parse_hdv_profile_weights(args.hdv_profile_weights)
    generate_rou_xml(
        seed=args.seed,
        cav_ratio=args.cav_ratio,
        main_vph=args.main_vph,
        ramp_vph=args.ramp_vph,
        duration=args.duration,
        arrival_mode=args.arrival_mode,
        output=args.output,
        use_profiles=use_profiles,
        hdv_profile_weights=hdv_profile_weights,
    )


if __name__ == "__main__":
    main()
