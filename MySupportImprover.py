# Cura is released under the terms of the LGPLv3 or higher.
import os
import sys
import json
from PyQt6.QtCore import Qt, QTimer, pyqtProperty
from PyQt6.QtWidgets import QApplication
from UM.Resources import Resources
from UM.Logger import Logger
from UM.Application import Application
from UM.Math.Vector import Vector
from UM.Operations.TranslateOperation import TranslateOperation
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

from UM.Settings.SettingInstance import SettingInstance

import numpy

# Suggested solution from fieldOfView . in this discussion solved in Cura 4.9
# https://github.com/5axes/Calibration-Shapes/issues/1
# Cura are able to find the scripts from inside the plugin folder if the scripts are into a folder named resources
#Resources.addSearchPath(
#    os.path.join(os.path.abspath(os.path.dirname(__file__)),'resources')
#)  # Plugin translation file import

class MySupportImprover(Tool):
    def __init__(self):
        super().__init__()
        self._shortcut_key = Qt.Key.Key_E
        self._controller = self.getController()
        
        # Initialize properties with default values
        self._cube_x = 3.0
        self._cube_y = 3.0
        self._cube_z = 3.0
        self._can_modify = True
        self._show_settings = False
        self._use_presets = False
        self._support_angle = 45.0  # Default support angle
        self._current_preset = "Medium"  # Add current preset tracking
        self._is_custom = False  # Track if using custom values
        self._export_mode = False  # Export mesh data mode
        self._auto_detect = False  # Automatic overhang detection mode

        self.setExposedProperties("CubeX", "CubeY", "CubeZ", "ShowSettings", "CanModify", "Presets", "SupportAngle", "CurrentPreset", "IsCustom", "ExportMode", "AutoDetect")
        
        # Log initialization
        Logger.log("d", "Support Improver Tool initialized with properties: X=%s, Y=%s, Z=%s", 
                  str(self._cube_x), str(self._cube_y), str(self._cube_z))

        # Load presets from JSON file
        self._presets = {}
        self._load_presets()

        self._selection_pass = None
        CuraApplication.getInstance().globalContainerStackChanged.connect(self._updateEnabled)

        Selection.selectionChanged.connect(self._onSelectionChanged)
        self._had_selection = False
        self._skip_press = False

        self._had_selection_timer = QTimer()
        self._had_selection_timer.setInterval(0)
        self._had_selection_timer.setSingleShot(True)
        self._had_selection_timer.timeout.connect(self._selectionChangeDelay)

    # Property getters and setters
    def getCubeX(self) -> float:
        return self._cube_x

    def setCubeX(self, value: float) -> None:
        if value != self._cube_x:
            self._cube_x = float(value)
            self.setIsCustom(True)
            Logger.log("d", "CubeX changed to %s", str(self._cube_x))

    def getCubeY(self) -> float:
        return self._cube_y

    def setCubeY(self, value: float) -> None:
        if value != self._cube_y:
            self._cube_y = float(value)
            self.setIsCustom(True)
            Logger.log("d", "CubeY changed to %s", str(self._cube_y))

    def getCubeZ(self) -> float:
        return self._cube_z

    def setCubeZ(self, value: float) -> None:
        if value != self._cube_z:
            self._cube_z = float(value)
            self.setIsCustom(True)
            Logger.log("d", "CubeZ changed to %s", str(self._cube_z))

    def getCanModify(self) -> bool:
        return self._can_modify

    def setCanModify(self, value: bool) -> None:
        if value != self._can_modify:
            self._can_modify = bool(value)

    def getShowSettings(self) -> bool:
        return self._show_settings

    def setShowSettings(self, value: bool) -> None:
        if value != self._show_settings:
            self._show_settings = bool(value)

    def getUsePresets(self) -> bool:
        return self._use_presets

    def setUsePresets(self, value: bool) -> None:
        if value != self._use_presets:
            self._use_presets = bool(value)

    def getPresets(self) -> dict:
        return self._presets

    Presets = pyqtProperty("QVariantMap", fget=getPresets)

    def getSupportAngle(self) -> float:
        return self._support_angle

    def setSupportAngle(self, value: float) -> None:
        if value != self._support_angle:
            self._support_angle = float(value)
            Logger.log("d", "Support angle changed to %s", str(self._support_angle))

    SupportAngle = pyqtProperty(float, fget=getSupportAngle, fset=setSupportAngle)

    def getCurrentPreset(self) -> str:
        return self._current_preset

    def setCurrentPreset(self, preset_name: str) -> None:
        if preset_name != self._current_preset:
            self._current_preset = preset_name
            self.propertyChanged.emit()

    CurrentPreset = pyqtProperty(str, fget=getCurrentPreset, fset=setCurrentPreset)

    def getIsCustom(self) -> bool:
        return self._is_custom

    def setIsCustom(self, value: bool) -> None:
        if value != self._is_custom:
            self._is_custom = value
            if value:
                self._current_preset = "Custom"
            self.propertyChanged.emit()

    IsCustom = pyqtProperty(bool, fget=getIsCustom, fset=setIsCustom)

    def getExportMode(self) -> bool:
        return self._export_mode

    def setExportMode(self, value: bool) -> None:
        if value != self._export_mode:
            self._export_mode = value
            if value:
                Logger.log("i", "Export mode ENABLED - click on mesh to export data")
            else:
                Logger.log("i", "Export mode DISABLED - normal operation")
            self.propertyChanged.emit()

    ExportMode = pyqtProperty(bool, fget=getExportMode, fset=setExportMode)

    def getAutoDetect(self) -> bool:
        return self._auto_detect

    def setAutoDetect(self, value: bool) -> None:
        if value != self._auto_detect:
            self._auto_detect = value
            if value:
                Logger.log("i", "Auto-detect mode ENABLED - click to detect overhangs automatically")
            else:
                Logger.log("i", "Auto-detect mode DISABLED - manual cube placement")
            self.propertyChanged.emit()

    AutoDetect = pyqtProperty(bool, fget=getAutoDetect, fset=setAutoDetect)

    def getQmlPath(self):
        """Return the path to the QML file for the tool panel."""
        qml_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "qt6", "SupportImprover.qml")
        Logger.log("d", f"QML path: {qml_path}")
        return qml_path

    def event(self, event):
        super().event(event)
        modifiers = QApplication.keyboardModifiers()
        ctrl_is_active = modifiers & Qt.KeyboardModifier.ControlModifier

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons and self._controller.getToolsEnabled():
            if ctrl_is_active:
                self._controller.setActiveTool("TranslateTool")
                return

            if self._skip_press:
                # The selection was previously cleared, do not add/remove an anti-support mesh but
                # use this click for selection and reactivating this tool only.
                self._skip_press = False
                return

            if self._selection_pass is None:
                # The selection renderpass is used to identify objects in the current view
                self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")
            picked_node = self._controller.getScene().findObject(self._selection_pass.getIdAtPosition(event.x, event.y))
            if not picked_node:
                # There is no slicable object at the picked location
                return

            # EXPORT MODE: Export mesh for debugging
            if self._export_mode:
                Logger.log("i", "Export mode active - exporting mesh data for analysis")

                # Get the clicked position in 3D space
                active_camera = self._controller.getScene().getActiveCamera()
                picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
                picking_pass.render()
                picked_position = picking_pass.getPickedPosition(event.x, event.y)

                self._exportMeshData(picked_node, picked_position)
                return

            # AUTO-DETECT MODE: Automatically detect overhangs and create support blockers
            if self._auto_detect:
                Logger.log("i", "Auto-detect mode active - detecting overhangs automatically")
                self._autoDetectOverhangs(picked_node)
                return

            node_stack = picked_node.callDecoration("getStack")
            if node_stack:
                if node_stack.getProperty("anti_overhang_mesh", "value"):
                    self._removeEraserMesh(picked_node)
                    return

                elif node_stack.getProperty("support_mesh", "value") or node_stack.getProperty("infill_mesh", "value") or node_stack.getProperty("cutting_mesh", "value"):
                    # Only "normal" meshes can have anti_overhang_meshes added to them
                    return

            # Create a pass for picking a world-space location from the mouse location
            active_camera = self._controller.getScene().getActiveCamera()
            picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
            picking_pass.render()

            picked_position = picking_pass.getPickedPosition(event.x, event.y)

            # Add the anti_overhang_mesh cube at the picked location
            self._createModifierVolume(picked_node, picked_position)


    def setMeshType(self, node: CuraSceneNode, mesh_type: str) -> bool:
        """Set the mesh type for a specific node.
        Returns True when the mesh_type was changed, False when current mesh_type == mesh_type.
        """

        # Check the current mesh type of the node
        old_mesh_type = self.getMeshType(node)
        if old_mesh_type == mesh_type:
            return False

        if node is None:
            Logger.log("w", "Tried setting the mesh type of the provided node, but node is None.")
            return False

        stack = node.callDecoration("getStack")  # Get the setting stack for the node
        if not stack:
            node.addDecorator(SettingOverrideDecorator())
            stack = node.callDecoration("getStack")

        settings_visibility_changed = False
        settings = stack.getTop()

        # Iterate through each possible mesh type and set the new mesh type
        for property_key in ["infill_mesh", "cutting_mesh", "support_mesh", "anti_overhang_mesh"]:
            if property_key != mesh_type:
                if settings.getInstance(property_key):
                    settings.removeInstance(property_key)
            else:
                if not (settings.getInstance(property_key) and settings.getProperty(property_key, "value")):
                    definition = stack.getSettingDefinition(property_key)
                    new_instance = SettingInstance(definition, settings)
                    new_instance.setProperty("value", True)
                    new_instance.resetState()  # Ensure that the state is not seen as a user state.
                    settings.addInstance(new_instance)

        # Override some settings specifically for infill_mesh, or clean up if not an infill mesh
        specialized_settings = {
        #    "top_bottom_thickness": 0,
        #    "top_thickness": "=top_bottom_thickness",
        #    "bottom_thickness": "=top_bottom_thickness",
        #    "top_layers": "=0 if infill_sparse_density == 100 else math.ceil(round(top_thickness / resolveOrValue('layer_height'), 4))",
        #    "bottom_layers": "=0 if infill_sparse_density == 100 else math.ceil(round(bottom_thickness / resolveOrValue('layer_height'), 4))",
        #    "wall_thickness": 0,
        #    "wall_line_count": "=max(1, round((wall_thickness - wall_line_width_0) / wall_line_width_x) + 1) if wall_thickness != 0 else 0"
        }

        for property_key in specialized_settings:
            if mesh_type == "infill_mesh":
                if settings.getInstance(property_key) is None:
                    definition = stack.getSettingDefinition(property_key)
                    new_instance = SettingInstance(definition, settings)
                    new_instance.setProperty("value", specialized_settings[property_key])
                    new_instance.resetState()  # Ensure that the state is not seen as a user state.
                    settings.addInstance(new_instance)
                    settings_visibility_changed = True
            elif old_mesh_type == "infill_mesh" and settings.getInstance(property_key):
                settings.removeInstance(property_key)
                settings_visibility_changed = True

        if settings_visibility_changed:
            self.visibility_handler.forceVisibilityChanged()

        #self.propertyChangedSignal.emit()
        return True

    def getMeshType(self, node: CuraSceneNode) -> str:
        """Get the mesh type of a specific node."""
        if node is None:
            Logger.log("w", "Tried getting the mesh type of the provided node, but node is None.")
            return ""

        stack = node.callDecoration("getStack")
        if not stack:
            return ""

        settings = stack.getTop()
        for property_key in ["infill_mesh", "cutting_mesh", "support_mesh", "anti_overhang_mesh"]:
            if settings.getInstance(property_key) and settings.getProperty(property_key, "value"):
                return property_key

        return ""
    
    def onPropertyChanged(instance, property_name):
        Logger.log("d", f"Property '{property_name}' changed for instance '{instance.definition.key}'.")
        if property_name == "validationState":
            if instance.validationState and instance.validationState.isValid():
                Logger.log("i", "Setting is valid after change.")
            else:
                Logger.log("e", "Setting became invalid after change.")
            
    def _createModifierVolume(self, parent: CuraSceneNode, position: Vector): 
        try:
            node = CuraSceneNode()
            
            Logger.log("d", "Creating modifier volume node...")
        
            node.setName("Modifier Volume")
            node.setSelectable(True)
            node.setCalculateBoundingBox(True)

            # Get cube dimensions from properties
            cube_x = self._cube_x
            cube_y = self._cube_y
            cube_z = self._cube_z
            
            Logger.log("d", f"Creating cube with dimensions: X={cube_x}, Y={cube_y}, Z={cube_z}")
            
            # Create cube with the specified dimensions
            mesh = self._createCube(cube_x, cube_y, cube_z)
            node.setMeshData(mesh.build())
            node.calculateBoundingBoxMesh()

            active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
            node.addDecorator(BuildPlateDecorator(active_build_plate))
            node.addDecorator(SliceableObjectDecorator())
            
            current_mesh_type = self.getMeshType(node)
            if current_mesh_type == "infill_mesh":
                Logger.log("d", "Current mesh type is infill_mesh.")
            elif current_mesh_type == "cutting_mesh":
                Logger.log("d", "Current mesh type is cutting_mesh.")
            else:
                Logger.log("d", f"Current mesh type is {current_mesh_type}.")
                
            # Instead of manually setting the mesh type, use setMeshType
            if not self.setMeshType(node, "cutting_mesh"):
                Logger.log("e", "Failed to set mesh type to infill_mesh.")
                return

            stack = node.callDecoration("getStack")  # Stack is where settings modifications are stored
            if not stack:
                Logger.log("e", "Failed to retrieve stack from node decoration.")
                return
            
            settings = stack.getTop()
            
            Logger.log("i", "Modifier mesh type set successfully.")

            settingsList = {
            "support_z_distance": None,
            "support_top_distance": None,
            "support_xy_distance": None,
            "support_bottom_distance": None,
            "support_angle": None  # TODO: Why does it not work to set the angle here?
            }
            
            for property_key in settingsList:
                if settings.getInstance(property_key) is None:
                    definition = stack.getSettingDefinition(property_key)
                    new_instance = SettingInstance(definition, settings)
                    value = settingsList[property_key]
                    if value != None :
                        new_instance.setProperty("value", value)
                    new_instance.resetState()  # Ensure that the state is not seen as a user state.
                    settings.addInstance(new_instance)
       
            stack.setProperty("support_angle", "value", float(self._support_angle))
            Logger.log("d", "Set support_angle to " + str(self._support_angle) + " via stack.setProperty.")
            Logger.log("d", f"Now top property says: {stack.getProperty('support_angle', 'value')}")
            op = GroupedOperation()
            op.addOperation(AddSceneNodeOperation(node, self._controller.getScene().getRoot()))
            op.addOperation(SetParentOperation(node, parent))
            op.addOperation(TranslateOperation(node, position, set_position=True))
            op.push()

            CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)
                    
            Logger.log("i", "Modifier volume created and added to scene successfully.")
            
            
            #angle_instance.propertyChanged.disconnect(self.onPropertyChanged) #test
            
            
            
        except Exception as e:
            Logger.log("e", f"An error occurred while creating the modifier volume: {e}")

    def _removeEraserMesh(self, node: CuraSceneNode):
        parent = node.getParent()
        if parent == self._controller.getScene().getRoot():
            parent = None

        op = RemoveSceneNodeOperation(node)
        op.push()

        if parent and not Selection.isSelected(parent):
            Selection.add(parent)

        CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

    def _updateEnabled(self):
        plugin_enabled = False

        global_container_stack = CuraApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            plugin_enabled = global_container_stack.getProperty("anti_overhang_mesh", "enabled")

        # NOTE!!!
        # BE carefull messing things up here as it will give "imposible to slice due to settting" error

        # Set both the tool enabled state and the CanModify property
        #self.setProperty("CanModify", plugin_enabled)
        self.setCanModify = plugin_enabled
        
        CuraApplication.getInstance().getController().toolEnabledChanged.emit(self._plugin_id, plugin_enabled)

    def _onSelectionChanged(self):
        # When selection is passed from one object to another object, first the selection is cleared
        # and then it is set to the new object. We are only interested in the change from no selection
        # to a selection or vice-versa, not in a change from one object to another. A timer is used to
        # "merge" a possible clear/select action in a single frame
        if Selection.hasSelection() != self._had_selection:
            self._had_selection_timer.start()

    def _selectionChangeDelay(self):
        has_selection = Selection.hasSelection()
        if not has_selection and self._had_selection:
            self._skip_press = True
        else:
            self._skip_press = False

        self._had_selection = has_selection

    def _createCube(self, size_x, size_y, size_z):
        mesh = MeshBuilder()
        s_x = size_x / 2
        s_y = size_y / 2
        s_z = size_z / 2

        # Switched Y and Z coordinates order to fix dimensions
        verts = [ # 6 faces with 4 corners each:  [x, z, y] format
            [-s_x,  s_z, -s_y], [-s_x,  s_z,  s_y], [ s_x,  s_z,  s_y], [ s_x,  s_z, -s_y],  # top
            [-s_x, -s_z, -s_y], [-s_x, -s_z,  s_y], [ s_x, -s_z,  s_y], [ s_x, -s_z, -s_y],  # bottom
            [-s_x, -s_z, -s_y], [-s_x,  s_z, -s_y], [ s_x,  s_z, -s_y], [ s_x, -s_z, -s_y],  # back
            [-s_x, -s_z,  s_y], [-s_x,  s_z,  s_y], [ s_x,  s_z,  s_y], [ s_x, -s_z,  s_y],  # front
            [-s_x, -s_z, -s_y], [-s_x, -s_z,  s_y], [-s_x,  s_z,  s_y], [-s_x,  s_z, -s_y],  # left
            [ s_x, -s_z, -s_y], [ s_x, -s_z,  s_y], [ s_x,  s_z,  s_y], [ s_x,  s_z, -s_y]   # right
        ]
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        for i in range(0, 24, 4): # All 6 quads (12 triangles)
            indices.append([i, i+2, i+1])
            indices.append([i, i+3, i+2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh

    def _exportMeshData(self, node: CuraSceneNode, picked_position: Vector = None):
        """Export mesh data to files for external analysis"""
        import struct
        import time

        if not node or not node.getMeshData():
            Logger.log("e", "No mesh data available to export")
            return

        try:
            # Get transformed mesh data (with position/rotation applied)
            mesh_data = node.getMeshData().getTransformed(node.getWorldTransformation())

            # Get mesh arrays
            vertices = mesh_data.getVertices()
            has_indices = mesh_data.hasIndices()

            if has_indices:
                indices = mesh_data.getIndices()
            else:
                Logger.log("w", "Mesh has no indices - vertices only")
                indices = None

            # Log mesh info
            Logger.log("i", "=== MESH DATA EXPORT ===")
            Logger.log("i", f"Node name: {node.getName()}")
            Logger.log("i", f"Vertices: {len(vertices)}")
            Logger.log("i", f"Has indices: {has_indices}")
            if has_indices:
                Logger.log("i", f"Faces: {len(indices)}")

            # Log clicked position if available
            if picked_position:
                Logger.log("i", f"Clicked position: [{picked_position.x:.2f}, {picked_position.y:.2f}, {picked_position.z:.2f}]")

            # Create output directory
            output_dir = os.path.expanduser("~/MySupportImprover_exports")
            os.makedirs(output_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            base_filename = f"mesh_{node.getName()}_{timestamp}"

            # Export to STL (binary format)
            stl_path = os.path.join(output_dir, f"{base_filename}.stl")
            self._exportToSTL(mesh_data, stl_path)
            Logger.log("i", f"Exported STL to: {stl_path}")

            # Export to JSON (detailed data)
            json_path = os.path.join(output_dir, f"{base_filename}.json")
            self._exportToJSON(mesh_data, node, json_path, picked_position)
            Logger.log("i", f"Exported JSON to: {json_path}")

            Logger.log("i", f"=== EXPORT COMPLETE ===")
            Logger.log("i", f"Files saved to: {output_dir}")

        except Exception as e:
            Logger.log("e", f"Failed to export mesh data: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())

    def _exportToSTL(self, mesh_data, filepath):
        """Export mesh to binary STL format"""
        import struct

        vertices = mesh_data.getVertices()

        if mesh_data.hasIndices():
            indices = mesh_data.getIndices()
        else:
            # Create indices for non-indexed mesh
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        with open(filepath, 'wb') as f:
            # 80-byte header
            header = b'Binary STL exported from MySupportImprover'
            header = header.ljust(80, b'\x00')
            f.write(header)

            # Face count
            face_count = len(indices)
            f.write(struct.pack("<I", int(face_count)))

            # Write triangles
            for face in indices:
                try:
                    v0 = vertices[face[0]]
                    v1 = vertices[face[1]]
                    v2 = vertices[face[2]]

                    # Calculate normal
                    edge1 = v1 - v0
                    edge2 = v2 - v0
                    normal = numpy.cross(edge1, edge2)
                    normal_length = numpy.linalg.norm(normal)
                    if normal_length > 1e-10:
                        normal = normal / normal_length
                    else:
                        normal = numpy.array([0.0, 0.0, 1.0])

                    # Write normal
                    f.write(struct.pack("<fff", float(normal[0]), float(normal[1]), float(normal[2])))
                    # Write vertices
                    f.write(struct.pack("<fff", float(v0[0]), float(v0[1]), float(v0[2])))
                    f.write(struct.pack("<fff", float(v1[0]), float(v1[1]), float(v1[2])))
                    f.write(struct.pack("<fff", float(v2[0]), float(v2[1]), float(v2[2])))
                    # Attribute byte count
                    f.write(struct.pack("<H", 0))
                except Exception as e:
                    Logger.log("e", f"Error writing face: {e}")

    def _exportToJSON(self, mesh_data, node, filepath, picked_position: Vector = None):
        """Export detailed mesh data to JSON"""
        vertices = mesh_data.getVertices()

        data = {
            "node_name": node.getName(),
            "vertex_count": len(vertices),
            "has_indices": mesh_data.hasIndices(),
            "vertices": vertices.tolist(),
        }

        if mesh_data.hasIndices():
            indices = mesh_data.getIndices()
            data["face_count"] = len(indices)
            data["indices"] = indices.tolist()

        if mesh_data.hasNormals():
            normals = mesh_data.getNormals()
            data["normals"] = normals.tolist()

        # Add bounding box info
        data["bounds"] = {
            "min": vertices.min(axis=0).tolist(),
            "max": vertices.max(axis=0).tolist(),
            "center": vertices.mean(axis=0).tolist()
        }

        # Add clicked position if available
        if picked_position:
            click_pos = numpy.array([picked_position.x, picked_position.y, picked_position.z])
            data["clicked_position"] = click_pos.tolist()

            # Find closest face to clicked position
            if mesh_data.hasIndices():
                closest_face_id, closest_distance = self._findClosestFace(vertices, indices, click_pos)
                data["closest_face_id"] = int(closest_face_id)
                data["closest_face_distance"] = float(closest_distance)

                # Get the vertices of the closest face
                closest_face_indices = indices[closest_face_id]
                closest_face_vertices = [
                    vertices[closest_face_indices[0]].tolist(),
                    vertices[closest_face_indices[1]].tolist(),
                    vertices[closest_face_indices[2]].tolist()
                ]
                data["closest_face_vertices"] = closest_face_vertices

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def _findClosestFace(self, vertices, indices, point):
        """Find the closest face to a given point"""
        min_distance = float('inf')
        closest_face_id = 0

        for face_id, face in enumerate(indices):
            # Get face vertices
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            # Calculate face center (centroid)
            face_center = (v0 + v1 + v2) / 3.0

            # Calculate distance from point to face center
            distance = numpy.linalg.norm(face_center - point)

            if distance < min_distance:
                min_distance = distance
                closest_face_id = face_id

        return closest_face_id, min_distance

    def _autoDetectOverhangs(self, node: CuraSceneNode):
        """Automatically detect overhangs and create support blockers"""
        if not node or not node.getMeshData():
            Logger.log("e", "No mesh data available for overhang detection")
            return

        try:
            Logger.log("i", "=== AUTO OVERHANG DETECTION ===")

            # Get transformed mesh data
            mesh_data = node.getMeshData().getTransformed(node.getWorldTransformation())
            vertices = mesh_data.getVertices()

            # Handle non-indexed meshes
            if not mesh_data.hasIndices():
                Logger.log("i", "Non-indexed mesh detected, rebuilding indices...")
                vertices, indices = self._rebuildIndexedMesh(vertices)
            else:
                indices = mesh_data.getIndices()

            Logger.log("i", f"Mesh: {len(vertices)} vertices, {len(indices)} faces")

            # Detect overhang faces
            overhang_face_ids = self._detectOverhangFaces(vertices, indices, self._support_angle)
            Logger.log("i", f"Found {len(overhang_face_ids)} overhang faces")

            if len(overhang_face_ids) == 0:
                Logger.log("i", "No overhangs detected")
                return

            # Find connected regions
            regions = self._findConnectedRegions(vertices, indices, overhang_face_ids)
            Logger.log("i", f"Found {len(regions)} connected overhang regions")

            # Create support blockers for significant regions (more than 10 faces)
            min_faces = 10
            created_count = 0

            for region_id, region_faces in enumerate(regions):
                if len(region_faces) >= min_faces:
                    # Calculate region center and bounds
                    region_center, region_bounds = self._calculateRegionBounds(vertices, indices, region_faces)

                    # Create a support blocker at the region center
                    position = Vector(region_center[0], region_center[1], region_center[2])
                    self._createModifierVolume(node, position)
                    created_count += 1

                    Logger.log("i", f"Created support blocker for region {region_id+1} ({len(region_faces)} faces)")

            Logger.log("i", f"=== CREATED {created_count} SUPPORT BLOCKERS ===")

        except Exception as e:
            Logger.log("e", f"Failed to auto-detect overhangs: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())

    def _rebuildIndexedMesh(self, vertices):
        """Rebuild index buffer for non-indexed mesh by merging duplicate vertices"""
        Logger.log("i", f"Rebuilding indices from {len(vertices)} vertices...")

        vertex_map = {}
        unique_vertices = []
        indices = []
        tolerance = 1e-6

        for i in range(0, len(vertices), 3):
            triangle_indices = []
            for j in range(3):
                if i + j >= len(vertices):
                    break
                v = vertices[i + j]
                v_key = tuple(numpy.round(v / tolerance) * tolerance)

                if v_key in vertex_map:
                    triangle_indices.append(vertex_map[v_key])
                else:
                    vertex_idx = len(unique_vertices)
                    unique_vertices.append(v)
                    vertex_map[v_key] = vertex_idx
                    triangle_indices.append(vertex_idx)

            if len(triangle_indices) == 3:
                indices.append(triangle_indices)

        unique_vertices = numpy.array(unique_vertices, dtype=numpy.float32)
        indices = numpy.array(indices, dtype=numpy.int32)

        reduction = 100 * (1 - len(unique_vertices)/len(vertices))
        Logger.log("i", f"Vertex reduction: {reduction:.1f}% ({len(vertices)} → {len(unique_vertices)})")

        return unique_vertices, indices

    def _detectOverhangFaces(self, vertices, indices, threshold_angle):
        """Detect faces that are overhangs based on angle threshold"""
        threshold_rad = numpy.deg2rad(threshold_angle)
        overhang_faces = []

        for face_id, face in enumerate(indices):
            # Get face vertices
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            # Calculate face normal
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = numpy.cross(edge1, edge2)
            normal_length = numpy.linalg.norm(normal)

            if normal_length > 1e-10:
                normal = normal / normal_length

                # Calculate angle with up vector (0, 1, 0)
                up_vector = numpy.array([0.0, 1.0, 0.0])
                dot_product = numpy.dot(normal, up_vector)
                angle = numpy.arccos(numpy.clip(dot_product, -1.0, 1.0))

                # Check if angle exceeds threshold
                if angle > threshold_rad:
                    overhang_faces.append(face_id)

        return numpy.array(overhang_faces, dtype=numpy.int32)

    def _findConnectedRegions(self, vertices, indices, overhang_face_ids):
        """Find connected regions of overhang faces using BFS"""
        # Build adjacency graph
        adjacency = {}
        overhang_set = set(overhang_face_ids)

        # Build edge to face mapping
        edge_to_faces = {}
        for face_id in overhang_face_ids:
            face = indices[face_id]
            edges = [
                tuple(sorted([face[0], face[1]])),
                tuple(sorted([face[1], face[2]])),
                tuple(sorted([face[2], face[0]]))
            ]

            for edge in edges:
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(face_id)

        # Build adjacency list
        for edge, faces in edge_to_faces.items():
            if len(faces) == 2:
                f1, f2 = faces
                if f1 not in adjacency:
                    adjacency[f1] = []
                if f2 not in adjacency:
                    adjacency[f2] = []
                adjacency[f1].append(f2)
                adjacency[f2].append(f1)

        # Find connected regions using BFS
        visited = set()
        regions = []

        for start_face in overhang_face_ids:
            if start_face in visited:
                continue

            # BFS to find connected component
            region = []
            queue = [start_face]
            visited.add(start_face)

            while queue:
                current_face = queue.pop(0)
                region.append(current_face)

                if current_face in adjacency:
                    for neighbor in adjacency[current_face]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

            regions.append(region)

        # Sort regions by size (largest first)
        regions.sort(key=lambda r: len(r), reverse=True)

        return regions

    def _calculateRegionBounds(self, vertices, indices, region_face_ids):
        """Calculate the center and bounds of a region"""
        region_vertices = []

        for face_id in region_face_ids:
            face = indices[face_id]
            region_vertices.extend([
                vertices[face[0]],
                vertices[face[1]],
                vertices[face[2]]
            ])

        region_vertices = numpy.array(region_vertices)

        # Calculate bounds
        min_bounds = region_vertices.min(axis=0)
        max_bounds = region_vertices.max(axis=0)
        center = (min_bounds + max_bounds) / 2.0

        return center, (min_bounds, max_bounds)


    def _load_presets(self):
        """Load presets from the presets.json file."""
        try:
            self._presets_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "presets.json")
            if os.path.exists(self._presets_path):
                with open(self._presets_path, 'r') as f:
                    data = json.load(f)
                    self._presets = data.get("presets", {})
                    Logger.log("i", f"Loaded {len(self._presets)} presets from presets.json")
            else:
                Logger.log("w", "presets.json not found, using default presets")
                self._presets = {
                    "Small": {"x": 2.0, "y": 2.0, "z": 2.0},
                    "Medium": {"x": 3.0, "y": 3.0, "z": 3.0},
                    "Large": {"x": 5.0, "y": 5.0, "z": 5.0}
                }
                # Save default presets to file
                self._save_presets_to_file()
        except Exception as e:
            Logger.log("e", f"Error loading presets: {e}")
            self._presets = {
                "Small": {"x": 2.0, "y": 2.0, "z": 2.0},
                "Medium": {"x": 3.0, "y": 3.0, "z": 3.0},
                "Large": {"x": 5.0, "y": 5.0, "z": 5.0}
            }

    def _save_presets_to_file(self):
        """Save presets to the JSON file."""
        try:
            data = {"presets": self._presets}
            with open(self._presets_path, 'w') as f:
                json.dump(data, f, indent=4)
            Logger.log("i", f"Saved {len(self._presets)} presets to presets.json")
        except Exception as e:
            Logger.log("e", f"Error saving presets: {e}")

    def savePreset(self, preset_name):
        """Save current dimensions as a new preset."""
        if not preset_name:
            Logger.log("w", "Cannot save preset with empty name")
            return False
            
        if preset_name in ["Custom"]:
            Logger.log("w", "Cannot use reserved name 'Custom' for preset")
            return False
            
        # Create new preset with current dimensions
        new_preset = {
            "x": float(self._cube_x),
            "y": float(self._cube_y),
            "z": float(self._cube_z)
        }
        
        # Add to presets dictionary
        self._presets[preset_name] = new_preset
        
        # Save to file
        self._save_presets_to_file()
        
        # Update current preset
        self._is_custom = False
        self.setCurrentPreset(preset_name)
        
        # Notify UI of changes
        self.propertyChanged.emit()
        
        Logger.log("i", f"Saved new preset: {preset_name}")
        return True

    def applyPreset(self, preset_name):
        """Apply a preset to the cube dimensions."""
        if preset_name == "Custom":
            self.setIsCustom(True)
            return
            
        if preset_name in self._presets:
            preset = self._presets[preset_name]
            self._cube_x = float(preset["x"])
            self._cube_y = float(preset["y"])          
            self._cube_z = float(preset["z"])
            self._is_custom = False
            self.setCurrentPreset(preset_name)
            self.propertyChanged.emit()
            Logger.log("i", f"Applied preset: {preset_name}")
        else:
            Logger.log("w", f"Preset not found: {preset_name}")
