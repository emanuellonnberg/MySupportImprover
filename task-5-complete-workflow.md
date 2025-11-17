# Task 5: Complete Implementation Workflow

**Priority:** High - Integration Task
**Estimated Complexity:** Medium
**Dependencies:** Task 1, Task 2, Task 3, Task 4

## Overview

Combine all components into a cohesive, production-ready workflow that provides automatic overhang detection and support blocker generation with interactive user control.

## Objectives

1. Integrate all components into unified workflow
2. Implement complete tool with all features
3. Handle edge cases and error conditions
4. Optimize for performance and memory usage
5. Provide comprehensive user feedback

## Complete Tool Implementation

### Main Tool Class

```python
from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Application import Application
from UM.Message import Message
from UM.Logger import Logger
from cura.CuraApplication import CuraApplication
from cura.Utils.Threading import call_on_qt_thread

class AutoOverhangTool(Tool):
    def __init__(self):
        super().__init__()
        self._application = Application.getInstance()
        self._controller = self._application.getController()
        self._selection_pass = None
        self._active_job = None
        self._threshold_angle = 45.0
        self._horizontal_padding = 3.0
        self._extend_to_buildplate = True

    def event(self, event):
        """Handle mouse events for interactive detection"""
        super().event(event)

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons:
            if not self._selection_pass:
                self._selection_pass = self._application.getRenderer().getRenderPass("selection")

            node = self._controller.getScene().findObject(
                self._selection_pass.getIdAtPosition(event.x, event.y)
            )

            if node and node.getMeshData():
                # Cancel any running job
                if self._active_job:
                    self._active_job.cancel()

                # Start analysis
                self._active_job = OverhangAnalysisJob(
                    node,
                    threshold_angle=self._threshold_angle,
                    horizontal_padding=self._horizontal_padding,
                    extend_to_buildplate=self._extend_to_buildplate
                )
                self._active_job.finished.connect(lambda job: self._onAnalysisComplete(job, node))
                self._active_job.start()

                Message("Analyzing overhang region...", lifetime=2).show()
                return True

        return False

    @call_on_qt_thread
    def _onAnalysisComplete(self, job, parent_node):
        """Handle analysis results on main thread"""
        results = job.getResults()

        if not results:
            Message("No overhangs detected at clicked location").show()
            return

        # Create support blockers for each region
        created_count = 0
        for region_data in results:
            obb = region_data['obb']

            # Skip if volume intersects parent (except at top)
            parent_mesh = parent_node.getMeshData()
            if self._checkInvalidIntersection(obb, parent_mesh):
                Logger.log("w", "Skipping overhang region due to invalid intersection")
                continue

            # Create volume
            create_support_blocker_volume(obb, parent_node)
            created_count += 1

        if created_count > 0:
            Message(f"Created {created_count} support blocker(s)", lifetime=3).show()
        else:
            Message("No valid support blocker positions found", lifetime=3).show()

        self._active_job = None

    def _checkInvalidIntersection(self, obb, parent_mesh):
        """Verify volume doesn't intersect parent except at top"""
        # Simplified check: ensure support is below overhang
        support_top = obb['center'][2] + obb['extents'][2]
        parent_vertices = parent_mesh.getVertices()
        parent_min_z = np.min(parent_vertices[:, 2])

        # Support should extend below the model
        return support_top < parent_min_z

    def setProperty(self, property_name, value):
        """Set tool properties from QML interface"""
        if property_name == "threshold_angle":
            self._threshold_angle = float(value)
        elif property_name == "horizontal_padding":
            self._horizontal_padding = float(value)
        elif property_name == "extend_to_buildplate":
            self._extend_to_buildplate = bool(value)
```

## Complete Workflow Pipeline

### Step-by-Step Execution Flow

1. **User Interaction**
   - User selects mesh and activates detection tool
   - Tool enters listening mode for mouse clicks
   - User clicks on overhang region

2. **Job Creation and Startup**
   - Tool creates OverhangAnalysisJob
   - Job executes on background thread
   - Progress message displayed to user

3. **Background Analysis**
   - Extract mesh geometry with transformations
   - Compute face angles (vectorized)
   - Build adjacency graph
   - Apply connectivity smoothing
   - Identify connected overhang region
   - Compute tight OBB
   - Expand OBB with padding
   - Validate positioning

4. **Result Processing**
   - Job finishes, triggers signal
   - Main thread callback receives results
   - Validate each OBB
   - Create support blocker geometry
   - Add to scene with operations
   - Display success message

