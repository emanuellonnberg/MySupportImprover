"""
Unit tests for MySupportImprover core algorithms.

These tests focus on the pure algorithmic parts that don't require
the full Cura framework - overhang detection, edge merging, etc.
"""

import json
import os
import unittest
import numpy as np
from collections import deque
from typing import List, Dict, Set, Tuple
import math


# ============================================================================
# Extracted algorithm functions for testing
# These are standalone versions of the algorithms from MySupportImprover.py
# ============================================================================

def compute_face_normals(vertices: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Calculate face normals from vertices and indices."""
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]

    edge1 = v1 - v0
    edge2 = v2 - v0
    normals = np.cross(edge1, edge2)

    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(lengths, 1e-10)

    return normals


def build_face_adjacency_graph(indices: np.ndarray) -> Dict[int, List[int]]:
    """Build adjacency list for mesh faces."""
    face_count = len(indices)

    edge_to_faces: Dict[Tuple[int, int], List[int]] = {}
    for face_id, face in enumerate(indices):
        for i in range(3):
            edge = tuple(sorted([int(face[i]), int(face[(i + 1) % 3])]))
            if edge not in edge_to_faces:
                edge_to_faces[edge] = []
            edge_to_faces[edge].append(face_id)

    adjacency: Dict[int, List[int]] = {i: [] for i in range(face_count)}
    for edge, faces in edge_to_faces.items():
        if len(faces) == 2:
            adjacency[faces[0]].append(faces[1])
            adjacency[faces[1]].append(faces[0])

    return adjacency


def find_connected_overhang_region(seed_face_id: int, overhang_mask: np.ndarray,
                                    adjacency: Dict[int, List[int]]) -> List[int]:
    """BFS to find connected overhang region from seed face."""
    if seed_face_id >= len(overhang_mask) or not overhang_mask[seed_face_id]:
        return []

    visited: Set[int] = set()
    queue = deque([seed_face_id])
    region: List[int] = []

    while queue:
        face_id = queue.popleft()

        if face_id in visited:
            continue

        if not overhang_mask[face_id]:
            continue

        visited.add(face_id)
        region.append(face_id)

        for neighbor_id in adjacency.get(face_id, []):
            if neighbor_id not in visited:
                queue.append(neighbor_id)

    return region


def detect_overhangs(vertices: np.ndarray, indices: np.ndarray,
                     threshold_angle: float = 45.0) -> Tuple[np.ndarray, np.ndarray]:
    """Detect overhang faces using normal vector analysis."""
    face_normals = compute_face_normals(vertices, indices)

    build_direction = np.array([[0., -1., 0.]])
    dot_products = np.dot(face_normals, build_direction.T).flatten()
    dot_products = np.clip(dot_products, -1.0, 1.0)
    angles = np.degrees(np.arccos(dot_products))

    overhang_mask = angles < (90 - threshold_angle)
    overhang_face_ids = np.where(overhang_mask)[0]

    return overhang_face_ids, angles


def rebuild_indexed_mesh(vertices: np.ndarray, tolerance: float = 1e-4) -> Tuple[np.ndarray, np.ndarray]:
    """Rebuild index buffer for non-indexed mesh by merging duplicate vertices."""
    vertex_map = {}
    unique_vertices = []
    indices = []

    for i in range(0, len(vertices), 3):
        triangle_indices = []
        for j in range(3):
            if i + j >= len(vertices):
                break
            vertex = vertices[i + j]
            vertex_key = tuple(np.round(vertex / tolerance) * tolerance)

            if vertex_key in vertex_map:
                triangle_indices.append(vertex_map[vertex_key])
            else:
                vertex_idx = len(unique_vertices)
                unique_vertices.append(vertex)
                vertex_map[vertex_key] = vertex_idx
                triangle_indices.append(vertex_idx)

        if len(triangle_indices) == 3:
            indices.append(triangle_indices)

    unique_vertices = np.array(unique_vertices, dtype=np.float32)
    indices = np.array(indices, dtype=np.int32)

    return unique_vertices, indices


def mesh_needs_index_rebuild(vertices: np.ndarray, indices: np.ndarray) -> bool:
    """Return True when indexed mesh has no shared vertices (triangle soup)."""
    if len(vertices) == 0 or len(indices) == 0:
        return False
    flat_indices = np.array(indices, dtype=np.int32).reshape(-1)
    if len(flat_indices) == 0:
        return False
    usage = np.bincount(flat_indices, minlength=len(vertices))
    return int(usage.max()) <= 1


def load_exported_mesh(json_path: str) -> Tuple[np.ndarray, np.ndarray, int, bool]:
    """Load exported mesh data from JSON and return indexed geometry."""
    with open(json_path, "r") as handle:
        data = json.load(handle)

    raw_vertices = np.array(data["vertices"], dtype=np.float32)
    has_indices = bool(data.get("has_indices"))

    if has_indices:
        indices = np.array(data["indices"], dtype=np.int32)
        vertices = raw_vertices
        if mesh_needs_index_rebuild(vertices, indices):
            expanded_vertices = indices.reshape(-1)
            vertices, indices = rebuild_indexed_mesh(vertices[expanded_vertices])
    else:
        vertices, indices = rebuild_indexed_mesh(raw_vertices)

    return vertices, indices, len(raw_vertices), has_indices


def find_connected_overhang_regions(overhang_face_ids: np.ndarray,
                                    overhang_mask: np.ndarray,
                                    adjacency: Dict[int, List[int]]) -> List[List[int]]:
    """Find all connected overhang regions using BFS."""
    visited: Set[int] = set()
    regions: List[List[int]] = []

    for face_id in overhang_face_ids:
        if face_id in visited:
            continue
        if not overhang_mask[face_id]:
            continue

        region = []
        queue = deque([face_id])

        while queue:
            current_face = queue.popleft()
            if current_face in visited:
                continue
            if not overhang_mask[current_face]:
                continue

            visited.add(current_face)
            region.append(current_face)

            for neighbor in adjacency.get(current_face, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        regions.append(region)

    return regions


def compute_region_bounds(vertices: np.ndarray, indices: np.ndarray,
                          region_face_ids: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    """Return (min_bounds, max_bounds) for the given region."""
    region_vertices = []
    for face_id in region_face_ids:
        face = indices[face_id]
        region_vertices.extend([
            vertices[face[0]],
            vertices[face[1]],
            vertices[face[2]],
        ])

    region_vertices = np.array(region_vertices, dtype=np.float32)
    min_bounds = region_vertices.min(axis=0)
    max_bounds = region_vertices.max(axis=0)

    return min_bounds, max_bounds


def compute_face_centers(vertices: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Compute face centroids for all faces."""
    v0 = vertices[indices[:, 0]]
    v1 = vertices[indices[:, 1]]
    v2 = vertices[indices[:, 2]]
    return (v0 + v1 + v2) / 3.0


def build_vertex_adjacency(indices: np.ndarray, vertex_count: int) -> List[Set[int]]:
    """Build adjacency list for vertices based on shared edges."""
    adjacency: List[Set[int]] = [set() for _ in range(vertex_count)]
    for face in indices:
        v0 = int(face[0])
        v1 = int(face[1])
        v2 = int(face[2])
        adjacency[v0].update([v1, v2])
        adjacency[v1].update([v0, v2])
        adjacency[v2].update([v0, v1])
    return adjacency


def detect_dangling_vertices(vertices: np.ndarray, indices: np.ndarray,
                             face_mask: np.ndarray, min_drop: float = 0.05) -> np.ndarray:
    """Detect vertices with no neighboring vertices below them on candidate faces."""
    dangling = np.zeros(len(vertices), dtype=bool)
    candidate_faces = np.where(face_mask)[0]
    if len(candidate_faces) == 0:
        return dangling

    vertex_ids = np.unique(indices[candidate_faces])
    adjacency = build_vertex_adjacency(indices, len(vertices))

    for vertex_id in vertex_ids:
        neighbors = adjacency[int(vertex_id)]
        if not neighbors:
            dangling[int(vertex_id)] = True
            continue

        v_y = vertices[int(vertex_id)][1]
        has_lower = any(vertices[n][1] < (v_y - min_drop) for n in neighbors)
        if not has_lower:
            dangling[int(vertex_id)] = True

    return dangling


def detect_dangling_faces(indices: np.ndarray, dangling_vertex_mask: np.ndarray,
                          face_mask: np.ndarray) -> np.ndarray:
    """Detect candidate faces that touch a dangling vertex."""
    if len(indices) == 0:
        return np.array([], dtype=np.int32)
    face_has_dangling = np.any(dangling_vertex_mask[indices], axis=1)
    face_mask = face_has_dangling & face_mask
    return np.where(face_mask)[0].astype(np.int32)


def find_dangling_vertex_regions(vertices: np.ndarray, indices: np.ndarray,
                                 min_drop: float, min_face_y: float
                                 ) -> Tuple[List[Set[int]], List[Set[int]]]:
    """Find connected vertex regions where no vertex has a lower neighbor."""
    if len(vertices) == 0 or len(indices) == 0:
        return [], []

    adjacency = build_vertex_adjacency(indices, len(vertices))
    vertex_y = vertices[:, 1]
    eligible = vertex_y > min_face_y

    has_lower = np.zeros(len(vertices), dtype=bool)
    for vertex_id in range(len(vertices)):
        if not eligible[vertex_id]:
            continue
        v_y = vertex_y[vertex_id]
        for neighbor in adjacency[vertex_id]:
            if vertex_y[neighbor] < (v_y - min_drop):
                has_lower[vertex_id] = True
                break

    dangling_mask = eligible & ~has_lower
    seeds = np.where(dangling_mask)[0]

    assigned = np.zeros(len(vertices), dtype=bool)
    regions: List[Set[int]] = []
    for seed in seeds:
        if assigned[seed]:
            continue
        region = {seed}
        assigned[seed] = True
        queue = deque([seed])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if assigned[neighbor] or not dangling_mask[neighbor]:
                    continue
                assigned[neighbor] = True
                region.add(neighbor)
                queue.append(neighbor)
        if region:
            regions.append(region)

    return regions, adjacency


def merge_small_dangling_regions(regions: List[Set[int]], adjacency: List[Set[int]],
                                 min_vertices: int) -> List[Set[int]]:
    """Merge small dangling regions into a single neighboring region."""
    if not regions:
        return regions

    region_id = [-1] * len(adjacency)
    for idx, region in enumerate(regions):
        for vertex_id in region:
            region_id[int(vertex_id)] = idx

    region_sizes = [len(region) for region in regions]
    small = [size < min_vertices for size in region_sizes]
    parent = list(range(len(regions)))

    def find_root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra = find_root(a)
        rb = find_root(b)
        if ra != rb:
            parent[rb] = ra

    region_neighbors = [set() for _ in range(len(regions))]
    for vertex_id, neighbors in enumerate(adjacency):
        region_a = region_id[vertex_id]
        if region_a < 0:
            continue
        for neighbor in neighbors:
            region_b = region_id[neighbor]
            if region_b < 0 or region_a == region_b:
                continue
            region_neighbors[region_a].add(region_b)

    for idx, is_small in enumerate(small):
        if not is_small:
            continue
        neighbors = region_neighbors[idx]
        if not neighbors:
            continue
        best_neighbor = max(neighbors, key=lambda n: region_sizes[n])
        union(idx, best_neighbor)

    merged: Dict[int, Set[int]] = {}
    for idx, region in enumerate(regions):
        root = find_root(idx)
        merged.setdefault(root, set()).update(region)

    return list(merged.values())


def expand_dangling_face_region(seed_faces: np.ndarray,
                                adjacency: Dict[int, List[int]],
                                candidate_mask: np.ndarray,
                                max_faces: int,
                                max_depth: int) -> List[int]:
    """Expand seed faces into a local candidate-face region."""
    if seed_faces is None or len(seed_faces) == 0:
        return []

    visited = set(int(face_id) for face_id in seed_faces)
    queue = deque((int(face_id), 0) for face_id in seed_faces)

    while queue:
        face_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in adjacency.get(face_id, []):
            if neighbor in visited:
                continue
            if not candidate_mask[neighbor]:
                continue
            visited.add(neighbor)
            if len(visited) >= max_faces:
                return list(visited)
            queue.append((neighbor, depth + 1))

    return list(visited)


def merge_overlapping_face_regions(regions: List[List[int]]) -> List[List[int]]:
    """Merge face regions that overlap."""
    if not regions:
        return []

    region_sets = [set(region) for region in regions]
    parent = list(range(len(region_sets)))

    def find_root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra = find_root(a)
        rb = find_root(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(region_sets)):
        for j in range(i + 1, len(region_sets)):
            if region_sets[i] & region_sets[j]:
                union(i, j)

    merged: Dict[int, Set[int]] = {}
    for idx, region in enumerate(region_sets):
        root = find_root(idx)
        merged.setdefault(root, set()).update(region)

    return [list(region) for region in merged.values()]


def dangling_vertex_regions_to_faces(vertex_regions: List[Set[int]],
                                     indices: np.ndarray,
                                     face_mask: np.ndarray | None = None
                                     ) -> List[List[int]]:
    """Convert dangling vertex regions to face regions, with a loose fallback."""
    if not vertex_regions or len(indices) == 0:
        return []

    vertex_count = int(indices.max()) + 1 if len(indices) else 0
    region_id = [-1] * vertex_count
    for idx, region in enumerate(vertex_regions):
        for vertex_id in region:
            region_id[int(vertex_id)] = idx

    face_regions: List[List[int]] = [[] for _ in range(len(vertex_regions))]
    loose_regions: List[List[int]] = [[] for _ in range(len(vertex_regions))]
    for face_id, face in enumerate(indices):
        if face_mask is not None and not bool(face_mask[face_id]):
            continue
        v0, v1, v2 = int(face[0]), int(face[1]), int(face[2])
        rid = region_id[v0]
        if rid >= 0 and rid == region_id[v1] == region_id[v2]:
            face_regions[rid].append(face_id)
            continue
        region_ids = [region_id[v0], region_id[v1], region_id[v2]]
        region_ids = [rid for rid in region_ids if rid >= 0]
        if not region_ids:
            continue
        pick = max(set(region_ids), key=region_ids.count)
        loose_regions[pick].append(face_id)

    combined = []
    for idx, region_faces in enumerate(face_regions):
        if region_faces:
            combined.append(region_faces)
            continue
        if loose_regions[idx]:
            combined.append(loose_regions[idx])
    return combined


def compute_face_lower_fraction_and_convexity(face_centers: np.ndarray,
                                              face_normals: np.ndarray,
                                              adjacency: Dict[int, List[int]],
                                              min_delta_y: float = 0.05
                                              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute lower-neighbor fractions and convexity counts per face."""
    face_count = len(face_normals)
    lower_fraction = np.zeros(face_count, dtype=np.float32)
    convex_pos = np.zeros(face_count, dtype=np.int32)
    convex_total = np.zeros(face_count, dtype=np.int32)

    for face_id in range(face_count):
        neighbors = adjacency.get(face_id, [])
        if not neighbors:
            continue

        face_y = face_centers[face_id][1]
        lower_count = 0
        n1 = face_normals[face_id]
        c1 = face_centers[face_id]

        for neighbor_id in neighbors:
            if face_centers[neighbor_id][1] < (face_y - min_delta_y):
                lower_count += 1

            n2 = face_normals[neighbor_id]
            c2 = face_centers[neighbor_id]
            dn = n2 - n1
            dc = c2 - c1
            s = float(np.dot(dn, dc))
            if abs(s) > 1e-9:
                convex_total[face_id] += 1
                if s > 0:
                    convex_pos[face_id] += 1

        lower_fraction[face_id] = lower_count / len(neighbors)

    return lower_fraction, convex_pos, convex_total


def merge_nearby_edges(edges: List[Tuple[np.ndarray, np.ndarray]],
                       merge_distance: float = 1.0,
                       min_length: float = 2.0) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Merge nearby boundary edges into longer continuous edges."""
    if len(edges) <= 1:
        return edges

    merged = []
    used = set()

    for i, (start1, end1) in enumerate(edges):
        if i in used:
            continue

        chain_start = start1.copy()
        chain_end = end1.copy()
        used.add(i)

        changed = True
        while changed:
            changed = False
            for j, (start2, end2) in enumerate(edges):
                if j in used:
                    continue

                dist_start_start = np.linalg.norm(chain_start - start2)
                dist_start_end = np.linalg.norm(chain_start - end2)
                dist_end_start = np.linalg.norm(chain_end - start2)
                dist_end_end = np.linalg.norm(chain_end - end2)

                min_dist = min(dist_start_start, dist_start_end, dist_end_start, dist_end_end)

                if min_dist < merge_distance:
                    used.add(j)
                    changed = True

                    if dist_end_start < merge_distance:
                        chain_end = end2.copy()
                    elif dist_end_end < merge_distance:
                        chain_end = start2.copy()
                    elif dist_start_start < merge_distance:
                        chain_start = end2.copy()
                    elif dist_start_end < merge_distance:
                        chain_start = start2.copy()

        edge_length = np.linalg.norm(chain_end - chain_start)
        if edge_length >= min_length:
            merged.append((chain_start, chain_end))

    return merged


def classify_overhang_type(region_vertices: np.ndarray,
                           all_overhang_vertices: np.ndarray,
                           tolerance: float = 0.5) -> str:
    """Classify an overhang region as 'tip' or 'boundary'."""
    if len(region_vertices) == 0:
        return "boundary"

    region_min_y = np.min(region_vertices[:, 1])
    global_min_y = np.min(all_overhang_vertices[:, 1])

    if abs(region_min_y - global_min_y) < tolerance:
        return "tip"
    else:
        return "boundary"


def find_obstruction_height(x: float, z: float, max_y: float,
                            vertices: np.ndarray, indices: np.ndarray) -> float:
    """Find the highest point on the mesh below a given position."""
    highest_y = 0.0
    tolerance = 0.5

    for face in indices:
        v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

        min_x = min(v0[0], v1[0], v2[0]) - tolerance
        max_x = max(v0[0], v1[0], v2[0]) + tolerance
        min_z = min(v0[2], v1[2], v2[2]) - tolerance
        max_z = max(v0[2], v1[2], v2[2]) + tolerance

        if x < min_x or x > max_x or z < min_z or z > max_z:
            continue

        denom = (v1[2] - v2[2]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[2] - v2[2])
        if abs(denom) < 1e-10:
            continue

        a = ((v1[2] - v2[2]) * (x - v2[0]) + (v2[0] - v1[0]) * (z - v2[2])) / denom
        b = ((v2[2] - v0[2]) * (x - v2[0]) + (v0[0] - v2[0]) * (z - v2[2])) / denom
        c = 1.0 - a - b

        if a >= -0.1 and b >= -0.1 and c >= -0.1:
            y = a * v0[1] + b * v1[1] + c * v2[1]
            if y < max_y - 0.5 and y > highest_y:
                highest_y = y

    return highest_y


# ============================================================================
# Test Cases
# ============================================================================

class TestComputeFaceNormals(unittest.TestCase):
    """Tests for face normal computation."""

    def test_horizontal_face_pointing_up(self):
        """A horizontal triangle should have normal pointing up (0, 1, 0)."""
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 0.0, 1.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        normals = compute_face_normals(vertices, indices)

        self.assertEqual(normals.shape, (1, 3))
        # Normal should point up (0, 1, 0) or down depending on winding
        self.assertAlmostEqual(abs(normals[0, 1]), 1.0, places=5)
        self.assertAlmostEqual(normals[0, 0], 0.0, places=5)
        self.assertAlmostEqual(normals[0, 2], 0.0, places=5)

    def test_vertical_face(self):
        """A vertical triangle should have horizontal normal."""
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.5, 1.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        normals = compute_face_normals(vertices, indices)

        # Normal should be horizontal (X or Z component dominant)
        self.assertAlmostEqual(abs(normals[0, 0]), 1.0, places=5)
        self.assertAlmostEqual(normals[0, 1], 0.0, places=5)

    def test_multiple_faces(self):
        """Test with multiple faces."""
        # Simple cube-like structure (2 triangles)
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)
        indices = np.array([
            [0, 1, 2],
            [0, 2, 3]
        ], dtype=np.int32)

        normals = compute_face_normals(vertices, indices)

        self.assertEqual(normals.shape, (2, 3))
        # Both should have similar normals (pointing up or down)
        for i in range(2):
            self.assertAlmostEqual(abs(normals[i, 1]), 1.0, places=5)


class TestBuildFaceAdjacencyGraph(unittest.TestCase):
    """Tests for face adjacency graph building."""

    def test_two_adjacent_triangles(self):
        """Two triangles sharing an edge should be adjacent."""
        indices = np.array([
            [0, 1, 2],
            [1, 3, 2]
        ], dtype=np.int32)

        adjacency = build_face_adjacency_graph(indices)

        self.assertEqual(len(adjacency), 2)
        self.assertIn(1, adjacency[0])
        self.assertIn(0, adjacency[1])

    def test_isolated_triangles(self):
        """Non-adjacent triangles should have empty adjacency."""
        indices = np.array([
            [0, 1, 2],
            [3, 4, 5]
        ], dtype=np.int32)

        adjacency = build_face_adjacency_graph(indices)

        self.assertEqual(len(adjacency), 2)
        self.assertEqual(adjacency[0], [])
        self.assertEqual(adjacency[1], [])

    def test_three_triangles_fan(self):
        """Three triangles in a fan pattern."""
        # Central vertex at 0, others radiate out
        indices = np.array([
            [0, 1, 2],
            [0, 2, 3],
            [0, 3, 4]
        ], dtype=np.int32)

        adjacency = build_face_adjacency_graph(indices)

        self.assertEqual(len(adjacency), 3)
        # Face 0 is adjacent to face 1
        self.assertIn(1, adjacency[0])
        # Face 1 is adjacent to faces 0 and 2
        self.assertIn(0, adjacency[1])
        self.assertIn(2, adjacency[1])
        # Face 2 is adjacent to face 1
        self.assertIn(1, adjacency[2])


class TestFindConnectedOverhangRegion(unittest.TestCase):
    """Tests for connected overhang region finding (BFS)."""

    def test_single_overhang_face(self):
        """Single overhang face should return itself."""
        overhang_mask = np.array([True, False, False])
        adjacency = {0: [1], 1: [0, 2], 2: [1]}

        region = find_connected_overhang_region(0, overhang_mask, adjacency)

        self.assertEqual(region, [0])

    def test_connected_overhangs(self):
        """Connected overhang faces should all be found."""
        overhang_mask = np.array([True, True, True, False])
        adjacency = {0: [1], 1: [0, 2], 2: [1, 3], 3: [2]}

        region = find_connected_overhang_region(0, overhang_mask, adjacency)

        self.assertEqual(set(region), {0, 1, 2})

    def test_separated_overhangs(self):
        """Overhangs separated by non-overhang should not connect."""
        overhang_mask = np.array([True, False, True])
        adjacency = {0: [1], 1: [0, 2], 2: [1]}

        region = find_connected_overhang_region(0, overhang_mask, adjacency)

        self.assertEqual(region, [0])

    def test_non_overhang_seed(self):
        """Non-overhang seed should return empty."""
        overhang_mask = np.array([False, True, True])
        adjacency = {0: [1], 1: [0, 2], 2: [1]}

        region = find_connected_overhang_region(0, overhang_mask, adjacency)

        self.assertEqual(region, [])


class TestDetectOverhangs(unittest.TestCase):
    """Tests for overhang detection using normal vectors."""

    def test_horizontal_floor_no_overhang(self):
        """Horizontal upward-facing surface is not an overhang."""
        # Counter-clockwise winding when viewed from above = normal points up
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [0.5, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        overhang_ids, angles = detect_overhangs(vertices, indices, threshold_angle=45.0)

        # Upward-facing face should NOT be detected as overhang
        # (angle to down vector should be ~180 degrees)
        self.assertEqual(len(overhang_ids), 0)

    def test_horizontal_ceiling_is_overhang(self):
        """Horizontal downward-facing surface is an overhang."""
        # Clockwise winding when viewed from above = normal points down
        vertices = np.array([
            [0.0, 10.0, 0.0],
            [1.0, 10.0, 0.0],
            [0.5, 10.0, 1.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        overhang_ids, angles = detect_overhangs(vertices, indices, threshold_angle=45.0)

        # Downward-facing face SHOULD be detected as overhang
        self.assertEqual(len(overhang_ids), 1)

    def test_45_degree_overhang_at_threshold(self):
        """45-degree overhang should be detected at 45-degree threshold."""
        # Create a face at 45 degrees
        vertices = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.5, 0.5, 1.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        # The normal calculation and angle threshold logic should handle this
        overhang_ids, angles = detect_overhangs(vertices, indices, threshold_angle=45.0)

        # This is a borderline case - the face is at exactly 45 degrees
        # Based on implementation, angle < (90 - threshold) means it's an overhang
        # So at 45 threshold, faces with angle < 45 are overhangs


class TestMergeNearbyEdges(unittest.TestCase):
    """Tests for edge merging algorithm."""

    def test_single_edge(self):
        """Single edge should be returned as-is if long enough."""
        edges = [(np.array([0, 0, 0]), np.array([5, 0, 0]))]

        merged = merge_nearby_edges(edges, merge_distance=1.0, min_length=2.0)

        self.assertEqual(len(merged), 1)

    def test_short_edge_filtered(self):
        """Edge shorter than min_length should be filtered out."""
        # Two short edges that don't connect
        edges = [
            (np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])),
            (np.array([10.0, 0.0, 0.0]), np.array([11.0, 0.0, 0.0])),
        ]

        merged = merge_nearby_edges(edges, merge_distance=1.0, min_length=2.0)

        # Both edges are too short (length 1) and should be filtered
        self.assertEqual(len(merged), 0)

    def test_merge_connected_edges(self):
        """Connected edges should merge into one."""
        edges = [
            (np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])),
            (np.array([2.0, 0.0, 0.0]), np.array([4.0, 0.0, 0.0])),
        ]

        merged = merge_nearby_edges(edges, merge_distance=1.0, min_length=2.0)

        self.assertEqual(len(merged), 1)
        # Merged edge should span from 0 to 4
        start, end = merged[0]
        length = np.linalg.norm(end - start)
        self.assertGreaterEqual(length, 4.0)

    def test_distant_edges_not_merged(self):
        """Edges far apart should not be merged."""
        edges = [
            (np.array([0.0, 0.0, 0.0]), np.array([3.0, 0.0, 0.0])),
            (np.array([10.0, 0.0, 0.0]), np.array([13.0, 0.0, 0.0])),
        ]

        merged = merge_nearby_edges(edges, merge_distance=1.0, min_length=2.0)

        self.assertEqual(len(merged), 2)


class TestClassifyOverhangType(unittest.TestCase):
    """Tests for tip vs boundary classification."""

    def test_lowest_region_is_tip(self):
        """Region containing the lowest point should be classified as tip."""
        region_vertices = np.array([
            [0, 5, 0],
            [1, 5, 0],
            [0.5, 4, 0],  # Lowest at y=4
        ])
        all_vertices = np.array([
            [0, 5, 0],
            [1, 5, 0],
            [0.5, 4, 0],
            [5, 10, 0],  # Other region at y=10
        ])

        result = classify_overhang_type(region_vertices, all_vertices)

        self.assertEqual(result, "tip")

    def test_higher_region_is_boundary(self):
        """Region above the lowest point should be classified as boundary."""
        region_vertices = np.array([
            [5, 10, 0],
            [6, 11, 0],
            [5.5, 10.5, 0],
        ])
        all_vertices = np.array([
            [0, 5, 0],  # Lower region
            [1, 4, 0],  # Lowest point
            [5, 10, 0],
            [6, 11, 0],
        ])

        result = classify_overhang_type(region_vertices, all_vertices)

        self.assertEqual(result, "boundary")

    def test_empty_region(self):
        """Empty region should be classified as boundary."""
        region_vertices = np.array([]).reshape(0, 3)
        all_vertices = np.array([[0, 5, 0]])

        result = classify_overhang_type(region_vertices, all_vertices)

        self.assertEqual(result, "boundary")


class TestFindObstructionHeight(unittest.TestCase):
    """Tests for obstruction detection (ray casting)."""

    def test_no_obstruction(self):
        """Point with no geometry below should return 0."""
        vertices = np.array([
            [10.0, 5.0, 10.0],
            [11.0, 5.0, 10.0],
            [10.5, 5.0, 11.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        # Check at point far from triangle
        height = find_obstruction_height(0.0, 0.0, 10.0, vertices, indices)

        self.assertEqual(height, 0.0)

    def test_obstruction_found(self):
        """Point above a horizontal triangle should find it."""
        vertices = np.array([
            [0.0, 5.0, 0.0],
            [2.0, 5.0, 0.0],
            [1.0, 5.0, 2.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        # Check at center of triangle, from above
        height = find_obstruction_height(1.0, 1.0, 10.0, vertices, indices)

        self.assertAlmostEqual(height, 5.0, places=1)

    def test_obstruction_below_max_y(self):
        """Should only find obstructions below max_y."""
        vertices = np.array([
            [0.0, 15.0, 0.0],  # Above max_y
            [2.0, 15.0, 0.0],
            [1.0, 15.0, 2.0],
        ], dtype=np.float32)
        indices = np.array([[0, 1, 2]], dtype=np.int32)

        # max_y is 10, triangle is at 15
        height = find_obstruction_height(1.0, 1.0, 10.0, vertices, indices)

        self.assertEqual(height, 0.0)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple algorithms."""

    def test_full_overhang_detection_pipeline(self):
        """Test the full pipeline: detect overhangs, find regions, classify."""
        # Create a simple model with an overhang
        # Floor at y=0 (upward facing - CCW winding from above)
        # Overhang at y=10 (downward facing - CW winding from above)
        vertices = np.array([
            # Floor (upward facing) - CCW when viewed from +Y
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 2.0],
            [2.0, 0.0, 0.0],
            # Overhang (downward facing) - CW when viewed from +Y
            [0.0, 10.0, 0.0],
            [2.0, 10.0, 0.0],
            [1.0, 10.0, 2.0],
        ], dtype=np.float32)
        indices = np.array([
            [0, 1, 2],  # Floor - normal points up
            [3, 4, 5],  # Overhang - normal points down
        ], dtype=np.int32)

        # Detect overhangs
        overhang_ids, angles = detect_overhangs(vertices, indices, threshold_angle=45.0)

        # Should detect exactly one overhang (the ceiling)
        self.assertEqual(len(overhang_ids), 1)

        # Build adjacency
        adjacency = build_face_adjacency_graph(indices)

        # Find connected region
        overhang_mask = np.zeros(len(indices), dtype=bool)
        overhang_mask[overhang_ids] = True
        region = find_connected_overhang_region(overhang_ids[0], overhang_mask, adjacency)

        self.assertEqual(len(region), 1)


class TestExportedMeshOverhangs(unittest.TestCase):
    """Tests using exported mesh data from tests/fixtures/exports."""

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.export_path = os.path.join(
            base_dir,
            "tests",
            "fixtures",
            "exports",
            "component1_export.json",
        )
        cls.vertices, cls.indices, cls.raw_vertex_count, cls.has_indices = load_exported_mesh(cls.export_path)

    def test_rebuild_indices_for_exported_mesh(self):
        """Non-indexed exports should rebuild a valid index buffer."""
        if self.has_indices:
            self.skipTest("Export already indexed.")
        self.assertEqual(self.raw_vertex_count % 3, 0)
        self.assertEqual(len(self.indices), self.raw_vertex_count // 3)
        self.assertLessEqual(len(self.vertices), self.raw_vertex_count)

    def test_overhang_detection_invariant_to_uniform_scale(self):
        """Overhang IDs should not change under uniform scale and translation."""
        threshold = 45.0
        overhang_ids, _ = detect_overhangs(self.vertices, self.indices, threshold_angle=threshold)

        scale = 2.5
        offset = np.array([10.0, -5.0, 3.0], dtype=np.float32)
        vertices_scaled = self.vertices * scale + offset
        overhang_ids_scaled, _ = detect_overhangs(vertices_scaled, self.indices, threshold_angle=threshold)

        self.assertTrue(np.array_equal(overhang_ids, overhang_ids_scaled))

    def test_overhang_region_bounds_scale_with_transform(self):
        """Region bounds should scale and translate with transformed vertices."""
        threshold = 45.0
        overhang_ids, _ = detect_overhangs(self.vertices, self.indices, threshold_angle=threshold)
        if len(overhang_ids) == 0:
            self.skipTest("No overhangs detected in exported mesh.")

        adjacency = build_face_adjacency_graph(self.indices)
        overhang_mask = np.zeros(len(self.indices), dtype=bool)
        overhang_mask[overhang_ids] = True
        regions = find_connected_overhang_regions(overhang_ids, overhang_mask, adjacency)
        if not regions:
            self.skipTest("No connected overhang regions found in exported mesh.")

        largest_region = max(regions, key=len)
        min_bounds, max_bounds = compute_region_bounds(self.vertices, self.indices, largest_region)

        scale = 2.5
        offset = np.array([10.0, -5.0, 3.0], dtype=np.float32)
        vertices_scaled = self.vertices * scale + offset
        scaled_min, scaled_max = compute_region_bounds(vertices_scaled, self.indices, largest_region)

        expected_min = min_bounds * scale + offset
        expected_max = max_bounds * scale + offset

        self.assertTrue(np.allclose(scaled_min, expected_min, atol=1e-4))
        self.assertTrue(np.allclose(scaled_max, expected_max, atol=1e-4))

    def test_dangling_vertex_detection_finds_two_regions(self):
        """Dangling-vertex pipeline should find two dangling regions in the export."""
        mesh_min_y = float(self.vertices[:, 1].min())
        min_face_y = mesh_min_y + 0.2
        if mesh_min_y > 0.5:
            min_face_y = mesh_min_y

        min_faces = 6
        face_normals = compute_face_normals(self.vertices, self.indices)
        build_direction = np.array([0.0, -1.0, 0.0], dtype=np.float32)
        downward_mask = (face_normals @ build_direction) > 0.0
        overhang_ids, _ = detect_overhangs(self.vertices, self.indices, threshold_angle=45.0)
        overhang_mask = np.zeros(len(self.indices), dtype=bool)
        if len(overhang_ids) > 0:
            overhang_mask[overhang_ids] = True
        face_down_dot = np.clip(face_normals @ build_direction, -1.0, 1.0)
        dangling_candidate_mask = downward_mask & overhang_mask

        vertex_regions, adjacency = find_dangling_vertex_regions(
            self.vertices, self.indices, min_drop=0.0, min_face_y=min_face_y
        )
        if not vertex_regions:
            self.fail("No dangling vertex regions found in exported mesh.")

        vertex_regions = merge_small_dangling_regions(
            vertex_regions, adjacency, min_vertices=max(3, min_faces * 3)
        )
        adjacency_faces = build_face_adjacency_graph(self.indices)
        expanded_regions = []
        for region in vertex_regions:
            region_mask = np.zeros(len(self.vertices), dtype=bool)
            region_mask[list(region)] = True
            seed_faces = np.where(
                dangling_candidate_mask & np.any(region_mask[self.indices], axis=1)
            )[0]
            expanded = expand_dangling_face_region(
                seed_faces,
                adjacency_faces,
                dangling_candidate_mask,
                max_faces=180,
                max_depth=4,
            )
            if expanded:
                expanded_regions.append(expanded)

        face_regions = merge_overlapping_face_regions(expanded_regions)
        kept = [region for region in face_regions if len(region) >= min_faces]

        self.assertEqual(len(kept), 2)


class TestFloatingSphereOverhangs(unittest.TestCase):
    """Ensure floating sphere exports form a connected overhang region."""

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.export_path = os.path.join(
            base_dir,
            "tests",
            "fixtures",
            "exports",
            "floating_sphere_export.json",
        )
        cls.vertices, cls.indices, cls.raw_vertex_count, cls.has_indices = load_exported_mesh(cls.export_path)

    def test_sphere_rebuilds_deindexed_mesh(self):
        """Sphere export should rebuild to a shared-vertex mesh."""
        self.assertTrue(self.has_indices)
        self.assertLess(len(self.vertices), self.raw_vertex_count)

    def test_sphere_overhang_region_is_kept(self):
        """Auto-detect pipeline should keep the floating sphere overhang region."""
        threshold = 65.0
        overhang_ids, _ = detect_overhangs(self.vertices, self.indices, threshold_angle=threshold)
        self.assertGreater(len(overhang_ids), 0)

        adjacency = build_face_adjacency_graph(self.indices)
        overhang_mask = np.zeros(len(self.indices), dtype=bool)
        overhang_mask[overhang_ids] = True
        regions = find_connected_overhang_regions(overhang_ids, overhang_mask, adjacency)
        self.assertEqual(len(regions), 1)

        face_centers = compute_face_centers(self.vertices, self.indices)
        mesh_min_y = float(self.vertices[:, 1].min()) if len(self.vertices) else 0.0
        min_face_y = mesh_min_y + 0.2
        if mesh_min_y > 0.5:
            min_face_y = mesh_min_y
        min_delta_y = 0.05
        max_lower_fraction = 0.5

        filtered = []
        for face_id in overhang_ids:
            face_y = face_centers[face_id][1]
            if face_y <= min_face_y:
                continue
            neighbors = adjacency.get(int(face_id), [])
            if not neighbors:
                filtered.append(int(face_id))
                continue
            lower_count = 0
            for neighbor_id in neighbors:
                if face_centers[neighbor_id][1] < (face_y - min_delta_y):
                    lower_count += 1
            if (lower_count / len(neighbors)) <= max_lower_fraction:
                filtered.append(int(face_id))

        filtered_set = set(filtered)
        regions = [region for region in regions if any(face_id in filtered_set for face_id in region)]
        self.assertEqual(len(regions), 1)

        face_normals = compute_face_normals(self.vertices, self.indices)
        lower_fraction, convex_pos, convex_total = compute_face_lower_fraction_and_convexity(
            face_centers, face_normals, adjacency, min_delta_y=min_delta_y
        )

        region_lower_fraction_threshold = 0.35
        mesh_min_y = float(self.vertices[:, 1].min()) if len(self.vertices) else 0.0
        if mesh_min_y > 0.5:
            region_lower_fraction_threshold = 0.45
        convexity_threshold = 0.6
        min_faces = 10
        kept = []
        for region in regions:
            if float(lower_fraction[region].mean()) > region_lower_fraction_threshold:
                continue
            total = int(convex_total[region].sum())
            if total > 0:
                score = float(convex_pos[region].sum()) / total
                if score < convexity_threshold:
                    continue
            if len(region) >= min_faces:
                kept.append(region)

        self.assertEqual(len(kept), 1)


if __name__ == '__main__':
    unittest.main()
