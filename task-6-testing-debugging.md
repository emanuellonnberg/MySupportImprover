# Task 6: Testing and Debugging Strategies

**Priority:** Critical - Quality Assurance
**Estimated Complexity:** Medium
**Dependencies:** Task 1-5

## Overview

Establish comprehensive testing strategies, debugging techniques, and verification methods to ensure robust, production-quality overhang detection functionality.

## Objectives

1. Develop unit tests for core algorithms
2. Create integration tests for complete workflow
3. Implement visualization tools for debugging
4. Export intermediate results for verification
5. Handle common pitfalls and edge cases
6. Ensure version compatibility

## Testing Strategy

### Unit Tests for Core Components

#### Test 1: Mesh Data Access

```python
def test_mesh_data_extraction():
    """Verify mesh data can be extracted correctly"""
    # Create test mesh
    mesh_builder = MeshBuilder()
    mesh_builder.addCube(width=10, height=10, depth=10, center=Vector(0, 0, 0))
    mesh_builder.calculateNormals()
    mesh_data = mesh_builder.build()

    # Test extraction
    vertices = mesh_data.getVertices()
    assert vertices is not None
    assert len(vertices) > 0

    indices = mesh_data.getIndices()
    assert indices is not None
    assert mesh_data.getFaceCount() == 12  # Cube has 12 triangular faces

    print("✓ Mesh data extraction test passed")
```

#### Test 2: Overhang Angle Detection

```python
import numpy as np

def test_overhang_angle_calculation():
    """Verify angle calculations match theoretical values"""

    # Test case 1: Horizontal face (0° from vertical)
    normal_horizontal = np.array([[0., 0., 1.0]])
    build_direction = np.array([[0., 0., -1.0]])
    dot = np.dot(build_direction, normal_horizontal.T)
    angle = np.degrees(np.arccos(np.clip(dot, -1.0, 1.0))).flatten()[0]
    assert abs(angle - 180.0) < 0.1, f"Expected 180°, got {angle}°"

    # Test case 2: Vertical face (90° from vertical)
    normal_vertical = np.array([[1., 0., 0.]])
    dot = np.dot(build_direction, normal_vertical.T)
    angle = np.degrees(np.arccos(np.clip(dot, -1.0, 1.0))).flatten()[0]
    assert abs(angle - 90.0) < 0.1, f"Expected 90°, got {angle}°"

    # Test case 3: 45° overhang
    normal_45 = np.array([[0., 1./np.sqrt(2), -1./np.sqrt(2)]])
    dot = np.dot(build_direction, normal_45.T)
    angle = np.degrees(np.arccos(np.clip(dot, -1.0, 1.0))).flatten()[0]
    assert abs(angle - 45.0) < 0.1, f"Expected 45°, got {angle}°"

    print("✓ Overhang angle calculation test passed")
```

#### Test 3: Face Adjacency Graph

```python
def test_face_adjacency_construction():
    """Verify adjacency graph is built correctly"""
    # Create simple test mesh (pyramid)
    mesh_builder = MeshBuilder()
    mesh_builder.addPyramid(width=10, height=10, depth=10, angle=45)
    mesh_data = mesh_builder.build()

    adjacency = build_face_adjacency_graph(mesh_data)

    # Each face should have neighbors
    face_count = mesh_data.getFaceCount()
    assert len(adjacency) == face_count

    # Check adjacency is symmetric
    for face_id, neighbors in adjacency.items():
        for neighbor_id in neighbors:
            assert face_id in adjacency[neighbor_id], \
                f"Adjacency not symmetric: {face_id} -> {neighbor_id}"

    print("✓ Face adjacency graph test passed")
```

#### Test 4: OBB Computation

```python
def test_obb_computation():
    """Verify OBB computation produces correct results"""
    # Create aligned box of known dimensions
    vertices = np.array([
        [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
        [0, 0, 5], [10, 0, 5], [10, 10, 5], [0, 10, 5]
    ], dtype=np.float32)

    obb = compute_obb_pca(vertices)

    # Check center
    expected_center = np.array([5., 5., 2.5])
    assert np.allclose(obb['center'], expected_center, atol=0.1), \
        f"Center mismatch: {obb['center']} vs {expected_center}"

    # Check extents (half-dimensions)
    expected_extents = np.array([5., 5., 2.5])
    # Extents may be in different order, so check set equality
    assert np.allclose(sorted(obb['extents']), sorted(expected_extents), atol=0.1), \
        f"Extents mismatch: {sorted(obb['extents'])} vs {sorted(expected_extents)}"

    print("✓ OBB computation test passed")
```

### Integration Tests

#### Test 5: Complete Workflow

