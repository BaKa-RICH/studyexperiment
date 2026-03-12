"""Single Source of Truth for vehicle type definitions, route topology, and constants.

All vType parameters used in rou.xml generation, runtime filtering, and
controller logic must originate from this module.  Other modules import
from here instead of hard-coding ``'cav'`` / ``'hdv'`` strings or
duplicating parameter dictionaries.

History:
  - 2026-03-12 Todo 3.1: Heterogeneous Krauss HDV library.
    4 HDV profiles: normal, distracted, aggressive, hesitant.
    Gate 2 parameters: sigma, speedDev, actionStepLength, lcCooperative,
    lcSpeedGain, lcAssertive, lcStrategic.
  - 2026-03-12: sigma=0.7, speedDev=0.15 adopted as canonical HDV profile.
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

_HDV_BASE: dict[str, str] = {
    "carFollowModel": "Krauss",
    "length": "5.0",
}

VTYPE_HDV_NORMAL: dict[str, str] = {
    **_HDV_BASE,
    "id": "hdv_normal",
    "accel": "2.6", "decel": "4.5",
    "minGap": "2.5", "tau": "1.0", "maxSpeed": "25.0",
    "sigma": "0.5", "speedDev": "0.1",
    "actionStepLength": "0.5",
    "lcCooperative": "1.0", "lcSpeedGain": "1.0",
    "lcAssertive": "1.0", "lcStrategic": "1.0",
}

VTYPE_HDV_DISTRACTED: dict[str, str] = {
    **_HDV_BASE,
    "id": "hdv_distracted",
    "accel": "2.6", "decel": "4.5",
    "minGap": "2.5", "tau": "1.0", "maxSpeed": "25.0",
    "sigma": "0.7", "speedDev": "0.15",
    "actionStepLength": "0.8",
    "lcCooperative": "0.7", "lcSpeedGain": "0.5",
    "lcAssertive": "0.8", "lcStrategic": "0.5",
}

VTYPE_HDV_AGGRESSIVE: dict[str, str] = {
    **_HDV_BASE,
    "id": "hdv_aggressive",
    "accel": "3.0", "decel": "5.0",
    "minGap": "2.0", "tau": "0.8", "maxSpeed": "27.0",
    "sigma": "0.4", "speedDev": "0.08",
    "actionStepLength": "0.3",
    "lcCooperative": "0.3", "lcSpeedGain": "1.5",
    "lcAssertive": "1.5", "lcStrategic": "1.2",
}

VTYPE_HDV_HESITANT: dict[str, str] = {
    **_HDV_BASE,
    "id": "hdv_hesitant",
    "accel": "2.0", "decel": "4.0",
    "minGap": "3.0", "tau": "1.5", "maxSpeed": "23.0",
    "sigma": "0.6", "speedDev": "0.12",
    "actionStepLength": "0.6",
    "lcCooperative": "0.9", "lcSpeedGain": "0.3",
    "lcAssertive": "0.5", "lcStrategic": "0.8",
}

VTYPE_HDV: dict[str, str] = {
    "id": VEH_TYPE_HDV,
    "carFollowModel": "Krauss",
    "accel": "2.6", "decel": "4.5",
    "length": "5.0", "minGap": "2.5",
    "tau": "1.0", "maxSpeed": "25.0",
    "sigma": "0.7", "speedDev": "0.15",
    "lcStrategic": "1.0",
}

HDV_PROFILES: tuple[dict[str, str], ...] = (
    VTYPE_HDV_NORMAL,
    VTYPE_HDV_DISTRACTED,
    VTYPE_HDV_AGGRESSIVE,
    VTYPE_HDV_HESITANT,
)

HDV_PROFILE_IDS: frozenset[str] = frozenset(
    p["id"] for p in HDV_PROFILES
)

HDV_VTYPE_IDS: frozenset[str] = HDV_PROFILE_IDS | {VEH_TYPE_HDV}


def is_hdv(type_id: str) -> bool:
    """Return True if *type_id* is any HDV variant (including legacy 'hdv')."""
    return type_id in HDV_VTYPE_IDS


ROUTE_MAIN: dict[str, str] = {"id": "main_route", "edges": "main_h1 main_h2 main_h3 main_h4"}
ROUTE_RAMP: dict[str, str] = {"id": "ramp_route", "edges": "ramp_h5 ramp_h6 main_h3 main_h4"}

MAIN_LANES: list[int] = [0, 1, 2, 3]
RAMP_LANE: int = 1

_CRITICAL_VTYPE_ATTRS = (
    "sigma", "speedDev", "carFollowModel",
    "actionStepLength", "lcCooperative", "lcSpeedGain", "lcAssertive", "lcStrategic",
)


def write_vtypes_to_xml(root: ET.Element, *, use_profiles: bool = False) -> None:
    """Append canonical <vType> elements to an XML root.

    When *use_profiles* is True, writes all 4 HDV profiles instead of the
    legacy single ``hdv`` vType.
    """
    vtypes: list[dict[str, str]]
    if use_profiles:
        vtypes = [VTYPE_CAV, *HDV_PROFILES]
    else:
        vtypes = [VTYPE_CAV, VTYPE_HDV]
    for vtype_dict in vtypes:
        elem = ET.SubElement(root, "vType")
        for k, v in vtype_dict.items():
            elem.set(k, v)


def validate_rou_vtypes(xml_path: str | Path) -> list[str]:
    """Compare vType definitions in *xml_path* against this module's SSoT.

    Returns a list of discrepancy messages (empty == all consistent).
    Checks the legacy 'hdv' vType against VTYPE_HDV and any profile
    vTypes against their respective definitions.  Missing lc-parameters
    in legacy files are logged as warnings but not counted as errors.
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        msg = f"rou.xml not found: {xml_path}"
        logger.warning(msg)
        return [msg]

    tree = ET.parse(xml_path)
    root = tree.getroot()
    issues: list[str] = []

    ssot: dict[str, dict[str, str]] = {VEH_TYPE_CAV: VTYPE_CAV, VEH_TYPE_HDV: VTYPE_HDV}
    for profile in HDV_PROFILES:
        ssot[profile["id"]] = profile

    xml_vtypes: dict[str, dict[str, str]] = {}
    for vtype_elem in root.findall("vType"):
        vid = vtype_elem.get("id", "")
        if vid:
            xml_vtypes[vid] = dict(vtype_elem.attrib)

    legacy_attrs = ("sigma", "speedDev", "carFollowModel")

    for type_id, expected in ssot.items():
        if type_id not in xml_vtypes:
            continue
        actual = xml_vtypes[type_id]
        check_attrs = _CRITICAL_VTYPE_ATTRS if type_id in HDV_PROFILE_IDS else legacy_attrs
        for attr in check_attrs:
            exp_val = expected.get(attr)
            act_val = actual.get(attr)
            if exp_val is not None and act_val is not None and act_val != exp_val:
                msg = (
                    f"vType '{type_id}' attr '{attr}' mismatch in {xml_path.name}: "
                    f"expected={exp_val}, actual={act_val}"
                )
                issues.append(msg)
                logger.warning(msg)

    if not issues:
        logger.info("vType validation passed: %s", xml_path.name)

    return issues


