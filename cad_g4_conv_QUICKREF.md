# Quick Reference: cad_g4_conv.py

## Command Cheatsheet

### Basic Usage

```bash
# STEP native conversion (auto-detects hierarchy mode)
python cad_g4_conv.py --step-file input.STEP

# STEP flat mode (robust fallback)
python cad_g4_conv.py --step-file input.STEP --flat

# STL+STEP mesh conversion (auto-detects)
python cad_g4_conv.py --step-file assembly.STEP --stl-dir STLs/

# Single STL conversion (simplest workflow)
python cad_g4_conv.py --stl-file mesh.stl

# Custom output file
python cad_g4_conv.py --step-file input.STEP -o output.gdml

# Check for overlaps
python cad_g4_conv.py --step-file input.STEP --check-overlaps

# Center geometry at world origin
python cad_g4_conv.py --step-file input.STEP --center-origin

# Write detailed logs
python cad_g4_conv.py --stl-file mesh.stl --log-file convert.log --log-level DEBUG
```

Note: All conversions automatically check and repair tessellated meshes before export.

### Real Examples

```bash
# HEPI-SiO2 detector (STEP native)
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o HEPI-SiO2.gdml

# Stacked Trays (STL+STEP)
python cad_g4_conv.py \
    --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP \
    --stl-dir CAD_files/Stacked-Trays/STLs \
    -o Stacked-Trays.gdml

# HEPI-PbF2 with overlap check
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-PbF2/HEPI-PbF2.STEP \
    -o HEPI-PbF2.gdml \
    --check-overlaps

# Stacked Trays centered at origin
python cad_g4_conv.py \
    --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP \
    --stl-dir CAD_files/Stacked-Trays/STLs \
    --center-origin \
    -o Stacked-Trays.gdml
```

## Decision Tree

```
Need to convert CAD to GDML?
│
├─ Have a single STL file?
│  │
│  ├─ YES → Use Single STL mode
│  │        python cad_g4_conv.py --stl-file mesh.stl
│  │        ✓ Simplest workflow
│  │        ✓ Auto-sized world
│  │        ✓ Fastest conversion
│  │
│  └─ NO → Have multiple STL files?
│           │
│           ├─ YES → Have STEP for placements?
│           │  │
│           │  ├─ YES → Use STL+STEP mode
│           │  │        python cad_g4_conv.py --step-file X.STEP --stl-dir STLs/
│           │  │        ✓ High mesh quality
│           │  │        ✓ Auto-sized world
│           │  │        ✓ Assembly structure
│           │  │
│           │  └─ NO → Convert STLs individually or get STEP
│           │
│           └─ NO → Have STEP file?
│                    │
│                    ├─ Hierarchy mode works?
│                    │  │
│                    │  ├─ YES → Use default (hierarchy)
│                    │  │        python cad_g4_conv.py --step-file X.STEP
│                    │  │        ✓ CSG primitives
│                    │  │        ✓ Maintains structure
│                    │  │        ✓ Efficient geometry
│                    │  │
│                    │  └─ NO → Use flat mode
│                    │           python cad_g4_conv.py --step-file X.STEP --flat
│                    │           ✓ More robust
│                    │           ✓ Single solid
│                    │           ✓ Fewer failures
```

## Workflow Comparison

| Aspect | STEP Native | STEP Flat | STL+STEP | Single STL |
|--------|-------------|-----------|----------|------------|
| **Input** | STEP file | STEP file | STEP + STL dir | STL file |
| **Geometry** | CSG + Tessellation | Tessellation only | Mesh (tessellated) | Mesh (tessellated) |
| **Hierarchy** | Preserved | Lost | Flat | None |
| **Speed** | Medium | Fast | Fast | Fastest |
| **Robustness** | Medium | High | High | Highest |
| **File Size** | Small-Medium | Medium-Large | Medium-Large | Small |
| **World Size** | Fixed 5000mm | Fixed 5000mm | Auto-calculated | Auto-calculated |
| **Best For** | Clean assemblies | Complex CAD | When STLs available | Single meshes |

## Output Comparison

