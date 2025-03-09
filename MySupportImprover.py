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
        
        self.setExposedProperties("CubeX", "CubeY", "CubeZ", "ShowSettings", "CanModify", "Presets", "SupportAngle")
        
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
            Logger.log("d", "CubeX changed to %s", str(self._cube_x))

    def getCubeY(self) -> float:
        return self._cube_y

    def setCubeY(self, value: float) -> None:
        if value != self._cube_y:
            self._cube_y = float(value)
            Logger.log("d", "CubeY changed to %s", str(self._cube_y))

    def getCubeZ(self) -> float:
        return self._cube_z

    def setCubeZ(self, value: float) -> None:
        if value != self._cube_z:
            self._cube_z = float(value)
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

    def getQmlPath(self):
        """Return the path to the QML file for the tool panel."""
        qml_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "qt6", "SupportImprover.qml")
        Logger.log("d", f"QML path: {qml_path}")
        return qml_path


    #def triggerAction(self, action_name, *args):
    #    """Handle actions triggered from the QML interface."""
    #    Logger.log("d", "triggerAction called: %s", action_name)
    #    if action_name == "addModifier":
    #        # This will be handled by the event() function when clicking in the scene
    #        pass
    #    elif action_name == "showSettings":
    #        self.setProperty("ShowSettings", True)
    #        # Add your settings panel show logic here
    #    elif action_name == "hideSettings":
    #        self.setProperty("ShowSettings", False)
    #        # Add your settings panel hide logic here
    #    elif action_name == "selectPreset":
    #        if len(args) > 0:
    #            preset_name = args[0]
    #            self._applyPreset(preset_name)

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

    def _load_presets(self):
        """Load presets from the presets.json file."""
        try:
            presets_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "presets.json")
            if os.path.exists(presets_path):
                with open(presets_path, 'r') as f:
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
        except Exception as e:
            Logger.log("e", f"Error loading presets: {e}")
            self._presets = {
                "Small": {"x": 2.0, "y": 2.0, "z": 2.0},
                "Medium": {"x": 3.0, "y": 3.0, "z": 3.0},
                "Large": {"x": 5.0, "y": 5.0, "z": 5.0}
            }

    def applyPreset(self, preset_name):
        """Apply a preset to the cube dimensions."""
        if preset_name in self._presets:
            preset = self._presets[preset_name]
            self._cube_x = float(preset["x"])
            self._cube_y = float(preset["y"])          
            self._cube_z = float(preset["z"])
            self.propertyChanged.emit()
            Logger.log("i", f"Applied preset: {preset_name}")
        else:
            Logger.log("w", f"Preset not found: {preset_name}")
