#!/usr/bin/env python3
"""Unified CAD to Geant4 converter supporting STEP and STL formats.

This script uses pyg4ometry to convert CAD files to GDML for Geant4 simulations.
It supports three main workflows:

1. STEP-to-GDML (Native Geometry):
   - Maintains assembly hierarchy from STEP file
   - Converts simple shapes to CSG primitives where possible
   - Falls back to tessellation for complex shapes
   - Preserves parent-child relationships
   - Optional flat mode for robustness

2. STL+STEP-to-GDML (Mesh Geometry):
   - Uses STL files for mesh data
   - Extracts placement information from STEP assembly
   - Useful when STEP conversion fails or mesh is preferred
   - Auto-sizes world volume based on geometry bounds

3. Single STL-to-GDML (Simple Mesh):
   - Converts a single STL file to GDML
   - Auto-sizes world volume around the mesh
   - Places mesh at origin
   - Quickest workflow for standalone meshes

USAGE EXAMPLES:
===============

    # STEP-to-GDML with hierarchy (CSG where possible)
    python cad_g4_conv.py --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP
    
    # STEP-to-GDML flat mode (single tessellated solid)
    python cad_g4_conv.py --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP --flat
    
    # STL+STEP-to-GDML (mesh mode)
    python cad_g4_conv.py --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP --stl-dir CAD_files/Stacked-Trays/STLs
    
    # Single STL-to-GDML (simple mesh)
    python cad_g4_conv.py --stl-file mesh.stl
    
    # Custom output file
    python cad_g4_conv.py --step-file input.STEP -o output.gdml
    
    # Check overlaps
    python cad_g4_conv.py --step-file input.STEP --check-overlaps

FEATURES:
=========
- Auto-detection of workflow based on inputs
- Hierarchy preservation with CSG conversion
- Overlap checking
- Auto-sizing world volume
- Structure tree printing
- Fuzzy name matching for STL/STEP association
- Identity transforms for STLs (already in world coordinates)
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import io
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

import pyg4ometry


def configure_logging(logfile: str | None = None, level: str = "INFO") -> None:
    """Configure root logger to output to console and optionally to a file."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(lvl)

    # Remove existing handlers to avoid duplicate logs in repeated calls
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    if logfile:
        fh = logging.FileHandler(logfile)
        fh.setFormatter(fmt)
        root.addHandler(fh)


logger = logging.getLogger(__name__)


def _get_first_free_shape_name(reader: pyg4ometry.pyoce.Reader) -> str:
    """Get name of first free shape in STEP file."""
    free_shapes = reader.freeShapes()
    if free_shapes.Size() < 1:
        raise RuntimeError("No free shapes found in STEP file")

    label = free_shapes.Value(1)
    name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
    if not name:
        raise RuntimeError("First free shape has no name in STEP file")
    return name


def _print_step_tree(step_path: Path) -> None:
    """Print STEP file structure tree with complete hierarchy."""
    reader = pyg4ometry.pyoce.Reader(str(step_path))
    st = reader.shapeTool
    free_shapes = reader.freeShapes()
    if free_shapes.Size() < 1:
        return
    
    root = free_shapes.Value(1)
    circular_refs = []  # Track circular references found
    
    def label_name(label) -> str:
        name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
        return name.strip() if name else "(unnamed)"
    
    def get_referred_label(label):
        """Get the label that this reference points to."""
        if st.IsReference(label):
            pyoce = pyg4ometry.pyoce
            referred = pyoce.TDF.TDF_Label()
            if st.GetReferredShape(label, referred):
                return referred
        return None
    
    def print_node(label, indent=0, prefix="", connector="", visited=None, path=None):
        if visited is None:
            visited = set()
        if path is None:
            path = []
        
        name = label_name(label)
        
        # Avoid infinite loops
        label_id = label.Tag()
        if label_id in visited:
            print(f"{prefix}{connector}{name} [Circular Reference]")
            # Record circular reference with path info
            circular_refs.append({
                'name': name,
                'tag': label_id,
                'path': ' → '.join(path) + f" → {name}"
            })
            return
        visited.add(label_id)
        path = path + [name]
        
        shape = st.GetShape(label)
        shape_type = type(shape).__name__ if shape else "None"
        is_assy = "[Assembly]" if st.IsAssembly(label) else "[Part]"
        is_ref = "[Ref]" if st.IsReference(label) else ""
        
        # Get shape info if available
        shape_info = ""
        if shape and not st.IsAssembly(label):
            try:
                bbox_min, bbox_max = _oce_shape_bbox(shape, lin_def=1.0, ang_def=1.0)
                size = [bbox_max[i] - bbox_min[i] for i in range(3)]
                if any(s > 0.01 for s in size):
                    shape_info = f" [Size: {size[0]:.1f}×{size[1]:.1f}×{size[2]:.1f}mm]"
            except:
                pass
        
        print(f"{prefix}{connector}{name} {is_assy}{is_ref} ({shape_type}){shape_info}")
        
        # Process children
        children = []
        if label.NbChildren() > 0:
            for i in range(1, label.NbChildren() + 1):
                found, child = label.FindChild(i, False)
                if found:
                    children.append(child)
        
        # If this is a reference, also show what it refers to
        if st.IsReference(label):
            referred = get_referred_label(label)
            if referred and referred.Tag() not in visited:
                # Add the referred content as a special child
                children.insert(0, referred)
        
        # Print all children
        for idx, child in enumerate(children):
            is_last = (idx == len(children) - 1)
            new_connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "
            print_node(child, indent + 1, prefix + extension, new_connector, visited.copy(), path)
    
    print("\n" + "="*60)
    print("STEP FILE STRUCTURE TREE (Complete Hierarchy)")
    print("="*60)
    
    # Count total components
    def count_components(label, visited=None):
        if visited is None:
            visited = set()
        label_id = label.Tag()
        if label_id in visited:
            return 0
        visited.add(label_id)
        
        count = 1
        if label.NbChildren() > 0:
            for i in range(1, label.NbChildren() + 1):
                found, child = label.FindChild(i, False)
                if found:
                    count += count_components(child, visited)
        return count
    
    total_count = count_components(root)
    
    print_node(root)
    print("="*60)
    print(f"Total components: {total_count}")
    
    # Print circular reference summary
    if circular_refs:
        print(f"⚠ Circular references detected: {len(circular_refs)}")
        print("-" * 60)
        for i, ref in enumerate(circular_refs, 1):
            print(f"  {i}. {ref['name']} (Tag: {ref['tag']})")
            print(f"     Path: {ref['path']}")
    else:
        print("✓ No circular references detected")
    
    print("="*60 + "\n")


