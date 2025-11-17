# Task 3: Creating Minimal Bounding Volumes Around Detected Overhangs

**Priority:** High - Core Functionality
**Estimated Complexity:** High
**Dependencies:** Task 1 (Mesh Data Access), Task 2 (Overhang Detection)

## Overview

Implement algorithms to generate tight-fitting oriented bounding boxes (OBBs) around overhang regions, with proper padding and collision avoidance to ensure effective support blocker placement.

## Objectives

1. Compute oriented bounding boxes using PCA
2. Implement minimal OBB algorithms for tighter fitting
3. Apply appropriate padding for support requirements
4. Implement collision detection (Separating Axis Theorem)
5. Ensure volumes don't intersect the main model except at attachment

## Implementation Details

### PCA-Based Oriented Bounding Box

The fastest approach uses Principal Component Analysis to find optimal box orientation:

**Algorithm Steps:**
1. Compute centroid of vertices
2. Center vertices around origin
3. Compute 3×3 covariance matrix
4. Perform eigenvalue decomposition
5. Sort eigenvectors by eigenvalue magnitude
6. Project vertices onto principal axes
7. Find min/max extents along each axis

**Time Complexity:** O(n) where n = number of vertices

```python
import numpy as np

def compute_obb_pca(vertices):
    """Compute oriented bounding box using PCA"""

    # Step 1: Compute centroid
    centroid = np.mean(vertices, axis=0)

    # Step 2: Center vertices
    centered = vertices - centroid

    # Step 3: Compute covariance matrix
    cov_matrix = np.cov(centered.T)

    # Step 4: Eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)

    # Step 5: Sort by eigenvalue magnitude (largest first)
    idx = eigenvalues.argsort()[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Step 6: Ensure right-handed coordinate system
    eigenvectors[:, 2] = np.cross(eigenvectors[:, 0], eigenvectors[:, 1])

    # Step 7: Project vertices onto principal axes
    rotated = centered @ eigenvectors

    # Step 8: Find min/max along each axis
    min_point = np.min(rotated, axis=0)
    max_point = np.max(rotated, axis=0)

    # Compute OBB parameters
    extents = (max_point - min_point) / 2  # Half-extents
    center_local = (max_point + min_point) / 2
    center_world = eigenvectors @ center_local + centroid

    return {
        'center': center_world,
        'axes': eigenvectors,  # 3×3 rotation matrix
        'extents': extents,    # Half-extents along each axis
        'rotation_matrix': eigenvectors
    }
```

### Convex Hull Preprocessing (Performance Optimization)

**Key Insight:** The minimal bounding box depends only on the convex hull vertices.

**Benefits:**
- 10-100× speedup for dense meshes
- Maintains same final result
- Reduces vertex count dramatically

```python
from scipy.spatial import ConvexHull

def compute_obb_with_convex_hull(vertices):
    """Compute OBB using convex hull preprocessing"""

    # Compute convex hull
    hull = ConvexHull(vertices)
    hull_vertices = vertices[hull.vertices]

    # Run OBB algorithm on reduced vertex set
    return compute_obb_pca(hull_vertices)
```

### Minimal OBB Using Open3D (Highest Accuracy)

For production use, Open3D provides optimized implementations:

```python
import open3d as o3d
import numpy as np

def compute_tight_obb_open3d(vertices):
    """Compute minimal OBB using Open3D optimization"""

    # Create point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(vertices)

    # Compute minimal OBB (uses optimization, slower but tighter)
    obb = pcd.get_minimal_oriented_bounding_box()

    return {
        'center': np.array(obb.center),
        'axes': np.array(obb.R),         # 3×3 rotation matrix
        'extents': np.array(obb.extent) / 2  # Convert to half-extents
    }

def compute_fast_obb_open3d(vertices):
    """Compute OBB using Open3D PCA (faster)"""

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(vertices)

    # Fast PCA-based OBB
    obb = pcd.get_oriented_bounding_box()

    return {
        'center': np.array(obb.center),
        'axes': np.array(obb.R),
        'extents': np.array(obb.extent) / 2
    }
```

### Padding and Extension for Support Volumes

Apply appropriate padding to ensure complete overhang coverage:

**Padding Strategies:**
1. **Uniform padding:** Fixed distance in all directions
2. **Percentage-based:** Scale relative to object size
3. **Anisotropic:** Different padding per axis

**Recommended Values:**
- Horizontal (X/Y): 2-5mm padding
- Vertical extension: Down to build plate if needed

```python
def expand_obb_for_support(obb, horizontal_padding=3.0, bottom_extension=None):
    """Expand OBB with support-specific requirements"""

    # Apply horizontal padding to X and Y extents
    padded_extents = obb['extents'].copy()
    padded_extents[0] += horizontal_padding  # X
    padded_extents[1] += horizontal_padding  # Y

    # Optionally extend to build plate
    if bottom_extension is not None:
        # Calculate how far to extend downward
        current_bottom = obb['center'][2] - obb['extents'][2]
        if current_bottom > 0:
            # Extend to Z=0 (build plate)
            padded_extents[2] += current_bottom / 2
            # Shift center downward
            new_center = obb['center'].copy()
            new_center[2] -= current_bottom / 2
            obb = obb.copy()
            obb['center'] = new_center

    return {
        'center': obb['center'],
        'axes': obb['axes'],
        'extents': padded_extents
    }
```

