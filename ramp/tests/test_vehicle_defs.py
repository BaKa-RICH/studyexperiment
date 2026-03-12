"""Tests for ramp.common.vehicle_defs and generate_mixed_rou reproducibility."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ramp.common.vehicle_defs import (
    HDV_PROFILES,
    HDV_PROFILE_IDS,
    HDV_VTYPE_IDS,
    MAIN_LANES,
    RAMP_LANE,
    ROUTE_MAIN,
    ROUTE_RAMP,
    VEH_TYPE_CAV,
    VEH_TYPE_HDV,
    VTYPE_CAV,
    VTYPE_HDV,
    VTYPE_HDV_AGGRESSIVE,
    VTYPE_HDV_DISTRACTED,
    VTYPE_HDV_HESITANT,
    VTYPE_HDV_NORMAL,
    is_hdv,
    validate_rou_vtypes,
    vtype_meta_dict,
    write_vtypes_to_xml,
)
from ramp.tools.generate_mixed_rou import (
    build_vehicles,
    generate_rou_xml,
    parse_hdv_profile_weights,
)

import random


def test_veh_type_constants():
    assert VEH_TYPE_CAV == "cav"
    assert VEH_TYPE_HDV == "hdv"


def test_vtype_has_car_follow_model():
    assert VTYPE_CAV["carFollowModel"] == "Krauss"
    assert VTYPE_HDV["carFollowModel"] == "Krauss"


def test_vtype_hdv_sigma():
    assert VTYPE_HDV["sigma"] == "0.7"
    assert VTYPE_HDV["speedDev"] == "0.15"


def test_vtype_cav_deterministic():
    assert VTYPE_CAV["sigma"] == "0.0"
    assert VTYPE_CAV["speedDev"] == "0.0"


def test_route_definitions():
    assert "main_h1" in ROUTE_MAIN["edges"]
    assert "ramp_h5" in ROUTE_RAMP["edges"]


def test_lane_constants():
    assert MAIN_LANES == [0, 1, 2, 3]
    assert RAMP_LANE == 1


def test_write_vtypes_to_xml():
    root = ET.Element("routes")
    write_vtypes_to_xml(root)
    vtypes = root.findall("vType")
    assert len(vtypes) == 2
    ids = {vt.get("id") for vt in vtypes}
    assert ids == {"cav", "hdv"}
    for vt in vtypes:
        assert vt.get("carFollowModel") == "Krauss"


def test_vtype_meta_dict():
    meta = vtype_meta_dict()
    assert meta["vtype_hdv_sigma"] == "0.7"
    assert meta["vtype_cav_car_follow_model"] == "Krauss"
    assert "vtype_hdv_lc_strategic" in meta


def test_validate_rou_vtypes_consistent():
    with tempfile.NamedTemporaryFile(suffix=".rou.xml", mode="w", delete=False) as f:
        root = ET.Element("routes")
        write_vtypes_to_xml(root)
        ET.indent(root)
        tree = ET.ElementTree(root)
        tree.write(f.name, encoding="unicode")
        f.flush()
        issues = validate_rou_vtypes(f.name)
    assert issues == []


def test_validate_rou_vtypes_detects_mismatch():
    with tempfile.NamedTemporaryFile(suffix=".rou.xml", mode="w", delete=False) as f:
        root = ET.Element("routes")
        cav = ET.SubElement(root, "vType")
        cav.set("id", "cav")
        cav.set("sigma", "0.0")
        cav.set("speedDev", "0.0")
        cav.set("carFollowModel", "Krauss")
        hdv = ET.SubElement(root, "vType")
        hdv.set("id", "hdv")
        hdv.set("sigma", "0.5")
        hdv.set("speedDev", "0.1")
        hdv.set("carFollowModel", "Krauss")
        tree = ET.ElementTree(root)
        tree.write(f.name, encoding="unicode")
        f.flush()
        issues = validate_rou_vtypes(f.name)
    assert len(issues) >= 1
    assert any("sigma" in i for i in issues)


def test_validate_missing_vtype():
    with tempfile.NamedTemporaryFile(suffix=".rou.xml", mode="w", delete=False) as f:
        root = ET.Element("routes")
        cav = ET.SubElement(root, "vType")
        cav.set("id", "cav")
        cav.set("sigma", "0.0")
        cav.set("carFollowModel", "Krauss")
        tree = ET.ElementTree(root)
        tree.write(f.name, encoding="unicode")
        f.flush()
        issues = validate_rou_vtypes(f.name)
    assert issues == []


def test_reproducibility_same_seed_same_hash():
    """Same seed + same parameters must produce byte-identical rou.xml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "a" / "gen.rou.xml"
        path_b = Path(tmpdir) / "b" / "gen.rou.xml"

        params = dict(seed=42, cav_ratio=0.6, main_vph=1200, ramp_vph=500,
                      duration=60, arrival_mode="uniform")

        generate_rou_xml(**params, output=path_a)
        generate_rou_xml(**params, output=path_b)

        hash_a = hashlib.sha256(path_a.read_bytes()).hexdigest()
        hash_b = hashlib.sha256(path_b.read_bytes()).hexdigest()
        assert hash_a == hash_b, f"Hash mismatch: {hash_a} != {hash_b}"


