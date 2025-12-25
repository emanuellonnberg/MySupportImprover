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
from UM.Operations.RotateOperation import RotateOperation
from UM.Math.Quaternion import Quaternion
import math
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
from collections import deque
from typing import List, Dict, Set, Tuple, Optional

# Suggested solution from fieldOfView . in this discussion solved in Cura 4.9
# https://github.com/5axes/Calibration-Shapes/issues/1
# Cura are able to find the scripts from inside the plugin folder if the scripts are into a folder named resources
#Resources.addSearchPath(
#    os.path.join(os.path.abspath(os.path.dirname(__file__)),'resources')
#)  # Plugin translation file import

class MySupportImprover(Tool):
    # Support mode constants
    SUPPORT_MODE_STRUCTURAL = "structural"
    SUPPORT_MODE_STABILITY = "stability"
    SUPPORT_MODE_CUSTOM = "custom"
    SUPPORT_MODE_WING = "wing"  # Attached stability wing

    # Wing direction constants
    WING_DIRECTION_TO_BUILDPLATE = "to_buildplate"
    WING_DIRECTION_HORIZONTAL = "horizontal"

    # Support mode presets with Cura setting values
    SUPPORT_MODE_SETTINGS = {
        "structural": {
            "support_pattern": "grid",
            "support_infill_rate": 15,
            "support_line_width": 0.4,
            "support_wall_count": 1,
            "support_interface_enable": True,
            "support_roof_enable": True,
            "support_bottom_enable": True,
            "description": "Dense support for load-bearing (under tip)"
        },
        "stability": {
            "support_pattern": "lines",
            "support_infill_rate": 5,
            "support_line_width": 0.3,
            "support_wall_count": 1,
            "support_interface_enable": False,
            "support_roof_enable": False,
            "support_bottom_enable": False,
            "description": "Minimal support for edge stabilization"
        },
        "custom": {
            "support_pattern": "lines",
            "support_infill_rate": 10,
            "support_line_width": 0.4,
            "support_wall_count": 0,
            "support_interface_enable": False,
            "support_roof_enable": False,
            "support_bottom_enable": False,
            "description": "Custom support settings"
        },
        "wing": {
            "description": "Attached wing extending to build plate or horizontal"
        }
    }

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

        # Support mode settings
        self._support_mode = self.SUPPORT_MODE_STRUCTURAL  # Default to structural
        self._support_pattern = "grid"
        self._support_infill_rate = 15
        self._support_line_width = 0.4
        self._support_wall_count = 1
        self._support_interface_enable = True
        self._support_roof_enable = True
        self._support_bottom_enable = True

        # Overhang detection settings
        self._overhang_threshold = 45.0  # degrees - typical for PLA
        self._detected_overhangs = []  # List of detected overhang regions
        self._overhang_adjacency = {}  # Face adjacency graph
        self._overhang_angles = None  # Cached overhang angles per face

        # Wing-specific settings
        self._wing_direction = self.WING_DIRECTION_TO_BUILDPLATE
        self._wing_thickness = 1.5  # mm - thickness of the wing
        self._wing_width = 5.0  # mm - width of the wing (perpendicular to edge)
        self._wing_angle = 0.0  # degrees - angle from vertical (0 = straight down)
        self._wing_breakline_enable = True  # Enable break-line for easy removal
        self._wing_breakline_depth = 0.5  # mm - how deep the break-line notch is
        self._wing_breakline_position = 2.0  # mm - distance from top of wing
        self._wing_rotation = 0.0  # degrees - rotation around vertical axis

        self.setExposedProperties(
            "CubeX", "CubeY", "CubeZ", "ShowSettings", "CanModify", "Presets",
            "SupportAngle", "CurrentPreset", "IsCustom",
            # Support mode properties
            "SupportMode", "SupportModes", "SupportPattern", "SupportInfillRate",
            "SupportLineWidth", "SupportWallCount", "SupportInterfaceEnable",
            "SupportRoofEnable", "SupportBottomEnable", "SupportModeDescription",
            # Wing properties
            "WingDirection", "WingThickness", "WingWidth", "WingAngle",
            "WingBreaklineEnable", "WingBreaklineDepth", "WingBreaklinePosition",
            "WingRotation",
            # Overhang detection properties
            "OverhangThreshold", "DetectedOverhangCount"
        )
        
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

    # Support Mode Properties
    def getSupportMode(self) -> str:
        return self._support_mode

    def setSupportMode(self, mode: str) -> None:
        if mode != self._support_mode and mode in self.SUPPORT_MODE_SETTINGS:
            self._support_mode = mode
            # Apply preset settings for this mode
            settings = self.SUPPORT_MODE_SETTINGS[mode]
            self._support_pattern = settings["support_pattern"]
            self._support_infill_rate = settings["support_infill_rate"]
            self._support_line_width = settings["support_line_width"]
            self._support_wall_count = settings["support_wall_count"]
            self._support_interface_enable = settings["support_interface_enable"]
            self._support_roof_enable = settings["support_roof_enable"]
            self._support_bottom_enable = settings["support_bottom_enable"]
            Logger.log("d", f"Support mode changed to {mode}")
            self.propertyChanged.emit()

    SupportMode = pyqtProperty(str, fget=getSupportMode, fset=setSupportMode)

    def getSupportModes(self) -> list:
        """Return list of available support modes for UI dropdown."""
        return [
            {"value": "structural", "label": "Structural (Dense)"},
            {"value": "stability", "label": "Stability (Minimal)"},
            {"value": "wing", "label": "Attached Wing"},
            {"value": "custom", "label": "Custom"}
        ]

    SupportModes = pyqtProperty("QVariantList", fget=getSupportModes)

    def getSupportModeDescription(self) -> str:
        """Return description of current support mode."""
        return self.SUPPORT_MODE_SETTINGS.get(self._support_mode, {}).get("description", "")

    SupportModeDescription = pyqtProperty(str, fget=getSupportModeDescription)

    def getSupportPattern(self) -> str:
        return self._support_pattern

    def setSupportPattern(self, value: str) -> None:
        if value != self._support_pattern:
            self._support_pattern = value
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportPattern = pyqtProperty(str, fget=getSupportPattern, fset=setSupportPattern)

    def getSupportInfillRate(self) -> int:
        return self._support_infill_rate

    def setSupportInfillRate(self, value: int) -> None:
        if value != self._support_infill_rate:
            self._support_infill_rate = int(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportInfillRate = pyqtProperty(int, fget=getSupportInfillRate, fset=setSupportInfillRate)

    def getSupportLineWidth(self) -> float:
        return self._support_line_width

    def setSupportLineWidth(self, value: float) -> None:
        if value != self._support_line_width:
            self._support_line_width = float(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportLineWidth = pyqtProperty(float, fget=getSupportLineWidth, fset=setSupportLineWidth)

    def getSupportWallCount(self) -> int:
        return self._support_wall_count

    def setSupportWallCount(self, value: int) -> None:
        if value != self._support_wall_count:
            self._support_wall_count = int(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportWallCount = pyqtProperty(int, fget=getSupportWallCount, fset=setSupportWallCount)

    def getSupportInterfaceEnable(self) -> bool:
        return self._support_interface_enable

    def setSupportInterfaceEnable(self, value: bool) -> None:
        if value != self._support_interface_enable:
            self._support_interface_enable = bool(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportInterfaceEnable = pyqtProperty(bool, fget=getSupportInterfaceEnable, fset=setSupportInterfaceEnable)

    def getSupportRoofEnable(self) -> bool:
        return self._support_roof_enable

    def setSupportRoofEnable(self, value: bool) -> None:
        if value != self._support_roof_enable:
            self._support_roof_enable = bool(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportRoofEnable = pyqtProperty(bool, fget=getSupportRoofEnable, fset=setSupportRoofEnable)

    def getSupportBottomEnable(self) -> bool:
        return self._support_bottom_enable

    def setSupportBottomEnable(self, value: bool) -> None:
        if value != self._support_bottom_enable:
            self._support_bottom_enable = bool(value)
            self._support_mode = self.SUPPORT_MODE_CUSTOM
            self.propertyChanged.emit()

    SupportBottomEnable = pyqtProperty(bool, fget=getSupportBottomEnable, fset=getSupportBottomEnable)

    # Wing Properties
    def getWingDirection(self) -> str:
        return self._wing_direction

    def setWingDirection(self, value: str) -> None:
        if value != self._wing_direction:
            self._wing_direction = value
            self.propertyChanged.emit()

    WingDirection = pyqtProperty(str, fget=getWingDirection, fset=setWingDirection)

    def getWingThickness(self) -> float:
        return self._wing_thickness

    def setWingThickness(self, value: float) -> None:
        if value != self._wing_thickness:
            self._wing_thickness = float(value)
            self.propertyChanged.emit()

    WingThickness = pyqtProperty(float, fget=getWingThickness, fset=setWingThickness)

    def getWingWidth(self) -> float:
        return self._wing_width

    def setWingWidth(self, value: float) -> None:
        if value != self._wing_width:
            self._wing_width = float(value)
            self.propertyChanged.emit()

    WingWidth = pyqtProperty(float, fget=getWingWidth, fset=setWingWidth)

    def getWingAngle(self) -> float:
        return self._wing_angle

    def setWingAngle(self, value: float) -> None:
        if value != self._wing_angle:
            self._wing_angle = float(value)
            self.propertyChanged.emit()

    WingAngle = pyqtProperty(float, fget=getWingAngle, fset=setWingAngle)

    def getWingBreaklineEnable(self) -> bool:
        return self._wing_breakline_enable

    def setWingBreaklineEnable(self, value: bool) -> None:
        if value != self._wing_breakline_enable:
            self._wing_breakline_enable = bool(value)
            self.propertyChanged.emit()

    WingBreaklineEnable = pyqtProperty(bool, fget=getWingBreaklineEnable, fset=setWingBreaklineEnable)

    def getWingBreaklineDepth(self) -> float:
        return self._wing_breakline_depth

    def setWingBreaklineDepth(self, value: float) -> None:
        if value != self._wing_breakline_depth:
            self._wing_breakline_depth = float(value)
            self.propertyChanged.emit()

    WingBreaklineDepth = pyqtProperty(float, fget=getWingBreaklineDepth, fset=setWingBreaklineDepth)

    def getWingBreaklinePosition(self) -> float:
        return self._wing_breakline_position

    def setWingBreaklinePosition(self, value: float) -> None:
        if value != self._wing_breakline_position:
            self._wing_breakline_position = float(value)
            self.propertyChanged.emit()

    WingBreaklinePosition = pyqtProperty(float, fget=getWingBreaklinePosition, fset=setWingBreaklinePosition)

    def getWingRotation(self) -> float:
        return self._wing_rotation

    def setWingRotation(self, value: float) -> None:
        # Normalize to -180 to 180 range
        value = float(value)
        while value > 180:
            value -= 360
        while value < -180:
            value += 360
        if value != self._wing_rotation:
            self._wing_rotation = value
            self.propertyChanged.emit()

    WingRotation = pyqtProperty(float, fget=getWingRotation, fset=setWingRotation)

    def applySupportMode(self, mode: str) -> None:
        """Apply a support mode preset. Called from QML."""
        self.setSupportMode(mode)

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

            # Create different geometry based on support mode
            if self._support_mode == self.SUPPORT_MODE_WING:
                # Create attached wing geometry
                self._createAttachedWing(picked_node, picked_position)
            else:
                # Add the support modifier volume at the picked location
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
        
            # Name the node based on support mode for easy identification
            mode_names = {
                "structural": "Structural Support Volume",
                "stability": "Stability Support Volume",
                "custom": "Custom Support Volume"
            }
            node.setName(mode_names.get(self._support_mode, "Modifier Volume"))
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

            # Basic support settings (always included)
            basicSettingsList = {
                "support_z_distance": None,
                "support_top_distance": None,
                "support_xy_distance": None,
                "support_bottom_distance": None,
                "support_angle": None
            }

            # Extended support settings based on support mode
            extendedSettingsList = {
                "support_pattern": self._support_pattern,
                "support_infill_rate": self._support_infill_rate,
                "support_line_width": self._support_line_width,
                "support_wall_count": self._support_wall_count,
                "support_interface_enable": self._support_interface_enable,
                "support_roof_enable": self._support_roof_enable,
                "support_bottom_enable": self._support_bottom_enable
            }

            # Apply basic settings
            for property_key in basicSettingsList:
                if settings.getInstance(property_key) is None:
                    definition = stack.getSettingDefinition(property_key)
                    if definition:
                        new_instance = SettingInstance(definition, settings)
                        value = basicSettingsList[property_key]
                        if value is not None:
                            new_instance.setProperty("value", value)
                        new_instance.resetState()
                        settings.addInstance(new_instance)

            # Apply extended support mode settings
            for property_key, value in extendedSettingsList.items():
                definition = stack.getSettingDefinition(property_key)
                if definition:
                    if settings.getInstance(property_key) is None:
                        new_instance = SettingInstance(definition, settings)
                        new_instance.setProperty("value", value)
                        new_instance.resetState()
                        settings.addInstance(new_instance)
                    else:
                        stack.setProperty(property_key, "value", value)
                    Logger.log("d", f"Set {property_key} to {value}")

            stack.setProperty("support_angle", "value", float(self._support_angle))
            Logger.log("d", f"Applied support mode '{self._support_mode}' settings to modifier volume")
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

    def _createWingMesh(self, width: float, thickness: float, height: float,
                        breakline_enable: bool = False, breakline_depth: float = 0.5,
                        breakline_position: float = 2.0, breakline_height: float = 0.8):
        """Create a thin wing/fin mesh, optionally with a break-line notch.

        The wing is oriented as a vertical plate:
        - Width: along X axis (how wide the wing extends from the attachment point)
        - Thickness: along Y axis (how thin the wing is)
        - Height: along Z axis (how tall the wing is, from top to bottom)

        The wing is centered at origin, with the top at Z=height/2

        If breakline_enable is True, a notch is created near the top of the wing
        to make it easier to snap off after printing.
        """
        mesh = MeshBuilder()
        w = width / 2
        t = thickness / 2
        h = height / 2

        if not breakline_enable or height < (breakline_position + breakline_height + 1.0):
            # Simple wing without break-line (or wing too short for break-line)
            # Cura uses [x, z, y] coordinate format
            verts = [
                # Top face
                [-w,  h, -t], [-w,  h,  t], [ w,  h,  t], [ w,  h, -t],
                # Bottom face
                [-w, -h, -t], [-w, -h,  t], [ w, -h,  t], [ w, -h, -t],
                # Back face (Y-)
                [-w, -h, -t], [-w,  h, -t], [ w,  h, -t], [ w, -h, -t],
                # Front face (Y+)
                [-w, -h,  t], [-w,  h,  t], [ w,  h,  t], [ w, -h,  t],
                # Left face (X-)
                [-w, -h, -t], [-w, -h,  t], [-w,  h,  t], [-w,  h, -t],
                # Right face (X+)
                [ w, -h, -t], [ w, -h,  t], [ w,  h,  t], [ w,  h, -t]
            ]
            mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

            indices = []
            for i in range(0, 24, 4):
                indices.append([i, i+2, i+1])
                indices.append([i, i+3, i+2])
            mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))
        else:
            # Wing with break-line notch
            # The notch is a thinner section near the top
            # We create 3 sections: top (above notch), notch (thin), bottom (below notch)

            notch_top = h - breakline_position  # Y position of notch top
            notch_bottom = notch_top - breakline_height  # Y position of notch bottom
            notch_thickness = t - breakline_depth  # Reduced thickness at notch (on both sides)

            # Ensure notch doesn't go below the bottom
            if notch_bottom < -h:
                notch_bottom = -h + 0.5

            # Ensure some thickness remains
            if notch_thickness < 0.2:
                notch_thickness = 0.2

            Logger.log("d", f"Creating wing with break-line: notch_top={notch_top:.2f}, "
                          f"notch_bottom={notch_bottom:.2f}, notch_thickness={notch_thickness:.2f}")

            # Build a more complex mesh with the notch
            # We'll create the wing as three boxes stacked vertically
            verts = []
            indices = []
            vert_offset = 0

            def add_box(x_min, x_max, y_min, y_max, z_min, z_max, verts, indices, offset):
                """Add a box to the mesh."""
                box_verts = [
                    # Top face
                    [x_min, y_max, z_min], [x_min, y_max, z_max], [x_max, y_max, z_max], [x_max, y_max, z_min],
                    # Bottom face
                    [x_min, y_min, z_min], [x_min, y_min, z_max], [x_max, y_min, z_max], [x_max, y_min, z_min],
                    # Back face
                    [x_min, y_min, z_min], [x_min, y_max, z_min], [x_max, y_max, z_min], [x_max, y_min, z_min],
                    # Front face
                    [x_min, y_min, z_max], [x_min, y_max, z_max], [x_max, y_max, z_max], [x_max, y_min, z_max],
                    # Left face
                    [x_min, y_min, z_min], [x_min, y_min, z_max], [x_min, y_max, z_max], [x_min, y_max, z_min],
                    # Right face
                    [x_max, y_min, z_min], [x_max, y_min, z_max], [x_max, y_max, z_max], [x_max, y_max, z_min]
                ]
                verts.extend(box_verts)

                for i in range(0, 24, 4):
                    indices.append([offset + i, offset + i + 2, offset + i + 1])
                    indices.append([offset + i, offset + i + 3, offset + i + 2])

                return offset + 24

            # Top section (above notch) - full thickness
            if notch_top < h:
                vert_offset = add_box(-w, w, notch_top, h, -t, t, verts, indices, vert_offset)

            # Notch section (thin) - reduced thickness
            vert_offset = add_box(-w, w, notch_bottom, notch_top, -notch_thickness, notch_thickness, verts, indices, vert_offset)

            # Bottom section (below notch) - full thickness
            if notch_bottom > -h:
                vert_offset = add_box(-w, w, -h, notch_bottom, -t, t, verts, indices, vert_offset)

            mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))
            mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh

    def _checkWingCollision(self, parent: CuraSceneNode, wing_position: Vector,
                            wing_width: float, wing_thickness: float, wing_height: float) -> dict:
        """Check if the proposed wing would collide with the parent model.

        Returns a dict with:
        - 'collides': bool - whether collision detected
        - 'message': str - description of the collision
        - 'suggested_adjustment': Vector or None - suggested position adjustment
        """
        try:
            # Get parent mesh bounding box
            parent_bbox = parent.getBoundingBox()
            if not parent_bbox:
                Logger.log("w", "Could not get parent bounding box for collision check")
                return {"collides": False, "message": "", "suggested_adjustment": None}

            # Calculate wing bounding box at the proposed position
            half_width = wing_width / 2
            half_thickness = wing_thickness / 2
            half_height = wing_height / 2

            wing_min_x = wing_position.x - half_width
            wing_max_x = wing_position.x + half_width
            wing_min_y = wing_position.y - half_height
            wing_max_y = wing_position.y + half_height
            wing_min_z = wing_position.z - half_thickness
            wing_max_z = wing_position.z + half_thickness

            # Get parent bounding box extents
            parent_min = parent_bbox.minimum
            parent_max = parent_bbox.maximum

            Logger.log("d", f"Wing bbox: X[{wing_min_x:.2f}, {wing_max_x:.2f}], "
                          f"Y[{wing_min_y:.2f}, {wing_max_y:.2f}], Z[{wing_min_z:.2f}, {wing_max_z:.2f}]")
            Logger.log("d", f"Parent bbox: min={parent_min}, max={parent_max}")

            # Check for bounding box intersection
            x_overlap = wing_min_x < parent_max.x and wing_max_x > parent_min.x
            y_overlap = wing_min_y < parent_max.y and wing_max_y > parent_min.y
            z_overlap = wing_min_z < parent_max.z and wing_max_z > parent_min.z

            if x_overlap and y_overlap and z_overlap:
                # Bounding boxes overlap - potential collision
                # Calculate how much the wing is inside the parent
                x_penetration = min(wing_max_x - parent_min.x, parent_max.x - wing_min_x)
                z_penetration = min(wing_max_z - parent_min.z, parent_max.z - wing_min_z)

                # Suggest moving the wing outward (in X or Z direction)
                # Choose the direction with less penetration
                if x_penetration < z_penetration:
                    # Move in X direction
                    if wing_position.x < (parent_min.x + parent_max.x) / 2:
                        # Wing is on the left, move further left
                        adjustment = Vector(-x_penetration - 1.0, 0, 0)
                    else:
                        # Wing is on the right, move further right
                        adjustment = Vector(x_penetration + 1.0, 0, 0)
                else:
                    # Move in Z direction
                    if wing_position.z < (parent_min.z + parent_max.z) / 2:
                        adjustment = Vector(0, 0, -z_penetration - 1.0)
                    else:
                        adjustment = Vector(0, 0, z_penetration + 1.0)

                return {
                    "collides": True,
                    "message": f"Wing would intersect with model (X overlap: {x_overlap}, Z overlap: {z_overlap})",
                    "suggested_adjustment": adjustment
                }

            return {"collides": False, "message": "", "suggested_adjustment": None}

        except Exception as e:
            Logger.log("e", f"Error checking wing collision: {e}")
            return {"collides": False, "message": "", "suggested_adjustment": None}

    def _createAttachedWing(self, parent: CuraSceneNode, position: Vector):
        """Create an attached stability wing at the clicked position.

        The wing extends from the click position either:
        - Down to the build plate (to_buildplate mode)
        - Horizontally outward (horizontal mode)
        """
        try:
            Logger.log("d", f"Creating attached wing at position: {position}")

            # Calculate wing dimensions based on direction mode
            click_z = position.y  # In Cura, Y is the vertical axis in world coords
            # But Vector uses y for the vertical, and the picked position z-component is height

            # Get the Z height of the clicked position
            # Note: Cura's coordinate system has Z as vertical
            wing_top_z = position.z if hasattr(position, 'z') else position.y

            # For simplicity, let's get the actual height from the position
            # The picked_position from PickingPass returns world coordinates
            actual_z = position.y  # In the PickingPass result, y is typically height

            Logger.log("d", f"Click position Y (height): {actual_z}")

            if self._wing_direction == self.WING_DIRECTION_TO_BUILDPLATE:
                # Wing extends from click position down to build plate (Z=0)
                wing_height = max(actual_z, 1.0)  # At least 1mm tall
                # Position the wing so its top is at the click point
                wing_center_z = actual_z - (wing_height / 2)
            else:
                # Horizontal wing - fixed height, extends outward
                wing_height = self._wing_width  # Use width setting for horizontal extent
                wing_center_z = actual_z

            # Create the wing mesh (with optional break-line)
            wing_mesh = self._createWingMesh(
                width=self._wing_width,
                thickness=self._wing_thickness,
                height=wing_height,
                breakline_enable=self._wing_breakline_enable,
                breakline_depth=self._wing_breakline_depth,
                breakline_position=self._wing_breakline_position
            )

            # Create scene node
            node = CuraSceneNode()
            wing_name = "Stability Wing"
            if self._wing_breakline_enable:
                wing_name += " (with break-line)"
            node.setName(wing_name)
            node.setSelectable(True)
            node.setCalculateBoundingBox(True)
            node.setMeshData(wing_mesh.build())
            node.calculateBoundingBoxMesh()

            # Add decorators
            active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
            node.addDecorator(BuildPlateDecorator(active_build_plate))
            node.addDecorator(SliceableObjectDecorator())

            # Calculate wing position
            # The wing should be positioned at the click point
            if self._wing_direction == self.WING_DIRECTION_TO_BUILDPLATE:
                # Center the wing vertically between click point and build plate
                wing_position = Vector(
                    position.x,
                    wing_height / 2,  # Center the wing vertically
                    position.z if hasattr(position, 'z') else 0
                )
            else:
                # Horizontal mode - position at click point
                wing_position = position

            Logger.log("d", f"Initial wing position: {wing_position}, height: {wing_height}")

            # Check for collision with parent model
            collision_result = self._checkWingCollision(
                parent, wing_position,
                self._wing_width, self._wing_thickness, wing_height
            )

            if collision_result["collides"]:
                Logger.log("w", f"Wing collision detected: {collision_result['message']}")

                if collision_result["suggested_adjustment"]:
                    # Auto-adjust position to avoid collision
                    adjustment = collision_result["suggested_adjustment"]
                    wing_position = Vector(
                        wing_position.x + adjustment.x,
                        wing_position.y + adjustment.y,
                        wing_position.z + adjustment.z
                    )
                    Logger.log("i", f"Adjusted wing position to: {wing_position}")

                    # Verify the adjustment resolved the collision
                    recheck = self._checkWingCollision(
                        parent, wing_position,
                        self._wing_width, self._wing_thickness, wing_height
                    )
                    if recheck["collides"]:
                        Logger.log("w", "Wing still collides after adjustment - placing anyway")
                        node.setName("Stability Wing (collision)")
                    else:
                        node.setName("Stability Wing (adjusted)")
                else:
                    Logger.log("w", "No adjustment suggested - placing wing anyway")
                    node.setName("Stability Wing (collision)")

            Logger.log("d", f"Final wing position: {wing_position}")

            # Add to scene
            op = GroupedOperation()
            op.addOperation(AddSceneNodeOperation(node, self._controller.getScene().getRoot()))
            op.addOperation(SetParentOperation(node, parent))
            op.addOperation(TranslateOperation(node, wing_position, set_position=True))

            # Apply rotation if specified
            if abs(self._wing_rotation) > 0.1:
                # Create rotation quaternion around Y axis (vertical)
                rotation_radians = math.radians(self._wing_rotation)
                rotation_quaternion = Quaternion.fromAngleAxis(rotation_radians, Vector(0, 1, 0))
                op.addOperation(RotateOperation(node, rotation_quaternion))
                Logger.log("d", f"Applied rotation of {self._wing_rotation} degrees")

            op.push()

            CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

            Logger.log("i", f"Attached wing created successfully (mode: {self._wing_direction}, rotation: {self._wing_rotation}°)")

        except Exception as e:
            Logger.log("e", f"Error creating attached wing: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())

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

    # =====================================================================
    # Overhang Detection Properties and Methods
    # =====================================================================

    def getOverhangThreshold(self) -> float:
        return self._overhang_threshold

    def setOverhangThreshold(self, value: float) -> None:
        if value != self._overhang_threshold:
            self._overhang_threshold = float(value)
            # Clear cached detection results when threshold changes
            self._detected_overhangs = []
            self._overhang_angles = None
            self.propertyChanged.emit()
            Logger.log("d", f"Overhang threshold changed to {self._overhang_threshold}")

    OverhangThreshold = pyqtProperty(float, fget=getOverhangThreshold, fset=setOverhangThreshold)

    def getDetectedOverhangCount(self) -> int:
        return len(self._detected_overhangs)

    DetectedOverhangCount = pyqtProperty(int, fget=getDetectedOverhangCount)

    def _compute_face_normals(self, vertices: numpy.ndarray, indices: numpy.ndarray) -> numpy.ndarray:
        """Calculate face normals from vertices and indices.

        Args:
            vertices: Nx3 array of vertex positions
            indices: Mx3 array of face indices

        Returns:
            Mx3 array of unit face normals
        """
        # Get triangle vertices
        v0 = vertices[indices[:, 0]]
        v1 = vertices[indices[:, 1]]
        v2 = vertices[indices[:, 2]]

        # Compute normals via cross product
        edge1 = v1 - v0
        edge2 = v2 - v0
        normals = numpy.cross(edge1, edge2)

        # Normalize
        lengths = numpy.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / numpy.maximum(lengths, 1e-10)

        return normals

    def _build_face_adjacency_graph(self, indices: numpy.ndarray) -> Dict[int, List[int]]:
        """Build adjacency list for mesh faces.

        Two faces are adjacent if they share an edge.

        Args:
            indices: Mx3 array of face indices

        Returns:
            Dictionary mapping face_id to list of adjacent face_ids
        """
        face_count = len(indices)

        # Create edge-to-face mapping
        edge_to_faces: Dict[Tuple[int, int], List[int]] = {}
        for face_id, face in enumerate(indices):
            for i in range(3):
                # Create edge key (sorted for consistency)
                edge = tuple(sorted([int(face[i]), int(face[(i + 1) % 3])]))
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(face_id)

        # Build adjacency list
        adjacency: Dict[int, List[int]] = {i: [] for i in range(face_count)}
        for edge, faces in edge_to_faces.items():
            if len(faces) == 2:  # Interior edge (shared by exactly 2 faces)
                adjacency[faces[0]].append(faces[1])
                adjacency[faces[1]].append(faces[0])

        return adjacency

    def _detect_overhangs(self, node: CuraSceneNode, threshold_angle: Optional[float] = None) -> Tuple[numpy.ndarray, numpy.ndarray]:
        """Detect overhang faces using normal vector analysis.

        Args:
            node: The CuraSceneNode to analyze
            threshold_angle: Overhang threshold in degrees (default: use self._overhang_threshold)

        Returns:
            Tuple of (overhang_face_ids, angles) where:
            - overhang_face_ids: array of face indices that are overhangs
            - angles: array of angles for all faces
        """
        if threshold_angle is None:
            threshold_angle = self._overhang_threshold

        mesh_data = node.getMeshData()
        if not mesh_data:
            Logger.log("w", "Node has no mesh data")
            return numpy.array([]), numpy.array([])

        # Get transformed mesh data
        transformed_mesh = mesh_data.getTransformed(node.getWorldTransformation())

        vertices = transformed_mesh.getVertices()
        if vertices is None or len(vertices) == 0:
            Logger.log("w", "Mesh has no vertices")
            return numpy.array([]), numpy.array([])

        if transformed_mesh.hasIndices():
            indices = transformed_mesh.getIndices()
        else:
            # Create indices if not present (each 3 vertices = 1 face)
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        # Compute face normals
        face_normals = self._compute_face_normals(vertices, indices)

        # Build direction (downward in Cura's coordinate system: -Y)
        # In Cura, Y is the vertical axis
        build_direction = numpy.array([[0., -1., 0.]])

        # Compute angles for all faces
        # The dot product gives cos(angle) where angle is between normal and build direction
        dot_products = numpy.dot(face_normals, build_direction.T).flatten()

        # Clamp dot products to valid range for arccos
        dot_products = numpy.clip(dot_products, -1.0, 1.0)

        # Convert to angles in degrees
        # We want the angle from the downward direction
        angles = numpy.degrees(numpy.arccos(dot_products))

        # Faces pointing downward (normal pointing down) have small angles
        # Overhangs are faces that face downward beyond the threshold
        # A face with normal pointing straight down has angle = 0
        # A horizontal face has angle = 90
        # A face pointing up has angle = 180

        # For overhang detection, we want faces with normals pointing down
        # (i.e., the undersides of geometry)
        # These are faces where the angle to the down vector is small
        overhang_mask = angles < (90 - threshold_angle)

        overhang_face_ids = numpy.where(overhang_mask)[0]

        Logger.log("d", f"Detected {len(overhang_face_ids)} overhang faces "
                      f"out of {len(angles)} total faces (threshold: {threshold_angle}°)")

        return overhang_face_ids, angles

    def _find_connected_overhang_region(self, seed_face_id: int, overhang_mask: numpy.ndarray,
                                         adjacency: Dict[int, List[int]]) -> List[int]:
        """BFS to find connected overhang region from seed face.

        Args:
            seed_face_id: The starting face index
            overhang_mask: Boolean array indicating which faces are overhangs
            adjacency: Face adjacency graph

        Returns:
            List of face indices in the connected overhang region
        """
        if seed_face_id >= len(overhang_mask) or not overhang_mask[seed_face_id]:
            return []

        visited: Set[int] = set()
        queue = deque([seed_face_id])
        region: List[int] = []

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

    def _get_region_vertices(self, region_face_ids: List[int], vertices: numpy.ndarray,
                              indices: numpy.ndarray) -> numpy.ndarray:
        """Extract vertices belonging to faces in a region.

        Args:
            region_face_ids: List of face indices in the region
            vertices: Nx3 array of all vertex positions
            indices: Mx3 array of all face indices

        Returns:
            Array of unique vertex positions in the region
        """
        if not region_face_ids:
            return numpy.array([])

        # Get all vertex indices for faces in the region
        region_indices = indices[region_face_ids].flatten()
        unique_vertex_ids = numpy.unique(region_indices)

        return vertices[unique_vertex_ids]

    def _classify_overhang_type(self, region_vertices: numpy.ndarray,
                                 all_overhang_vertices: numpy.ndarray) -> str:
        """Classify an overhang region as 'tip' or 'boundary'.

        The tip is the lowest point of the overhang (needs structural support).
        Boundary regions are the sides (need stability support only).

        Args:
            region_vertices: Vertices of this region
            all_overhang_vertices: Vertices of all overhang regions combined

        Returns:
            'tip' or 'boundary'
        """
        if len(region_vertices) == 0:
            return "boundary"

        # Find the lowest point in this region (minimum Y in Cura)
        region_min_y = numpy.min(region_vertices[:, 1])

        # Find the lowest point across all overhangs
        global_min_y = numpy.min(all_overhang_vertices[:, 1])

        # If this region contains the lowest point (within tolerance), it's a tip
        tolerance = 0.5  # mm
        if abs(region_min_y - global_min_y) < tolerance:
            return "tip"
        else:
            return "boundary"

    def detectOverhangsOnSelection(self):
        """Detect overhangs on the currently selected model.

        This method analyzes the selected model and populates self._detected_overhangs
        with information about each overhang region.
        """
        selected_node = Selection.getSelectedObject(0)
        if not selected_node:
            Logger.log("w", "No object selected for overhang detection")
            return

        Logger.log("i", f"Detecting overhangs on: {selected_node.getName()}")

        # Get mesh data
        mesh_data = selected_node.getMeshData()
        if not mesh_data:
            Logger.log("w", "Selected node has no mesh data")
            return

        transformed_mesh = mesh_data.getTransformed(selected_node.getWorldTransformation())
        vertices = transformed_mesh.getVertices()

        if transformed_mesh.hasIndices():
            indices = transformed_mesh.getIndices()
        else:
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        # Detect all overhang faces
        overhang_face_ids, angles = self._detect_overhangs(selected_node)
        self._overhang_angles = angles

        if len(overhang_face_ids) == 0:
            Logger.log("i", "No overhangs detected")
            self._detected_overhangs = []
            self.propertyChanged.emit()
            return

        # Build face adjacency graph
        self._overhang_adjacency = self._build_face_adjacency_graph(indices)

        # Create overhang mask
        overhang_mask = numpy.zeros(len(angles), dtype=bool)
        overhang_mask[overhang_face_ids] = True

        # Find connected regions using BFS
        visited_faces: Set[int] = set()
        regions: List[Dict] = []

        for face_id in overhang_face_ids:
            if face_id in visited_faces:
                continue

            region_faces = self._find_connected_overhang_region(
                face_id, overhang_mask, self._overhang_adjacency
            )

            if region_faces:
                visited_faces.update(region_faces)
                region_vertices = self._get_region_vertices(region_faces, vertices, indices)

                # Calculate region statistics
                region_info = {
                    "face_ids": region_faces,
                    "face_count": len(region_faces),
                    "vertices": region_vertices,
                    "min_y": float(numpy.min(region_vertices[:, 1])) if len(region_vertices) > 0 else 0,
                    "max_angle": float(numpy.max(angles[region_faces])),
                    "avg_angle": float(numpy.mean(angles[region_faces])),
                    "center": numpy.mean(region_vertices, axis=0) if len(region_vertices) > 0 else numpy.zeros(3),
                }
                regions.append(region_info)

        # Get all overhang vertices for tip classification
        all_overhang_face_ids = []
        for r in regions:
            all_overhang_face_ids.extend(r["face_ids"])
        all_overhang_vertices = self._get_region_vertices(all_overhang_face_ids, vertices, indices)

        # Classify each region as tip or boundary
        for region in regions:
            region["type"] = self._classify_overhang_type(region["vertices"], all_overhang_vertices)

        # Sort regions by min_y (lowest first - tips at the bottom)
        regions.sort(key=lambda r: r["min_y"])

        self._detected_overhangs = regions
        self.propertyChanged.emit()

        # Log summary
        tip_count = sum(1 for r in regions if r["type"] == "tip")
        boundary_count = sum(1 for r in regions if r["type"] == "boundary")
        Logger.log("i", f"Detected {len(regions)} overhang regions: "
                      f"{tip_count} tips, {boundary_count} boundaries")

        for i, region in enumerate(regions):
            Logger.log("d", f"  Region {i}: {region['face_count']} faces, "
                          f"type={region['type']}, min_y={region['min_y']:.2f}mm, "
                          f"avg_angle={region['avg_angle']:.1f}°")

    def createSupportForOverhangs(self):
        """Create support volumes for detected overhang regions.

        Uses structural support for tips and stability support for boundaries.
        """
        selected_node = Selection.getSelectedObject(0)
        if not selected_node:
            Logger.log("w", "No object selected")
            return

        if not self._detected_overhangs:
            Logger.log("w", "No overhangs detected. Run detection first.")
            return

        Logger.log("i", f"Creating support for {len(self._detected_overhangs)} overhang regions")

        for i, region in enumerate(self._detected_overhangs):
            # Determine support mode based on region type
            if region["type"] == "tip":
                self._support_mode = self.SUPPORT_MODE_STRUCTURAL
                Logger.log("d", f"Region {i}: Creating structural support (tip)")
            else:
                self._support_mode = self.SUPPORT_MODE_STABILITY
                Logger.log("d", f"Region {i}: Creating stability support (boundary)")

            # Apply the mode settings
            self.setSupportMode(self._support_mode)

            # Calculate bounding box of the region for volume placement
            region_vertices = region["vertices"]
            if len(region_vertices) == 0:
                continue

            min_coords = numpy.min(region_vertices, axis=0)
            max_coords = numpy.max(region_vertices, axis=0)
            center = (min_coords + max_coords) / 2

            # Calculate appropriate cube size to cover the region
            size = max_coords - min_coords
            padding = 2.0  # mm padding around the region

            self._cube_x = max(size[0] + padding, 3.0)
            self._cube_y = max(size[2] + padding, 3.0)  # Swap Y/Z for Cura coords
            self._cube_z = max(size[1] + padding, 3.0)

            # Create the modifier volume at the region center
            position = Vector(float(center[0]), float(center[1]), float(center[2]))
            self._createModifierVolume(selected_node, position)

        Logger.log("i", "Support creation complete")

    # =====================================================================
    # Phase 3: Custom Support Mesh Generation
    # =====================================================================

    # Custom support mesh settings
    SUPPORT_MESH_EDGE_RAIL = "edge_rail"
    SUPPORT_MESH_TIP_COLUMN = "tip_column"

    def _find_boundary_edges(self, region_face_ids: List[int], overhang_mask: numpy.ndarray,
                              adjacency: Dict[int, List[int]], indices: numpy.ndarray,
                              vertices: numpy.ndarray) -> List[Tuple[numpy.ndarray, numpy.ndarray]]:
        """Find edges between overhang and non-overhang faces.

        These are the "boundary edges" where the overhang region meets the rest of the model.

        Args:
            region_face_ids: List of face indices in the overhang region
            overhang_mask: Boolean array indicating which faces are overhangs
            adjacency: Face adjacency graph
            indices: Mx3 array of all face indices
            vertices: Nx3 array of all vertex positions

        Returns:
            List of edge tuples, where each edge is (vertex1, vertex2) as numpy arrays
        """
        boundary_edges = []
        region_set = set(region_face_ids)

        for face_id in region_face_ids:
            face = indices[face_id]

            for neighbor_id in adjacency.get(face_id, []):
                if neighbor_id not in region_set and not overhang_mask[neighbor_id]:
                    # This neighbor is not an overhang - find the shared edge
                    neighbor_face = indices[neighbor_id]

                    # Find shared vertices between the two faces
                    shared_verts = set(face) & set(neighbor_face)
                    if len(shared_verts) == 2:
                        v_ids = list(shared_verts)
                        edge = (vertices[v_ids[0]].copy(), vertices[v_ids[1]].copy())
                        boundary_edges.append(edge)

        Logger.log("d", f"Found {len(boundary_edges)} boundary edges")
        return boundary_edges

    def _create_edge_rail_mesh(self, edge_start: numpy.ndarray, edge_end: numpy.ndarray,
                                rail_width: float = 0.8, rail_height: float = 2.0,
                                extend_to_plate: bool = True) -> MeshBuilder:
        """Create a thin rail mesh along an edge.

        The rail extends perpendicular to the edge and downward.

        Args:
            edge_start: Start vertex of the edge (numpy array [x, y, z])
            edge_end: End vertex of the edge (numpy array [x, y, z])
            rail_width: Width of the rail in mm (perpendicular to edge)
            rail_height: Height of the rail below the edge (if not extending to plate)
            extend_to_plate: If True, extend rail down to Z=0

        Returns:
            MeshBuilder with the rail geometry
        """
        mesh = MeshBuilder()

        # Calculate edge direction and length
        edge_vec = edge_end - edge_start
        edge_length = numpy.linalg.norm(edge_vec)

        if edge_length < 0.1:
            return mesh  # Edge too short

        edge_dir = edge_vec / edge_length

        # Calculate perpendicular direction (horizontal, away from edge)
        # Cross with up vector to get horizontal perpendicular
        up = numpy.array([0.0, 1.0, 0.0])
        perp_dir = numpy.cross(edge_dir, up)
        perp_length = numpy.linalg.norm(perp_dir)

        if perp_length < 0.01:
            # Edge is vertical, use a different approach
            perp_dir = numpy.array([1.0, 0.0, 0.0])
        else:
            perp_dir = perp_dir / perp_length

        # Determine rail height
        edge_min_y = min(edge_start[1], edge_end[1])
        if extend_to_plate and edge_min_y > 0:
            actual_height = edge_min_y + 0.5  # Extend slightly into build plate
        else:
            actual_height = rail_height

        # Rail half-dimensions
        half_width = rail_width / 2
        half_length = edge_length / 2

        # Center of the rail
        edge_center = (edge_start + edge_end) / 2
        rail_center = edge_center.copy()
        rail_center[1] -= actual_height / 2  # Move center down

        # Build vertices for the rail box
        # The rail is oriented along the edge direction
        verts = []

        # 8 corners of the rail box
        for dy in [-actual_height / 2, actual_height / 2]:  # Bottom, Top
            for dw in [-half_width, half_width]:  # Perpendicular direction
                for dl in [-half_length, half_length]:  # Along edge direction
                    vert = rail_center.copy()
                    vert[1] += dy
                    vert += perp_dir * dw
                    vert += edge_dir * dl
                    # Convert to Cura coordinate format [x, z, y]
                    verts.append([vert[0], vert[1], vert[2]])

        # Create faces (12 triangles for 6 faces)
        # Vertex order: 0-3 bottom, 4-7 top
        # 0: -w,-l  1: +w,-l  2: -w,+l  3: +w,+l (bottom)
        # 4: -w,-l  5: +w,-l  6: -w,+l  7: +w,+l (top)

        face_indices = [
            # Bottom face
            [0, 1, 3], [0, 3, 2],
            # Top face
            [4, 7, 5], [4, 6, 7],
            # Front face (-l)
            [0, 4, 5], [0, 5, 1],
            # Back face (+l)
            [2, 3, 7], [2, 7, 6],
            # Left face (-w)
            [0, 2, 6], [0, 6, 4],
            # Right face (+w)
            [1, 5, 7], [1, 7, 3],
        ]

        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))
        mesh.setIndices(numpy.asarray(face_indices, dtype=numpy.int32))
        mesh.calculateNormals()

        return mesh

    def _create_tip_column_mesh(self, tip_position: numpy.ndarray,
                                 column_radius: float = 2.0,
                                 sides: int = 8,
                                 taper: float = 0.7) -> MeshBuilder:
        """Create a support column from the tip down to the build plate.

        Args:
            tip_position: Position of the tip (numpy array [x, y, z])
            column_radius: Radius of the column at the base
            sides: Number of sides for the column (polygon approximation)
            taper: Taper factor (0.5 = 50% smaller at top than bottom)

        Returns:
            MeshBuilder with the column geometry
        """
        mesh = MeshBuilder()

        tip_y = tip_position[1]
        if tip_y <= 0:
            Logger.log("w", "Tip is at or below build plate, cannot create column")
            return mesh

        # Column parameters
        base_y = 0.0
        height = tip_y
        top_radius = column_radius * taper
        base_radius = column_radius

        # Generate vertices
        verts = []
        indices = []

        # Bottom center
        verts.append([tip_position[0], base_y, tip_position[2]])
        bottom_center_idx = 0

        # Top center
        verts.append([tip_position[0], tip_y, tip_position[2]])
        top_center_idx = 1

        # Bottom ring vertices
        bottom_start_idx = 2
        for i in range(sides):
            angle = 2 * math.pi * i / sides
            x = tip_position[0] + base_radius * math.cos(angle)
            z = tip_position[2] + base_radius * math.sin(angle)
            verts.append([x, base_y, z])

        # Top ring vertices
        top_start_idx = bottom_start_idx + sides
        for i in range(sides):
            angle = 2 * math.pi * i / sides
            x = tip_position[0] + top_radius * math.cos(angle)
            z = tip_position[2] + top_radius * math.sin(angle)
            verts.append([x, tip_y, z])

        # Bottom cap faces (fan from center)
        for i in range(sides):
            next_i = (i + 1) % sides
            indices.append([bottom_center_idx,
                           bottom_start_idx + next_i,
                           bottom_start_idx + i])

        # Top cap faces (fan from center)
        for i in range(sides):
            next_i = (i + 1) % sides
            indices.append([top_center_idx,
                           top_start_idx + i,
                           top_start_idx + next_i])

        # Side faces (quads as two triangles)
        for i in range(sides):
            next_i = (i + 1) % sides
            b1 = bottom_start_idx + i
            b2 = bottom_start_idx + next_i
            t1 = top_start_idx + i
            t2 = top_start_idx + next_i

            # Two triangles per quad
            indices.append([b1, t1, b2])
            indices.append([b2, t1, t2])

        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))
        mesh.calculateNormals()

        return mesh

    def _create_support_mesh_node(self, mesh_builder: MeshBuilder, name: str,
                                   parent: CuraSceneNode) -> Optional[CuraSceneNode]:
        """Create a scene node with the support_mesh property set.

        Args:
            mesh_builder: The MeshBuilder containing the geometry
            name: Name for the node
            parent: Parent node to attach to

        Returns:
            The created CuraSceneNode, or None if creation failed
        """
        try:
            mesh_data = mesh_builder.build()
            if mesh_data is None or mesh_data.getVertexCount() == 0:
                Logger.log("w", f"Cannot create support mesh '{name}': empty mesh")
                return None

            node = CuraSceneNode()
            node.setName(name)
            node.setSelectable(True)
            node.setCalculateBoundingBox(True)
            node.setMeshData(mesh_data)
            node.calculateBoundingBoxMesh()

            # Add decorators
            active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
            node.addDecorator(BuildPlateDecorator(active_build_plate))
            node.addDecorator(SliceableObjectDecorator())

            # Set as support_mesh type
            if not self.setMeshType(node, "support_mesh"):
                Logger.log("w", f"Failed to set support_mesh type for '{name}'")

            # Add to scene
            op = GroupedOperation()
            op.addOperation(AddSceneNodeOperation(node, self._controller.getScene().getRoot()))
            op.addOperation(SetParentOperation(node, parent))
            op.push()

            CuraApplication.getInstance().getController().getScene().sceneChanged.emit(node)

            Logger.log("i", f"Created support mesh: {name}")
            return node

        except Exception as e:
            Logger.log("e", f"Error creating support mesh '{name}': {e}")
            import traceback
            Logger.log("e", traceback.format_exc())
            return None

    def createCustomSupportMesh(self, support_type: str = "auto"):
        """Create custom support mesh geometry for detected overhangs.

        Args:
            support_type: Type of support to create:
                - "auto": Create edge rails for boundaries, columns for tips
                - "edge_rail": Only create edge rails
                - "tip_column": Only create tip columns
        """
        selected_node = Selection.getSelectedObject(0)
        if not selected_node:
            Logger.log("w", "No object selected")
            return

        if not self._detected_overhangs:
            Logger.log("w", "No overhangs detected. Run detection first.")
            return

        # Get mesh data for boundary edge detection
        mesh_data = selected_node.getMeshData()
        if not mesh_data:
            return

        transformed_mesh = mesh_data.getTransformed(selected_node.getWorldTransformation())
        vertices = transformed_mesh.getVertices()

        if transformed_mesh.hasIndices():
            indices = transformed_mesh.getIndices()
        else:
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        # Create overhang mask
        overhang_mask = numpy.zeros(len(self._overhang_angles), dtype=bool)
        for region in self._detected_overhangs:
            for face_id in region["face_ids"]:
                if face_id < len(overhang_mask):
                    overhang_mask[face_id] = True

        Logger.log("i", f"Creating custom support meshes (type: {support_type})")

        rails_created = 0
        columns_created = 0

        for i, region in enumerate(self._detected_overhangs):
            region_type = region["type"]

            # Create tip column for tip regions
            if region_type == "tip" and support_type in ["auto", "tip_column"]:
                # Find the lowest point in the region
                region_vertices = region["vertices"]
                if len(region_vertices) > 0:
                    min_y_idx = numpy.argmin(region_vertices[:, 1])
                    tip_pos = region_vertices[min_y_idx]

                    column_mesh = self._create_tip_column_mesh(
                        tip_pos,
                        column_radius=2.0,
                        sides=8,
                        taper=0.6
                    )

                    if column_mesh.getVertexCount() > 0:
                        self._create_support_mesh_node(
                            column_mesh,
                            f"Tip Support Column {i}",
                            selected_node
                        )
                        columns_created += 1

            # Create edge rails for boundary regions
            if region_type == "boundary" and support_type in ["auto", "edge_rail"]:
                boundary_edges = self._find_boundary_edges(
                    region["face_ids"],
                    overhang_mask,
                    self._overhang_adjacency,
                    indices,
                    vertices
                )

                # Merge nearby edges and create rails
                for j, (edge_start, edge_end) in enumerate(boundary_edges):
                    rail_mesh = self._create_edge_rail_mesh(
                        edge_start,
                        edge_end,
                        rail_width=0.8,
                        rail_height=3.0,
                        extend_to_plate=True
                    )

                    if rail_mesh.getVertexCount() > 0:
                        self._create_support_mesh_node(
                            rail_mesh,
                            f"Edge Rail {i}-{j}",
                            selected_node
                        )
                        rails_created += 1

        Logger.log("i", f"Custom support creation complete: "
                      f"{columns_created} columns, {rails_created} rails")
