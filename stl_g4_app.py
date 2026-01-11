#!/usr/bin/env python3
"""Geant4 (geant4_pybind) app that builds geometry from STL files and visualizes it.

Important:
- The STL import is done via `pyg4ometry` (installed in this workspace).
  There is no importable Python module named `pyg4geometry` in this env.
- Visualization is done with Geant4 visualization drivers (default macro uses
  VRML2FILE to create `g4_00.wrl`).

Usage:
  python stl_g4_app.py                 # builds GDML from CAD_files/*.STL and runs stl_vis.mac
  python stl_g4_app.py -m vis.mac      # run a different macro
  python stl_g4_app.py --stl-dir path/to/stls --step-file path/to/file.STEP --gdml-out output.gdml
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import io
import os
from pathlib import Path
from typing import Dict, List, Tuple

from geant4_pybind import *


def build_gdml_from_stls(stl_dir: Path, gdml_out: Path, *, step_file: Path | None = None) -> None:
    # pyg4ometry imports VTK-based visualisation by default; suppress its stderr noise.
    with contextlib.redirect_stderr(io.StringIO()):
        import pyg4ometry

    stl_paths = sorted(
        [Path(p) for p in glob.glob(str(stl_dir / "*.stl"))]
        + [Path(p) for p in glob.glob(str(stl_dir / "*.STL"))]
    )

    if not stl_paths:
        raise FileNotFoundError(f"No STL files found in {stl_dir} (expected *.stl or *.STL)")

    reg = pyg4ometry.geant4.Registry()

    world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
    part_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)

    # World box will be sized after loading all STL parts
    # Placeholder - will be updated later
    world_solid = None
    world_lv = None

    def _norm_key(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    def _axis_angle_to_matrix(axis: List[float], angle: float) -> List[List[float]]:
        # Rodrigues' rotation formula
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
        # Solve for angles (rx, ry, rz) such that:
        #   R = Rz(rz) * Ry(ry) * Rx(rx)
        # This matches Geant4 GDML's common convention:
        #   rot.rotateX(x); rot.rotateY(y); rot.rotateZ(z)
        import math

        r20 = m[2][0]
        r21 = m[2][1]
        r22 = m[2][2]
        r10 = m[1][0]
        r00 = m[0][0]

        # Clamp for numeric safety
        sy = -max(-1.0, min(1.0, r20))
        ry = math.asin(sy)
        cy = math.cos(ry)

        if abs(cy) < 1e-12:
            # Gimbal lock: choose rz = 0 and solve rx from remaining terms
            rz = 0.0
            rx = math.atan2(-m[0][1], m[1][1])
            return [rx, ry, rz]

        rx = math.atan2(r21, r22)
        rz = math.atan2(r10, r00)
        return [rx, ry, rz]

    def _mat_vec(m: List[List[float]], v: List[float]) -> List[float]:
        return [
            m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
        ]

    def _oce_shape_bbox(shape, *, lin_def: float = 0.5, ang_def: float = 0.5) -> Tuple[List[float], List[float]]:
        # Compute an approximate bounding box by meshing the B-Rep and scanning triangulation nodes.
        # We use this to infer the local-coordinate shift applied by STL exports and to
        # compute a reasonable pivot for local-frame corrections.
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

    def _extract_step_placements(step_path: Path) -> Dict[str, Tuple[List[float], List[float]]]:
        """Extract part placements from STEP assembly.
        
        Strategy:
        1. First get direct children following pyg4ometry's oce2Geant4.py approach
        2. For parts that need rotation (like Top Tray), check recursive components
           and prefer rotated occurrences if they exist
        
        This handles STEP files where the assembly structure doesn't properly
        encode all component orientations at the top level.
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

        placements: Dict[str, Tuple[List[float], List[float]]] = {}
        bbox_cache: Dict[str, Tuple[List[float], List[float]]] = {}
        all_occurrences: Dict[str, List[Dict]] = {}

        def _extract_transform(comp_label):
            """Extract transform from a component.
            
            Returns raw STEP data without computing final placement yet.
            Final placement will be computed based on whether rotation is needed.
            """
            child_shape = st.GetShape(comp_label)
            child_loc = child_shape.Location()
            trsf = child_loc.Transformation()
            
            # Extract translation (raw STEP value)
            tp = trsf.TranslationPart()
            step_tra = [float(tp.X()), float(tp.Y()), float(tp.Z())]
            
            # Extract rotation using GetRotation (axis-angle)
            axis_out = pyg4ometry.pyoce.gp.gp_XYZ()
            angle_out = 0.0
            ok, axis_out, angle_out = trsf.GetRotation(axis_out, angle_out)
            
            if ok and abs(angle_out) > 1e-12:
                axis_v = [float(axis_out.X()), float(axis_out.Y()), float(axis_out.Z())]
                angle_val = float(angle_out)
                m_step = _axis_angle_to_matrix(axis_v, angle_val)
                ang_abs = abs(angle_val)
            else:
                m_step = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
                axis_v = [0.0, 0.0, 1.0]
                angle_val = 0.0
                ang_abs = 0.0
            
            # Get part name from referred shape if this is a reference
            if st.IsReference(comp_label):
                ref_label = pyg4ometry.pyoce.TDF.TDF_Label()
                st.GetReferredShape(comp_label, ref_label)
                part_name = label_name(ref_label)
                ref_shape = st.GetShape(ref_label)
            else:
                part_name = label_name(comp_label)
                ref_shape = child_shape
            
            if not part_name:
                return None
            
            keyn = _norm_key(part_name)
            
            # Compute bbox from the referred shape (unplaced geometry)
            if keyn not in bbox_cache:
                bbox_cache[keyn] = _oce_shape_bbox(ref_shape)
            
            bbox_min, bbox_max = bbox_cache[keyn]
            
            # Convert to Euler angles following pyg4ometry's convention (use -angle)
            rot = pyg4ometry.transformation.axisangle2tbxyz(axis_v, -angle_val)
            rot = [float(rot[0]), float(rot[1]), float(rot[2])]
            
            return {
                "keyn": keyn,
                "rot": rot,
                "step_tra": step_tra,  # Raw STEP translation
                "m": m_step,
                "axis_v": axis_v,
                "angle_val": angle_val,
                "angle_abs": ang_abs,
                "bbox_min": bbox_min,
                "bbox_max": bbox_max,
            }

        # Collect all occurrences from both direct and recursive traversal
        # Direct children
        if st.IsAssembly(root):
            for i in range(1, root.NbChildren() + 1):
                found, child = root.FindChild(i, False)
                if found:
                    data = _extract_transform(child)
                    if data:
                        all_occurrences.setdefault(data["keyn"], []).append(data)
        
        # Also check recursive components (expand=True) to find rotated variants
        seq = pyg4ometry.pyoce.TDF.TDF_LabelSequence()
        st.GetComponents(root, seq, True)
        for i in range(1, seq.Size() + 1):
            comp = seq.Value(i)
            data = _extract_transform(comp)
            if data:
                # Avoid exact duplicates (check step_tra and angle)
                keyn = data["keyn"]
                if not any(
                    abs(o["step_tra"][0] - data["step_tra"][0]) < 0.001
                    and abs(o["step_tra"][1] - data["step_tra"][1]) < 0.001
                    and abs(o["step_tra"][2] - data["step_tra"][2]) < 0.001
                    and abs(o["angle_abs"] - data["angle_abs"]) < 0.01
                    for o in all_occurrences.get(keyn, [])
                ):
                    all_occurrences.setdefault(keyn, []).append(data)
        
        # Compute final placements for each part
        # Note: Our STL files are already in world (assembly) coordinates.
        # They were exported from the STEP assembly with all transformations applied.
        # Therefore, we should place them at origin with no rotation.
        for keyn, occs in all_occurrences.items():
            if not occs:
                continue
            
            # All STL files use identity transformation (already in world coords)
            placements[keyn] = {
                "type": "identity",
                "rot": [0.0, 0.0, 0.0],
                "tra": [0.0, 0.0, 0.0],
            }


        return placements

    if step_file is None:
        raise ValueError("STEP-only placement requested: --step-file must be provided")
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    step_placements: Dict[str, Tuple[List[float], List[float]]] = _extract_step_placements(step_file)
    if not step_placements:
        raise RuntimeError(f"No component placements extracted from STEP file: {step_file}")

    def aabb_from_facets(facets) -> Tuple[List[float], List[float]]:
        # facets: [((p0,p1,p2), normal), ...], points are (x,y,z)
        min_v = [float("inf"), float("inf"), float("inf")]
        max_v = [float("-inf"), float("-inf"), float("-inf")]
        for tri, _n in facets:
            for x, y, z in tri:
                if x < min_v[0]:
                    min_v[0] = x
                if y < min_v[1]:
                    min_v[1] = y
                if z < min_v[2]:
                    min_v[2] = z
                if x > max_v[0]:
                    max_v[0] = x
                if y > max_v[1]:
                    max_v[1] = y
                if z > max_v[2]:
                    max_v[2] = z
        return min_v, max_v

    def size_from_aabb(min_v: List[float], max_v: List[float]) -> List[float]:
        return [max_v[0] - min_v[0], max_v[1] - min_v[1], max_v[2] - min_v[2]]

    def center_from_aabb(min_v: List[float], max_v: List[float]) -> List[float]:
        return [(min_v[0] + max_v[0]) / 2.0, (min_v[1] + max_v[1]) / 2.0, (min_v[2] + max_v[2]) / 2.0]

    # Load STL meshes first so we can compute placements.
    parts: List[Dict] = []
    for idx, stl_path in enumerate(stl_paths):
        key = stl_path.stem.strip().lower()
        solid_name = f"stl_solid_{idx}_{stl_path.stem.replace(' ', '_')}"
        pv_name = f"pv_{idx}_{stl_path.stem.replace(' ', '_')}"

        reader = pyg4ometry.stl.Reader(
            filename=str(stl_path),
            solidname=solid_name,
            scale=1,
            centre=False,
            registry=reg,
        )
        min_v, max_v = aabb_from_facets(reader.facet_list)
        parts.append(
            {
                "idx": idx,
                "path": stl_path,
                "key": key,
                "key_norm": _norm_key(key),
                "solid": reader.getSolid(),
                "pv_name": pv_name,
                "aabb_min": min_v,
                "aabb_max": max_v,
                "size": size_from_aabb(min_v, max_v),
                "center": center_from_aabb(min_v, max_v),
            }
        )

    # Smart matching function to find best STEP placement for STL file
    def find_best_step_match(stl_key_norm: str, step_placements: Dict) -> str | None:
        """Find best matching STEP key for STL file.
        
        Strategy:
        1. Try exact match first
        2. Try fuzzy matching by finding STEP key that is a substring of STL key
        3. Try reverse: STL key contains STEP key
        """
        # Exact match
        if stl_key_norm in step_placements:
            return stl_key_norm
        
        # Find STEP keys that appear in the STL key (longest first)
        candidates = []
        for step_key in step_placements.keys():
            if step_key in stl_key_norm:
                candidates.append((step_key, len(step_key)))
        
        if candidates:
            # Return longest matching key
            return max(candidates, key=lambda x: x[1])[0]
        
        return None

    placements: Dict[int, Tuple[List[float], List[float]]] = {}
    missing: List[str] = []
    for p in parts:
        matched_key = find_best_step_match(p["key_norm"], step_placements)
        stp = step_placements.get(matched_key) if matched_key else None
        if stp is None:
            missing.append(p["path"].name)
        else:
            # STL files are not normalized - they keep original CAD coordinates
            # So we just use STEP translation and rotation directly
            placements[p["idx"]] = (stp["rot"], stp["tra"])

    if missing:
        known = sorted(step_placements.keys())
        raise RuntimeError(
            "Missing STEP placement(s) for STL file(s): "
            + ", ".join(missing)
            + ".\n"
            + "STEP-only mode requires a name match between STL stems and STEP component names.\n"
            + f"Extracted STEP part keys: {known}"
        )

    # Calculate world size from all STL bounding boxes
    global_min = [float('inf')] * 3
    global_max = [float('-inf')] * 3
    
    for p in parts:
        for i in range(3):
            global_min[i] = min(global_min[i], p["aabb_min"][i])
            global_max[i] = max(global_max[i], p["aabb_max"][i])
    
    # Add 10% margin on each side
    margin = 0.1
    size = [global_max[i] - global_min[i] for i in range(3)]
    center = [(global_min[i] + global_max[i]) / 2.0 for i in range(3)]
    
    for i in range(3):
        extra = size[i] * margin
        global_min[i] -= extra
        global_max[i] += extra
        size[i] += 2 * extra
    
    # Create world box (pyg4ometry Box takes half-lengths)
    world_solid = pyg4ometry.geant4.solid.Box(
        "world_solid",
        size[0] / 2.0,  # half-length in X
        size[1] / 2.0,  # half-length in Y
        size[2] / 2.0,  # half-length in Z
        reg,
        lunit="mm"
    )
    world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv", reg)
    
    # Offset all parts by the center of the bounding box
    # Since world box is centered at origin, we need to shift everything
    offset = [-center[0], -center[1], -center[2]]
    
    print(f"\nWorld volume:")
    print(f"  Bounding box: [{global_min[0]:.1f}, {global_min[1]:.1f}, {global_min[2]:.1f}] to [{global_max[0]:.1f}, {global_max[1]:.1f}, {global_max[2]:.1f}]")
    print(f"  Size: [{size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}] mm")
    print(f"  Center: [{center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}]")
    print(f"  Offset applied: [{offset[0]:.1f}, {offset[1]:.1f}, {offset[2]:.1f}]\n")

    for p in parts:
        solid_name = p["solid"].name
        lv = pyg4ometry.geant4.LogicalVolume(p["solid"], part_material, f"lv_{solid_name}", reg)
        rot, tra = placements[p["idx"]]
        # Apply offset to center everything in world volume
        tra_offset = [tra[i] + offset[i] for i in range(3)]
        pyg4ometry.geant4.PhysicalVolume(rot, tra_offset, lv, p["pv_name"], world_lv, reg)

    reg.setWorld(world_lv)

    writer = pyg4ometry.gdml.Writer()
    writer.addDetector(reg)
    writer.write(str(gdml_out))
    
    # Print GDML structure tree
    def _print_gdml_tree(reg) -> None:
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
    
    _print_gdml_tree(reg)


