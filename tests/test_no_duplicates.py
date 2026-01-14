"""Test that replace_in_place correctly removes _fixed duplicates from registry."""
import tempfile
from pathlib import Path
import pytest

try:
    import trimesh
except Exception:
    trimesh = None

try:
    import pyg4ometry
except Exception:
    pyg4ometry = None

# Load the cad_g4_conv module
import importlib.util
spec = importlib.util.spec_from_file_location("cad_g4_conv_mod", str(Path(__file__).resolve().parents[1] / "cad_g4_conv.py"))
cad_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad_mod)


@pytest.mark.skipif(trimesh is None or pyg4ometry is None, reason="trimesh or pyg4ometry not installed")
def test_no_fixed_duplicates_in_registry(tmp_path):
    """Test that with replace_in_place=True, no _fixed duplicates exist in the registry."""
    
    # Create a broken cube
    cube = trimesh.creation.box(extents=(10, 10, 10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]  # Make it non-watertight
    
    # Save to STL
    stl_file = tmp_path / "broken.stl"
    cube.export(str(stl_file))
    
    # Convert to GDML - automatic check and repair will run
    out_gdml = tmp_path / "test.gdml"
    reg = cad_mod.convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True)
    
    # After automatic repair with replace_in_place=True, _fixed solids should NOT exist
    # (they are cleaned up and replaced with the original name)
    fixed_count = sum(1 for name in reg.solidDict.keys() if name.endswith('_fixed'))
    double_fixed_count = sum(1 for name in reg.solidDict.keys() if name.endswith('_fixed_fixed'))

    # With replace_in_place=True, no _fixed solids should exist
    assert fixed_count == 0, f"Expected 0 _fixed solids with replace_in_place=True, got {fixed_count}"
    # Should NOT have any double-fixed solids
    assert double_fixed_count == 0, f"Should not have _fixed_fixed solids, got {double_fixed_count}"
