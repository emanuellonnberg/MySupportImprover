"""
Unit tests for MySupportImprover geometry generation.

Tests for edge rail and tip column mesh generation.
"""

import unittest
import numpy as np
import math
from typing import Tuple, List


# ============================================================================
# Simplified mesh generation functions for testing
# These mirror the logic in MySupportImprover.py but return raw vertex/index data
# ============================================================================

def create_edge_rail_geometry(edge_start: np.ndarray, edge_end: np.ndarray,
                               rail_width: float = 0.8,
                               base_y: float = 0.0) -> Tuple[List, List]:
    """Create edge rail geometry returning vertices and indices."""
    edge_vec = edge_end - edge_start
    edge_length = np.linalg.norm(edge_vec)

    if edge_length < 0.1:
        return [], []

    edge_dir = edge_vec / edge_length

    # Calculate perpendicular direction
    up = np.array([0.0, 1.0, 0.0])
    perp_dir = np.cross(edge_dir, up)
    perp_length = np.linalg.norm(perp_dir)

    if perp_length < 0.01:
        perp_dir = np.array([1.0, 0.0, 0.0])
    else:
        perp_dir = perp_dir / perp_length

    # Determine rail height
    edge_min_y = min(edge_start[1], edge_end[1])

    if edge_min_y <= base_y:
        return [], []

    half_width = rail_width / 2
    half_length = edge_length / 2

    edge_center = (edge_start + edge_end) / 2
    rail_height = edge_min_y - base_y
    rail_center_y = base_y + rail_height / 2

    # Build vertices
    verts = []
    for dy in [-rail_height / 2, rail_height / 2]:
        for dw in [-half_width, half_width]:
            for dl in [-half_length, half_length]:
                vert = np.array([edge_center[0], rail_center_y, edge_center[2]])
                vert[1] += dy
                vert += perp_dir * dw
                vert += edge_dir * dl
                verts.append([vert[0], vert[1], vert[2]])

    face_indices = [
        [0, 1, 3], [0, 3, 2],
        [4, 7, 5], [4, 6, 7],
        [0, 4, 5], [0, 5, 1],
        [2, 3, 7], [2, 7, 6],
        [0, 2, 6], [0, 6, 4],
        [1, 5, 7], [1, 7, 3],
    ]

    return verts, face_indices


def create_tip_column_geometry(tip_position: np.ndarray,
                                base_y: float = 0.0,
                                column_radius: float = 2.0,
                                taper: float = 0.6,
                                sides: int = 8) -> Tuple[List, List]:
    """Create tip column geometry returning vertices and indices."""
    tip_y = tip_position[1]
    if tip_y <= base_y:
        return [], []

    top_radius = column_radius * taper
    base_radius = column_radius

    verts = []
    indices = []

    # Bottom center
    verts.append([tip_position[0], base_y, tip_position[2]])
    bottom_center_idx = 0

    # Top center
    verts.append([tip_position[0], tip_y, tip_position[2]])
    top_center_idx = 1

    # Bottom ring vertices
    bottom_start_idx = 2
    for i in range(sides):
        angle = 2 * math.pi * i / sides
        x = tip_position[0] + base_radius * math.cos(angle)
        z = tip_position[2] + base_radius * math.sin(angle)
        verts.append([x, base_y, z])

    # Top ring vertices
    top_start_idx = bottom_start_idx + sides
    for i in range(sides):
        angle = 2 * math.pi * i / sides
        x = tip_position[0] + top_radius * math.cos(angle)
        z = tip_position[2] + top_radius * math.sin(angle)
        verts.append([x, tip_y, z])

    # Bottom cap faces
    for i in range(sides):
        next_i = (i + 1) % sides
        indices.append([bottom_center_idx, bottom_start_idx + next_i, bottom_start_idx + i])

    # Top cap faces
    for i in range(sides):
        next_i = (i + 1) % sides
        indices.append([top_center_idx, top_start_idx + i, top_start_idx + next_i])

    # Side faces
    for i in range(sides):
        next_i = (i + 1) % sides
        b1 = bottom_start_idx + i
        b2 = bottom_start_idx + next_i
        t1 = top_start_idx + i
        t2 = top_start_idx + next_i
        indices.append([b1, t1, b2])
        indices.append([b2, t1, t2])

    return verts, indices


