# Task 4: Integrating Mesh Analysis into Cura's Plugin Architecture

**Priority:** Critical - Required for Deployment
**Estimated Complexity:** High
**Dependencies:** Task 1, Task 2, Task 3

## Overview

Integrate the mesh analysis algorithms into Cura's plugin architecture using the Tool pattern for interactive placement, the Job pattern for background processing, and proper scene graph manipulation through Operations.

## Objectives

1. Create a Tool plugin for interactive viewport interaction
2. Implement background processing using the Job pattern
3. Create modifier volumes (support blockers) programmatically
4. Handle scene graph operations with proper undo/redo
5. Implement thread-safe UI updates
6. Register plugin with proper metadata

## Implementation Details

### Tool Pattern for Interactive Mesh Analysis

Extend the `Tool` base class to handle viewport interaction:

```python
from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Application import Application
from cura.CuraApplication import CuraApplication

class OverhangDetectionTool(Tool):
    def __init__(self):
        super().__init__()
        self._controller = Application.getInstance().getController()
        self._selection_pass = None

    def event(self, event):
        """Handle mouse events for interactive detection"""
        super().event(event)

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons:
            # Get rendering passes for picking
            if not self._selection_pass:
                self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")

            # Find clicked node
            picked_node = self._controller.getScene().findObject(
                self._selection_pass.getIdAtPosition(event.x, event.y)
            )

            if picked_node and picked_node.getMeshData():
                # Start overhang detection at click position
                self._detectOverhangAtPoint(picked_node, event.x, event.y)
                return True

        return False
```

**Key Components:**
- `event()` - Handles mouse and keyboard events
- `PickingPass` - Maps screen coordinates to 3D mesh positions
- `getIdAtPosition()` - Retrieves scene node under cursor

### Job Pattern for Background Processing

Implement computationally intensive analysis on background threads:

```python
from UM.Job import Job
from UM.Message import Message
from UM.Logger import Logger
import numpy as np

class OverhangAnalysisJob(Job):
    def __init__(self, node, threshold_angle=45.0):
        super().__init__()
        self._node = node
        self._threshold = threshold_angle
        self._overhang_regions = []

    def run(self):
        """Execute on background thread"""
        # Show progress message
        self.setProgress(0)

        try:
            # Get mesh data
            mesh_data = self._node.getMeshData().getTransformed(
                self._node.getWorldTransformation()
            )

            if self._is_aborted:
                return

            self.setProgress(20)

            # Detect overhangs
            overhang_faces, angles = detect_overhangs(mesh_data, self._threshold)

            if self._is_aborted:
                return

            self.setProgress(50)

            # Build adjacency graph
            adjacency = build_face_adjacency_graph(mesh_data)

            self.setProgress(70)

            # Find connected regions
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

            if self._is_aborted:
                return

            self.setProgress(90)

            # Compute bounding volumes for each region
            vertices = mesh_data.getVertices()
            indices = mesh_data.getIndices()

            for region in regions:
                # Extract vertices from this region
                region_faces = indices[region]
                region_vertex_ids = np.unique(region_faces.flatten())
                region_vertices = vertices[region_vertex_ids]

                # Compute OBB
                obb = compute_obb_pca(region_vertices)
                obb = expand_obb_for_support(obb, horizontal_padding=3.0)

                self._overhang_regions.append({
                    'faces': region,
                    'obb': obb,
                    'severity': np.max(angles[region])
                })

            self.setProgress(100)

        except Exception as e:
            Logger.logException("e", f"Overhang analysis failed: {e}")

    def getResults(self):
        """Access results from main thread"""
        return self._overhang_regions
```

**Job Best Practices:**
- Always check `self._is_aborted` periodically
- Call `setProgress()` to update UI indicators
- Handle exceptions gracefully with logging
- Use `finished` signal to return results to main thread

### Creating Modifier Volumes Programmatically

Build support blocker nodes with proper decorators:

