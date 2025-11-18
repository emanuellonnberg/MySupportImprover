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
            
            // Only apply preset values if not using custom values
            if (!UM.ActiveTool.properties.getValue("IsCustom")) {
                var currentPreset = UM.ActiveTool.properties.getValue("CurrentPreset")
                if (currentPreset && UM.ActiveTool.properties.getValue("Presets")) {
                    var presets = UM.ActiveTool.properties.getValue("Presets")
                    if (presets[currentPreset]) {
                        var preset = presets[currentPreset]
                        xSlider.value = parseFloat(preset.x)
                        ySlider.value = parseFloat(preset.y)
                        zSlider.value = parseFloat(preset.z)
                        xInput.text = preset.x.toFixed(1)
                        yInput.text = preset.y.toFixed(1)
                        zInput.text = preset.z.toFixed(1)
                    }
                }
            }
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
                model: {
                    if (UM.ActiveTool && UM.ActiveTool.properties.getValue("Presets")) {
                        var presets = Object.keys(UM.ActiveTool.properties.getValue("Presets"))
                        if (UM.ActiveTool.properties.getValue("IsCustom")) {
                            presets.push("Custom")
                        }
                        return presets
                    }
                    return []
                }
                currentIndex: {
                    if (UM.ActiveTool) {
                        if (UM.ActiveTool.properties.getValue("IsCustom")) {
                            return model.indexOf("Custom")
                        }
                        var presetName = UM.ActiveTool.properties.getValue("CurrentPreset")
                        var index = model.indexOf(presetName)
                        return index >= 0 ? index : 0
                    }
                    return 0
                }
                onActivated: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.triggerActionWithData("applyPreset", currentText)
                    }
                }
            }
        }

        // Save Preset Row - only visible in custom mode
        Row {
            id: savePresetRow
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("IsCustom")
            height: visible ? implicitHeight : 0

            TextField {
                id: presetNameField
                width: 120
                height: UM.Theme.getSize("setting_control").height
                placeholderText: catalog.i18nc("@label", "Preset name")
                validator: RegularExpressionValidator {
                    regularExpression: /^[a-zA-Z0-9\- ]+$/
                }
            }

            Button {
                id: savePresetButton
                width: 70
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@button", "Save")
                enabled: presetNameField.text.length > 0
                onClicked: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.triggerActionWithData("savePreset", presetNameField.text)
                        presetNameField.text = ""  // Clear the field after saving
                    }
                }
            }
        }

        // Single Region Mode Checkbox
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            CheckBox {
                id: singleRegionCheckbox
                height: UM.Theme.getSize("setting_control").height
                checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SingleRegion") : false
                onToggled: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.setProperty("SingleRegion", checked)
                        // Disable other modes when single region is enabled
                        if (checked) {
                            if (UM.ActiveTool.properties.getValue("AutoDetect")) {
                                UM.ActiveTool.setProperty("AutoDetect", false)
                            }
                            if (UM.ActiveTool.properties.getValue("ExportMode")) {
                                UM.ActiveTool.setProperty("ExportMode", false)
                            }
                        }
                    }
                }

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    x: singleRegionCheckbox.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 3
                    border.color: singleRegionCheckbox.down ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    border.width: 1
                    color: "transparent"

                    Rectangle {
                        width: 12
                        height: 12
                        x: 4
                        y: 4
                        radius: 2
                        color: UM.Theme.getColor("primary")
                        visible: singleRegionCheckbox.checked
                    }
                }

                contentItem: Label {
                    text: catalog.i18nc("@label", "Single Region (Fast)")
                    font: UM.Theme.getFont("default")
                    color: singleRegionCheckbox.checked ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: singleRegionCheckbox.indicator.width + singleRegionCheckbox.spacing
                }
            }
        }

        // Auto Detect All Regions Checkbox
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            CheckBox {
                id: autoDetectCheckbox
                height: UM.Theme.getSize("setting_control").height
                checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("AutoDetect") : false
                onToggled: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.setProperty("AutoDetect", checked)
                        // Disable other modes when auto-detect is enabled
                        if (checked) {
                            if (UM.ActiveTool.properties.getValue("SingleRegion")) {
                                UM.ActiveTool.setProperty("SingleRegion", false)
                            }
                            if (UM.ActiveTool.properties.getValue("ExportMode")) {
                                UM.ActiveTool.setProperty("ExportMode", false)
                            }
                        }
                    }
                }

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    x: autoDetectCheckbox.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 3
                    border.color: autoDetectCheckbox.down ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    border.width: 1
                    color: "transparent"

                    Rectangle {
                        width: 12
                        height: 12
                        x: 4
                        y: 4
                        radius: 2
                        color: UM.Theme.getColor("primary")
                        visible: autoDetectCheckbox.checked
                    }
                }

                contentItem: Label {
                    text: catalog.i18nc("@label", "Auto-Detect All Regions")
                    font: UM.Theme.getFont("default")
                    color: autoDetectCheckbox.checked ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: autoDetectCheckbox.indicator.width + autoDetectCheckbox.spacing
                }
            }
        }

        // Sharp Feature Detection Checkbox
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            CheckBox {
                id: sharpFeaturesCheckbox
                height: UM.Theme.getSize("setting_control").height
                checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("DetectSharpFeatures") : false
                onToggled: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.setProperty("DetectSharpFeatures", checked)
                    }
                }

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    x: sharpFeaturesCheckbox.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 3
                    border.color: sharpFeaturesCheckbox.down ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    border.width: 1
                    color: "transparent"

                    Rectangle {
                        width: 12
                        height: 12
                        x: 4
                        y: 4
                        radius: 2
                        color: UM.Theme.getColor("primary")
                        visible: sharpFeaturesCheckbox.checked
                    }
                }

                contentItem: Label {
                    text: catalog.i18nc("@label", "Detect Sharp Features (auto-detect mode)")
                    font: UM.Theme.getFont("default")
                    color: sharpFeaturesCheckbox.checked ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: sharpFeaturesCheckbox.indicator.width + sharpFeaturesCheckbox.spacing
                }
            }
        }

        // Export Mode Checkbox
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            CheckBox {
                id: exportModeCheckbox
                height: UM.Theme.getSize("setting_control").height
                checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("ExportMode") : false
                onToggled: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.setProperty("ExportMode", checked)
                        // Disable other modes when export mode is enabled
                        if (checked) {
                            if (UM.ActiveTool.properties.getValue("AutoDetect")) {
                                UM.ActiveTool.setProperty("AutoDetect", false)
                            }
                            if (UM.ActiveTool.properties.getValue("SingleRegion")) {
                                UM.ActiveTool.setProperty("SingleRegion", false)
                            }
                        }
                    }
                }

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    x: exportModeCheckbox.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 3
                    border.color: exportModeCheckbox.down ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    border.width: 1
                    color: "transparent"

                    Rectangle {
                        width: 12
                        height: 12
                        x: 4
                        y: 4
                        radius: 2
                        color: UM.Theme.getColor("primary")
                        visible: exportModeCheckbox.checked
                    }
                }

                contentItem: Label {
                    text: catalog.i18nc("@label", "Export Mode (click to save mesh data)")
                    font: UM.Theme.getFont("default")
                    color: exportModeCheckbox.checked ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: exportModeCheckbox.indicator.width + exportModeCheckbox.spacing
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
                    value: {
                        if (UM.ActiveTool) {
                            var currentPreset = UM.ActiveTool.properties.getValue("CurrentPreset")
                            var presets = UM.ActiveTool.properties.getValue("Presets")
                            if (currentPreset && presets && presets[currentPreset]) {
                                return parseFloat(presets[currentPreset].x)
                            }
                            return UM.ActiveTool.properties.getValue("CubeX")
                        }
                        return defaultX
                    }
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
                    value: {
                        if (UM.ActiveTool) {
                            var currentPreset = UM.ActiveTool.properties.getValue("CurrentPreset")
                            var presets = UM.ActiveTool.properties.getValue("Presets")
                            if (currentPreset && presets && presets[currentPreset]) {
                                return parseFloat(presets[currentPreset].y)
                            }
                            return UM.ActiveTool.properties.getValue("CubeY")
                        }
                        return defaultY
                    }
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
                    value: {
                        if (UM.ActiveTool) {
                            var currentPreset = UM.ActiveTool.properties.getValue("CurrentPreset")
                            var presets = UM.ActiveTool.properties.getValue("Presets")
                            if (currentPreset && presets && presets[currentPreset]) {
                                return parseFloat(presets[currentPreset].z)
                            }
                            return UM.ActiveTool.properties.getValue("CubeZ")
                        }
                        return defaultZ
                    }
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

            // Support Angle controls
            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Support Angle")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
                width: Math.ceil(contentWidth)
            }

            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
                
                Slider {
                    id: angleSlider
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.0
                    to: 90.0
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportAngle") : 45.0
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("SupportAngle", value)
                            angleInput.text = value.toFixed(1)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    id: angleInput
                    width: 70
                    height: UM.Theme.getSize("setting_control").height
                    unit: "°"
                    text: angleSlider.value.toFixed(1)
                    validator: DoubleValidator {
                        decimals: 1
                        bottom: 0.0
                        top: 90.0
                        locale: "en_US"
                    }
                    onEditingFinished: {
                        if (UM.ActiveTool) {
                            var modified_text = text.replace(",", ".")
                            var value = parseFloat(modified_text)
                            if (!isNaN(value)) {
                                UM.ActiveTool.setProperty("SupportAngle", value)
                                angleSlider.value = value
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