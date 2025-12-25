#!/usr/bin/env python3
"""
Standalone mesh analysis script for MySupportImprover

This script analyzes exported mesh data and tests overhang detection
algorithms WITHOUT needing Cura running.

Usage:
    python analyze_mesh.py path/to/mesh.json
    python analyze_mesh.py path/to/mesh.stl
    python analyze_mesh.py path/to/mesh.json.zip
    python analyze_mesh.py path/to/mesh.stl.zip
"""

import json
import sys
import os
import numpy as np
from collections import deque
import zipfile
import tempfile


def load_mesh_from_json(filepath):
    """Load mesh data from JSON export"""
    with open(filepath, 'r') as f:
        data = json.load(f)

    vertices = np.array(data['vertices'], dtype=np.float32)

    if data['has_indices']:
        indices = np.array(data['indices'], dtype=np.int32)
    else:
        # Create indices for non-indexed mesh
        indices = np.arange(len(vertices)).reshape(-1, 3)

    normals = None
    if 'normals' in data:
        normals = np.array(data['normals'], dtype=np.float32)

    # Extract clicked position data if available
    clicked_data = {}
    if 'clicked_position' in data:
        clicked_data['position'] = np.array(data['clicked_position'], dtype=np.float32)
        clicked_data['closest_face_id'] = data.get('closest_face_id')
        clicked_data['closest_face_distance'] = data.get('closest_face_distance')

    return {
        'vertices': vertices,
        'indices': indices,
        'normals': normals,
        'clicked_data': clicked_data,
        'metadata': {
            'name': data.get('node_name', 'unknown'),
            'vertex_count': data['vertex_count'],
            'face_count': data.get('face_count', len(indices)),
            'bounds': data.get('bounds', {})
        }
    }


def load_mesh_from_stl(filepath):
    """Load mesh data from binary STL file"""
    import struct

    with open(filepath, 'rb') as f:
        # Read header (80 bytes)
        header = f.read(80)

        # Read face count
        face_count = struct.unpack("<I", f.read(4))[0]

        vertices = []
        indices = []

        vertex_map = {}  # Map vertex tuple to index
        next_vertex_id = 0

        for i in range(face_count):
            # Read normal (we'll recalculate these)
            normal = struct.unpack("<fff", f.read(12))

            # Read 3 vertices
            face_indices = []
            for j in range(3):
                v = struct.unpack("<fff", f.read(12))

                # Check if we've seen this vertex
                v_tuple = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
                if v_tuple not in vertex_map:
                    vertex_map[v_tuple] = next_vertex_id
                    vertices.append(v)
                    next_vertex_id += 1

                face_indices.append(vertex_map[v_tuple])

            indices.append(face_indices)

            # Read attribute byte count
            f.read(2)

        return {
            'vertices': np.array(vertices, dtype=np.float32),
            'indices': np.array(indices, dtype=np.int32),
            'normals': None,
            'clicked_data': {},  # STL files don't have clicked position data
            'metadata': {
                'name': os.path.basename(filepath),
                'vertex_count': len(vertices),
                'face_count': face_count
            }
        }


def rebuild_indexed_mesh(vertices):
    """Rebuild index buffer for non-indexed mesh by merging duplicate vertices"""
    print("Rebuilding index buffer from non-indexed mesh...")
    print(f"Original vertices: {len(vertices)}")

    # Create a dictionary to find duplicate vertices
    vertex_map = {}
    unique_vertices = []
    indices = []

    tolerance = 1e-6  # Vertices within this distance are considered the same

    for i in range(0, len(vertices), 3):
        # Process each triangle (3 vertices)
        triangle_indices = []

        for j in range(3):
            if i + j >= len(vertices):
                break

            v = vertices[i + j]

            # Round vertex coordinates to find duplicates
            v_key = tuple(np.round(v / tolerance) * tolerance)

            if v_key in vertex_map:
                # Reuse existing vertex
                triangle_indices.append(vertex_map[v_key])
            else:
                # Add new unique vertex
                vertex_idx = len(unique_vertices)
                unique_vertices.append(v)
                vertex_map[v_key] = vertex_idx
                triangle_indices.append(vertex_idx)

        if len(triangle_indices) == 3:
            indices.append(triangle_indices)

    unique_vertices = np.array(unique_vertices, dtype=np.float32)
    indices = np.array(indices, dtype=np.int32)

    print(f"Unique vertices: {len(unique_vertices)}")
    print(f"Faces: {len(indices)}")
    print(f"Vertex reduction: {100 * (1 - len(unique_vertices)/len(vertices)):.1f}%")

    return unique_vertices, indices


