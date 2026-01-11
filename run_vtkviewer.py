#!/usr/bin/env python3
"""Wrapper to run pyg4ometry VtkViewer with support for multiple geometry formats.

SUPPORTED FORMATS:
  - GDML (.gdml)           Geant4 Markup Language
  - STL (.stl)             Stereolithography (tessellated meshes)
  - STEP (.step, .stp)     CAD format via OpenCASCADE
  - FLUKA (.inp)           FLUKA geometry input
  
FEATURES:
  - Multi-format geometry loading
  - Interactive 3D visualization
  - Material editing (GDML only)
  - Volume/material listing

USAGE:
  python run_vtkviewer.py <geometry_file> [options]
  
OPTIONS:
  --list-volumes          List all logical volumes and their materials
  --list-materials        List all materials in the registry
  --change-material VOLUME MATERIAL   Change material of a logical volume (GDML only)
  --flat                  Use flat tessellated solid for STEP files (instead of hierarchy)
  
EXAMPLES:
  # View GDML file
  python run_vtkviewer.py HEPI-PbF2.gdml
  
  # View STL file
  python run_vtkviewer.py model.stl
  
  # View STEP file with hierarchy
  python run_vtkviewer.py assembly.step
  
  # View STEP file as single tessellated solid
  python run_vtkviewer.py assembly.step --flat
  
  # View FLUKA geometry
  python run_vtkviewer.py detector.inp
  
  # List volumes and change materials (GDML)
  python run_vtkviewer.py HEPI-PbF2.gdml --list-volumes
  python run_vtkviewer.py HEPI-PbF2.gdml --change-material lv_radiator G4_WATER
"""

import sys
import os
import argparse

# FIX: Clear any cached VtkViewer modules that cause the frozen runpy warning
# This must happen before any pyg4ometry imports
modules_to_clear = [k for k in sys.modules.keys() if 'VtkViewer' in k]
for mod in modules_to_clear:
    del sys.modules[mod]

# Ensure DISPLAY is set for X11 (hardware acceleration)
os.environ["DISPLAY"] = ":0"


