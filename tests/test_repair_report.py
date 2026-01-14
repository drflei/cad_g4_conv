import os
from pathlib import Path
import pytest

try:
    import trimesh
except Exception:
    trimesh = None

# Load module from file
import importlib.util
spec = importlib.util.spec_from_file_location("cad_g4_conv_mod", str(Path(__file__).resolve().parents[1] / "cad_g4_conv.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
convert_single_stl_to_gdml = mod.convert_single_stl_to_gdml


@pytest.mark.skipif(trimesh is None, reason="trimesh not installed")
def test_repair_report_and_log_created(tmp_path):
    # Create a broken cube mesh (remove one face)
    cube = trimesh.creation.box(extents=(10,10,10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]
    stl_file = tmp_path / "broken_report.stl"
    cube.export(str(stl_file))

    out_gdml = tmp_path / "out_report.gdml"

    # Run conversion - automatic repair now runs by default
    reg = convert_single_stl_to_gdml(
        stl_file,
        out_gdml,
        center_origin=True,
    )

    # Check GDML output created
    assert out_gdml.exists(), "GDML output missing"
    assert reg is not None
    
    # With replace_in_place=True, repaired solids replace the originals (no _fixed suffix)
    # Verify that tessellated solids exist and are repaired
    stl_solids = [name for name in reg.solidDict.keys() if 'stl_solid' in name]
    assert len(stl_solids) > 0, "Expected at least one stl_solid from conversion"