def compute_face_normals(vertices, indices):
    """Calculate face normals from vertices and indices"""
    print("Computing face normals...")

    # Get triangle vertices
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]

    # Compute normals via cross product
    edge1 = v1 - v0
    edge2 = v2 - v0
    normals = np.cross(edge1, edge2)

    # Normalize
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(lengths, 1e-10)

    return normals


def detect_overhangs(vertices, indices, normals=None, threshold_angle=45.0):
    """Detect overhang faces using normal vector analysis"""
    print(f"\nDetecting overhangs with threshold angle: {threshold_angle}°")

    # Compute face normals if not provided
    if normals is None:
        normals = compute_face_normals(vertices, indices)

    # Build direction (downward in Z)
    build_direction = np.array([[0., 0., -1.0]])

    # Compute angles for all faces (vectorized)
    dot_products = np.dot(build_direction, normals.T)
    angles = np.degrees(np.arccos(np.clip(dot_products, -1.0, 1.0))).flatten()

    # Identify overhangs
    overhang_mask = angles > threshold_angle
    overhang_face_ids = np.where(overhang_mask)[0]

    print(f"Found {len(overhang_face_ids)} overhang faces out of {len(angles)} total")

    return overhang_face_ids, angles, overhang_mask


def build_face_adjacency_graph(indices):
    """Build adjacency list for mesh faces"""
    print("Building face adjacency graph...")

    face_count = len(indices)

    # Create edge-to-face mapping
    edge_to_faces = {}
    for face_id, face in enumerate(indices):
        for i in range(3):
            # Create edge key (sorted for consistency)
            edge = tuple(sorted([face[i], face[(i+1)%3]]))
            if edge not in edge_to_faces:
                edge_to_faces[edge] = []
            edge_to_faces[edge].append(face_id)

    # Build adjacency list
    adjacency = {i: [] for i in range(face_count)}
    for edge, faces in edge_to_faces.items():
        if len(faces) == 2:  # Interior edge
            adjacency[faces[0]].append(faces[1])
            adjacency[faces[1]].append(faces[0])

    avg_neighbors = np.mean([len(neighbors) for neighbors in adjacency.values()])
    print(f"Average neighbors per face: {avg_neighbors:.1f}")

    return adjacency


