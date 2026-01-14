import os
import tempfile
from pathlib import Path

import pytest

import importlib.util
spec = importlib.util.spec_from_file_location("cad_g4_conv_mod", str(Path(__file__).resolve().parents[1] / "cad_g4_conv.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

convert_single_stl_to_gdml = mod.convert_single_stl_to_gdml

try:
    import trimesh
except Exception:
    trimesh = None


@pytest.mark.skipif(trimesh is None, reason="trimesh not installed")
def test_logging_file_created_and_contains_postcheck(tmp_path):
    # Create a broken cube - automatic repair will run
    cube = trimesh.creation.box(extents=(10, 10, 10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]
    stl_file = tmp_path / "broken_cube_log.stl"
    cube.export(str(stl_file))

    out_gdml = tmp_path / "out_log.gdml"
    log_file = tmp_path / "cad_g4_conv_test.log"

    # Configure logger via CLI-like call
    mod.configure_logging(str(log_file), level="DEBUG")

    # Run conversion - automatic check and repair runs by default
    reg = convert_single_stl_to_gdml(stl_file, out_gdml, center_origin=True)

    assert Path(log_file).exists(), "Log file not created"
    txt = Path(log_file).read_text()
    # Check for automatic repair messages
    assert "CHECKING AND REPAIRING TESSELLATED SOLIDS" in txt or "_fixed" in txt or "tessellated" in txt.lower()