```python
def test_complete_workflow():
    """Test full analysis pipeline"""
    # Load test model
    scene = CuraApplication.getInstance().getController().getScene()
    test_node = create_test_model_with_overhang()

    # Create analysis job
    job = OverhangAnalysisJob(test_node, threshold_angle=45.0)
    job.run()

    # Check results
    results = job.getResults()
    assert len(results) > 0, "Should detect at least one overhang region"

    # Verify OBB structure
    for result in results:
        assert 'obb' in result
        assert 'faces' in result
        assert 'severity' in result

        obb = result['obb']
        assert 'center' in obb
        assert 'axes' in obb
        assert 'extents' in obb

    print("✓ Complete workflow test passed")
```

## Debugging Techniques

### Export Intermediate Results

#### Export Detected Overhang Faces

```python
def export_overhang_faces_to_stl(mesh_data, overhang_face_ids, filepath):
    """Export only the detected overhang faces for visualization"""
    vertices = mesh_data.getVertices()
    indices = mesh_data.getIndices()

    # Extract overhang faces
    overhang_faces = indices[overhang_face_ids]

    import struct
    with open(filepath, 'wb') as f:
        # STL header
        f.write(b'\x00' * 80)
        f.write(struct.pack("<I", len(overhang_faces)))

        # Write faces
        for face in overhang_faces:
            v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

            # Compute normal
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)
            normal = normal / np.linalg.norm(normal)

            # Write normal and vertices
            f.write(struct.pack("<fff", normal[0], normal[1], normal[2]))
            f.write(struct.pack("<fff", v0[0], v0[1], v0[2]))
            f.write(struct.pack("<fff", v1[0], v1[1], v1[2]))
            f.write(struct.pack("<fff", v2[0], v2[1], v2[2]))
            f.write(struct.pack("<H", 0))

    Logger.log("d", f"Exported {len(overhang_faces)} overhang faces to {filepath}")
```

#### Visualize OBB as Mesh

```python
def create_obb_visualization_mesh(obb):
    """Create a visible mesh representing the OBB"""
    from UM.Mesh.MeshBuilder import MeshBuilder
    from UM.Math.Vector import Vector

    mesh_builder = MeshBuilder()
    mesh_builder.addCube(
        width=obb['extents'][0] * 2,
        height=obb['extents'][1] * 2,
        depth=obb['extents'][2] * 2,
        center=Vector(0, 0, 0)
    )
    mesh_builder.calculateNormals()

    return mesh_builder.build()
```

### Logging and Debug Output

```python
from UM.Logger import Logger

def debug_overhang_analysis(mesh_data, threshold_angle=45.0):
    """Run analysis with detailed debug logging"""
    Logger.log("d", "=== Starting Debug Analysis ===")

    # Log mesh info
    vertices = mesh_data.getVertices()
    indices = mesh_data.getIndices()
    Logger.log("d", f"Mesh: {len(vertices)} vertices, {len(indices)} faces")

    # Detect overhangs
    overhang_faces, angles = detect_overhangs(mesh_data, threshold_angle)
    Logger.log("d", f"Detected {len(overhang_faces)} overhang faces")
    Logger.log("d", f"Angle range: {np.min(angles):.1f}° - {np.max(angles):.1f}°")

    # Log overhang distribution
    bins = [0, 30, 45, 60, 75, 90, 180]
    hist, _ = np.histogram(angles[overhang_faces], bins=bins)
    Logger.log("d", "Overhang distribution:")
    for i in range(len(bins)-1):
        Logger.log("d", f"  {bins[i]}-{bins[i+1]}°: {hist[i]} faces")

    # Build adjacency
    adjacency = build_face_adjacency_graph(mesh_data)
    avg_neighbors = np.mean([len(neighbors) for neighbors in adjacency.values()])
    Logger.log("d", f"Average neighbors per face: {avg_neighbors:.1f}")

    # Find regions
    overhang_mask = np.zeros(len(angles), dtype=bool)
    overhang_mask[overhang_faces] = True

    regions = []
    visited = set()
    for face_id in overhang_faces:
        if face_id not in visited:
            region = find_connected_overhang_region(face_id, overhang_mask, adjacency)
            if region:
                regions.append(region)
                visited.update(region)

    Logger.log("d", f"Found {len(regions)} connected regions")
    for i, region in enumerate(regions):
        Logger.log("d", f"  Region {i+1}: {len(region)} faces")

    Logger.log("d", "=== Debug Analysis Complete ===")
```

## Common Pitfalls and Solutions

### Pitfall 1: Missing Normal Calculation

**Problem:** Meshes render black or angle detection fails