def find_connected_overhang_regions(overhang_face_ids, overhang_mask, adjacency):
    """Find connected overhang regions using BFS"""
    print("Finding connected overhang regions...")

    regions = []
    visited = set()

    for seed_face in overhang_face_ids:
        if seed_face in visited:
            continue

        # BFS from seed
        queue = deque([seed_face])
        region = []

        while queue:
            face_id = queue.popleft()

            if face_id in visited or not overhang_mask[face_id]:
                continue

            visited.add(face_id)
            region.append(face_id)

            for neighbor in adjacency.get(face_id, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        if region:
            regions.append(region)

    print(f"Found {len(regions)} connected overhang regions")
    for i, region in enumerate(regions):
        print(f"  Region {i+1}: {len(region)} faces")

    return regions


def analyze_overhang_region(region_face_ids, vertices, indices, angles):
    """Analyze properties of an overhang region"""
    # Filter out invalid face IDs
    max_face_id = len(indices) - 1
    valid_face_ids = [fid for fid in region_face_ids if fid <= max_face_id]

    if len(valid_face_ids) < len(region_face_ids):
        print(f"Warning: Filtered out {len(region_face_ids) - len(valid_face_ids)} invalid face IDs")

    region_face_ids = np.array(valid_face_ids)
    region_faces = indices[region_face_ids]
    region_vertex_ids = np.unique(region_faces.flatten())
    region_vertices = vertices[region_vertex_ids]

    # Calculate surface area
    v0 = vertices[region_faces[:, 0]]
    v1 = vertices[region_faces[:, 1]]
    v2 = vertices[region_faces[:, 2]]

    edge1 = v1 - v0
    edge2 = v2 - v0
    cross_products = np.cross(edge1, edge2)
    areas = 0.5 * np.linalg.norm(cross_products, axis=1)
    surface_area = np.sum(areas)

    # Get angle statistics
    region_angles = angles[region_face_ids]

    # Compute bounding box
    min_point = np.min(region_vertices, axis=0)
    max_point = np.max(region_vertices, axis=0)
    center = (min_point + max_point) / 2
    extents = (max_point - min_point) / 2

    return {
        'face_count': len(region_face_ids),
        'vertex_count': len(region_vertex_ids),
        'surface_area': surface_area,
        'min_angle': np.min(region_angles),
        'max_angle': np.max(region_angles),
        'avg_angle': np.mean(region_angles),
        'bbox_center': center,
        'bbox_extents': extents,
        'bbox_size': extents * 2
    }


def export_overhang_faces(filepath, vertices, indices, overhang_face_ids):
    """Export only the overhang faces to STL for visualization"""
    import struct

    # Filter out invalid face IDs
    max_face_id = len(indices) - 1
    valid_face_ids = overhang_face_ids[overhang_face_ids <= max_face_id]

    if len(valid_face_ids) < len(overhang_face_ids):
        print(f"Warning: Filtered out {len(overhang_face_ids) - len(valid_face_ids)} invalid face IDs before export")

    overhang_faces = indices[valid_face_ids]

    with open(filepath, 'wb') as f:
        # STL header
        header = b'Overhang faces from MySupportImprover analysis'
        header = header.ljust(80, b'\x00')
        f.write(header)

        # Face count
        f.write(struct.pack("<I", len(overhang_faces)))

        # Write faces
        for face in overhang_faces:
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            # Compute normal
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)
            normal_length = np.linalg.norm(normal)
            if normal_length > 1e-10:
                normal = normal / normal_length
            else:
                normal = np.array([0.0, 0.0, 1.0])

            # Write normal and vertices
            f.write(struct.pack("<fff", float(normal[0]), float(normal[1]), float(normal[2])))
            f.write(struct.pack("<fff", float(v0[0]), float(v0[1]), float(v0[2])))
            f.write(struct.pack("<fff", float(v1[0]), float(v1[1]), float(v1[2])))
            f.write(struct.pack("<fff", float(v2[0]), float(v2[1]), float(v2[2])))
            f.write(struct.pack("<H", 0))

    print(f"Exported overhang faces to: {filepath}")