def load_geometry(file_path, use_flat=False):
    """Load geometry from various formats.
    
    Args:
        file_path: Path to geometry file
        use_flat: For STEP files, use flat tessellated solid instead of hierarchy
        
    Returns:
        (registry, world_lv, format_type) tuple
    """
    import pyg4ometry
    
    # Determine file format by extension
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.gdml':
        print(f"Loading GDML: {file_path}")
        reader = pyg4ometry.gdml.Reader(file_path)
        reg = reader.getRegistry()
        world_lv = reg.getWorldVolume()
        return reg, world_lv, 'gdml'
    
    elif ext == '.stl':
        print(f"Loading STL: {file_path}")
        # Create a registry for the STL mesh
        reg = pyg4ometry.geant4.Registry()
        
        # Read STL and convert to tessellated solid
        reader = pyg4ometry.stl.Reader(file_path, registry=reg)
        mesh_solid = reader.getSolid()
        
        # Create materials
        world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
        mesh_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)
        
        # Create logical volume for the STL mesh
        mesh_lv = pyg4ometry.geant4.LogicalVolume(
            mesh_solid, mesh_material, "stl_lv", reg
        )
        
        # Create world volume to contain the STL mesh
        world_solid = pyg4ometry.geant4.solid.Box(
            "world_solid", 5000, 5000, 5000, reg, lunit="mm"
        )
        world_lv = pyg4ometry.geant4.LogicalVolume(
            world_solid, world_material, "world_lv", reg
        )
        
        # Place STL mesh in world
        pyg4ometry.geant4.PhysicalVolume(
            [0, 0, 0], [0, 0, 0], mesh_lv, "stl_pv", world_lv, reg
        )
        reg.setWorld(world_lv)
        
        return reg, world_lv, 'stl'
    
    elif ext in ['.step', '.stp']:
        print(f"Loading STEP: {file_path}")
        # Use pyoce to read STEP file
        reader = pyg4ometry.pyoce.Reader(file_path)
        
        # Get first free shape
        free_shapes = reader.freeShapes()
        if free_shapes.Size() < 1:
            raise RuntimeError("No free shapes found in STEP file")
        
        label = free_shapes.Value(1)
        shape_name = pyg4ometry.pyoce.pythonHelpers.get_TDataStd_Name_From_Label(label)
        if not shape_name:
            shape_name = "step_shape"
        
        top_shape = reader.shapeTool.GetShape(label)
        
        # Create registry and materials
        reg = pyg4ometry.geant4.Registry()
        world_material = pyg4ometry.geant4.Material(name="G4_AIR", registry=reg)
        cad_material = pyg4ometry.geant4.Material(name="G4_Al", registry=reg)
        
        if not use_flat:
            # Try hierarchy mode first
            print("  Converting with hierarchy preservation...")
            try:
                result = pyg4ometry.convert.oce2Geant4(
                    shapeTool=reader.shapeTool,
                    shapeName=shape_name,
                    materialMap={shape_name: cad_material},
                    meshQualityMap={},
                    oceName=False,
                )
                
                if hasattr(result, 'getWorldVolume'):
                    reg = result
                    world_lv = reg.getWorldVolume()
                    print("  ✓ Hierarchy conversion successful")
                    return reg, world_lv, 'step'
                else:
                    print("  Warning: Unexpected return type, falling back to flat mode")
                    use_flat = True
            except Exception as e:
                print(f"  Warning: Hierarchy mode failed ({type(e).__name__}), using flat mode")
                use_flat = True
        
        if use_flat:
            print("  Converting to single tessellated solid...")
            cad_solid = pyg4ometry.convert.oceShape_Geant4_Tessellated(
                name="step_solid",
                shape=top_shape,
                greg=reg,
                linDef=0.5,
                angDef=0.5,
            )
            cad_lv = pyg4ometry.geant4.LogicalVolume(
                cad_solid, cad_material, "step_lv", reg
            )
            
            # Create world volume
            world_solid = pyg4ometry.geant4.solid.Box(
                "world_solid", 5000, 5000, 5000, reg, lunit="mm"
            )
            world_lv = pyg4ometry.geant4.LogicalVolume(
                world_solid, world_material, "world_lv", reg
            )
            pyg4ometry.geant4.PhysicalVolume(
                [0, 0, 0], [0, 0, 0], cad_lv, "step_pv", world_lv, reg
            )
            reg.setWorld(world_lv)
            print("  ✓ Flat conversion successful")
        
        return reg, world_lv, 'step'
    
    elif ext == '.inp':
        print(f"Loading FLUKA: {file_path}")
        # Read FLUKA input file
        reader = pyg4ometry.fluka.Reader(file_path)
        fluka_reg = reader.flukaregistry
        
        # Convert to Geant4 registry
        reg = pyg4ometry.geant4.Registry()
        
        # Convert FLUKA geometry to Geant4
        # This creates logical volumes from FLUKA regions
        geant4_reg = fluka_reg.makeGeant4Registry(reg)
        world_lv = geant4_reg.getWorldVolume()
        
        return geant4_reg, world_lv, 'fluka'
    
    else:
        raise ValueError(f"Unsupported file format: {ext}\n"
                        f"Supported: .gdml, .stl, .step, .stp, .inp")


def list_volumes(reg):
    """List all logical volumes and their materials."""
    print("\nLogical Volumes:")
    print("-" * 80)
    print(f"{'Volume Name':<40} {'Material':<30}")
    print("-" * 80)
    for name, lv in reg.logicalVolumeDict.items():
        if hasattr(lv, 'material'):
            mat_name = lv.material.name if hasattr(lv.material, 'name') else str(lv.material)
        else:
            mat_name = "(Assembly - no material)"
        print(f"{name:<40} {mat_name:<30}")
    print("-" * 80)


def list_materials(reg):
    """List all materials in the registry."""
    print("\nMaterials:")
    print("-" * 80)
    for name, mat in reg.materialDict.items():
        print(f"  {name}")
    print("-" * 80)


