# Quick Start: Single STL Workflow

The simplest way to convert an STL mesh to GDML for Geant4.

## One-Line Conversion

```bash
python cad_g4_app.py --stl-file your_mesh.stl
```

That's it! Output will be `output.gdml` by default.

## What Happens?

1. **STL Loading**: Reads the mesh using pyg4ometry
2. **Bounding Box**: Calculates mesh dimensions automatically
3. **World Sizing**: Creates world volume with 10% margin around mesh
4. **Centering**: Places mesh at origin for optimal viewing
5. **GDML Export**: Writes ready-to-use GDML file

## Example Session

```bash
# Convert
$ python cad_g4_app.py --stl-file part.stl

============================================================
SINGLE STL-TO-GDML CONVERSION (Simple Mesh)
============================================================
Input: part.stl
Output: output.gdml

Loading STL file...

Geometry information:
  Bounding box: [10.0, 20.0, 5.0] to [50.0, 80.0, 35.0]
  World size: [40.0, 60.0, 30.0] mm
  Center offset: [-30.0, -50.0, -20.0]

Placing mesh in world volume...

============================================================
GDML STRUCTURE TREE
============================================================
world_lv [Box, G4_AIR]
    └── pv_part (LV: lv_stl_solid_part) [TessellatedSolid, G4_Al]

Total volumes: 2
============================================================

Writing GDML file: output.gdml
✓ GDML export complete

# Visualize
$ python run_vtkviewer.py output.gdml
```

## Common Use Cases

### 1. Quick Mesh Preview
```bash
# Just exported from CAD? Check it immediately:
python cad_g4_app.py --stl-file exported.stl
python run_vtkviewer.py output.gdml
```

### 2. Custom Output Name
```bash
python cad_g4_app.py --stl-file detector_base.stl -o base.gdml
```

### 3. Batch Processing
```bash
# Convert all STLs in current directory:
for stl in *.stl; do
    python cad_g4_app.py --stl-file "$stl" -o "${stl%.stl}.gdml"
done
```

### 4. Test Different Resolutions
```bash
python cad_g4_app.py --stl-file mesh_low_res.stl -o low.gdml
python cad_g4_app.py --stl-file mesh_high_res.stl -o high.gdml
# Compare file sizes and quality
```

## Output Structure

Every single STL conversion produces:

```
GDML File
├── world_lv [Box, G4_AIR]
│   ├── Auto-sized to fit mesh + 10% margin
│   └── Centered at origin
│
└── pv_<meshname> [TessellatedSolid, G4_Al]
    ├── Mesh geometry from STL
    ├── Material: Aluminum (G4_Al)
    └── Positioned at world center
```

Total volumes: Always 2 (world + mesh)

## Advantages Over Other Workflows

| Feature | Single STL | STL+STEP | STEP Native |
|---------|-----------|----------|-------------|
| Input files | 1 STL | N STLs + 1 STEP | 1 STEP |
| Setup time | Seconds | Minutes | Minutes |
| Dependencies | None | STEP for placements | STEP reader |
| Complexity | ⭐ | ⭐⭐ | ⭐⭐⭐ |
| Best for | Prototyping | Assemblies | CAD native |

## When to Use

✅ **Use Single STL workflow when:**
- You have a single mesh file
- No assembly structure needed
- Quick visualization required
- Learning/teaching CAD→Geant4 workflow
- Testing mesh quality
- Prototyping detector geometry

❌ **Don't use Single STL if:**
- You need multiple parts → Use STL+STEP
- You need assembly hierarchy → Use STEP Native
- You need CSG primitives → Use STEP Native

## Tips

1. **File Format**: Accepts both `.stl` and `.STL` extensions
2. **Units**: STL should be in millimeters (Geant4 default)
3. **Orientation**: Mesh will be centered; check original orientation
4. **Materials**: Default is G4_Al; edit GDML file to change
5. **World Size**: Auto-calculated; typically 20% larger than mesh

## Troubleshooting

### "STL file not found"
```bash
# Check path is correct:
ls -lh your_mesh.stl

# Use absolute path:
python cad_g4_app.py --stl-file /full/path/to/mesh.stl
```

### Mesh appears offset in viewer
This is normal! The converter centers the mesh at origin. If you need a specific position, edit the GDML file's `<position>` tag.

### World box too small/large
The auto-sizing adds 10% margin. If you need different sizing, edit the `<box>` dimensions in the GDML file, or use a different workflow.

## Next Steps

After successful conversion:

1. **Visualize**: `python run_vtkviewer.py output.gdml`
2. **Validate**: Check mesh quality and orientation
3. **Customize**: Edit GDML to change materials, positions
4. **Simulate**: Use in Geant4 application
5. **Integrate**: Combine with other geometries

## Complete Example

```bash
# 1. Convert STL to GDML
python cad_g4_app.py --stl-file detector_housing.stl -o housing.gdml

# 2. View in 3D
python run_vtkviewer.py housing.gdml

# 3. Check structure
grep -A 5 "<volume name" housing.gdml

# 4. Ready for Geant4!
# Use housing.gdml in your Geant4 application
```

## Need More?

- **Multiple parts?** → Use `--step-file X.STEP --stl-dir STLs/`
- **Assembly structure?** → Use `--step-file X.STEP` (native)
- **Help?** → Run `python cad_g4_app.py --help`

---

**Remember**: This is the simplest workflow! One file in, one GDML out. Perfect for getting started or quick prototyping.
