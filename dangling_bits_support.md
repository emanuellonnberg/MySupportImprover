# Dangling Bits Support - Differentiated Support Strategy

## Overview

This document outlines a new approach to supporting "dangling bits" in 3D printing that recognizes the different structural requirements of various parts of an overhang.

## The Core Insight

Traditional support generation treats all overhanging surfaces uniformly - if a face exceeds the overhang threshold angle, it gets support. However, **dangling bits have differentiated support needs**:

### Two Types of Support Requirements

| Type | Location | Purpose | Physical Requirement |
|------|----------|---------|---------------------|
| **Structural Support** | Under the tip/lowest point | Bear weight and printing forces | Solid, load-bearing column to build plate |
| **Stability Support** | Along the side edges | Prevent lateral movement, drooping, curling | Minimal - just needs to "pin" geometry in place |

```
        DANGLING BIT CROSS-SECTION

             ╔═══════════╗
             ║           ║ ← Sides: stability support only
             ║  dangling ║   (prevent drooping/curling)
             ║    bit    ║
             ╚═════╤═════╝
                   │
                   ▼ ← Tip: structural support
                   │    (bears the load)
              ┌────┴────┐
              │ support │
              │ column  │
              └────┬────┘
        ═══════════╧═══════════ build plate
```

## Why This Matters

### Current Approach Problems
- Full support under all overhanging surfaces
- Wastes material on sides that don't need load-bearing support
- More post-processing to remove supports
- Risk of surface damage from dense side supports

### Differentiated Approach Benefits
- **Less material**: Thin edge supports use fraction of filament
- **Easier removal**: Minimal side supports snap off cleanly
- **Better surface quality**: Less contact = less scarring
- **Structural integrity maintained**: Tip still gets proper support

## Technical Analysis

### What the Tip Needs (Structural)
- Traditional support column/tower
- Adequate cross-section to bear weight
- Connection to build plate or lower model geometry
- Standard support settings (density, pattern, interface layers)

### What the Sides Need (Stability)
The sides only need to be prevented from:
1. **Drooping** during printing (gravity while hot)
2. **Curling** during cooling (thermal contraction)
3. **Vibrating** from print head movement

This can be achieved with **minimal edge supports**:
- Thin walls/fins along the perimeter
- Low-density contact
- Just enough to "hold it in place"

## Implementation Approaches

### Approach 1: Multiple Modifier Volumes

Use the existing `cutting_mesh` system to create regions with different support settings.

**Under the tip:**
```python
tip_volume_settings = {
    "support_enable": True,
    "support_pattern": "grid",        # or zigzag
    "support_infill_rate": 15-20,     # standard density
    "support_z_distance": 0.2,        # normal gap
}
```

**Along the edges:**
```python
edge_volume_settings = {
    "support_enable": True,
    "support_pattern": "lines",       # thinnest pattern
    "support_infill_rate": 5-10,      # very sparse
    "support_line_width": 0.2-0.3,    # minimal width
    "support_wall_count": 1,          # single wall
}
```

**Pros:**
- Works within existing Cura support system
- No custom geometry generation needed
- Leverages proven support algorithms

**Cons:**
- Less precise control over exact support shape
- Still generates "fill" rather than true edge rails
- Multiple volumes to manage

### Approach 2: Custom Support Mesh Generation

Generate actual `support_mesh` geometry instead of modifier volumes.

**Structural support (under tip):**
```python
def create_tip_support(tip_position, target_z=0):
    """Generate support column from tip to build plate"""
    # Conical or cylindrical column
    # Cross-section based on estimated load
    # Tapers toward tip for easier removal
```

**Stability support (edge rails):**
```python
def create_edge_rails(boundary_edges, rail_width=0.4, rail_height=2.0):
    """Generate thin fins along boundary edges"""
    # Thin walls perpendicular to edge direction
    # Just tall enough to prevent drooping
    # Minimal contact area
```

```
    TOP VIEW OF EDGE RAILS

    ┌─────────────────────┐
    │                     │
    ╠═╗                 ╔═╣  ← thin rail supports
    ║ ║   dangling bit  ║ ║    along edges
    ╠═╝                 ╚═╣
    │                     │
    └─────────────────────┘
```

**Pros:**
- Complete control over support geometry
- True minimal edge supports possible
- Optimal material usage

**Cons:**
- More complex implementation
- Must handle collision detection
- Need to generate valid mesh geometry

### Approach 3: Hybrid - Structural Volume + Edge Detection

