# CAD to Geant4 Converter Suite

A collection of tools for converting CAD files (STEP, STL) to GDML for use in Geant4 simulations.

## Requirements

- Python 3.10 or above
- pyg4ometry >= 1.0.0
- vtk >= 9.0.0
- trimesh (for automatic mesh repair)
- pymeshlab (optional, for advanced mesh repair of stubborn cases)

Install dependencies:
```bash
pip install -r requirements.txt
pip install pymeshlab  # Optional but recommended
```

## Overview

Converting CAD to GDML/Geant4 requires care; a few export best-practices greatly improve results (trim small parts, preserve named components and hierarchy, avoid intended overlaps).

What's new (concise):
- Automatic mesh check and repair on all tessellated volumes before GDML export
- CI added (pytest + Black + Flake8) to keep quality steady

For full implementation details and reasoning, see [IMPLEMENTATION.md](IMPLEMENTATION.md).

Note: GDML output typically lacks detailed material assignments. Post-process the GDML with `gdml-editor` to add or correct materials: https://github.com/drflei/gdml-editor

## Main Application: `cad_g4_conv.py`

Unified converter supporting three workflows. All conversions automatically check and repair tessellated meshes before saving to GDML.

### Quick Start

```bash
# STEP native conversion
python cad_g4_conv.py --step-file assembly.STEP

# STL+STEP mesh conversion
python cad_g4_conv.py --step-file assembly.STEP --stl-dir STLs/

# Single STL conversion
python cad_g4_conv.py --stl-file mesh.stl
```

All conversions automatically check and repair tessellated meshes before export.

### Automatic Mesh Repair

The converter includes a comprehensive 10-phase mesh repair system that automatically fixes common issues:

1. **Basic cleanup**: Removes duplicate/unreferenced vertices
2. **Normal fixing**: Ensures consistent face orientations  
3. **Degenerate removal**: Removes zero-area faces and duplicates
4. **Broken face repair**: Detects and removes topologically broken faces
5. **Hole filling**: Iteratively attempts to close surface holes (up to 3 attempts)
6. **Inversion fix**: Corrects inverted face orientations
7. **Final cleanup**: Merges vertices after all repairs
8. **Winding correction**: Fixes inconsistent face winding
9. **Fallback strategies**: Uses convex hull or voxelization for severely broken meshes
10. **PyMeshLab fallback** (optional): For very stubborn meshes, uses MeshLab's industrial-strength repair algorithms

Most meshes are repaired automatically. The system tries progressively more aggressive techniques:
- **Phases 1-8** handle 90%+ of issues using trimesh (lightweight, fast)
- **Phase 9** applies convex hull for small holes or voxelization for complex geometry
- **Phase 10** uses PyMeshLab's powerful algorithms for the most challenging cases (requires `pip install pymeshlab`)

Example repair output:
```
stl_solid_8: watertight_before=False watertight_after=True 
  notes=removed_92_broken_faces;subdivided;used_convex_hull(vol_diff=0.04);
```

**Optional: PyMeshLab for stubborn meshes**
```bash
pip install pymeshlab  # Optional but recommended for complex meshes
```
If installed, PyMeshLab provides a final fallback using MeshLab's industrial-strength repair algorithms.

For full usage and examples see `cad_g4_conv_QUICKREF.md` and `cad_g4_conv_README.md`.
## Files in This Directory

### Main Tools
- **cad_g4_conv.py** - Unified CAD to GDML converter (recommended)
- **step_g4_app.py** - Original STEP-only converter (legacy)
- **stl_g4_app.py** - Original STL+STEP converter (legacy)

### Documentation
- **cad_g4_conv_README.md** - Complete user guide
- **cad_g4_conv_QUICKREF.md** - Quick reference and cheatsheet
- **SINGLE_STL_QUICKSTART.md** - Quick start for single STL workflow
- **MERGER_SUMMARY.md** - Technical details of the unified app
- **SINGLE_STL_FEATURE.md** - Single STL feature documentation

### Scripts
- **demo_all_workflows.sh** - Demonstrates all three workflows
- **test_cad_g4_conv.sh** - Automated testing script

## Installation

The tools require pyg4ometry and VTK:

```bash
pip install pyg4ometry vtk
```

## Usage

See [cad_g4_conv_README.md](cad_g4_conv_README.md) for complete documentation.

### Three Workflows

| Workflow | Command | Best For |
|----------|---------|----------|
| STEP Native | `--step-file X.STEP` | Assemblies with hierarchy |
| STL+STEP | `--step-file X.STEP --stl-dir STLs/` | High-quality meshes |
| Single STL | `--stl-file mesh.stl` | Single meshes, prototyping |

## Examples

```bash
# 1. STEP native with hierarchy
python cad_g4_conv.py --step-file detector.STEP -o detector.gdml

# 2. STL+STEP with auto-sized world
python cad_g4_conv.py \
    --step-file assembly.STEP \
    --stl-dir parts/ \
    -o assembly.gdml

# 3. Single STL (simplest)
python cad_g4_conv.py --stl-file housing.stl -o housing.gdml

# 4. With overlap checking
python cad_g4_conv.py --step-file detector.STEP --check-overlaps

# 5. Flat mode (robust fallback)
python cad_g4_conv.py --step-file complex.STEP --flat

# 6. Center geometry at world origin
python cad_g4_conv.py --step-file detector.STEP --center-origin

# 7. Logging example
# Write detailed logs to 'convert.log'
python cad_g4_conv.py --stl-file mesh.stl --log-file convert.log --log-level DEBUG

# Notes:
# - All tessellated meshes are automatically checked and repaired before export
# - Repairs use trimesh (fix_normals, merge_vertices, remove degenerates, fill_holes, fix_inversion)
# - `--log-file` / `--log-level` control logging output for debugging and reproducibility
```

## Running from Other Directories

You can run the tools from anywhere by specifying the full path:

```bash
# From any directory
python ~/cad_g4_conv/cad_g4_conv.py --stl-file /path/to/mesh.stl
```

Or add to PATH:

```bash
# Add to ~/.bashrc
export PATH="$HOME/cad_g4_conv:$PATH"

# Then use directly
cad_g4_conv.py --stl-file mesh.stl
```

## Demo

Run the comprehensive demo to see all workflows in action:

```bash
cd ~/cad_g4_conv
./demo_all_workflows.sh
```

## Testing

Run automated tests:

```bash
cd ~/cad_g4_conv
./test_cad_g4_conv.sh
```

## Visualization

After conversion, visualize the GDML with the viewer from the CLAIRE directory:

```bash
python ~/CLAIRE/run_vtkviewer.py output.gdml
```

## Help

```bash
python cad_g4_conv.py --help
```

## Features (short)

- Supports STEP-native conversion (hierarchy + CSG where possible), STL+STEP mesh-based conversion, and single-STL conversions.
- Automatic 10-phase mesh check and repair on all tessellated volumes before GDML export (trimesh + optional pymeshlab).
- Auto-sized and centered world volume, fuzzy name matching for STL→STEP associations, and overlap diagnostics.

## Documentation

For detailed usage, see the [docs/](docs/) folder:
- [docs/QUICKREF.md](docs/QUICKREF.md) - Quick reference
- [docs/DETAILED_USAGE.md](docs/DETAILED_USAGE.md) - Complete guide
- [docs/SINGLE_STL_QUICKSTART.md](docs/SINGLE_STL_QUICKSTART.md) - Single STL guide
- [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) - Technical implementation details
- [docs/TESTING.md](docs/TESTING.md) - Test suite documentation

## License

GNU V3.0
