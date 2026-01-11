#!/usr/bin/env python3
"""Import and visualise a STEP CAD file using pyg4ometry.

This uses the OpenCASCADE (pyoce) backend and pyg4ometry's built-in conversion
helper to produce a Geant4 logical-world volume, then renders it with VTK.

CONVERSION MODES:
=================

1. Default mode (no flags):
   - Maintains STEP assembly structure
   - Converts simple shapes to CSG primitives where possible
   - Falls back to tessellation for complex shapes
   - Preserves parent-child relationships
   - May fail with deeply nested assemblies

2. Flat mode (--flat flag):
   - Converts to single tessellated solid
   - Robust for complex assemblies
   - No hierarchy preservation
   - Use when hierarchy mode fails

USAGE:
======

    # Default: Hierarchy with CSG conversion
    python visualize_step.py
    
    # Flat tessellated solid (fallback)
    python visualize_step.py --flat

OUTPUT:
=======

The script generates a GDML file for use with Geant4.

The GDML will contain either:
    - Hierarchical: Multiple logical volumes with CSG primitives (default)
    - Flat structure: Single tessellated solid (--flat)
"""

from __future__ import annotations

import argparse
import os

import pyg4ometry


def _get_first_free_shape_name(reader: pyg4ometry.pyoce.Reader) -> str:
    free_shapes = reader.freeShapes()
    if free_shapes.Size() < 1:
        raise RuntimeError("No free shapes found in STEP file")

    label = free_shapes.Value(1)
    name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
    if not name:
        raise RuntimeError("First free shape has no name in STEP file")
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and visualize a STEP CAD file using pyg4ometry")
    parser.add_argument(
        "--step-file",
        type=str,
        default="CAD_files/Stacked Trays.STEP",
        help="Path to the STEP file to visualize (default: CAD_files/Stacked Trays.STEP)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output.gdml",
        help="Output GDML file path (default: output.gdml). VRML file will use same base name with .wrl extension",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Use flat tessellated solid instead of hierarchy mode",
    )
    args = parser.parse_args()
    
    step_file = args.step_file
    use_hierarchy = not args.flat  # Default to hierarchy, disable with --flat flag

    print(f"Loading STEP file: {step_file}")
    reader = pyg4ometry.pyoce.Reader(step_file)

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

    cad_registry = None  # Track if we got a registry from hierarchy conversion

    if use_hierarchy:
        # Convert STEP to Geant4 maintaining hierarchy and using CSG where possible
        print("Converting STEP to Geant4 geometry with hierarchy...")
        print("  - Maintaining assembly hierarchy")
        print("  - Using CSG primitives where possible")
        print("  - Falling back to tessellation for complex shapes")
        
        try:
            # Convert using oce2Geant4 which maintains hierarchy
            result = pyg4ometry.convert.oce2Geant4(
                shapeTool=reader.shapeTool,
                shapeName=shape_name,
                materialMap={shape_name: cad_material},
                meshQualityMap={},
                oceName=False,
            )
            
            # Check what type of object was returned
            print(f"  Conversion returned: {type(result)}")
            
            # oce2Geant4 returns a Registry with the world volume already set up
            if hasattr(result, 'getWorldVolume'):
                cad_registry = result
                world_lv = cad_registry.getWorldVolume()
                
                # Replace spaces with underscores in all logical volume names
                def rename_volumes(lv, visited=None):
                    """Recursively rename logical volumes to replace spaces with underscores"""
                    if visited is None:
                        visited = set()
                    
                    if id(lv) in visited:
                        return
                    visited.add(id(lv))
                    
                    # Rename the logical volume
                    if ' ' in lv.name:
                        old_name = lv.name
                        new_name = lv.name.replace(' ', '_')
                        lv.name = new_name
                        # Update in registry
                        if old_name in cad_registry.logicalVolumeDict:
                            cad_registry.logicalVolumeDict[new_name] = cad_registry.logicalVolumeDict.pop(old_name)
                    
                    # Rename solid if it has spaces
                    if hasattr(lv, 'solid') and hasattr(lv.solid, 'name') and ' ' in lv.solid.name:
                        old_solid_name = lv.solid.name
                        new_solid_name = lv.solid.name.replace(' ', '_')
                        lv.solid.name = new_solid_name
                        # Update in registry
                        if old_solid_name in cad_registry.solidDict:
                            cad_registry.solidDict[new_solid_name] = cad_registry.solidDict.pop(old_solid_name)
                    
                    # Recursively process daughter volumes
                    for pv in lv.daughterVolumes:
                        rename_volumes(pv.logicalVolume, visited)
                
                print("  Renaming volumes (replacing spaces with underscores)...")
                rename_volumes(world_lv)
                
                # Rename physical volumes based on their logical volume names
                def rename_physical_volumes(lv, visited=None, pv_counts=None):
                    """Recursively rename physical volumes based on logical volume names"""
                    if visited is None:
                        visited = set()
                    if pv_counts is None:
                        pv_counts = {}
                    
                    if id(lv) in visited:
                        return
                    visited.add(id(lv))
                    
                    for pv in lv.daughterVolumes:
                        # Generate PV name from logical volume name
                        lv_name = pv.logicalVolume.name
                        
                        # Count occurrences of this LV type to handle multiple instances
                        if lv_name not in pv_counts:
                            pv_counts[lv_name] = 0
                        
                        # Create PV name: if single instance, just use LV name, otherwise append number
                        if pv_counts[lv_name] == 0:
                            # Check if there will be multiple instances by scanning all PVs
                            count_same_lv = sum(1 for other_pv in lv.daughterVolumes if other_pv.logicalVolume.name == lv_name)
                            if count_same_lv > 1:
                                new_pv_name = f"{lv_name}_PV{pv_counts[lv_name]}"
                            else:
                                new_pv_name = f"{lv_name}_PV"
                        else:
                            new_pv_name = f"{lv_name}_PV{pv_counts[lv_name]}"
                        
                        pv_counts[lv_name] += 1
                        
                        # Update physical volume name
                        old_pv_name = pv.name
                        pv.name = new_pv_name
                        
                        # Update in registry
                        if old_pv_name in cad_registry.physicalVolumeDict:
                            cad_registry.physicalVolumeDict[new_pv_name] = cad_registry.physicalVolumeDict.pop(old_pv_name)
                        
                        # Recursively process daughter volumes
                        rename_physical_volumes(pv.logicalVolume, visited, pv_counts)
                
                print("  Renaming physical volumes based on logical volume names...")
                rename_physical_volumes(world_lv)
                
                print(f"✓ Converted with hierarchy preservation")
                print(f"  Root logical volume: {world_lv.name}")
                
                # Print hierarchy tree
                def print_hierarchy(lv, pv_name="", indent=0, prefix="", connector=""):
                    """Print volume hierarchy recursively"""
                    solid_type = type(lv.solid).__name__ if hasattr(lv, 'solid') else "Unknown"
                    material = lv.material.name if hasattr(lv, 'material') and hasattr(lv.material, 'name') else "N/A"
                    
                    # Show physical volume name (if any) and logical volume name
                    if pv_name:
                        display_name = f"{pv_name} (LV: {lv.name})"
                    else:
                        display_name = lv.name
                    
                    print(f"{prefix}{connector}{display_name} [{solid_type}, {material}]")
                    
                    for i, pv in enumerate(lv.daughterVolumes):
                        is_last = (i == len(lv.daughterVolumes) - 1)
                        new_connector = "└── " if is_last else "├── "
                        extension = "    " if is_last else "│   "
                        pv_name_str = pv.name if hasattr(pv, 'name') else ""
                        print_hierarchy(pv.logicalVolume, pv_name_str, indent + 1, prefix + extension, new_connector)
                
                # Count daughter volumes recursively
                def count_daughters(lv):
                    count = 0
                    for pv in lv.daughterVolumes:
                        count += 1
                        count += count_daughters(pv.logicalVolume)
                    return count
                
                n_daughters = count_daughters(world_lv)
                print(f"  Total volumes in hierarchy: {n_daughters + 1}")
                print("\nVolume hierarchy:")
                print_hierarchy(world_lv)
            else:
                raise TypeError(f"Unexpected return type from oce2Geant4: {type(result)}")
            
        except Exception as e:
            import traceback
            print(f"Warning: Hierarchy conversion failed: {type(e).__name__}")
            print(f"  {str(e)[:200]}")
            print("  Full traceback:")
            traceback.print_exc()
            print("Falling back to single tessellated solid...")
            use_hierarchy = False
    
    if not use_hierarchy:
        # Convert to single tessellated solid (fallback, more robust)
        print("Converting STEP to single tessellated solid...")
        print("  - Single unified mesh")
        print("  - More robust for complex assemblies")
        print("  - Hierarchy mode disabled (--flat flag used)")
        
        cad_solid = pyg4ometry.convert.oceShape_Geant4_Tessellated(
            name="cad_solid",
            shape=top_shape,
            greg=reg,
            linDef=0.5,
            angDef=0.5,
        )
        cad_lv = pyg4ometry.geant4.LogicalVolume(cad_solid, cad_material, "cad_lv", reg)
        print(f"✓ Converted to tessellated solid")

        # Create a simple world volume large enough to contain the CAD model.
        world_solid = pyg4ometry.geant4.solid.Box(
            "world_solid",
            5000,
            5000,
            5000,
            reg,
            lunit="mm",
        )
        world_lv = pyg4ometry.geant4.LogicalVolume(world_solid, world_material, "world_lv", reg)
        pyg4ometry.geant4.PhysicalVolume([0, 0, 0], [0, 0, 0], cad_lv, "cad_pv", world_lv, reg)
        reg.setWorld(world_lv)
        cad_registry = reg

    # Perform overlap check
    print("\n" + "=" * 60)
    print("PERFORMING OVERLAP CHECK")
    print("=" * 60)
    
    world_lv = cad_registry.getWorldVolume()
    
    # Check overlaps on the world volume (recursively checks all daughter volumes)
    print("Checking for overlaps in geometry...")
    overlap_result = world_lv.checkOverlaps()
    
    # The checkOverlaps method prints overlaps directly and returns the count
    # Look for the printed message to determine if overlaps were found
    print("=" * 60 + "\n")
    
    # Export to GDML
    gdml_file = args.output
    try:
        writer = pyg4ometry.gdml.Writer()
        writer.addDetector(cad_registry)
        writer.write(gdml_file)
        print(f"Wrote GDML file: {gdml_file}")
    except Exception as exc:
        print(f"GDML export failed: {exc}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
