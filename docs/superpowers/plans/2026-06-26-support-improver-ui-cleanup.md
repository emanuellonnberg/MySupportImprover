# Support Improver UI Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Support Improver tool panel so each support type shows only the controls valid for it, the support settings are editable, and the flaky automatic-detection controls are tucked into a collapsible experimental section.

**Architecture:** Pure QML edit of the single file `qt6/SupportImprover.qml`. No Python changes — the new "Support Type" (Modifier Volume / Wing) and "Density" (Structural / Stability / Custom) selectors are derived in QML from the existing `SupportMode` property (`structural | stability | custom | wing`). All backend logic (`SUPPORT_MODE_SETTINGS`, geometry switch on `"wing"`, auto-flip to `custom` when a setting changes) is untouched.

**Tech Stack:** QtQuick 6.0, QtQuick.Controls 6.0, `UM 1.6`, `Cura 1.0`. Cura plugin loaded via junction at `C:\Users\emanu\AppData\Roaming\cura\5.13\plugins\MySupportImprover` → `E:\MySupportImprover`.

## Global Constraints

- Edit only `qt6/SupportImprover.qml`. No changes to `MySupportImprover.py` or any Python.
- All user-facing strings use `catalog.i18nc("@label"/"@button", "...")` (existing pattern).
- Read setting values via `UM.ActiveTool.properties.getValue("Prop")`; write via `UM.ActiveTool.setProperty("Prop", value)` (existing pattern).
- Every binding that reads `UM.ActiveTool` must guard with `UM.ActiveTool && ...` (existing pattern) to avoid null errors when no tool is active.
- The existing `SupportMode` property values stay `structural | stability | custom | wing`. Do NOT add new SupportMode values.
- **No automated QML tests exist.** Each task's verification is a manual smoke test in Cura: save the file, in Cura switch to another tool and back to Support Improver (or restart Cura) to reload the QML, then observe. Commit only after the observed result matches "Expected".
- Make a backup tag before starting so the working manual UI can be restored: the first step of Task 1 covers this.

---

### Task 1: Add "Support Type" selector and derive Density from SupportMode

**Files:**
- Modify: `qt6/SupportImprover.qml:58-93` (the existing "Support Mode Selection" Row)
- Modify: `qt6/SupportImprover.qml:95-113` (the description Label)

**Interfaces:**
- Consumes: existing `SupportMode` property (string `structural|stability|custom|wing`), existing `SupportModeDescription` property (string).
- Produces: QML ids `supportTypeComboBox`, `densityComboBox`; QML property `base.lastDensityMode` (string, default `"structural"`) used by later tasks' visibility bindings via `supportTypeComboBox.currentIndex`.

- [ ] **Step 1: Safety tag the current working UI**

Run:
```bash
git -C E:/MySupportImprover tag pre-ui-cleanup
```
Expected: no output, tag created. (Restore later with `git checkout pre-ui-cleanup -- qt6/SupportImprover.qml` if needed.)

- [ ] **Step 2: Add a `lastDensityMode` property**

In `qt6/SupportImprover.qml`, after line 19 (`property real defaultZ: 3.0`), add:

```qml
    // Remembers the last non-wing density so switching Wing -> Modifier Volume restores it
    property string lastDensityMode: "structural"
```

- [ ] **Step 3: Replace the "Support Mode Selection" Row with Type + Density selectors**

Replace the whole block at lines 58-93 (the comment `// Support Mode Selection` through the closing `}` of that `Row`) with:

