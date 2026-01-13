# CAD to Geant4 Converter Suite

A collection of tools for converting CAD files (STEP, STL) to GDML for use in Geant4 simulations.

## Requirements

- Python 3.10 or above
- pyg4ometry >= 1.0.0
- vtk >= 9.0.0

Install dependencies:
```bash
pip install -r requirements.txt
```

## Overview

Converting CAD to GDML/Geant4 requires care; a few export best-practices greatly improve results (trim small parts, preserve named components and hierarchy, avoid intended overlaps).

What's new (concise):
- Added pre-conversion checks and repairs for source meshes (`--precheck`, `--repair`).
- Added post-conversion tessellated-solid checks and repairs (`--postcheck`, `--postrepair`) so the same repair actions can be applied after STEP tessellation or STL import.
- CI added (pytest + Black + Flake8) to keep quality steady.

For full implementation details and reasoning, see [IMPLEMENTATION.md](IMPLEMENTATION.md).

Note: GDML output typically lacks detailed material assignments. Post-process the GDML with `gdml-editor` to add or correct materials: https://github.com/drflei/gdml-editor

## Main Application: `cad_g4_conv.py`

Unified converter supporting three workflows. Recent additions include pre- and post-conversion mesh checks/repairs.

### Quick Start

```bash
# STEP native conversion
python cad_g4_conv.py --step-file assembly.STEP

# STL+STEP mesh conversion
python cad_g4_conv.py --step-file assembly.STEP --stl-dir STLs/

# Single STL conversion
python cad_g4_conv.py --stl-file mesh.stl
```

### Useful validation flags

- `--precheck`  : run pre-conversion checks on source meshes (STL or STEP dry-run tessellation)
- `--repair`    : when used with `--precheck`, attempt automatic repairs on STLs
- `--postcheck` : check tessellated solids created by conversion (after STEP tessellation or STL import)
- `--postrepair`: when used with `--postcheck`, attempt automatic repairs on tessellated solids

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
- Pre/post conversion checks & best-effort automated repairs for STL and tessellated solids.
- Auto-sized and centered world volume, fuzzy name matching for STL→STEP associations, and overlap diagnostics.

For full technical details, see `cad_g4_conv_README.md` and `IMPLEMENTATION.md`.

## Support

For detailed usage, see:
- [cad_g4_conv_README.md](cad_g4_conv_README.md) - Complete guide
- [cad_g4_conv_QUICKREF.md](cad_g4_conv_QUICKREF.md) - Quick reference
- [SINGLE_STL_QUICKSTART.md](SINGLE_STL_QUICKSTART.md) - Single STL guide

## License

GNU V3.0
