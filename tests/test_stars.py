"""Faint-star data parsing, matching and projection (stdlib unittest, no GUI, no network).

Run from the repo root:  python -m unittest tests.test_stars -v
The real-data test runs only when data/stars.6.json has been added to the checkout.
"""
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro import stars as st  # noqa: E402
from astro.catalog import BRIGHT_STARS  # noqa: E402
from astro.core import altaz, precess  # noqa: E402
from astro.numpy_engine import HAVE_NUMPY, PERF  # noqa: E402

DOC = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": 1, "properties": {"mag": 5.5, "bv": "0.5"}, "geometry": {"type": "Point", "coordinates": [-170.0, 10.0]}},
    {"type": "Feature", "id": 2, "properties": {"mag": 2.0, "bv": ""}, "geometry": {"type": "Point", "coordinates": [10.0, -20.0]}},
    {"type": "Feature", "id": 3, "properties": {"mag": 3.5, "bv": "-0.1"}, "geometry": {"type": "Point", "coordinates": [100.0, 30.0]}},
    {"type": "Feature", "id": 4, "properties": {"mag": 4.0}, "geometry": {"type": "Point", "coordinates": [100.01, 30.0]}}]}
JD, LAT, LON = 2461000.5, 9.1769, 105.1524


class ParseTests(unittest.TestCase):
    def test_fields_and_ra_fold(self):
        rows = st.parse_stars(DOC)
        self.assertEqual(rows[0], (1, 190.0, 10.0, 5.5, 0.5))
        self.assertIsNone(rows[1][4])      # empty colour index -> None, not 0.0
        self.assertIsNone(rows[3][4])      # missing colour index -> None

    def test_malformed_documents_raise(self):
        for bad in ({}, {"features": 3},
                    {"features": [{"id": 1, "properties": {"mag": 1}, "geometry": {"type": "LineString", "coordinates": []}}]},
                    {"features": [{"id": 1, "properties": {"mag": 1}, "geometry": {"type": "Point", "coordinates": [0, 95]}}]},
                    {"features": [{"id": 1, "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 5]}}]}):
            with self.assertRaises((ValueError, KeyError, TypeError), msg=bad):
                st.parse_stars(bad)


class SetTests(unittest.TestCase):
    def setUp(self):
        self.rows = st.parse_stars(DOC)
        self.addCleanup(PERF.__setitem__, "numpy", PERF["numpy"])

    def test_named_star_is_excluded_by_position(self):
        s = st.StarSet(self.rows, named=[(100.0, 30.0)])   # id 3 is the named star, id 4 (0.0087 deg away in RA) is also within tolerance
        self.assertEqual(s.n_skipped, 1)
        self.assertEqual(len(s.rows), 3)
        self.assertNotIn(3, [r[0] for r in s.rows])

    def test_sorted_by_magnitude_and_limit_is_a_prefix(self):
        s = st.StarSet(self.rows)
        self.assertEqual(s.mags, sorted(s.mags))
        PERF["numpy"] = False
        self.assertEqual(len(s.visible(JD, LAT, LON, 1.0)), 0)
        self.assertLessEqual(len(s.visible(JD, LAT, LON, 3.0)), 1)

    def check(self, limit):
        s = st.StarSet(self.rows)
        want = []
        for _h, ra, dec, m, _b in s.rows:
            if m <= limit:
                a, z = altaz(*precess(ra, dec, JD), JD, LAT, LON)
                if a > 0:
                    want.append((a, z, m))
        got = s.visible(JD, LAT, LON, limit)
        self.assertEqual(len(got), len(want))
        for g, w in zip(got, want):
            for a, b in zip(g, w):
                self.assertAlmostEqual(a, b, places=6)

    def test_scalar_path_matches_direct_calls(self):
        PERF["numpy"] = False
        self.check(6.0)

    @unittest.skipUnless(HAVE_NUMPY, "NumPy not installed")
    def test_numpy_path_matches_scalar(self):
        PERF["numpy"] = True
        self.check(6.0)


class LoadTests(unittest.TestCase):
    def test_missing_file_gives_an_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(st.load_set(d), st.EMPTY)

    def test_invalid_json_raises_and_get_stars_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, st.STARS_FILE), "w") as f:
                f.write("{not json")
            with self.assertRaises(ValueError):
                st.load_set(d)
            st._CACHE.clear()
            old, st.data_dir = st.data_dir, (lambda: d)
            try:
                s, err = st.get_stars()
            finally:
                st.data_dir = old
                st._CACHE.clear()
        self.assertIs(s, st.EMPTY)
        self.assertIn("unusable", err)


@unittest.skipUnless(os.path.exists(os.path.join(st.data_dir(), st.STARS_FILE)), "bundled data not added yet")
class BundledDataTests(unittest.TestCase):
    @staticmethod
    def load():
        with open(os.path.join(st.data_dir(), st.STARS_FILE), encoding="utf-8") as f:
            return json.load(f)

    def test_real_file_matches_the_bright_star_catalog(self):
        rows = st.parse_stars(self.load())
        self.assertGreaterEqual(len(rows), 5000)
        self.assertTrue(all(-2.0 <= r[3] <= 6.5 for r in rows))
        for name, ra_h, dec, mag in BRIGHT_STARS:  # same epoch and convention: every named star must be in the file
            ra = ra_h * 15.0
            d = min(math.hypot((((r[1] - ra) + 180.0) % 360.0 - 180.0) * math.cos(math.radians(dec)), r[2] - dec) for r in rows)
            self.assertLess(d, 0.02, name)

    def test_named_stars_are_not_duplicated(self):
        rows = st.parse_stars(self.load())
        s = st.StarSet(rows, named=[(h * 15.0, d) for _n, h, d, _m in BRIGHT_STARS])
        self.assertEqual(s.n_skipped, len(BRIGHT_STARS))
        self.assertEqual(len(s.rows), len(rows) - len(BRIGHT_STARS))


if __name__ == "__main__":
    unittest.main()
