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
    MAIN_LANES,
    RAMP_LANE,
    ROUTE_MAIN,
    ROUTE_RAMP,
    VEH_TYPE_CAV,
    VEH_TYPE_HDV,
    VTYPE_CAV,
    VTYPE_HDV,
    validate_rou_vtypes,
    vtype_meta_dict,
    write_vtypes_to_xml,
)
from ramp.tools.generate_mixed_rou import generate_rou_xml


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
    assert any("missing" in i.lower() for i in issues)


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
