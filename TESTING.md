# Testing Overhang Detection Outside Cura

This guide explains how to extract mesh data from Cura and test overhang detection algorithms independently.

## Quick Start

### 1. Extract Mesh Data from Cura

1. Load a model in Cura
2. Activate the **MySupportImprover** tool (press E key)
3. **Check the "Export Mode" checkbox** in the tool panel
4. **Click on your model**

This will export two files to `~/MySupportImprover_exports/`:
- `mesh_<name>_<timestamp>.stl` - Binary STL file (viewable in any 3D viewer)
- `mesh_<name>_<timestamp>.json` - Detailed mesh data with vertices, indices, normals

### 2. Analyze the Mesh Outside Cura

```bash
cd ~/MySupportImprover
python analyze_mesh.py ~/MySupportImprover_exports/mesh_*.json
```

This will:
- Load the mesh data
- Detect overhang faces (default threshold: 45°)
- Build face adjacency graph
- Find connected overhang regions
- Analyze each region (size, angles, bounding box)
- Export overhang faces to STL for visualization

## Example Output

```
============================================================
MySupportImprover Mesh Analysis
============================================================

Loading mesh from: /home/user/MySupportImprover_exports/mesh_model_20250117.json

Mesh loaded: model
Vertices: 2456
Faces: 4820

Detecting overhangs with threshold angle: 45.0°
Found 342 overhang faces out of 4820 total

Angle distribution:
  45-60°: 234 faces
  60-75°: 89 faces
  75-90°: 19 faces

Building face adjacency graph...
Average neighbors per face: 2.8

Finding connected overhang regions...
Found 3 connected overhang regions
  Region 1: 256 faces
  Region 2: 67 faces
  Region 3: 19 faces

Region analysis:

  Region 1:
    Faces: 256
    Vertices: 312
    Surface area: 456.23 mm²
    Angle range: 45.2° - 73.4°
    Average angle: 52.1°
    Bounding box center: [12.34, -5.67, 45.89]
    Bounding box size: [23.45, 18.90, 12.34]

Exported overhang faces to: mesh_model_20250117_overhangs.stl

============================================================
Analysis complete!
============================================================
```

## Files Generated

### From Cura (Shift+Click):
- `mesh_<name>_<timestamp>.stl` - Full mesh in STL format
- `mesh_<name>_<timestamp>.json` - Detailed mesh data

### From Analysis Script:
- `mesh_<name>_<timestamp>_overhangs.stl` - Only the detected overhang faces

## Viewing Results

1. **Full mesh:** Open `mesh_*.stl` in any 3D viewer (PrusaSlicer, Meshmixer, etc.)
2. **Overhang faces:** Open `mesh_*_overhangs.stl` to see exactly what was detected
3. **Compare:** Load both STLs together to verify detection accuracy

## Debugging Tips

### Check the JSON file
```bash
head -n 20 ~/MySupportImprover_exports/mesh_*.json
```

This shows:
- Vertex count
- Face count
- Whether mesh has indices
- Bounding box information

### Verify STL is valid
```bash
python -c "
import struct
with open('~/MySupportImprover_exports/mesh_*.stl', 'rb') as f:
    f.read(80)  # header
    count = struct.unpack('<I', f.read(4))[0]
    print(f'STL has {count} triangles')
"
```

### Test different angles
Edit `analyze_mesh.py` and change the threshold:
```python
overhang_face_ids, angles, overhang_mask = detect_overhangs(
    vertices, indices, normals, threshold_angle=60.0  # Try different values
)
```

## Why This Approach Works

1. **No Cura complexity** - Test algorithms with pure Python/NumPy
2. **Reproducible** - Same mesh file gives same results
3. **Fast iteration** - No need to restart Cura
4. **Visual verification** - See exactly what's being detected
5. **Easy debugging** - Add print statements anywhere

## Next Steps

Once algorithms work correctly on exported data:
1. Integrate back into Cura plugin
2. Add Job pattern for background processing
3. Add OBB generation around detected regions
4. Create modifier volumes automatically

## Troubleshooting

### "No overhangs detected"
- Check model actually has overhangs
- Try lower threshold angle (30° instead of 45°)
- Verify mesh exported correctly (check JSON file)

### "File not found"
- Check `~/MySupportImprover_exports/` directory exists
- Verify Export Mode checkbox was enabled (check Cura logs)
- Make sure you clicked on the model after enabling Export Mode
- Try absolute path to file

### "Import errors"
- Make sure numpy is installed: `pip install numpy`
- Use Python 3.6+

### Mesh looks weird in viewer
- Check coordinate system (Y-up vs Z-up)
- Verify transformations were applied correctly
- Compare with original model in Cura
