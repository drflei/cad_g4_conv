# CAD to Geant4 Converter (cad_g4_conv.py)

Unified application merging `step_g4_app.py` and `stl_g4_app.py` functionality with maximum use of pyg4ometry features.

## Overview

Converting CAD to GDML/Geant4 requires preparation and deliberate export choices in the CAD tool. This application supports three workflows and assumes you follow best practices (see the main README):

### 1. STEP-to-GDML (Native Geometry)
- Direct STEP file conversion using pyg4ometry's OpenCASCADE backend
- Maintains assembly hierarchy from STEP file
- Converts simple shapes to CSG primitives where possible
- Falls back to tessellation for complex shapes
- Optional flat mode for robustness

### 2. STL+STEP-to-GDML (Mesh Geometry)
- Uses STL files for high-quality mesh data
- Extracts placement information from STEP assembly
- Auto-sizes world volume based on geometry bounds
- Fuzzy name matching between STL files and STEP components

### 3. Single STL-to-GDML (Simple Mesh)
- Converts a single STL file to GDML
- Auto-sizes world volume around the mesh
- Places mesh at origin
- Quickest workflow for standalone meshes

## Installation Requirements

```bash
pip install pyg4ometry vtk
```

## Usage Examples

### STEP Native Conversion (Hierarchy Mode)
```bash
# Maintain assembly structure with CSG primitives
python cad_g4_conv.py --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP

# Custom output file
python cad_g4_conv.py --step-file input.STEP -o output.gdml
```

### STEP Flat Mode (Single Tessellated Solid)
```bash
# More robust for complex assemblies
python cad_g4_conv.py --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP --flat
```

### STL+STEP Mesh Conversion
```bash
# Use STL meshes with STEP placement data
python cad_g4_conv.py \
    --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP \
    --stl-dir CAD_files/Stacked-Trays/STLs

# Custom output
python cad_g4_conv.py \
    --step-file assembly.STEP \
    --stl-dir STLs/ \
    -o custom_output.gdml
```

### Single STL Conversion
```bash
# Convert a single STL file (quickest method)
python cad_g4_conv.py --stl-file mesh.stl

# With custom output
python cad_g4_conv.py --stl-file part.stl -o part.gdml
```

### Overlap Checking
```bash
# Check for geometry overlaps (STEP-only workflow)
python cad_g4_conv.py --step-file input.STEP --check-overlaps
```

### Centering Geometry
```bash
# Center geometry at world origin (applies offset to all placements)
python cad_g4_conv.py --step-file input.STEP --center-origin

# Center STL+STEP geometry
python cad_g4_conv.py \
    --step-file assembly.STEP \
    --stl-dir STLs/ \
    --center-origin \
    -o centered.gdml
```

## Command Line Options

```
--step-file PATH        Path to STEP file
--stl-file PATH         Path to single STL file (for simple mesh workflow)
--stl-dir PATH          Directory containing STL files (for STL+STEP workflow)
--output, -o PATH       Output GDML file path (default: output.gdml)
--flat                  Use flat tessellated mode (STEP-only)
--check-overlaps        Perform geometry overlap checking (STEP-only)
--center-origin         Center the geometry at world origin
```

## Workflow Detection

The tool automatically detects which workflow to use:

- **STEP-only**: When only `--step-file` is provided
- **STL+STEP**: When both `--step-file` and `--stl-dir` are provided
- **Single STL**: When only `--stl-file` is provided

## Features

### STEP-to-GDML Features
- **Hierarchy preservation**: Maintains parent-child relationships from STEP assembly
- **CSG conversion**: Converts simple shapes (boxes, cylinders, etc.) to efficient primitives
- **Tessellation fallback**: Complex shapes automatically tessellated
- **Volume renaming**: Replaces spaces with underscores for compatibility
- **Overlap detection**: Built-in geometry validation
- **Structure tree printing**: Visual hierarchy display

### STL+STEP Features
- **Auto-sizing world volume**: Calculates optimal bounding box with 10% margin
- **Fuzzy name matching**: Robust matching between STL filenames and STEP component names
- **Identity transforms**: STL files assumed to be in world coordinates
- **Centered geometry**: Automatically centers assembly at origin
- **Batch processing**: Handles multiple STL files efficiently

### Single STL Features
- **Ultra-simple workflow**: Just one STL file input
- **Auto-sizing world volume**: Calculates optimal bounding box with 10% margin
- **Centered geometry**: Mesh automatically centered at origin
- **Fast conversion**: No STEP parsing overhead
- **Perfect for prototyping**: Quick conversion for visualization and testing

### Common Features
- **Material assignment**: Automatic material setup (G4_AIR for world, G4_Al for parts)
- **STEP tree visualization**: Displays assembly structure before conversion
- **GDML tree visualization**: Shows resulting GDML hierarchy
- **Volume counting**: Reports total number of volumes created
- **Error handling**: Graceful degradation with informative messages