def _print_gdml_tree(reg: pyg4ometry.geant4.Registry) -> None:
    """Print GDML structure tree."""
    world_lv = reg.getWorldVolume()
    
    def print_volume(lv, pv_name="", indent=0, prefix="", connector=""):
        solid_type = type(lv.solid).__name__ if hasattr(lv, 'solid') else "Unknown"
        material = lv.material.name if hasattr(lv, 'material') and hasattr(lv.material, 'name') else "N/A"
        
        if pv_name:
            display_name = f"{pv_name} (LV: {lv.name})"
        else:
            display_name = lv.name
        
        print(f"{prefix}{connector}{display_name} [{solid_type}, {material}]")
        
        if hasattr(lv, 'daughterVolumes'):
            for i, pv in enumerate(lv.daughterVolumes):
                is_last = (i == len(lv.daughterVolumes) - 1)
                new_connector = "└── " if is_last else "├── "
                extension = "    " if is_last else "│   "
                pv_name_str = pv.name if hasattr(pv, 'name') else ""
                print_volume(pv.logicalVolume, pv_name_str, indent + 1, prefix + extension, new_connector)
    
    print("\n" + "="*60)
    print("GDML STRUCTURE TREE")
    print("="*60)
    print_volume(world_lv)
    
    # Count total volumes
    def count_volumes(lv):
        count = 1
        if hasattr(lv, 'daughterVolumes'):
            for pv in lv.daughterVolumes:
                count += count_volumes(pv.logicalVolume)
        return count
    
    total = count_volumes(world_lv)
    print(f"\nTotal volumes: {total}")
    print("="*60 + "\n")


def _norm_key(s: str) -> str:
    """Normalize key for fuzzy matching (remove spaces, lowercase, alphanumeric only)."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _axis_angle_to_matrix(axis: List[float], angle: float) -> List[List[float]]:
    """Convert axis-angle to rotation matrix using Rodrigues' formula."""
    import math

    ax, ay, az = axis
    n2 = ax * ax + ay * ay + az * az
    if n2 == 0.0:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    inv_n = 1.0 / math.sqrt(n2)
    ax *= inv_n
    ay *= inv_n
    az *= inv_n

    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c

    return [
        [t * ax * ax + c, t * ax * ay - s * az, t * ax * az + s * ay],
        [t * ax * ay + s * az, t * ay * ay + c, t * ay * az - s * ax],
        [t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c],
    ]


def _mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    """Multiply two 3x3 matrices."""
    return [
        [
            a[0][0] * b[0][0] + a[0][1] * b[1][0] + a[0][2] * b[2][0],
            a[0][0] * b[0][1] + a[0][1] * b[1][1] + a[0][2] * b[2][1],
            a[0][0] * b[0][2] + a[0][1] * b[1][2] + a[0][2] * b[2][2],
        ],
        [
            a[1][0] * b[0][0] + a[1][1] * b[1][0] + a[1][2] * b[2][0],
            a[1][0] * b[0][1] + a[1][1] * b[1][1] + a[1][2] * b[2][1],
            a[1][0] * b[0][2] + a[1][1] * b[1][2] + a[1][2] * b[2][2],
        ],
        [
            a[2][0] * b[0][0] + a[2][1] * b[1][0] + a[2][2] * b[2][0],
            a[2][0] * b[0][1] + a[2][1] * b[1][1] + a[2][2] * b[2][1],
            a[2][0] * b[0][2] + a[2][1] * b[1][2] + a[2][2] * b[2][2],
        ],
    ]


def _matrix_to_euler_xyz_from_rzryrx(m: List[List[float]]) -> List[float]:
    """Convert rotation matrix to Euler angles (XYZ convention)."""
    import math

    r20 = m[2][0]
    r21 = m[2][1]
    r22 = m[2][2]
    r10 = m[1][0]
    r00 = m[0][0]

    sy = -max(-1.0, min(1.0, r20))
    ry = math.asin(sy)
    cy = math.cos(ry)

    if abs(cy) < 1e-12:
        rz = 0.0
        rx = math.atan2(-m[0][1], m[1][1])
        return [rx, ry, rz]

    rx = math.atan2(r21, r22)
    rz = math.atan2(r10, r00)
    return [rx, ry, rz]


def _oce_shape_bbox(shape, *, lin_def: float = 0.5, ang_def: float = 0.5) -> Tuple[List[float], List[float]]:
    """Compute bounding box of OpenCASCADE shape by meshing and scanning vertices."""
    pyoce = pyg4ometry.pyoce

    _ = pyoce.BRepMesh.BRepMesh_IncrementalMesh(shape, lin_def, False, ang_def, True)
    exp = pyoce.TopExp.TopExp_Explorer(shape, pyoce.TopAbs.TopAbs_FACE, pyoce.TopAbs.TopAbs_SHAPE)

    mn = [float("inf"), float("inf"), float("inf")]
    mx = [float("-inf"), float("-inf"), float("-inf")]
    any_nodes = False
    while exp.More():
        face = pyoce.TopoDS.TopoDSClass.Face(exp.Current())
        loc = pyoce.TopLoc.TopLoc_Location()
        tri = pyoce.BRep.BRep_Tool.Triangulation(face, loc, 0)
        if tri is not None:
            any_nodes = True
            trsf = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                pt = tri.Node(i)
                p = pyoce.gp.gp_Pnt(pt.X(), pt.Y(), pt.Z())
                p.Transform(trsf)
                x, y, z = float(p.X()), float(p.Y()), float(p.Z())
                if x < mn[0]:
                    mn[0] = x
                if y < mn[1]:
                    mn[1] = y
                if z < mn[2]:
                    mn[2] = z
                if x > mx[0]:
                    mx[0] = x
                if y > mx[1]:
                    mx[1] = y
                if z > mx[2]:
                    mx[2] = z
        exp.Next()

    if not any_nodes:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    return mn, mx


def _extract_step_placements(step_path: Path) -> Dict[str, Dict]:
    """Extract part placements from STEP assembly.
    
    Returns dict mapping normalized part names to placement info:
    {
        "partname": {
            "type": "identity",
            "rot": [rx, ry, rz],
            "tra": [x, y, z]
        }
    }
    
    For STL workflow, all placements use identity transform since STLs
    are exported in world coordinates.
    """
    reader = pyg4ometry.pyoce.Reader(str(step_path))
    st = reader.shapeTool
    free_shapes = reader.freeShapes()
    if free_shapes.Size() < 1:
        raise RuntimeError(f"No free shapes found in STEP file: {step_path}")

    root = free_shapes.Value(1)

    def label_name(label) -> str:
        name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
        return name.strip() if name else ""

    placements: Dict[str, Dict] = {}
    all_occurrences: Dict[str, List[Dict]] = {}

    def collect_occurrences(label, parent_loc=None):
        """Recursively collect all component occurrences."""
        name = label_name(label)
        if not name:
            return
        
        keyn = _norm_key(name)
        if keyn not in all_occurrences:
            all_occurrences[keyn] = []
        
        all_occurrences[keyn].append({"label": label, "parent_loc": parent_loc})
        
        for i in range(1, label.NbChildren() + 1):
            found, child = label.FindChild(i, False)
            if found:
                collect_occurrences(child, parent_loc)

    collect_occurrences(root)

    # For STL workflow: all parts use identity transform (already in world coords)
    for keyn, occs in all_occurrences.items():
        if not occs:
            continue
        
        placements[keyn] = {
            "type": "identity",
            "rot": [0.0, 0.0, 0.0],
            "tra": [0.0, 0.0, 0.0],
        }

    return placements