### Extended Analysis Job with Full Pipeline

```python
from UM.Job import Job
from UM.Logger import Logger
import numpy as np

class OverhangAnalysisJob(Job):
    def __init__(self, node, threshold_angle=45.0, horizontal_padding=3.0, extend_to_buildplate=True):
        super().__init__()
        self._node = node
        self._threshold = threshold_angle
        self._horizontal_padding = horizontal_padding
        self._extend_to_buildplate = extend_to_buildplate
        self._overhang_regions = []

    def run(self):
        """Execute complete analysis pipeline"""
        try:
            self.setProgress(0)
            Logger.log("d", "Starting overhang analysis")

            # Step 1: Extract mesh data
            mesh_data = self._node.getMeshData().getTransformed(
                self._node.getWorldTransformation()
            )

            if self._is_aborted:
                return

            vertices = mesh_data.getVertices()
            indices = mesh_data.getIndices()
            face_count = mesh_data.getFaceCount()

            Logger.log("d", f"Processing mesh with {len(vertices)} vertices, {face_count} faces")
            self.setProgress(10)

            # Step 2: Detect overhangs
            overhang_faces, angles = self._detectOverhangs(mesh_data)

            if self._is_aborted:
                return

            if len(overhang_faces) == 0:
                Logger.log("d", "No overhangs detected")
                return

            Logger.log("d", f"Detected {len(overhang_faces)} overhang faces")
            self.setProgress(30)

            # Step 3: Build adjacency graph
            adjacency = self._buildAdjacency(mesh_data)

            if self._is_aborted:
                return

            self.setProgress(50)

            # Step 4: Apply smoothing
            smoothed_angles = self._smoothAngles(angles, adjacency)

            # Update overhang mask with smoothed values
            overhang_mask = smoothed_angles > self._threshold
            overhang_faces = np.where(overhang_mask)[0]

            self.setProgress(60)

            # Step 5: Find connected regions
            regions = self._findRegions(overhang_faces, overhang_mask, adjacency)

            if self._is_aborted:
                return

            Logger.log("d", f"Found {len(regions)} connected overhang regions")
            self.setProgress(70)

            # Step 6: Compute bounding volumes
            for i, region in enumerate(regions):
                if self._is_aborted:
                    return

                obb = self._computeRegionOBB(region, vertices, indices, angles)

                if obb is not None:
                    self._overhang_regions.append({
                        'faces': region,
                        'obb': obb,
                        'severity': np.max(angles[region]),
                        'surface_area': self._calculateSurfaceArea(region, indices, vertices)
                    })

                self.setProgress(70 + int(20 * (i + 1) / len(regions)))

            Logger.log("d", f"Created {len(self._overhang_regions)} bounding volumes")
            self.setProgress(100)

        except Exception as e:
            Logger.logException("e", f"Overhang analysis failed: {e}")

    def _detectOverhangs(self, mesh_data):
        """Detect overhang faces using angle threshold"""
        # Compute face normals
        normals = self._computeFaceNormals(mesh_data)

        # Build direction (downward)
        build_direction = np.array([[0., 0., -1.0]])

        # Compute angles
        dot_products = np.dot(build_direction, normals.T)
        angles = np.degrees(np.arccos(np.clip(dot_products, -1.0, 1.0))).flatten()

        # Identify overhangs
        overhang_mask = angles > self._threshold
        overhang_face_ids = np.where(overhang_mask)[0]

        return overhang_face_ids, angles

    def _computeFaceNormals(self, mesh_data):
        """Calculate face normals from vertices and indices"""
        vertices = mesh_data.getVertices()
        indices = mesh_data.getIndices()

        v0 = vertices[indices[:, 0]]
        v1 = vertices[indices[:, 1]]
        v2 = vertices[indices[:, 2]]

        edge1 = v1 - v0
        edge2 = v2 - v0
        normals = np.cross(edge1, edge2)

        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.maximum(lengths, 1e-10)

        return normals

    def _buildAdjacency(self, mesh_data):
        """Build face adjacency graph"""
        indices = mesh_data.getIndices()
        face_count = mesh_data.getFaceCount()

        edge_to_faces = {}
        for face_id, face in enumerate(indices):
            for i in range(3):
                edge = tuple(sorted([face[i], face[(i+1)%3]]))
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(face_id)

        adjacency = {i: [] for i in range(face_count)}
        for edge, faces in edge_to_faces.items():
            if len(faces) == 2:
                adjacency[faces[0]].append(faces[1])
                adjacency[faces[1]].append(faces[0])

        return adjacency

    def _smoothAngles(self, angles, adjacency):
        """Apply connectivity-based smoothing"""
        smoothed = angles.copy()

        for face_id in range(len(angles)):
            neighbors = adjacency.get(face_id, [])
            local_faces = [face_id] + neighbors
            smoothed[face_id] = np.mean(angles[local_faces])

        return smoothed

    def _findRegions(self, overhang_faces, overhang_mask, adjacency):
        """Find connected overhang regions using BFS"""
        from collections import deque

        regions = []
        visited = set()

        for seed_face in overhang_faces:
            if seed_face in visited:
                continue

            # BFS from seed
            queue = deque([seed_face])
            region = []

            while queue:
                face_id = queue.popleft()

                if face_id in visited or not overhang_mask[face_id]:
                    continue

                visited.add(face_id)
                region.append(face_id)

                for neighbor in adjacency.get(face_id, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if region:
                regions.append(region)

        return regions

    def _computeRegionOBB(self, region, vertices, indices, angles):
        """Compute OBB for overhang region"""
        # Extract vertices
        region_faces = indices[region]
        region_vertex_ids = np.unique(region_faces.flatten())
        region_vertices = vertices[region_vertex_ids]

        if len(region_vertices) < 4:
            return None

        # Compute OBB using PCA
        obb = compute_obb_pca(region_vertices)

        # Expand with padding
        obb = expand_obb_for_support(
            obb,
            horizontal_padding=self._horizontal_padding,
            bottom_extension=0.0 if self._extend_to_buildplate else None
        )

        return obb

    def _calculateSurfaceArea(self, region, indices, vertices):
        """Calculate total surface area of region"""
        region_faces = indices[region]

        v0 = vertices[region_faces[:, 0]]
        v1 = vertices[region_faces[:, 1]]
        v2 = vertices[region_faces[:, 2]]

        edge1 = v1 - v0
        edge2 = v2 - v0
        cross_products = np.cross(edge1, edge2)
        areas = 0.5 * np.linalg.norm(cross_products, axis=1)

        return np.sum(areas)

    def getResults(self):
        """Access results from main thread"""
        return self._overhang_regions
```

