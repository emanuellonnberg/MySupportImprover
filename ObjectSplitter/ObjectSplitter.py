# Copyright (c) 2024 Emanuel Lönnberg.
# This tool is released under the terms of the LGPLv3 or higher.

from PyQt6.QtCore import Qt, pyqtProperty, pyqtSignal
from PyQt6.QtWidgets import QApplication

from UM.Logger import Logger
from UM.Application import Application
from UM.Math.Vector import Vector
from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Scene.Selection import Selection

from cura.CuraApplication import CuraApplication
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.PickingPass import PickingPass

from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from cura.Operations.SetParentOperation import SetParentOperation

from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator

import numpy
from typing import Optional, Tuple, List

# Try to import trimesh - it's optional but required for cutting
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False
    Logger.log("w", "trimesh not available - Object Splitter cutting functionality disabled")


class ObjectSplitter(Tool):
    """Tool for splitting 3D objects into multiple parts by cutting along planes."""

    # Cut mode constants
    CUT_MODE_HORIZONTAL = "horizontal"      # Cut parallel to build plate
    CUT_MODE_VERTICAL = "vertical"          # Cut perpendicular to build plate
    CUT_MODE_SMALLEST = "smallest"          # Find smallest cross-section
    CUT_MODE_CUSTOM = "custom"              # User-defined plane orientation

    # Signals
    cutComplete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._shortcut_key = Qt.Key.Key_K  # K for "Kut" (avoiding conflicts)
        self._controller = self.getController()

        # Cut settings
        self._cut_mode = self.CUT_MODE_HORIZONTAL
        self._cut_height = 0.0  # For horizontal cuts: Z position (relative to object)
        self._cut_height_percent = 50.0  # Percentage of object height
        self._plane_normal = numpy.array([0.0, 1.0, 0.0])  # Y-up in Cura
        self._plane_origin = numpy.array([0.0, 0.0, 0.0])

        # Preview settings
        self._show_preview = True
        self._preview_node = None

        # Search settings for smallest cut
        self._search_resolution = 18  # Number of angles to search

        # State
        self._selection_pass = None
        self._last_picked_node = None
        self._last_picked_position = None

        self.setExposedProperties(
            "CutMode",
            "CutModes",
            "CutHeightPercent",
            "ShowPreview",
            "TrimeshAvailable",
            "SearchResolution"
        )

        Logger.log("d", "Object Splitter Tool initialized (trimesh available: %s)", str(TRIMESH_AVAILABLE))

        CuraApplication.getInstance().globalContainerStackChanged.connect(self._updateEnabled)
        Selection.selectionChanged.connect(self._onSelectionChanged)

    def _updateEnabled(self):
        """Update whether the tool is enabled based on current state."""
        plugin_enabled = True

        global_container_stack = CuraApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            plugin_enabled = True  # Could add conditions here

        Application.getInstance().getController().toolEnabledChanged.emit(self._plugin_id, plugin_enabled)

    def _onSelectionChanged(self):
        """Handle selection changes."""
        pass  # Could update preview here

    # ==========================================================================
    # Properties for QML
    # ==========================================================================

    def getCutMode(self) -> str:
        return self._cut_mode

    def setCutMode(self, mode: str) -> None:
        if mode != self._cut_mode:
            self._cut_mode = mode
            Logger.log("d", "Cut mode changed to: %s", mode)
            self.propertyChanged.emit()

    def getCutModes(self) -> list:
        """Return available cut modes for QML dropdown."""
        return [
            {"value": self.CUT_MODE_HORIZONTAL, "text": "Horizontal (parallel to bed)"},
            {"value": self.CUT_MODE_VERTICAL, "text": "Vertical"},
            {"value": self.CUT_MODE_SMALLEST, "text": "Smallest cross-section"},
            # {"value": self.CUT_MODE_CUSTOM, "text": "Custom angle"},  # Future
        ]

    def getCutHeightPercent(self) -> float:
        return self._cut_height_percent

    def setCutHeightPercent(self, value: float) -> None:
        if value != self._cut_height_percent:
            self._cut_height_percent = float(value)
            Logger.log("d", "Cut height percent changed to: %s", str(value))
            self.propertyChanged.emit()

    def getShowPreview(self) -> bool:
        return self._show_preview

    def setShowPreview(self, value: bool) -> None:
        if value != self._show_preview:
            self._show_preview = value
            self.propertyChanged.emit()

    def getTrimeshAvailable(self) -> bool:
        return TRIMESH_AVAILABLE

    def getSearchResolution(self) -> int:
        return self._search_resolution

    def setSearchResolution(self, value: int) -> None:
        if value != self._search_resolution:
            self._search_resolution = int(value)
            self.propertyChanged.emit()

    # ==========================================================================
    # Event Handling
    # ==========================================================================

    def event(self, event):
        super().event(event)
        modifiers = QApplication.keyboardModifiers()
        ctrl_is_active = modifiers & Qt.KeyboardModifier.ControlModifier

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons and self._controller.getToolsEnabled():
            if ctrl_is_active:
                self._controller.setActiveTool("TranslateTool")
                return

            if not TRIMESH_AVAILABLE:
                Logger.log("e", "Cannot split: trimesh library not available. Install with: pip install trimesh")
                return

            # Get the object under the mouse
            if self._selection_pass is None:
                self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")

            picked_node = self._controller.getScene().findObject(
                self._selection_pass.getIdAtPosition(event.x, event.y)
            )

            if not picked_node:
                Logger.log("d", "No object picked")
                return

            # Check if it's a regular mesh (not a modifier volume)
            node_stack = picked_node.callDecoration("getStack")
            if node_stack:
                if (node_stack.getProperty("support_mesh", "value") or
                    node_stack.getProperty("anti_overhang_mesh", "value") or
                    node_stack.getProperty("infill_mesh", "value") or
                    node_stack.getProperty("cutting_mesh", "value")):
                    Logger.log("d", "Cannot split modifier meshes")
                    return

            # Get 3D click position
            active_camera = self._controller.getScene().getActiveCamera()
            picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
            picking_pass.render()
            picked_position = picking_pass.getPickedPosition(event.x, event.y)

            Logger.log("i", "Splitting object '%s' at position %s", picked_node.getName(), str(picked_position))

            # Store for potential preview updates
            self._last_picked_node = picked_node
            self._last_picked_position = picked_position

            # Perform the cut
            self._performCut(picked_node, picked_position)

    # ==========================================================================
    # Cutting Logic
    # ==========================================================================

    def _performCut(self, node: CuraSceneNode, click_position: Vector):
        """Perform the cut operation on the given node."""

        mesh_data = node.getMeshData()
        if mesh_data is None:
            Logger.log("e", "Node has no mesh data")
            return

        # Get mesh in world coordinates
        transformed_mesh = mesh_data.getTransformed(node.getWorldTransformation())
        vertices = transformed_mesh.getVertices()
        indices = transformed_mesh.getIndices()

        if indices is None:
            # Non-indexed mesh - create indices
            indices = numpy.arange(len(vertices)).reshape(-1, 3).astype(numpy.int32)

        # Convert to trimesh
        tm = trimesh.Trimesh(vertices=vertices, faces=indices)

        # Determine cut plane based on mode
        if self._cut_mode == self.CUT_MODE_HORIZONTAL:
            plane_normal, plane_origin = self._getHorizontalCutPlane(tm, click_position)
        elif self._cut_mode == self.CUT_MODE_VERTICAL:
            plane_normal, plane_origin = self._getVerticalCutPlane(tm, click_position)
        elif self._cut_mode == self.CUT_MODE_SMALLEST:
            plane_normal, plane_origin = self._findSmallestCutPlane(tm, click_position)
        else:
            plane_normal, plane_origin = self._getHorizontalCutPlane(tm, click_position)

        Logger.log("d", "Cut plane: origin=%s, normal=%s", str(plane_origin), str(plane_normal))

        # Perform the cut - create two meshes
        try:
            # Upper part (positive side of plane)
            mesh_upper = trimesh.intersections.slice_mesh_plane(
                tm,
                plane_normal=plane_normal,
                plane_origin=plane_origin,
                cap=True
            )

            # Lower part (negative side of plane)
            mesh_lower = trimesh.intersections.slice_mesh_plane(
                tm,
                plane_normal=-plane_normal,  # Flip normal for other side
                plane_origin=plane_origin,
                cap=True
            )
        except Exception as e:
            Logger.log("e", "Error during mesh cutting: %s", str(e))
            return

        # Check if we got valid meshes
        if mesh_upper is None or len(mesh_upper.vertices) == 0:
            Logger.log("w", "Upper mesh is empty after cut")
            return
        if mesh_lower is None or len(mesh_lower.vertices) == 0:
            Logger.log("w", "Lower mesh is empty after cut")
            return

        Logger.log("i", "Cut successful: upper=%d verts, lower=%d verts",
                   len(mesh_upper.vertices), len(mesh_lower.vertices))

        # Create new scene nodes for both parts
        original_name = node.getName()

        op = GroupedOperation()

        # Create upper part
        node_upper = self._createMeshNode(
            mesh_upper.vertices,
            mesh_upper.faces,
            f"{original_name}_part1"
        )

        # Create lower part
        node_lower = self._createMeshNode(
            mesh_lower.vertices,
            mesh_lower.faces,
            f"{original_name}_part2"
        )

        # Add new nodes and remove original
        scene_root = self._controller.getScene().getRoot()

        op.addOperation(AddSceneNodeOperation(node_upper, scene_root))
        op.addOperation(AddSceneNodeOperation(node_lower, scene_root))
        op.addOperation(RemoveSceneNodeOperation(node))

        op.push()

        # Emit scene changed
        CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node_upper)

        Logger.log("i", "Split complete: created '%s' and '%s'",
                   node_upper.getName(), node_lower.getName())

        self.cutComplete.emit()

    def _getHorizontalCutPlane(self, mesh: "trimesh.Trimesh", click_pos: Vector) -> Tuple[numpy.ndarray, numpy.ndarray]:
        """Get a horizontal cut plane at the specified height percentage."""
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        min_y = bounds[0][1]
        max_y = bounds[1][1]
        height = max_y - min_y

        # Calculate cut height based on percentage
        cut_y = min_y + (height * self._cut_height_percent / 100.0)

        # Or use click position Y if closer to it
        # cut_y = click_pos.y  # Could use this instead

        plane_origin = numpy.array([0.0, cut_y, 0.0])
        plane_normal = numpy.array([0.0, 1.0, 0.0])  # Y-up

        return plane_normal, plane_origin

    def _getVerticalCutPlane(self, mesh: "trimesh.Trimesh", click_pos: Vector) -> Tuple[numpy.ndarray, numpy.ndarray]:
        """Get a vertical cut plane through the click position."""
        # Use click position as origin
        plane_origin = numpy.array([click_pos.x, click_pos.y, click_pos.z])

        # Default to cutting along X axis (YZ plane)
        plane_normal = numpy.array([1.0, 0.0, 0.0])

        return plane_normal, plane_origin

    def _findSmallestCutPlane(self, mesh: "trimesh.Trimesh", click_pos: Vector) -> Tuple[numpy.ndarray, numpy.ndarray]:
        """Find the plane orientation that produces the smallest cross-sectional area."""

        plane_origin = numpy.array([click_pos.x, click_pos.y, click_pos.z])

        best_normal = numpy.array([0.0, 1.0, 0.0])  # Default to horizontal
        best_area = float('inf')

        # Sample orientations in spherical coordinates
        n_theta = self._search_resolution
        n_phi = self._search_resolution * 2

        for i in range(n_theta):
            theta = numpy.pi * i / n_theta  # 0 to pi (elevation)
            for j in range(n_phi):
                phi = 2 * numpy.pi * j / n_phi  # 0 to 2pi (azimuth)

                # Convert spherical to Cartesian
                normal = numpy.array([
                    numpy.sin(theta) * numpy.cos(phi),
                    numpy.cos(theta),
                    numpy.sin(theta) * numpy.sin(phi)
                ])

                # Get cross-section at this orientation
                try:
                    section = mesh.section(plane_origin=plane_origin, plane_normal=normal)
                    if section is not None:
                        # Get 2D area of the cross-section
                        path_2d, _ = section.to_planar()
                        area = abs(path_2d.area)

                        if area < best_area and area > 0:
                            best_area = area
                            best_normal = normal.copy()
                except Exception:
                    continue

        Logger.log("d", "Smallest cut found: area=%.2f mm², normal=%s", best_area, str(best_normal))

        return best_normal, plane_origin

    def _createMeshNode(self, vertices: numpy.ndarray, faces: numpy.ndarray, name: str) -> CuraSceneNode:
        """Create a new CuraSceneNode from vertices and faces."""

        # Build mesh using MeshBuilder
        mesh_builder = MeshBuilder()
        mesh_builder.setVertices(vertices.astype(numpy.float32))
        mesh_builder.setIndices(faces.astype(numpy.int32))
        mesh_builder.calculateNormals()

        mesh_data = mesh_builder.build()

        # Create scene node
        node = CuraSceneNode()
        node.setName(name)
        node.setSelectable(True)
        node.setCalculateBoundingBox(True)
        node.setMeshData(mesh_data)
        node.calculateBoundingBoxMesh()

        # Add decorators for Cura integration
        active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))
        node.addDecorator(SliceableObjectDecorator())

        return node