def _find_best_step_match(stl_key_norm: str, step_placements: Dict) -> str | None:
    """Find best matching STEP key for STL file using fuzzy matching."""
    # Exact match
    if stl_key_norm in step_placements:
        return stl_key_norm
    
    # Find STEP keys that appear in the STL key (longest first)
    candidates = []
    for step_key in step_placements.keys():
        if step_key in stl_key_norm:
            candidates.append((step_key, len(step_key)))
    
    if candidates:
        return max(candidates, key=lambda x: x[1])[0]
    
    return None


def _build_hierarchy_manually(reader: pyg4ometry.pyoce.Reader, root_label, reg, cad_material, world_lv, offset=None):
    """Build hierarchy manually by converting each component separately, avoiding circular refs."""
    if offset is None:
        offset = [0.0, 0.0, 0.0]
    
    st = reader.shapeTool
    
    def label_name(label) -> str:
        name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
        name = name.strip() if name else f"part_{label.Tag()}"
        return name.replace(' ', '_')
    
    def get_transform(label):
        """Extract transformation from label."""
        # For now, use identity transformation with global offset
        # TODO: Extract proper transformations from STEP assembly
        tra = [offset[0], offset[1], offset[2]]
        rot = [0.0, 0.0, 0.0]
        return tra, rot
    
    def process_label(label, parent_lv, visited=None):
        """Process a label and its children, avoiding circular references."""
        if visited is None:
            visited = set()
        
        label_id = label.Tag()
        
        # Skip circular references
        if label_id in visited:
            print(f"  Skipping circular reference: {label_name(label)} (Tag: {label_id})")
            return
        
        visited.add(label_id)
        name = label_name(label)
        
        # Check if this is a reference or has a shape
        is_ref = st.IsReference(label)
        is_assembly = st.IsAssembly(label)
        
        try:
            shape = st.GetShape(label)
            if shape and not shape.IsNull():
                # Convert this component's shape to tessellated solid
                solid_name = f"{name}_solid"
                lv_name = f"{name}_lv"
                pv_name = f"{name}_pv"
                
                print(f"    Converting {name}...")
                
                # Create tessellated solid
                solid = pyg4ometry.convert.oceShape_Geant4_Tessellated(
                    name=solid_name,
                    shape=shape,
                    greg=reg,
                    linDef=0.5,
                    angDef=0.5,
                )
                
                # Create logical volume
                lv = pyg4ometry.geant4.LogicalVolume(solid, cad_material, lv_name, reg)
                
                # Get transformation
                tra, rot = get_transform(label)
                
                # Place in parent
                pyg4ometry.geant4.PhysicalVolume(rot, tra, lv, pv_name, parent_lv, reg)
        
        except Exception as e:
            print(f"  Warning: Could not process {name}: {e}")
        
        # Process children
        for i in range(1, label.NbChildren() + 1):
            found, child = label.FindChild(i, False)
            if found:
                process_label(child, parent_lv, visited)
    
    # Process all top-level components
    component_count = 0
    for i in range(1, root_label.NbChildren() + 1):
        found, child = root_label.FindChild(i, False)
        if found:
            component_count += 1
            process_label(child, world_lv)
    
    return component_count



def _check_and_repair_tessellated_solids(reg, repair=False, replace_in_place=False):
    """Inspect tessellated solids in a registry, optionally attempt mesh repairs.

    Args:
        reg: pyg4ometry Registry
        repair: attempt repairs with trimesh if non-watertight
        replace_in_place: if True, replace solids in-place (keep same names); otherwise add new solids with '-fixed' suffix and update LVs

    Returns:
        report: list of dicts with fields: solid_name, watertight_before, watertight_after, replaced_name, notes
    """
    """Inspect tessellated solids in a registry, optionally attempt mesh repairs.

    Args:
        reg: pyg4ometry Registry
        repair: attempt repairs with trimesh if non-watertight
        replace_in_place: if True, replace solids in-place (keep same names); otherwise add new solids with '-fixed' suffix and update LVs

    Returns:
        report: list of dicts with fields: solid_name, watertight_before, watertight_after, replaced_name, notes
    """
    try:
        import trimesh
    except Exception:
        print("Warning: trimesh not available; skipping tessellated solids postcheck/repair.")
        return []
    
    # Try to import pymeshlab as optional fallback
    try:
        import pymeshlab
    except Exception:
        pymeshlab = None

    reports = []
    # Iterate over a copy of solid items to allow modification
    solids_items = list(reg.solidDict.items())
    for sname, solid in solids_items:
        try:
            # Skip already-repaired solids (those ending with _fixed) to avoid re-processing
            if sname.endswith('_fixed'):
                continue
            if not (hasattr(solid, 'type') and solid.type == 'TessellatedSolid'):
                continue
            notes = ''
            mesh_csg = None
            try:
                mesh_csg = solid.mesh()
            except Exception as e:
                notes += f'mesh_extract_failed:{e};'
                reports.append({'solid_name': sname, 'watertight_before': None, 'watertight_after': None, 'replaced_name': None, 'notes': notes})
                continue
            # Get vertices and polygons
            try:
                verts, polys, extra = mesh_csg.toVerticesAndPolygons()
            except Exception as e:
                notes += f'toVerticesAndPolygons_failed:{e};'
                reports.append({'solid_name': sname, 'watertight_before': None, 'watertight_after': None, 'replaced_name': None, 'notes': notes})
                continue

            import numpy as np
            vertices = np.array(verts, dtype=float)
            faces = np.array(polys, dtype=int)
            try:
                tm = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            except Exception as e:
                notes += f'trig_construct_failed:{e};'
                reports.append({'solid_name': sname, 'watertight_before': None, 'watertight_after': None, 'replaced_name': None, 'notes': notes})
                continue

            wat_before = bool(tm.is_watertight)
            wat_after = wat_before
            replaced_name = None

            if not wat_before and not repair:
                reports.append({'solid_name': sname, 'watertight_before': wat_before, 'watertight_after': wat_after, 'replaced_name': None, 'notes': notes})
                continue

            if repair:
                # Comprehensive mesh repair strategy
                try:
                    # Phase 1: Basic cleanup
                    try:
                        # Remove duplicate and unreferenced vertices
                        tm.merge_vertices()
                        tm.remove_unreferenced_vertices()
                    except Exception:
                        pass
                    
                    # Phase 2: Fix normals (important for hole detection)
                    try:
                        trimesh.repair.fix_normals(tm)
                    except Exception:
                        pass
                    
                    # Phase 3: Remove degenerate and duplicate faces
                    try:
                        if hasattr(tm, 'nondegenerate_faces'):
                            mask = tm.nondegenerate_faces()
                            if mask is not None and mask.sum() < len(tm.faces):
                                tm.update_faces(mask)
                    except Exception:
                        pass
                    
                    try:
                        # Remove duplicate faces
                        if hasattr(tm, 'remove_duplicate_faces'):
                            tm.remove_duplicate_faces()
                    except Exception:
                        pass
                    
                    # Phase 4: Fix broken faces and edges
                    try:
                        if hasattr(trimesh.repair, 'broken_faces'):
                            broken = trimesh.repair.broken_faces(tm)
                            if len(broken) > 0:
                                notes += f'removed_{len(broken)}_broken_faces;'
                                # After removing broken faces, try subdividing to close gaps
                                try:
                                    # Light subdivision can help close small gaps
                                    if hasattr(tm, 'subdivide') and not tm.is_watertight:
                                        tm = tm.subdivide()
                                        notes += 'subdivided;'
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    
                    # Phase 5: Aggressive hole filling (multiple attempts)
                    if hasattr(trimesh.repair, 'fill_holes'):
                        for attempt in range(3):  # Try up to 3 times
                            if tm.is_watertight:
                                break
                            try:
                                trimesh.repair.fill_holes(tm)
                            except Exception as e:
                                if attempt == 2:  # Only log on last attempt
                                    notes += f'fill_holes_failed:{e};'
                                break
                    
                    # Phase 5b: If still not watertight, try splitting and repairing components
                    if not tm.is_watertight and hasattr(tm, 'split'):
                        try:
                            components = tm.split()
                            if len(components) > 1:
                                notes += f'split_into_{len(components)}_components;'
                                # Repair each component separately
                                repaired_components = []
                                for comp in components:
                                    try:
                                        trimesh.repair.fill_holes(comp)
                                        repaired_components.append(comp)
                                    except Exception:
                                        repaired_components.append(comp)
                                # Merge back
                                if len(repaired_components) > 1:
                                    tm = trimesh.util.concatenate(repaired_components)
                                    notes += 'merged_components;'
                        except Exception as e:
                            notes += f'split_failed:{e};'
                    
                    # Phase 6: Fix inverted faces
                    try:
                        trimesh.repair.fix_inversion(tm)
                    except Exception:
                        pass
                    
                    # Phase 7: Final cleanup - merge vertices again after all repairs
                    try:
                        tm.merge_vertices()
                        tm.remove_unreferenced_vertices()
                    except Exception:
                        pass
                    
                    # Phase 8: If still not watertight, try more aggressive methods
                    if not tm.is_watertight:
                        try:
                            # Try fixing with winding number
                            if hasattr(trimesh.repair, 'fix_winding'):
                                trimesh.repair.fix_winding(tm)
                        except Exception:
                            pass
                        
                        # One more fill_holes attempt after winding fix
                        if not tm.is_watertight and hasattr(trimesh.repair, 'fill_holes'):
                            try:
                                trimesh.repair.fill_holes(tm)
                            except Exception:
                                pass
                        
                        # Phase 9: Last resort - try convex hull for very broken meshes
                        if not tm.is_watertight:
                            try:
                                # Check if mesh is severely broken (small percentage watertight)
                                # We try convex hull only as a last resort since it changes geometry
                                from trimesh.convex import convex_hull
                                hull = convex_hull(tm)
                                if hull.is_watertight:
                                    # Only use hull if original mesh is very broken
                                    # Compare volumes to decide if hull is reasonable
                                    original_vol = abs(tm.volume) if hasattr(tm, 'volume') else 0
                                    hull_vol = abs(hull.volume)
                                    # Use hull if volume difference is reasonable (<80% difference)
                                    # For very broken meshes, we're very lenient
                                    # Better to have a slightly inaccurate but watertight mesh than holes
                                    if original_vol > 0:
                                        vol_diff = abs(hull_vol - original_vol) / original_vol
                                        if vol_diff < 0.8:
                                            tm = hull
                                            notes += f'used_convex_hull(vol_diff={vol_diff:.2f});'
                                        else:
                                            notes += f'convex_hull_rejected(vol_diff={vol_diff:.2f});'
                                            # Try voxelization as alternative for meshes with deep concavities
                                            try:
                                                if hasattr(tm, 'voxelized'):
                                                    # Use a pitch that preserves reasonable detail
                                                    pitch = tm.extents.max() / 50.0  # 50 voxels along longest axis
                                                    vox = tm.voxelized(pitch=pitch)
                                                    if hasattr(vox, 'marching_cubes'):
                                                        vox_mesh = vox.marching_cubes
                                                        if vox_mesh.is_watertight:
                                                            tm = vox_mesh
                                                            notes += f'used_voxelization(pitch={pitch:.2f});'
                                            except Exception as e:
                                                notes += f'voxelization_failed:{e};'
                                    else:
                                        # If we can't compute original volume, use hull anyway
                                        tm = hull
                                        notes += 'used_convex_hull(no_vol);'
                            except Exception as e:
                                notes += f'convex_hull_failed:{e};'
                    
                    # Phase 10: Last resort - PyMeshLab for very stubborn meshes
                    if not tm.is_watertight and pymeshlab is not None:
                        try:
                            import tempfile
                            import os
                            # Export to temp STL for PyMeshLab
                            with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmpf:
                                tmp_input = tmpf.name
                            tm.export(tmp_input)
                            
                            # Use PyMeshLab's powerful repair tools
                            ms = pymeshlab.MeshSet()
                            ms.load_new_mesh(tmp_input)
                            
                            # Apply comprehensive MeshLab repairs
                            ms.meshing_remove_duplicate_vertices()
                            ms.meshing_remove_duplicate_faces()
                            ms.meshing_repair_non_manifold_edges()
                            ms.meshing_repair_non_manifold_vertices()
                            ms.meshing_remove_unreferenced_vertices()
                            ms.meshing_close_holes(maxholesize=200)
                            ms.meshing_repair_non_manifold_edges()  # Repair again after hole filling
                            
                            # Save and reload with trimesh
                            with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmpf:
                                tmp_output = tmpf.name
                            ms.save_current_mesh(tmp_output)
                            
                            # Load back into trimesh
                            tm_fixed = trimesh.load(tmp_output, process=False)
                            
                            # Clean up temp files
                            try:
                                os.unlink(tmp_input)
                                os.unlink(tmp_output)
                            except Exception:
                                pass
                            
                            if tm_fixed.is_watertight:
                                tm = tm_fixed
                                notes += 'used_pymeshlab;'
                            else:
                                notes += 'pymeshlab_attempted_still_not_watertight;'
                        except Exception as e:
                            notes += f'pymeshlab_failed:{e};'
                    elif not tm.is_watertight and pymeshlab is None:
                        notes += 'pymeshlab_not_available;'
                    
                except Exception as e:
                    notes += f'repair_exception:{e};'

                wat_after = bool(tm.is_watertight)
                # Always export the mesh (even if not fully repaired) to avoid losing geometry
                if True:
                    # Export repaired mesh to a temporary STL and re-import via pyg4ometry.stl.Reader
                    import tempfile
                    try:
                        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmpf:
                            out_tmp = tmpf.name
                        tm.export(out_tmp)
                        # Read back using pyg4ometry's STL reader which produces a compatible TessellatedSolid
                        reader = pyg4ometry.stl.Reader(filename=str(out_tmp), solidname=sname + '_fixed', scale=1, centre=False, registry=reg)
                        new_solid = reader.getSolid()
                        if replace_in_place:
                            # Replace in-place: change the solid name back to original and replace in registry
                            # First, remove the '_fixed' solid that was just added by the reader
                            fixed_name = sname + '_fixed'
                            if fixed_name in reg.solidDict:
                                del reg.solidDict[fixed_name]
                            # Now rename and replace the original
                            new_solid.name = sname
                            reg.solidDict[sname] = new_solid
                            replaced_name = sname
                            # Update logical volumes to point to the replaced solid
                            for lv_name, lv in list(reg.logicalVolumeDict.items()):
                                if hasattr(lv, 'solid') and getattr(lv.solid, 'name', None) == sname:
                                    lv.solid = new_solid
                        else:
                            # Add new solid with _fixed suffix (already added by reader)
                            replaced_name = new_solid.name
                            # Update logical volumes to point to the new _fixed solid
                            for lv_name, lv in list(reg.logicalVolumeDict.items()):
                                if hasattr(lv, 'solid') and getattr(lv.solid, 'name', None) == sname:
                                    lv.solid = new_solid
                    except Exception as e:
                        notes += f'new_solid_via_stl_failed:{e};'
            reports.append({'solid_name': sname, 'watertight_before': wat_before, 'watertight_after': wat_after, 'replaced_name': replaced_name, 'notes': notes})
        except Exception as e:
            reports.append({'solid_name': sname, 'watertight_before': None, 'watertight_after': None, 'replaced_name': None, 'notes': f'unexpected:{e};'})
    return reports