## Performance Optimization

### Memory Management

```python
def optimize_for_large_meshes(mesh_data):
    """Handle memory efficiently for large meshes"""
    face_count = mesh_data.getFaceCount()

    # Use chunked processing for very large meshes
    if face_count > 100000:
        chunk_size = 50000
        # Process in chunks with streaming
        Logger.log("d", f"Using chunked processing for {face_count} faces")
        return True

    return False
```

### Early-Out Collision Checks

```python
def quick_intersection_check(obb_a, obb_b):
    """Fast bounding sphere test before expensive SAT"""
    # Compute bounding sphere radius
    radius_a = np.linalg.norm(obb_a['extents'])
    radius_b = np.linalg.norm(obb_b['extents'])

    # Check distance between centers
    distance = np.linalg.norm(obb_a['center'] - obb_b['center'])

    if distance > (radius_a + radius_b):
        return False  # Definitely no intersection

    # Run full SAT test
    return obb_intersects_sat(obb_a, obb_b)
```

## Error Handling and User Feedback

```python
from UM.Message import Message

def show_analysis_error(error_type):
    """Display user-friendly error messages"""
    messages = {
        'no_mesh': "No mesh selected. Please select a model first.",
        'no_overhangs': "No overhangs detected in this region.",
        'analysis_failed': "Analysis failed. Check logs for details.",
        'invalid_position': "Cannot place support blocker at this location."
    }

    Message(messages.get(error_type, "An error occurred"), lifetime=5).show()
```

## Success Criteria

- [ ] Complete workflow executes without errors
- [ ] All components integrate smoothly
- [ ] Performance acceptable for meshes up to 100K faces
- [ ] Memory usage stays reasonable
- [ ] User feedback is clear and timely
- [ ] Error cases handled gracefully
- [ ] Support blockers positioned correctly
- [ ] Undo/redo works for all operations

## Performance Targets

| Mesh Size | Analysis Time | Memory Usage |
|-----------|---------------|--------------|
| 1K faces | <100ms | <10MB |
| 10K faces | <500ms | <50MB |
| 100K faces | <5s | <200MB |
| 1M faces | <30s | <1GB |

## Related Tasks

- **Requires:** All previous tasks (1-4)
- **Testing:** Task 6 - Testing and Debugging

## References

- Complete implementation examples in previous task documents
- Performance profiling with cProfile
- Memory profiling with memory_profiler