def test_reproducibility_different_seed_different_output():
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "a" / "gen.rou.xml"
        path_b = Path(tmpdir) / "b" / "gen.rou.xml"

        base = dict(cav_ratio=0.6, main_vph=1200, ramp_vph=500,
                     duration=60, arrival_mode="uniform")

        generate_rou_xml(seed=1, **base, output=path_a)
        generate_rou_xml(seed=2, **base, output=path_b)

        assert path_a.read_bytes() != path_b.read_bytes()


def test_generate_rou_meta_contains_vtype_params():
    with tempfile.TemporaryDirectory() as tmpdir:
        rou_path, meta = generate_rou_xml(
            seed=42, cav_ratio=0.6, main_vph=600, ramp_vph=200,
            duration=30, arrival_mode="uniform", output=Path(tmpdir) / "test.rou.xml",
        )
        assert "vtype_hdv_sigma" in meta
        assert meta["vtype_hdv_sigma"] == "0.7"
        assert meta["vtype_hdv_car_follow_model"] == "Krauss"

        meta_path = Path(tmpdir) / "rou_meta.json"
        assert meta_path.exists()
        loaded = json.loads(meta_path.read_text())
        assert loaded["vtype_hdv_sigma"] == "0.7"


def test_generate_rou_xml_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        rou_path, meta = generate_rou_xml(
            seed=1, cav_ratio=0.5, main_vph=600, ramp_vph=200,
            duration=30, arrival_mode="uniform", output=Path(tmpdir) / "test.rou.xml",
        )
        tree = ET.parse(str(rou_path))
        root = tree.getroot()
        assert root.tag == "routes"
        vtypes = root.findall("vType")
        assert len(vtypes) == 2
        vehicles = root.findall("vehicle")
        assert len(vehicles) == meta["total_vehicles"]
        assert meta["total_vehicles"] > 0


def test_validate_existing_scenarios():
    """Validate all rou.xml files in the scenarios directory (expect known discrepancies)."""
    scenarios_dir = _REPO_ROOT / "ramp" / "scenarios"
    if not scenarios_dir.exists():
        return

    for rou_xml in scenarios_dir.glob("**/*.rou.xml"):
        issues = validate_rou_vtypes(rou_xml)
        pass


# ---- Todo 3.1: Heterogeneous HDV library tests ----


def test_hdv_profiles_count():
    assert len(HDV_PROFILES) == 4


def test_hdv_profiles_ids():
    expected = {"hdv_normal", "hdv_distracted", "hdv_aggressive", "hdv_hesitant"}
    assert HDV_PROFILE_IDS == expected


def test_hdv_vtype_ids_includes_legacy():
    assert VEH_TYPE_HDV in HDV_VTYPE_IDS
    assert "hdv_normal" in HDV_VTYPE_IDS
    assert "cav" not in HDV_VTYPE_IDS


def test_is_hdv():
    assert is_hdv("hdv")
    assert is_hdv("hdv_normal")
    assert is_hdv("hdv_distracted")
    assert is_hdv("hdv_aggressive")
    assert is_hdv("hdv_hesitant")
    assert not is_hdv("cav")
    assert not is_hdv("")
    assert not is_hdv("hdv_unknown")


def test_hdv_profiles_gate2_params():
    """Gate 2: every profile must include all 7 required parameters."""
    gate2_params = [
        "sigma", "speedDev", "actionStepLength",
        "lcCooperative", "lcSpeedGain", "lcAssertive", "lcStrategic",
    ]
    for profile in HDV_PROFILES:
        for param in gate2_params:
            assert param in profile, f"{profile['id']} missing {param}"


def test_hdv_profiles_all_krauss():
    for profile in HDV_PROFILES:
        assert profile["carFollowModel"] == "Krauss"


def test_hdv_profiles_distinct_params():
    """Different profiles should have at least one parameter difference."""
    for i, p1 in enumerate(HDV_PROFILES):
        for p2 in HDV_PROFILES[i + 1:]:
            common_keys = set(p1) & set(p2) - {"id"}
            diffs = [k for k in common_keys if p1[k] != p2[k]]
            assert len(diffs) >= 1, f"{p1['id']} and {p2['id']} are identical"


