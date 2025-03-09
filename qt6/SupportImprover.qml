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

    Column {
        id: mainColumn
        spacing: UM.Theme.getSize("default_margin").height
        
        // Remove anchors from Column
        width: mainGrid.width + UM.Theme.getSize("default_margin").width * 2

        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
            
            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Presets:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }

            ComboBox {
                id: presetComboBox
                width: 120
                height: UM.Theme.getSize("setting_control").height
                model: UM.ActiveTool && UM.ActiveTool.properties.getValue("Presets") ? Object.keys(UM.ActiveTool.properties.getValue("Presets")) : []
                onActivated: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.triggerActionWithData("applyPreset", currentText)
                    }
                }
            }
        }

        Grid {
            id: mainGrid
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

            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
                
                Slider {
                    id: xSlider
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    from: 1.0
                    to: 100.0
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("CubeX") : defaultX
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("CubeX", value)
                            xInput.text = value.toFixed(1)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    id: xInput
                    width: 70
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: xSlider.value.toFixed(1)
                    validator: DoubleValidator {
                        decimals: 1
                        bottom: 1.0
                        top: 100.0
                        locale: "en_US"
                    }
                    onEditingFinished: {
                        if (UM.ActiveTool) {
                            var modified_text = text.replace(",", ".")
                            var value = parseFloat(modified_text)
                            if (!isNaN(value)) {
                                UM.ActiveTool.setProperty("CubeX", value)
                                xSlider.value = value
                            }
                        }
                    }
                }
            }

            // Y dimension controls
            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Depth (Y)")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
                width: Math.ceil(contentWidth)
            }

            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
                
                Slider {
                    id: ySlider
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    from: 1.0
                    to: 100.0
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("CubeY") : defaultY
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("CubeY", value)
                            yInput.text = value.toFixed(1)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    id: yInput
                    width: 70
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: ySlider.value.toFixed(1)
                    validator: DoubleValidator {
                        decimals: 1
                        bottom: 1.0
                        top: 100.0
                        locale: "en_US"
                    }
                    onEditingFinished: {
                        if (UM.ActiveTool) {
                            var modified_text = text.replace(",", ".")
                            var value = parseFloat(modified_text)
                            if (!isNaN(value)) {
                                UM.ActiveTool.setProperty("CubeY", value)
                                ySlider.value = value
                            }
                        }
                    }
                }
            }

            // Z dimension controls
            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Height (Z)")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
                width: Math.ceil(contentWidth)
            }

            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
                
                Slider {
                    id: zSlider
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    from: 1.0
                    to: 100.0
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("CubeZ") : defaultZ
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("CubeZ", value)
                            zInput.text = value.toFixed(1)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    id: zInput
                    width: 70
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: zSlider.value.toFixed(1)
                    validator: DoubleValidator {
                        decimals: 1
                        bottom: 1.0
                        top: 100.0
                        locale: "en_US"
                    }
                    onEditingFinished: {
                        if (UM.ActiveTool) {
                            var modified_text = text.replace(",", ".")
                            var value = parseFloat(modified_text)
                            if (!isNaN(value)) {
                                UM.ActiveTool.setProperty("CubeZ", value)
                                zSlider.value = value
                            }
                        }
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