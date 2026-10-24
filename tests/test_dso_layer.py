"""DSO layer: type mapping, 999 handling, de-duplication, binary loading (stdlib unittest, no GUI).
Run from the repo root:  python -m unittest tests.test_dso_layer -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro import dso_layer as dl  # noqa: E402
from astro.dso_catalog_binary import DsoRecord  # noqa: E402
from tests.test_binary_catalogs import awds, rec  # noqa: E402

NAN = float("nan")


def r(desig, typ="g", ra=10.0, dec=20.0, mag=8.0, dmaj=5.0):
    return DsoRecord(desig, desig, typ, "", "", "", "", ra, dec, mag, dmaj, dmaj, NAN)


class Rows(unittest.TestCase):
    def test_mapping_and_drops(self):
        rows, dropped = dl.rows_from([r("a", "gc"), r("b", "oc"), r("c", "xx"), r("d", mag=999.0), r("e", dec=95.0), r("f", ra=400.0),
                                      r("g", "dn")])
        self.assertEqual([x["kind"] for x in rows], ["GC", "OC"])
        self.assertEqual(dropped, 5)

    def test_missing_dimension_is_zero_and_arcmin_kept(self):
        rows, _ = dl.rows_from([r("a", dmaj=NAN), r("b", dmaj=11.5)])
        self.assertEqual([x["size"] for x in rows], [0.0, 11.5])


class Dedupe(unittest.TestCase):
    def test_named_catalog_wins_and_nearby_duplicates_collapse(self):
        rows, _ = dl.rows_from([r("M31", ra=10.68, dec=41.27, mag=3.4), r("NGC 224", ra=10.684, dec=41.269, mag=4.0),
                                r("X", ra=50.0, dec=-30.0, mag=9.0), r("Y", ra=50.0, dec=-29.0, mag=9.5)])
        s = dl.DsoSet(rows, named=[(10.68, 41.27)])
        self.assertEqual([x["id"] for x in s.rows], ["X", "Y"])
        self.assertEqual(s.n_skipped, 2)

    def test_ra_wrap(self):
        rows, _ = dl.rows_from([r("A", ra=359.98, dec=10.0), r("B", ra=0.02, dec=10.0)])
        self.assertEqual(len(dl.DsoSet(rows).rows), 1)

    def test_sorted_by_magnitude_prefix(self):
        rows, _ = dl.rows_from([r("A", ra=1.0, mag=9.0), r("B", ra=20.0, mag=5.0), r("C", ra=40.0, mag=7.0)])
        s = dl.DsoSet(rows)
        self.assertEqual(s.mags, [5.0, 7.0, 9.0])


class Loading(unittest.TestCase):
    def test_missing_file_is_empty_and_corrupt_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIs(dl.load_set("dsos.6.awds", d), dl.EMPTY)
            os.makedirs(os.path.join(d, "binary"))
            with open(os.path.join(d, "binary", "dsos.6.awds"), "wb") as f:
                f.write(b"AWDS" + b"\0" * 5)
            with self.assertRaises(ValueError):
                dl.load_set("dsos.6.awds", d)

    def test_loads_valid_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "binary"))
            with open(os.path.join(d, "binary", "dsos.6.awds"), "wb") as f:
                f.write(awds([rec(desig="NGC 1", typ="oc", ra=30.0, dec=5.0, mag=5.0), rec(desig="NGC 2", typ="g", mag=999.0, ra=60.0)]))
            s = dl.load_set("dsos.6.awds", d)
        self.assertEqual([x["id"] for x in s.rows], ["NGC 1"])


if __name__ == "__main__":
    unittest.main()
