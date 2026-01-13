#!/bin/bash
# Quick test script for cad_g4_conv.py demonstrating all features

echo "========================================"
echo "CAD to G4 Converter - Feature Demo"
echo "========================================"
echo

# Test 1: STEP native conversion with hierarchy
echo "Test 1: STEP Native (Hierarchy Mode)"
echo "--------------------------------------"
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o test_step_hierarchy.gdml
echo

# Test 2: STEP flat mode
echo "Test 2: STEP Flat Mode (Single Tessellated Solid)"
echo "---------------------------------------------------"
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o test_step_flat.gdml \
    --flat
echo

# Test 3: STEP with overlap checking
echo "Test 3: STEP with Overlap Checking"
echo "------------------------------------"
python cad_g4_conv.py \
    --step-file CAD_files/HEPI-SiO2/HEPI-SiO2.STEP \
    -o test_step_overlaps.gdml \
    --check-overlaps | grep -E "(overlap|Total volumes)"
echo

# Test 4: STL+STEP mesh conversion
echo "Test 4: STL+STEP Mesh Conversion"
echo "----------------------------------"
python cad_g4_conv.py \
    --step-file CAD_files/Stacked-Trays/Stacked-Trays.STEP \
    --stl-dir CAD_files/Stacked-Trays/STLs \
    -o test_stl_mesh.gdml
echo

# Summary
echo "========================================"
echo "All Tests Complete!"
echo "========================================"
echo "Generated files:"
ls -lh test_*.gdml
echo
echo "To visualize:"
echo "  python run_vtkviewer.py test_step_hierarchy.gdml"
echo "  python run_vtkviewer.py test_stl_mesh.gdml"
