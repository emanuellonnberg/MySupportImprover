# Copyright (c) 2024 Emanuel Lönnberg.
# This tool is released under the terms of the LGPLv3 or higher.

import sys
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QProgressDialog

from UM.Logger import Logger
from UM.Application import Application
from UM.Math.Vector import Vector
from UM.Math.Matrix import Matrix
from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Scene.Selection import Selection
from UM.Scene.SceneNode import SceneNode
from UM.View.GL.OpenGL import OpenGL

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
import math
from typing import Optional, Tuple, List

# Log Python environment info for debugging
Logger.log("i", "ObjectSplitter: Python executable: %s", sys.executable)
Logger.log("i", "ObjectSplitter: Python version: %s", sys.version)
Logger.log("i", "ObjectSplitter: Python path: %s", os.pathsep.join(sys.path[:3]))  # First 3 paths

# Try to import trimesh - it's optional but required for cutting
try:
    import trimesh
    TRIMESH_AVAILABLE = True
    Logger.log("i", "ObjectSplitter: trimesh version: %s", trimesh.__version__)
except ImportError:
    TRIMESH_AVAILABLE = False
    Logger.log("w", "trimesh not available - Object Splitter cutting functionality disabled")

# Check for rtree availability
try:
    import rtree
    RTREE_AVAILABLE = True
    Logger.log("i", "ObjectSplitter: rtree is available")
except ImportError:
    RTREE_AVAILABLE = False
    Logger.log("w", "ObjectSplitter: rtree not available - will use fallback triangulation")

# Check for scipy (used for fallback triangulation)
try:
    from scipy.spatial import Delaunay
    SCIPY_AVAILABLE = True
    Logger.log("i", "ObjectSplitter: scipy is available for triangulation")
except ImportError:
    SCIPY_AVAILABLE = False
    Logger.log("w", "ObjectSplitter: scipy not available - triangulation may fail")