Combine automatic detection with targeted support generation:

1. **Detect the dangling region** (using existing overhang detection)
2. **Classify the geometry:**
   - Find the "tip" (lowest Z, or most severe angle)
   - Find the "boundary edges" (where overhang meets non-overhang)
3. **Generate appropriate support:**
   - Modifier volume under tip with standard settings
   - Custom edge rails along boundary, OR
   - Very thin modifier ribbons with minimal settings

## Detection Algorithm

### Finding the Tip
```python
def find_structural_point(overhang_region, mesh_data):
    """Identify the point that needs structural support"""
    vertices = get_region_vertices(overhang_region, mesh_data)

    # Option A: Lowest Z coordinate
    tip_vertex = vertices[np.argmin(vertices[:, 2])]

    # Option B: Most severe overhang angle
    # (already computed during overhang detection)

    # Option C: Centroid of most severe area
    # (weighted by angle severity)

    return tip_vertex
```

### Finding Boundary Edges
```python
def find_boundary_edges(overhang_region, adjacency, overhang_mask):
    """Find edges between overhang and non-overhang faces"""
    boundary_edges = []

    for face_id in overhang_region:
        for neighbor_id in adjacency[face_id]:
            if not overhang_mask[neighbor_id]:
                # This edge is on the boundary
                edge = get_shared_edge(face_id, neighbor_id)
                boundary_edges.append(edge)

    return boundary_edges
```

## Leveraging Cura's Settings

The key insight is that Cura's existing support settings can be configured very differently for structural vs stability support. By using multiple `cutting_mesh` modifier volumes with different settings, we can achieve differentiated support without generating custom geometry.

### Structural Support Settings (Under Tip)

Standard robust support configuration:

| Setting | Value | Purpose |
|---------|-------|---------|
| `support_pattern` | `grid` or `zigzag` | Strong cross-linked structure |
| `support_infill_rate` | 15-20% | Adequate density for load |
| `support_line_width` | 0.4mm | Standard line width |
| `support_wall_count` | 0-1 | Optional perimeter |
| `support_z_distance` | 0.2mm | Normal gap for removal |
| `support_interface_enable` | True | Dense top for clean surface |
| `support_interface_density` | 80-100% | Solid contact layer |

### Stability Support Settings (Edge Rails)

Minimal configuration for side stabilization:

| Setting | Value | Purpose |
|---------|-------|---------|
| `support_pattern` | `lines` | Thinnest possible pattern |
| `support_infill_rate` | 5-10% | Very sparse - just enough contact |
| `support_line_width` | 0.2-0.3mm | Thinner than normal |
| `support_wall_count` | 1 | Single thin wall along edge |
| `support_z_distance` | 0.15-0.2mm | Can be slightly closer |
| `support_xy_distance` | 0.2-0.4mm | Close to edge for stability |
| `support_interface_enable` | False | No dense layer needed |
| `support_roof_enable` | False | Skip roof entirely |
| `support_bottom_enable` | False | Skip floor for easy removal |

### Key Settings Combinations

**"Wall Only" Support (Maximum Minimal)**
```
support_wall_count = 1
support_infill_rate = 0
support_pattern = lines
```
This creates just a thin perimeter wall with no infill - essentially a hollow shell that stabilizes without bulk.

**"Single Line" Support**
```
support_pattern = lines
support_line_distance = 999  (very large)
support_wall_count = 0
```
This attempts to create just individual support lines rather than a filled area.

### Settings Available via Cutting Mesh

The plugin currently injects these settings into cutting meshes:
- `support_z_distance`
- `support_top_distance`
- `support_xy_distance`
- `support_bottom_distance`
- `support_angle`

**To implement differentiated support, we need to also expose:**
- `support_pattern`
- `support_infill_rate`
- `support_line_width`
- `support_wall_count`
- `support_interface_enable`
- `support_roof_enable`
- `support_bottom_enable`

This would allow creating "minimal" volumes for edges vs "standard" volumes for tips.

## Edge Rail Geometry Concept

For custom `support_mesh` generation, edge rails could be:

```
    EDGE RAIL CROSS-SECTION

    ════════════════════ model surface
         ▲
         │ gap (support_z_distance)
         ▼
    ┌─────────┐ ← rail height: 1-3mm
    │   rail  │   (enough to stabilize, easy to remove)
    └────┬────┘
         │ ← rail width: 0.4-0.8mm (1-2 line widths)
         │
         ▼
    (continues down to build plate or model)
```

