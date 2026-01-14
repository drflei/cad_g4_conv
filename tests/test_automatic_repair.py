"""Test automatic mesh repair during conversion."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

try:
    import trimesh
except Exception:
    trimesh = None

# Load the cad_g4_conv module from file (so tests run without installing the package)
import importlib.util
spec = importlib.util.spec_from_file_location("cad_g4_conv_mod", str(Path(__file__).resolve().parents[1] / "cad_g4_conv.py"))
cad_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad_mod)
convert_single_stl_to_gdml = cad_mod.convert_single_stl_to_gdml
convert_step_to_gdml = cad_mod.convert_step_to_gdml


@pytest.mark.skipif(trimesh is None, reason="trimesh not installed")
def test_single_stl_automatic_repair(tmp_path):
    """Test that broken STL meshes are automatically repaired during conversion."""
    # Create a simple cube mesh and then remove a face to make it non-watertight
    cube = trimesh.creation.box(extents=(10, 10, 10))
    # Remove one face to break watertightness
    faces = cube.faces.copy()
    if faces.shape[0] < 1:
        pytest.skip("Cube has no faces")
    cube.faces = faces[:-1]

    stl_file = tmp_path / "broken_cube.stl"
    cube.export(str(stl_file))

    out_gdml = tmp_path / "out.gdml"

    # Conversion now automatically checks and repairs tessellated volumes
    reg = convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True)

    assert out_gdml.exists(), "GDML output missing"
    # Registry should be returned
    assert reg is not None


def test_step_conversion_with_automatic_repair(tmp_path):
    """Test STEP file conversion with automatic tessellated solid repair."""
    # Use a small STEP file from the CLAIRE data (HEPI-SiO2) to test basic conversion with automatic repair
    step_file = Path(__file__).resolve().parents[1] / "../CLAIRE/CAD_files/HEPI-SiO2/HEPI-SiO2.STEP"
    step_file = Path(os.path.normpath(str(step_file)))
    if not step_file.exists():
        pytest.skip("STEP test file not available")

    out_gdml = tmp_path / "step_out.gdml"
    reg = convert_step_to_gdml(step_file, out_gdml, use_hierarchy=True, check_overlaps=False, center_origin=True)
    assert out_gdml.exists(), "STEP GDML output missing"
    assert reg is not None


def test_watertight_mesh_after_automatic_repair(tmp_path):
    """Test that automatically repaired meshes are watertight."""
    # Create a broken cube - conversion now automatically checks and repairs
    cube = trimesh.creation.box(extents=(10,10,10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]
    stl_file = tmp_path / "broken_cube2.stl"
    cube.export(str(stl_file))
    out_gdml = tmp_path / "out_post.gdml"

    # Automatic repair now runs by default with replace_in_place=True
    reg = convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True)
    # With replace_in_place=True, the original solid is replaced (no _fixed suffix)
    # Check that tessellated solids are watertight after repair
    found_repaired = False
    for sname, solid in reg.solidDict.items():
        if 'stl_solid' in sname:
            # Inspect mesh to verify it's watertight
            try:
                m = solid.mesh()
                vp = m.toVerticesAndPolygons()
                import numpy as np
                vertices = np.array(vp[0])
                faces = np.array(vp[1])
                import trimesh as _tm
                tm = _tm.Trimesh(vertices=vertices, faces=faces, process=False)
                if tm.is_watertight:
                    found_repaired = True
            except Exception:
                pass
    assert found_repaired, 'No repaired tessellated solid found (watertight) in registry'