### Collision Detection Using Separating Axis Theorem (SAT)

Ensure support volumes don't intersect the main model improperly:

**SAT Algorithm:**
- Test 15 candidate axes for two OBBs:
  - 3 face normals from OBB A
  - 3 face normals from OBB B
  - 9 cross products of edge pairs (3×3)
- If any axis shows non-overlapping projections → no collision

```python
def obb_intersects_sat(obb_a, obb_b):
    """Test if two OBBs intersect using Separating Axis Theorem"""

    def get_obb_corners(obb):
        """Get 8 corner points of OBB"""
        center = obb['center']
        axes = obb['axes']
        extents = obb['extents']

        corners = []
        for x in [-1, 1]:
            for y in [-1, 1]:
                for z in [-1, 1]:
                    local = np.array([x, y, z]) * extents
                    world = center + axes @ local
                    corners.append(world)
        return np.array(corners)

    def project_obb(obb, axis):
        """Project OBB onto axis and return min/max"""
        corners = get_obb_corners(obb)
        projections = corners @ axis
        return np.min(projections), np.max(projections)

    # Test face normals from both OBBs
    for i in range(3):
        axis = obb_a['axes'][:, i]
        min_a, max_a = project_obb(obb_a, axis)
        min_b, max_b = project_obb(obb_b, axis)
        if max_a < min_b or max_b < min_a:
            return False  # Separating axis found

        axis = obb_b['axes'][:, i]
        min_a, max_a = project_obb(obb_a, axis)
        min_b, max_b = project_obb(obb_b, axis)
        if max_a < min_b or max_b < min_a:
            return False

    # Test edge cross products
    for i in range(3):
        for j in range(3):
            axis = np.cross(obb_a['axes'][:, i], obb_b['axes'][:, j])
            length = np.linalg.norm(axis)
            if length > 1e-6:  # Skip parallel edges
                axis = axis / length
                min_a, max_a = project_obb(obb_a, axis)
                min_b, max_b = project_obb(obb_b, axis)
                if max_a < min_b or max_b < min_a:
                    return False

    return True  # No separating axis found
```

### Simplified Top-Only Attachment Check

For support blockers, we want contact only at the top of the overhang:

```python
def check_valid_support_position(support_obb, model_mesh_data):
    """Verify support volume only touches model at top surface"""

    # Create model OBB
    model_vertices = model_mesh_data.getVertices()
    model_obb = compute_obb_pca(model_vertices)

    # Check if support is mostly below the overhang
    support_top = support_obb['center'][2] + support_obb['extents'][2]
    model_bottom = model_obb['center'][2] - model_obb['extents'][2]

    # Support should be between build plate and model
    if support_top > model_bottom:
        # Acceptable - support extends to touch overhang
        return True

    return False
```

## Algorithm Performance Comparison

| Algorithm | Time Complexity | Accuracy | Use Case |
|-----------|----------------|----------|----------|
| PCA | O(n) | Good | Real-time, interactive |
| PCA + Convex Hull | O(n log n) | Good | Dense meshes |
| Open3D Minimal | O(n log n) + optimization | Best | Offline processing |
| O'Rourke (theoretical) | O(n³) | Optimal | Research only |

## Testing Strategy

1. Test OBB computation on simple shapes (cubes, cylinders)
2. Verify rotation matrices are orthonormal
3. Test convex hull optimization provides same results
4. Verify padding is applied correctly in all directions
5. Test SAT collision detection with known intersecting/non-intersecting pairs
6. Visualize OBBs by creating cube meshes at computed positions

## Common Pitfalls

- **Non-orthonormal rotation matrices** - Always ensure right-handed coordinate system
- **Confusing half-extents with full extents** - MeshBuilder uses full dimensions
- **Forgetting to apply world transformations** - OBB should be in world coordinates
- **Numerical instability** - Add epsilon values for edge parallelism checks in SAT
- **Wrong padding dimensions** - Remember extents are half-dimensions

## Success Criteria

- [ ] OBB correctly oriented along principal axes
- [ ] Minimal volume within 10% of theoretical minimum
- [ ] Convex hull optimization provides correct results
- [ ] Padding applied correctly in all directions
- [ ] SAT correctly detects all collisions
- [ ] Performance acceptable for interactive use (<100ms)

## Performance Targets

- **PCA OBB:** <1ms for meshes up to 10,000 vertices
- **Convex Hull + PCA:** <10ms for meshes up to 100,000 vertices
- **Open3D Minimal:** <100ms for meshes up to 50,000 vertices
- **SAT Test:** <1ms per pair of OBBs

## Related Tasks

- **Requires:** Task 1 - Mesh Data Access
- **Requires:** Task 2 - Overhang Detection Algorithms
- **Next:** Task 4 - Plugin Architecture Integration
- **Uses this:** Task 5 - Complete Workflow Implementation

## References

- O'Rourke, J. (1985). "Finding minimal enclosing boxes"
- Open3D documentation: http://www.open3d.org/
- Scipy ConvexHull: https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html
- CGAL OBB optimization: https://doc.cgal.org/latest/Bounding_volumes/
- Separating Axis Theorem tutorial: https://www.geometrictools.com/
