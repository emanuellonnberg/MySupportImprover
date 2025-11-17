# Task 2: Overhang Detection Algorithms

**Priority:** High - Core Functionality
**Estimated Complexity:** High
**Dependencies:** Task 1 (Mesh Data Access)

## Overview

Implement algorithms to detect overhanging geometry in 3D meshes using normal vector analysis, face adjacency graphs, and connectivity-based region finding.

## Objectives

1. Calculate overhang angles using normal vector dot product analysis
2. Build face adjacency graphs for connectivity information
3. Apply connectivity smoothing to reduce false positives
4. Identify connected overhang regions from seed points
5. Handle special cases (small features, complex geometry)

## Implementation Details

### Angle-Based Overhang Detection

Overhang detection relies on analyzing the **angle between each triangle's normal vector and the vertical build direction**.

**Mathematical Foundation:**
- Given face normal `n` and downward build direction `[0, 0, -1]`
- Angle θ = arccos(|n_z|) where n_z is the z-component of the unit normal
- Threshold typically **45° for PLA, 30-40° for ABS**

```python
import numpy as np

def detect_overhangs(mesh_data, threshold_angle=45.0):
    """Detect overhang faces using normal vector analysis"""

    # Get face normals (compute if not available)
    if mesh_data.hasNormals():
        normals = mesh_data.getNormals()
    else:
        normals = compute_face_normals(mesh_data)

    # Build direction (downward)
    build_direction = np.array([[0., 0., -1.0]])

    # Compute angles for all faces (vectorized)
    dot_products = np.dot(build_direction, normals.T)
    angles = np.degrees(np.arccos(np.clip(dot_products, -1.0, 1.0))).flatten()

    # Identify overhangs
    overhang_mask = angles > threshold_angle
    overhang_face_ids = np.where(overhang_mask)[0]

    return overhang_face_ids, angles

def compute_face_normals(mesh_data):
    """Calculate face normals from vertices and indices"""
    vertices = mesh_data.getVertices()
    indices = mesh_data.getIndices()

    # Get triangle vertices
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]

    # Compute normals via cross product
    edge1 = v1 - v0
    edge2 = v2 - v0
    normals = np.cross(edge1, edge2)

    # Normalize
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(lengths, 1e-10)

    return normals
```

### Face Adjacency Graph Construction

Build an adjacency graph to identify connected faces sharing edges:

```python
from collections import deque

def build_face_adjacency_graph(mesh_data):
    """Build adjacency list for mesh faces"""
    indices = mesh_data.getIndices()
    face_count = mesh_data.getFaceCount()

    # Create edge-to-face mapping
    edge_to_faces = {}
    for face_id, face in enumerate(indices):
        for i in range(3):
            # Create edge key (sorted for consistency)
            edge = tuple(sorted([face[i], face[(i+1)%3]]))
            if edge not in edge_to_faces:
                edge_to_faces[edge] = []
            edge_to_faces[edge].append(face_id)

    # Build adjacency list
    adjacency = {i: [] for i in range(face_count)}
    for edge, faces in edge_to_faces.items():
        if len(faces) == 2:  # Interior edge
            adjacency[faces[0]].append(faces[1])
            adjacency[faces[1]].append(faces[0])

    return adjacency
```

### Connectivity-Based Region Finding

Use breadth-first search to identify connected overhang regions from a seed face:

```python
def find_connected_overhang_region(seed_face_id, overhang_mask, adjacency):
    """BFS to find connected overhang region from seed face"""
    if not overhang_mask[seed_face_id]:
        return []

    visited = set()
    queue = deque([seed_face_id])
    region = []

    while queue:
        face_id = queue.popleft()

        if face_id in visited:
            continue

        # Check if this face is an overhang
        if not overhang_mask[face_id]:
            continue

        visited.add(face_id)
        region.append(face_id)

        # Add adjacent faces to queue
        for neighbor_id in adjacency.get(face_id, []):
            if neighbor_id not in visited:
                queue.append(neighbor_id)

    return region
```

### Connectivity Smoothing

Reduce false positives from mesh tessellation by averaging angles across adjacent faces:

```python
def smooth_angles_by_connectivity(angles, adjacency):
    """Smooth overhang angles using face adjacency"""
    smoothed_angles = angles.copy()

    for face_id in range(len(angles)):
        # Get connected faces
        neighbors = adjacency.get(face_id, [])
        local_faces = [face_id] + neighbors

        # Average angles
        smoothed_angles[face_id] = np.mean(angles[local_faces])

    return smoothed_angles
```

### Handling Small Overhang Features

Detect and classify overhang regions by size and severity:

```python
def classify_overhang_regions(regions, vertices, indices, angles):
    """Classify overhang regions by size and severity"""
    classified = []

    for region_face_ids in regions:
        # Extract vertices for this region
        region_faces = indices[region_face_ids]
        region_vertex_ids = np.unique(region_faces.flatten())
        region_vertices = vertices[region_vertex_ids]

        # Calculate surface area
        surface_area = calculate_region_surface_area(region_faces, vertices)

        # Get maximum angle
        max_angle = np.max(angles[region_face_ids])
        avg_angle = np.mean(angles[region_face_ids])

        classified.append({
            'face_ids': region_face_ids,
            'vertex_count': len(region_vertex_ids),
            'surface_area': surface_area,
            'max_angle': max_angle,
            'avg_angle': avg_angle,
            'severity': 'high' if max_angle > 60 else 'medium' if max_angle > 50 else 'low'
        })

    return classified

def calculate_region_surface_area(faces, vertices):
    """Calculate total surface area of triangular faces"""
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]

    # Triangle area = 0.5 * |cross(edge1, edge2)|
    edge1 = v1 - v0
    edge2 = v2 - v0
    cross_products = np.cross(edge1, edge2)
    areas = 0.5 * np.linalg.norm(cross_products, axis=1)

    return np.sum(areas)
```

## Algorithm Performance

- **Angle computation:** O(n) where n = number of faces (fully vectorized)
- **Adjacency graph:** O(n) construction time
- **Region finding:** O(n) per region with BFS
- **Smoothing:** O(n × k) where k = average neighbor count (~6 for typical meshes)

## Testing Strategy

1. Test with simple geometric shapes (cubes, pyramids, overhanging cylinders)
2. Verify angle calculations match expected values
3. Test adjacency graph construction on known meshes
4. Verify connected region finding with manual inspection
5. Test smoothing reduces noise on tessellated curved surfaces
6. Export detected overhang faces as separate STL for visualization

## Common Pitfalls

- **Forgetting to normalize normals** - Leads to incorrect angle calculations
- **Not handling vertex vs face normals** - MeshData may store either
- **Ignoring boundary edges** - Single-face edges need special handling
- **Over-smoothing** - Too much smoothing can merge distinct overhang regions
- **Numerical precision** - Use `np.clip()` for arccos to avoid domain errors

## Success Criteria

- [ ] Correctly identifies overhang faces within 1° of theoretical values
- [ ] Adjacency graph correctly identifies all face neighbors
- [ ] Connected region finding isolates distinct overhang areas
- [ ] Smoothing reduces noise without losing overhang boundaries
- [ ] Handles edge cases (vertical walls, horizontal surfaces)
- [ ] Performance is acceptable for meshes up to 100,000 faces

## Special Considerations

### Arc Overhang Support
For extremely steep overhangs (60-90°), consider arc overhang printing techniques that use:
- Recursive arc generation
- Extremely slow print speeds (1-5 mm/s)
- Maximum cooling
- Reference: https://github.com/stmcculloch/arc-overhang

### PySLM Library Reference
The PySLM library provides a reference implementation:
- Repository: https://github.com/drlukeparry/pyslm
- Includes connectivity-based smoothing
- Handles mesh tessellation artifacts

## Related Tasks

- **Requires:** Task 1 - Mesh Data Access
- **Next:** Task 3 - Bounding Volume Generation
- **Uses this:** Task 5 - Complete Workflow Implementation

## References

- PySLM: https://github.com/drlukeparry/pyslm
- Arc Overhang: https://github.com/stmcculloch/arc-overhang
- NumPy documentation for vectorized operations