def vtype_meta_dict(*, use_profiles: bool = False) -> dict[str, Any]:
    """Return vType parameters as a flat dict suitable for rou_meta.json."""
    meta: dict[str, Any] = {
        "vtype_cav_sigma": VTYPE_CAV["sigma"],
        "vtype_cav_speed_dev": VTYPE_CAV["speedDev"],
        "vtype_cav_car_follow_model": VTYPE_CAV["carFollowModel"],
    }
    if use_profiles:
        for profile in HDV_PROFILES:
            pid = profile["id"]
            meta[f"vtype_{pid}_sigma"] = profile["sigma"]
            meta[f"vtype_{pid}_speedDev"] = profile["speedDev"]
            meta[f"vtype_{pid}_actionStepLength"] = profile.get("actionStepLength", "")
            meta[f"vtype_{pid}_lcCooperative"] = profile.get("lcCooperative", "")
            meta[f"vtype_{pid}_lcSpeedGain"] = profile.get("lcSpeedGain", "")
            meta[f"vtype_{pid}_lcAssertive"] = profile.get("lcAssertive", "")
            meta[f"vtype_{pid}_lcStrategic"] = profile.get("lcStrategic", "")
    else:
        meta["vtype_hdv_sigma"] = VTYPE_HDV["sigma"]
        meta["vtype_hdv_speed_dev"] = VTYPE_HDV["speedDev"]
        meta["vtype_hdv_car_follow_model"] = VTYPE_HDV["carFollowModel"]
        meta["vtype_hdv_lc_strategic"] = VTYPE_HDV.get("lcStrategic", "")
    return meta