```qml
        // Support Type Selection (Modifier Volume vs Wing)
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Support Type:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }

            ComboBox {
                id: supportTypeComboBox
                width: 150
                height: UM.Theme.getSize("setting_control").height
                model: [catalog.i18nc("@option", "Modifier Volume"), catalog.i18nc("@option", "Wing")]
                currentIndex: (UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") === "wing") ? 1 : 0
                onActivated: {
                    if (!UM.ActiveTool) return
                    if (currentIndex === 1) {
                        UM.ActiveTool.setProperty("SupportMode", "wing")
                    } else {
                        UM.ActiveTool.setProperty("SupportMode", base.lastDensityMode)
                    }
                }
            }
        }

        // Density preset (only meaningful for Modifier Volume)
        Row {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)

            Label {
                height: UM.Theme.getSize("setting_control").height
                text: catalog.i18nc("@label", "Density:")
                font: UM.Theme.getFont("default")
                color: UM.Theme.getColor("text")
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }

            ComboBox {
                id: densityComboBox
                width: 150
                height: UM.Theme.getSize("setting_control").height
                model: [catalog.i18nc("@option", "Structural (Dense)"), catalog.i18nc("@option", "Stability (Minimal)"), catalog.i18nc("@option", "Custom")]
                currentIndex: {
                    if (UM.ActiveTool) {
                        var mode = UM.ActiveTool.properties.getValue("SupportMode")
                        if (mode === "structural") return 0
                        if (mode === "stability") return 1
                        if (mode === "custom") return 2
                    }
                    return 0
                }
                onActivated: {
                    if (!UM.ActiveTool) return
                    var modeMap = ["structural", "stability", "custom"]
                    base.lastDensityMode = modeMap[currentIndex]
                    UM.ActiveTool.setProperty("SupportMode", modeMap[currentIndex])
                }
            }
        }
```

- [ ] **Step 4: Point the description Label at the Python value and hide it in wing mode**

Replace the `text:` binding inside the description Label (lines 99-108) with a single source of truth, and add a `visible` line. The Label becomes:

```qml
        // Support Mode Description (from Python, single source of truth)
        Label {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            width: parent.width
            height: UM.Theme.getSize("setting_control").height
            text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportModeDescription") : ""
            font: UM.Theme.getFont("default_italic")
            color: UM.Theme.getColor("text_inactive")
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
        }
```

- [ ] **Step 5: Manual verify in Cura**

Save file. Reload tool in Cura (switch tools or restart). Expected:
- A "Support Type:" dropdown with `Modifier Volume` / `Wing`.
- With `Modifier Volume` selected, a "Density:" dropdown with `Structural / Stability / Custom`, plus the italic description text coming from Python.
- Selecting `Wing` hides the Density dropdown and the description; the wing settings still appear lower down (unchanged for now).
- Selecting `Structural`/`Stability`/`Custom` updates the description text.

- [ ] **Step 6: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Split support mode into Support Type + Density selectors"
```

---

### Task 2: Move Wing settings adjacent to the Type selector

**Files:**
- Modify: `qt6/SupportImprover.qml` — relocate the Wing settings block (currently `visible: ... SupportMode === "wing"`, starts at the comment near line 430) to sit immediately after the Density Row added in Task 1.

**Interfaces:**
- Consumes: `supportTypeComboBox` / `SupportMode` from Task 1.
- Produces: nothing new; only reorders existing elements.

- [ ] **Step 1: Locate the Wing settings block**

Run:
```bash
git -C E:/MySupportImprover grep -n 'SupportMode") === "wing"' -- qt6/SupportImprover.qml
```
Expected: the line of the outer Wing `Column`'s `visible:` binding (the block containing "Wing Settings:", Direction, Thickness, Width, Rotation, Break-line, Notch Depth). Note its start (the `Column {` or wrapping element above that `visible:`) and end (its matching closing `}`).

- [ ] **Step 2: Cut the entire Wing block and paste it directly after the Density Row**

Move the whole Wing `Column { visible: ... === "wing" ... }` block so it appears immediately after the Density `Row` block from Task 1 Step 3 (i.e. right after the description Label). Do not change its contents — only its position. Keep its existing `visible:` binding.

- [ ] **Step 3: Add the inverse guard to the Size Preset block**

The Size Preset Row already has `visible: ... SupportMode !== "wing"` (near line 702). Leave it. No change needed beyond confirming it is still present after the move.

- [ ] **Step 4: Manual verify in Cura**

Save, reload. Expected:
- `Wing` selected → Wing Settings (Direction/Thickness/Width/Rotation/Break-line/Notch) appear right under the Type selector; Size Preset, W/D/H, support settings are hidden.
- `Modifier Volume` selected → Wing Settings hidden; Density + sizing controls visible.

- [ ] **Step 5: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Move Wing settings next to Support Type selector"
```

---

### Task 3: Replace read-only support-settings display with editable controls

**Files:**
- Modify: `qt6/SupportImprover.qml:1293-1373` (the "Support Settings (applied to volume):" header Label and the read-only `Grid` with id `supportSettingsGrid`).

**Interfaces:**
- Consumes: properties `SupportPattern` (str), `SupportInfillRate` (int), `SupportLineWidth` (float), `SupportWallCount` (int), `SupportInterfaceEnable` (bool), `SupportRoofEnable` (bool), `SupportBottomEnable` (bool). All have setters in Python that flip `SupportMode` → `custom` on change.
- Produces: nothing new.

- [ ] **Step 1: Replace the read-only header + grid with editable controls**

Replace lines 1293-1373 (the header Label through the closing `}` of `supportSettingsGrid`) with:

```qml
        // Support Settings (editable; changing any value flips Density to Custom)
        Label {
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            text: catalog.i18nc("@label", "Support Settings:")
            font: UM.Theme.getFont("default_bold")
            color: UM.Theme.getColor("text")
            renderType: Text.NativeRendering
        }

        Grid {
            id: supportSettingsGrid
            visible: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportMode") !== "wing"
            columns: 2
            columnSpacing: Math.round(UM.Theme.getSize("default_margin").width)
            rowSpacing: Math.round(UM.Theme.getSize("default_margin").height / 2)
            verticalItemAlignment: Grid.AlignVCenter

            Label {
                text: catalog.i18nc("@label", "Pattern:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            ComboBox {
                id: patternComboBox
                width: 130
                height: UM.Theme.getSize("setting_control").height
                model: ["lines", "grid", "triangles", "concentric", "zigzag"]
                currentIndex: {
                    if (UM.ActiveTool) {
                        var p = UM.ActiveTool.properties.getValue("SupportPattern")
                        var i = model.indexOf(p)
                        if (i >= 0) return i
                    }
                    return 0
                }
                onActivated: {
                    if (UM.ActiveTool) UM.ActiveTool.setProperty("SupportPattern", model[currentIndex])
                }
            }

            Label {
                text: catalog.i18nc("@label", "Infill Rate:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            UM.TextFieldWithUnit {
                width: 70; height: UM.Theme.getSize("setting_control").height
                unit: "%"
                text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportInfillRate").toString() : "15"
                validator: IntValidator { bottom: 0; top: 100 }
                onEditingFinished: {
                    var v = parseInt(text)
                    if (!isNaN(v) && UM.ActiveTool) UM.ActiveTool.setProperty("SupportInfillRate", v)
                }
            }

            Label {
                text: catalog.i18nc("@label", "Line Width:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            UM.TextFieldWithUnit {
                width: 70; height: UM.Theme.getSize("setting_control").height
                unit: "mm"
                text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportLineWidth").toFixed(2) : "0.40"
                validator: DoubleValidator { bottom: 0.1; top: 2.0; decimals: 2 }
                onEditingFinished: {
                    var v = parseFloat(text)
                    if (!isNaN(v) && UM.ActiveTool) UM.ActiveTool.setProperty("SupportLineWidth", v)
                }
            }

            Label {
                text: catalog.i18nc("@label", "Wall Count:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            UM.TextFieldWithUnit {
                width: 70; height: UM.Theme.getSize("setting_control").height
                unit: ""
                text: UM.ActiveTool ? UM.ActiveTool.properties.getValue("SupportWallCount").toString() : "1"
                validator: IntValidator { bottom: 0; top: 5 }
                onEditingFinished: {
                    var v = parseInt(text)
                    if (!isNaN(v) && UM.ActiveTool) UM.ActiveTool.setProperty("SupportWallCount", v)
                }
            }

            Label {
                text: catalog.i18nc("@label", "Interface:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            CheckBox {
                checked: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportInterfaceEnable")
                onToggled: { if (UM.ActiveTool) UM.ActiveTool.setProperty("SupportInterfaceEnable", checked) }
            }

            Label {
                text: catalog.i18nc("@label", "Roof:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            CheckBox {
                checked: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportRoofEnable")
                onToggled: { if (UM.ActiveTool) UM.ActiveTool.setProperty("SupportRoofEnable", checked) }
            }

            Label {
                text: catalog.i18nc("@label", "Bottom:")
                font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text_inactive")
                renderType: Text.NativeRendering
            }
            CheckBox {
                checked: UM.ActiveTool && UM.ActiveTool.properties.getValue("SupportBottomEnable")
                onToggled: { if (UM.ActiveTool) UM.ActiveTool.setProperty("SupportBottomEnable", checked) }
            }
        }
```

- [ ] **Step 2: Manual verify in Cura**

Save, reload. With `Modifier Volume` + `Structural`:
- Pattern shows `grid`, Infill `15`, Line Width `0.40`, Wall `1`, Interface/Roof/Bottom checked.
- Change Infill to `30` and press Enter → Density dropdown flips to `Custom` (Python auto-flips `SupportMode`), value persists.
- Switch Density back to `Structural` → fields reset to preset defaults (15 etc.).

- [ ] **Step 3: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Make volume support settings editable"
```

---

### Task 4: Collapsible "Automatic Detection (experimental)" section + nested sub-options

**Files:**
- Modify: `qt6/SupportImprover.qml` — wrap the Automatic Detection content (the `overhangDetectionSection` Column starting ~line 125 and the Custom Support Mesh sub-block within it) in a collapsible container; relocate the detection-related checkboxes (Single Region ~783, Auto-Detect All ~837, Sharp Features ~891, Dangling Vertices ~936) into it.

**Interfaces:**
- Consumes: existing properties `OverhangThreshold`, `DetectedOverhangCount`, `SingleRegion`, `AutoDetect`, `DetectSharpFeatures`, `DetectDanglingVertices`, actions `detectOverhangsOnSelection`, `createSupportForOverhangs`, `createCustomSupportMesh` (whichever the existing Create Custom Mesh button calls).
- Produces: QML property `base.autoExpanded` (bool, default false).

- [ ] **Step 1: Add the expand-state property**

After the `lastDensityMode` property added in Task 1 Step 2, add:

```qml
    property bool autoExpanded: false
    property bool debugExpanded: false
```

- [ ] **Step 2: Add a collapsible header above the detection content**

Immediately before the `overhangDetectionSection` Column (the `// Automatic Overhang Detection Section` comment ~line 122), insert a clickable header:

```qml
        // Separator before experimental section
        Rectangle { width: parent.width; height: 1; color: UM.Theme.getColor("lining") }

        // Collapsible header: Automatic Detection (experimental)
        Row {
            spacing: Math.round(UM.Theme.getSize("default_margin").width / 2)
            Label {
                text: (base.autoExpanded ? "▼ " : "▷ ") + catalog.i18nc("@label", "Automatic Detection (experimental)")
                font: UM.Theme.getFont("default_bold")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }
            MouseArea {
                anchors.fill: parent
                onClicked: base.autoExpanded = !base.autoExpanded
            }
        }
```

Note: place the `MouseArea` so it covers the header Label (e.g. give the Row an `id` and width, or wrap the Label and MouseArea so the click toggles). Simplest robust form: wrap the Label in an `Item` sized to the Label with the `MouseArea` as a child filling it.

- [ ] **Step 3: Gate the detection Column on `autoExpanded`**

On the `overhangDetectionSection` Column, add:

```qml
            visible: base.autoExpanded
```

Remove the now-redundant bold "Automatic Detection:" Label inside it (the header above replaces it).

- [ ] **Step 4: Move the detection checkboxes inside the section and nest sub-options**

Cut the four checkboxes — Single Region, Auto-Detect All Regions, Detect Sharp Features, Detect Dangling Vertices — from their current location (~lines 783-980) and paste them inside `overhangDetectionSection`, after the detection status label. Add an `enabled` gate to the two sub-options so they only apply with Auto-Detect on, and indent them. The Sharp Features and Dangling Vertices `CheckBox` elements get:

```qml
                // inside each of the Sharp Features and Dangling Vertices CheckBox:
                enabled: UM.ActiveTool && UM.ActiveTool.properties.getValue("AutoDetect")
                leftPadding: UM.Theme.getSize("default_margin").width   // visual nesting under Auto-Detect
```

Leave their existing `onClicked`/`checked` logic intact.

- [ ] **Step 5: Manual verify in Cura**

Save, reload. Expected:
- A collapsed `▷ Automatic Detection (experimental)` header; clicking expands to `▼` and reveals Detection Angle, Detect/Create buttons, status, and the four checkboxes.
- Sharp Features and Dangling Vertices are visibly indented and greyed out (disabled) until Auto-Detect All Regions is checked.
- Custom Support Mesh sub-block still appears (inside the section) once overhangs are detected.

- [ ] **Step 6: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Collapse automatic detection into experimental section with nested options"
```

---

### Task 5: Debug section for Export Mode

**Files:**
- Modify: `qt6/SupportImprover.qml` — relocate the Export Mode checkbox (~line 981) into a new collapsible Debug section at the bottom of `mainColumn`.

**Interfaces:**
- Consumes: existing `ExportMode` property and `base.debugExpanded` (from Task 4 Step 1).
- Produces: nothing new.

- [ ] **Step 1: Add the Debug section at the end of `mainColumn`**

Just before the closing `}` of `mainColumn` (after the editable support-settings Grid from Task 3, around old line 1373), insert:

```qml
        // Separator before debug
        Rectangle { width: parent.width; height: 1; color: UM.Theme.getColor("lining") }

        // Collapsible Debug header
        Item {
            width: debugHeaderLabel.width; height: debugHeaderLabel.height
            Label {
                id: debugHeaderLabel
                text: (base.debugExpanded ? "▼ " : "▷ ") + catalog.i18nc("@label", "Debug")
                font: UM.Theme.getFont("default_bold")
                color: UM.Theme.getColor("text")
                renderType: Text.NativeRendering
            }
            MouseArea { anchors.fill: parent; onClicked: base.debugExpanded = !base.debugExpanded }
        }

        Column {
            visible: base.debugExpanded
            spacing: Math.round(UM.Theme.getSize("default_margin").height / 2)
            width: parent.width

            CheckBox {
                id: exportModeCheckbox
                checked: UM.ActiveTool && UM.ActiveTool.properties.getValue("ExportMode")
                onToggled: { if (UM.ActiveTool) UM.ActiveTool.setProperty("ExportMode", checked) }
                contentItem: Label {
                    text: catalog.i18nc("@label", "Export Mesh Data")
                    leftPadding: exportModeCheckbox.indicator.width + exportModeCheckbox.spacing
                    verticalAlignment: Text.AlignVCenter
                    font: UM.Theme.getFont("default"); color: UM.Theme.getColor("text")
                    renderType: Text.NativeRendering
                }
            }
        }
```

- [ ] **Step 2: Delete the old Export Mode checkbox**

Remove the original Export Mode `CheckBox` block (~lines 981-1031) from its old position so it is not duplicated. Verify only one `id: exportModeCheckbox` (or equivalent) remains.

- [ ] **Step 3: Manual verify in Cura**

Save, reload. Expected:
- A collapsed `▷ Debug` header at the bottom; expanding shows a single "Export Mesh Data" checkbox.
- Toggling it sets ExportMode (next detect/create writes mesh data, same as before).
- Export Mode no longer appears among the main controls.

- [ ] **Step 4: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Move Export Mode into collapsible Debug section"
```

