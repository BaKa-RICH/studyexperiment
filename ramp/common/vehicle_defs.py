"""Single Source of Truth for vehicle type definitions, route topology, and constants.

All vType parameters used in rou.xml generation, runtime filtering, and
controller logic must originate from this module.  Other modules import
from here instead of hard-coding ``'cav'`` / ``'hdv'`` strings or
duplicating parameter dictionaries.

History:
  - 2026-03-12: sigma=0.7, speedDev=0.15 adopted as canonical HDV profile.
    Earlier scenarios (ramp__mlane_v2_mixed, _hf) used sigma=0.5, speedDev=0.1.
    If those baselines need re-comparison, regenerate rou.xml from this module.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VEH_TYPE_CAV: str = "cav"
VEH_TYPE_HDV: str = "hdv"

VTYPE_CAV: dict[str, str] = {
    "id": VEH_TYPE_CAV,
    "carFollowModel": "Krauss",
    "accel": "2.6",
    "decel": "4.5",
    "length": "5.0",
    "minGap": "2.5",
    "tau": "1.0",
    "maxSpeed": "25.0",
    "sigma": "0.0",
    "speedDev": "0.0",
}

VTYPE_HDV: dict[str, str] = {
    "id": VEH_TYPE_HDV,
    "carFollowModel": "Krauss",
    "accel": "2.6",
    "decel": "4.5",
    "length": "5.0",
    "minGap": "2.5",
    "tau": "1.0",
    "maxSpeed": "25.0",
    "sigma": "0.7",
    "speedDev": "0.15",
    "lcStrategic": "1.0",
}

ROUTE_MAIN: dict[str, str] = {"id": "main_route", "edges": "main_h1 main_h2 main_h3 main_h4"}
ROUTE_RAMP: dict[str, str] = {"id": "ramp_route", "edges": "ramp_h5 ramp_h6 main_h3 main_h4"}

MAIN_LANES: list[int] = [0, 1, 2, 3]
RAMP_LANE: int = 1

_CRITICAL_VTYPE_ATTRS = ("sigma", "speedDev", "carFollowModel")


def write_vtypes_to_xml(root: ET.Element) -> None:
    """Append canonical <vType> elements to an XML root."""
    for vtype_dict in (VTYPE_CAV, VTYPE_HDV):
        elem = ET.SubElement(root, "vType")
        for k, v in vtype_dict.items():
            elem.set(k, v)


def validate_rou_vtypes(xml_path: str | Path) -> list[str]:
    """Compare vType definitions in *xml_path* against this module's SSoT.

    Returns a list of discrepancy messages (empty == all consistent).
    Each discrepancy is also logged as WARNING.
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        msg = f"rou.xml not found: {xml_path}"
        logger.warning(msg)
        return [msg]

    tree = ET.parse(xml_path)
    root = tree.getroot()
    issues: list[str] = []

    ssot = {VEH_TYPE_CAV: VTYPE_CAV, VEH_TYPE_HDV: VTYPE_HDV}

    xml_vtypes: dict[str, dict[str, str]] = {}
    for vtype_elem in root.findall("vType"):
        vid = vtype_elem.get("id", "")
        if vid:
            xml_vtypes[vid] = dict(vtype_elem.attrib)

    for type_id, expected in ssot.items():
        if type_id not in xml_vtypes:
            msg = f"vType '{type_id}' missing from {xml_path.name}"
            issues.append(msg)
            logger.warning(msg)
            continue

        actual = xml_vtypes[type_id]
        for attr in _CRITICAL_VTYPE_ATTRS:
            exp_val = expected.get(attr)
            act_val = actual.get(attr)
            if exp_val is not None and act_val != exp_val:
                msg = (
                    f"vType '{type_id}' attr '{attr}' mismatch in {xml_path.name}: "
                    f"expected={exp_val}, actual={act_val}"
                )
                issues.append(msg)
                logger.warning(msg)

    if not issues:
        logger.info("vType validation passed: %s", xml_path.name)

    return issues


def vtype_meta_dict() -> dict[str, Any]:
    """Return vType parameters as a flat dict suitable for rou_meta.json."""
    return {
        "vtype_cav_sigma": VTYPE_CAV["sigma"],
        "vtype_cav_speed_dev": VTYPE_CAV["speedDev"],
        "vtype_cav_car_follow_model": VTYPE_CAV["carFollowModel"],
        "vtype_hdv_sigma": VTYPE_HDV["sigma"],
        "vtype_hdv_speed_dev": VTYPE_HDV["speedDev"],
        "vtype_hdv_car_follow_model": VTYPE_HDV["carFollowModel"],
        "vtype_hdv_lc_strategic": VTYPE_HDV.get("lcStrategic", ""),
    }