```python
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from cura.Settings.SettingOverrideDecorator import SettingOverrideDecorator
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Math.Vector import Vector
from UM.Math.Matrix import Matrix
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.SetTransformOperation import SetTransformOperation
from cura.CuraApplication import CuraApplication

def create_support_blocker_volume(obb, parent_node=None):
    """Create support blocker mesh from OBB parameters"""

    # Build cube mesh at origin
    mesh_builder = MeshBuilder()
    mesh_builder.addCube(
        width=obb['extents'][0] * 2,
        height=obb['extents'][1] * 2,
        depth=obb['extents'][2] * 2,
        center=Vector(0, 0, 0)
    )
    mesh_builder.calculateNormals()  # CRITICAL!
    mesh_data = mesh_builder.build()

    # Create scene node
    node = CuraSceneNode()
    node.setName("Support Blocker")
    node.setMeshData(mesh_data)
    node.setSelectable(True)

    # Add required decorators
    active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
    node.addDecorator(BuildPlateDecorator(active_build_plate))

    # Mark as support blocker
    node.addDecorator(SettingOverrideDecorator())
    node.callDecoration("setSettingOverride", "anti_overhang_mesh", True)

    # Create transformation matrix from OBB orientation
    rotation_matrix = Matrix()
    rotation_matrix._data[0:3, 0:3] = obb['axes']

    # Add to scene with operations for undo support
    scene = CuraApplication.getInstance().getController().getScene()
    op = GroupedOperation()
    op.addOperation(AddSceneNodeOperation(node, parent_node or scene.getRoot()))

    # Apply transformation
    full_transform = Matrix()
    full_transform.setByTranslation(Vector(obb['center'][0], obb['center'][1], obb['center'][2]))
    full_transform.multiply(rotation_matrix)

    op.addOperation(SetTransformOperation(node, full_transform))

    op.push()  # Execute and add to undo stack

    return node
```

**Modifier Mesh Types:**
- `anti_overhang_mesh` - Support blocker
- `support_mesh` - Support enforcer
- `infill_mesh` - Custom infill region
- `cutting_mesh` - Boolean subtraction

### Thread-Safe UI Updates

Use the `@call_on_qt_thread` decorator for thread safety:

```python
from cura.Utils.Threading import call_on_qt_thread
from UM.Message import Message

class OverhangDetectionTool(Tool):
    # ... previous code ...

    def _detectOverhangAtPoint(self, node, screen_x, screen_y):
        """Start overhang detection analysis"""
        # Cancel any running job
        if self._active_job:
            self._active_job.cancel()

        # Start analysis
        self._active_job = OverhangAnalysisJob(node, threshold_angle=45.0)
        self._active_job.finished.connect(lambda job: self._onAnalysisComplete(job, node))
        self._active_job.start()

        Message("Analyzing overhang region...", lifetime=2).show()

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
            create_support_blocker_volume(obb, parent_node)
            created_count += 1

        Message(f"Created {created_count} support blocker(s)").show()
        self._active_job = None
```

### Plugin Registration

Create proper `__init__.py` with metadata and registration:

```python
# plugin/__init__.py
from . import OverhangDetectionTool

def getMetaData():
    return {
        "tool": {
            "name": "Overhang Detector",
            "description": "Automatically detect overhangs and create support volumes",
            "icon": "icon.svg",
            "tool_panel": "OverhangDetectionPanel.qml",  # Optional QML UI
            "weight": 10
        }
    }

def register(app):
    return {"tool": OverhangDetectionTool.OverhangDetectionTool()}
```

**Metadata Fields:**
- `name` - Display name in UI
- `description` - Tooltip text
- `icon` - Path to SVG icon file
- `tool_panel` - Optional QML interface
- `weight` - Tool ordering priority

### Optional: QML Configuration Panel

Create a settings panel for the tool:

```qml
// OverhangDetectionPanel.qml
import QtQuick 2.7
import QtQuick.Controls 2.0
import UM 1.1 as UM

Item {
    width: childrenRect.width
    height: childrenRect.height

    Column {
        spacing: UM.Theme.getSize("default_margin").height

        Label {
            text: "Overhang Detection Settings"
            font: UM.Theme.getFont("large")
        }

        Row {
            spacing: UM.Theme.getSize("default_margin").width

            Label {
                text: "Threshold Angle:"
                anchors.verticalCenter: parent.verticalCenter
            }

            TextField {
                id: thresholdField
                text: "45"
                validator: IntValidator { bottom: 0; top: 90 }
                onTextChanged: {
                    // Update tool settings
                    UM.ActiveTool.setProperty("threshold_angle", parseInt(text))
                }
            }

            Label {
                text: "°"
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Row {
            spacing: UM.Theme.getSize("default_margin").width

            Label {
                text: "Horizontal Padding:"
                anchors.verticalCenter: parent.verticalCenter
            }

            TextField {
                id: paddingField
                text: "3.0"
                validator: DoubleValidator { bottom: 0; top: 20 }
            }

            Label {
                text: "mm"
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Button {
            text: "Detect All Overhangs"
            onClicked: {
                UM.ActiveTool.triggerAction("detect_all")
            }
        }
    }
}
```

## Best Practices from Successful Plugins

### MeshTools Plugin Patterns
Reference: https://github.com/fieldOfView/Cura-MeshTools

1. Always verify mesh normals after geometry creation
2. Use trimesh library for complex geometric operations
3. Convert between MeshData and trimesh.Trimesh formats
4. Implement proper error handling and user feedback

### CustomSupportEraserPlus Patterns
Reference: https://github.com/5axes/CustomSupportEraserPlus

1. Interactive tool implementation with picking
2. Custom shape generation
3. Modifier mesh creation and management
4. Coordinate transformation handling

## Testing Strategy

1. Test tool activation and deactivation
2. Verify mouse event handling and picking
3. Test job execution and cancellation
4. Verify thread-safe UI updates
5. Test scene node creation and transformation
6. Verify undo/redo functionality
7. Test plugin loading and registration

## Common Pitfalls

- **Forgetting `calculateNormals()`** - Results in black meshes
- **Updating scene from background thread** - Qt threading violations
- **Missing decorators** - Nodes won't behave as modifiers
- **Wrong transformation order** - Translation must come before rotation
- **Not using GroupedOperation** - No undo/redo support
- **Forgetting to check `_is_aborted`** - Jobs can't be cancelled
- **Missing `@call_on_qt_thread`** - UI updates from wrong thread

## Success Criteria

- [ ] Tool activates and appears in Cura toolbar
- [ ] Mouse clicks correctly select mesh nodes
- [ ] Analysis runs on background thread without blocking UI
- [ ] Progress updates display correctly
- [ ] Support blockers created at correct positions
- [ ] Support blockers properly oriented and scaled
- [ ] Undo/redo works correctly
- [ ] No threading errors in logs
- [ ] Plugin loads without errors

## Version Compatibility

Test against target Cura versions:
- **Cura 4.x:** Older decorator patterns
- **Cura 5.x:** Updated scene graph API
- **Reference:** https://github.com/Ultimaker/Cura/wiki/CuraAPI-and-SDK-Versions

## Performance Considerations

- Use convex hull preprocessing for dense meshes
- Implement early-out collision checks
- Cache rendering passes and frequently used objects
- Use streaming for very large models
- Implement chunked processing with progress updates

## Related Tasks

- **Requires:** Task 1 - Mesh Data Access
- **Requires:** Task 2 - Overhang Detection Algorithms
- **Requires:** Task 3 - Bounding Volume Generation
- **Next:** Task 5 - Complete Workflow Implementation
- **Testing:** Task 6 - Testing and Debugging

## References

- Cura Tool API: `UM/Tool.py`
- Job pattern: `UM/Job.py`
- Scene operations: `UM/Operations/`
- MeshTools: https://github.com/fieldOfView/Cura-MeshTools
- CustomSupportEraserPlus: https://github.com/5axes/CustomSupportEraserPlus
- Cura API versions: https://github.com/Ultimaker/Cura/wiki/CuraAPI-and-SDK-Versions