def extract_from_zip(zip_path):
    """Extract file from zip and return path to extracted file"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Get list of files in zip
        file_list = zip_ref.namelist()

        # Find JSON or STL file
        for filename in file_list:
            if filename.endswith('.json') or filename.endswith('.stl'):
                # Extract to temp directory
                temp_dir = tempfile.mkdtemp()
                extracted_path = zip_ref.extract(filename, temp_dir)
                print(f"Extracted {filename} from zip archive")
                return extracted_path

        print("Error: No .json or .stl file found in zip archive")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_mesh.py <mesh_file>")
        print("\nSupported formats:")
        print("  - mesh.json")
        print("  - mesh.stl")
        print("  - mesh.json.zip")
        print("  - mesh.stl.zip")
        print("\nThis script analyzes mesh data exported from MySupportImprover")
        print("and tests overhang detection algorithms.")
        sys.exit(1)

    filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    print("=" * 60)
    print("MySupportImprover Mesh Analysis")
    print("=" * 60)

    # Handle zipped files
    if filepath.endswith('.zip'):
        print(f"\nExtracting from zip: {filepath}")
        filepath = extract_from_zip(filepath)

    # Load mesh
    print(f"\nLoading mesh from: {filepath}")

    if filepath.endswith('.json'):
        print("Loading JSON format (may take a moment for large files)...")
        mesh = load_mesh_from_json(filepath)
    elif filepath.endswith('.stl'):
        print("Loading STL format...")
        mesh = load_mesh_from_stl(filepath)
    else:
        print("Error: Unsupported file format. Use .json, .stl, or .zip")
        sys.exit(1)

    vertices = mesh['vertices']
    indices = mesh['indices']
    normals = mesh['normals']
    metadata = mesh['metadata']
    clicked_data = mesh.get('clicked_data', {})

    print(f"\nMesh loaded: {metadata['name']}")
    print(f"Vertices: {metadata['vertex_count']}")
    print(f"Faces: {metadata['face_count']}")

    if 'bounds' in metadata:
        bounds = metadata['bounds']
        if bounds:
            print(f"Bounds: {bounds}")

    # Check if this is a non-indexed mesh (vertices stored as triplets)
    # This happens when has_indices is false in the JSON
    if len(vertices) == len(indices) * 3:
        print("\n⚠️  Non-indexed mesh detected (vertices as triplets)")
        print("Rebuilding index buffer to enable connectivity analysis...")
        vertices, indices = rebuild_indexed_mesh(vertices)

    # Display clicked position if available
    if clicked_data and 'position' in clicked_data:
        pos = clicked_data['position']
        print(f"\n🎯 Clicked Position: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")
        if 'closest_face_id' in clicked_data and clicked_data['closest_face_id'] is not None:
            print(f"   Closest face ID: {clicked_data['closest_face_id']}")
            if 'closest_face_distance' in clicked_data:
                print(f"   Distance to face: {clicked_data['closest_face_distance']:.2f} mm")

    # Detect overhangs
    overhang_face_ids, angles, overhang_mask = detect_overhangs(
        vertices, indices, normals, threshold_angle=45.0
    )

    if len(overhang_face_ids) == 0:
        print("\nNo overhangs detected!")
        return

    # Angle distribution
    print("\nAngle distribution:")
    bins = [0, 30, 45, 60, 75, 90, 180]
    hist, _ = np.histogram(angles[overhang_face_ids], bins=bins)
    for i in range(len(bins)-1):
        print(f"  {bins[i]}-{bins[i+1]}°: {hist[i]} faces")

    # Build adjacency graph
    adjacency = build_face_adjacency_graph(indices)

    # Find connected regions
    regions = find_connected_overhang_regions(overhang_face_ids, overhang_mask, adjacency)

    # Sort regions by size (largest first) and analyze only top regions
    regions_sorted = sorted(enumerate(regions), key=lambda x: len(x[1]), reverse=True)
    max_regions_to_analyze = min(20, len(regions))  # Analyze top 20 or fewer

    print(f"\nAnalyzing top {max_regions_to_analyze} largest overhang regions (out of {len(regions)} total):")
    clicked_region = None

    for rank, (original_idx, region) in enumerate(regions_sorted[:max_regions_to_analyze]):
        analysis = analyze_overhang_region(region, vertices, indices, angles)

        # Check if this region contains the clicked face
        is_clicked_region = False
        if clicked_data and 'closest_face_id' in clicked_data and clicked_data['closest_face_id'] is not None:
            if clicked_data['closest_face_id'] in region:
                is_clicked_region = True
                clicked_region = rank + 1

        region_label = f"Region #{rank+1} (#{original_idx+1} overall)"
        if is_clicked_region:
            region_label += " 🎯 (CLICKED)"

        print(f"\n  {region_label}:")
        print(f"    Faces: {analysis['face_count']}")
        print(f"    Vertices: {analysis['vertex_count']}")
        print(f"    Surface area: {analysis['surface_area']:.2f} mm²")
        print(f"    Angle range: {analysis['min_angle']:.1f}° - {analysis['max_angle']:.1f}°")
        print(f"    Average angle: {analysis['avg_angle']:.1f}°")
        print(f"    Bounding box center: [{analysis['bbox_center'][0]:.2f}, {analysis['bbox_center'][1]:.2f}, {analysis['bbox_center'][2]:.2f}]")
        print(f"    Bounding box size: [{analysis['bbox_size'][0]:.2f}, {analysis['bbox_size'][1]:.2f}, {analysis['bbox_size'][2]:.2f}]")

    # Highlight clicked region
    if clicked_region:
        print(f"\n💡 You clicked on Region {clicked_region} - this is the overhang you're interested in!")

    # Export overhang faces
    output_dir = os.path.dirname(filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    overhang_stl = os.path.join(output_dir, f"{base_name}_overhangs.stl")
    export_overhang_faces(overhang_stl, vertices, indices, overhang_face_ids)

    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
