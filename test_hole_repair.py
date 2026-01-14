#!/usr/bin/env python3
"""Quick test to verify hole repair works with corrected trimesh API usage."""

import trimesh

print("Testing hole repair sequence with corrected trimesh API...")

# Create a cube with one face removed
cube = trimesh.creation.box(extents=(10, 10, 10))
print(f"Original: {len(cube.faces)} faces, watertight={cube.is_watertight}")

faces = cube.faces.copy()
cube.faces = faces[:-1]
print(f"With hole: {len(cube.faces)} faces, watertight={cube.is_watertight}")

# Apply repair sequence
try:
    trimesh.repair.fix_normals(cube)
    print("  ✓ fix_normals")
except Exception as e:
    print(f"  ✗ fix_normals: {e}")

try:
    cube.merge_vertices()
    print("  ✓ merge_vertices")
except Exception as e:
    print(f"  ✗ merge_vertices: {e}")

try:
    if hasattr(cube, 'nondegenerate_faces'):
        mask = cube.nondegenerate_faces()
        if mask is not None and mask.sum() < len(cube.faces):
            cube.update_faces(mask)
            print(f"  ✓ removed {len(cube.faces) - mask.sum()} degenerate faces")
        else:
            print("  ✓ no degenerate faces to remove")
except Exception as e:
    print(f"  ✗ degenerate face removal: {e}")

try:
    trimesh.repair.fill_holes(cube)
    print(f"  ✓ fill_holes: {len(cube.faces)} faces")
except Exception as e:
    print(f"  ✗ fill_holes: {e}")

try:
    trimesh.repair.fix_inversion(cube)
    print("  ✓ fix_inversion")
except Exception as e:
    print(f"  ✗ fix_inversion: {e}")

print(f"\nFinal result: {len(cube.faces)} faces, watertight={cube.is_watertight}")

if cube.is_watertight:
    print("✅ SUCCESS: Mesh is now watertight!")
else:
    print("⚠️  WARNING: Mesh is still not watertight")