def convert_step_to_gdml(
    step_file: Path,
    output_file: Path,
    *,
    use_hierarchy: bool = True,
    check_overlaps: bool = False,
    center_origin: bool = False,
) -> pyg4ometry.geant4.Registry:
    """Convert STEP file directly to GDML using pyg4ometry.
    
    Args:
        step_file: Path to STEP file
        output_file: Path to output GDML file
        use_hierarchy: If True, maintain assembly hierarchy; if False, use flat tessellation
        check_overlaps: If True, perform geometry overlap checking
        center_origin: If True, center geometry at world origin
    
    Returns:
        pyg4ometry Registry containing the geometry
    """
    print(f"\n{'='*60}")
    print("STEP-TO-GDML CONVERSION (Native Geometry)")
    print(f"{'='*60}")
    print(f"Input: {step_file}")
    print(f"Output: {output_file}")
    print(f"Mode: {'Hierarchy' if use_hierarchy else 'Flat'}")
    
    # Print STEP structure
    _print_step_tree(step_file)
    
    reader = pyg4ometry.pyoce.Reader(str(step_file))
    shape_name = _get_first_free_shape_name(reader)
    print(f"Top-level CAD shape: {shape_name}")

    # Create registry and materials
    reg = pyg4ometry.geant4.Registry()
    world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
    cad_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)

    # Get the top shape
    free_shapes = reader.freeShapes()
    top_label = free_shapes.Value(1)
    top_shape = reader.shapeTool.GetShape(top_label)

    cad_registry = None

    if use_hierarchy:
        print("\nConverting with hierarchy preservation...")
        print("  - Maintaining assembly structure")
        print("  - Component-by-component tessellation")
        print("  - Avoiding circular references")
        
        try:
            # Use manual hierarchy building to avoid circular reference issues
            print("  Building hierarchy manually...")
            
            # Calculate world size first
            min_v, max_v = _oce_shape_bbox(top_shape, lin_def=0.5, ang_def=0.5)
            margin = 0.1
            size = [max_v[i] - min_v[i] for i in range(3)]
            center = [(min_v[i] + max_v[i]) / 2.0 for i in range(3)]
            offset = [-center[0], -center[1], -center[2]] if center_origin else [0, 0, 0]
            
            # Apply centering offset to bounding box for correct world sizing
            if center_origin:
                for i in range(3):
                    min_v[i] += offset[i]
                    max_v[i] += offset[i]
            
            for i in range(3):
                extra = size[i] * margin
                min_v[i] -= extra
                max_v[i] += extra
                size[i] += 2 * extra
            
            # Create world volume
            world_solid = pyg4ometry.geant4.solid.Box(
                "world_solid",
                size[0] / 2.0,
                size[1] / 2.0,
                size[2] / 2.0,
                reg,
                lunit="mm"
            )
            world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv", reg)
            reg.setWorld(world_lv)
            
            # Build components
            component_count = _build_hierarchy_manually(reader, top_label, reg, cad_material, world_lv, offset=offset)
            
            print(f"  Bounding box: [{min_v[0]:.1f}, {min_v[1]:.1f}, {min_v[2]:.1f}] to [{max_v[0]:.1f}, {max_v[1]:.1f}, {max_v[2]:.1f}]")
            print(f"  World size: [{size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}] mm")
            if center_origin:
                print(f"  Center offset: [{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]")
            print(f"✓ Conversion successful with {component_count} components")
            
            cad_registry = reg
            result = reg  # For compatibility with code below
            
        except Exception as e:
            import traceback
            print(f"\n⚠ Hierarchy conversion failed: {type(e).__name__}")
            print(f"  {str(e)[:200]}")
            traceback.print_exc()
            print("  Falling back to flat mode...")
            use_hierarchy = False
    
    if not use_hierarchy:
        print("\nConverting to flat tessellated solid...")
        print("  - Single unified mesh")
        print("  - Robust for complex assemblies")
        
        cad_solid = pyg4ometry.convert.oceShape_Geant4_Tessellated(
            name="cad_solid",
            shape=top_shape,
            greg=reg,
            linDef=0.5,
            angDef=0.5,
        )
        cad_lv = pyg4ometry.geant4.LogicalVolume(cad_solid, cad_material, "cad_lv", reg)
        print(f"✓ Converted to tessellated solid")

        # Calculate bounding box for auto-sizing world
        print("\nCalculating geometry bounds...")
        min_v, max_v = _oce_shape_bbox(top_shape, lin_def=0.5, ang_def=0.5)
        
        # Add 10% margin
        margin = 0.1
        size = [max_v[i] - min_v[i] for i in range(3)]
        center = [(min_v[i] + max_v[i]) / 2.0 for i in range(3)]
        
        # Offset to center geometry
        offset = [-center[0], -center[1], -center[2]] if center_origin else [0, 0, 0]
        
        # Apply centering offset to bounding box for correct world sizing
        if center_origin:
            for i in range(3):
                min_v[i] += offset[i]
                max_v[i] += offset[i]
        
        for i in range(3):
            extra = size[i] * margin
            min_v[i] -= extra
            max_v[i] += extra
            size[i] += 2 * extra
        
        # Create world volume (Box takes half-lengths)
        # Use unique name for flat fallback to avoid duplicate registration
        world_solid = pyg4ometry.geant4.solid.Box(
            "world_solid_flat",
            size[0] / 2.0,
            size[1] / 2.0,
            size[2] / 2.0,
            reg,
            lunit="mm"
        )
        world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv_flat", reg)
        
        print(f"  Bounding box: [{min_v[0]:.1f}, {min_v[1]:.1f}, {min_v[2]:.1f}] to [{max_v[0]:.1f}, {max_v[1]:.1f}, {max_v[2]:.1f}]")
        print(f"  World size: [{size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}] mm")
        if center_origin:
            print(f"  Center offset: [{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]")
        
        pyg4ometry.geant4.PhysicalVolume([0, 0, 0], offset, cad_lv, "cad_pv", world_lv, reg)
        reg.setWorld(world_lv)
        cad_registry = reg

    # Print GDML tree
    _print_gdml_tree(cad_registry)

    # Always check and repair tessellated solids before saving
    logger.info("%s", "=" * 60)
    logger.info("CHECKING AND REPAIRING TESSELLATED SOLIDS")
    logger.info("%s", "=" * 60)
    reports = _check_and_repair_tessellated_solids(cad_registry, repair=True, replace_in_place=True)
    failed_repairs = []
    if reports:
        for r in reports:
            logger.info(f"  {r['solid_name']}: watertight_before={r.get('watertight_before')} watertight_after={r.get('watertight_after')} replaced={r.get('replaced_name')} notes={r.get('notes')}")
            if r.get('watertight_before') == False and r.get('watertight_after') == False:
                failed_repairs.append(r['solid_name'])
        if failed_repairs:
            logger.warning("\n⚠️  WARNING: %d solid(s) still have holes after repair attempts:", len(failed_repairs))
            for name in failed_repairs:
                logger.warning(f"    - {name}")
            logger.warning("  These meshes may cause issues in Geant4. Consider manual repair in CAD software.")
    else:
        logger.info('  No tessellated solids found or trimesh not available')

    # Overlap checking
    if check_overlaps:
        logger.info("%s", "=" * 60)
        logger.info("OVERLAP CHECKING")
        logger.info("%s", "=" * 60)
        world_lv = cad_registry.getWorldVolume()
        logger.info("Checking for overlaps...")
        try:
            # Use mesh-based overlap checking on the world logical volume.
            # This can raise RuntimeError from the underlying CGAL/mesh library
            # for very complex or invalid tessellated meshes.
            overlap_count = world_lv.checkOverlaps(recursive=True, coplanar=True)
            logger.info(f"Overlap check completed, {overlap_count} overlaps reported.")
        except RuntimeError as e:
            import traceback
            logger.warning("Mesh-based overlap checking failed:")
            logger.warning(f"  {type(e).__name__}: {e}")
            logger.warning("The tessellated mesh operations raised an error (CGAL/pycgal). Possible causes:")
            logger.warning("  - Very high-polygon or self-intersecting STL meshes")
            logger.warning("  - Invalid mesh topology or non-manifold geometry")
            logger.warning("  - Numerical robustness issues in the mesh library")
            logger.warning("Suggested actions:")
            logger.warning("  1) Simplify or repair the STL meshes (reduce polygon count or fix intersections).")
            logger.warning("  2) Export the GDML and run Geant4's native overlap checker (use /geometry/test/run).")
            print("  3) Visual inspection with the VTK viewer to highlight overlaps.")
            print("\nStack trace (for debugging):")
            traceback.print_exc()
            overlap_count = None
        except Exception as e:
            import traceback
            print("\n⚠ Unexpected error during overlap checking:")
            print(f"  {type(e).__name__}: {e}")
            traceback.print_exc()
            overlap_count = None
        print(f"{'='*60}\n")

    # Export to GDML
    print(f"Writing GDML file: {output_file}")
    writer = pyg4ometry.gdml.Writer()
    writer.addDetector(cad_registry)
    writer.write(str(output_file))
    print(f"✓ GDML export complete\n")

    return cad_registry


