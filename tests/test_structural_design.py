"""Tests para el motor de propuesta estructural automática."""
import unittest

from etabs_gui.architectural import FloorDrawing, Segment
from etabs_gui.structural_design import (
    SYSTEMS, _cluster_points, evaluate_alternatives, generate_proposal,
)


class StructuralProposalTests(unittest.TestCase):
    def test_point_clustering_is_transitive(self):
        # A-B and B-C are within tolerance, even though A-C are not.
        clusters = _cluster_points([
            (0.00, 0.0, "a", "MUROS"),
            (0.10, 0.0, "b", "MUROS"),
            (0.20, 0.0, "c", "MUROS"),
        ], tolerance=0.11)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 3)

    def test_wall_corners_create_candidates(self):
        drawing = FloorDrawing("P1", "p1.dxf", [
            Segment("MUROS", 0, 0, 4, 0),
            Segment("MUROS", 4, 0, 4, 3),
        ])
        result = generate_proposal(drawing)
        self.assertGreaterEqual(len(result.nodes), 3)
        self.assertGreaterEqual(len(result.beams), 1)

    def test_grid_intersections_guide_supported_column_candidates(self):
        drawing = FloorDrawing("P1", "p1.dxf", [
            Segment("MUROS", 0, 0, 4, 0),
            Segment("EJES", 0, -1, 0, 1),
            Segment("EJES", -1, 0, 5, 0),
        ])
        result = generate_proposal(drawing, tolerance=0.15)
        self.assertEqual(len(result.grid_lines), 2)
        self.assertTrue(any(abs(node.x) < 0.01 and abs(node.y) < 0.01 and
                            "Intersección de ejes" in node.reasons
                            for node in result.nodes))

    def test_unit_conversion_cm_to_m(self):
        drawing = FloorDrawing("P1", "p1.dxf", [Segment("MUROS", 0, 0, 400, 0)])
        result = generate_proposal(drawing, unit_scale=0.01)
        self.assertAlmostEqual(max(n.x for n in result.nodes), 4.0)

    def test_low_wall_is_not_used_as_regular_wall_candidate(self):
        drawing = FloorDrawing("P1", "p1.dxf", [Segment("MUROS-BAJOS", 0, 0, 4, 0)])
        result = generate_proposal(drawing)
        self.assertEqual(result.nodes, [])

    def test_alternatives_are_ranked_and_explainable(self):
        drawing = FloorDrawing("P1", "p1.dxf", [
            Segment("MUROS", 0, 0, 4, 0),
            Segment("MUROS", 4, 0, 4, 3),
            Segment("MUROS", 4, 3, 0, 3),
        ])
        proposal = generate_proposal(drawing, system=SYSTEMS[1], stories=4)
        alternatives = evaluate_alternatives(proposal)
        self.assertEqual(len(alternatives), 3)
        self.assertIn("placas", " ".join(proposal.notes).lower())


    def test_slab_panel_requires_four_supported_edges(self):
        drawing = FloorDrawing("P1", "p1.dxf", [
            Segment("MUROS", 0, 0, 4, 0),
            Segment("MUROS", 4, 0, 4, 3),
            Segment("MUROS", 4, 3, 0, 3),
            Segment("MUROS", 0, 3, 0, 0),
        ])
        result = generate_proposal(drawing)
        self.assertEqual(len(result.slabs), 1)
        self.assertAlmostEqual(result.slabs[0].area, 12.0)

    def test_negative_max_span_is_rejected(self):
        drawing = FloorDrawing("P1", "p1.dxf", [Segment("MUROS", 0, 0, 4, 0)])
        with self.assertRaises(ValueError):
            generate_proposal(drawing, max_span=-1)

    def test_unknown_layers_are_not_assumed_structural(self):
        drawing = FloorDrawing("P1", "p1.dxf", [Segment("LAYER_X", 0, 0, 4, 0)])
        self.assertEqual(generate_proposal(drawing).nodes, [])


if __name__ == "__main__":
    unittest.main()
