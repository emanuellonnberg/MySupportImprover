# Installing Your Plugin in Cura - Quick Guide

## Step 1: Download the Beta Release

1. Go to your GitHub repository releases:
   **https://github.com/emanuellonnberg/MySupportImprover/releases**

2. Find **v1.0.0-beta.1** (it should be marked as "Pre-release")

3. Download **MySupportImprover-1.0.0-beta.1.zip**

## Step 2: Find Your Cura Plugins Folder

### Easy Method (Recommended):
1. **Open Cura**
2. Go to: **Help → Show Configuration Folder**
3. A file browser will open
4. Navigate to the **plugins** folder inside

### Manual Method:

**Windows:**
```
%APPDATA%\cura\<version>\plugins\
```
Example: `C:\Users\YourName\AppData\Roaming\cura\5.8\plugins\`

**macOS:**
```
~/Library/Application Support/Cura/<version>/plugins/
```
Example: `/Users/YourName/Library/Application Support/Cura/5.8/plugins/`

**Linux:**
```
~/.local/share/cura/<version>/plugins/
```
Example: `/home/yourname/.local/share/cura/5.8/plugins/`

## Step 3: Install the Plugin

1. **Extract** the downloaded zip file
2. You should see a folder named **MySupportImprover**
3. **Copy** the entire **MySupportImprover** folder into the Cura plugins folder
4. The structure should look like:
   ```
   cura/5.8/plugins/
   └── MySupportImprover/
       ├── __init__.py
       ├── MySupportImprover.py
       ├── plugin.json
       ├── presets.json
       ├── down.svg
       ├── qt6/
       │   └── SupportImprover.qml
       └── ... (other files)
   ```

## Step 4: Restart Cura

1. **Close Cura completely** (if it was open)
2. **Reopen Cura**

## Step 5: Verify the Plugin Loaded

### Check 1: Look for the Tool Icon
- Look at the **left toolbar** in Cura
- You should see a new tool icon (down arrow)
- The tool should be called "My Support Improver"

### Check 2: Check the Logs (if icon doesn't appear)
1. Go to: **Help → Show Log File**
2. Search for "MySupportImprover" or "Support Improver"
3. Look for any error messages

**What you should see in logs:**
```
Support Improver Tool initialized with properties: X=3.0, Y=3.0, Z=3.0
Loaded 5 presets from presets.json
```

**What indicates an error:**
- Lines starting with `[ERROR]` or `[e]`
- Python import errors
- File not found errors

## Step 6: Test the Plugin

### Basic Test:
1. **Load a model** (any STL file)
2. **Click the My Support Improver tool** in the left toolbar (or press **E** key)
3. **Look at the right panel** - you should see:
   - Presets dropdown (Small, Medium, Large, Wide, Tall)
   - X, Y, Z dimension sliders
   - Support Angle slider
4. **Click on your model** - a small cube should appear
5. Try adjusting the sliders and clicking again

### Advanced Test:
1. Select a preset from the dropdown
2. Place a volume on your model
3. Adjust the support angle slider
4. Slice the model and check if supports appear differently in that area

## Troubleshooting

### Plugin doesn't appear in toolbar

**Check 1: Cura version**
- Minimum required: Cura 5.0.0
- Check your version: Help → About Cura

**Check 2: Folder structure**
```bash
# Make sure it's NOT:
plugins/MySupportImprover-1.0.0-beta.1/MySupportImprover/  ❌

# Should be:
plugins/MySupportImprover/  ✓
```

**Check 3: Read the log file**
- Help → Show Log File
- Search for errors related to MySupportImprover

### Common Issues:

**"Module not found" error:**
- The folder structure is wrong
- Make sure you copied the **MySupportImprover** folder, not the zip file

**Tool appears but crashes when clicking:**
- Check log file for Python errors
- Make sure all files are present (especially qt6/SupportImprover.qml)

**Tool appears but nothing happens when clicking:**
- Make sure you have a model loaded
- Make sure you're clicking on the model, not empty space
- Check that "cutting_mesh" is enabled in your Cura profile

### Getting Help:

If you encounter issues, gather this info:
1. Cura version (Help → About Cura)
2. Operating system (Windows/macOS/Linux)
3. Error messages from log file (Help → Show Log File)
4. Screenshots of the error or unexpected behavior

## Success Indicators

✅ **Plugin is working if you see:**
- Tool icon appears in left toolbar
- Tool panel shows on the right when activated
- Clicking on a model creates a small cube
- Sliders adjust the cube dimensions
- Presets can be selected from dropdown

## Next Steps After Testing

1. **Test all features:**
   - Try different presets
   - Create custom dimensions
   - Save a new preset
   - Adjust support angle
   - Place multiple volumes

2. **Report issues:**
   - Create a GitHub issue if you find bugs
   - Include Cura version and error logs

3. **Ready for stable release?**
   - If everything works, you can create v1.0.0!
   - If issues found, fix them and create v1.0.0-beta.2

---

## Quick Reference

**Plugin folder location (via Cura):** Help → Show Configuration Folder → plugins/

**Activate tool:** Click icon or press **E** key

**Remove volume:** Click on an existing volume

**View logs:** Help → Show Log File

**Restart Cura:** Close completely and reopen
