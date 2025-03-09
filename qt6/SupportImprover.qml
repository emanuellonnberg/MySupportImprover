// Copyright (c) 2024 Emanuel Lönnberg.
// This tool is released under the terms of the LGPLv3 or higher.

import QtQuick 6.0
import QtQuick.Controls 6.0

import UM 1.6 as UM
import Cura 1.0 as Cura

Item {
    id: base
    width: childrenRect.width
    height: childrenRect.height

    UM.I18nCatalog { id: catalog; name: "mysupportimprover" }

    property real defaultX: 3.0
    property real defaultY: 3.0
    property real defaultZ: 3.0

    // Properties to track current values with proper default handling
    property real currentX: UM.ActiveTool && UM.ActiveTool.properties.cubeX !== undefined ? UM.ActiveTool.properties.cubeX : defaultX
    property real currentY: UM.ActiveTool && UM.ActiveTool.properties.cubeY !== undefined ? UM.ActiveTool.properties.cubeY : defaultY
    property real currentZ: UM.ActiveTool && UM.ActiveTool.properties.cubeZ !== undefined ? UM.ActiveTool.properties.cubeZ : defaultZ

    Component.onCompleted: {
        console.log("Support Improver QML loaded")
        if (UM.ActiveTool) {
            console.log("Tool active")
            console.log("Initial values - X:", currentX, "Y:", currentY, "Z:", currentZ)
        }
    }

    Grid {
        id: mainGrid
        anchors.leftMargin: UM.Theme.getSize("default_margin").width
        anchors.top: parent.top

        columns: 2
        flow: Grid.LeftToRight
        spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

        Label {
            height: UM.Theme.getSize("setting_control").height
            text: catalog.i18nc("@label", "Width (X)")
            font: UM.Theme.getFont("default")
            color: UM.Theme.getColor("text")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
            width: Math.ceil(contentWidth)
        }

        UM.TextFieldWithUnit {
            id: xInput
            width: 70
            height: UM.Theme.getSize("setting_control").height
            unit: "mm"
            text: UM.ActiveTool.properties.getValue("CubeX")
            validator: DoubleValidator {
                decimals: 1
                bottom: 1.0
                top: 100.0
                locale: "en_US"
            }
            onEditingFinished: {
                if (UM.ActiveTool) {
                    console.log("Setting CubeX value to:", text)
                    var modified_text = text.replace(",", ".")
                    var value = parseFloat(modified_text)
                    if (!isNaN(value)) {
                        UM.ActiveTool.setProperty("CubeX", value)
                        base.currentX = value
                    }
                }
            }
        }

        Label {
            height: UM.Theme.getSize("setting_control").height
            text: catalog.i18nc("@label", "Depth (Y)")
            font: UM.Theme.getFont("default")
            color: UM.Theme.getColor("text")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
            width: Math.ceil(contentWidth)
        }

        UM.TextFieldWithUnit {
            id: yInput
            width: 70
            height: UM.Theme.getSize("setting_control").height
            unit: "mm"
            text: UM.ActiveTool.properties.getValue("CubeY")
            validator: DoubleValidator {
                decimals: 1
                bottom: 1.0
                top: 100.0
                locale: "en_US"
            }
            onEditingFinished: {
                if (UM.ActiveTool) {
                    console.log("Setting CubeY value to:", text)
                    var modified_text = text.replace(",", ".")
                    var value = parseFloat(modified_text)
                    if (!isNaN(value)) {
                        UM.ActiveTool.setProperty("CubeY", value)
                        base.currentY = value
                    }
                }
            }
        }

        Label {
            height: UM.Theme.getSize("setting_control").height
            text: catalog.i18nc("@label", "Height (Z)")
            font: UM.Theme.getFont("default")
            color: UM.Theme.getColor("text")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
            width: Math.ceil(contentWidth)
        }

        UM.TextFieldWithUnit {
            id: zInput
            width: 70
            height: UM.Theme.getSize("setting_control").height
            unit: "mm"
            text: UM.ActiveTool.properties.getValue("CubeZ")
            validator: DoubleValidator {
                decimals: 1
                bottom: 1.0
                top: 100.0
                locale: "en_US"
            }
            onEditingFinished: {
                if (UM.ActiveTool) {
                    console.log("Setting CubeZ value to:", text)
                    var modified_text = text.replace(",", ".")
                    var value = parseFloat(modified_text)
                    if (!isNaN(value)) {
                        UM.ActiveTool.setProperty("CubeZ", value)
                        base.currentZ = value
                    }
                }
            }
        }

    }

    Connections {
        target: UM.ActiveTool
        function onPropertiesChanged() {
            console.log("Properties changed in tool")
            if (UM.ActiveTool) {
                if (UM.ActiveTool.properties.cubeX !== undefined) {
                    base.currentX = UM.ActiveTool.properties.cubeX
                }
                if (UM.ActiveTool.properties.cubeY !== undefined) {
                    base.currentY = UM.ActiveTool.properties.cubeY
                }
                if (UM.ActiveTool.properties.cubeZ !== undefined) {
                    base.currentZ = UM.ActiveTool.properties.cubeZ
                }
            }
        }
    }
} 