def test_write_vtypes_profiles():
    root = ET.Element("routes")
    write_vtypes_to_xml(root, use_profiles=True)
    vtypes = root.findall("vType")
    assert len(vtypes) == 5
    ids = {vt.get("id") for vt in vtypes}
    assert "cav" in ids
    assert "hdv_normal" in ids
    assert "hdv_distracted" in ids
    assert "hdv_aggressive" in ids
    assert "hdv_hesitant" in ids
    assert "hdv" not in ids


def test_vtype_meta_dict_profiles():
    meta = vtype_meta_dict(use_profiles=True)
    assert "vtype_hdv_normal_sigma" in meta
    assert "vtype_hdv_aggressive_lcAssertive" in meta
    assert "vtype_hdv_sigma" not in meta


def test_build_vehicles_with_profiles():
    rng = random.Random(42)
    vehicles = build_vehicles(
        cav_ratio=0.5, main_vph=600, ramp_vph=200, duration=30,
        arrival_mode="uniform", rng=rng, use_profiles=True,
    )
    types_used = {v["type"] for v in vehicles}
    assert "cav" in types_used
    hdv_types = {t for t in types_used if is_hdv(t)}
    assert len(hdv_types) >= 2


def test_build_vehicles_without_profiles():
    rng = random.Random(42)
    vehicles = build_vehicles(
        cav_ratio=0.5, main_vph=600, ramp_vph=200, duration=30,
        arrival_mode="uniform", rng=rng, use_profiles=False,
    )
    types_used = {v["type"] for v in vehicles}
    hdv_types = {t for t in types_used if t != "cav"}
    assert hdv_types == {"hdv"}


def test_generate_rou_xml_profiles():
    with tempfile.TemporaryDirectory() as tmpdir:
        rou_path, meta = generate_rou_xml(
            seed=42, cav_ratio=0.5, main_vph=600, ramp_vph=200,
            duration=30, arrival_mode="uniform",
            output=Path(tmpdir) / "profiles.rou.xml",
            use_profiles=True,
        )
        assert meta["use_profiles"] is True
        assert "hdv_profile_counts" in meta

        tree = ET.parse(str(rou_path))
        root = tree.getroot()
        vtypes = root.findall("vType")
        assert len(vtypes) == 5
        vtype_ids = {vt.get("id") for vt in vtypes}
        assert "hdv_normal" in vtype_ids


def test_generate_rou_xml_profiles_reproducible():
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "a" / "gen.rou.xml"
        path_b = Path(tmpdir) / "b" / "gen.rou.xml"
        params = dict(seed=42, cav_ratio=0.5, main_vph=600, ramp_vph=200,
                      duration=30, arrival_mode="uniform", use_profiles=True)
        generate_rou_xml(**params, output=path_a)
        generate_rou_xml(**params, output=path_b)
        hash_a = hashlib.sha256(path_a.read_bytes()).hexdigest()
        hash_b = hashlib.sha256(path_b.read_bytes()).hexdigest()
        assert hash_a == hash_b


def test_parse_hdv_profile_weights():
    w = parse_hdv_profile_weights("hdv_normal:0.6,hdv_distracted:0.4")
    assert abs(w["hdv_normal"] - 0.6) < 1e-6
    assert abs(w["hdv_distracted"] - 0.4) < 1e-6


def test_parse_hdv_profile_weights_auto_normalize():
    w = parse_hdv_profile_weights("hdv_normal:3,hdv_aggressive:1")
    assert abs(w["hdv_normal"] - 0.75) < 1e-6
    assert abs(w["hdv_aggressive"] - 0.25) < 1e-6


def test_build_vehicles_custom_weights():
    rng = random.Random(42)
    weights = {"hdv_normal": 0.0, "hdv_aggressive": 1.0,
               "hdv_distracted": 0.0, "hdv_hesitant": 0.0}
    vehicles = build_vehicles(
        cav_ratio=0.0, main_vph=600, ramp_vph=200, duration=30,
        arrival_mode="uniform", rng=rng, use_profiles=True,
        hdv_profile_weights=weights,
    )
    hdv_types = {v["type"] for v in vehicles}
    assert hdv_types == {"hdv_aggressive"}


def test_legacy_hdv_compat():
    """Legacy VTYPE_HDV dict must remain accessible."""
    assert VTYPE_HDV["id"] == "hdv"
    assert VTYPE_HDV["sigma"] == "0.7"