def change_material(reg, volume_name, material_name):
    """Change the material of a logical volume."""
    # Find the logical volume
    if volume_name not in reg.logicalVolumeDict:
        print(f"Error: Volume '{volume_name}' not found")
        print("\nAvailable volumes:")
        for name in reg.logicalVolumeDict.keys():
            print(f"  {name}")
        return False
    
    lv = reg.logicalVolumeDict[volume_name]
    
    # Check if it's an assembly (no material)
    if not hasattr(lv, 'material'):
        print(f"Error: '{volume_name}' is an assembly volume and has no material")
        return False
    
    # Find or create the material
    if material_name not in reg.materialDict:
        # Try to create as a NIST material
        try:
            import pyg4ometry
            # Use pyg4ometry's NIST material database
            new_material = pyg4ometry.geant4.nist_material_2geant4Material(
                material_name, reg
            )
            print(f"Created NIST material: {material_name}")
        except Exception as e:
            print(f"Error: Material '{material_name}' not found and cannot create as NIST material")
            print(f"Error details: {e}")
            print("\nAvailable materials:")
            for name in reg.materialDict.keys():
                print(f"  {name}")
            return False
    
    # Change the material
    old_material = lv.material.name if hasattr(lv.material, 'name') else str(lv.material)
    lv.material = reg.materialDict[material_name]
    print(f"✓ Changed material of '{volume_name}' from '{old_material}' to '{material_name}'")
    return True



    """List all logical volumes and their materials."""
    print("\nLogical Volumes:")
    print("-" * 80)
    print(f"{'Volume Name':<40} {'Material':<30}")
    print("-" * 80)
    for name, lv in reg.logicalVolumeDict.items():
        if hasattr(lv, 'material'):
            mat_name = lv.material.name if hasattr(lv.material, 'name') else str(lv.material)
        else:
            mat_name = "(Assembly - no material)"
        print(f"{name:<40} {mat_name:<30}")
    print("-" * 80)


def list_materials(reg):
    """List all materials in the registry."""
    print("\nMaterials:")
    print("-" * 80)
    for name, mat in reg.materialDict.items():
        print(f"  {name}")
    print("-" * 80)


