#!/usr/bin/env python3
"""
Minimal Geant4 application to import GDML geometry and check for overlaps.

Requirements:
    pip install geant4_pybind

Usage:
    python check_overlaps.py <gdml_file>
"""

import sys
import re
import io
import contextlib
from pathlib import Path
from geant4_pybind import *


class MinimalPhysicsList(G4VUserPhysicsList):
    """Minimal physics list for geometry checking only."""
    
    def __init__(self):
        super().__init__()
    
    def ConstructParticle(self):
        """Construct minimal particles."""
        pass
    
    def ConstructProcess(self):
        """Construct minimal processes."""
        pass
    
    def SetCuts(self):
        """Set minimal cuts."""
        pass


class MinimalDetectorConstruction(G4VUserDetectorConstruction):
    """Detector construction that loads GDML geometry."""
    
    def __init__(self, gdml_file, world_size_m=10.0):
        super().__init__()
        self.gdml_file = str(gdml_file)
        self.world_size_m = world_size_m
        self.parser = G4GDMLParser()
        
    def Construct(self):
        """Load GDML and return world volume with expanded size if needed."""
        print(f"\nLoading GDML file: {self.gdml_file}")
        
        # Parse GDML file
        self.parser.Read(self.gdml_file, False)  # False = no schema validation
        
        # Get original world volume
        world_pv = self.parser.GetWorldVolume()
        world_lv = world_pv.GetLogicalVolume()
        
        print(f"Original world volume: {world_pv.GetName()}")
        
        # Get the solid from original world
        original_solid = world_lv.GetSolid()
        
        # Check if we need to expand world
        if hasattr(original_solid, 'GetXHalfLength'):
            # It's a box
            x_half = original_solid.GetXHalfLength()
            y_half = original_solid.GetYHalfLength()
            z_half = original_solid.GetZHalfLength()
            
            # Convert to meters (Geant4 default is mm)
            max_dim_m = max(x_half, y_half, z_half) / 1000.0
            
            print(f"Original world dimensions: {x_half*2:.1f} x {y_half*2:.1f} x {z_half*2:.1f} mm")
            
            if max_dim_m < self.world_size_m:
                print(f"Expanding world to {self.world_size_m*2:.1f} x {self.world_size_m*2:.1f} x {self.world_size_m*2:.1f} m")
                
                # Create new larger box solid (half-length in mm)
                new_solid = G4Box("world_box_expanded", 
                                 self.world_size_m * 1000,  # Convert m to mm
                                 self.world_size_m * 1000,
                                 self.world_size_m * 1000)
                
                # Replace the solid in the logical volume
                world_lv.SetSolid(new_solid)
                print(f"World expanded successfully")
            else:
                print(f"World is large enough ({max_dim_m:.1f} m), no expansion needed")
        
        return world_pv


def check_overlaps(gdml_file, resolution=1000, tolerance=0.001, verbose=True, world_size_m=10.0):
    """
    Check for geometry overlaps in GDML file.
    
    Args:
        gdml_file: Path to GDML file
        resolution: Number of points to check (default: 1000)
        tolerance: Tolerance for overlap detection in mm (default: 0.001)
        verbose: Print detailed overlap information (default: True)
        world_size_m: World volume size in meters (default: 10.0)
    """
    gdml_path = Path(gdml_file)
    if not gdml_path.exists():
        print(f"Error: File not found: {gdml_file}")
        return False
    
    print("="*70)
    print("Geant4 Overlap Checker")
    print("="*70)
    
    # Create run manager
    run_manager = G4RunManager()
    
    # Set detector construction with expanded world
    detector = MinimalDetectorConstruction(gdml_path, world_size_m)
    run_manager.SetUserInitialization(detector)
    
    # Set minimal physics list (required for initialization)
    physics = MinimalPhysicsList()
    run_manager.SetUserInitialization(physics)
    
    # Prepare list to collect surface defect/hole messages
    surface_issues = []

    # Initialize (this constructs the geometry) and capture output for surface issues
    init_buf = io.StringIO()
    with contextlib.redirect_stdout(init_buf), contextlib.redirect_stderr(init_buf):
        run_manager.Initialize()
    init_output = init_buf.getvalue()
    # Parse any surface defect messages from initialization output
    for line in init_output.splitlines():
        if re.search(r"Defects in solid:|surface hole|defect", line, re.I):
            surface_issues.append(('Initialization', line.strip()))
    if verbose and init_output.strip():
        print(init_output, end='')

    print("\nNote: Check output above for any surface hole warnings from Geant4")
    print("      (Lines starting with 'Defects in solid:')")
    
    # Get world volume
    world_pv = detector.parser.GetWorldVolume()
    world_lv = world_pv.GetLogicalVolume()
    
    print(f"\nChecking overlaps with {resolution} points...")
    print(f"Tolerance: {tolerance} mm")
    print("="*70)
    
    # Check overlaps recursively and collect results (collecting pairs)
    overlap_pairs = []
    check_volume_overlaps(world_lv, resolution, tolerance, verbose, overlap_pairs, surface_issues)

    # Deduplicate pairs for summary (normalize by base names to avoid index duplication)
    seen = set()
    unique_pairs = []
    for a, b in overlap_pairs:
        key = tuple(sorted((a.split(':')[0], b.split(':')[0])))
        if key not in seen:
            seen.add(key)
            unique_pairs.append((a, b))

    # Print summary
    print("="*70)
    print("\nGEOMETRY CHECK SUMMARY")
    print("="*70)
    
    # Report overlaps (unique pairs)
    if unique_pairs:
        print(f"\n⚠️  FOUND {len(unique_pairs)} UNIQUE OVERLAPPING PAIR(S):\n")
        sep = " === "
        formatted = [f"{i:2d}. {a} {sep} {b}" for i, (a, b) in enumerate(unique_pairs, 1)]
        print("  " + "\n  ".join(formatted))
        print(f"\n{'-'*70}")
        print(f"Total overlapping pairs: {len(unique_pairs)}")
        print(f"{'-'*70}")
        print("\n⚠️  ACTION REQUIRED: Please review and fix the overlapping volumes.")
        print("    Overlaps can cause incorrect simulation results.")
    else:
        print("\n✓ NO OVERLAPS DETECTED")
        print("  Geometry overlap check passed.")
    
    print("\n" + "="*70)
    print("SURFACE HOLE / DEFECT REPORT")
    print("="*70)
    if surface_issues:
        # Deduplicate and print
        seen_si = set()
        for src, line in surface_issues:
            key = (src, line)
            if key not in seen_si:
                seen_si.add(key)
                print(f"  - {src}: {line}")
        print("\n⚠️  ACTION REQUIRED: Investigate and repair the affected solids (e.g., re-tessellate or fix STL/STEP exports).")
    else:
        print("\n✓ No surface hole warnings detected.")
    print("="*70 + "\n")
    
    return len(unique_pairs) == 0