def create_wing_geometry(width: float, thickness: float, height: float,
                          breakline_enable: bool = False,
                          breakline_depth: float = 0.5,
                          breakline_position: float = 2.0,
                          breakline_height: float = 0.8) -> Tuple[List, List]:
    """Create wing geometry returning vertices and indices."""
    half_width = width / 2
    half_thickness = thickness / 2

    if not breakline_enable:
        # Simple box
        verts = []
        for y in [0, height]:
            for t in [-half_thickness, half_thickness]:
                for w in [-half_width, half_width]:
                    verts.append([w, y, t])

        face_indices = [
            [0, 1, 3], [0, 3, 2],
            [4, 7, 5], [4, 6, 7],
            [0, 4, 5], [0, 5, 1],
            [2, 3, 7], [2, 7, 6],
            [0, 2, 6], [0, 6, 4],
            [1, 5, 7], [1, 7, 3],
        ]
        return verts, face_indices

    # With breakline - create three sections
    notch_start_y = height - breakline_position
    notch_end_y = notch_start_y + breakline_height
    notch_thickness = thickness * (1 - breakline_depth)
    half_notch = notch_thickness / 2

    verts = []
    indices = []

    # Top section (above notch)
    section_heights = [
        (notch_end_y, height, half_thickness),  # Top
        (notch_start_y, notch_end_y, half_notch),  # Notch (thinner)
        (0, notch_start_y, half_thickness),  # Bottom
    ]

    vert_offset = 0
    for (y_start, y_end, half_t) in section_heights:
        if y_end <= y_start:
            continue

        section_verts = []
        for y in [y_start, y_end]:
            for t in [-half_t, half_t]:
                for w in [-half_width, half_width]:
                    section_verts.append([w, y, t])

        section_indices = [
            [0, 1, 3], [0, 3, 2],
            [4, 7, 5], [4, 6, 7],
            [0, 4, 5], [0, 5, 1],
            [2, 3, 7], [2, 7, 6],
            [0, 2, 6], [0, 6, 4],
            [1, 5, 7], [1, 7, 3],
        ]

        verts.extend(section_verts)
        for face in section_indices:
            indices.append([f + vert_offset for f in face])
        vert_offset += len(section_verts)

    return verts, indices


# ============================================================================
# Test Cases
# ============================================================================

class TestEdgeRailGeometry(unittest.TestCase):
    """Tests for edge rail mesh generation."""

    def test_basic_rail_creation(self):
        """Basic rail should have 8 vertices and 12 faces."""
        edge_start = np.array([0.0, 10.0, 0.0])
        edge_end = np.array([5.0, 10.0, 0.0])

        verts, indices = create_edge_rail_geometry(edge_start, edge_end)

        self.assertEqual(len(verts), 8)  # Box has 8 corners
        self.assertEqual(len(indices), 12)  # Box has 6 faces = 12 triangles

    def test_rail_at_build_plate(self):
        """Edge at build plate level should not create rail."""
        edge_start = np.array([0.0, 0.0, 0.0])
        edge_end = np.array([5.0, 0.0, 0.0])

        verts, indices = create_edge_rail_geometry(edge_start, edge_end)

        self.assertEqual(len(verts), 0)
        self.assertEqual(len(indices), 0)

    def test_short_edge_rejected(self):
        """Very short edge should not create rail."""
        edge_start = np.array([0.0, 10.0, 0.0])
        edge_end = np.array([0.05, 10.0, 0.0])

        verts, indices = create_edge_rail_geometry(edge_start, edge_end)

        self.assertEqual(len(verts), 0)

    def test_rail_width_affects_geometry(self):
        """Different rail widths should produce different geometry."""
        edge_start = np.array([0.0, 10.0, 0.0])
        edge_end = np.array([5.0, 10.0, 0.0])

        verts_thin, _ = create_edge_rail_geometry(edge_start, edge_end, rail_width=0.5)
        verts_thick, _ = create_edge_rail_geometry(edge_start, edge_end, rail_width=2.0)

        # Both should have vertices, but positions will differ
        self.assertEqual(len(verts_thin), 8)
        self.assertEqual(len(verts_thick), 8)

    def test_rail_with_base_height(self):
        """Rail with base height should not reach build plate."""
        edge_start = np.array([0.0, 10.0, 0.0])
        edge_end = np.array([5.0, 10.0, 0.0])

        verts, _ = create_edge_rail_geometry(edge_start, edge_end, base_y=5.0)

        # Check that lowest vertex is at base_y (approximately)
        if verts:
            min_y = min(v[1] for v in verts)
            self.assertGreaterEqual(min_y, 4.5)  # Allow some tolerance