def change_material(reg, volume_name, material_name):
    """Change the material of a logical volume."""
    # Find the logical volume
    if volume_name not in reg.logicalVolumeDict:
        print(f"Error: Volume '{volume_name}' not found")
        print("\nAvailable volumes:")
        for name in reg.logicalVolumeDict.keys():
            print(f"  {name}")
        return False
    
    lv = reg.logicalVolumeDict[volume_name]
    
    # Check if it's an assembly (no material)
    if not hasattr(lv, 'material'):
        print(f"Error: '{volume_name}' is an assembly volume and has no material")
        return False
    
    # Find or create the material
    if material_name not in reg.materialDict:
        # Try to create as a NIST material
        try:
            import pyg4ometry
            # Use pyg4ometry's NIST material database
            new_material = pyg4ometry.geant4.nist_material_2geant4Material(
                material_name, reg
            )
            print(f"Created NIST material: {material_name}")
        except Exception as e:
            print(f"Error: Material '{material_name}' not found and cannot create as NIST material")
            print(f"Error details: {e}")
            print("\nAvailable materials:")
            for name in reg.materialDict.keys():
                print(f"  {name}")
            return False
    
    # Change the material
    old_material = lv.material.name if hasattr(lv.material, 'name') else str(lv.material)
    lv.material = reg.materialDict[material_name]
    print(f"✓ Changed material of '{volume_name}' from '{old_material}' to '{material_name}'")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="View geometry files with pyg4ometry VtkViewer (GDML, STL, STEP, FLUKA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("geometry_file", help="Geometry file to visualize (.gdml, .stl, .step, .stp, .inp)")
    parser.add_argument("--list-volumes", action="store_true", 
                        help="List all logical volumes and their materials")
    parser.add_argument("--list-materials", action="store_true",
                        help="List all available materials")
    parser.add_argument("--change-material", nargs=2, metavar=("VOLUME", "MATERIAL"),
                        action="append", help="Change material of a volume (GDML only, can be used multiple times)")
    parser.add_argument("--save", metavar="FILE", help="Save modified geometry to new GDML file")
    parser.add_argument("--flat", action="store_true",
                        help="Use flat tessellated solid for STEP files (instead of hierarchy)")
    
    args = parser.parse_args()
    geometry_file = args.geometry_file
    
    if not os.path.exists(geometry_file):
        print(f"Error: File not found: {geometry_file}")
        sys.exit(1)
    
    # Import VTK and pyg4ometry AFTER clearing sys.modules
    import vtk
    import pyg4ometry
    
    # Load geometry (auto-detects format)
    try:
        reg, world_lv, file_format = load_geometry(geometry_file, use_flat=args.flat)
        print(f"✓ Loaded {file_format.upper()} geometry successfully")
    except Exception as e:
        print(f"Error loading geometry: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Handle listing operations
    if args.list_volumes:
        list_volumes(reg)
    
    if args.list_materials:
        list_materials(reg)
    
    # Handle material changes (GDML only)
    if args.change_material:
        if file_format != 'gdml':
            print(f"Warning: Material changes only supported for GDML files, not {file_format.upper()}")
        else:
            print("\nApplying material changes:")
            for volume_name, material_name in args.change_material:
                change_material(reg, volume_name, material_name)
    
    # Save modified geometry if requested (GDML only)
    if args.save:
        if file_format != 'gdml':
            print(f"Warning: Saving only supported for GDML files, not {file_format.upper()}")
        else:
            print(f"\nSaving modified geometry to: {args.save}")
            writer = pyg4ometry.gdml.Writer()
            writer.addDetector(reg)
            writer.write(args.save)
            print(f"✓ Saved to {args.save}")
    
    # Create VtkViewer and add geometry
    viewer = pyg4ometry.visualisation.VtkViewer()
    viewer.addLogicalVolume(world_lv)
    
    # Add clipping plane for sectioned view
    # Create a clipping plane along Z-axis
    clipPlane = vtk.vtkPlane()
    clipPlane.SetOrigin(0, 0, 0)
    clipPlane.SetNormal(0, 0, 1)  # Normal pointing in +Z direction
    
    # Track clipping state
    clipping_enabled = [True]  # Use list to allow modification in nested function
    
    # Add clipping plane to all mappers initially
    for mapper in viewer.mappers:
        mapper.AddClippingPlane(clipPlane)
    
    # Create interactive plane widget for adjusting clip plane
    planeWidget = vtk.vtkImplicitPlaneWidget()
    planeWidget.SetInteractor(viewer.iren)
    planeWidget.SetPlaceFactor(1.25)
    planeWidget.PlaceWidget(viewer.ren.ComputeVisiblePropBounds())
    planeWidget.SetOrigin(clipPlane.GetOrigin())
    planeWidget.SetNormal(clipPlane.GetNormal())
    planeWidget.DrawPlaneOff()  # Don't draw the plane surface, just the outline
    planeWidget.OutlineTranslationOff()
    planeWidget.ScaleEnabledOff()
    
    # Callback to update clipping plane when widget is moved
    def updateClipPlane(obj, event):
        obj.GetPlane(clipPlane)
        viewer.renWin.Render()
    
    planeWidget.AddObserver("InteractionEvent", updateClipPlane)
    planeWidget.On()
    
    # Add keyboard callback to toggle clipping with 'c' key
    def keyPressCallback(obj, event):
        key = obj.GetKeySym()
        if key == 'c' or key == 'C':
            clipping_enabled[0] = not clipping_enabled[0]
            if clipping_enabled[0]:
                # Enable clipping
                for mapper in viewer.mappers:
                    mapper.AddClippingPlane(clipPlane)
                planeWidget.On()
                print("Clipping enabled")
            else:
                # Disable clipping
                for mapper in viewer.mappers:
                    mapper.RemoveAllClippingPlanes()
                planeWidget.Off()
                print("Clipping disabled")
            viewer.renWin.Render()
    
    viewer.iren.AddObserver('KeyPressEvent', keyPressCallback)
    
    print("\nStarting interactive viewer...")
    print("Rotate: Left mouse | Zoom: Right mouse | Pan: Middle mouse")
    print("Press 'q' in window to quit")
    
    # Configure render window
    viewer.renWin.SetSize(1024, 768)
    viewer.renWin.SetWindowName(f"pyg4ometry Viewer - {os.path.basename(geometry_file)} [{file_format.upper()}]")
    viewer.ren.ResetCamera()
    
    # Force initial render before starting interactor
    viewer.renWin.Render()
    
    print(f"\n{'='*60}")
    print(f"Geometry Type: {file_format.upper()}")
    print(f"Window created. If you don't see it, check your X server.")
    print("Controls:")
    print("  Rotate: Left mouse button")
    print("  Zoom:   Right mouse button or scroll wheel")
    print("  Pan:    Middle mouse button")
    print("  Clipping: Click and drag the plane widget")
    print("  Toggle Clipping: Press 'c' key")
    print("  Quit:   Press 'q' in the window")
    print(f"{'='*60}\n")
    
    # Start interactive event loop (blocks until window is closed)
    # This allows full 3D interaction with the geometry
    viewer.iren.Initialize()
    viewer.iren.Start()
    
    print("Viewer closed.")
