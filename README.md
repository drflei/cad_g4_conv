# CAD to Geant4 Converter Suite

A collection of tools for converting CAD files (STEP, STL) to GDML format for Geant4 simulations.

## Main Application: cad_g4_app.py

Unified converter supporting three workflows:

### Quick Start

```bash
# STEP native conversion
python cad_g4_app.py --step-file assembly.STEP

# STL+STEP mesh conversion
python cad_g4_app.py --step-file assembly.STEP --stl-dir STLs/

# Single STL conversion
python cad_g4_app.py --stl-file mesh.stl
```

## Files in This Directory

### Main Tools
- **cad_g4_app.py** - Unified CAD to GDML converter (recommended)
- **step_g4_app.py** - Original STEP-only converter (legacy)
- **stl_g4_app.py** - Original STL+STEP converter (legacy)

### Documentation
- **cad_g4_app_README.md** - Complete user guide
- **cad_g4_app_QUICKREF.md** - Quick reference and cheatsheet
- **SINGLE_STL_QUICKSTART.md** - Quick start for single STL workflow
- **MERGER_SUMMARY.md** - Technical details of the unified app
- **SINGLE_STL_FEATURE.md** - Single STL feature documentation

### Scripts
- **demo_all_workflows.sh** - Demonstrates all three workflows
- **test_cad_g4_app.sh** - Automated testing script

## Installation

The tools require pyg4ometry and VTK:

```bash
pip install pyg4ometry vtk
```

## Usage

See [cad_g4_app_README.md](cad_g4_app_README.md) for complete documentation.

### Three Workflows

| Workflow | Command | Best For |
|----------|---------|----------|
| STEP Native | `--step-file X.STEP` | Assemblies with hierarchy |
| STL+STEP | `--step-file X.STEP --stl-dir STLs/` | High-quality meshes |
| Single STL | `--stl-file mesh.stl` | Single meshes, prototyping |

## Examples

```bash
# 1. STEP native with hierarchy
python cad_g4_app.py --step-file detector.STEP -o detector.gdml

# 2. STL+STEP with auto-sized world
python cad_g4_app.py \
    --step-file assembly.STEP \
    --stl-dir parts/ \
    -o assembly.gdml

# 3. Single STL (simplest)
python cad_g4_app.py --stl-file housing.stl -o housing.gdml

# 4. With overlap checking
python cad_g4_app.py --step-file detector.STEP --check-overlaps

# 5. Flat mode (robust fallback)
python cad_g4_app.py --step-file complex.STEP --flat

# 6. Center geometry at world origin
python cad_g4_app.py --step-file detector.STEP --center-origin
```

## Running from Other Directories

You can run the tools from anywhere by specifying the full path:

```bash
# From any directory
python ~/cad_g4_app/cad_g4_app.py --stl-file /path/to/mesh.stl
```

Or add to PATH:

```bash
# Add to ~/.bashrc
export PATH="$HOME/cad_g4_app:$PATH"

# Then use directly
cad_g4_app.py --stl-file mesh.stl
```

## Demo

Run the comprehensive demo to see all workflows in action:

```bash
cd ~/cad_g4_app
./demo_all_workflows.sh
```

## Testing

Run automated tests:

```bash
cd ~/cad_g4_app
./test_cad_g4_app.sh
```

## Visualization

After conversion, visualize the GDML with the viewer from the CLAIRE directory:

```bash
python ~/CLAIRE/run_vtkviewer.py output.gdml
```

## Help

```bash
python cad_g4_app.py --help
```

## Features

### All Workflows
- ✓ Auto-detection based on inputs
- ✓ GDML export for Geant4
- ✓ Structure tree printing
- ✓ Comprehensive error handling

### STEP Native
- ✓ Hierarchy preservation
- ✓ CSG primitives where possible
- ✓ Overlap checking
- ✓ Flat mode fallback

### STL+STEP
- ✓ Auto-sizing world volume
- ✓ Fuzzy name matching
- ✓ Centered geometry
- ✓ Multiple mesh support

### Single STL
- ✓ Simplest workflow
- ✓ Auto-sizing world volume
- ✓ Automatic centering
- ✓ Fastest conversion

## pyg4ometry Features Used

This suite maximizes pyg4ometry capabilities:
- OpenCASCADE integration (STEP reading)
- STL mesh loading
- Geometry conversion with CSG
- Tessellation support
- GDML export
- Overlap detection
- Material management

## Support

For detailed usage, see:
- [cad_g4_app_README.md](cad_g4_app_README.md) - Complete guide
- [cad_g4_app_QUICKREF.md](cad_g4_app_QUICKREF.md) - Quick reference
- [SINGLE_STL_QUICKSTART.md](SINGLE_STL_QUICKSTART.md) - Single STL guide

## License

GNU V3.0