The rail acts as a "fence" that prevents the edge from curling outward during cooling.

## Build Plate vs Model-to-Model Support

### Clear Path to Build Plate
If nothing is between the dangling bit and the build plate:
- Structural support goes directly to plate
- Edge rails extend to plate (or stop at reasonable height)

### Obstructed Path
If another part of the model is below:
- Structural support lands on model surface
- Edge rails may bridge between model surfaces
- More complex collision detection needed

```
    OBSTRUCTED SCENARIO

         ╔═══════╗ dangling bit
         ╚═══╤═══╝
             │ support
    ┌────────┴────────┐
    │   lower model   │ ← support lands here
    │     surface     │
    └─────────────────┘
```

## Implementation Roadmap

### Phase 1: Enhanced Detection
- [ ] Extend overhang detection to identify "tip" vs "boundary"
- [ ] Implement boundary edge finding algorithm
- [ ] Classify overhang regions by type

### Phase 2: Multiple Modifier Volume Approach
- [ ] Auto-generate tip volume with structural settings
- [ ] Auto-generate edge volumes with minimal settings
- [ ] Add UI controls for stability support parameters

### Phase 3: Custom Support Mesh (Optional)
- [ ] Implement edge rail geometry generation
- [ ] Implement tip column geometry generation
- [ ] Add as `support_mesh` type nodes

### Phase 4: Refinement
- [ ] Handle obstructed paths (model-to-model support)
- [ ] Optimize rail dimensions based on material/printer
- [ ] User testing and iteration

## Open Questions

1. **How thin can stability supports be?** Need to test minimum effective rail width for common materials (PLA, ABS, PETG). Likely depends on:
   - Layer height
   - Print speed
   - Cooling capability
   - Overhang length

2. **When is structural support not needed?** Very short overhangs might only need stability support, not full structural. Need to determine thresholds based on:
   - Overhang length (< 5mm might self-bridge?)
   - Material properties
   - Print temperature

3. **Multiple dangling bits?** How to handle complex models with many overhangs efficiently:
   - Batch detection and classification
   - Grouping nearby overhangs
   - Priority ordering by severity

4. **Tree supports as alternative?** Could tree supports naturally provide this differentiated approach? The trunk could act as structural support while branches provide stability. Worth investigating Cura's tree support implementation.

5. **Validation testing?** Need test models with various dangling bit configurations to validate the approach:
   - Single vertical finger
   - Horizontal blade
   - Curved overhang
   - Multiple dangling bits at different heights

## Immediate Next Steps

### Step 1: Extend Plugin Settings

Modify `MySupportImprover.py` to support additional settings in cutting meshes:

```python
# Current settings (line 354-359)
settingsList = {
    "support_z_distance": None,
    "support_top_distance": None,
    "support_xy_distance": None,
    "support_bottom_distance": None,
    "support_angle": None
}

# Add these for differentiated support:
extended_settings = {
    "support_pattern": None,          # lines, grid, triangles, etc.
    "support_infill_rate": None,      # 0-100%
    "support_line_width": None,       # mm
    "support_wall_count": None,       # 0, 1, 2...
    "support_interface_enable": None, # True/False
}
```

### Step 2: Add UI Controls for Support Type

Add a dropdown or toggle in `SupportImprover.qml` to select support mode:
- **Structural** (standard dense support)
- **Stability** (minimal edge support)
- **Custom** (manual settings)

### Step 3: Create Preset Configurations

Add built-in presets for the two support types:

```python
support_presets = {
    "structural": {
        "support_pattern": "grid",
        "support_infill_rate": 15,
        "support_wall_count": 1,
        "support_interface_enable": True,
    },
    "stability": {
        "support_pattern": "lines",
        "support_infill_rate": 5,
        "support_wall_count": 1,
        "support_interface_enable": False,
    }
}
```

### Step 4: Test with Simple Models

Create or find test STL files:
- Simple vertical finger (classic dangling bit)
- Horizontal blade edge
- T-shaped overhang

Test placing structural volume under tip, stability volumes on sides.

## Related Files

- `MySupportImprover.py` - Main plugin implementation
- `improvements.md` - Overhang detection algorithms
- `qt6/SupportImprover.qml` - UI components

## References

- Cura support settings: https://github.com/Ultimaker/Cura
- PySLM overhang detection: https://github.com/drlukeparry/pyslm
- Arc overhang technique: https://github.com/stmcculloch/arc-overhang