### STEP Native (Hierarchy)
```
HEPI-SiO2 [Assembly]
├── Housing [TessellatedSolid]
├── Base [TessellatedSolid]
└── Sensor Assembly [Assembly]
    ├── SiPM [TessellatedSolid]
    └── Radiator [TessellatedSolid]

Total: 10 volumes
```

### STEP Flat
```
world_lv [Box]
└── cad_lv [TessellatedSolid]

Total: 2 volumes
```

### STL+STEP
```
world_lv [Box, auto-sized]
├── Part1 [TessellatedSolid]
├── Part2 [TessellatedSolid]
└── Part3 [TessellatedSolid]

Total: 14 volumes
World: 114×120×115 mm³
```

## Common Patterns

### Development Workflow
```bash
# 1. First try: hierarchy mode
python cad_g4_conv.py --step-file input.STEP -o v1.gdml

# 2. Visualize
python run_vtkviewer.py v1.gdml

# 3. Check overlaps
python cad_g4_conv.py --step-file input.STEP -o v1.gdml --check-overlaps

# 4. If issues, try flat
python cad_g4_conv.py --step-file input.STEP -o v2_flat.gdml --flat

# 5. Or try STL if available
python cad_g4_conv.py --step-file input.STEP --stl-dir STLs/ -o v3_stl.gdml
```

### Batch Processing
```bash
# Process all STEP files in directory
for f in CAD_files/*/*.STEP; do
    base=$(basename "$f" .STEP)
    python cad_g4_conv.py --step-file "$f" -o "${base}.gdml"
done
```

### Validation Pipeline
```bash
# Convert with overlap check
python cad_g4_conv.py \
    --step-file input.STEP \
    -o output.gdml \
    --check-overlaps > validation.log 2>&1

# Visualize
python run_vtkviewer.py output.gdml

# Extract key metrics
grep -E "(Total volumes|overlap)" validation.log
```

## Troubleshooting Quick Guide

| Problem | Solution |
|---------|----------|
| "No free shapes found" | STEP file corrupt, re-export from CAD |
| "Hierarchy conversion failed" | Use `--flat` flag |
| "Missing STEP placement" | Check STL filenames match STEP parts |
| Many overlaps | Try `--flat` or STL+STEP mode |
| Geometry offset | Check CAD export units and origin |
| Viewer shows nothing | Check GDML file size, may be empty |
| Out of memory | Use `--flat` for simpler geometry |

## pyg4ometry Features Used

✓ **pyoce.Reader** - STEP file parsing  
✓ **convert.oce2Geant4()** - Hierarchy conversion with CSG  
✓ **convert.oceShape_Geant4_Tessellated()** - Robust tessellation  
✓ **stl.Reader** - STL mesh loading  
✓ **geant4.Registry** - Geometry management  
✓ **geant4.Material** - Material definitions  
✓ **geant4.solid.Box** - World volume creation  
✓ **geant4.LogicalVolume** - Volume hierarchy  
✓ **geant4.PhysicalVolume** - Placement and positioning  
✓ **LogicalVolume.checkOverlaps()** - Validation  
✓ **gdml.Writer** - GDML export  

## Tips for Best Results

1. **Start Simple**: Try default hierarchy mode first
2. **Check Overlaps**: Always validate geometry before simulation
3. **Use Flat When Needed**: Don't fight with complex hierarchies
4. **STL for Quality**: Use STL+STEP when mesh quality matters
5. **Visualize Early**: Catch issues before running simulations
6. **Read Logs**: Structure trees show what was converted
7. **Name Files Well**: STL filenames should match STEP part names
8. **Export Settings**: Check CAD export units (mm) and coordinate system

## Performance Notes

| Task | Typical Time | Memory |
|------|-------------|--------|
| STEP read | 1-5s | 100-500 MB |
| Hierarchy conversion | 5-30s | 500 MB - 2 GB |
| Flat conversion | 2-10s | 200-800 MB |
| STL loading (10 files) | 1-3s | 100-300 MB |
| GDML write | 1-5s | Minimal |
| Overlap check | 10-60s | Minimal |

## Related Commands

```bash
# View GDML
python run_vtkviewer.py output.gdml

# View STEP directly
python run_vtkviewer.py input.STEP

# View STL
python run_vtkviewer.py mesh.stl

# Help
python cad_g4_conv.py --help
```
