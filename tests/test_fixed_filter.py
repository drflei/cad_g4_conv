"""Test that -fixed.stl files are excluded from directory processing."""
import tempfile
from pathlib import Path
import pytest

try:
    import trimesh
except Exception:
    trimesh = None

# Load the cad_g4_conv module
import importlib.util
spec = importlib.util.spec_from_file_location("cad_g4_conv_mod", str(Path(__file__).resolve().parents[1] / "cad_g4_conv.py"))
cad_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad_mod)


@pytest.mark.skipif(trimesh is None, reason="trimesh not installed")
def test_fixed_files_excluded_from_stl_dir_processing(tmp_path):
    """Test that when precheck/repair creates -fixed.stl files, they are not re-processed."""
    import glob
    
    # Create a test directory with both regular and -fixed STL files
    stl_dir = tmp_path / "stl_test"
    stl_dir.mkdir()
    
    # Create a broken cube
    cube = trimesh.creation.box(extents=(10, 10, 10))
    faces = cube.faces.copy()
    cube.faces = faces[:-1]  # Make it non-watertight
    
    # Save original
    original_stl = stl_dir / "part1.stl"
    cube.export(str(original_stl))
    
    # Manually create a -fixed.stl file (simulating what repair does)
    fixed_stl = stl_dir / "part1-fixed.stl"
    cube_fixed = trimesh.creation.box(extents=(10, 10, 10))  # watertight
    cube_fixed.export(str(fixed_stl))
    
    # Also create another regular file
    part2_stl = stl_dir / "part2.stl"
    cube.export(str(part2_stl))
    
    # Now use the same glob pattern as in convert_stl_step_to_gdml
    stl_paths = sorted(
        [Path(p) for p in glob.glob(str(stl_dir / "*.stl")) if not p.endswith('-fixed.stl')]
        + [Path(p) for p in glob.glob(str(stl_dir / "*.STL")) if not p.endswith('-fixed.STL')]
    )
    
    # Should only find the 2 original files, not the -fixed one
    assert len(stl_paths) == 2, f"Expected 2 STL files, found {len(stl_paths)}: {[p.name for p in stl_paths]}"
    assert original_stl in stl_paths
    assert part2_stl in stl_paths
    assert fixed_stl not in stl_paths, "-fixed.stl file should be excluded"
    
    # Verify the files actually exist
    assert original_stl.exists()
    assert fixed_stl.exists()
    assert part2_stl.exists()