def check_volume_overlaps(logical_volume, resolution, tolerance, verbose, overlap_pairs, surface_issues, level=0):
    """
    Recursively check overlaps for a logical volume and its daughters.
    
    Args:
        logical_volume: The logical volume to check
        resolution: Number of points to check
        tolerance: Tolerance in mm
        verbose: Print detailed information
        overlap_pairs: List to collect tuples of overlapping volumes (a, b)
        surface_issues: List to collect tuples (source_volume, message) about defects/hole messages
        level: Recursion depth for indentation
    
    Returns:
        True if any overlaps found, False otherwise
    """
    overlap_found = False
    indent = "  " * level
    
    # Check all daughter volumes
    n_daughters = logical_volume.GetNoDaughters()
    
    for i in range(n_daughters):
        daughter_pv = logical_volume.GetDaughter(i)
        daughter_lv = daughter_pv.GetLogicalVolume()
        daughter_name = daughter_pv.GetName()
        
        if verbose:
            print(f"{indent}Checking: {daughter_name}")
        
        # Capture Geant4 output while running CheckOverlaps so we can parse partner names
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            has_overlap = daughter_pv.CheckOverlaps(resolution, tolerance, verbose)
        captured = buf.getvalue()
        # Re-print the captured output when verbose so the user still sees Geant4 messages
        if captured and verbose:
            print(captured, end="")
        
        if has_overlap:
            overlap_found = True
            # Attempt to extract partner names from captured output lines mentioning overlap/clash
            other_names = set()
            base_daughter = daughter_name.split(':')[0]
            for line in captured.splitlines():
                if re.search(r'overlap|Overlap|OVERLAP|clash|Clash|CLASH|clashing', line):
                    # First try: quoted names (e.g., 'name' or "name")
                    for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", line):
                        name = a or b
                        if name:
                            base_name = name.split(':')[0]
                            if base_name != base_daughter:
                                other_names.add(name)
                    # Second try: unquoted pattern used by Geant4
                    m = re.search(r'Overlap is detected for volume\s+(\S+)(?:\s*\([^\)]*\))?\s+with\s+(\S+)', line, re.I)
                    if m:
                        a_name, b_name = m.group(1), m.group(2)
                        if a_name:
                            if a_name.split(':')[0] != base_daughter:
                                other_names.add(a_name)
                        if b_name:
                            if b_name.split(':')[0] != base_daughter:
                                other_names.add(b_name)
                # Also check for surface defect/hole messages
                if re.search(r'Defects in solid:|surface hole|defect', line, re.I):
                    surface_issues.append((daughter_name, line.strip()))
            # Fallback: any quoted names in the entire captured output
            if not other_names:
                for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", captured):
                    name = a or b
                    if name and name.split(':')[0] != base_daughter:
                        other_names.add(name)
            if other_names:
                for other in sorted(other_names):
                    overlap_pairs.append((daughter_name, other))
                print(f"{indent}⚠️  OVERLAP in: {daughter_name} === {', '.join(sorted(other_names))}")
            else:
                overlap_pairs.append((daughter_name, '<unknown>'))
                print(f"{indent}⚠️  OVERLAP in: {daughter_name} (partner unknown)")
        
        # Recursively check daughter's daughters
        if check_volume_overlaps(daughter_lv, resolution, tolerance, verbose, overlap_pairs, surface_issues, level + 1):
            overlap_found = True
    
    return overlap_found


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python check_overlaps.py <gdml_file> [resolution] [tolerance] [world_size_m]")
        print("\nExample:")
        print("  python check_overlaps.py geometry.gdml")
        print("  python check_overlaps.py geometry.gdml 2000 0.01")
        print("  python check_overlaps.py geometry.gdml 2000 0.01 20.0")
        print("\nArguments:")
        print("  gdml_file    : Path to GDML geometry file")
        print("  resolution   : Number of points to check (default: 1000)")
        print("  tolerance    : Tolerance in mm (default: 0.001)")
        print("  world_size_m : World half-size in meters (default: 10.0)")
        sys.exit(1)
    
    gdml_file = sys.argv[1]
    resolution = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    tolerance = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
    world_size_m = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0
    
    success = check_overlaps(gdml_file, resolution, tolerance, verbose=True, world_size_m=world_size_m)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