## Output Files

All commands generate a GDML file suitable for:
- Geant4 simulation
- Visualization with VTK viewer (`run_vtkviewer.py`)
- Import into Geant4 applications

## pyg4ometry Features Used

This tool maximizes use of pyg4ometry capabilities:

1. **OpenCASCADE Integration** (`pyg4ometry.pyoce`)
   - `Reader`: STEP file parsing
   - `pythonHelpers`: Label and name extraction
   - Shape manipulation and querying

2. **Conversion Tools** (`pyg4ometry.convert`)
   - `oce2Geant4()`: Hierarchy-preserving STEP→G4 conversion with CSG
   - `oceShape_Geant4_Tessellated()`: Robust tessellation fallback

3. **Geant4 Geometry** (`pyg4ometry.geant4`)
   - `Registry`: Geometry database management
   - `Material`: Material definitions
   - `solid.Box`: World volume creation
   - `LogicalVolume`: Volume hierarchy
   - `PhysicalVolume`: Placement and positioning
   - `checkOverlaps()`: Built-in overlap detection

4. **STL Import** (`pyg4ometry.stl`)
   - `Reader`: STL mesh loading
   - Facet list access for bounding box calculations

5. **GDML Export** (`pyg4ometry.gdml`)
   - `Writer`: GDML file generation

## Tips and Best Practices

### When to Use STEP Native Mode
- You have a well-formed STEP assembly
- You need efficient CSG primitives
- Hierarchy preservation is important
- File size needs to be minimized

### When to Use Flat Mode
- STEP hierarchy mode fails
- Complex nested assemblies cause issues
- You don't need hierarchy information
- Maximum robustness required

### When to Use STL+STEP Mode
- STEP native conversion fails or produces artifacts
- You have high-quality STL exports available
- Mesh accuracy is critical
- STEP file is unreliable but assembly structure is correct

### When to Use Single STL Mode
- You have a single mesh file
- No assembly structure needed
- Quick prototyping and visualization
- Testing mesh quality before simulation
- Simplest possible workflow

### Overlap Checking
- Always check for overlaps before running simulations
- Overlaps can cause incorrect physics results
- Some overlaps may be acceptable (tessellation artifacts)
- Use flat mode if overlaps are unavoidable

## Common Issues and Solutions

### Issue: "No free shapes found in STEP file"
**Solution**: STEP file may be corrupt or empty. Try re-exporting from CAD software.

### Issue: "Hierarchy conversion failed"
**Solution**: Use `--flat` mode for robustness.

### Issue: "Missing STEP placement for STL file"
**Solution**: Check that STL filenames contain recognizable part names from STEP assembly. The tool uses fuzzy matching but needs some name overlap.

### Issue: Geometry appears offset or incorrectly sized
**Solution**: 
- For STEP mode: Try flat mode
- For STL mode: STL files are assumed to be in world coordinates. Check your CAD export settings.

### Issue: Many overlaps detected
**Solution**: 
- Review CAD model for actual overlaps
- Try flat mode to eliminate tessellation-induced overlaps
- Accept minor overlaps if they're tessellation artifacts

## Related Tools

- **run_vtkviewer.py**: Interactive 3D viewer for GDML, STL, STEP, FLUKA files
- **step_g4_app.py**: Original STEP-only converter (deprecated, use cad_g4_conv.py)
- **stl_g4_app.py**: Original STL+STEP converter (deprecated, use cad_g4_conv.py)

## Example Workflow

```bash
# 1. Convert CAD to GDML
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o hepi.gdml \
    --check-overlaps

# 2. Visualize result
python run_vtkviewer.py hepi.gdml

# 3. If overlaps are problematic, try flat mode
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o hepi_flat.gdml \
    --flat

# 4. Or try STL+STEP mode if STLs available
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    --stl-dir CAD_files/HEPI-SiO2/STLs \
    -o hepi_mesh.gdml
```

## Technical Notes

### Coordinate Systems
- **STEP mode**: Uses native STEP coordinate transformations
- **STL mode**: Assumes STL files are exported in world coordinates (identity transform)

### World Volume Sizing
- **STEP hierarchy**: Uses default 5000×5000×5000 mm³ box
- **STEP flat**: Uses default 5000×5000×5000 mm³ box
- **STL+STEP**: Auto-calculates from geometry bounds + 10% margin

### Materials
- All parts default to G4_Al (aluminum)
- World volume uses G4_AIR
- Materials can be customized by editing the script

### Performance
- **STEP hierarchy**: Moderate (CSG conversion + hierarchy traversal)
- **STEP flat**: Fast (single tessellation)
- **STL+STEP**: Fast (direct mesh loading, no conversion)

## License

Part of the CLAIRE project. See project LICENSE file.
