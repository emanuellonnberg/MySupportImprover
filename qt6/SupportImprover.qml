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

        // Support Mode Selection
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Support Mode:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }

            ComboBox {
                id: supportModeComboBox
                width: 150
                height: UM.Theme.getSize("setting_control").height
                model: ["Structural (Dense)", "Stability (Minimal)", "Attached Wing", "Custom"]
                currentIndex: {
                    if (UM.ActiveTool) {
                        var mode = UM.ActiveTool.properties.getValue("SupportMode")
                        if (mode === "structural") return 0
                        if (mode === "stability") return 1
                        if (mode === "wing") return 2
                        if (mode === "custom") return 3
                    }
                    return 0
                }
                onActivated: {
                    if (UM.ActiveTool) {
                        var modeMap = ["structural", "stability", "wing", "custom"]
                        UM.ActiveTool.setProperty("SupportMode", modeMap[currentIndex])
                    }
                }
            }
        }

        // Support Mode Description
        Label {
            width: parent.width
            height: UM.Theme.getSize("setting_control").height
            text: {
                if (UM.ActiveTool) {
                    var mode = UM.ActiveTool.properties.getValue("SupportMode")
                    if (mode === "structural") return "Dense support for load-bearing areas"
                    if (mode === "stability") return "Minimal support for edge stabilization"
                    if (mode === "wing") return "Attached wing extending to build plate"
                    if (mode === "custom") return "Custom support settings"
                }
                return ""
            }
            font: UM.Theme.getFont("default_italic")
            color: UM.Theme.getColor("text_inactive")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
        }

        // Separator
        Rectangle {
            width: parent.width
            height: 1
            color: UM.Theme.getColor("lining")
        }

        // =====================================================
        // Automatic Overhang Detection Section
        // =====================================================
        Column {
            id: overhangDetectionSection
            spacing: Math.round(UM.Theme.getSize("default_margin").height / 2)
            width: parent.width

            Label {
                text: catalog.i18nc("@label", "Automatic Detection:")
                font: UM.Theme.getFont("default_bold")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            // Overhang Threshold
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Detection Angle:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                Slider {
                    id: overhangThresholdSlider
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    from: 20.0
                    to: 70.0
                    stepSize: 5.0
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("OverhangThreshold") : 45.0
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("OverhangThreshold", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 55
                    height: UM.Theme.getSize("setting_control").height
                    unit: "°"
                    text: overhangThresholdSlider.value.toFixed(0)
                    validator: DoubleValidator { bottom: 20; top: 70; decimals: 0 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("OverhangThreshold", value)
                            overhangThresholdSlider.value = value
                        }
                    }
                }
            }

            // Detection Buttons Row
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Button {
                    id: detectOverhangsButton
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@button", "Detect Overhangs")
                    onClicked: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.triggerAction("detectOverhangsOnSelection")
                        }
                    }
                }

                Button {
                    id: createSupportButton
                    width: 120
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@button", "Create Support")
                    enabled: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                    onClicked: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.triggerAction("createSupportForOverhangs")
                        }
                    }
                }
            }

            // Detection Status
            Label {
                id: detectionStatusLabel
                width: parent.width
                height: UM.Theme.getSize("setting_control").height
                text: {
                    if (UM.ActiveTool) {
                        var count = UM.ActiveTool.properties.getValue("DetectedOverhangCount")
                        if (count === 0) {
                            return "No overhangs detected. Select a model and click Detect."
                        } else if (count === 1) {
                            return "Detected 1 overhang region"
                        } else {
                            return "Detected " + count + " overhang regions"
                        }
                    }
                    return ""
                }
                font: UM.Theme.getFont("default")
                color: {
                    if (UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0) {
                        return UM.Theme.getColor("primary")
                    }
                    return UM.Theme.getColor("text_inactive")
                }
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
                wrapMode: Text.WordWrap
            }

            // Custom Support Mesh Section (Phase 3 + 4)
            Label {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                text: catalog.i18nc("@label", "Custom Support Mesh:")
                font: UM.Theme.getFont("default_bold")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            // Column Radius
            Row {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Column Radius:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 85
                }

                Slider {
                    id: columnRadiusSlider
                    width: 80
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.5
                    to: 5.0
                    stepSize: 0.5
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("ColumnRadius") : 2.0
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("ColumnRadius", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 50
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: columnRadiusSlider.value.toFixed(1)
                    validator: DoubleValidator { bottom: 0.5; top: 5.0; decimals: 1 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("ColumnRadius", value)
                            columnRadiusSlider.value = value
                        }
                    }
                }
            }

            // Column Taper
            Row {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Column Taper:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 85
                }

                Slider {
                    id: columnTaperSlider
                    width: 80
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.2
                    to: 1.0
                    stepSize: 0.1
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("ColumnTaper") : 0.6
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("ColumnTaper", value)
                        }
                    }
                }

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: Math.round(columnTaperSlider.value * 100) + "%"
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 40
                }
            }

            // Rail Width
            Row {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Rail Width:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 85
                }

                Slider {
                    id: railWidthSlider
                    width: 80
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.3
                    to: 3.0
                    stepSize: 0.1
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("RailWidth") : 0.8
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("RailWidth", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 50
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: railWidthSlider.value.toFixed(1)
                    validator: DoubleValidator { bottom: 0.3; top: 3.0; decimals: 1 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("RailWidth", value)
                            railWidthSlider.value = value
                        }
                    }
                }
            }

            Row {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                ComboBox {
                    id: customSupportTypeComboBox
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    model: ["Auto", "Columns Only", "Rails Only"]
                    currentIndex: 0
                }

                Button {
                    id: createCustomMeshButton
                    width: 130
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@button", "Create Custom Mesh")
                    onClicked: {
                        if (UM.ActiveTool) {
                            var typeMap = ["auto", "tip_column", "edge_rail"]
                            UM.ActiveTool.triggerActionWithData("createCustomSupportMeshV2", typeMap[customSupportTypeComboBox.currentIndex])
                        }
                    }
                }
            }

            Label {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("DetectedOverhangCount") > 0
                width: parent.width
                text: "Columns for tips, rails for edges. Supports model-to-model."
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
                wrapMode: Text.WordWrap
            }

            // Separator after detection section
            Rectangle {
                width: parent.width
                height: 1
                color: UM.Theme.getColor("lining")
            }
        }

        // Wing Settings (only visible in wing mode)
        Column {
            id: wingSettingsColumn
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") === "wing"
            spacing: Math.round(UM.Theme.getSize("default_margin").height / 2)
            width: parent.width

            Label {
                text: catalog.i18nc("@label", "Wing Settings:")
                font: UM.Theme.getFont("default_bold")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            // Wing Direction
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Direction:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                }

                ComboBox {
                    id: wingDirectionComboBox
                    width: 140
                    height: UM.Theme.getSize("setting_control").height
                    model: ["To Build Plate", "Horizontal"]
                    currentIndex: {
                        if (UM.ActiveTool) {
                            var dir = UM.ActiveTool.properties.getValue("WingDirection")
                            return dir === "horizontal" ? 1 : 0
                        }
                        return 0
                    }
                    onActivated: {
                        if (UM.ActiveTool) {
                            var dirMap = ["to_buildplate", "horizontal"]
                            UM.ActiveTool.setProperty("WingDirection", dirMap[currentIndex])
                        }
                    }
                }
            }

            // Wing Thickness
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Thickness:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                Slider {
                    id: wingThicknessSlider
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.5
                    to: 5.0
                    stepSize: 0.1
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("WingThickness") : 1.5
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingThickness", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 60
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: wingThicknessSlider.value.toFixed(1)
                    validator: DoubleValidator { bottom: 0.5; top: 5.0; decimals: 1 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingThickness", value)
                            wingThicknessSlider.value = value
                        }
                    }
                }
            }

            // Wing Width
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Width:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                Slider {
                    id: wingWidthSlider
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    from: 2.0
                    to: 20.0
                    stepSize: 0.5
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("WingWidth") : 5.0
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingWidth", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 60
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: wingWidthSlider.value.toFixed(1)
                    validator: DoubleValidator { bottom: 2.0; top: 20.0; decimals: 1 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingWidth", value)
                            wingWidthSlider.value = value
                        }
                    }
                }
            }

            // Wing Rotation
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Rotation:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                Slider {
                    id: wingRotationSlider
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    from: -180
                    to: 180
                    stepSize: 15
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("WingRotation") : 0
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingRotation", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 60
                    height: UM.Theme.getSize("setting_control").height
                    unit: "°"
                    text: wingRotationSlider.value.toFixed(0)
                    validator: DoubleValidator { bottom: -180; top: 180; decimals: 0 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingRotation", value)
                            wingRotationSlider.value = value
                        }
                    }
                }
            }

            // Break-line Enable
            Row {
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Break-line:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                CheckBox {
                    id: breaklineCheckbox
                    height: UM.Theme.getSize("setting_control").height
                    checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("WingBreaklineEnable") : true
                    onCheckedChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingBreaklineEnable", checked)
                        }
                    }
                }

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: breaklineCheckbox.checked ? "Enabled (easier removal)" : "Disabled"
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text_inactive")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                }
            }

            // Break-line Depth (only visible when break-line is enabled)
            Row {
                visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("WingBreaklineEnable")
                spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

                Label {
                    height: UM.Theme.getSize("setting_control").height
                    text: catalog.i18nc("@label", "Notch Depth:")
                    font: UM.Theme.getFont("default")
                    color: UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    renderType: Text.NativeRendering
                    width: 70
                }

                Slider {
                    id: breaklineDepthSlider
                    width: 100
                    height: UM.Theme.getSize("setting_control").height
                    from: 0.2
                    to: 1.0
                    stepSize: 0.1
                    value: UM.ActiveTool ? UM.ActiveTool.properties.getValue("WingBreaklineDepth") : 0.5
                    onValueChanged: {
                        if (UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingBreaklineDepth", value)
                        }
                    }
                }

                UM.TextFieldWithUnit {
                    width: 60
                    height: UM.Theme.getSize("setting_control").height
                    unit: "mm"
                    text: breaklineDepthSlider.value.toFixed(1)
                    validator: DoubleValidator { bottom: 0.2; top: 1.0; decimals: 1 }
                    onEditingFinished: {
                        var value = parseFloat(text)
                        if (!isNaN(value) && UM.ActiveTool) {
                            UM.ActiveTool.setProperty("WingBreaklineDepth", value)
                            breaklineDepthSlider.value = value
                        }
                    }
                }
            }

            // Separator after wing settings
            Rectangle {
                width: parent.width
                height: 1
                color: UM.Theme.getColor("lining")
            }
        }

        // Size Presets Row (hidden in wing mode)
        Row {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Size Preset:")
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

        // Save Preset Row - only visible in custom mode (and not wing mode)
        Row {
            id: savePresetRow
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("IsCustom") && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
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

        // Dangling Vertex Detection Checkbox
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            CheckBox {
                id: danglingVertexCheckbox
                height: UM.Theme.getSize("setting_control").height
                checked: UM.ActiveTool ? UM.ActiveTool.properties.getValue("DetectDanglingVertices") : false
                onToggled: {
                    if (UM.ActiveTool) {
                        UM.ActiveTool.setProperty("DetectDanglingVertices", checked)
                    }
                }

                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    x: danglingVertexCheckbox.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 3
                    border.color: danglingVertexCheckbox.down ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    border.width: 1
                    color: "transparent"

                    Rectangle {
                        width: 12
                        height: 12
                        x: 4
                        y: 4
                        radius: 2
                        color: UM.Theme.getColor("primary")
                        visible: danglingVertexCheckbox.checked
                    }
                }

                contentItem: Label {
                    text: catalog.i18nc("@label", "Detect Dangling Vertices (auto-detect mode)")
                    font: UM.Theme.getFont("default")
                    color: danglingVertexCheckbox.checked ? UM.Theme.getColor("primary") : UM.Theme.getColor("text")
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: danglingVertexCheckbox.indicator.width + danglingVertexCheckbox.spacing
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
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
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

        // Separator before support settings (hidden in wing mode)
        Rectangle {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            width: parent.width
            height: 1
            color: UM.Theme.getColor("lining")
        }

        // Support Settings Info Header (hidden in wing mode)
        Label {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            text: catalog.i18nc("@label", "Support Settings (applied to volume):")
            font: UM.Theme.getFont("default_bold")
            color: UM.Theme.getColor("text")
            renderType: Text.NativeRendering
        }

        // Support Settings Display Grid (hidden in wing mode)
        Grid {
            id: supportSettingsGrid
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            columns: 2
            columnSpacing: Math.round(UM.Theme.getSize("default_margin").width)
            rowSpacing: Math.round(UM.Theme.getSize("default_margin").height / 2)

            Label {
                text: catalog.i18nc("@label", "Pattern:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            Label {
                text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportPattern") : "grid"
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            Label {
                text: catalog.i18nc("@label", "Infill Rate:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            Label {
                text: (UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportInfillRate") : 15) + "%"
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            Label {
                text: catalog.i18nc("@label", "Line Width:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            Label {
                text: (UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportLineWidth").toFixed(2) : "0.40") + " mm"
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            Label {
                text: catalog.i18nc("@label", "Wall Count:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            Label {
                text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportWallCount") : 1
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }

            Label {
                text: catalog.i18nc("@label", "Interface:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            Label {
                text: (UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportInterfaceEnable")) ? "Enabled" : "Disabled"
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
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
