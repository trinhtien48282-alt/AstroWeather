"""Constellation data parsing, projection and failure handling (stdlib unittest, no GUI, no network).

Run from the repo root:  python -m unittest tests.test_constellations -v
The real-data test runs only when data/constellations.lines.json has been added to the checkout.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro import constellations as con  # noqa: E402
from astro.core import altaz, precess  # noqa: E402
from astro.numpy_engine import HAVE_NUMPY, PERF  # noqa: E402

LINES = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": "Tst", "properties": {}, "geometry": {
        "type": "MultiLineString", "coordinates": [[[-170, 10], [-160, 20], [-150, 30]], [[10, -20], [20, -30]]]}},
    {"type": "Feature", "id": "Lin", "properties": {}, "geometry": {
        "type": "LineString", "coordinates": [[0, 0], [5, 5], [5, 5.0]]}},
    {"type": "Feature", "id": "Dup", "properties": {}, "geometry": {
        "type": "MultiLineString", "coordinates": [[[100, 0], [110, 0]]]}},
    {"type": "Feature", "id": "Dup", "properties": {}, "geometry": {
        "type": "MultiLineString", "coordinates": [[[-100, 0], [-90, 0]]]}}]}
NAMES = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": "Tst", "properties": {"desig": "Tst", "name": "Testudo", "en": "Test Turtle"},
     "geometry": {"type": "Point", "coordinates": [-165, 15]}},
    {"type": "Feature", "id": "Dup", "properties": {"name": "Duplicus Prior", "en": "Twin"},
     "geometry": {"type": "Point", "coordinates": [10, 10]}},
    {"type": "Feature", "id": "Dup", "properties": {"name": "Duplicus Posterior", "en": "Twin"},
     "geometry": {"type": "Point", "coordinates": [20, 10]}}]}
JD, LAT, LON = 2461000.5, 9.1769, 105.1524  # a fixed instant and Ca Mau


def expected_segments(lines):
    out = []
    for polylines in lines.values():
        for pl in polylines:
            ends = [altaz(*precess(ra, dec, JD), JD, LAT, LON) for ra, dec in pl]
            out += [a + b for a, b in zip(ends, ends[1:]) if a[0] > 0 and b[0] > 0]
    return out


class ParseTests(unittest.TestCase):
    def test_lines_fold_ra_and_keep_figures(self):
        d = con.parse_lines(LINES)
        self.assertEqual(d["Tst"][0], [(190.0, 10.0), (200.0, 20.0), (210.0, 30.0)])  # -170 deg -> RA 190 deg
        self.assertEqual(d["Tst"][1], [(10.0, -20.0), (20.0, -30.0)])
        self.assertEqual(len(d["Lin"]), 1)

    def test_names_use_the_latin_name_not_the_english_gloss(self):
        n = con.parse_names(NAMES)
        self.assertEqual(n["Tst"], ("Testudo", 195.0, 15.0))
        self.assertNotIn("Test Turtle", [v[0] for v in n.values()])

    def test_duplicate_ids_keep_both_features_in_order(self):
        d, n = con.parse_lines(LINES), con.parse_names(NAMES)
        self.assertEqual(sorted(k for k in d if k.startswith("Dup")), ["Dup", "Dup#2"])
        self.assertEqual([n["Dup"][0], n["Dup#2"][0]], ["Duplicus Prior", "Duplicus Posterior"])
        self.assertEqual(d["Dup"][0][0][0], 100.0)
        self.assertEqual(d["Dup#2"][0][0][0], 260.0)

    def test_label_sits_at_the_centre_of_the_figure_even_across_ra_zero(self):
        s = con.ConstellationSet({"W": [[(359.0, 10.0), (1.0, 10.0)]]}, {"W": ("Wrap", 180.0, 0.0)})
        (name, ra, dec), = s.labels
        self.assertEqual(name, "Wrap")
        self.assertTrue(ra < 0.01 or ra > 359.99)  # not 180, not the naive mean
        self.assertAlmostEqual(dec, 10.0, delta=0.05)

    def test_label_falls_back_to_the_anchor_without_lines(self):
        s = con.ConstellationSet({}, {"N": ("Nolines", 40.0, -20.0)})
        self.assertEqual(s.labels, [("Nolines", 40.0, -20.0)])

    def test_malformed_documents_raise(self):
        for bad in ({}, {"features": 3}, {"features": [{"geometry": {}}]},
                    {"features": [{"id": "X", "geometry": {"type": "Polygon", "coordinates": []}}]},
                    {"features": [{"id": "X", "geometry": {"type": "LineString", "coordinates": [[0, 95], [1, 1]]}}]},
                    {"features": [{"id": "X", "geometry": {"type": "LineString", "coordinates": [["a", 1], [1, 1]]}}]}):
            with self.assertRaises((ValueError, TypeError), msg=bad):
                con.parse_lines(bad)
        with self.assertRaises(ValueError):
            con.parse_names({"features": [{"id": "X", "geometry": {"type": "LineString", "coordinates": []}}]})


class LoadTests(unittest.TestCase):
    def write(self, d, name, doc):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(doc if isinstance(doc, str) else json.dumps(doc))

    def test_load_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, con.LINES_FILE, LINES)
            self.write(d, con.NAMES_FILE, NAMES)
            s = con.load_set(d)
        self.assertEqual((s.n_lines, len(s.segs), len(s.labels)), (4, 7, 3))  # Tst 3, Lin 2, Dup 1+1 segments; 3 names

    def test_missing_files_give_an_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            s = con.load_set(d)
        self.assertEqual((s.segments(JD, LAT, LON), s.label_positions(JD, LAT, LON)), ([], []))

    def test_invalid_json_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, con.LINES_FILE, "{not json")
            with self.assertRaises(ValueError):
                con.load_set(d)

    def test_get_constellations_never_raises(self):
        con._CACHE.clear()
        old = con.data_dir
        with tempfile.TemporaryDirectory() as d:
            self.write(d, con.LINES_FILE, "{not json")
            con.data_dir = lambda: d
            try:
                s, err = con.get_constellations()
            finally:
                con.data_dir = old
                con._CACHE.clear()
        self.assertIs(s, con.EMPTY)
        self.assertIn("unusable", err)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.set = con.ConstellationSet(con.parse_lines(LINES), con.parse_names(NAMES))
        self.want = expected_segments(con.parse_lines(LINES))
        self.addCleanup(PERF.__setitem__, "numpy", PERF["numpy"])

    def check(self):
        got = self.set.segments(JD, LAT, LON)
        self.assertEqual(len(got), len(self.want))
        for g, w in zip(got, self.want):
            for a, b in zip(g, w):
                self.assertAlmostEqual(a, b, places=6)

    def test_scalar_path_matches_direct_calls(self):
        PERF["numpy"] = False
        self.check()

    @unittest.skipUnless(HAVE_NUMPY, "NumPy not installed")
    def test_numpy_path_matches_scalar(self):
        PERF["numpy"] = True
        self.check()

    def test_something_is_visible_and_something_is_hidden(self):
        self.assertTrue(0 < len(self.want) < len(self.set.segs))  # the fixture exercises the horizon cut

    def test_horizon_crossing_segment_is_cut_on_its_great_circle(self):
        import math
        PERF["numpy"] = False
        p1, p2 = (190.0, 10.0), (200.0, 20.0)
        one = con.ConstellationSet({"X": [[p1, p2]]}, {})

        def v(a, z):
            a, z = math.radians(a), math.radians(z)
            return (math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a))

        def det(a, b, c):
            return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]))
        found = 0
        for k in range(0, 48 * 4):  # scan a day in 15-minute steps for instants where exactly one end is up
            jd = JD + k / 96.0
            e1, e2 = altaz(*precess(*p1, jd), jd, LAT, LON), altaz(*precess(*p2, jd), jd, LAT, LON)
            if (e1[0] > 0) == (e2[0] > 0):
                self.assertEqual(len(one.segments(jd, LAT, LON)), 1 if e1[0] > 0 else 0)
                continue
            (seg,) = one.segments(jd, LAT, LON)
            up, dn = (e1, e2) if e1[0] > 0 else (e2, e1)
            vis = (seg[0], seg[1]) if seg[2] == 0.0 else (seg[2], seg[3])
            cut = (0.0, seg[3]) if seg[2] == 0.0 else (0.0, seg[1])
            self.assertEqual(seg[0] == 0.0 or seg[2] == 0.0, True)
            self.assertAlmostEqual(vis[0], up[0], places=9)
            self.assertAlmostEqual(vis[1], up[1], places=9)
            self.assertLess(abs(det(v(*up), v(*cut), v(*dn))), 1e-9)  # cut point lies on the great circle up -> down
            found += 1
        self.assertGreater(found, 0, "no horizon crossing in the scanned day")

    def test_label_below_horizon_is_dropped(self):
        PERF["numpy"] = False
        up = sum(1 for _n, ra, dec in self.set.labels if altaz(*precess(ra, dec, JD), JD, LAT, LON)[0] > 0)
        self.assertEqual(len(self.set.label_positions(JD, LAT, LON)), up)


@unittest.skipUnless(os.path.exists(os.path.join(con.data_dir(), con.LINES_FILE)), "bundled data not added yet")
class BundledDataTests(unittest.TestCase):
    def test_real_files_parse_and_orion_matches_betelgeuse(self):
        s = con.load_set()
        self.assertGreaterEqual(s.n_lines, 80)
        # Betelgeuse (RA 5.919 h, Dec +7.407, J2000) must be an endpoint of some Orion segment
        bet_ra, bet_dec = 5.919 * 15.0, 7.407
        self.assertTrue(any(abs(ra - bet_ra) < 0.6 and abs(dec - bet_dec) < 0.6 for ra, dec in zip(s.pts_ra, s.pts_dec)))

    @unittest.skipUnless(os.path.exists(os.path.join(con.data_dir(), con.NAMES_FILE)), "names file not added")
    def test_real_names_are_latin_and_complete(self):
        s = con.load_set()
        names = [n for n, _r, _d in s.labels]
        self.assertIn("Triangulum", names)
        self.assertIn("Puppis", names)
        self.assertNotIn("Poop Deck", names)
        self.assertNotIn("Triangle", names)
        self.assertEqual(names.count("Serpens Caput") + names.count("Serpens Cauda"), 2)
        self.assertGreaterEqual(len(names), 85)


if __name__ == "__main__":
    unittest.main()
