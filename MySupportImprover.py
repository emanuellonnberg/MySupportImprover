# Cura is released under the terms of the LGPLv3 or higher.

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

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

class SupportImprover(Tool):
    def __init__(self):
        super().__init__()
        self._shortcut_key = Qt.Key.Key_E
        self._controller = self.getController()

        self._selection_pass = None
        CuraApplication.getInstance().globalContainerStackChanged.connect(self._updateEnabled)

        # Note: if the selection is cleared with this tool active, there is no way to switch to
        # another tool than to reselect an object (by clicking it) because the tool buttons in the
        # toolbar will have been disabled. That is why we need to ignore the first press event
        # after the selection has been cleared.
        Selection.selectionChanged.connect(self._onSelectionChanged)
        self._had_selection = False
        self._skip_press = False

        self._had_selection_timer = QTimer()
        self._had_selection_timer.setInterval(0)
        self._had_selection_timer.setSingleShot(True)
        self._had_selection_timer.timeout.connect(self._selectionChangeDelay)

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

        self.propertyChanged.emit()
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
            mesh = self._createCube(3)
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
            
            #modifier_definition = stack.getSettingDefinition("mesh_type")
            #modifier_instance = SettingInstance(modifier_definition, settings)
            #modifier_instance.setProperty("value", "cutting_mesh")  # This sets the mesh type to a modifier mesh
            #modifier_instance.resetState()  # Ensure that the state is not seen as a user state.
            #settings.addInstance(modifier_instance)

            # Example: Modify the infill density setting
            #infill_definition = stack.getSettingDefinition("infill_sparse_density")
            #infill_instance = SettingInstance(infill_definition, settings)
            #infill_instance.setProperty("value", 20)  # Set infill density to 20%
            #infill_instance.resetState()  # Ensure that the state is not seen as a user state.
            #settings.addInstance(infill_instance)


            Logger.log("i", "Modifier mesh type set successfully.")

            # Now set the specific setting you want to modify within this mesh
            #angle_definition = stack.getSettingDefinition("support_angle")

            #Log the properties of the angle_definition to understand what it requires
            # Print out all attributes of angle_definition
            #Logger.log("d", f"Attributes of angle_definition: {dir(angle_definition)}")
            
            #angle_instance = settings.getInstance("support_angle")
            #if not angle_instance:
            #    angle_instance = SettingInstance(angle_definition, settings)
            #   settings.addInstance(angle_instance)

            # Log the current values of all properties of the SettingInstance
            #property_names = angle_instance.getPropertyNames()
            #Logger.log("d", f"Supported property names for 'support_angle' angle_instance: {property_names}")
            #for prop in property_names:
            #    try:
            #        prop_value = angle_instance.getProperty(prop)
            #        Logger.log("d", f"Property '{prop}' - Current Value: {prop_value}")
            #    except Exception as e:
            #        Logger.log("e", f"Failed to get value for property '{prop}': {e}")
                    
                
            # Log all property names supported by this setting definition
            #property_names = angle_definition.getPropertyNames()
            #Logger.log("d", f"Supported property names for 'support_angle': {property_names}")
            
            #for prop in property_names:
            #    prop_type = angle_definition.getPropertyType(prop)
            #    is_read_only = angle_definition.isReadOnlyProperty(prop)
            #    prop_value = angle_definition.getProperty(prop)
            #    Logger.log("d", f"Property '{prop}' - Type: {prop_type}, Read-Only: {is_read_only}, value {prop_value} ")
                        
   
            # Remove existing 'support_angle' setting instances if necessary
            #if settings.getInstance("support_angle"):
            #    settings.removeInstance("support_angle")

            # Create a new setting instance for 'support_angle'
            #angle_definition = stack.getSettingDefinition("support_angle")
            #if not angle_definition:
            #    Logger.log("e", "Could not retrieve the definition for 'support_angle'.")
            #    return

            #angle_instance = SettingInstance(angle_definition, settings)
            #angle_instance.setProperty("value", "45.0")  # Set the desired support angle value
            #angle_instance.resetState()  # Ensure the state is not seen as a user override
            #settings.addInstance(angle_instance)
            
            
            settingsList = {
            "support_z_distance": None,
            "support_top_distance": None,
            "support_xy_distance": None,
            "support_bottom_distance": None,
            "support_angle": "=45"  
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
       
            definition = stack.getSettingDefinition("support_angle")  
            
            property_names = definition.getPropertyNames()
            Logger.log("d", f"Supported property names for 'support_angle': {property_names}")

            value = stack.getProperty("support_angle", "value")
            Logger.log("d", f"angle = {value}")
                            
            # Set the support_angle value
            angle_definition = stack.getSettingDefinition("support_angle")
            if not angle_definition:
                Logger.log("e", "Could not retrieve the definition for 'support_angle'.")
                return

            # Check if a validator exists for this setting type
            validator_type = angle_definition.getValidatorForType(angle_definition.type)
            validator = validator_type("support_angle")
            if validator:
                Logger.log("d", f"Methods and attributes of Validator object: {dir(validator)}")
            else:
                Logger.log("e", "Validator object not found for 'support_angle'.")
            #if validator_type:


            # Assuming you found a validator, validate the desired value before setting it
            
            angle_instance = settings.getInstance("support_angle")
            
            #angle_instance.propertyChanged.connect(self.onPropertyChanged) #test
            
            if not angle_instance:
                angle_instance = SettingInstance(angle_definition, settings)
                settings.addInstance(angle_instance)

            try:
                angle_instance.setProperty("value", 52.0)  # Try setting with a valid number
                angle_instance.resetState()  # Reset state to ensure it’s not treated as a user override
                if validator.isValid():  # Call isValid with no additional arguments
                    Logger.log("i", "Setting 'support_angle' to 45 is valid after applying the change.")
                else:
                    Logger.log("e", "Setting 'support_angle' to 45 is not valid after applying the change.")
                # Handle invalid state, possibly revert changes or alert user
                Logger.log("i", "Support angle 'value' set to 45 successfully.")
            except Exception as e:
                Logger.log("e", f"Failed to set support angle 'value': {e}")

            # Re-check the property value after setting
            #current_value = stack.getProperty("support_angle", "value")
            #Logger.log("d", f"Current 'support_angle' value after setting: {current_value}")           
                          
            #min_value = stack.getProperty("support_angle", "minimum_value")
            #max_value = stack.getProperty("support_angle", "maximum_value")
            #Logger.log("d", f"Support angle constraints - Min: {min_value}, Max: {max_value}")
            
            # Log any dependencies or overrides for 'support_angle'
            #dependencies = stack.getProperty("support_angle", "depends_on_property")
            #overrides = stack.getProperty("support_angle", "overrides")
            #type = stack.getProperty("support_angle", "type")
            #setableMesh = stack.getProperty("support_angle", "settable_per_mesh")
            #settablePerMeshgroup = stack.getProperty("support_angle", "settable_per_meshgroup")
            #resolve = stack.getProperty("support_angle", "resolve")
            #Logger.log("d", f"'support_angle' settablePerMeshgroup: {settablePerMeshgroup}")
            #Logger.log("d", f"'support_angle' setableMesh: {setableMesh}")
            #Logger.log("d", f"'support_angle' dependencies: {dependencies}")
            #Logger.log("d", f"'support_angle' overrides: {overrides}")
            #Logger.log("d", f"'support_angle' type: {type}")
            #Logger.log("d", f"'support_angle' resolve: {resolve}")
            #self.visibility_handler.forceVisibilityChanged()
            
            #CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

            # Re-check the property value after forcing an update
            current_value = stack.getProperty("support_angle", "value")
            Logger.log("d", f"Current 'support_angle' value after forcing update: {current_value}")

            self.propertyChanged.emit()        
                        
            Logger.log("i", "Support overhang angle set successfully.")

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

    def _createCube(self, size):
        mesh = MeshBuilder()

        # Can't use MeshBuilder.addCube() because that does not get per-vertex normals
        # Per-vertex normals require duplication of vertices
        s = size / 2
        verts = [ # 6 faces with 4 corners each
            [-s, -s,  s], [-s,  s,  s], [ s,  s,  s], [ s, -s,  s],
            [-s,  s, -s], [-s, -s, -s], [ s, -s, -s], [ s,  s, -s],
            [ s, -s, -s], [-s, -s, -s], [-s, -s,  s], [ s, -s,  s],
            [-s,  s, -s], [ s,  s, -s], [ s,  s,  s], [-s,  s,  s],
            [-s, -s,  s], [-s, -s, -s], [-s,  s, -s], [-s,  s,  s],
            [ s, -s, -s], [ s, -s,  s], [ s,  s,  s], [ s,  s, -s]
        ]
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        for i in range(0, 24, 4): # All 6 quads (12 triangles)
            indices.append([i, i+2, i+1])
            indices.append([i, i+3, i+2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh
