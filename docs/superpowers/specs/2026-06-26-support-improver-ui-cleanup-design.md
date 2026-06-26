# Support Improver — UI Cleanup Design

Date: 2026-06-26
Status: Approved (pending spec review)

## Problem

The tool panel (`qt6/SupportImprover.qml`, ~1393 lines, one flat `Column`) is hard to
read and the top "Support Mode" dropdown's effect is unclear.

Concrete issues found:

1. **"Support Mode" mixes two unrelated concepts.** The dropdown
   `[Structural (Dense), Stability (Minimal), Attached Wing, Custom]` lumps three
   *support-density presets* (structural/stability/custom — same modifier cube,
   different Cura support settings) together with *Attached Wing* (a different
   geometry type entirely).
2. **Mode effect is invisible.** For structural/stability/custom the only on-screen
   difference is the **read-only** "Support Settings (applied to volume)" block at the
   very bottom of the panel — five lines of non-editable text, far from the dropdown.
   Three of the four modes therefore look identical. "Custom" is meaningless because
   nothing is editable.
3. **Two workflows are interleaved.** Manual modifier-volume placement (size preset,
   W/D/H, angle) and automatic overhang detection (detect, create support, custom
   mesh) are mixed top-to-bottom instead of separated.
4. **Checkbox pile.** Five always-visible checkboxes with no header: Single Region,
   Auto-Detect All, Detect Sharp Features, Detect Dangling Vertices, Export Mode. Two
   are labelled "(auto-detect mode)" but are not nested under Auto-Detect. Export Mode
   is a debug feature shown alongside user features.
5. **Divergent descriptions.** QML hardcodes mode description strings that differ from
   the `SUPPORT_MODE_SETTINGS[...]["description"]` values in Python.

Current usage: the user works almost entirely with **manual volumes** because the
automatic modes are unreliable. Automatic detection must stay accessible (for future
fixing/testing) but should not clutter the working manual path.

## Decisions

- **Split the mode selector into two.**
  - `Support Type` = { Modifier Volume, Wing } at the top.
  - When *Modifier Volume*: a `Density` selector = { Structural, Stability, Custom }.
  - When *Wing*: show Wing settings instead.
- **Support settings are always editable.** Picking a Density preset loads default
  values; any field can be overridden. Changing any field flips Density to "Custom"
  (already the Python behaviour). The read-only display block is replaced with live
  controls.
- **Automatic detection becomes a collapsible "experimental" section**, collapsed by
  default. Sharp Features and Dangling Vertices nest under (and enable only with)
  Auto-Detect All.
- **Export Mode → "Export Mesh Data"**, moved into a collapsed Debug section.
- **Single source of truth for descriptions:** QML reads `SupportModeDescription`
  from Python instead of hardcoding strings.
- **Implementation:** in-place reorganization of the single `SupportImprover.qml`
  file (no component split). Lowest risk to the working manual path; matches Cura's
  single-QML plugin convention.

## New Layout (top → bottom)

```
Support Type:  ( ● Modifier Volume   ○ Wing )

IF Modifier Volume:
  Density: [ Structural ▼ ]   <italic description from Python>
  Size Preset: [ Medium ▼ ]  [Save]
  Width (X)  / Depth (Y) / Height (Z) sliders + fields
  Support Angle slider + field
  Support Settings (editable):
    Pattern [▼] · Infill [%] · Line Width [mm] · Wall Count [#]
    Interface [✓] · Roof [✓] · Bottom [✓]

IF Wing:
  Direction [▼] · Thickness · Width · Rotation
  Break-line [✓] · Notch Depth

▷ Automatic Detection (experimental)   [collapsed by default]
    Detection Angle slider + field
    [Detect Overhangs]  [Create Support]
    <status: N regions detected>
    [ ] Single Region (fast)
    [ ] Auto-Detect All Regions
        └ [ ] Sharp Features      (enabled only when Auto-Detect All on)
        └ [ ] Dangling Vertices   (enabled only when Auto-Detect All on)
    — Custom Support Mesh — (visible when DetectedOverhangCount > 0)
    Column Radius · Taper · Rail Width
    [Create Custom Mesh]

▷ Debug   [collapsed by default]
    [ ] Export Mesh Data
```

## Visibility / Behaviour Rules

| Element | Visible / enabled when |
|---|---|
| Density selector + size + support settings | Support Type == Modifier Volume |
| Wing settings | Support Type == Wing |
| Sharp Features / Dangling Vertices checkboxes | enabled only when Auto-Detect All checked |
| Custom Support Mesh sub-block | `DetectedOverhangCount > 0` |
| Automatic Detection section body | section expanded (collapsed by default) |
| Debug section body | section expanded (collapsed by default) |

## Type ↔ Density mapping (no Python model change)

The existing `SupportMode` property keeps values `structural | stability | custom | wing`.
The QML derives the two new selectors from it:

- `Support Type`: `Wing` if `SupportMode == "wing"`, else `Modifier Volume`.
- Selecting `Wing` → `setProperty("SupportMode", "wing")`.
- Selecting `Modifier Volume` → restore the last non-wing density (default
  `structural`).
- `Density` selector reads/writes `SupportMode` among `structural/stability/custom`,
  hidden while Type == Wing.

This keeps all backend logic (`SUPPORT_MODE_SETTINGS`, geometry switch on `"wing"`,
auto-flip to `custom`) unchanged. The change is almost entirely in QML.

## Collapsible section pattern

No standard collapse widget is used in the current file. Implement a small reusable
pattern inline: a clickable header `Row` (chevron + bold label) toggling a `bool`
property that drives the body `Column`'s `visible` / `height`. Two instances:
Automatic Detection and Debug.

## Out of Scope

- Fixing the automatic-detection algorithms themselves (separate effort).
- Splitting the QML into multiple component files (deferred; revisit if the file
  stays unwieldy after cleanup).
- Any change to support geometry generation or detection logic.

## Testing / Verification

- Manual smoke test in Cura 5.13 (plugin is junctioned): load the tool, confirm
  Type/Density switching shows/hides the right blocks, editing a support setting flips
  Density to Custom, presets load values, Wing mode shows only wing settings,
  collapsible sections toggle, auto-detect still runs.
- Existing `tests/` continue to pass (UI change should not affect Python logic tests).