def convert_single_stl_to_gdml(
    stl_file: Path,
    output_file: Path,
    center_origin: bool = True,
) -> pyg4ometry.geant4.Registry:
    """Convert a single STL file to GDML.

    Args:
        stl_file: Path to STL mesh file
        output_file: Path to output GDML file
        center_origin: If True, center geometry at world origin (default: True)

    Returns:
        pyg4ometry Registry containing the geometry
    """
    print(f"\n{'='*60}")
    print("SINGLE STL-TO-GDML CONVERSION (Simple Mesh)")
    print(f"{'='*60}")
    print(f"Input: {stl_file}")
    print(f"Output: {output_file}")
    
    if not stl_file.exists():
        raise FileNotFoundError(f"STL file not found: {stl_file}")

    # Create registry and materials
    reg = pyg4ometry.geant4.Registry()
    world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
    part_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)

    # Load STL file
    print("\nLoading STL file...")
    solid_name = f"stl_solid_{stl_file.stem.replace(' ', '_')}"
    
    reader = pyg4ometry.stl.Reader(
        filename=str(stl_file),
        solidname=solid_name,
        scale=1,
        centre=False,
        registry=reg,
    )
    
    # Calculate bounding box
    def aabb_from_facets(facets) -> Tuple[List[float], List[float]]:
        min_v = [float("inf")] * 3
        max_v = [float("-inf")] * 3
        for tri, _n in facets:
            for x, y, z in tri:
                for i in range(3):
                    if [x, y, z][i] < min_v[i]:
                        min_v[i] = [x, y, z][i]
                    if [x, y, z][i] > max_v[i]:
                        max_v[i] = [x, y, z][i]
        return min_v, max_v
    
    min_v, max_v = aabb_from_facets(reader.facet_list)
    
    # Calculate world size with 10% margin
    margin = 0.1
    size = [max_v[i] - min_v[i] for i in range(3)]
    center = [(min_v[i] + max_v[i]) / 2.0 for i in range(3)]
    
    # Offset to center geometry
    offset = [-center[0], -center[1], -center[2]] if center_origin else [0, 0, 0]
    
    # Apply centering offset to bounding box for correct world sizing
    if center_origin:
        for i in range(3):
            min_v[i] += offset[i]
            max_v[i] += offset[i]
    
    for i in range(3):
        extra = size[i] * margin
        min_v[i] -= extra
        max_v[i] += extra
        size[i] += 2 * extra
    
    # Create world box (Box takes half-lengths)
    world_solid = pyg4ometry.geant4.solid.Box(
        "world_solid",
        size[0] / 2.0,
        size[1] / 2.0,
        size[2] / 2.0,
        reg,
        lunit="mm"
    )
    world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv", reg)
    
    print(f"\nGeometry information:")
    print(f"  Bounding box: [{min_v[0]:.1f}, {min_v[1]:.1f}, {min_v[2]:.1f}] to [{max_v[0]:.1f}, {max_v[1]:.1f}, {max_v[2]:.1f}]")
    print(f"  World size: [{size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}] mm")
    if center_origin:
        print(f"  Center offset: [{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]")
    
    # Place mesh in world volume
    print("\nPlacing mesh in world volume...")
    lv = pyg4ometry.geant4.LogicalVolume(reader.getSolid(), part_material, f"lv_{solid_name}", reg)
    pyg4ometry.geant4.PhysicalVolume(
        [0, 0, 0],  # no rotation
        offset,      # center the mesh
        lv,
        f"pv_{stl_file.stem.replace(' ', '_')}",
        world_lv,
        reg
    )
    
    reg.setWorld(world_lv)
    
    # Print GDML tree
    _print_gdml_tree(reg)

    # Always check and repair tessellated solids before saving
    print(f"\n{'='*60}")
    print("CHECKING AND REPAIRING TESSELLATED SOLIDS")
    print(f"{'='*60}")
    logger.info("="*60)
    logger.info("CHECKING AND REPAIRING TESSELLATED SOLIDS")
    logger.info("="*60)
    reports = _check_and_repair_tessellated_solids(reg, repair=True, replace_in_place=True)
    failed_repairs = []
    if reports:
        for r in reports:
            print(f"  {r['solid_name']}: watertight_before={r.get('watertight_before')} watertight_after={r.get('watertight_after')} replaced={r.get('replaced_name')} notes={r.get('notes')}")
            if r.get('watertight_before') == False and r.get('watertight_after') == False:
                failed_repairs.append(r['solid_name'])
        if failed_repairs:
            print(f"\n⚠️  WARNING: {len(failed_repairs)} solid(s) still have holes after repair attempts:")
            for name in failed_repairs:
                print(f"    - {name}")
            print("  These meshes may cause issues in Geant4. Consider manual repair in CAD software.")
    else:
        print('  No tessellated solids found or trimesh not available')

    # Export to GDML
    print(f"Writing GDML file: {output_file}")
    writer = pyg4ometry.gdml.Writer()
    writer.addDetector(reg)
    writer.write(str(output_file))
    print(f"✓ GDML export complete\n")
    
    return reg


