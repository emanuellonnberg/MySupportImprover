# Cura is released under the terms of the LGPLv3 or higher.
import os
import sys
import json
from PyQt6.QtCore import Qt, QTimer, pyqtProperty
from PyQt6.QtWidgets import QApplication, QProgressDialog
from UM.Resources import Resources
from UM.Logger import Logger
from UM.Application import Application
from UM.Math.Vector import Vector
from UM.Operations.TranslateOperation import TranslateOperation
from UM.Operations.RotateOperation import RotateOperation
from UM.Math.Quaternion import Quaternion
import math
import re
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

from . import geometry_utils

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
        self._mesh_cache = {}  # Cached mesh data per node

        # Custom support mesh settings (Phase 4)
        self._column_radius = 2.0  # mm - radius of tip support columns
        self._column_taper = 0.6  # taper factor (0.6 = 60% of base radius at top)
        self._column_sides = 8  # number of sides for column polygon
        self._rail_width = 0.8  # mm - width of edge rails
        self._rail_min_length = 2.0  # mm - minimum edge length to create rail
        self._merge_edge_distance = 1.0  # mm - merge edges closer than this

        # Wing-specific settings
        self._wing_direction = self.WING_DIRECTION_TO_BUILDPLATE
        self._wing_thickness = 1.5  # mm - thickness of the wing
        self._wing_width = 5.0  # mm - width of the wing (perpendicular to edge)
        self._wing_angle = 0.0  # degrees - angle from vertical (0 = straight down)
        self._wing_breakline_enable = True  # Enable break-line for easy removal
        self._wing_breakline_depth = 0.5  # mm - how deep the break-line notch is
        self._wing_breakline_position = 2.0  # mm - distance from top of wing
        self._wing_rotation = 0.0  # degrees - rotation around vertical axis

        # Export/auto-detect settings
        self._export_mode = False  # Export mesh data mode
        self._auto_detect = False  # Automatic overhang detection mode (all regions)
        self._single_region = False  # Single region mode (fast, one region only)
        self._detect_sharp_features = False  # Sharp feature detection mode (for pointy things)
        self._detect_dangling_vertices = False  # Vertex-based dangling detection mode

        self.setExposedProperties(
            "CubeX", "CubeY", "CubeZ", "ShowSettings", "CanModify", "Presets",
            "SupportAngle", "CurrentPreset", "IsCustom",
            "ExportMode", "AutoDetect", "SingleRegion", "DetectSharpFeatures", "DetectDanglingVertices",
            # Support mode properties
            "SupportMode", "SupportModes", "SupportPattern", "SupportInfillRate",
            "SupportLineWidth", "SupportWallCount", "SupportInterfaceEnable",
            "SupportRoofEnable", "SupportBottomEnable", "SupportModeDescription",
            # Wing properties
            "WingDirection", "WingThickness", "WingWidth", "WingAngle",
            "WingBreaklineEnable", "WingBreaklineDepth", "WingBreaklinePosition",
            "WingRotation",
            # Overhang detection properties
            "OverhangThreshold", "DetectedOverhangCount",
            # Custom support mesh properties (Phase 4)
            "ColumnRadius", "ColumnTaper", "RailWidth"
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
        self._progress_dialog = None

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

    SupportBottomEnable = pyqtProperty(bool, fget=getSupportBottomEnable, fset=setSupportBottomEnable)

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
                Logger.log("i", "Auto-detect mode ENABLED - click to detect all overhang regions")
                # Disable single region mode
                if self._single_region:
                    self._single_region = False
            else:
                Logger.log("i", "Auto-detect mode DISABLED")
            self.propertyChanged.emit()

    AutoDetect = pyqtProperty(bool, fget=getAutoDetect, fset=setAutoDetect)

    def getSingleRegion(self) -> bool:
        return self._single_region

    def setSingleRegion(self, value: bool) -> None:
        if value != self._single_region:
            self._single_region = value
            if value:
                Logger.log("i", "Single region mode ENABLED - click to detect one overhang region (fast)")
                # Disable auto-detect mode
                if self._auto_detect:
                    self._auto_detect = False
            else:
                Logger.log("i", "Single region mode DISABLED")
            self.propertyChanged.emit()

    SingleRegion = pyqtProperty(bool, fget=getSingleRegion, fset=setSingleRegion)

    def getDetectSharpFeatures(self) -> bool:
        return self._detect_sharp_features

    def setDetectSharpFeatures(self, value: bool) -> None:
        if value != self._detect_sharp_features:
            self._detect_sharp_features = value
            if value:
                Logger.log("i", "Sharp feature detection ENABLED - will detect pointy features that need support")
            else:
                Logger.log("i", "Sharp feature detection DISABLED")
            self.propertyChanged.emit()

    DetectSharpFeatures = pyqtProperty(bool, fget=getDetectSharpFeatures, fset=setDetectSharpFeatures)

    def getDetectDanglingVertices(self) -> bool:
        return self._detect_dangling_vertices

    def setDetectDanglingVertices(self, value: bool) -> None:
        if value != self._detect_dangling_vertices:
            self._detect_dangling_vertices = value
            if value:
                Logger.log("i", "Dangling vertex detection ENABLED - will filter to vertex-local minima")
            else:
                Logger.log("i", "Dangling vertex detection DISABLED")
            self.propertyChanged.emit()

    DetectDanglingVertices = pyqtProperty(bool, fget=getDetectDanglingVertices, fset=setDetectDanglingVertices)

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
            Logger.log("i", "Click mode: export=%s, auto=%s, single=%s", str(self._export_mode), str(self._auto_detect), str(self._single_region))

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

            # SINGLE REGION MODE: Fast detection of one overhang region under click
            if self._single_region:
                Logger.log("i", "Single region mode active - detecting one overhang region (fast)")

                # Get the clicked position in 3D space
                active_camera = self._controller.getScene().getActiveCamera()
                picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
                picking_pass.render()
                picked_position = picking_pass.getPickedPosition(event.x, event.y)

                self._detectSingleRegion(picked_node, picked_position)
                return

            # AUTO-DETECT MODE: Automatically detect all overhang regions
            if self._auto_detect:
                Logger.log("i", "Auto-detect mode active - detecting all overhang regions")

                # Get the clicked position in 3D space (optional - for validation)
                active_camera = self._controller.getScene().getActiveCamera()
                picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
                picking_pass.render()
                picked_position = picking_pass.getPickedPosition(event.x, event.y)

                self._autoDetectOverhangs(picked_node, None)  # None = detect all regions
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
        """Create a modifier volume using the default cube dimensions from properties"""
        self._createModifierVolumeWithSize(parent, position, self._cube_x, self._cube_y, self._cube_z)

    def _createModifierVolumeWithSize(self, parent: CuraSceneNode, position: Vector, size_x: float, size_y: float, size_z: float, rotation_matrix: Optional[numpy.ndarray] = None):
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

            Logger.log("d", f"Creating cube with dimensions: X={size_x}, Y={size_y}, Z={size_z}")

            # Create cube with the specified dimensions
            mesh = self._createCube(size_x, size_y, size_z)
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
            if rotation_matrix is not None:
                q = Quaternion(rotation_matrix)
                op.addOperation(RotateOperation(node, q))
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

        verts = [ # 6 faces with 4 corners each: [x, y, z] format
            [-s_x,  s_y, -s_z], [-s_x,  s_y,  s_z], [ s_x,  s_y,  s_z], [ s_x,  s_y, -s_z],  # top
            [-s_x, -s_y, -s_z], [-s_x, -s_y,  s_z], [ s_x, -s_y,  s_z], [ s_x, -s_y, -s_z],  # bottom
            [-s_x, -s_y, -s_z], [-s_x,  s_y, -s_z], [ s_x,  s_y, -s_z], [ s_x, -s_y, -s_z],  # back
            [-s_x, -s_y,  s_z], [-s_x,  s_y,  s_z], [ s_x,  s_y,  s_z], [ s_x, -s_y,  s_z],  # front
            [-s_x, -s_y, -s_z], [-s_x, -s_y,  s_z], [-s_x,  s_y,  s_z], [-s_x,  s_y, -s_z],  # left
            [ s_x, -s_y, -s_z], [ s_x, -s_y,  s_z], [ s_x,  s_y,  s_z], [ s_x,  s_y, -s_z]   # right
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

            Logger.log("i", f"Attached wing created successfully (mode: {self._wing_direction}, rotation: {self._wing_rotation}Â°)")

        except Exception as e:
            Logger.log("e", f"Error creating attached wing: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())


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
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", node.getName()).strip("._")
            if not safe_name:
                safe_name = "model"
            base_filename = f"mesh_{safe_name}_{timestamp}"

            # Export to STL (binary format)
            stl_path = os.path.join(output_dir, f"{base_filename}.stl")
            self._exportToSTL(mesh_data, stl_path)
            Logger.log("i", f"Exported STL to: {stl_path}")

            # Export to JSON (detailed data)
            json_path = os.path.join(output_dir, f"{base_filename}.json")
            self._exportToJSON(mesh_data, node, json_path, picked_position)
            Logger.log("i", f"Exported JSON to: {json_path}")

            # Export overhang debug data
            debug_json_path = os.path.join(output_dir, f"{base_filename}_overhang_debug.json")
            debug_stl_path = os.path.join(output_dir, f"{base_filename}_overhang_faces.stl")
            self._exportOverhangDebug(mesh_data, debug_json_path, debug_stl_path, self._overhang_threshold)
            Logger.log("i", f"Exported overhang debug JSON to: {debug_json_path}")
            Logger.log("i", f"Exported overhang faces STL to: {debug_stl_path}")

            # Export current support volumes (cutting_mesh) attached to this model
            volumes_json_path = os.path.join(output_dir, f"{base_filename}_volumes.json")
            self._exportSupportVolumes(node, volumes_json_path)
            Logger.log("i", f"Exported support volumes JSON to: {volumes_json_path}")

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

    def _exportOverhangDebug(self, mesh_data, json_path, stl_path, threshold_angle: float):
        """Export overhang detection diagnostics for a mesh."""
        vertices = mesh_data.getVertices()

        if mesh_data.hasIndices():
            indices = mesh_data.getIndices()
        else:
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        # Prefer provided normals if available
        face_normals = None
        if mesh_data.hasNormals():
            normals = mesh_data.getNormals()
            if normals is not None and len(normals) > 0:
                normals = numpy.array(normals, dtype=numpy.float32)
                if len(normals) == len(vertices):
                    face_normals = self._computeFaceNormalsFromVertexNormals(normals, indices)
                elif len(normals) == len(indices):
                    face_normals = normals

        if face_normals is None:
            face_normals = self._compute_face_normals(vertices, indices)

        # Overhang detection
        overhang_face_ids = self._detectOverhangFacesFromNormals(face_normals, threshold_angle)
        overhang_set = set(int(face_id) for face_id in overhang_face_ids)

        # Apply neighbor-height filter (same as auto-detect)
        adjacency = self._buildAdjacencyGraph(indices)
        face_centers = self._computeFaceCenters(vertices, indices)
        filtered_overhang_ids = self._filterOverhangFacesByNeighborHeight(
            overhang_face_ids,
            adjacency,
            face_centers,
            min_delta_y=0.05,
            max_lower_fraction=0.5,
            min_face_y=0.2,
            obstruction_vertices=vertices,
            obstruction_indices=indices,
            min_clearance=0.0
        )
        filtered_overhang_set = set(int(face_id) for face_id in filtered_overhang_ids)

        # Angle per face (for debugging)
        build_direction = numpy.array([0.0, -1.0, 0.0])
        dot_products = numpy.dot(face_normals, build_direction)
        dot_products = numpy.clip(dot_products, -1.0, 1.0)
        angles = numpy.degrees(numpy.arccos(dot_products))

        # Per-face debug data
        faces_debug = []
        for face_id, face in enumerate(indices):
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]
            center = (v0 + v1 + v2) / 3.0

            faces_debug.append({
                "face_id": int(face_id),
                "center": [float(center[0]), float(center[1]), float(center[2])],
                "normal": [float(face_normals[face_id][0]), float(face_normals[face_id][1]), float(face_normals[face_id][2])],
                "angle_to_down": float(angles[face_id]),
                "is_overhang_raw": face_id in overhang_set,
                "is_overhang_filtered": face_id in filtered_overhang_set,
            })

        debug_payload = {
            "threshold_angle": float(threshold_angle),
            "face_count": int(len(indices)),
            "overhang_face_count_raw": int(len(overhang_face_ids)),
            "overhang_face_ids_raw": [int(face_id) for face_id in overhang_face_ids],
            "overhang_face_count_filtered": int(len(filtered_overhang_ids)),
            "overhang_face_ids_filtered": [int(face_id) for face_id in filtered_overhang_ids],
            "faces": faces_debug,
        }

        with open(json_path, 'w') as f:
            json.dump(debug_payload, f, indent=2)

        # Export only filtered overhang faces as STL for visual inspection
        self._exportFacesToSTL(vertices, indices, filtered_overhang_ids, stl_path)

    def _exportFacesToSTL(self, vertices, indices, face_ids, filepath):
        """Export selected faces to binary STL format."""
        import struct

        face_ids = list(face_ids)
        with open(filepath, 'wb') as f:
            header = b'Overhang faces exported from MySupportImprover'
            header = header.ljust(80, b'\x00')
            f.write(header)

            f.write(struct.pack("<I", int(len(face_ids))))

            for face_id in face_ids:
                face = indices[int(face_id)]
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]

                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = numpy.cross(edge1, edge2)
                normal_length = numpy.linalg.norm(normal)
                if normal_length > 1e-10:
                    normal = normal / normal_length
                else:
                    normal = numpy.array([0.0, 0.0, 1.0])

                f.write(struct.pack("<fff", float(normal[0]), float(normal[1]), float(normal[2])))
                f.write(struct.pack("<fff", float(v0[0]), float(v0[1]), float(v0[2])))
                f.write(struct.pack("<fff", float(v1[0]), float(v1[1]), float(v1[2])))
                f.write(struct.pack("<fff", float(v2[0]), float(v2[1]), float(v2[2])))
                f.write(struct.pack("<H", 0))

    def _exportSupportVolumes(self, model_node: CuraSceneNode, json_path: str) -> None:
        """Export cutting volumes attached to the selected model."""
        def collect_nodes(root):
            nodes = [root]
            if hasattr(root, "getChildren"):
                for child in root.getChildren():
                    nodes.extend(collect_nodes(child))
            return nodes

        def is_descendant(node, ancestor):
            current = node
            while current is not None:
                if current == ancestor:
                    return True
                if hasattr(current, "getParent"):
                    current = current.getParent()
                else:
                    break
            return False

        scene_root = self._controller.getScene().getRoot()
        volumes = []

        for node in collect_nodes(scene_root):
            if node == model_node:
                continue
            try:
                if self.getMeshType(node) != "cutting_mesh":
                    continue
            except Exception:
                continue

            if not is_descendant(node, model_node):
                continue

            mesh_data = node.getMeshData()
            if not mesh_data:
                continue

            transformed = mesh_data.getTransformed(node.getWorldTransformation())
            vertices = transformed.getVertices()
            if vertices is None or len(vertices) == 0:
                continue

            min_bounds = vertices.min(axis=0)
            max_bounds = vertices.max(axis=0)
            center = (min_bounds + max_bounds) / 2.0
            size = max_bounds - min_bounds

            volumes.append({
                "name": node.getName(),
                "center": [float(center[0]), float(center[1]), float(center[2])],
                "size": [float(size[0]), float(size[1]), float(size[2])],
                "min": [float(min_bounds[0]), float(min_bounds[1]), float(min_bounds[2])],
                "max": [float(max_bounds[0]), float(max_bounds[1]), float(max_bounds[2])],
            })

        payload = {
            "model_name": model_node.getName(),
            "volume_count": len(volumes),
            "volumes": volumes,
        }

        with open(json_path, 'w') as f:
            json.dump(payload, f, indent=2)

    def _collectCuttingMeshVolumes(self, model_node: CuraSceneNode) -> List[Dict[str, object]]:
        """Collect cutting mesh volumes attached to the selected model."""
        def collect_nodes(root):
            nodes = [root]
            if hasattr(root, "getChildren"):
                for child in root.getChildren():
                    nodes.extend(collect_nodes(child))
            return nodes

        def is_descendant(node, ancestor):
            current = node
            while current is not None:
                if current == ancestor:
                    return True
                if hasattr(current, "getParent"):
                    current = current.getParent()
                else:
                    break
            return False

        volumes = []
        scene_root = self._controller.getScene().getRoot()
        for node in collect_nodes(scene_root):
            if node == model_node:
                continue
            try:
                if self.getMeshType(node) != "cutting_mesh":
                    continue
            except Exception:
                continue

            if not is_descendant(node, model_node):
                continue

            mesh_data = node.getMeshData()
            if not mesh_data:
                continue

            transformed = mesh_data.getTransformed(node.getWorldTransformation())
            vertices = transformed.getVertices()
            if vertices is None or len(vertices) == 0:
                continue

            min_bounds = vertices.min(axis=0)
            max_bounds = vertices.max(axis=0)
            volumes.append({
                "node": node,
                "name": node.getName(),
                "min": min_bounds,
                "max": max_bounds,
            })

        return volumes

    def _logDanglingProbeVolumes(self, model_node: CuraSceneNode,
                                 vertices_world: numpy.ndarray,
                                 indices: numpy.ndarray,
                                 face_centers_world: numpy.ndarray,
                                 dangling_seed_mask: numpy.ndarray,
                                 dangling_candidate_mask: numpy.ndarray,
                                 overhang_mask: numpy.ndarray,
                                 vertex_adjacency: List[Set[int]],
                                 min_face_y: float,
                                 min_drop: float) -> None:
        """Log dangling detection stats for existing volumes."""
        volumes = self._collectCuttingMeshVolumes(model_node)
        if not volumes:
            return

        seed_ids = numpy.where(dangling_seed_mask)[0]
        seed_positions = vertices_world[seed_ids] if len(seed_ids) > 0 else None

        for volume in volumes:
            min_bounds = volume["min"]
            max_bounds = volume["max"]
            volume_name = volume["name"]

            seed_count = 0
            seed_min_y = None
            seed_max_y = None
            if seed_positions is not None:
                seed_inside = (
                    (seed_positions[:, 0] >= min_bounds[0]) & (seed_positions[:, 0] <= max_bounds[0]) &
                    (seed_positions[:, 1] >= min_bounds[1]) & (seed_positions[:, 1] <= max_bounds[1]) &
                    (seed_positions[:, 2] >= min_bounds[2]) & (seed_positions[:, 2] <= max_bounds[2])
                )
                seed_count = int(numpy.count_nonzero(seed_inside))
                if seed_count > 0:
                    seed_y = seed_positions[seed_inside][:, 1]
                    seed_min_y = float(seed_y.min())
                    seed_max_y = float(seed_y.max())

            face_inside = (
                (face_centers_world[:, 0] >= min_bounds[0]) & (face_centers_world[:, 0] <= max_bounds[0]) &
                (face_centers_world[:, 1] >= min_bounds[1]) & (face_centers_world[:, 1] <= max_bounds[1]) &
                (face_centers_world[:, 2] >= min_bounds[2]) & (face_centers_world[:, 2] <= max_bounds[2])
            )
            candidate_count = int(numpy.count_nonzero(face_inside & dangling_candidate_mask))
            overhang_count = int(numpy.count_nonzero(face_inside & overhang_mask))
            candidate_face_ids = numpy.where(face_inside & dangling_candidate_mask)[0]

            vertex_count = 0
            eligible_count = 0
            no_lower_count = 0
            min_delta_min = None
            min_delta_max = None
            if len(candidate_face_ids) > 0:
                vertex_ids = numpy.unique(indices[candidate_face_ids].reshape(-1))
                vertex_count = int(len(vertex_ids))
                vertex_y = vertices_world[:, 1]
                for vertex_id in vertex_ids:
                    v_id = int(vertex_id)
                    v_y = float(vertex_y[v_id])
                    if v_y <= min_face_y:
                        continue
                    eligible_count += 1
                    min_delta = None
                    for neighbor in vertex_adjacency[v_id]:
                        delta = float(vertex_y[int(neighbor)] - v_y)
                        if min_delta is None or delta < min_delta:
                            min_delta = delta
                    if min_delta is None:
                        min_delta = 0.0
                    if min_delta >= -min_drop:
                        no_lower_count += 1
                    if min_delta_min is None or min_delta < min_delta_min:
                        min_delta_min = min_delta
                    if min_delta_max is None or min_delta > min_delta_max:
                        min_delta_max = min_delta

            if seed_count > 0:
                Logger.log(
                    "d",
                    "Probe volume '%s': seeds=%d (y=%.3f..%.3f) candidate_faces=%d overhang_faces=%d",
                    volume_name,
                    seed_count,
                    float(seed_min_y),
                    float(seed_max_y),
                    candidate_count,
                    overhang_count,
                )
            else:
                Logger.log(
                    "d",
                    "Probe volume '%s': seeds=0 candidate_faces=%d overhang_faces=%d",
                    volume_name,
                    candidate_count,
                    overhang_count,
                )

            if candidate_count > 0:
                Logger.log(
                    "d",
                    "Probe volume '%s' detail: candidate_vertices=%d eligible=%d no_lower=%d min_delta=%.5f..%.5f min_face_y=%.3f",
                    volume_name,
                    vertex_count,
                    eligible_count,
                    no_lower_count,
                    float(min_delta_min) if min_delta_min is not None else 0.0,
                    float(min_delta_max) if min_delta_max is not None else 0.0,
                    float(min_face_y),
                )

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

    def _findClickedRegion(self, picked_position, regions, vertices, indices, world_transform=None):
        """Find which overhang region contains the clicked position

        Args:
            picked_position: World-space position where user clicked
            regions: List of overhang regions (each is a list of face IDs)
            vertices: Vertex positions in the same space as picked_position
            indices: Face indices
            world_transform: Optional transformation to convert local to world space

        Returns:
            Region index if found, None otherwise
        """
        if world_transform:
            # Convert picked position to local space
            inverse_transform = world_transform.getInverse()
            picked_local = picked_position.preMultiply(inverse_transform)
            picked_point = numpy.array([picked_local.x, picked_local.y, picked_local.z])
        else:
            picked_point = numpy.array([picked_position.x, picked_position.y, picked_position.z])

        # Find closest face to clicked position
        closest_face_id, closest_distance = self._findClosestFace(vertices, indices, picked_point)

        Logger.log("i", f"Closest face to click: {closest_face_id}, distance: {closest_distance:.2f}mm")

        # Find which region contains this face
        for region_id, region_faces in enumerate(regions):
            if closest_face_id in region_faces:
                return region_id

        return None

    def _detectSingleRegion(self, node: CuraSceneNode, picked_position: Vector):
        """Fast detection of a single overhang region under the click position

        This is much faster than full auto-detect because it:
        1. Only checks faces near the click
        2. Only finds one connected region
        3. Doesn't analyze the entire mesh
        """
        if not node or not node.getMeshData():
            Logger.log("e", "No mesh data available for overhang detection")
            return

        self._startProgress("MySupportImprover", "Preparing mesh...", 0, 100)
        try:
            Logger.log("i", "=== SINGLE REGION DETECTION ===")

            cache = self._getCachedMeshData(node)
            if not cache:
                Logger.log("e", "No mesh data available for overhang detection")
                return

            # Get mesh data in LOCAL space
            vertices_local = cache["vertices_local"]
            indices = cache["indices"]
            world_transform = node.getWorldTransformation()

            Logger.log("i", f"Mesh: {len(vertices_local)} vertices, {len(indices)} faces")
            self._updateProgress("Finding closest face...", 20)

            # Convert clicked position to local space
            inverse_transform = world_transform.getInverse()
            picked_local = picked_position.preMultiply(inverse_transform)
            picked_point = numpy.array([picked_local.x, picked_local.y, picked_local.z])

            # Find closest face to click
            closest_face_id, closest_distance = self._findClosestFace(vertices_local, indices, picked_point)
            Logger.log("i", f"Closest face to click: {closest_face_id}, distance: {closest_distance:.2f}mm")
            self._updateProgress("Searching for overhang face...", 35)

            # Build adjacency graph for ALL faces (needed for BFS)
            Logger.log("i", "Building face adjacency graph...")
            adjacency = self._getCachedFaceAdjacency(cache)

            # Check if this face is an overhang
            start_face_id = closest_face_id
            if not self._isFaceOverhang(vertices_local, indices, closest_face_id, self._overhang_threshold, world_transform):
                Logger.log("i", "Clicked face is not an overhang - searching nearby for overhang faces...")

                # Search nearby faces (BFS up to 20 levels deep) for an overhang
                # This helps find overhangs even when clicking on non-overhang faces of a dangling feature
                start_face_id = self._findNearbyOverhang(closest_face_id, vertices_local, indices, adjacency,
                                                         self._overhang_threshold, world_transform, max_depth=20)

                if start_face_id is None:
                    Logger.log("w", "No overhang faces found near click position - no blocker created")
                    return

                Logger.log("i", f"Found overhang face {start_face_id} near click position")
            else:
                Logger.log("i", "Clicked face is an overhang")

            Logger.log("i", "Finding connected overhang region (including near-threshold faces)...")
            self._updateProgress("Building overhang region...", 55)

            # Do BFS from start face to find overhang faces AND near-threshold faces
            # This captures the entire dangling feature, not just the strict overhangs
            region_faces = self._findConnectedOverhangRegionExpanded(
                start_face_id, vertices_local, indices, adjacency,
                self._overhang_threshold, world_transform, angle_margin=10.0
            )

            Logger.log("i", f"Found connected overhang region with {len(region_faces)} faces")
            self._updateProgress(f"Region found: {len(region_faces)} faces", 70)

            if len(region_faces) < 10:
                Logger.log("w", f"Region too small ({len(region_faces)} faces) - no blocker created")
                return

            # Calculate region bounds and create blocker
            region_center_local, region_bounds = self._calculateRegionBounds(vertices_local, indices, region_faces)
            min_bounds, max_bounds = region_bounds

            # Calculate dimensions with padding
            region_size = max_bounds - min_bounds
            padding_factor = 1.4
            padded_size_x = max(1.0, float(region_size[0] * padding_factor))
            padded_size_y = max(1.0, float(region_size[1] * padding_factor))
            padded_size_z = max(1.0, float(region_size[2] * padding_factor))

            # Position volume so its TOP is at the highest point of the region
            # This ensures the dangling part only intersects the top of the volume
            # Volume position is at its center, so: center_y = max_y - size_y/2
            position_local_x = (min_bounds[0] + max_bounds[0]) / 2.0  # Center in X
            position_local_y = max_bounds[1] - (padded_size_y / 2.0)  # Top at max Y
            position_local_z = (min_bounds[2] + max_bounds[2]) / 2.0  # Center in Z

            # Transform to world space
            position_local_vec = Vector(position_local_x, position_local_y, position_local_z)
            position_world = position_local_vec.preMultiply(world_transform)

            # Create blocker
            self._updateProgress("Creating support blocker...", 90)
            self._createModifierVolumeWithSize(node, position_world, padded_size_x, padded_size_y, padded_size_z)

            Logger.log("i", f"Created support blocker for region ({len(region_faces)} faces) at world pos: [{position_world.x:.2f}, {position_world.y:.2f}, {position_world.z:.2f}], size: [{padded_size_x:.2f}, {padded_size_y:.2f}, {padded_size_z:.2f}]")
            Logger.log("d", f"Region bounds: min_y={min_bounds[1]:.2f}, max_y={max_bounds[1]:.2f}, volume top at y={max_bounds[1]:.2f}")
            self._updateProgress("Support blocker created.", 100)

        except Exception as e:
            Logger.log("e", f"Failed to detect single region: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())
        finally:
            self._closeProgress()

    def _transformVertices(self, vertices: numpy.ndarray, transform) -> numpy.ndarray:
        """Apply a world transform to vertex positions."""
        transform_data = transform.getData()
        rotation_matrix = transform_data[0:3, 0:3]
        translation = transform_data[0:3, 3]
        return (vertices @ rotation_matrix.T) + translation

    def _transformNormals(self, normals: numpy.ndarray, transform) -> numpy.ndarray:
        """Apply a world transform to normals (handles non-uniform scaling)."""
        transform_data = transform.getData()
        matrix = transform_data[0:3, 0:3]
        try:
            normal_matrix = numpy.linalg.inv(matrix).T
        except numpy.linalg.LinAlgError:
            normal_matrix = matrix

        normals_world = normals @ normal_matrix.T
        lengths = numpy.linalg.norm(normals_world, axis=1, keepdims=True)
        return normals_world / numpy.maximum(lengths, 1e-10)

    def _startProgress(self, title: str, message: str, minimum: int = 0, maximum: int = 100):
        app = QApplication.instance()
        if app is None:
            return None

        dialog = self._progress_dialog
        if dialog is None:
            dialog = QProgressDialog(message, None, minimum, maximum)
            dialog.setWindowTitle(title)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.setCancelButton(None)
            dialog.setMinimumDuration(0)
            dialog.setAutoClose(False)
            dialog.setAutoReset(False)
            dialog.setValue(minimum)
            self._progress_dialog = dialog
        else:
            dialog.setLabelText(message)
            dialog.setRange(minimum, maximum)
            dialog.setValue(minimum)

        dialog.show()
        app.processEvents()
        return dialog

    def _updateProgress(self, message: str, value: Optional[int] = None) -> None:
        dialog = self._progress_dialog
        if dialog is None:
            return
        if message:
            dialog.setLabelText(message)
        if value is not None:
            dialog.setValue(int(value))
        QApplication.processEvents()

    def _closeProgress(self) -> None:
        dialog = self._progress_dialog
        if dialog is None:
            return
        dialog.close()
        self._progress_dialog = None

    def _computeFaceNormalsFromVertexNormals(self, vertex_normals: numpy.ndarray,
                                             indices: numpy.ndarray) -> numpy.ndarray:
        """Compute face normals by averaging vertex normals."""
        face_normals = vertex_normals[indices].mean(axis=1)
        lengths = numpy.linalg.norm(face_normals, axis=1, keepdims=True)
        return face_normals / numpy.maximum(lengths, 1e-10)

    def _computeFaceCenters(self, vertices: numpy.ndarray, indices: numpy.ndarray) -> numpy.ndarray:
        """Compute face centroids for all faces."""
        v0 = vertices[indices[:, 0]]
        v1 = vertices[indices[:, 1]]
        v2 = vertices[indices[:, 2]]
        return (v0 + v1 + v2) / 3.0

    def _detectOverhangFacesFromNormals(self, face_normals_world: numpy.ndarray,
                                        threshold_angle: float) -> numpy.ndarray:
        """Detect overhang faces using precomputed world-space normals."""
        build_direction = numpy.array([0.0, -1.0, 0.0])
        dot_products = numpy.dot(face_normals_world, build_direction)
        dot_products = numpy.clip(dot_products, -1.0, 1.0)
        angles = numpy.degrees(numpy.arccos(dot_products))

        overhang_mask = angles < (90.0 - threshold_angle)
        return numpy.where(overhang_mask)[0]

    def _find_obstruction_height_in_mesh(self, x: float, z: float, max_y: float,
                                         vertices: numpy.ndarray, indices: numpy.ndarray,
                                         tolerance: float = 0.5, max_y_epsilon: float = 0.05) -> float:
        """Find highest mesh point below (x, z) within the provided mesh."""
        highest_y = 0.0

        for face in indices:
            v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

            min_x = min(v0[0], v1[0], v2[0]) - tolerance
            max_x = max(v0[0], v1[0], v2[0]) + tolerance
            min_z = min(v0[2], v1[2], v2[2]) - tolerance
            max_z = max(v0[2], v1[2], v2[2]) + tolerance

            if x < min_x or x > max_x or z < min_z or z > max_z:
                continue

            denom = (v1[2] - v2[2]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[2] - v2[2])
            if abs(denom) < 1e-10:
                continue

            a = ((v1[2] - v2[2]) * (x - v2[0]) + (v2[0] - v1[0]) * (z - v2[2])) / denom
            b = ((v2[2] - v0[2]) * (x - v2[0]) + (v0[0] - v2[0]) * (z - v2[2])) / denom
            c = 1.0 - a - b

            if a >= -0.1 and b >= -0.1 and c >= -0.1:
                y = a * v0[1] + b * v1[1] + c * v2[1]
                if y < max_y - max_y_epsilon and y > highest_y:
                    highest_y = y

        return highest_y

    def _filterOverhangFacesByNeighborHeight(self, overhang_face_ids: numpy.ndarray,
                                             adjacency: Dict[int, List[int]],
                                             face_centers_world: numpy.ndarray,
                                             min_delta_y: float = 0.05,
                                             max_lower_fraction: float = 0.5,
                                             min_face_y: float = 0.2,
                                             obstruction_vertices: Optional[numpy.ndarray] = None,
                                             obstruction_indices: Optional[numpy.ndarray] = None,
                                             min_clearance: float = 0.0) -> numpy.ndarray:
        """Filter overhang faces using neighbor height, build-plate proximity, and obstructions."""
        filtered = []
        for face_id in overhang_face_ids:
            neighbors = adjacency.get(int(face_id), [])
            face_y = face_centers_world[int(face_id)][1]
            if face_y <= min_face_y:
                continue

            if not neighbors:
                filtered.append(int(face_id))
                continue

            lower_count = 0
            for neighbor_id in neighbors:
                if face_centers_world[neighbor_id][1] < (face_y - min_delta_y):
                    lower_count += 1

            if (lower_count / len(neighbors)) <= max_lower_fraction:
                if min_clearance > 0.0 and obstruction_vertices is not None and obstruction_indices is not None:
                    face_x = face_centers_world[int(face_id)][0]
                    face_z = face_centers_world[int(face_id)][2]
                    obstruction_y = self._find_obstruction_height_in_mesh(
                        face_x, face_z, face_y, obstruction_vertices, obstruction_indices
                    )
                    if obstruction_y > 0.0 and (face_y - obstruction_y) <= min_clearance:
                        continue
                filtered.append(int(face_id))

        return numpy.array(filtered, dtype=numpy.int32)

    def _buildVertexAdjacency(self, indices: numpy.ndarray, vertex_count: int) -> List[Set[int]]:
        """Build adjacency list for vertices based on shared edges."""
        adjacency: List[Set[int]] = [set() for _ in range(vertex_count)]
        for face in indices:
            v0 = int(face[0])
            v1 = int(face[1])
            v2 = int(face[2])
            adjacency[v0].update([v1, v2])
            adjacency[v1].update([v0, v2])
            adjacency[v2].update([v0, v1])
        return adjacency

    def _detectDanglingVertices(self, vertices_world: numpy.ndarray, indices: numpy.ndarray,
                                face_mask: numpy.ndarray, min_drop: float = 0.05) -> numpy.ndarray:
        """Detect vertices with no neighboring vertices below them on candidate faces."""
        vertex_count = len(vertices_world)
        dangling = numpy.zeros(vertex_count, dtype=bool)
        if vertex_count == 0:
            return dangling

        candidate_faces = numpy.where(face_mask)[0]
        if len(candidate_faces) == 0:
            return dangling

        overhang_vertex_ids = numpy.unique(indices[candidate_faces])
        adjacency = self._buildVertexAdjacency(indices, vertex_count)

        for vertex_id in overhang_vertex_ids:
            neighbors = adjacency[int(vertex_id)]
            if not neighbors:
                dangling[int(vertex_id)] = True
                continue

            v_y = vertices_world[int(vertex_id)][1]
            has_lower = False
            for neighbor_id in neighbors:
                if vertices_world[neighbor_id][1] < (v_y - min_drop):
                    has_lower = True
                    break
            if not has_lower:
                dangling[int(vertex_id)] = True

        return dangling

    def _detectDanglingFacesFromVertices(self, indices: numpy.ndarray,
                                         dangling_vertex_mask: numpy.ndarray,
                                         face_mask: numpy.ndarray) -> numpy.ndarray:
        """Detect candidate faces that touch a dangling vertex."""
        if len(indices) == 0:
            return numpy.array([], dtype=numpy.int32)
        face_has_dangling = numpy.any(dangling_vertex_mask[indices], axis=1)
        face_mask = face_has_dangling & face_mask
        return numpy.where(face_mask)[0].astype(numpy.int32)

    def _findDanglingVertexRegions(self, vertices_world: numpy.ndarray, indices: numpy.ndarray,
                                   min_drop: float, min_face_y: float,
                                   height_epsilon: float = 0.0) -> Tuple[List[Set[int]], numpy.ndarray]:
        """Find connected vertex regions where no vertex has a lower neighbor."""
        vertex_count = len(vertices_world)
        if vertex_count == 0 or len(indices) == 0:
            return [], numpy.zeros(vertex_count, dtype=bool)

        adjacency = self._buildVertexAdjacency(indices, vertex_count)
        vertex_y = vertices_world[:, 1]
        eligible = vertex_y > min_face_y

        has_lower = numpy.zeros(vertex_count, dtype=bool)
        for vertex_id in range(vertex_count):
            if not eligible[vertex_id]:
                continue
            v_y = vertex_y[vertex_id]
            for neighbor in adjacency[vertex_id]:
                if vertex_y[neighbor] < (v_y - min_drop - height_epsilon):
                    has_lower[vertex_id] = True
                    break

        dangling_mask = eligible & ~has_lower
        seeds = numpy.where(dangling_mask)[0]
        Logger.log(
            "d",
            "Dangling vertex stats: eligible=%d dangling=%d min_drop=%.3f eps=%.3f",
            int(numpy.count_nonzero(eligible)),
            int(len(seeds)),
            float(min_drop),
            float(height_epsilon),
        )
        if len(seeds) > 0:
            max_debug = 30
            sample = seeds[:max_debug]
            for idx, vertex_id in enumerate(sample, start=1):
                neighbors = adjacency[int(vertex_id)]
                v = vertices_world[int(vertex_id)]
                v_y = vertex_y[int(vertex_id)]
                min_delta = None
                for neighbor in neighbors:
                    delta = float(vertex_y[neighbor] - v_y)
                    if min_delta is None or delta < min_delta:
                        min_delta = delta
                Logger.log(
                    "d",
                    "Dangling seed %d: id=%d pos=[%.3f, %.3f, %.3f] neighbors=%d min_neighbor_delta=%.4f",
                    idx,
                    int(vertex_id),
                    float(v[0]),
                    float(v[1]),
                    float(v[2]),
                    int(len(neighbors)),
                    float(min_delta) if min_delta is not None else 0.0,
                )

        assigned = numpy.zeros(vertex_count, dtype=bool)
        regions = []

        for seed in seeds:
            if assigned[seed]:
                continue
            region = set([seed])
            assigned[seed] = True
            queue = deque([seed])

            while queue:
                current = queue.popleft()
                for neighbor in adjacency[current]:
                    if assigned[neighbor] or not dangling_mask[neighbor]:
                        continue
                    assigned[neighbor] = True
                    region.add(neighbor)
                    queue.append(neighbor)

            if region:
                regions.append(region)

        return regions, dangling_mask

    def _mergeSmallDanglingRegions(self, regions: List[Set[int]],
                                   adjacency: List[Set[int]],
                                   min_vertices: int) -> List[Set[int]]:
        """Merge small dangling regions into a single neighboring region."""
        if not regions:
            return regions

        vertex_count = len(adjacency)
        region_id = [-1] * vertex_count
        for idx, region in enumerate(regions):
            for vertex_id in region:
                region_id[int(vertex_id)] = idx

        region_sizes = [len(region) for region in regions]
        small = [size < min_vertices for size in region_sizes]
        parent = list(range(len(regions)))

        def find_root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra = find_root(a)
            rb = find_root(b)
            if ra != rb:
                parent[rb] = ra

        region_neighbors = [set() for _ in range(len(regions))]
        for vertex_id, neighbors in enumerate(adjacency):
            region_a = region_id[vertex_id]
            if region_a < 0:
                continue
            for neighbor in neighbors:
                region_b = region_id[neighbor]
                if region_b < 0 or region_a == region_b:
                    continue
                region_neighbors[region_a].add(region_b)

        for idx, is_small in enumerate(small):
            if not is_small:
                continue
            neighbors = region_neighbors[idx]
            if not neighbors:
                continue
            best_neighbor = max(neighbors, key=lambda n: region_sizes[n])
            union(idx, best_neighbor)

        merged = {}
        for idx, region in enumerate(regions):
            root = find_root(idx)
            merged.setdefault(root, set()).update(region)

        return list(merged.values())

    def _expandDanglingFaceRegion(self, seed_faces: numpy.ndarray,
                                  adjacency: Dict[int, List[int]],
                                  candidate_mask: numpy.ndarray,
                                  max_faces: int,
                                  max_depth: int) -> List[int]:
        """Expand seed faces into a local candidate-face region."""
        if seed_faces is None or len(seed_faces) == 0:
            return []

        visited = set(int(face_id) for face_id in seed_faces)
        queue = deque((int(face_id), 0) for face_id in seed_faces)

        while queue:
            face_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(face_id, []):
                if neighbor in visited:
                    continue
                if not candidate_mask[neighbor]:
                    continue
                visited.add(neighbor)
                if len(visited) >= max_faces:
                    return list(visited)
                queue.append((neighbor, depth + 1))

        return list(visited)

    def _mergeOverlappingFaceRegions(self, regions: List[List[int]]) -> List[List[int]]:
        """Merge face regions that overlap."""
        if not regions:
            return []

        region_sets = [set(region) for region in regions]
        parent = list(range(len(region_sets)))

        def find_root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra = find_root(a)
            rb = find_root(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(region_sets)):
            for j in range(i + 1, len(region_sets)):
                if region_sets[i] & region_sets[j]:
                    union(i, j)

        merged = {}
        for idx, region in enumerate(region_sets):
            root = find_root(idx)
            merged.setdefault(root, set()).update(region)

        return [list(region) for region in merged.values()]

    def _mergeOverlappingFaceRegionsWithVertices(self, face_regions: List[List[int]],
                                                 vertex_regions: List[Set[int]]) -> Tuple[List[List[int]], List[List[int]]]:
        """Merge overlapping face regions and union corresponding vertex regions."""
        if not face_regions:
            return [], []

        region_sets = [set(region) for region in face_regions]
        parent = list(range(len(region_sets)))

        def find_root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra = find_root(a)
            rb = find_root(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(region_sets)):
            for j in range(i + 1, len(region_sets)):
                if region_sets[i] & region_sets[j]:
                    union(i, j)

        merged_faces = {}
        merged_vertices = {}
        for idx, region in enumerate(region_sets):
            root = find_root(idx)
            merged_faces.setdefault(root, set()).update(region)
            merged_vertices.setdefault(root, set()).update(vertex_regions[idx])

        merged_face_list = [list(region) for region in merged_faces.values()]
        merged_vertex_list = [list(region) for region in merged_vertices.values()]
        return merged_face_list, merged_vertex_list

    def _expandDanglingVertexRegionUpwards(self, region: Set[int], vertices: numpy.ndarray,
                                           adjacency: Dict[int, List[int]],
                                           min_drop: float = 0.0,
                                           height_epsilon: float = 0.0) -> Set[int]:
        """Expand a dangling vertex region upward while all lower neighbors stay inside the region."""
        if not region:
            return set()

        expanded = set(int(v) for v in region)
        use_dict = hasattr(adjacency, "get")
        changed = True
        safety = 0
        while changed and safety < 1000:
            changed = False
            safety += 1
            for vertex_id in list(expanded):
                if use_dict:
                    neighbors = adjacency.get(int(vertex_id), [])
                else:
                    neighbors = adjacency[int(vertex_id)]
                for neighbor in neighbors:
                    if neighbor in expanded:
                        continue
                    neighbor_y = vertices[neighbor][1]
                    if use_dict:
                        neighbor_adjacency = adjacency.get(int(neighbor), [])
                    else:
                        neighbor_adjacency = adjacency[int(neighbor)]
                    lower_neighbors = [
                        int(nid) for nid in neighbor_adjacency
                        if vertices[nid][1] < (neighbor_y - min_drop - height_epsilon)
                    ]
                    if all(nid in expanded for nid in lower_neighbors):
                        expanded.add(int(neighbor))
                        changed = True
            if safety >= 1000:
                Logger.log("w", "Dangling vertex expansion reached max iterations (size=%d)", len(expanded))

        return expanded

    def _danglingVertexRegionsToFaceRegions(self, vertex_regions: List[Set[int]],
                                            indices: numpy.ndarray,
                                            face_mask: Optional[numpy.ndarray] = None
                                            ) -> List[List[int]]:
        """Convert dangling vertex regions to face regions, with a loose fallback."""
        if not vertex_regions or len(indices) == 0:
            return []

        vertex_count = int(indices.max()) + 1 if len(indices) else 0
        region_id = [-1] * vertex_count
        for idx, region in enumerate(vertex_regions):
            for vertex_id in region:
                region_id[int(vertex_id)] = idx

        face_regions: List[List[int]] = [[] for _ in range(len(vertex_regions))]
        loose_regions: List[List[int]] = [[] for _ in range(len(vertex_regions))]
        for face_id, face in enumerate(indices):
            if face_mask is not None and not bool(face_mask[face_id]):
                continue
            v0, v1, v2 = int(face[0]), int(face[1]), int(face[2])
            rid = region_id[v0]
            if rid >= 0 and rid == region_id[v1] == region_id[v2]:
                face_regions[rid].append(face_id)
                continue
            region_ids = [region_id[v0], region_id[v1], region_id[v2]]
            region_ids = [rid for rid in region_ids if rid >= 0]
            if not region_ids:
                continue
            pick = max(set(region_ids), key=region_ids.count)
            loose_regions[pick].append(face_id)

        if face_regions and sum(len(region) for region in face_regions) == 0:
            Logger.log(
                "d",
                "Dangling face conversion produced zero strict faces (regions=%d, vertices min=%d max=%d).",
                len(vertex_regions),
                min(len(region) for region in vertex_regions),
                max(len(region) for region in vertex_regions),
            )

        combined = []
        for idx, region_faces in enumerate(face_regions):
            if region_faces:
                combined.append(region_faces)
                continue
            if loose_regions[idx]:
                Logger.log(
                    "d",
                    "Dangling region %d: strict faces=0 loose faces=%d (face_mask=%s)",
                    idx + 1,
                    len(loose_regions[idx]),
                    "on" if face_mask is not None else "off",
                )
                combined.append(loose_regions[idx])
        return combined

    def _autoDetectOverhangs(self, node: CuraSceneNode, picked_position: Vector = None):
        """Automatically detect overhangs and create support blockers

        Args:
            node: The scene node to analyze
            picked_position: Optional clicked position - if provided, only create blocker for clicked region
        """
        if not node or not node.getMeshData():
            Logger.log("e", "No mesh data available for overhang detection")
            return

        self._startProgress("MySupportImprover", "Preparing mesh...", 0, 100)
        try:
            Logger.log("i", "=== AUTO OVERHANG DETECTION ===")
            Logger.log(
                "i",
                "Auto-detect settings: threshold=%.1f, sharp_features=%s, dangling_vertices=%s",
                float(self._overhang_threshold),
                str(self._detect_sharp_features),
                str(self._detect_dangling_vertices),
            )

            cache = self._getCachedMeshData(node)
            if not cache:
                Logger.log("e", "No mesh data available for overhang detection")
                return

            # Get mesh data in LOCAL space (bounds/sizes should be in local coordinates)
            vertices_local = cache["vertices_local"]
            indices = cache["indices"]
            world_transform = node.getWorldTransformation()

            Logger.log("i", f"Mesh: {len(vertices_local)} vertices, {len(indices)} faces")
            if self._detect_dangling_vertices:
                self._updateProgress("Detecting dangling vertices...", 15)
            else:
                self._updateProgress("Detecting overhang faces...", 15)

            vertices_world = self._transformVertices(vertices_local, world_transform)

            # Detect overhang faces using world-space normals for correct orientation
            face_normals_local = cache["face_normals_from_mesh"]
            if face_normals_local is not None:
                Logger.log("d", "Using mesh normals for overhang detection")

            face_normals_geom_local = cache["face_normals_geom"]
            if face_normals_local is None:
                face_normals_local = face_normals_geom_local

            face_normals_world = self._transformNormals(face_normals_local, world_transform)
            face_normals_geom_world = self._transformNormals(face_normals_geom_local, world_transform)
            raw_overhang_ids = self._detectOverhangFacesFromNormals(face_normals_world, self._overhang_threshold)

            adjacency_all = self._getCachedFaceAdjacency(cache)
            face_centers_local = cache["face_centers_local"]
            face_centers_world = self._transformVertices(face_centers_local, world_transform)
            face_vertices_world = vertices_world[indices]
            face_min_world = face_vertices_world.min(axis=1)
            face_max_world = face_vertices_world.max(axis=1)
            mesh_min_y = float(vertices_world[:, 1].min()) if len(vertices_world) else 0.0
            mesh_max_y = float(vertices_world[:, 1].max()) if len(vertices_world) else 0.0
            min_face_y = mesh_min_y + 0.2
            if mesh_min_y > 0.5:
                min_face_y = mesh_min_y
                Logger.log("d", "Floating mesh detected; skipping build-plate offset for filters")
            face_count = len(indices)
            overhang_mask = numpy.zeros(face_count, dtype=bool)
            if len(raw_overhang_ids) > 0:
                overhang_mask[raw_overhang_ids] = True
            build_direction = numpy.array([0.0, -1.0, 0.0])
            normals_for_dangling = face_normals_geom_world if self._detect_dangling_vertices else face_normals_world
            face_down_dot = numpy.dot(face_normals_world, build_direction)
            face_down_dot = numpy.clip(face_down_dot, -1.0, 1.0)
            face_down_angles = numpy.degrees(numpy.arccos(face_down_dot))
            downward_mask = numpy.dot(normals_for_dangling, build_direction) > 0.0
            dangling_min_angle = 0.0
            dangling_candidate_mask = downward_mask & overhang_mask
            downward_face_ids = numpy.where(downward_mask)[0]

            face_lower_fraction = numpy.zeros(face_count, dtype=numpy.float32)
            convex_pos_counts = numpy.zeros(face_count, dtype=numpy.int32)
            convex_total_counts = numpy.zeros(face_count, dtype=numpy.int32)
            normals_for_stats = normals_for_dangling if self._detect_dangling_vertices else face_normals_world

            for face_id in range(face_count):
                neighbors = adjacency_all.get(face_id, [])
                if not neighbors:
                    continue

                face_y = face_centers_world[face_id][1]
                lower_count = 0

                n1 = normals_for_stats[face_id]
                c1 = face_centers_world[face_id]

                for neighbor_id in neighbors:
                    if face_centers_world[neighbor_id][1] < (face_y - 0.05):
                        lower_count += 1

                    n2 = normals_for_stats[neighbor_id]
                    c2 = face_centers_world[neighbor_id]
                    dn = n2 - n1
                    dc = c2 - c1
                    s = numpy.dot(dn, dc)
                    if abs(s) > 1e-9:
                        convex_total_counts[face_id] += 1
                        if s > 0:
                            convex_pos_counts[face_id] += 1

                face_lower_fraction[face_id] = lower_count / len(neighbors)
            Logger.log("i", f"Found {len(raw_overhang_ids)} overhang faces")

            min_faces_overhang = 10
            min_faces_dangling = 6
            min_faces = min_faces_overhang
            regions = []
            dangling_vertex_regions_active = False
            dangling_region_vertices = None

            if self._detect_dangling_vertices:
                self._updateProgress("Detecting dangling regions...", 35)
                dangling_min_drop = 0.0
                dangling_height_epsilon_seed = 0.0
                dangling_height_epsilon_expand = 0.005
                dangling_regions, dangling_seed_mask = self._findDanglingVertexRegions(
                    vertices_world,
                    indices,
                    min_drop=dangling_min_drop,
                    min_face_y=min_face_y,
                    height_epsilon=dangling_height_epsilon_seed,
                )
                vertex_adjacency = self._getCachedVertexAdjacency(cache, len(vertices_world))
                self._logDanglingProbeVolumes(
                    node,
                    vertices_world,
                    indices,
                    face_centers_world,
                    dangling_seed_mask,
                    dangling_candidate_mask,
                    overhang_mask,
                    vertex_adjacency,
                    min_face_y,
                    dangling_min_drop,
                )
                if len(dangling_regions) > 0:
                    dangling_regions = self._mergeSmallDanglingRegions(
                        dangling_regions, vertex_adjacency, min_vertices=max(3, min_faces_dangling * 3)
                    )
                    expanded_regions = []
                    expanded_vertex_regions = []
                    vertex_count = len(vertices_world)
                    for idx, region in enumerate(dangling_regions, start=1):
                        expanded_vertex_region = self._expandDanglingVertexRegionUpwards(
                            region,
                            vertices_world,
                            vertex_adjacency,
                            min_drop=dangling_min_drop,
                            height_epsilon=dangling_height_epsilon_expand,
                        )
                        region_mask = numpy.zeros(vertex_count, dtype=bool)
                        region_mask[list(expanded_vertex_region)] = True
                        seed_faces = numpy.where(
                            dangling_candidate_mask & numpy.any(region_mask[indices], axis=1)
                        )[0]
                        if len(seed_faces) == 0:
                            Logger.log("d", "Dangling region %d: no seed faces in candidate mask", idx)
                            continue
                        expanded = self._expandDanglingFaceRegion(
                            seed_faces,
                            adjacency_all,
                            dangling_candidate_mask,
                            max_faces=180,
                            max_depth=4,
                        )
                        Logger.log(
                            "d",
                            "Dangling region %d: seeds=%d expanded_vertices=%d seed_faces=%d expanded_faces=%d",
                            idx,
                            len(region),
                            len(expanded_vertex_region),
                            len(seed_faces),
                            len(expanded),
                        )
                        expanded_regions.append(expanded)
                        expanded_vertex_regions.append(expanded_vertex_region)

                    regions, dangling_region_vertices = self._mergeOverlappingFaceRegionsWithVertices(
                        expanded_regions, expanded_vertex_regions
                    )
                    if regions:
                        dangling_vertex_regions_active = True
                        min_faces = min_faces_dangling
                        region_sizes = [len(region) for region in regions]
                        Logger.log(
                            "i",
                            "Found %d connected dangling regions (candidate faces=%d, min_angle=%.1f)",
                            len(regions),
                            int(dangling_candidate_mask.sum()),
                            dangling_min_angle,
                        )
                        Logger.log(
                            "d",
                            "Dangling region sizes: min=%d max=%d avg=%.1f",
                            int(min(region_sizes)),
                            int(max(region_sizes)),
                            float(sum(region_sizes)) / len(region_sizes),
                        )
                        self._updateProgress(f"Found {len(regions)} dangling regions", 50)
                    else:
                        Logger.log("i", "Dangling vertex regions produced no faces - stopping (no fallback)")
                        return
                else:
                    Logger.log("i", "Dangling vertex detector found no regions - stopping (no fallback)")
                    return

            region_source_ids = raw_overhang_ids
            region_source_label = "overhang"
            use_neighbor_filter = True
            filtered_set = set()
            if not dangling_vertex_regions_active:
                if self._detect_dangling_vertices:
                    Logger.log("i", "Dangling vertex mode inactive - using overhang regions")

            if not dangling_vertex_regions_active:
                self._updateProgress(f"Found {len(raw_overhang_ids)} overhang faces", 35)
                filtered_overhang_ids = region_source_ids
                if use_neighbor_filter and len(region_source_ids) > 0:
                    filtered_overhang_ids = self._filterOverhangFacesByNeighborHeight(
                        region_source_ids,
                        adjacency_all,
                        face_centers_world,
                        min_delta_y=0.05,
                        max_lower_fraction=0.5,
                        min_face_y=min_face_y,
                        obstruction_vertices=vertices_world,
                        obstruction_indices=indices,
                        min_clearance=0.0
                    )
                    if len(filtered_overhang_ids) != len(region_source_ids):
                        Logger.log("i", f"Filtered to {len(filtered_overhang_ids)} faces after neighbor-height check")

                filtered_set = set(int(face_id) for face_id in filtered_overhang_ids)
                if len(region_source_ids) == 0:
                    if self._detect_sharp_features:
                        Logger.log("i", "No detection faces found - falling back to sharp feature detection")
                    else:
                        Logger.log("i", "No overhangs detected")
                        return
                else:
                    # Find connected regions using selected detection faces, then keep regions with filtered faces
                    regions = self._findConnectedRegions(vertices_local, indices, region_source_ids)
                    Logger.log("i", f"Found {len(regions)} connected {region_source_label} regions")
                    self._updateProgress(f"Found {len(regions)} regions", 50)

                    if use_neighbor_filter:
                        if len(filtered_set) > 0:
                            regions = [r for r in regions if any(face_id in filtered_set for face_id in r)]
                            Logger.log("i", f"Kept {len(regions)} regions after neighbor-height filter")
                            self._updateProgress(f"Filtered to {len(regions)} regions", 55)
                        else:
                            Logger.log("i", "All detection faces filtered out by neighbor-height check")
                            regions = []

            # Apply sharp feature detection if enabled
            if self._detect_sharp_features:
                Logger.log("i", "Sharp feature detection enabled - analyzing vertex curvature...")
                self._updateProgress("Analyzing sharp features...", 60)
                sharp_vertices = self._detectSharpVertices(vertices_world, indices, curvature_threshold=2.0)
                if len(sharp_vertices) > 0:
                    Logger.log("i", f"Detected {len(sharp_vertices)} sharp vertices - expanding regions...")
                    regions = self._expandRegionsWithSharpFeatures(vertices_world, indices, regions,
                                                                   sharp_vertices, expansion_radius=5.0)
                    Logger.log("i", f"After sharp feature expansion: {len(regions)} total regions")
                    self._updateProgress(f"Expanded to {len(regions)} regions", 65)

            # If clicked position provided, find which region was clicked
            target_region_id = None
            if picked_position:
                target_region_id = self._findClickedRegion(picked_position, regions, vertices_local, indices, world_transform)
                if target_region_id is not None:
                    Logger.log("i", f"Clicked on region {target_region_id + 1} - will create blocker only for this region")
                else:
                    Logger.log("w", "Click position not in any overhang region - creating blockers for all regions")

            # Create support blockers
            created_count = 0
            total_regions = len(regions)
            if total_regions > 0:
                self._updateProgress(f"Creating blockers for {total_regions} regions...", 75)

            # Dangling regions should have mostly upward neighbors (few lower neighbors).
            region_lower_fraction_threshold = 0.35
            if mesh_min_y > 0.5:
                region_lower_fraction_threshold = 0.45
                Logger.log("d", "Floating mesh detected; relaxing lower-neighbor threshold to %.2f",
                           region_lower_fraction_threshold)
            convexity_threshold = 0.6
            apply_convexity_filter = not dangling_vertex_regions_active and self._detect_dangling_vertices
            apply_lower_fraction_filter = not dangling_vertex_regions_active
            processed_regions = 0
            for region_id, region_faces in enumerate(regions):
                processed_regions += 1
                # If we have a target region, skip all others
                if target_region_id is not None and region_id != target_region_id:
                    continue
                region_faces_for_stats = region_faces

                # Filter out regions that are mostly sloping downward (not dangling tips)
                if apply_lower_fraction_filter and region_faces_for_stats:
                    avg_lower_fraction = float(face_lower_fraction[region_faces_for_stats].mean())
                    if avg_lower_fraction > region_lower_fraction_threshold:
                        Logger.log("d", f"Skipping region {region_id + 1}: avg lower fraction {avg_lower_fraction:.2f}")
                        continue

                # Convexity filter: dangling parts should curve outward (stalactite-like).
                if apply_convexity_filter:
                    convex_total = int(convex_total_counts[region_faces_for_stats].sum())
                    if convex_total > 0:
                        convex_score = float(convex_pos_counts[region_faces_for_stats].sum()) / convex_total
                        if convex_score < convexity_threshold:
                            Logger.log("d", f"Skipping region {region_id + 1}: convex score {convex_score:.2f}")
                            continue

                region_faces_for_bounds = region_faces
                region_vertex_mask = None
                dangling_region_faces_full = None
                if dangling_vertex_regions_active:
                    candidate_region_faces = [face_id for face_id in region_faces if dangling_candidate_mask[face_id]]
                    if not candidate_region_faces:
                        Logger.log("d", f"Skipping region {region_id + 1}: no downward overhang faces")
                        continue
                    region_faces_for_bounds = candidate_region_faces
                    dangling_region_faces_full = candidate_region_faces
                elif len(filtered_set) > 0:
                    filtered_region_faces = [face_id for face_id in region_faces if face_id in filtered_set]
                    if len(filtered_region_faces) == 0:
                        continue
                    # For tiny regions, keep raw bounds to avoid offset from single-face filtering.
                    if len(filtered_region_faces) == 1 and len(region_faces) <= 2:
                        region_faces_for_bounds = region_faces
                    else:
                        region_faces_for_bounds = filtered_region_faces

                if len(region_faces_for_bounds) >= min_faces:
                    # Calculate region center and bounds in LOCAL space
                    region_center_local, region_bounds = self._calculateRegionBounds(vertices_local, indices, region_faces_for_bounds)
                    min_bounds, max_bounds = region_bounds
                    min_bounds_world = None
                    max_bounds_world = None
                    min_bounds_world_faces = None
                    max_bounds_world_faces = None
                    if dangling_vertex_regions_active:
                        face_center_y = face_centers_local[region_faces_for_bounds][:, 1]
                        if len(face_center_y) > 0 and len(region_faces_for_bounds) >= max(200, min_faces * 20):
                            height_cut = float(numpy.percentile(face_center_y, 35))
                            lower_band_faces = [face_id for face_id, cy in zip(region_faces_for_bounds, face_center_y)
                                                if cy <= height_cut]
                            min_band_faces = max(min_faces, min_faces // 2)
                            if len(lower_band_faces) >= min_band_faces:
                                region_center_local, region_bounds = self._calculateRegionBounds(
                                    vertices_local, indices, lower_band_faces
                                )
                                min_bounds, max_bounds = region_bounds
                                region_faces_for_bounds = lower_band_faces
                                Logger.log(
                                    "d",
                                    "Dangling bounds tightened: faces=%d height_cut=%.3f",
                                    len(region_faces_for_bounds),
                                    height_cut,
                                )
                    if dangling_vertex_regions_active:
                        dangling_faces_full = dangling_region_faces_full or region_faces_for_bounds
                        region_face_mask = numpy.zeros(len(indices), dtype=bool)
                        region_face_mask[dangling_faces_full] = True
                        _, face_bounds_world = self._calculateRegionBounds(vertices_world, indices, region_faces_for_bounds)
                        min_bounds_world_faces, max_bounds_world_faces = face_bounds_world
                        region_vertex_ids = None
                        if dangling_region_vertices is not None and region_id < len(dangling_region_vertices):
                            face_vertex_ids = numpy.unique(indices[dangling_faces_full])
                            region_vertex_ids = numpy.unique(
                                numpy.concatenate(
                                    (numpy.array(dangling_region_vertices[region_id], dtype=numpy.int32), face_vertex_ids)
                                )
                            )
                        if region_vertex_ids is None or region_vertex_ids.size == 0:
                            region_vertex_ids = numpy.unique(indices[dangling_faces_full])
                        region_vertex_mask = numpy.zeros(len(vertices_local), dtype=bool)
                        region_vertex_mask[region_vertex_ids] = True
                        if region_vertex_ids is not None and region_vertex_ids.size > 0:
                            region_face_mask |= (numpy.sum(region_vertex_mask[indices], axis=1) >= 2)
                        region_vertices_world = vertices_world[region_vertex_ids]
                        min_bounds_world = region_vertices_world.min(axis=0)
                        max_bounds_world = region_vertices_world.max(axis=0)
                        max_center_y = float(face_centers_world[region_faces_for_bounds][:, 1].max())
                        Logger.log(
                            "d",
                            "Dangling bounds: faces=%d vertices=%d min_y=%.3f max_y=%.3f max_center_y=%.3f",
                            len(region_faces_for_bounds),
                            int(region_vertex_mask.sum()),
                            float(min_bounds_world[1]),
                            float(max_bounds_world[1]),
                            max_center_y,
                        )

                    # Calculate region dimensions in local space
                    region_size = max_bounds - min_bounds

                    # Add padding around the region
                    padding_factor = 1.4
                    padding_factor_y = 1.4
                    if dangling_vertex_regions_active:
                        padding_factor = 1.15
                        padding_factor_y = 1.0
                    padded_size_x = float(region_size[0] * padding_factor)
                    padded_size_y = float(region_size[1] * padding_factor_y)
                    padded_size_z = float(region_size[2] * padding_factor)

                    # Ensure minimum size of 1mm
                    padded_size_x = max(1.0, padded_size_x)
                    padded_size_y = max(1.0, padded_size_y)
                    padded_size_z = max(1.0, padded_size_z)

                    if dangling_vertex_regions_active:
                        bottom_clearance = 0.01
                        top_clearance = 0.01
                        min_overlap = 0.005
                        overlap_slack = 0.02
                        horizontal_threshold = 0.95
                        build_plate_y = 0.0
                        if min_bounds_world is None or max_bounds_world is None:
                            _, bounds_world = self._calculateRegionBounds(vertices_world, indices, dangling_faces_full)
                            min_bounds_world, max_bounds_world = bounds_world
                        if min_bounds_world_faces is None or max_bounds_world_faces is None:
                            min_bounds_world_faces, max_bounds_world_faces = min_bounds_world, max_bounds_world
                        region_size_world_x = float(max_bounds_world_faces[0] - min_bounds_world_faces[0])
                        region_size_world_z = float(max_bounds_world_faces[2] - min_bounds_world_faces[2])
                        min_dangling_y = float(min_bounds_world[1])
                        base_bottom_y = max(build_plate_y, min_dangling_y - bottom_clearance)
                        position_world_x = (min_bounds_world_faces[0] + max_bounds_world_faces[0]) / 2.0
                        position_world_z = (min_bounds_world_faces[2] + max_bounds_world_faces[2]) / 2.0
                        shrink_attempts = 0
                        padded_size_x = max(1.0, float(region_size_world_x * padding_factor))
                        padded_size_z = max(1.0, float(region_size_world_z * padding_factor))
                        Logger.log(
                            "d",
                            "Dangling volume start: size=[%.2f, %.2f, %.2f] bottom_y=%.3f min_y=%.3f",
                            padded_size_x,
                            padded_size_y,
                            padded_size_z,
                            base_bottom_y,
                            min_dangling_y,
                        )
                        while shrink_attempts < 10:
                            min_x = position_world_x - (padded_size_x / 2.0)
                            max_x = position_world_x + (padded_size_x / 2.0)
                            min_z = position_world_z - (padded_size_z / 2.0)
                            max_z = position_world_z + (padded_size_z / 2.0)

                            inside_face_mask = (
                                (face_min_world[:, 0] <= max_x) & (face_max_world[:, 0] >= min_x) &
                                (face_min_world[:, 2] <= max_z) & (face_max_world[:, 2] >= min_z)
                            )
                            other_face_mask = inside_face_mask & ~region_face_mask
                            other_face_min_y = face_min_world[other_face_mask][:, 1]
                            other_face_max_y = face_max_world[other_face_mask][:, 1]
                            other_face_min_y_blocking = other_face_min_y
                            other_face_max_y_blocking = other_face_max_y
                            other_face_min_y_side = other_face_min_y
                            other_face_max_y_side = other_face_max_y
                            if other_face_min_y.size > 0:
                                other_face_normals_y = face_normals_world[other_face_mask][:, 1]
                                blocking_mask = numpy.abs(other_face_normals_y) >= horizontal_threshold
                                other_face_min_y_blocking = other_face_min_y[blocking_mask]
                                other_face_max_y_blocking = other_face_max_y[blocking_mask]
                                other_face_min_y_side = other_face_min_y[~blocking_mask]
                                other_face_max_y_side = other_face_max_y[~blocking_mask]
                            lower_limit = build_plate_y
                            upper_limit = float(mesh_max_y + top_clearance)
                            other_above_count = 0
                            other_below_count = 0
                            if other_face_min_y_blocking.size > 0:
                                other_above = other_face_min_y_blocking[other_face_min_y_blocking > (min_dangling_y + min_overlap)]
                                other_above_count = int(other_above.size)
                                if other_above.size > 0:
                                    upper_limit = min(upper_limit, float(other_above.min()) - top_clearance)
                                other_below = other_face_max_y_blocking[other_face_max_y_blocking < (min_dangling_y - min_overlap)]
                                other_below_count = int(other_below.size)
                                if other_below.size > 0:
                                    lower_limit = max(lower_limit, float(other_below.max()) + bottom_clearance)

                            bottom_y = max(base_bottom_y, lower_limit)
                            top_y = upper_limit

                            side_intrusion = 0
                            if other_face_min_y_side.size > 0:
                                mid_mask = (other_face_max_y_side > (bottom_y + 0.01)) & (other_face_min_y_side < (top_y - 0.01))
                                side_intrusion = int(numpy.count_nonzero(mid_mask))

                            if (side_intrusion == 0 and
                                    other_above_count == 0 and
                                    other_below_count == 0 and
                                    top_y >= (min_dangling_y + min_overlap - overlap_slack) and
                                    bottom_y <= (min_dangling_y - min_overlap + overlap_slack)):
                                if shrink_attempts == 0:
                                    Logger.log(
                                        "d",
                                        "Dangling volume settled: upper=%.3f lower=%.3f side=%d above=%d below=%d size=[%.2f, %.2f, %.2f]",
                                        upper_limit,
                                        lower_limit,
                                        side_intrusion,
                                        other_above_count,
                                        other_below_count,
                                        padded_size_x,
                                        padded_size_y,
                                        padded_size_z,
                                    )
                                break

                            new_size_x = max(region_size_world_x, padded_size_x * 0.85)
                            new_size_z = max(region_size_world_z, padded_size_z * 0.85)
                            if new_size_x == padded_size_x and new_size_z == padded_size_z:
                                if side_intrusion > 0 and other_face_min_y_side.size > 0:
                                    side_above_min = other_face_min_y_side[other_face_min_y_side > (bottom_y + 0.01)]
                                    if side_above_min.size > 0:
                                        top_y = min(top_y, float(side_above_min.min()) - top_clearance)
                                break
                            padded_size_x = new_size_x
                            padded_size_z = new_size_z
                            shrink_attempts += 1
                            Logger.log(
                                "d",
                                "Dangling shrink %d: upper=%.3f lower=%.3f side=%d above=%d below=%d size=[%.2f, %.2f, %.2f]",
                                shrink_attempts,
                                upper_limit,
                                lower_limit,
                                side_intrusion,
                                other_above_count,
                                other_below_count,
                                padded_size_x,
                                padded_size_y,
                                padded_size_z,
                            )

                        if top_y < (min_dangling_y + min_overlap - overlap_slack):
                            Logger.log(
                                "d",
                                "Skipping region %d: top below dangling min (top_y=%.3f min_y=%.3f)",
                                region_id + 1,
                                top_y,
                                min_dangling_y,
                            )
                            continue
                        if bottom_y > (min_dangling_y - min_overlap + overlap_slack):
                            Logger.log(
                                "d",
                                "Skipping region %d: bottom above dangling min (bottom_y=%.3f min_y=%.3f)",
                                region_id + 1,
                                bottom_y,
                                min_dangling_y,
                            )
                            continue
                        min_clearance = 0.005
                        if top_y <= bottom_y + min_clearance:
                            if top_y >= bottom_y - overlap_slack and top_y >= (bottom_y + min_clearance - overlap_slack):
                                top_y = bottom_y + min_clearance
                            else:
                                Logger.log(
                                    "d",
                                    "Skipping region %d: no vertical clearance (top_y=%.3f bottom_y=%.3f)",
                                    region_id + 1,
                                    top_y,
                                    bottom_y,
                                )
                                continue

                        padded_size_y = float(top_y - bottom_y)
                        position_world_y = bottom_y + (padded_size_y / 2.0)
                        Logger.log(
                            "d",
                            "Dangling volume final: size=[%.2f, %.2f, %.2f] top_y=%.3f bottom_y=%.3f attempts=%d",
                            padded_size_x,
                            padded_size_y,
                            padded_size_z,
                            top_y,
                            bottom_y,
                            shrink_attempts,
                        )
                    else:
                        # Position volume so its TOP aligns with the region's highest point
                        position_local_x = (min_bounds[0] + max_bounds[0]) / 2.0
                        position_local_y = max_bounds[1] - (padded_size_y / 2.0)
                        position_local_z = (min_bounds[2] + max_bounds[2]) / 2.0

                    if dangling_vertex_regions_active:
                        center_world = Vector(position_world_x, position_world_y, position_world_z)
                    else:
                        center_local_vec = Vector(position_local_x, position_local_y, position_local_z)
                        center_world = center_local_vec.preMultiply(world_transform)

                    # Calculate OBB for the region
                    region_vertices_local = vertices_local[numpy.unique(indices[region_faces_for_bounds].flatten())]
                    obb = geometry_utils.calculate_obb_pca(region_vertices_local)

                    # Check for collision
                    if geometry_utils.check_obb_mesh_collision(obb, vertices_local, indices, excluded_faces=set(region_faces)):
                        Logger.log("w", f"Region {region_id+1} OBB collides with the mesh, skipping.")
                        continue

                    # Create a support blocker sized to fit the region
                    self._createModifierVolumeWithSize(node, Vector(obb['center'][0], obb['center'][1], obb['center'][2]), obb['extents'][0] * 2, obb['extents'][1] * 2, obb['extents'][2] * 2, obb['rotation'])
                    created_count += 1
                    if total_regions > 0:
                        progress_value = 75 + int(20 * (processed_regions / total_regions))
                        self._updateProgress(
                            f"Created {created_count} of {total_regions} blockers...",
                            min(95, progress_value),
                        )

                    Logger.log("i", f"Created support blocker for region {region_id+1} ({len(region_faces)} faces) at world pos: [{center_world.x:.2f}, {center_world.y:.2f}, {center_world.z:.2f}], size: [{padded_size_x:.2f}, {padded_size_y:.2f}, {padded_size_z:.2f}]")

            Logger.log("i", f"=== CREATED {created_count} SUPPORT BLOCKERS ===")
            self._updateProgress(f"Created {created_count} support blockers.", 100)

        except Exception as e:
            Logger.log("e", f"Failed to auto-detect overhangs: {e}")
            import traceback
            Logger.log("e", traceback.format_exc())
        finally:
            self._closeProgress()

    def _rebuildIndexedMesh(self, vertices):
        """Rebuild index buffer for non-indexed mesh by merging duplicate vertices"""
        Logger.log("i", f"Rebuilding indices from {len(vertices)} vertices...")

        vertex_map = {}
        unique_vertices = []
        indices = []
        tolerance = 1e-4

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
        Logger.log("i", f"Vertex reduction: {reduction:.1f}% ({len(vertices)} â†’ {len(unique_vertices)})")

        return unique_vertices, indices

    def _getCachedMeshData(self, node: CuraSceneNode):
        mesh_data = node.getMeshData()
        if not mesh_data:
            return None

        cache_key = id(node)
        mesh_data_id = id(mesh_data)
        vertex_count = mesh_data.getVertexCount()
        cache = self._mesh_cache.get(cache_key)
        if cache and cache.get("mesh_data_id") == mesh_data_id and cache.get("vertex_count") == vertex_count:
            return cache

        vertices_local = mesh_data.getVertices()
        if vertices_local is None or len(vertices_local) == 0:
            return None

        reindexed = False
        if not mesh_data.hasIndices():
            Logger.log("i", "Non-indexed mesh detected, rebuilding indices...")
            vertices_local, indices = self._rebuildIndexedMesh(vertices_local)
            reindexed = True
        else:
            indices = mesh_data.getIndices()
            if self._meshNeedsIndexRebuild(vertices_local, indices):
                Logger.log("i", "Indexed mesh has no shared vertices; rebuilding indices for adjacency...")
                expanded_vertices = numpy.array(indices, dtype=numpy.int32).reshape(-1)
                vertices_local, indices = self._rebuildIndexedMesh(vertices_local[expanded_vertices])
                reindexed = True

        face_normals_from_mesh = None
        if mesh_data.hasNormals() and not reindexed:
            normals = mesh_data.getNormals()
            if normals is not None and len(normals) > 0:
                normals = numpy.array(normals, dtype=numpy.float32)
                if mesh_data.hasIndices():
                    if len(normals) == len(vertices_local):
                        face_normals_from_mesh = self._computeFaceNormalsFromVertexNormals(normals, indices)
                    elif len(normals) == len(indices):
                        face_normals_from_mesh = normals
                else:
                    if len(normals) == len(vertices_local):
                        face_normals_from_mesh = normals.reshape(-1, 3, 3).mean(axis=1)
                        lengths = numpy.linalg.norm(face_normals_from_mesh, axis=1, keepdims=True)
                        face_normals_from_mesh = face_normals_from_mesh / numpy.maximum(lengths, 1e-10)
                    elif len(normals) == len(indices):
                        face_normals_from_mesh = normals

        face_normals_geom = self._compute_face_normals(vertices_local, indices)
        face_centers_local = self._computeFaceCenters(vertices_local, indices)

        cache = {
            "mesh_data_id": mesh_data_id,
            "vertex_count": vertex_count,
            "vertices_local": vertices_local,
            "indices": indices,
            "reindexed": reindexed,
            "face_normals_from_mesh": face_normals_from_mesh,
            "face_normals_geom": face_normals_geom,
            "face_centers_local": face_centers_local,
            "face_adjacency": None,
            "vertex_adjacency": None,
        }
        self._mesh_cache[cache_key] = cache
        return cache

    def _getCachedFaceAdjacency(self, cache: dict):
        if cache["face_adjacency"] is None:
            cache["face_adjacency"] = self._buildAdjacencyGraph(cache["indices"])
        return cache["face_adjacency"]

    def _getCachedVertexAdjacency(self, cache: dict, vertex_count: int):
        if cache["vertex_adjacency"] is None:
            cache["vertex_adjacency"] = self._buildVertexAdjacency(cache["indices"], vertex_count)
        return cache["vertex_adjacency"]

    def _meshNeedsIndexRebuild(self, vertices, indices) -> bool:
        """Return True when indexed mesh has no shared vertices (triangle soup)."""
        if vertices is None or indices is None:
            return False
        if len(vertices) == 0 or len(indices) == 0:
            return False
        flat_indices = numpy.array(indices, dtype=numpy.int32).reshape(-1)
        if len(flat_indices) == 0:
            return False
        usage = numpy.bincount(flat_indices, minlength=len(vertices))
        return int(usage.max()) <= 1

    def _isFaceOverhang(self, vertices, indices, face_id, threshold_angle, transform=None):
        """Check if a single face is an overhang"""
        face = indices[face_id]
        v0 = vertices[face[0]]
        v1 = vertices[face[1]]
        v2 = vertices[face[2]]

        # Calculate normal
        edge1 = v1 - v0
        edge2 = v2 - v0
        normal_local = numpy.cross(edge1, edge2)
        normal_length = numpy.linalg.norm(normal_local)

        if normal_length < 1e-10:
            return False

        normal_local = normal_local / normal_length

        # Transform to world space if needed
        if transform:
            transform_data = transform.getData()
            rotation_matrix = transform_data[0:3, 0:3]
            normal_world = rotation_matrix.dot(normal_local)
            normal_world_length = numpy.linalg.norm(normal_world)
            if normal_world_length > 1e-10:
                normal = normal_world / normal_world_length
            else:
                normal = normal_local
        else:
            normal = normal_local

        # Check angle
        threshold_from_up = 90.0 + threshold_angle
        threshold_rad = numpy.deg2rad(threshold_from_up)
        up_vector = numpy.array([0.0, 1.0, 0.0])
        dot_product = numpy.dot(normal, up_vector)
        angle = numpy.arccos(numpy.clip(dot_product, -1.0, 1.0))

        return angle > threshold_rad

    def _buildAdjacencyGraph(self, indices):
        """Build adjacency graph for ALL faces (not just overhangs)"""
        edge_to_faces = {}

        for face_id, face in enumerate(indices):
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
        adjacency = {}
        for edge, faces in edge_to_faces.items():
            if len(faces) == 2:
                f1, f2 = faces
                if f1 not in adjacency:
                    adjacency[f1] = []
                if f2 not in adjacency:
                    adjacency[f2] = []
                adjacency[f1].append(f2)
                adjacency[f2].append(f1)

        return adjacency

    def _findNearbyOverhang(self, start_face_id, vertices, indices, adjacency, threshold_angle, transform, max_depth=3):
        """Search nearby faces for an overhang face using limited BFS

        Args:
            start_face_id: Face to start search from
            max_depth: Maximum neighbor levels to search (default 3)

        Returns:
            Face ID of nearest overhang face, or None if not found
        """
        visited = set()
        queue = [(start_face_id, 0)]  # (face_id, depth)
        visited.add(start_face_id)

        while queue:
            current_face, depth = queue.pop(0)

            # Check if current face is an overhang
            if self._isFaceOverhang(vertices, indices, current_face, threshold_angle, transform):
                return current_face

            # Continue searching neighbors if within depth limit
            if depth < max_depth:
                if current_face in adjacency:
                    for neighbor in adjacency[current_face]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, depth + 1))

        return None

    def _findConnectedOverhangRegion(self, start_face_id, vertices, indices, adjacency, threshold_angle, transform):
        """Find connected overhang region starting from a specific face using BFS"""
        region = []
        visited = set()
        queue = [start_face_id]
        visited.add(start_face_id)

        while queue:
            current_face = queue.pop(0)

            # Check if current face is an overhang
            if self._isFaceOverhang(vertices, indices, current_face, threshold_angle, transform):
                region.append(current_face)

                # Check neighbors
                if current_face in adjacency:
                    for neighbor in adjacency[current_face]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

        return region

    def _findConnectedOverhangRegionExpanded(self, start_face_id, vertices, indices, adjacency,
                                            threshold_angle, transform, angle_margin=10.0):
        """Find connected overhang region including near-threshold faces

        This is used for single-region mode to capture entire dangling features.
        It includes faces that are within angle_margin degrees of the support angle threshold,
        allowing it to capture complete features even when some faces are slightly above
        the strict overhang threshold.

        Args:
            start_face_id: Face to start BFS from
            vertices: Vertex positions in local space
            indices: Face indices
            adjacency: Face adjacency graph
            threshold_angle: Base support angle (e.g., 45Â°)
            transform: World transformation for normal rotation
            angle_margin: Degrees to expand beyond strict threshold (default 10Â°)

        Returns:
            List of face IDs forming the complete dangling feature
        """
        # Calculate expanded threshold
        # Normal threshold: 90 + 45 = 135Â° from up
        # With 10Â° margin: also include faces 125Â°-135Â° from up
        expanded_threshold = threshold_angle - angle_margin

        region = []
        visited = set()
        queue = [start_face_id]
        visited.add(start_face_id)

        while queue:
            current_face = queue.pop(0)

            # Check if face is overhang OR near-threshold (with expanded threshold)
            if self._isFaceNearOverhang(vertices, indices, current_face, expanded_threshold, transform):
                region.append(current_face)

                # Expand to neighbors
                if current_face in adjacency:
                    for neighbor in adjacency[current_face]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

        return region

    def _isFaceNearOverhang(self, vertices, indices, face_id, threshold_angle, transform=None):
        """Check if a face is at or near overhang threshold

        This uses a relaxed threshold to include faces that are close to needing support,
        helping to capture entire dangling features rather than just strict overhangs.

        Args:
            vertices: Vertex positions in local space
            indices: Face indices
            face_id: Face to check
            threshold_angle: Relaxed support angle (already reduced by angle_margin)
            transform: Optional transformation matrix to convert normals to world space

        Returns:
            True if face angle exceeds the relaxed threshold
        """
        face = indices[face_id]
        v0 = vertices[face[0]]
        v1 = vertices[face[1]]
        v2 = vertices[face[2]]

        # Calculate normal in local space
        edge1 = v1 - v0
        edge2 = v2 - v0
        normal_local = numpy.cross(edge1, edge2)
        normal_length = numpy.linalg.norm(normal_local)

        if normal_length < 1e-10:
            return False

        normal_local = normal_local / normal_length

        # Transform to world space if needed
        if transform:
            transform_data = transform.getData()
            rotation_matrix = transform_data[0:3, 0:3]
            normal_world = rotation_matrix.dot(normal_local)
            normal_world_length = numpy.linalg.norm(normal_world)
            if normal_world_length > 1e-10:
                normal = normal_world / normal_world_length
            else:
                normal = normal_local
        else:
            normal = normal_local

        # Check angle against relaxed threshold
        # Note: threshold_angle passed here is already (base_threshold - margin)
        threshold_from_up = 90.0 + threshold_angle
        threshold_rad = numpy.deg2rad(threshold_from_up)
        up_vector = numpy.array([0.0, 1.0, 0.0])
        dot_product = numpy.dot(normal, up_vector)
        angle = numpy.arccos(numpy.clip(dot_product, -1.0, 1.0))

        return angle > threshold_rad

    def _detectOverhangFaces(self, vertices, indices, threshold_angle, transform=None):
        """Detect faces that are overhangs based on angle threshold

        Args:
            vertices: Vertex positions (in local space if transform is provided)
            indices: Face indices
            threshold_angle: Angle threshold in degrees (Cura support angle - max overhang without support)
            transform: Optional transformation matrix to convert normals to world space
        """
        # Convert support angle to the angle from vertical
        # Support angle of 45Â° means surfaces up to 45Â° from horizontal are printable
        # This corresponds to normals at angles > (90Â° + 45Â°) = 135Â° from up vector
        threshold_from_up = 90.0 + threshold_angle
        threshold_rad = numpy.deg2rad(threshold_from_up)
        overhang_faces = []

        for face_id, face in enumerate(indices):
            # Get face vertices (in local space)
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            # Calculate face normal (in local space)
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal_local = numpy.cross(edge1, edge2)
            normal_length = numpy.linalg.norm(normal_local)

            if normal_length > 1e-10:
                normal_local = normal_local / normal_length

                # Transform normal to world space if transform is provided
                if transform:
                    # Get rotation matrix (3x3 upper-left of 4x4 transform matrix)
                    transform_data = transform.getData()
                    rotation_matrix = transform_data[0:3, 0:3]

                    # Apply rotation to normal (normals are direction vectors - no translation)
                    normal_world = rotation_matrix.dot(normal_local)

                    # Normalize after transformation
                    normal_world_length = numpy.linalg.norm(normal_world)
                    if normal_world_length > 1e-10:
                        normal = normal_world / normal_world_length
                    else:
                        normal = normal_local
                else:
                    normal = normal_local

                # Calculate angle with up vector (0, 1, 0) in world space
                up_vector = numpy.array([0.0, 1.0, 0.0])
                dot_product = numpy.dot(normal, up_vector)
                angle = numpy.arccos(numpy.clip(dot_product, -1.0, 1.0))

                # Check if angle exceeds threshold (surface normal points more down than threshold)
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
            queue = deque([start_face])
            visited.add(start_face)

            while queue:
                current_face = queue.popleft()
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


    def _detectSharpVertices(self, vertices, indices, curvature_threshold=2.0):
        """Detect vertices with high curvature (sharp points)

        Optimized version that uses average normal deviation instead of pairwise comparison.
        Much faster on large meshes.

        Args:
            vertices: Vertex positions in local space
            indices: Face indices
            curvature_threshold: Threshold for considering a vertex "sharp" (radians)
                                Higher values = only very sharp points detected
                                Default 2.0 radians (~115Â°) catches moderately sharp features

        Returns:
            List of vertex IDs that are sharp points
        """
        # Build vertex-to-faces mapping
        vertex_faces = {}
        for face_id, face in enumerate(indices):
            for vertex_id in face:
                if vertex_id not in vertex_faces:
                    vertex_faces[vertex_id] = []
                vertex_faces[vertex_id].append(face_id)

        sharp_vertices = []
        checked_count = 0

        # Calculate curvature at each vertex (optimized version)
        for vertex_id, face_list in vertex_faces.items():
            if len(face_list) < 3:
                continue

            checked_count += 1

            # Calculate normals for all faces touching this vertex
            normals = []
            for face_id in face_list:
                face = indices[face_id]
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]

                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = numpy.cross(edge1, edge2)
                normal_length = numpy.linalg.norm(normal)

                if normal_length > 1e-10:
                    normal = normal / normal_length
                    normals.append(normal)

            if len(normals) < 3:
                continue

            # OPTIMIZED: Calculate average normal, then find max deviation
            # This is O(n) instead of O(nÂ²)
            normals_array = numpy.array(normals)
            avg_normal = numpy.mean(normals_array, axis=0)
            avg_normal_length = numpy.linalg.norm(avg_normal)

            if avg_normal_length > 1e-10:
                avg_normal = avg_normal / avg_normal_length

                # Find maximum deviation from average
                max_deviation = 0.0
                for normal in normals:
                    dot_product = numpy.dot(normal, avg_normal)
                    angle = numpy.arccos(numpy.clip(dot_product, -1.0, 1.0))
                    max_deviation = max(max_deviation, angle)

                # Sharp vertex if normals deviate significantly from average
                if max_deviation > curvature_threshold / 2.0:  # Divide by 2 since we're comparing to average
                    sharp_vertices.append(vertex_id)

        Logger.log("i", f"Checked {checked_count} vertices, detected {len(sharp_vertices)} sharp vertices")
        return sharp_vertices

    def _expandRegionsWithSharpFeatures(self, vertices, indices, regions, sharp_vertices, expansion_radius=5.0):
        """Expand overhang regions to include faces around sharp vertices

        When sharp features are detected (like cone tips), include nearby faces
        in the overhang region even if they don't meet the strict angle threshold.

        Args:
            vertices: Vertex positions in local space
            indices: Face indices
            regions: List of overhang regions (each is a list of face IDs)
            sharp_vertices: List of sharp vertex IDs
            expansion_radius: Radius (mm) around sharp vertex to include faces

        Returns:
            Modified list of regions with additional faces around sharp vertices
        """
        if len(sharp_vertices) == 0:
            return regions

        # Build vertex-to-faces mapping
        vertex_faces = {}
        for face_id, face in enumerate(indices):
            for vertex_id in face:
                if vertex_id not in vertex_faces:
                    vertex_faces[vertex_id] = []
                vertex_faces[vertex_id].append(face_id)

        # For each sharp vertex, find nearby faces
        sharp_feature_faces = set()
        for vertex_id in sharp_vertices:
            sharp_vertex_pos = vertices[vertex_id]

            # Find all faces within expansion_radius of this sharp vertex
            for face_id, face in enumerate(indices):
                # Get face center
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]
                face_center = (v0 + v1 + v2) / 3.0

                # Check distance to sharp vertex
                distance = numpy.linalg.norm(face_center - sharp_vertex_pos)
                if distance < expansion_radius:
                    sharp_feature_faces.add(face_id)

        Logger.log("i", f"Found {len(sharp_feature_faces)} faces near sharp vertices")

        # Create new regions from sharp feature faces if they're not already in existing regions
        existing_face_set = set()
        for region in regions:
            existing_face_set.update(region)

        # Add unclaimed sharp feature faces as new regions
        unclaimed_sharp_faces = sharp_feature_faces - existing_face_set
        if len(unclaimed_sharp_faces) > 0:
            # Use BFS to find connected components of sharp feature faces
            visited = set()
            new_regions = []

            for start_face in unclaimed_sharp_faces:
                if start_face in visited:
                    continue

                # Build adjacency for sharp feature faces only
                adjacency = self._buildAdjacencyGraph(indices)

                # BFS to find connected sharp feature faces
                region = []
                queue = [start_face]
                visited.add(start_face)

                while queue:
                    current_face = queue.pop(0)
                    if current_face in unclaimed_sharp_faces:
                        region.append(current_face)

                        if current_face in adjacency:
                            for neighbor in adjacency[current_face]:
                                if neighbor not in visited and neighbor in unclaimed_sharp_faces:
                                    visited.add(neighbor)
                                    queue.append(neighbor)

                if len(region) >= 5:  # Minimum faces for a sharp feature region
                    new_regions.append(region)
                    Logger.log("i", f"Created new sharp feature region with {len(region)} faces")

            regions.extend(new_regions)

        return regions

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
        Logger.log(
            "i",
            "Manual detect settings: threshold=%.1f, sharp_features=%s, dangling_vertices=%s (angle-only)",
            float(self._overhang_threshold),
            str(self._detect_sharp_features),
            str(self._detect_dangling_vertices),
        )

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

    # =====================================================================
    # Phase 4: Refinement - Properties and Methods
    # =====================================================================

    def getColumnRadius(self) -> float:
        return self._column_radius

    def setColumnRadius(self, value: float) -> None:
        if value != self._column_radius:
            self._column_radius = max(0.5, min(10.0, float(value)))
            self.propertyChanged.emit()

    ColumnRadius = pyqtProperty(float, fget=getColumnRadius, fset=setColumnRadius)

    def getColumnTaper(self) -> float:
        return self._column_taper

    def setColumnTaper(self, value: float) -> None:
        if value != self._column_taper:
            self._column_taper = max(0.2, min(1.0, float(value)))
            self.propertyChanged.emit()

    ColumnTaper = pyqtProperty(float, fget=getColumnTaper, fset=setColumnTaper)

    def getRailWidth(self) -> float:
        return self._rail_width

    def setRailWidth(self, value: float) -> None:
        if value != self._rail_width:
            self._rail_width = max(0.3, min(5.0, float(value)))
            self.propertyChanged.emit()

    RailWidth = pyqtProperty(float, fget=getRailWidth, fset=setRailWidth)

    def _find_obstruction_height(self, x: float, z: float, max_y: float,
                                   node: CuraSceneNode) -> float:
        """Find the highest point on the model below a given position.

        This is used for model-to-model support when there's geometry
        between the overhang and the build plate.

        Args:
            x: X coordinate to check
            z: Z coordinate to check
            max_y: Maximum Y (don't look above this)
            node: The model node to check against

        Returns:
            Y coordinate of the highest obstruction, or 0.0 if clear to build plate
        """
        mesh_data = node.getMeshData()
        if not mesh_data:
            return 0.0

        transformed_mesh = mesh_data.getTransformed(node.getWorldTransformation())
        vertices = transformed_mesh.getVertices()

        if transformed_mesh.hasIndices():
            indices = transformed_mesh.getIndices()
        else:
            indices = numpy.arange(len(vertices)).reshape(-1, 3)

        # Check each triangle for intersection with vertical ray at (x, z)
        highest_y = 0.0
        tolerance = 0.5  # mm - how close the ray needs to pass to count

        for face in indices:
            v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

            # Quick bounding box check
            min_x = min(v0[0], v1[0], v2[0]) - tolerance
            max_x = max(v0[0], v1[0], v2[0]) + tolerance
            min_z = min(v0[2], v1[2], v2[2]) - tolerance
            max_z = max(v0[2], v1[2], v2[2]) + tolerance

            if x < min_x or x > max_x or z < min_z or z > max_z:
                continue

            # Check if point (x, z) is inside triangle projection
            # Using barycentric coordinates
            denom = (v1[2] - v2[2]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[2] - v2[2])
            if abs(denom) < 1e-10:
                continue

            a = ((v1[2] - v2[2]) * (x - v2[0]) + (v2[0] - v1[0]) * (z - v2[2])) / denom
            b = ((v2[2] - v0[2]) * (x - v2[0]) + (v0[0] - v2[0]) * (z - v2[2])) / denom
            c = 1.0 - a - b

            # Allow some tolerance for edge cases
            if a >= -0.1 and b >= -0.1 and c >= -0.1:
                # Interpolate Y at this point
                y = a * v0[1] + b * v1[1] + c * v2[1]

                # Only count if below max_y (with gap)
                if y < max_y - 0.5 and y > highest_y:
                    highest_y = y

        return highest_y

    def _merge_nearby_edges(self, edges: List[Tuple[numpy.ndarray, numpy.ndarray]],
                             merge_distance: float = 1.0) -> List[Tuple[numpy.ndarray, numpy.ndarray]]:
        """Merge nearby boundary edges into longer continuous edges.

        This reduces the number of individual rail meshes and creates
        cleaner support structures.

        Args:
            edges: List of (start, end) vertex pairs
            merge_distance: Maximum distance between edge endpoints to merge

        Returns:
            List of merged edges
        """
        if len(edges) <= 1:
            return edges

        # Build a graph of connected edges
        merged = []
        used = set()

        for i, (start1, end1) in enumerate(edges):
            if i in used:
                continue

            # Start a chain with this edge
            chain_start = start1.copy()
            chain_end = end1.copy()
            used.add(i)

            # Try to extend the chain
            changed = True
            while changed:
                changed = False
                for j, (start2, end2) in enumerate(edges):
                    if j in used:
                        continue

                    # Check if this edge connects to our chain
                    dist_start_start = numpy.linalg.norm(chain_start - start2)
                    dist_start_end = numpy.linalg.norm(chain_start - end2)
                    dist_end_start = numpy.linalg.norm(chain_end - start2)
                    dist_end_end = numpy.linalg.norm(chain_end - end2)

                    min_dist = min(dist_start_start, dist_start_end, dist_end_start, dist_end_end)

                    if min_dist < merge_distance:
                        used.add(j)
                        changed = True

                        # Extend the chain appropriately
                        if dist_end_start < merge_distance:
                            chain_end = end2.copy()
                        elif dist_end_end < merge_distance:
                            chain_end = start2.copy()
                        elif dist_start_start < merge_distance:
                            chain_start = end2.copy()
                        elif dist_start_end < merge_distance:
                            chain_start = start2.copy()

            # Calculate merged edge length
            edge_length = numpy.linalg.norm(chain_end - chain_start)
            if edge_length >= self._rail_min_length:
                merged.append((chain_start, chain_end))

        Logger.log("d", f"Merged {len(edges)} edges into {len(merged)} chains")
        return merged

    def _create_tip_column_mesh_v2(self, tip_position: numpy.ndarray,
                                    base_y: float = 0.0,
                                    column_radius: float = None,
                                    taper: float = None,
                                    sides: int = None) -> MeshBuilder:
        """Create a support column from tip to specified base height.

        Enhanced version that supports model-to-model support.

        Args:
            tip_position: Position of the tip (numpy array [x, y, z])
            base_y: Y coordinate for the column base (0 = build plate)
            column_radius: Radius at base (uses self._column_radius if None)
            taper: Taper factor (uses self._column_taper if None)
            sides: Number of sides (uses self._column_sides if None)

        Returns:
            MeshBuilder with the column geometry
        """
        mesh = MeshBuilder()

        # Use instance defaults if not specified
        if column_radius is None:
            column_radius = self._column_radius
        if taper is None:
            taper = self._column_taper
        if sides is None:
            sides = self._column_sides

        tip_y = tip_position[1]
        if tip_y <= base_y:
            Logger.log("w", f"Tip ({tip_y}) is at or below base ({base_y}), cannot create column")
            return mesh

        # Column parameters
        height = tip_y - base_y
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

        # Bottom cap faces
        for i in range(sides):
            next_i = (i + 1) % sides
            indices.append([bottom_center_idx, bottom_start_idx + next_i, bottom_start_idx + i])

        # Top cap faces
        for i in range(sides):
            next_i = (i + 1) % sides
            indices.append([top_center_idx, top_start_idx + i, top_start_idx + next_i])

        # Side faces
        for i in range(sides):
            next_i = (i + 1) % sides
            b1 = bottom_start_idx + i
            b2 = bottom_start_idx + next_i
            t1 = top_start_idx + i
            t2 = top_start_idx + next_i
            indices.append([b1, t1, b2])
            indices.append([b2, t1, t2])

        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))
        mesh.calculateNormals()

        return mesh

    def _create_edge_rail_mesh_v2(self, edge_start: numpy.ndarray, edge_end: numpy.ndarray,
                                   base_y: float = 0.0,
                                   rail_width: float = None) -> MeshBuilder:
        """Create an edge rail mesh with configurable base height.

        Enhanced version supporting model-to-model support.

        Args:
            edge_start: Start vertex of the edge
            edge_end: End vertex of the edge
            base_y: Y coordinate for rail base (0 = build plate)
            rail_width: Width of the rail (uses self._rail_width if None)

        Returns:
            MeshBuilder with the rail geometry
        """
        mesh = MeshBuilder()

        if rail_width is None:
            rail_width = self._rail_width

        edge_vec = edge_end - edge_start
        edge_length = numpy.linalg.norm(edge_vec)

        if edge_length < 0.1:
            return mesh

        edge_dir = edge_vec / edge_length

        # Calculate perpendicular direction
        up = numpy.array([0.0, 1.0, 0.0])
        perp_dir = numpy.cross(edge_dir, up)
        perp_length = numpy.linalg.norm(perp_dir)

        if perp_length < 0.01:
            perp_dir = numpy.array([1.0, 0.0, 0.0])
        else:
            perp_dir = perp_dir / perp_length

        # Determine rail height
        edge_min_y = min(edge_start[1], edge_end[1])
        edge_max_y = max(edge_start[1], edge_end[1])

        if edge_min_y <= base_y:
            Logger.log("w", "Edge is at or below base, cannot create rail")
            return mesh

        # Rail dimensions
        half_width = rail_width / 2
        half_length = edge_length / 2

        edge_center = (edge_start + edge_end) / 2
        rail_height = edge_min_y - base_y
        rail_center_y = base_y + rail_height / 2

        # Build vertices
        verts = []
        for dy in [-rail_height / 2, rail_height / 2]:
            for dw in [-half_width, half_width]:
                for dl in [-half_length, half_length]:
                    vert = numpy.array([edge_center[0], rail_center_y, edge_center[2]])
                    vert[1] += dy
                    vert += perp_dir * dw
                    vert += edge_dir * dl
                    verts.append([vert[0], vert[1], vert[2]])

        face_indices = [
            [0, 1, 3], [0, 3, 2],  # Bottom
            [4, 7, 5], [4, 6, 7],  # Top
            [0, 4, 5], [0, 5, 1],  # Front
            [2, 3, 7], [2, 7, 6],  # Back
            [0, 2, 6], [0, 6, 4],  # Left
            [1, 5, 7], [1, 7, 3],  # Right
        ]

        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))
        mesh.setIndices(numpy.asarray(face_indices, dtype=numpy.int32))
        mesh.calculateNormals()

        return mesh

    def createCustomSupportMeshV2(self, support_type: str = "auto"):
        """Create custom support mesh with Phase 4 refinements.

        Includes obstruction detection, edge merging, and configurable dimensions.
        """
        selected_node = Selection.getSelectedObject(0)
        if not selected_node:
            Logger.log("w", "No object selected")
            return

        if not self._detected_overhangs:
            Logger.log("w", "No overhangs detected. Run detection first.")
            return

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

        Logger.log("i", f"Creating refined support meshes (type: {support_type})")

        rails_created = 0
        columns_created = 0

        for i, region in enumerate(self._detected_overhangs):
            region_type = region["type"]

            # Create tip column for tip regions
            if region_type == "tip" and support_type in ["auto", "tip_column"]:
                region_vertices = region["vertices"]
                if len(region_vertices) > 0:
                    min_y_idx = numpy.argmin(region_vertices[:, 1])
                    tip_pos = region_vertices[min_y_idx]

                    # Check for obstructions
                    obstruction_y = self._find_obstruction_height(
                        tip_pos[0], tip_pos[2], tip_pos[1], selected_node
                    )

                    base_y = obstruction_y if obstruction_y > 0 else 0.0

                    if obstruction_y > 0:
                        Logger.log("d", f"Column {i}: Found obstruction at Y={obstruction_y:.2f}")

                    column_mesh = self._create_tip_column_mesh_v2(
                        tip_pos,
                        base_y=base_y,
                        column_radius=self._column_radius,
                        taper=self._column_taper,
                        sides=self._column_sides
                    )

                    if column_mesh.getVertexCount() > 0:
                        name = f"Tip Column {i}"
                        if obstruction_y > 0:
                            name += f" (on model @ {obstruction_y:.1f}mm)"
                        self._create_support_mesh_node(column_mesh, name, selected_node)
                        columns_created += 1

            # Create edge rails for boundary regions
            if region_type == "boundary" and support_type in ["auto", "edge_rail"]:
                boundary_edges = self._find_boundary_edges(
                    region["face_ids"], overhang_mask,
                    self._overhang_adjacency, indices, vertices
                )

                # Merge nearby edges
                merged_edges = self._merge_nearby_edges(boundary_edges, self._merge_edge_distance)

                for j, (edge_start, edge_end) in enumerate(merged_edges):
                    edge_center_y = (edge_start[1] + edge_end[1]) / 2
                    edge_center_x = (edge_start[0] + edge_end[0]) / 2
                    edge_center_z = (edge_start[2] + edge_end[2]) / 2

                    # Check for obstructions
                    obstruction_y = self._find_obstruction_height(
                        edge_center_x, edge_center_z, edge_center_y, selected_node
                    )

                    base_y = obstruction_y if obstruction_y > 0 else 0.0

                    rail_mesh = self._create_edge_rail_mesh_v2(
                        edge_start, edge_end,
                        base_y=base_y,
                        rail_width=self._rail_width
                    )

                    if rail_mesh.getVertexCount() > 0:
                        name = f"Edge Rail {i}-{j}"
                        if obstruction_y > 0:
                            name += f" (on model)"
                        self._create_support_mesh_node(rail_mesh, name, selected_node)
                        rails_created += 1

        Logger.log("i", f"Refined support creation complete: "
                      f"{columns_created} columns, {rails_created} rails")
