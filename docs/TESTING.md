# Testing & CI Documentation

## Test Suite Overview

All tests verify the **automatic mesh repair** functionality that runs during GDML conversion.

### Test Files

#### `test_automatic_repair.py`
Tests that automatic repair works during conversion:
- `test_single_stl_automatic_repair` - Verifies broken STL meshes are automatically repaired
- `test_step_conversion_with_automatic_repair` - Tests STEP file conversion with automatic repair
- `test_watertight_mesh_after_automatic_repair` - Confirms repaired meshes are watertight

#### `test_no_duplicates.py`
Tests that `replace_in_place=True` correctly removes `_fixed` duplicates:
- `test_no_fixed_duplicates_in_registry` - Ensures only one copy of each solid exists in registry

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_automatic_repair.py -v

# Run with coverage
pytest tests/ --cov=cad_g4_conv --cov-report=html
```

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:

### Jobs
1. **Test Matrix** - Python 3.10 and 3.11
2. **Install Dependencies** - Install pyg4ometry, trimesh, pytest
3. **Lint** - Black formatting and Flake8 style checks (continue-on-error)
4. **Run Tests** - Execute pytest suite
5. **Smoke Test** - Create broken mesh, convert, verify automatic repair in logs

## Automatic Repair

**Repair now happens automatically** during all conversions. No flags needed:

```bash
# This is all you need - repair is automatic
python cad_g4_conv.py --stl-file mesh.stl -o output.gdml
```

The 10-phase comprehensive repair process (trimesh + optional pymeshlab) runs automatically before GDML export.

### CI Status
Check the latest CI run: https://github.com/drflei/cad_g4_conv/actions

All 7 tests should pass on both Python 3.10 and 3.11.