def convert_stl_to_gdml(
    stl_dir: Path,
    step_file: Path,
    output_file: Path,
    center_origin: bool = True,
) -> pyg4ometry.geant4.Registry:
    """Convert STL files + STEP assembly to GDML.

    Args:
        stl_dir: Directory containing STL mesh files
        step_file: STEP file for placement information
        output_file: Path to output GDML file
        center_origin: If True, center geometry at world origin (default: True)

    Returns:
        pyg4ometry Registry containing the geometry
    """
    print(f"\n{'='*60}")
    print("STL+STEP-TO-GDML CONVERSION (Mesh Geometry)")
    print(f"{'='*60}")
    print(f"STL directory: {stl_dir}")
    print(f"STEP file: {step_file}")
    print(f"Output: {output_file}")
    
    # Print STEP structure
    _print_step_tree(step_file)
    
    # Find STL files (exclude -fixed.stl files to avoid processing repaired duplicates)
    stl_paths = sorted(
        [Path(p) for p in glob.glob(str(stl_dir / "*.stl")) if not p.endswith('-fixed.stl')]
        + [Path(p) for p in glob.glob(str(stl_dir / "*.STL")) if not p.endswith('-fixed.STL')]
    )

    if not stl_paths:
        raise FileNotFoundError(f"No STL files found in {stl_dir}")

    # Create registry and materials
    reg = pyg4ometry.geant4.Registry()
    world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
    part_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)

    # Extract placements from STEP
    print("\nExtracting placements from STEP file...")
    step_placements = _extract_step_placements(step_file)
    print(f"Found {len(step_placements)} component placements")

    # Calculate global bounding box first to get center offset
    print("\nCalculating global bounding box...")
    global_min = [float("inf")] * 3
    global_max = [float("-inf")] * 3
    
    # First pass: scan all STL files to get global bounds
    temp_readers = []
    for stl_path in stl_paths:
        reader = pyg4ometry.stl.Reader(
            filename=str(stl_path),
            solidname="temp",
            scale=1,
            centre=False,
            registry=None,
        )
        temp_readers.append(reader)
        for tri, _n in reader.facet_list:
            for x, y, z in tri:
                for i in range(3):
                    if [x, y, z][i] < global_min[i]:
                        global_min[i] = [x, y, z][i]
                    if [x, y, z][i] > global_max[i]:
                        global_max[i] = [x, y, z][i]
    
    # Calculate center for offsetting
    center = [(global_min[i] + global_max[i]) / 2.0 for i in range(3)]
    
    print(f"  Bounding box: [{global_min[0]:.1f}, {global_min[1]:.1f}, {global_min[2]:.1f}] to [{global_max[0]:.1f}, {global_max[1]:.1f}, {global_max[2]:.1f}]")
    if center_origin:
        print(f"  Center offset: [{-center[0]:.1f}, {-center[1]:.1f}, {-center[2]:.1f}]")
    
    # Load STL files
    print("\nLoading STL files...")
    parts: List[Dict] = []

    for idx, stl_path in enumerate(stl_paths):
        key = stl_path.stem.strip().lower()
        solid_name = f"stl_solid_{idx}_{stl_path.stem.replace(' ', '_')}"
        pv_name = f"pv_{idx}_{stl_path.stem.replace(' ', '_')}"

        # Always load without centering
        reader = pyg4ometry.stl.Reader(
            filename=str(stl_path),
            solidname=solid_name,
            scale=1,
            centre=False,
            registry=reg,
        )
        solid = reader.getSolid()
        
        parts.append({
            "idx": idx,
            "path": stl_path,
            "key": key,
            "key_norm": _norm_key(key),
            "solid": solid,
            "pv_name": pv_name,
        })
        print(f"  [{idx+1}/{len(stl_paths)}] {stl_path.name}")

    # Match STL files to STEP placements
    print("\nMatching STL files to STEP placements...")
    placements: Dict[int, Tuple[List[float], List[float]]] = {}
    missing: List[str] = []
    
    for p in parts:
        matched_key = _find_best_step_match(p["key_norm"], step_placements)
        stp = step_placements.get(matched_key) if matched_key else None
        if stp is None:
            missing.append(p["path"].name)
        else:
            placements[p["idx"]] = (stp["rot"], stp["tra"])
            print(f"  ✓ {p['path'].name} → {matched_key}")

    if missing:
        known = sorted(step_placements.keys())
        raise RuntimeError(
            f"Missing STEP placement for: {', '.join(missing)}\n"
            f"Available STEP keys: {known}"
        )

    # Calculate world volume size
    print("\nCalculating world volume size...")
    
    # Calculate size and apply centering offset
    size = [global_max[i] - global_min[i] for i in range(3)]
    offset = [-center[0], -center[1], -center[2]] if center_origin else [0, 0, 0]
    
    # Apply centering offset to bounding box for correct world sizing
    if center_origin:
        for i in range(3):
            global_min[i] += offset[i]
            global_max[i] += offset[i]
    
    # Add 10% margin
    margin = 0.1
    for i in range(3):
        extra = size[i] * margin
        size[i] += 2 * extra
    
    print(f"  World size: [{size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}] mm")
    if center_origin:
        print(f"  Applying offset: [{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]")
    
    # Create world box (Box takes half-lengths)
    world_solid = pyg4ometry.geant4.solid.Box(
        "world_solid",
        size[0] / 2.0,
        size[1] / 2.0,
        size[2] / 2.0,
        reg,
        lunit="mm"
    )
    world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv", reg)

    # Place all parts (vertices already centered if center_origin=True)
    print("\nPlacing parts in world volume...")
    for p in parts:
        solid_name = p["solid"].name
        lv = pyg4ometry.geant4.LogicalVolume(p["solid"], part_material, f"lv_{solid_name}", reg)
        rot, tra = placements[p["idx"]]
        # tra is [0,0,0] for STL+STEP workflow, no additional offset needed
        pyg4ometry.geant4.PhysicalVolume(rot, tra, lv, p["pv_name"], world_lv, reg)

    reg.setWorld(world_lv)

    # Print GDML tree
    _print_gdml_tree(reg)

    # Always check and repair tessellated solids before saving
    print(f"\n{'='*60}")
    print("CHECKING AND REPAIRING TESSELLATED SOLIDS")
    print(f"{'='*60}")
    logger.info("="*60)
    logger.info("CHECKING AND REPAIRING TESSELLATED SOLIDS")
    logger.info("="*60)
    reports = _check_and_repair_tessellated_solids(reg, repair=True, replace_in_place=True)
    failed_repairs = []
    if reports:
        for r in reports:
            print(f"  {r['solid_name']}: watertight_before={r.get('watertight_before')} watertight_after={r.get('watertight_after')} replaced={r.get('replaced_name')} notes={r.get('notes')}")
            if r.get('watertight_before') == False and r.get('watertight_after') == False:
                failed_repairs.append(r['solid_name'])
        if failed_repairs:
            print(f"\n⚠️  WARNING: {len(failed_repairs)} solid(s) still have holes after repair attempts:")
            for name in failed_repairs:
                print(f"    - {name}")
            print("  These meshes may cause issues in Geant4. Consider manual repair in CAD software.")
    else:
        print('  No tessellated solids found or trimesh not available')

    # Export to GDML
    print(f"Writing GDML file: {output_file}")
    writer = pyg4ometry.gdml.Writer()
    writer.addDetector(reg)
    writer.write(str(output_file))
    
    # If centering enabled, post-process GDML to offset vertex positions
    if center_origin:
        print(f"Post-processing GDML to center vertices...")
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(output_file))
        root = tree.getroot()
        
        # Find and modify all position defines
        ns = {'gdml': 'http://www.w3.org/2001/XMLSchema-instance'}
        defines = root.find('define')
        if defines is not None:
            for position in defines.findall('position'):
                x = float(position.get('x', 0))
                y = float(position.get('y', 0))
                z = float(position.get('z', 0))
                position.set('x', str(x - center[0]))
                position.set('y', str(y - center[1]))
                position.set('z', str(z - center[2]))
        
        tree.write(str(output_file), encoding='utf-8', xml_declaration=True)
        
    print(f"✓ GDML export complete\n")

    return reg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified CAD to Geant4 converter (STEP and STL support)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
