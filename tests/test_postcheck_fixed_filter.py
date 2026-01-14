"""Test that _fixed solids are excluded from postcheck/postrepair processing."""
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
def test_fixed_solids_excluded_from_postcheck(tmp_path):
    """Test that solids ending with _fixed are not re-processed during postcheck/postrepair."""
    
    # Create a broken cube
    cube = trimesh.creation.box(extents=(10, 10, 10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]  # Make it non-watertight
    
    # Save to STL
    stl_file = tmp_path / "broken.stl"
    cube.export(str(stl_file))
    
    # Convert to GDML without postcheck first
    out_gdml = tmp_path / "test.gdml"
    reg = cad_mod.convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True, 
                                              precheck=False, repair=False, 
                                              postcheck=False, postrepair=False)
    
    # Now manually call postcheck with repair (replace_in_place=False to create _fixed solids)
    reports1 = cad_mod._check_and_repair_tessellated_solids(reg, repair=True, replace_in_place=False)
    
    # Should have processed 1 solid and created a _fixed version
    assert len(reports1) == 1, f"Expected 1 report, got {len(reports1)}"
    original_solid_name = reports1[0]['solid_name']
    fixed_solid_name = reports1[0]['replaced_name']
    
    assert fixed_solid_name is not None, "Should have created a fixed solid"
    assert fixed_solid_name.endswith('_fixed'), f"Fixed solid name should end with _fixed: {fixed_solid_name}"
    
    # Verify the _fixed solid exists in registry
    assert fixed_solid_name in reg.solidDict, f"Fixed solid {fixed_solid_name} should be in registry"
    
    # Now call postcheck again - it should NOT process the _fixed solid
    reports2 = cad_mod._check_and_repair_tessellated_solids(reg, repair=True, replace_in_place=False)
    
    # Should only process the original solid again (or none if it's been replaced)
    # but definitely should NOT create another _fixed_fixed or process the _fixed solid
    for report in reports2:
        assert not report['solid_name'].endswith('_fixed'), \
            f"Should not process _fixed solids: {report['solid_name']}"
        if report['replaced_name']:
            assert not report['replaced_name'].endswith('_fixed_fixed'), \
                f"Should not create double-fixed names: {report['replaced_name']}"
    
    # Count how many _fixed solids are in registry
    fixed_count = sum(1 for name in reg.solidDict.keys() if name.endswith('_fixed'))
    
    # Should only have one _fixed solid (or possibly more if original was processed again)
    # But importantly, should NOT have _fixed_fixed
    for name in reg.solidDict.keys():
        assert not name.endswith('_fixed_fixed'), f"Should not have double-fixed solid: {name}"
