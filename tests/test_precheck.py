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
def test_convert_single_stl_precheck_and_repair(tmp_path):
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

    # This should attempt repair and still produce a GDML file
    reg = convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True, precheck=True, repair=True)

    assert out_gdml.exists(), "GDML output missing"
    # Registry should be returned
    assert reg is not None


def test_step_precheck_dryrun_ok(tmp_path):
    # Use a small STEP file from the CLAIRE data (HEPI-SiO2) to test STEP dry-run tessellation
    step_file = Path(__file__).resolve().parents[1] / "../CLAIRE/CAD_files/HEPI-SiO2/HEPI-SiO2.STEP"
    step_file = Path(os.path.normpath(str(step_file)))
    if not step_file.exists():
        pytest.skip("STEP test file not available")

    out_gdml = tmp_path / "step_out.gdml"
    reg = convert_step_to_gdml(step_file, out_gdml, use_hierarchy=True, check_overlaps=False, center_origin=True, precheck=True, repair=False)
    assert out_gdml.exists(), "STEP GDML output missing"
    assert reg is not None


def test_postcheck_and_repair_on_converted_single_stl(tmp_path):
    # Create a broken cube and convert without precheck, then run postcheck/postrepair
    cube = trimesh.creation.box(extents=(10,10,10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]
    stl_file = tmp_path / "broken_cube2.stl"
    cube.export(str(stl_file))
    out_gdml = tmp_path / "out_post.gdml"

    reg = convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True, precheck=False, repair=False, postcheck=True, postrepair=True)
    # Find a tessellated solid and check that there is a replaced fixed version
    found_repaired = False
    for sname, solid in reg.solidDict.items():
        if sname.endswith('-fixed') or sname.endswith('_fixed'):
            # Inspect mesh
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