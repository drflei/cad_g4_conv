# CAD to Geant4 Implementation: STL/STEP Transformation Handling

## Overview

This document describes the correct implementation for transforming CAD assembly data (STEP format) into Geant4 geometry using STL meshes. The key challenge is handling the **coordinate system mismatch** between STEP reference shapes and STL exports.

## The Core Problem

When working with CAD assemblies:

1. **STEP files** store parts with their original CAD coordinate system, where `bbox_min` (minimum bounding box corner) is typically at a non-zero position relative to the assembly origin.

2. **STL exports** (via FreeCAD or similar tools) normalize meshes so that `bbox_min = (0, 0, 0)` — all vertex coordinates are shifted to start at the origin.

3. **STEP placement transforms** (translation + rotation) are defined relative to the original CAD coordinate system, NOT the STL-normalized coordinate system.

### Example: Top Tray Part

| Source | bbox_min | bbox_max |
|--------|----------|----------|
| STEP ref shape | (-26.55, 17.29, -6.57) | (65.45, 53.65, 26.43) |
| STL file | (0, 0, 0) | (95, 33, 33) |

The STL is shifted by the STEP bbox_min to start at origin.

---

## The Correct Transformation Formula

### Basic Formula (No Rotation)

For parts without rotation, the world position of the STL origin corner is:

```
placement = STEP_translation + STEP_bbox_min
```

This compensates for the STL normalization by adding back the offset that was removed.

### Formula with Rotation

For rotated parts, the formula becomes:

```
placement = STEP_translation + R @ STEP_bbox_min
```

Where:
- `R` is the 3×3 rotation matrix
- `@` denotes matrix-vector multiplication

**Why?** The rotation is applied around the STEP origin, so `bbox_min` must also be rotated before adding to the translation.

### Refined Formula (Using Actual STL Size)

When STEP reference shape dimensions differ slightly from STL dimensions (due to tessellation or export tolerances), use the actual STL size for precision:

```python
# Compute rotated bounding box from actual STL size
corners = 8 corner points of STL bbox (starting at origin)
rotated_corners = [R @ corner for corner in corners]
rot_bbox_min = minimum of all rotated corners

# Final placement
placement = unrot_world_corner - rot_bbox_min

# Where unrot_world_corner was computed from direct (non-rotated) occurrence:
unrot_world_corner = STEP_translation + STEP_bbox_min
```

---

## Rotation Extraction from STEP

### Using pyg4ometry/OpenCASCADE

```python
# Get transformation from component shape
child_shape = st.GetShape(comp_label)
child_loc = child_shape.Location()
trsf = child_loc.Transformation()

# Extract translation
tp = trsf.TranslationPart()
step_tra = [tp.X(), tp.Y(), tp.Z()]

# Extract rotation as axis-angle
axis_out = gp_XYZ()
ok, axis_out, angle_out = trsf.GetRotation(axis_out, angle_out)

# Convert axis-angle to rotation matrix using Rodrigues' formula
R = axis_angle_to_matrix(axis, angle)

# Convert to Euler angles for GDML (use NEGATIVE angle per pyg4ometry convention)
euler = axisangle2tbxyz(axis, -angle)
```

### Key Insight: Negative Angle

pyg4ometry's `axisangle2tbxyz()` expects the **negated** angle:
```python
rot = pyg4ometry.transformation.axisangle2tbxyz(axis_v, -angle_val)
```

This matches how Geant4 interprets rotation angles in GDML.

---

## Different Rotation Axes for Different Parts

180° rotations can occur around different axes:

| Part | Rotation Axis | Effect on (x,y,z) |
|------|--------------|-------------------|
| Top Tray | Z axis | (-x, -y, z) |
| Base | X axis | (x, -y, -z) |
| Back plate | Y axis | (-x, y, -z) |

The rotation matrix correctly handles all cases automatically.

---

## Implementation Strategy

### 1. Collect All Occurrences

Traverse STEP assembly to find all component occurrences:
- Direct children of assembly
- Recursive components (for nested assemblies)

```python
# Direct children
for i in range(1, root.NbChildren() + 1):
    found, child = root.FindChild(i, False)
    if found:
        extract_transform(child)

# Recursive components
st.GetComponents(root, seq, expand=True)
for comp in seq:
    extract_transform(comp)
```

### 2. Classify Occurrences

For each unique part, separate occurrences by rotation:

```python
no_rot = [o for o in occs if o["angle_abs"] < 0.1]    # ~0° rotation
rotated = [o for o in occs if o["angle_abs"] > 0.1]   # Has rotation
```

### 3. Compute Placement Based on Category

**Case A: Direct occurrence exists, no rotation needed**
```python
# Simple placement
placement = step_tra + bbox_min
```

**Case B: Both direct and rotated occurrences exist**
```python
# Use direct occurrence for unrotated world corner
# Use rotation from rotated occurrence
# Compute with actual STL size for precision
unrot_world_corner = direct.step_tra + direct.bbox_min
rot_bbox_min = compute_from_stl_size(R, stl_size)
placement = unrot_world_corner - rot_bbox_min
```

**Case C: Only rotated occurrence exists**
```python
# Apply formula directly
placement = step_tra + R @ bbox_min
```

---

## GDML Output Format

The final physical volume placement in GDML:

```xml
<physvol name="pv_5_Top_Tray">
    <volumeref ref="lv_stl_solid_5_Top_Tray"/>
    <position name="pv_5_Top_Tray_pos" 
              x="78.158" y="77.454" z="28.380" unit="mm"/>
    <rotation name="pv_5_Top_Tray_rot" 
              x="0.0" y="0.0" z="3.14159" unit="rad"/>
</physvol>
```

Where:
- Position is the computed `placement` vector
- Rotation is Euler angles (rx, ry, rz) for successive X→Y→Z rotations

---

## pyg4ometry Mesh Handling (Reference)

From pyg4ometry's `AssemblyVolume._getPVMeshes()`:

```python
# Rotation applied FIRST, then translation
m.rotate(rotation_axis, rotation_angle)
m.translate(translation_vector)
```

This is the standard convention: objects are rotated about their local origin first, then translated to their world position.

---

## Complete Code Reference

See `stl_g4_app.py`:

| Function | Purpose |
|----------|---------|
| `_axis_angle_to_matrix()` | Convert axis-angle to 3×3 rotation matrix |
| `_mat_vec()` | Matrix-vector multiplication |
| `_oce_shape_bbox()` | Compute bounding box of STEP shape |
| `_extract_step_placements()` | Main logic for extracting and computing placements |
| `aabb_from_facets()` | Compute STL bounding box |

---

## Summary

The key to correct CAD→Geant4 transformation:

1. **Understand the coordinate shift**: STL exports normalize to origin; STEP keeps original coordinates
2. **Apply the compensation formula**: `placement = STEP_tra + R @ STEP_bbox_min`
3. **Use negative angle** when converting axis-angle to Euler angles for pyg4ometry
4. **Consider actual STL size** when dimensions differ from STEP reference shape

This approach successfully places all assembly components (Base, Back plate, Middle Trays, Top Tray) in their correct positions with proper rotations.