**Solution:**
```python
# ALWAYS call this after MeshBuilder operations
mesh_builder.calculateNormals()
```

### Pitfall 2: Not Applying Transformations

**Problem:** Detection works on origin-centered mesh but fails on positioned models

**Solution:**
```python
# ALWAYS use transformed mesh data
mesh_data = node.getMeshData().getTransformed(node.getWorldTransformation())
```

### Pitfall 3: Threading Violations

**Problem:** Qt crashes with "QObject: Cannot create children for a parent in a different thread"

**Solution:**
```python
# ALWAYS use decorator for UI updates
from cura.Utils.Threading import call_on_qt_thread

@call_on_qt_thread
def update_scene_or_ui():
    # Safe to modify scene or UI here
    pass
```

### Pitfall 4: Incorrect Extent Interpretation

**Problem:** OBB appears twice as large as expected

**Solution:**
```python
# OBB extents are HALF-dimensions
# MeshBuilder uses FULL dimensions
mesh_builder.addCube(
    width=obb['extents'][0] * 2,  # Multiply by 2!
    height=obb['extents'][1] * 2,
    depth=obb['extents'][2] * 2
)
```

### Pitfall 5: Forgetting to Check Indices

**Problem:** Crashes when accessing indices on meshes without index buffer

**Solution:**
```python
if mesh_data.hasIndices():
    indices = mesh_data.getIndices()
else:
    # Handle non-indexed mesh
    Logger.log("w", "Mesh has no index buffer")
```

## Version Compatibility Testing

### Testing Across Cura Versions

```python
def check_cura_version_compatibility():
    """Check if running on compatible Cura version"""
    from cura.CuraApplication import CuraApplication

    app = CuraApplication.getInstance()
    version = app.getVersion()

    Logger.log("d", f"Running on Cura version: {version}")

    # Parse version
    major, minor = map(int, version.split('.')[:2])

    if major < 4:
        Logger.log("e", "Cura version too old, requires 4.0+")
        return False

    if major == 5:
        Logger.log("d", "Running on Cura 5.x, using updated API")
        # Use Cura 5.x specific APIs

    return True
```

## Performance Profiling

### Profile Analysis Job

```python
import cProfile
import pstats

def profile_analysis_job(node):
    """Profile the analysis job to find bottlenecks"""
    profiler = cProfile.Profile()

    job = OverhangAnalysisJob(node)

    profiler.enable()
    job.run()
    profiler.disable()

    # Print statistics
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 functions
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def analyze_memory_usage(mesh_data):
    """Profile memory usage during analysis"""
    overhang_faces, angles = detect_overhangs(mesh_data, 45.0)
    adjacency = build_face_adjacency_graph(mesh_data)
    # ... continue analysis
```

## Test Models

### Create Test Geometry

```python
def create_test_model_with_overhang():
    """Create a test model with known overhang characteristics"""
    mesh_builder = MeshBuilder()

    # Base (no overhang)
    mesh_builder.addCube(width=20, height=20, depth=5, center=Vector(0, 0, 2.5))

    # Overhanging section (45° angle)
    # Add custom geometry with known overhang angles

    mesh_builder.calculateNormals()
    mesh_data = mesh_builder.build()

    # Create scene node
    from cura.Scene.CuraSceneNode import CuraSceneNode
    node = CuraSceneNode()
    node.setMeshData(mesh_data)

    return node
```

## Success Criteria

- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] No threading errors in logs
- [ ] Performance meets targets
- [ ] Memory usage acceptable
- [ ] Works across target Cura versions
- [ ] Intermediate results can be exported
- [ ] Debug logging provides useful information

## Recommended Test Models

1. **Simple cube** - No overhangs expected
2. **Pyramid** - All sides are overhangs at 45°
3. **Overhang test model** - Standard 3D printing test with multiple angles
4. **Organic shape** - Tests smoothing and complex geometry
5. **Large mesh** - Performance testing (100K+ faces)

## Reference Plugins for Testing Patterns

- **MeshTools:** https://github.com/fieldOfView/Cura-MeshTools
  - Test mesh validation
  - Test mesh manipulation
  - Test trimesh integration

- **CustomSupportEraserPlus:** https://github.com/5axes/CustomSupportEraserPlus
  - Test interactive picking
  - Test modifier mesh creation
  - Test scene operations

## Related Tasks

- **Validates:** All previous tasks (1-5)
- **Required for:** Production deployment

## References

- Python unittest documentation
- cProfile documentation
- memory_profiler: https://pypi.org/project/memory-profiler/
- Cura logging: `UM/Logger.py`
- Cura version compatibility: https://github.com/Ultimaker/Cura/wiki/CuraAPI-and-SDK-Versions
