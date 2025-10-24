# My Support Improver

A Cura plugin that creates customizable cutting volumes to control support generation settings in specific areas of your 3D prints.

## Features

- **Click to Place**: Simply click on your model to place modifier volumes
- **Customizable Dimensions**: Control Width (X), Depth (Y), and Height (Z) independently
- **Support Angle Control**: Adjust support overhang angle (0-90°) within volumes
- **Preset System**: Save and load dimension presets for quick access
- **Visual Feedback**: Clear indication of custom vs preset modes

## What Does It Do?

This plugin creates a cutting volume that allows you to set specific support settings in localized areas. The most useful setting is the **support overhang angle**, which controls where supports are generated.

For example:
- Increase the angle in specific areas to reduce support material
- Decrease the angle to add more support in critical regions
- Fine-tune support placement without affecting the entire model

## Installation

### Method 1: Automatic Installation (Recommended)

1. Download the latest `MySupportImprover-X.X.X.zip` from the [Releases](https://github.com/emanuellonnberg/MySupportImprover/releases) page
2. Open Cura
3. Go to: **Help → Show Configuration Folder**
4. Navigate to the **plugins** folder
5. Extract the entire `MySupportImprover` folder into the plugins directory
6. Restart Cura
7. The tool should appear in the left toolbar (icon with down arrow)

### Method 2: Manual Installation

1. Clone or download this repository
2. Copy the entire `MySupportImprover` folder to your Cura plugins directory:
   - **Windows**: `%APPDATA%\cura\<version>\plugins\`
   - **macOS**: `~/Library/Application Support/Cura/<version>/plugins/`
   - **Linux**: `~/.local/share/cura/<version>/plugins/`
3. Restart Cura

### Verification

After installation, you should see the "My Support Improver" tool in the left toolbar. If not:
- Check that all files are in a folder called `MySupportImprover`
- Check the Cura log for errors (Help → Show Log File)
- Verify you're using Cura 5.0.0 or higher

## Usage

### Basic Usage

1. **Activate the Tool**: Click the tool icon in the left toolbar or press the `E` key
2. **Load a Model**: Make sure you have a model loaded on the build plate
3. **Place Volume**: Click anywhere on your model to place a modifier volume
4. **Adjust Settings**: Use the tool panel to adjust dimensions and support angle
5. **Remove Volume**: Click on an existing volume to remove it

### Working with Presets

**Using Presets:**
1. Select a preset from the dropdown (Small, Medium, Large, Wide, Tall)
2. The dimensions will automatically update
3. Place volumes with the preset dimensions

**Creating Custom Presets:**
1. Adjust the X, Y, Z sliders to your desired dimensions
2. The preset dropdown will show "Custom"
3. Enter a name in the text field
4. Click "Save" to store as a new preset
5. Your custom preset will appear in the dropdown

**Preset Sizes:**
- **Small**: 2×2×2 mm - Precision control for small details
- **Medium**: 3×3×3 mm - General purpose (default)
- **Large**: 5×5×5 mm - Broad coverage areas
- **Wide**: 10×5×3 mm - Horizontal spans
- **Tall**: 3×3×10 mm - Vertical control

### Advanced Tips

- **Ctrl+Click**: Hold Ctrl while clicking to switch to the Translate tool
- **Multiple Volumes**: Place multiple volumes with different settings on the same model
- **Support Angle Guide**:
  - `0°` - Support everywhere (including flat surfaces)
  - `45°` - Default Cura setting (good balance)
  - `60°` - Reduced supports (for well-tuned printers)
  - `90°` - No supports (only use if you know what you're doing)

## Keyboard Shortcuts

- `E` - Activate the Support Improver tool
- `Ctrl+Click` - Switch to Translate tool

## Settings Controlled

The plugin creates cutting mesh volumes that can override these support settings:
- `support_angle` - Overhang angle for support generation
- `support_z_distance` - Vertical distance between support and model
- `support_top_distance` - Distance from support to model top surfaces
- `support_bottom_distance` - Distance from support to model bottom surfaces
- `support_xy_distance` - Horizontal distance between support and model

## Troubleshooting

### Tool doesn't appear in toolbar
- Verify installation location (see Installation section)
- Check Cura version is 5.0.0 or higher
- Look for errors in Help → Show Log File

### Volumes don't affect support generation
- Make sure "Generate Support" is enabled in Cura settings
- Verify the volume intersects with your model
- Try adjusting the support angle to see changes

### Presets don't save
- Check write permissions in the plugin folder
- Look for errors in the Cura log file

### Support angle doesn't change
- This is a known issue being investigated
- Workaround: Manually adjust support settings in Per Model Settings

## Development

### Building a Release Package

**Linux/macOS:**
```bash
./package.sh
```

**Windows:**
```batch
package.bat
```

This creates a `MySupportImprover-X.X.X.zip` file ready for distribution.

### Project Structure

```
MySupportImprover/
├── __init__.py              # Plugin registration
├── MySupportImprover.py     # Main tool implementation
├── plugin.json              # Plugin metadata
├── presets.json            # Dimension presets
├── down.svg                # Tool icon
├── qt6/
│   └── SupportImprover.qml # User interface
├── README.md               # This file
├── CHANGELOG.md            # Version history
├── package.sh              # Linux/macOS build script
└── package.bat             # Windows build script
```

### Requirements

- Cura 5.0.0 or higher
- Python 3.x (included with Cura)
- PyQt6 (included with Cura)

## Known Issues

- Support angle setting may not apply correctly in all cases (under investigation)
- Multiple clicks in rapid succession may cause unexpected behavior

See [CHANGELOG.md](CHANGELOG.md) for version history and [Issues](https://github.com/emanuellonnberg/MySupportImprover/issues) for current bugs and feature requests.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This plugin is released under the terms of the LGPLv3 or higher.

Copyright (c) 2024 Emanuel Lönnberg

## Credits

Created by Emanuel Lönnberg

Special thanks to the Cura community for their support and feedback.

## Links

- [GitHub Repository](https://github.com/emanuellonnberg/MySupportImprover)
- [Issue Tracker](https://github.com/emanuellonnberg/MySupportImprover/issues)
- [Cura Documentation](https://github.com/Ultimaker/Cura)
- [Cura Plugin Development](https://github.com/Ultimaker/Cura/wiki/Plugin-Directory)
