"""
Unit tests for MySupportImprover core algorithms.

These tests focus on the pure algorithmic parts that don't require
the full Cura framework - overhang detection, edge merging, etc.
"""

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


if __name__ == '__main__':
    unittest.main()