class ObjectSplitter(Tool):
    """Tool for splitting 3D objects into multiple parts by cutting along planes."""

    # Cut mode constants
    CUT_MODE_HORIZONTAL = "horizontal"      # Cut parallel to build plate
    CUT_MODE_VERTICAL = "vertical"          # Cut perpendicular to build plate
    CUT_MODE_SMALLEST = "smallest"          # Find smallest cross-section
    CUT_MODE_CUSTOM = "custom"              # User-defined plane orientation

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
        self._preview_size = 100.0  # Size of preview plane (will be adjusted to mesh)

        # Connector settings
        self._connector_enabled = True
        self._connector_diameter = 4.0  # mm - diameter of peg/hole
        self._connector_height = 3.0  # mm - how deep the peg/hole extends
        self._connector_clearance = 0.2  # mm - extra space in hole for fit
        self._connector_sides = 16  # Number of sides for cylinder approximation

        # Search settings for smallest cut
        self._search_resolution = 18  # Number of angles to search

        # State
        self._selection_pass = None
        self._last_picked_node = None
        self._last_picked_position = None
        self._hover_node = None  # Node currently being hovered over
        self._picking_pass = None  # Cached picking pass
        self._progress_dialog = None  # Progress dialog for long operations

        self.setExposedProperties(
            "CutMode",
            "CutModes",
            "CutHeightPercent",
            "ShowPreview",
            "TrimeshAvailable",
            "SearchResolution",
            # Connector properties
            "ConnectorEnabled",
            "ConnectorDiameter",
            "ConnectorHeight",
            "ConnectorClearance"
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
    # Progress Dialog
    # ==========================================================================

    def _showProgress(self, title: str, message: str, minimum: int = 0, maximum: int = 100) -> QProgressDialog:
        """Show a progress dialog for long operations."""
        app = QApplication.instance()
        if app is None:
            return None

        dialog = self._progress_dialog
        if dialog is None:
            dialog = QProgressDialog(message, None, minimum, maximum)
            dialog.setWindowTitle(title)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.setCancelButton(None)  # No cancel button
            dialog.setMinimumDuration(0)  # Show immediately
            dialog.setAutoClose(False)
            dialog.setAutoReset(False)
            dialog.setValue(minimum)
            self._progress_dialog = dialog
        else:
            dialog.setLabelText(message)
            dialog.setRange(minimum, maximum)
            dialog.setWindowTitle(title)
            dialog.setValue(minimum)

        dialog.show()
        QApplication.processEvents()
        return dialog

    def _updateProgress(self, message: str, value: int = None) -> None:
        """Update the progress dialog."""
        dialog = self._progress_dialog
        if dialog is None:
            return
        if message:
            dialog.setLabelText(message)
        if value is not None:
            dialog.setValue(value)
        QApplication.processEvents()

    def _closeProgress(self) -> None:
        """Close the progress dialog."""
        dialog = self._progress_dialog
        if dialog is None:
            return
        dialog.close()
        self._progress_dialog = None

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
            if not value:
                self._removePreview()
            self.propertyChanged.emit()

    def getTrimeshAvailable(self) -> bool:
        return TRIMESH_AVAILABLE

    def getSearchResolution(self) -> int:
        return self._search_resolution

    def setSearchResolution(self, value: int) -> None:
        if value != self._search_resolution:
            self._search_resolution = int(value)
            self.propertyChanged.emit()

    # Connector properties
    def getConnectorEnabled(self) -> bool:
        return self._connector_enabled

    def setConnectorEnabled(self, value: bool) -> None:
        if value != self._connector_enabled:
            self._connector_enabled = value
            Logger.log("d", "Connector enabled changed to: %s", str(value))
            self.propertyChanged.emit()

    def getConnectorDiameter(self) -> float:
        return self._connector_diameter

    def setConnectorDiameter(self, value: float) -> None:
        if value != self._connector_diameter:
            self._connector_diameter = float(value)
            Logger.log("d", "Connector diameter changed to: %s", str(value))
            self.propertyChanged.emit()

    def getConnectorHeight(self) -> float:
        return self._connector_height

    def setConnectorHeight(self, value: float) -> None:
        if value != self._connector_height:
            self._connector_height = float(value)
            Logger.log("d", "Connector height changed to: %s", str(value))
            self.propertyChanged.emit()

    def getConnectorClearance(self) -> float:
        return self._connector_clearance

    def setConnectorClearance(self, value: float) -> None:
        if value != self._connector_clearance:
            self._connector_clearance = float(value)
            Logger.log("d", "Connector clearance changed to: %s", str(value))
            self.propertyChanged.emit()

    # ==========================================================================
    # Event Handling
    # ==========================================================================

    def event(self, event):
        super().event(event)
        modifiers = QApplication.keyboardModifiers()
        ctrl_is_active = modifiers & Qt.KeyboardModifier.ControlModifier

        # Handle mouse move for preview
        if event.type == Event.MouseMoveEvent and self._show_preview:
            self._updatePreview(event.x, event.y)
            return

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons and self._controller.getToolsEnabled():
            if ctrl_is_active:
                self._controller.setActiveTool("TranslateTool")
                return

            if not TRIMESH_AVAILABLE:
                Logger.log("e", "Cannot split: trimesh library not available. Install with: pip install trimesh")
                return

            # Hide preview before cutting
            self._removePreview()

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

    def setEnabled(self, enable: bool) -> None:
        """Called when the tool is enabled/disabled."""
        super().setEnabled(enable)
        if not enable:
            self._removePreview()

    # ==========================================================================
    # Preview Handling
    # ==========================================================================

    def _updatePreview(self, mouse_x: float, mouse_y: float):
        """Update the preview plane based on mouse position."""
        if not self._show_preview:
            self._removePreview()
            return

        # Get the object under the mouse
        if self._selection_pass is None:
            self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")

        picked_node = self._controller.getScene().findObject(
            self._selection_pass.getIdAtPosition(mouse_x, mouse_y)
        )

        # Don't show preview on preview node itself
        if picked_node == self._preview_node:
            return

        if not picked_node:
            self._removePreview()
            return

        # Check if it's a regular mesh (not a modifier volume)
        node_stack = picked_node.callDecoration("getStack")
        if node_stack:
            if (node_stack.getProperty("support_mesh", "value") or
                node_stack.getProperty("anti_overhang_mesh", "value") or
                node_stack.getProperty("infill_mesh", "value") or
                node_stack.getProperty("cutting_mesh", "value")):
                self._removePreview()
                return

        # Get 3D position under mouse
        active_camera = self._controller.getScene().getActiveCamera()
        if self._picking_pass is None:
            self._picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
        self._picking_pass.render()
        picked_position = self._picking_pass.getPickedPosition(mouse_x, mouse_y)

        if picked_position is None:
            self._removePreview()
            return

        # Get mesh data for plane calculation
        mesh_data = picked_node.getMeshData()
        if mesh_data is None:
            self._removePreview()
            return

        # Calculate plane parameters based on cut mode
        transformed_mesh = mesh_data.getTransformed(picked_node.getWorldTransformation())
        vertices = transformed_mesh.getVertices()

        # Get bounding box for plane size
        min_bounds = vertices.min(axis=0)
        max_bounds = vertices.max(axis=0)
        mesh_size = max_bounds - min_bounds
        plane_size = max(mesh_size[0], mesh_size[2]) * 1.2  # 20% larger than mesh

        # Determine plane normal and origin based on mode
        if self._cut_mode == self.CUT_MODE_HORIZONTAL:
            min_y = min_bounds[1]
            max_y = max_bounds[1]
            height = max_y - min_y
            cut_y = min_y + (height * self._cut_height_percent / 100.0)
            plane_origin = Vector(0, cut_y, 0)
            plane_normal = Vector(0, 1, 0)
        elif self._cut_mode == self.CUT_MODE_VERTICAL:
            plane_origin = picked_position
            plane_normal = Vector(1, 0, 0)  # Cut along X axis
        elif self._cut_mode == self.CUT_MODE_SMALLEST:
            # For smallest mode, just show horizontal plane at click position as hint
            # The actual smallest cut is computed on click
            plane_origin = picked_position
            plane_normal = Vector(0, 1, 0)
        else:
            plane_origin = picked_position
            plane_normal = Vector(0, 1, 0)

        # Create or update preview
        self._createOrUpdatePreview(plane_origin, plane_normal, plane_size)
        self._hover_node = picked_node

    def _createOrUpdatePreview(self, origin: Vector, normal: Vector, size: float):
        """Create or update the preview plane mesh."""
        if self._preview_node is None:
            self._preview_node = self._createPreviewNode()

        # Update preview mesh geometry
        mesh_builder = self._createPlaneMesh(origin, normal, size)
        mesh_data = mesh_builder.build()
        self._preview_node.setMeshData(mesh_data)

        # Make sure it's in the scene
        scene_root = self._controller.getScene().getRoot()
        if self._preview_node.getParent() != scene_root:
            self._preview_node.setParent(scene_root)

    def _createPreviewNode(self) -> SceneNode:
        """Create a new preview node (non-selectable, non-sliceable)."""
        node = SceneNode()
        node.setName("ObjectSplitter_Preview")
        node.setSelectable(False)
        node.setCalculateBoundingBox(False)

        # Set rendering to be translucent
        # Note: The actual transparency depends on Cura's rendering pipeline
        # We'll use a special mesh type or shader if available

        return node

    def _createPlaneMesh(self, origin: Vector, normal: Vector, size: float) -> MeshBuilder:
        """Create a flat plane mesh at the given position and orientation."""
        mesh = MeshBuilder()

        # Normalize the normal vector
        normal_arr = numpy.array([normal.x, normal.y, normal.z])
        normal_arr = normal_arr / numpy.linalg.norm(normal_arr)

        # Find two perpendicular vectors to the normal
        if abs(normal_arr[1]) < 0.9:
            up = numpy.array([0, 1, 0])
        else:
            up = numpy.array([1, 0, 0])

        tangent1 = numpy.cross(normal_arr, up)
        tangent1 = tangent1 / numpy.linalg.norm(tangent1)
        tangent2 = numpy.cross(normal_arr, tangent1)

        # Scale by half size
        half_size = size / 2.0
        t1 = tangent1 * half_size
        t2 = tangent2 * half_size

        # Create 4 corners of the plane
        center = numpy.array([origin.x, origin.y, origin.z])
        corners = [
            center - t1 - t2,  # Bottom-left
            center + t1 - t2,  # Bottom-right
            center + t1 + t2,  # Top-right
            center - t1 + t2,  # Top-left
        ]

        # Create vertices (we need 6 for 2 triangles, but we'll use indexed)
        vertices = numpy.array(corners, dtype=numpy.float32)

        # Create indices for 2 triangles (both sides for visibility)
        indices = numpy.array([
            [0, 1, 2],  # Front face triangle 1
            [0, 2, 3],  # Front face triangle 2
            [0, 2, 1],  # Back face triangle 1
            [0, 3, 2],  # Back face triangle 2
        ], dtype=numpy.int32)

        mesh.setVertices(vertices)
        mesh.setIndices(indices)

        # Set a distinct color for the preview (orange/red for visibility)
        # Colors are RGBA per vertex
        colors = numpy.array([
            [1.0, 0.3, 0.0, 0.5],  # Orange, semi-transparent
            [1.0, 0.3, 0.0, 0.5],
            [1.0, 0.3, 0.0, 0.5],
            [1.0, 0.3, 0.0, 0.5],
        ], dtype=numpy.float32)
        mesh.setColors(colors)

        mesh.calculateNormals()

        return mesh

    def _removePreview(self):
        """Remove the preview plane from the scene."""
        if self._preview_node is not None:
            if self._preview_node.getParent() is not None:
                self._preview_node.setParent(None)
            self._preview_node = None
        self._hover_node = None

    # ==========================================================================
    # Cutting Logic
    # ==========================================================================

    def _performCut(self, node: CuraSceneNode, click_position: Vector):
        """Perform the cut operation on the given node."""

        # Show progress dialog
        self._showProgress("Object Splitter", "Preparing mesh...", 0, 100)

        try:
            mesh_data = node.getMeshData()
            if mesh_data is None:
                Logger.log("e", "Node has no mesh data")
                self._closeProgress()
                return

            # Get mesh in world coordinates
            self._updateProgress("Loading mesh data...", 10)
            transformed_mesh = mesh_data.getTransformed(node.getWorldTransformation())
            vertices = transformed_mesh.getVertices()
            indices = transformed_mesh.getIndices()

            if indices is None:
                # Non-indexed mesh - create indices
                indices = numpy.arange(len(vertices)).reshape(-1, 3).astype(numpy.int32)

            # Convert to trimesh
            tm = trimesh.Trimesh(vertices=vertices, faces=indices)

            # Determine cut plane based on mode
            self._updateProgress("Calculating cut plane...", 20)
            if self._cut_mode == self.CUT_MODE_HORIZONTAL:
                plane_normal, plane_origin = self._getHorizontalCutPlane(tm, click_position)
            elif self._cut_mode == self.CUT_MODE_VERTICAL:
                plane_normal, plane_origin = self._getVerticalCutPlane(tm, click_position)
            elif self._cut_mode == self.CUT_MODE_SMALLEST:
                self._updateProgress("Searching for smallest cross-section...", 20)
                plane_normal, plane_origin = self._findSmallestCutPlane(tm, click_position)
            else:
                plane_normal, plane_origin = self._getHorizontalCutPlane(tm, click_position)

            Logger.log("d", "Cut plane: origin=%s, normal=%s", str(plane_origin), str(plane_normal))

            # Perform the cut - try with capping first, fallback to no cap
            self._updateProgress("Splitting mesh...", 40)
            mesh_upper, mesh_lower, capped = self._sliceMeshWithFallback(tm, plane_origin, plane_normal)

            if mesh_upper is None or mesh_lower is None:
                Logger.log("e", "Cut operation failed")
                self._closeProgress()
                return

            # Check if we got valid meshes
            if len(mesh_upper.vertices) == 0:
                Logger.log("w", "Upper mesh is empty after cut")
                self._closeProgress()
                return
            if len(mesh_lower.vertices) == 0:
                Logger.log("w", "Lower mesh is empty after cut")
                self._closeProgress()
                return

            Logger.log("i", "Cut successful: upper=%d verts, lower=%d verts, capped=%s",
                       len(mesh_upper.vertices), len(mesh_lower.vertices), str(capped))

            # Add connectors if enabled (only if mesh was capped properly)
            if self._connector_enabled and capped:
                self._updateProgress("Adding connectors...", 60)
                mesh_upper, mesh_lower = self._addConnectors(
                    mesh_upper, mesh_lower, plane_origin, plane_normal
                )
                Logger.log("i", "After connectors: upper=%d verts, lower=%d verts",
                           len(mesh_upper.vertices), len(mesh_lower.vertices))
            elif self._connector_enabled and not capped:
                Logger.log("w", "Skipping connectors - mesh was not capped (open edges)")

            self._updateProgress("Creating new objects...", 80)

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
            self._updateProgress("Finalizing...", 90)
            scene_root = self._controller.getScene().getRoot()

            op.addOperation(AddSceneNodeOperation(node_upper, scene_root))
            op.addOperation(AddSceneNodeOperation(node_lower, scene_root))
            op.addOperation(RemoveSceneNodeOperation(node))

            op.push()

            # Emit scene changed
            CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node_upper)

            self._updateProgress("Done!", 100)
            Logger.log("i", "Split complete: created '%s' and '%s'",
                       node_upper.getName(), node_lower.getName())

        except Exception as e:
            Logger.log("e", "Error during cut operation: %s", str(e))
        finally:
            self._closeProgress()

    def _sliceMeshWithFallback(self, mesh: "trimesh.Trimesh", plane_origin: numpy.ndarray,
                                plane_normal: numpy.ndarray) -> Tuple[Optional["trimesh.Trimesh"], Optional["trimesh.Trimesh"], bool]:
        """
        Slice mesh with multiple fallback strategies for robustness.

        Returns:
            Tuple of (upper_mesh, lower_mesh, was_capped)
            was_capped is True if the cut surfaces were closed (watertight result)
        """
        mesh_upper = None
        mesh_lower = None
        capped = False

        # Strategy 1: Try with capping (ideal case - watertight mesh with rtree)
        try:
            mesh_upper = trimesh.intersections.slice_mesh_plane(
                mesh,
                plane_normal=plane_normal,
                plane_origin=plane_origin,
                cap=True
            )
            mesh_lower = trimesh.intersections.slice_mesh_plane(
                mesh,
                plane_normal=-plane_normal,
                plane_origin=plane_origin,
                cap=True
            )
            if mesh_upper is not None and mesh_lower is not None:
                capped = True
                Logger.log("d", "Slicing with cap=True succeeded")
                return mesh_upper, mesh_lower, capped
        except ImportError as e:
            # rtree not available
            Logger.log("w", "Capping requires 'rtree' library: %s. Trying manual capping.", str(e))
        except Exception as e:
            error_msg = str(e).lower()
            if "watertight" in error_msg:
                Logger.log("w", "Mesh is not watertight, cannot use built-in cap. Trying manual capping.")
            elif "rtree" in error_msg:
                Logger.log("w", "rtree library missing: %s. Trying manual capping.", str(e))
            else:
                Logger.log("w", "Capped slicing failed: %s. Trying manual capping.", str(e))

        # Strategy 2: Slice without capping, then manually cap
        try:
            mesh_upper = trimesh.intersections.slice_mesh_plane(
                mesh,
                plane_normal=plane_normal,
                plane_origin=plane_origin,
                cap=False
            )
            mesh_lower = trimesh.intersections.slice_mesh_plane(
                mesh,
                plane_normal=-plane_normal,
                plane_origin=plane_origin,
                cap=False
            )
            if mesh_upper is not None and mesh_lower is not None:
                # Try to manually cap the meshes
                mesh_upper_capped = self._manualCapMesh(mesh_upper, plane_origin, plane_normal)
                mesh_lower_capped = self._manualCapMesh(mesh_lower, plane_origin, -plane_normal)

                if mesh_upper_capped is not None and mesh_lower_capped is not None:
                    Logger.log("i", "Slicing with manual capping succeeded")
                    return mesh_upper_capped, mesh_lower_capped, True
                else:
                    Logger.log("w", "Manual capping failed, using uncapped meshes")
                    return mesh_upper, mesh_lower, False
        except Exception as e:
            Logger.log("e", "Uncapped slicing failed: %s", str(e))

        # Strategy 3: Manual vertex-based splitting as last resort
        try:
            mesh_upper, mesh_lower = self._manualMeshSplit(mesh, plane_origin, plane_normal)
            if mesh_upper is not None and mesh_lower is not None:
                Logger.log("i", "Manual mesh splitting succeeded")
                return mesh_upper, mesh_lower, False
        except Exception as e:
            Logger.log("e", "Manual splitting failed: %s", str(e))

        return None, None, False

    def _manualCapMesh(self, mesh: "trimesh.Trimesh", plane_origin: numpy.ndarray,
                        plane_normal: numpy.ndarray) -> Optional["trimesh.Trimesh"]:
        """
        Manually cap a mesh by finding the boundary edges on the cut plane
        and triangulating them to close the surface.
        Uses scipy Delaunay triangulation to avoid rtree dependency.
        """
        try:
            # Get the cross-section path at the cut plane
            section = mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)
            if section is None:
                Logger.log("w", "Could not get cross-section for capping")
                return None

            # Convert to 2D for triangulation
            path_2d, transform = section.to_planar()
            if path_2d is None:
                Logger.log("w", "Could not convert section to 2D")
                return None

            # Get vertices from the path
            # The path contains discrete curves - we need to extract vertices
            vertices_2d = None
            faces_2d = None

            # Try scipy Delaunay triangulation first (doesn't need rtree)
            if SCIPY_AVAILABLE:
                try:
                    # Get all vertices from path entities
                    all_vertices = []
                    for entity in path_2d.entities:
                        points = path_2d.vertices[entity.points]
                        all_vertices.extend(points)

                    if len(all_vertices) < 3:
                        Logger.log("w", "Not enough vertices for triangulation")
                        return None

                    vertices_2d = numpy.array(all_vertices)

                    # Remove duplicate vertices
                    vertices_2d = numpy.unique(vertices_2d, axis=0)

                    if len(vertices_2d) < 3:
                        Logger.log("w", "Not enough unique vertices for triangulation")
                        return None

                    # Use scipy Delaunay triangulation
                    tri = Delaunay(vertices_2d)
                    faces_2d = tri.simplices

                    Logger.log("d", "Scipy Delaunay triangulation: %d vertices, %d faces",
                               len(vertices_2d), len(faces_2d))

                except Exception as e:
                    Logger.log("w", "Scipy triangulation failed: %s", str(e))
                    vertices_2d = None
                    faces_2d = None

            # Fallback to trimesh triangulation if scipy failed
            if vertices_2d is None or faces_2d is None:
                try:
                    vertices_2d, faces_2d = path_2d.triangulate()
                except Exception as e:
                    Logger.log("w", "Trimesh triangulation also failed: %s", str(e))
                    return None

            if vertices_2d is None or len(vertices_2d) == 0 or faces_2d is None or len(faces_2d) == 0:
                Logger.log("w", "Triangulation produced empty result")
                return None

            # Transform triangulated vertices back to 3D
            vertices_3d_homogeneous = numpy.column_stack([
                vertices_2d,
                numpy.zeros(len(vertices_2d)),
                numpy.ones(len(vertices_2d))
            ])
            transform_inv = numpy.linalg.inv(transform)
            vertices_3d = (transform_inv @ vertices_3d_homogeneous.T).T[:, :3]

            # Create cap mesh
            cap_mesh = trimesh.Trimesh(vertices=vertices_3d, faces=faces_2d)

            # Ensure cap normal faces the right direction (away from the part)
            # The cap should face in the direction of the plane normal
            if len(cap_mesh.face_normals) > 0:
                cap_normal = cap_mesh.face_normals.mean(axis=0)
                norm = numpy.linalg.norm(cap_normal)
                if norm > 1e-6:
                    cap_normal = cap_normal / norm
                    if numpy.dot(cap_normal, plane_normal) < 0:
                        # Flip the faces
                        cap_mesh.faces = cap_mesh.faces[:, ::-1]

            # Combine original mesh with cap
            combined = trimesh.util.concatenate([mesh, cap_mesh])

            Logger.log("d", "Manual capping added %d cap vertices, %d cap faces",
                       len(vertices_3d), len(faces_2d))

            return combined

        except Exception as e:
            Logger.log("w", "Manual capping error: %s", str(e))
            return None

    def _manualMeshSplit(self, mesh: "trimesh.Trimesh", plane_origin: numpy.ndarray,
                          plane_normal: numpy.ndarray) -> Tuple[Optional["trimesh.Trimesh"], Optional["trimesh.Trimesh"]]:
        """
        Manually split mesh by separating faces based on which side of the plane they're on.
        This is a simple approach that doesn't handle faces crossing the plane perfectly,
        but works as a fallback when trimesh's slice_mesh_plane fails.
        """
        vertices = mesh.vertices
        faces = mesh.faces

        # Compute signed distance of each vertex to the plane
        distances = numpy.dot(vertices - plane_origin, plane_normal)

        # For each face, determine which side it's on based on centroid
        face_centroids = vertices[faces].mean(axis=1)
        face_distances = numpy.dot(face_centroids - plane_origin, plane_normal)

        # Split faces
        upper_mask = face_distances >= 0
        lower_mask = face_distances < 0

        upper_faces = faces[upper_mask]
        lower_faces = faces[lower_mask]

        if len(upper_faces) == 0 or len(lower_faces) == 0:
            Logger.log("w", "Manual split resulted in empty mesh on one side")
            return None, None

        # Create new meshes (reusing all vertices, trimesh will clean up unused ones)
        mesh_upper = trimesh.Trimesh(vertices=vertices.copy(), faces=upper_faces)
        mesh_lower = trimesh.Trimesh(vertices=vertices.copy(), faces=lower_faces)

        # Remove unreferenced vertices
        mesh_upper.remove_unreferenced_vertices()
        mesh_lower.remove_unreferenced_vertices()

        return mesh_upper, mesh_lower

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

    # ==========================================================================
    # Connector Logic
    # ==========================================================================

    def _getMeshVolume(self, mesh: "trimesh.Trimesh") -> float:
        """Get the volume of a mesh. Uses convex hull if mesh is not watertight."""
        try:
            if mesh.is_watertight:
                return abs(mesh.volume)
            else:
                return abs(mesh.convex_hull.volume)
        except Exception:
            # Fallback to bounding box volume
            bounds = mesh.bounds
            return numpy.prod(bounds[1] - bounds[0])

    def _determinePegSide(self, mesh_a: "trimesh.Trimesh", mesh_b: "trimesh.Trimesh") -> Tuple[str, str]:
        """
        Determine which part gets the peg vs hole based on volume.
        Peg goes on smaller part, hole on larger part.

        Returns:
            Tuple of ("peg", "hole") or ("hole", "peg") indicating what mesh_a and mesh_b get.
        """
        volume_a = self._getMeshVolume(mesh_a)
        volume_b = self._getMeshVolume(mesh_b)

        Logger.log("d", "Volume comparison: mesh_a=%.2f mm³, mesh_b=%.2f mm³", volume_a, volume_b)

        if volume_a <= volume_b:
            return ("peg", "hole")  # mesh_a gets peg, mesh_b gets hole
        else:
            return ("hole", "peg")  # mesh_a gets hole, mesh_b gets peg

    def _findConnectorPosition(self, mesh: "trimesh.Trimesh", plane_origin: numpy.ndarray,
                                plane_normal: numpy.ndarray) -> Optional[numpy.ndarray]:
        """
        Find a suitable position for the connector on the cut surface.
        Returns the centroid of the cut surface if valid, None otherwise.
        """
        try:
            # Get the cross-section at the cut plane
            section = mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)
            if section is None:
                Logger.log("w", "Could not get cross-section for connector placement")
                return None

            # Convert to 2D path and get centroid
            path_2d, transform = section.to_planar()
            if path_2d is None or len(path_2d.entities) == 0:
                Logger.log("w", "Cross-section has no valid geometry")
                return None

            # Get centroid in 2D
            centroid_2d = path_2d.centroid

            # Transform back to 3D
            # The transform is a 4x4 matrix that maps 3D to 2D
            # We need to invert it to go from 2D back to 3D
            centroid_3d_homogeneous = numpy.array([centroid_2d[0], centroid_2d[1], 0, 1])
            transform_inv = numpy.linalg.inv(transform)
            centroid_3d = (transform_inv @ centroid_3d_homogeneous)[:3]

            # Verify the centroid is far enough from edges
            # Check distance from centroid to nearest boundary
            min_dist = self._connector_diameter / 2 + 1.0  # Need at least radius + 1mm margin

            # For now, just use the centroid - more sophisticated edge checking could be added
            Logger.log("d", "Connector position: %s", str(centroid_3d))

            return centroid_3d

        except Exception as e:
            Logger.log("w", "Error finding connector position: %s", str(e))
            return None

    def _createPegMesh(self, position: numpy.ndarray, normal: numpy.ndarray,
                       diameter: float, height: float) -> "trimesh.Trimesh":
        """Create a cylinder mesh for the peg at the given position."""
        radius = diameter / 2.0

        # Create cylinder along Z axis, then transform
        peg = trimesh.creation.cylinder(
            radius=radius,
            height=height,
            sections=self._connector_sides
        )

        # The cylinder is centered at origin along Z
        # We need to:
        # 1. Move it so the base is at Z=0 (shift up by height/2)
        # 2. Rotate to align with the plane normal
        # 3. Translate to the connector position

        # Shift so base is at origin
        peg.apply_translation([0, 0, height / 2])

        # Create rotation to align Z axis with the plane normal
        z_axis = numpy.array([0, 0, 1])
        normal_normalized = normal / numpy.linalg.norm(normal)

        # Rotation matrix from Z to normal
        rotation_matrix = self._rotationMatrixFromVectors(z_axis, normal_normalized)
        transform = numpy.eye(4)
        transform[:3, :3] = rotation_matrix
        peg.apply_transform(transform)

        # Translate to position
        peg.apply_translation(position)

        Logger.log("d", "Created peg: diameter=%.2f, height=%.2f, position=%s",
                   diameter, height, str(position))

        return peg

    def _createHoleMesh(self, position: numpy.ndarray, normal: numpy.ndarray,
                        diameter: float, height: float, clearance: float) -> "trimesh.Trimesh":
        """Create a cylinder mesh for the hole (to be subtracted) at the given position."""
        # Hole is slightly larger than peg for clearance
        radius = diameter / 2.0 + clearance
        # Hole is slightly deeper to ensure clean subtraction
        hole_height = height + 0.2

        hole = trimesh.creation.cylinder(
            radius=radius,
            height=hole_height,
            sections=self._connector_sides
        )

        # Shift so the top of the cylinder is at Z=0 (hole goes into the part)
        hole.apply_translation([0, 0, -hole_height / 2])

        # Create rotation to align Z axis with the negative plane normal (hole goes in)
        z_axis = numpy.array([0, 0, 1])
        normal_normalized = normal / numpy.linalg.norm(normal)

        rotation_matrix = self._rotationMatrixFromVectors(z_axis, -normal_normalized)
        transform = numpy.eye(4)
        transform[:3, :3] = rotation_matrix
        hole.apply_transform(transform)

        # Translate to position
        hole.apply_translation(position)

        Logger.log("d", "Created hole: diameter=%.2f (with clearance=%.2f), height=%.2f, position=%s",
                   diameter + clearance * 2, clearance, hole_height, str(position))

        return hole

    def _rotationMatrixFromVectors(self, vec1: numpy.ndarray, vec2: numpy.ndarray) -> numpy.ndarray:
        """
        Create a rotation matrix that rotates vec1 to vec2.
        Uses Rodrigues' rotation formula.
        """
        vec1 = vec1 / numpy.linalg.norm(vec1)
        vec2 = vec2 / numpy.linalg.norm(vec2)

        # Check if vectors are parallel
        cross = numpy.cross(vec1, vec2)
        dot = numpy.dot(vec1, vec2)

        if numpy.linalg.norm(cross) < 1e-6:
            if dot > 0:
                # Same direction, identity rotation
                return numpy.eye(3)
            else:
                # Opposite direction, 180 degree rotation
                # Find a perpendicular vector
                if abs(vec1[0]) < 0.9:
                    perp = numpy.array([1, 0, 0])
                else:
                    perp = numpy.array([0, 1, 0])
                perp = perp - numpy.dot(perp, vec1) * vec1
                perp = perp / numpy.linalg.norm(perp)
                # Rodrigues for 180 degree rotation around perp
                return 2 * numpy.outer(perp, perp) - numpy.eye(3)

        # Rodrigues' formula
        cross_normalized = cross / numpy.linalg.norm(cross)
        angle = numpy.arccos(numpy.clip(dot, -1, 1))

        K = numpy.array([
            [0, -cross_normalized[2], cross_normalized[1]],
            [cross_normalized[2], 0, -cross_normalized[0]],
            [-cross_normalized[1], cross_normalized[0], 0]
        ])

        R = numpy.eye(3) + numpy.sin(angle) * K + (1 - numpy.cos(angle)) * (K @ K)
        return R

    def _addConnectors(self, mesh_upper: "trimesh.Trimesh", mesh_lower: "trimesh.Trimesh",
                       plane_origin: numpy.ndarray, plane_normal: numpy.ndarray) -> Tuple["trimesh.Trimesh", "trimesh.Trimesh"]:
        """
        Add peg to smaller part and hole to larger part.
        Returns the modified meshes.
        """
        if not self._connector_enabled:
            return mesh_upper, mesh_lower

        # Determine which part gets peg vs hole
        upper_role, lower_role = self._determinePegSide(mesh_upper, mesh_lower)

        # Find connector position on the cut surface
        # Use the original mesh (upper) for finding position since both share the cut surface
        connector_pos = self._findConnectorPosition(mesh_upper, plane_origin, plane_normal)

        if connector_pos is None:
            Logger.log("w", "Could not find valid connector position, skipping connectors")
            return mesh_upper, mesh_lower

        # Create peg and hole meshes
        peg = self._createPegMesh(
            connector_pos, plane_normal,
            self._connector_diameter, self._connector_height
        )

        hole = self._createHoleMesh(
            connector_pos, plane_normal,
            self._connector_diameter, self._connector_height, self._connector_clearance
        )

        # Apply to the appropriate meshes
        try:
            if upper_role == "peg":
                # Upper gets peg (union), lower gets hole (difference)
                mesh_upper_result = trimesh.boolean.union([mesh_upper, peg])
                mesh_lower_result = trimesh.boolean.difference([mesh_lower, hole])
                Logger.log("i", "Added peg to upper part, hole to lower part")
            else:
                # Upper gets hole (difference), lower gets peg (union)
                mesh_upper_result = trimesh.boolean.difference([mesh_upper, hole])
                mesh_lower_result = trimesh.boolean.union([mesh_lower, peg])
                Logger.log("i", "Added hole to upper part, peg to lower part")

            # Verify results are valid
            if mesh_upper_result is None or len(mesh_upper_result.vertices) == 0:
                Logger.log("w", "Upper mesh invalid after connector operation, using original")
                mesh_upper_result = mesh_upper
            if mesh_lower_result is None or len(mesh_lower_result.vertices) == 0:
                Logger.log("w", "Lower mesh invalid after connector operation, using original")
                mesh_lower_result = mesh_lower

            return mesh_upper_result, mesh_lower_result

        except Exception as e:
            Logger.log("e", "Error adding connectors: %s. Using meshes without connectors.", str(e))
            return mesh_upper, mesh_lower
