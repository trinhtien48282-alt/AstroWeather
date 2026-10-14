"""Altitude-graph zoom/pan/interpolation logic (stdlib unittest, no GUI). Run: python -m unittest tests.test_altitude_graph -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.altitude_graph import MIN_SPAN, fit_view, lerp, zoom_view  # noqa: E402

F0, F1 = 0.0, 36000.0  # a 10 h plan


class ViewTests(unittest.TestCase):
    def test_full_window_is_none(self):
        self.assertIsNone(fit_view(F0, F1, F0, F1))
        self.assertIsNone(fit_view(-500, F1 + 500, F0, F1))

    def test_clamped_into_range_keeps_span(self):
        self.assertEqual(fit_view(-1000, 9000, F0, F1), (0.0, 10000.0))
        self.assertEqual(fit_view(30000, 40000, F0, F1), (26000.0, 36000.0))

    def test_min_span(self):
        v = fit_view(1000, 1100, F0, F1)
        self.assertAlmostEqual(v[1] - v[0], MIN_SPAN)

    def test_zoom_keeps_time_under_cursor(self):
        v = zoom_view(None, F0, F1, 0.25, 2.0)  # cursor at t = 9000
        self.assertAlmostEqual(v[1] - v[0], 18000.0)
        self.assertAlmostEqual(v[0] + 0.25 * (v[1] - v[0]), 9000.0)

    def test_zoom_out_returns_to_fit(self):
        v = zoom_view(None, F0, F1, 0.5, 4.0)
        self.assertIsNone(zoom_view(v, F0, F1, 0.5, 0.1))

    def test_zoom_stops_at_min_span(self):
        v = None
        for _ in range(40):
            v = zoom_view(v, F0, F1, 0.5, 1.25) or v
        self.assertGreaterEqual(v[1] - v[0], MIN_SPAN - 1e-6)


class LerpTests(unittest.TestCase):
    ts, arr = [0.0, 10.0, 20.0], [0.0, 10.0, 40.0]

    def test_samples_and_midpoints(self):
        self.assertEqual(lerp(self.ts, self.arr, 0.0), 0.0)
        self.assertEqual(lerp(self.ts, self.arr, 5.0), 5.0)
        self.assertEqual(lerp(self.ts, self.arr, 15.0), 25.0)
        self.assertEqual(lerp(self.ts, self.arr, 20.0), 40.0)


if __name__ == "__main__":
    unittest.main()
