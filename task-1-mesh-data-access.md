# Task 1: Accessing Mesh Data from Cura Scene Nodes

**Priority:** Foundation/Required First
**Estimated Complexity:** Medium
**Dependencies:** None

## Overview

Establish the foundation for mesh analysis by implementing methods to access and manipulate 3D mesh data from Cura's scene graph using the Uranium framework.

## Objectives

1. Retrieve mesh data from CuraSceneNode objects
2. Extract vertex, normal, and index arrays
3. Apply world transformations to mesh data
4. Create new mesh geometry programmatically
5. Export mesh data for testing and verification

## Implementation Details

### Accessing Scene Node Mesh Data

Cura's Uranium framework provides a clean Python API for accessing 3D mesh data through the **CuraSceneNode** class located in `cura/Scene/CuraSceneNode.py`.

**Key Methods:**
- `getMeshData()` - Returns raw MeshData object
- `getMeshDataTransformed()` - Returns mesh with node's world transformation applied
- `getTransformed(node.getWorldTransformation())` - Manual transformation application

**MeshData Structure** (`UM/Mesh/MeshData.py`):
- `_vertices` - Vertex positions (Nx3 float32)
- `_normals` - Vertex normals (Nx3 float32)
- `_indices` - Triangle face indices (Mx3 int32)
- `_colors` - Optional color data
- `_uvs` - Optional UV coordinates

### Code Example: Iterating Scene Nodes

```python
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.CuraApplication import CuraApplication

# Iterate through scene to find mesh nodes
scene = CuraApplication.getInstance().getController().getScene()
for node in DepthFirstIterator(scene.getRoot()):
    if isinstance(node, CuraSceneNode) and node.getMeshData() and node.isVisible():
        # Get transformed mesh data
        mesh_data = node.getMeshData().getTransformed(node.getWorldTransformation())

        # Extract geometry arrays
        vertices = mesh_data.getVertices()  # numpy array (N, 3)
        normals = mesh_data.getNormals()    # numpy array (N, 3)

        if mesh_data.hasIndices():
            indices = mesh_data.getIndices()  # numpy array (M, 3)
            face_count = mesh_data.getFaceCount()
```

### Creating New Mesh Geometry

Use the **MeshBuilder** class from `UM/Mesh/MeshBuilder.py` for constructing meshes:

```python
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Math.Vector import Vector

# Create oriented bounding box mesh
mesh_builder = MeshBuilder()
mesh_builder.addCube(
    width=extent_x * 2,
    height=extent_y * 2,
    depth=extent_z * 2,
    center=center_position
)

# IMPORTANT: Always calculate normals
mesh_builder.calculateNormals()

# Build final MeshData
mesh_data = mesh_builder.build()
```

**Critical:** Always call `calculateNormals()` or `calculateNormalsFromIndexedVertices()` after constructing geometry, as many operations depend on correct normal vectors.

### Exporting Mesh Data for Testing

Save mesh data to disk for external algorithm testing using binary STL format:

```python
import struct

def export_mesh_binary_stl(mesh_data, filepath):
    """Export mesh to binary STL format for testing"""
    with open(filepath, 'wb') as f:
        # 80-byte header
        f.write(b'\x00' * 80)

        # Face count
        face_count = mesh_data.getFaceCount()
        f.write(struct.pack("<I", int(face_count)))

        # Write triangles
        vertices = mesh_data.getVertices()
        indices = mesh_data.getIndices()

        for face in indices:
            v1, v2, v3 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

            # Normal (can compute or write zero)
            f.write(struct.pack("<fff", 0.0, 0.0, 0.0))
            # Vertices
            f.write(struct.pack("<fff", v1[0], v1[1], v1[2]))
            f.write(struct.pack("<fff", v2[0], v2[1], v2[2]))
            f.write(struct.pack("<fff", v3[0], v3[1], v3[2]))
            # Attribute byte count
            f.write(struct.pack("<H", 0))
```

## Testing Strategy

1. Create a simple test script that iterates all scene nodes
2. Export mesh data to STL and verify in external viewer
3. Create simple geometric shapes with MeshBuilder
4. Verify transformations are applied correctly
5. Check normal vector calculations are correct

## Common Pitfalls

- **Forgetting to check `hasIndices()`** before accessing indices
- **Not applying world transformations** for positioned/rotated objects
- **Missing `calculateNormals()` call** after MeshBuilder operations
- **Ignoring invisible or non-mesh nodes** in scene iteration

## Success Criteria

- [ ] Can iterate scene and extract all mesh nodes
- [ ] Can access vertices, normals, and indices as numpy arrays
- [ ] Can apply world transformations correctly
- [ ] Can create new mesh geometry with MeshBuilder
- [ ] Can export mesh data to STL for verification
- [ ] All mesh normals are correctly calculated

## Related Tasks

- **Next:** Task 2 - Overhang Detection Algorithms
- **Uses this:** Task 3 - Bounding Volume Generation
- **Uses this:** Task 4 - Plugin Architecture Integration

## References

- `cura/Scene/CuraSceneNode.py` - Scene node implementation
- `UM/Mesh/MeshData.py` - Mesh data structure
- `UM/Mesh/MeshBuilder.py` - Mesh construction utilities
- `UM/Scene/Iterator/DepthFirstIterator.py` - Scene traversal
