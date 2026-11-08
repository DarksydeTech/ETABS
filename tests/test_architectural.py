"""Pruebas unitarias del comparador de continuidad arquitectónica."""
import unittest

from etabs_gui.architectural import (
    FloorDrawing, Segment, align_by_centroid, compare_floors, compare_segments,
)


class ContinuityTests(unittest.TestCase):
    def test_identical_segments_are_continuous(self):
        a = Segment("A-WALL", 0, 0, 5, 0)
        b = Segment("A-WALL", 0, 0, 5, 0)
        ratio, offset, angle = compare_segments(a, b)
        self.assertAlmostEqual(ratio, 1.0)
        self.assertAlmostEqual(offset, 0.0)
        self.assertAlmostEqual(angle, 0.0)

    def test_partial_overlap_is_detected(self):
        lower = FloorDrawing("P1", "p1.dxf", [Segment("WALL", 0, 0, 5, 0)])
        upper = FloorDrawing("P2", "p2.dxf", [Segment("WALL", 2, 0, 5, 0)])
        matches = compare_floors(lower, upper)
        self.assertEqual(matches[0].status, "continuous")

    def test_offset_outside_tolerance_is_not_matched(self):
        a = Segment("WALL", 0, 0, 5, 0)
        b = Segment("WALL", 0, 1, 5, 1)
        ratio, _, _ = compare_segments(a, b, tolerance=0.15)
        self.assertEqual(ratio, 0.0)

    def test_centroid_alignment_translates_second_floor(self):
        first = FloorDrawing("P1", "p1.dxf", [Segment("W", 0, 0, 4, 0)])
        second = FloorDrawing("P2", "p2.dxf", [Segment("W", 10, 5, 14, 5)])
        align_by_centroid([first, second])
        self.assertAlmostEqual(second.segments[0].x1, 0.0)
        self.assertAlmostEqual(second.segments[0].y1, 0.0)


if __name__ == "__main__":
    unittest.main()
