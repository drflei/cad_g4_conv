#!/bin/bash
# Demonstration of all three cad_g4_conv.py workflows

echo "========================================================================"
echo "CAD to GDML Converter - All Workflow Demonstrations"
echo "========================================================================"
echo

# Workflow 1: STEP-to-GDML (native geometry with hierarchy)
echo "=========================================="
echo "WORKFLOW 1: STEP Native Conversion"
echo "=========================================="
echo "Converts STEP file directly to GDML, maintaining assembly hierarchy"
echo
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o demo_step_native.gdml | grep -E "(Mode:|Total volumes:|World size:)"
echo
echo "Output: demo_step_native.gdml"
echo

# Workflow 2: STL+STEP-to-GDML (mesh with placements)
echo "=========================================="
echo "WORKFLOW 2: STL+STEP Mesh Conversion"
echo "=========================================="
echo "Uses STL meshes with STEP file for placement information"
echo
python cad_g4_conv.py \
    --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP \
    --stl-dir CAD_files/Stacked-Trays/STLs \
    -o demo_stl_step.gdml | grep -E "(Found.*STL|Total volumes:|World size:)"
echo
echo "Output: demo_stl_step.gdml"
echo

# Workflow 3: Single STL-to-GDML (simple mesh)
echo "=========================================="
echo "WORKFLOW 3: Single STL Conversion"
echo "=========================================="
echo "Converts a single STL file to GDML (quickest method)"
echo
python cad_g4_conv.py \
    --stl-file "CAD_files/Stacked-Trays/STLs/Stacked Trays - Base-1.STL" \
    -o demo_single_stl.gdml | grep -E "(Input:|Total volumes:|World size:)"
echo
echo "Output: demo_single_stl.gdml"
echo

# Summary
echo "========================================================================"
echo "All Workflows Complete!"
echo "========================================================================"
echo
echo "Generated files:"
ls -lh demo_*.gdml
echo
echo "Comparison:"
echo "  Workflow 1 (STEP Native):   Best for assemblies, CSG primitives"
echo "  Workflow 2 (STL+STEP):       Best for multi-part meshes with placement"
echo "  Workflow 3 (Single STL):     Best for standalone meshes, quickest"
echo
echo "To visualize:"
echo "  python run_vtkviewer.py demo_step_native.gdml"
echo "  python run_vtkviewer.py demo_stl_step.gdml"
echo "  python run_vtkviewer.py demo_single_stl.gdml"