---

### Task 6: Final ordering pass and full smoke test

**Files:**
- Modify: `qt6/SupportImprover.qml` — confirm the top-to-bottom order matches the spec; fix any stray separators or leftover headers.

**Interfaces:**
- Consumes: everything above. Produces: final panel.

- [ ] **Step 1: Confirm element order matches the spec layout**

Read `qt6/SupportImprover.qml` top-to-bottom and confirm order:
1. Support Type selector
2. Density selector + description (Volume only)
3. Wing settings (Wing only)
4. Size Preset + Save (Volume only)
5. Width/Depth/Height/Support Angle (Volume only)
6. Support Settings editable grid (Volume only)
7. `▷ Automatic Detection (experimental)` collapsible
8. `▷ Debug` collapsible

Remove any orphaned separators (`Rectangle { height: 1 }`) left adjacent to moved blocks, and any leftover bold section Label that a collapsible header now replaces.

- [ ] **Step 2: Full manual smoke test in Cura**

Save, restart Cura. Verify in order:
- Modifier Volume / Structural: description from Python; size preset loads W/D/H; editing a support field flips Density → Custom; switching back to a preset resets values.
- Switch to Wing: only wing settings show; size/preset/support-settings hidden.
- Switch back to Modifier Volume: previous density restored (not forced back to Structural unless it was Structural).
- Expand Automatic Detection: angle, Detect/Create buttons, status, nested Sharp/Dangling disabled until Auto-Detect on; run Detect on a model still works.
- Expand Debug: Export Mesh Data toggle present.
- Place a modifier volume (manual path) end-to-end — confirm it still creates the volume as before.

- [ ] **Step 3: Commit**

```bash
git -C E:/MySupportImprover add qt6/SupportImprover.qml
git -C E:/MySupportImprover commit -m "Finalize Support Improver panel ordering"
```

- [ ] **Step 4: Drop the safety tag (optional, once satisfied)**

```bash
git -C E:/MySupportImprover tag -d pre-ui-cleanup
```

---

## Self-Review

**Spec coverage:**
- Split into Support Type + Density → Task 1. ✓
- Wing adjacent to type, only-valid options per type → Tasks 1–2 (visibility bindings). ✓
- Support settings always editable, deviate → Custom → Task 3 (relies on existing Python auto-flip). ✓
- Auto-detect collapsible experimental, Sharp/Dangling nested under Auto-Detect → Task 4. ✓
- Export Mode → "Export Mesh Data" in Debug section → Task 5. ✓
- Single source of truth for descriptions (Python) → Task 1 Step 4. ✓
- In-place QML reorg, no Python changes → Global Constraints + all tasks. ✓
- Manual Cura verification (no QML tests) → every task. ✓
- Final ordering matches spec → Task 6. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to" — concrete QML shown for every new/changed element. The two narrative steps (Task 2 move, Task 4/5 cut-paste) reference exact blocks by their `visible:`/`id:` anchors and grep commands.

**Type/property consistency:** Property names used match the Python `setExposedProperties` list (`SupportMode`, `SupportModeDescription`, `SupportPattern`, `SupportInfillRate`, `SupportLineWidth`, `SupportWallCount`, `SupportInterfaceEnable`, `SupportRoofEnable`, `SupportBottomEnable`, `ExportMode`, `AutoDetect`, `SingleRegion`, `DetectSharpFeatures`, `DetectDanglingVertices`, `OverhangThreshold`, `DetectedOverhangCount`). QML ids introduced (`supportTypeComboBox`, `densityComboBox`, `patternComboBox`, `exportModeCheckbox`) and base properties (`lastDensityMode`, `autoExpanded`, `debugExpanded`) are each defined before use.

**Open risk to verify during execution:** the exact action name for the "Create Custom Mesh" button (Task 4) — confirm via grep of the existing button's `triggerAction(...)` before moving the block; the move does not change it, so this is read-only confirmation.
