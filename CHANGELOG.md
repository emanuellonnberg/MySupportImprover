# Changelog

All notable changes to the My Support Improver plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-10-24

### Added
- Custom preset support - create and save your own dimension presets
- Preset management system with JSON-based storage
- Support angle control (0-90 degrees) via UI slider
- Visual feedback when switching between presets and custom mode
- Width (X), Depth (Y), and Height (Z) dimension controls with sliders and text input
- Keyboard shortcut (E key) to activate tool
- Click to place modifier volumes on models
- Cutting mesh volume creation with custom dimensions
- Support settings override within volumes:
  - support_z_distance
  - support_top_distance
  - support_xy_distance
  - support_bottom_distance
  - support_angle
- Three default presets: Small (2x2x2mm), Medium (3x3x3mm), Large (5x5x5mm)

### Changed
- Updated to semantic versioning (1.0.0)
- Improved property management with PyQt property decorators
- Enhanced logging for debugging

### Fixed
- Mesh coordinate system to properly match Cura's coordinate space
- Preset value synchronization between UI and backend

### Known Issues
- Support angle setting may not apply correctly in all cases (under investigation)

## [0.1] - Initial Development

### Added
- Initial plugin structure
- Basic modifier volume creation
- Simple dimension controls

---

## Version History Summary

- **1.0.0** - First stable release with preset system and enhanced UI
- **0.1** - Initial development version

## Upgrade Notes

### Upgrading to 1.0.0
- If you have an existing `presets.json` file, it will be automatically loaded
- New default presets will be created if no presets file exists
- All existing functionality is preserved

## Future Plans

See [GitHub Issues](https://github.com/emanuellonnberg/MySupportImprover/issues) for planned features and improvements.