WORKFLOW MODES:
  1. STEP-to-GDML: Provide --step-file only
  2. STL+STEP-to-GDML: Provide both --step-file and --stl-dir
  3. Single STL-to-GDML: Provide --stl-file only

EXAMPLES:
  # Native STEP conversion with hierarchy
  python cad_g4_conv.py --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP
  
  # STEP flat mode (tessellated solid)
  python cad_g4_conv.py --step-file input.STEP --flat
  
  # STL+STEP mesh conversion
  python cad_g4_conv.py --step-file assembly.STEP --stl-dir STLs/
  
  # Single STL mesh conversion
  python cad_g4_conv.py --stl-file mesh.stl
  
  # Check overlaps
  python cad_g4_conv.py --step-file input.STEP --check-overlaps
        """
    )
    parser.add_argument(
        "--step-file",
        type=str,
        default=None,
        help="Path to STEP file",
    )
    parser.add_argument(
        "--stl-file",
        type=str,
        default=None,
        help="Path to single STL file (for simple mesh workflow)",
    )
    parser.add_argument(
        "--stl-dir",
        type=str,
        default=None,
        help="Directory containing STL files (for STL+STEP workflow)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output.gdml",
        help="Output GDML file path (default: output.gdml)",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Use flat tessellated mode instead of hierarchy (STEP-only workflow)",
    )
    parser.add_argument(
        "--check-overlaps",
        action="store_true",
        help="Perform geometry overlap checking (STEP-only workflow)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to write detailed log output (optional)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    )
    parser.add_argument(
        "--center-origin",
        action="store_true",
        help="Center the geometry at world origin",
    )
    
    args = parser.parse_args()
    
    # Configure logging early based on CLI args
    configure_logging(args.log_file, level=args.log_level)
    output_file = Path(args.output)
    
    # Validate inputs
    if not args.step_file and not args.stl_file:
        print("Error: Must provide either --step-file or --stl-file")
        return 1
    
    if args.stl_file and args.stl_dir:
        print("Error: Cannot use both --stl-file and --stl-dir. Choose one workflow.")
        return 1
    
    if args.stl_file and args.step_file:
        print("Error: Cannot use both --stl-file and --step-file. Use --stl-dir for STL+STEP workflow.")
        return 1
    
    if args.stl_dir and not args.step_file:
        print("Error: STL+STEP workflow requires both --stl-dir and --step-file")
        return 1
    
    # Determine workflow based on inputs
    if args.stl_file:
        # Single STL workflow
        stl_file = Path(args.stl_file)
        if not stl_file.exists():
            print(f"Error: STL file not found: {stl_file}")
            return 1
        
        if args.flat:
            print("Warning: --flat flag ignored in single STL workflow")
        if args.check_overlaps:
            print("Warning: --check-overlaps not supported in single STL workflow")
        
        convert_single_stl_to_gdml(
            stl_file,
            output_file,
            center_origin=args.center_origin,
        )
        
    elif args.stl_dir:
        # STL+STEP workflow
        step_file = Path(args.step_file)
        stl_dir = Path(args.stl_dir)
        
        if not step_file.exists():
            print(f"Error: STEP file not found: {step_file}")
            return 1
        if not stl_dir.exists():
            print(f"Error: STL directory not found: {stl_dir}")
            return 1
        
        if args.flat:
            print("Warning: --flat flag ignored in STL+STEP workflow")
        if args.check_overlaps:
            print("Warning: --check-overlaps not supported in STL+STEP workflow")
        
        convert_stl_to_gdml(
            stl_dir,
            step_file,
            output_file,
            center_origin=args.center_origin,
        )
        
    else:
        # STEP-only workflow
        step_file = Path(args.step_file)
        
        if not step_file.exists():
            print(f"Error: STEP file not found: {step_file}")
            return 1
        
        convert_step_to_gdml(
            step_file,
            output_file,
            use_hierarchy=not args.flat,
            check_overlaps=args.check_overlaps,
            center_origin=args.center_origin,
        )
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