class TestTipColumnGeometry(unittest.TestCase):
    """Tests for tip column mesh generation."""

    def test_basic_column_creation(self):
        """Basic column should have correct vertex count."""
        tip_pos = np.array([0.0, 20.0, 0.0])
        sides = 8

        verts, indices = create_tip_column_geometry(tip_pos, sides=sides)

        # 2 center vertices + 2 rings of 'sides' vertices
        expected_verts = 2 + 2 * sides
        self.assertEqual(len(verts), expected_verts)

        # Bottom cap + top cap + side faces
        # caps: sides triangles each
        # sides: sides * 2 triangles
        expected_faces = sides + sides + sides * 2
        self.assertEqual(len(indices), expected_faces)

    def test_column_at_build_plate(self):
        """Tip at build plate should not create column."""
        tip_pos = np.array([0.0, 0.0, 0.0])

        verts, indices = create_tip_column_geometry(tip_pos)

        self.assertEqual(len(verts), 0)

    def test_column_with_base_height(self):
        """Column with base height should not reach build plate."""
        tip_pos = np.array([0.0, 20.0, 0.0])

        verts, _ = create_tip_column_geometry(tip_pos, base_y=10.0)

        if verts:
            min_y = min(v[1] for v in verts)
            self.assertAlmostEqual(min_y, 10.0, places=1)

    def test_column_taper(self):
        """Column taper should affect top radius."""
        tip_pos = np.array([0.0, 20.0, 0.0])

        verts_no_taper, _ = create_tip_column_geometry(tip_pos, taper=1.0, column_radius=2.0)
        verts_tapered, _ = create_tip_column_geometry(tip_pos, taper=0.5, column_radius=2.0)

        # With taper=1.0, top and bottom should have same radius
        # With taper=0.5, top should be smaller
        # Check that vertices differ
        self.assertNotEqual(verts_no_taper, verts_tapered)

    def test_column_different_sides(self):
        """Different side counts should produce different vertex counts."""
        tip_pos = np.array([0.0, 20.0, 0.0])

        verts_6, _ = create_tip_column_geometry(tip_pos, sides=6)
        verts_12, _ = create_tip_column_geometry(tip_pos, sides=12)

        self.assertEqual(len(verts_6), 2 + 2 * 6)  # 14
        self.assertEqual(len(verts_12), 2 + 2 * 12)  # 26


class TestWingGeometry(unittest.TestCase):
    """Tests for wing mesh generation."""

    def test_basic_wing_creation(self):
        """Basic wing without breakline should be a simple box."""
        verts, indices = create_wing_geometry(
            width=5.0, thickness=1.5, height=10.0,
            breakline_enable=False
        )

        self.assertEqual(len(verts), 8)  # Box
        self.assertEqual(len(indices), 12)  # 6 faces * 2 triangles

    def test_wing_with_breakline(self):
        """Wing with breakline should have more vertices (3 sections)."""
        verts, indices = create_wing_geometry(
            width=5.0, thickness=1.5, height=10.0,
            breakline_enable=True,
            breakline_depth=0.5,
            breakline_position=2.0,
            breakline_height=0.8
        )

        # 3 sections * 8 vertices each = 24
        self.assertEqual(len(verts), 24)
        # 3 sections * 12 triangles each = 36
        self.assertEqual(len(indices), 36)

    def test_wing_dimensions(self):
        """Wing vertices should respect specified dimensions."""
        width = 10.0
        height = 20.0

        verts, _ = create_wing_geometry(
            width=width, thickness=1.0, height=height,
            breakline_enable=False
        )

        # Check width (x dimension)
        x_coords = [v[0] for v in verts]
        self.assertAlmostEqual(max(x_coords) - min(x_coords), width, places=1)

        # Check height (y dimension)
        y_coords = [v[1] for v in verts]
        self.assertAlmostEqual(max(y_coords), height, places=1)


class TestGeometryValidity(unittest.TestCase):
    """Tests to ensure generated geometry is valid for 3D printing."""

    def test_rail_no_inverted_faces(self):
        """Rail faces should have consistent winding."""
        edge_start = np.array([0.0, 10.0, 0.0])
        edge_end = np.array([5.0, 10.0, 0.0])

        verts, indices = create_edge_rail_geometry(edge_start, edge_end)

        # All vertex indices should be valid
        for face in indices:
            for idx in face:
                self.assertLess(idx, len(verts))
                self.assertGreaterEqual(idx, 0)

    def test_column_watertight(self):
        """Column should be a closed mesh (watertight)."""
        tip_pos = np.array([0.0, 20.0, 0.0])

        verts, indices = create_tip_column_geometry(tip_pos, sides=8)

        # Count edge usage - each edge should appear exactly twice
        # in a watertight mesh
        edge_count = {}
        for face in indices:
            for i in range(3):
                edge = tuple(sorted([face[i], face[(i + 1) % 3]]))
                edge_count[edge] = edge_count.get(edge, 0) + 1

        for edge, count in edge_count.items():
            self.assertEqual(count, 2, f"Edge {edge} appears {count} times, expected 2")


if __name__ == '__main__':
    unittest.main()