class GDMLDetectorConstruction(G4VUserDetectorConstruction):
    def __init__(self, gdml_file: str):
        super().__init__()
        self._parser = G4GDMLParser()
        self._parser.Read(gdml_file, False)

    def Construct(self):
        return self._parser.GetWorldVolume()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build geometry from STL files and visualize via Geant4 drivers")
    parser.add_argument(
        "--stl-dir",
        type=str,
        default="CAD_files",
        help="Directory containing STL files (default: CAD_files)",
    )
    parser.add_argument(
        "--step-file",
        type=str,
        default="CAD_files/Stacked Trays.STEP",
        help="STEP assembly file to extract component displacements/rotations (default: CAD_files/Stacked Trays.STEP)",
    )
    parser.add_argument(
        "--gdml-out",
        type=str,
        default="stl_output.gdml",
        help="Path to write generated GDML file (default: stl_output.gdml)",
    )
    parser.add_argument("-m", "--macro", default="stl_vis.mac", help="Geant4 macro to execute")
    parser.add_argument("--visualize", action="store_true", help="Enable Geant4 visualization (disabled by default)")
    args = parser.parse_args()

    stl_dir = Path(args.stl_dir)
    gdml_out = Path(args.gdml_out)
    step_file = Path(args.step_file)

    print(f"Building GDML from STL files in: {stl_dir}")
    
    # Print STEP structure tree
    if step_file and step_file.exists():
        # Import here to avoid noise if not needed
        with contextlib.redirect_stderr(io.StringIO()):
            import pyg4ometry
        
        def _print_step_tree_wrapper(step_path: Path) -> None:
            """Print STEP file structure tree."""
            reader = pyg4ometry.pyoce.Reader(str(step_path))
            st = reader.shapeTool
            free_shapes = reader.freeShapes()
            if free_shapes.Size() < 1:
                return
            
            root = free_shapes.Value(1)
            
            def label_name(label) -> str:
                name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
                return name.strip() if name else "(unnamed)"
            
            def print_node(label, indent=0, prefix="", connector=""):
                name = label_name(label)
                shape = st.GetShape(label)
                shape_type = type(shape).__name__ if shape else "None"
                is_assy = "[Assembly]" if st.IsAssembly(label) else "[Part]"
                is_ref = "[Ref]" if st.IsReference(label) else ""
                
                print(f"{prefix}{connector}{name} {is_assy}{is_ref} ({shape_type})")
                
                if label.NbChildren() > 0:
                    for i in range(1, label.NbChildren() + 1):
                        found, child = label.FindChild(i, False)
                        if found:
                            is_last = (i == label.NbChildren())
                            new_connector = "└── " if is_last else "├── "
                            extension = "    " if is_last else "│   "
                            print_node(child, indent + 1, prefix + extension, new_connector)
            
            print("\n" + "="*60)
            print("STEP FILE STRUCTURE TREE")
            print("="*60)
            print_node(root)
            print("="*60 + "\n")
        
        _print_step_tree_wrapper(step_file)
    
    build_gdml_from_stls(stl_dir, gdml_out, step_file=step_file)
    print(f"Wrote GDML: {gdml_out}")

    if args.visualize:
        print("\nStarting Geant4 visualization...")
        # Run manager + initialization
        runManager = G4RunManager()
        runManager.SetUserInitialization(GDMLDetectorConstruction(str(gdml_out)))

        # Use a standard reference physics list.
        runManager.SetUserInitialization(QBBC())

        # Initialize visualization
        visManager = G4VisExecutive()
        visManager.Initialize()

        UImanager = G4UImanager.GetUIpointer()
        macro_path = args.macro
        if not os.path.exists(macro_path):
            raise FileNotFoundError(f"Macro file not found: {macro_path}")

        UImanager.ApplyCommand("/control/execute " + macro_path)

        # Cleanup
        del visManager
        del runManager
    else:
        print("\nVisualization disabled. Use --visualize flag to enable.\n")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
