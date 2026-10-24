"""AWST / AWDS binary readers. Fixtures are packed here with struct, independently of scripts/convert_catalogs.py.
Run from the repo root:  python -m unittest tests.test_binary_catalogs -v"""
import json
import math
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro import dso_catalog_binary as dso  # noqa: E402

NAN = float("nan")


def awds(records, *, magic=b"AWDS", version=1, rec_size=74, table_override=None, count=None, extra=b""):
    """records: [(7 strings, ra, dec, mag, dmaj, dmin, bv)] -> file bytes."""
    table, recs = bytearray(), bytearray()
    for strings, *nums in records:
        offs, lens = [], []
        for s in strings:
            b = s.encode("utf-8")
            offs.append(len(table))
            lens.append(len(b))
            table += b
        recs += struct.pack("<7I7Hddffff", *offs, *lens, *nums)
    if table_override is not None:
        table = bytearray(table_override)
    n = len(records) if count is None else count
    return struct.pack("<4sHHQQ", magic, version, rec_size, n, len(table)) + bytes(recs) + bytes(table) + extra


def rec(desig="M31", fid="M31", typ="g", ra=10.68, dec=41.27, mag=3.4, dmaj=178.0, dmin=63.0, bv=0.9, s=("", "", "", "")):
    return ((fid, desig, typ, *s), ra, dec, mag, dmaj, dmin, bv)


class Base(unittest.TestCase):
    def open(self, blob):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "x.awds")
        with open(p, "wb") as f:
            f.write(blob)
        return dso.DsoCatalogBinary(p)


class AwdsFormat(Base):
    def test_sizes_match_the_spec(self):
        self.assertEqual(dso.HEADER.size, 24)
        self.assertEqual(dso.RECORD.size, 74)

    def test_round_trip_incl_unicode_empty_and_byte_lengths(self):
        name = "Nébula Ω"
        c = self.open(awds([rec(desig=name, fid="", s=("é", "", "x", ""))]))
        r = c[0]
        self.assertEqual((r.desig, r.feature_id, r.type, r.morph, r.sub, r.pop, r.stream), (name, "", "g", "é", "", "x", ""))
        self.assertGreater(len(name.encode()), len(name))  # lengths are bytes, not characters
        self.assertAlmostEqual(r.ra, 10.68)
        self.assertAlmostEqual(r.mag, 3.4, places=5)
        self.assertEqual(len(c), 1)

    def test_missing_values(self):
        r = self.open(awds([rec(mag=999.0, dmaj=NAN, dmin=NAN, bv=NAN)]))[0]
        self.assertFalse(r.has_mag)
        self.assertFalse(r.has_dim)
        self.assertTrue(math.isnan(r.bv))
        self.assertTrue(self.open(awds([rec()]))[0].has_mag)

    def test_empty_catalogue(self):
        c = self.open(awds([]))
        self.assertEqual((len(c), list(c)), (0, []))

    def test_bad_headers(self):
        for kw, msg in ((dict(magic=b"AWST"), "Not an AWDS"), (dict(version=2), "Unsupported"), (dict(rec_size=70), "record size")):
            with self.assertRaisesRegex(ValueError, msg):
                self.open(awds([rec()], **kw))

    def test_truncated_and_trailing_bytes(self):
        good = awds([rec()])
        for bad in (good[:10], good[:-1], good[:30], good + b"\0"):
            with self.assertRaises(ValueError):
                self.open(bad)

    def test_count_larger_than_file(self):
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            self.open(awds([rec()], count=10**12))

    def test_string_ranges_are_checked(self):
        blob = bytearray(awds([rec()]))
        base = dso.HEADER.size
        struct.pack_into("<I", blob, base + 4, 10_000)  # desig offset beyond the table
        with self.assertRaisesRegex(ValueError, "outside"):
            self.open(bytes(blob))[0]
        blob = bytearray(awds([rec()]))
        struct.pack_into("<H", blob, base + 28 + 2, 65535)  # desig length too long
        with self.assertRaisesRegex(ValueError, "outside"):
            self.open(bytes(blob))[0]

    def test_malformed_utf8(self):
        blob = bytearray(awds([rec(fid="", desig="ab")]))
        blob[-2:] = b"\xff\xfe"
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            self.open(bytes(blob))[0]

    def test_index_errors(self):
        c = self.open(awds([rec()]))
        self.assertEqual(c[-1].desig, "M31")
        with self.assertRaises(IndexError):
            c[1]
        with self.assertRaises(TypeError):
            c["a"]


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


@unittest.skipUnless(os.path.isdir(os.path.join(DATA, "binary")), "data/binary not present")
class RealDataVsJson(unittest.TestCase):
    """Independent check of the generated files against the source GeoJSON (counts, order, coordinates, 999, NaN)."""

    def test_dso_files(self):
        checked = 0
        for name in ("dsos.6", "dsos.14", "dsos.bright", "messier", "lg"):
            jp, bp = os.path.join(DATA, name + ".json"), os.path.join(DATA, "binary", name + ".awds")
            if not (os.path.exists(jp) and os.path.exists(bp)):
                continue
            with open(jp, encoding="utf-8") as f:
                feats = json.load(f)["features"]
            valid = [x for x in feats if -90 <= float(x["geometry"]["coordinates"][1]) <= 90
                     and -180 <= float(x["geometry"]["coordinates"][0]) <= 180]
            c = dso.DsoCatalogBinary(bp)
            self.assertEqual(len(c), len(valid), name)
            for src, r in zip(valid, c):
                lon, dec = src["geometry"]["coordinates"][:2]
                self.assertAlmostEqual(r.ra, float(lon) % 360.0, places=9, msg=name)
                self.assertAlmostEqual(r.dec, float(dec), places=9, msg=name)
                p = src.get("properties") or {}
                self.assertEqual(r.desig, str(p.get("desig") or src.get("id") or ""), name)
                m = p.get("mag")
                self.assertEqual(r.has_mag, m not in (None, "") and float(m) < 999, name)
                checked += 1
        self.assertGreater(checked, 0)


try:
    from astro import star_catalog_binary as awst
except Exception:  # pragma: no cover
    awst = None


@unittest.skipIf(awst is None, "astro.star_catalog_binary not importable")
class AwstFormat(unittest.TestCase):
    def blob(self, recs, magic=b"AWST", version=1, rec_size=28, count=None):
        return struct.pack("<4sHHQ", magic, version, rec_size, len(recs) if count is None else count) + b"".join(
            struct.pack("<Iddff", *r) for r in recs)

    def open(self, blob):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "x.awst")
        with open(p, "wb") as f:
            f.write(blob)
        c = awst.StarCatalogBinary(p)
        self.addCleanup(c.close)
        return c

    def test_sizes_and_round_trip(self):
        self.assertEqual((awst.HEADER.size, awst.RECORD.size), (16, 28))
        c = self.open(self.blob([(32349, 101.28, -16.72, -1.46, 0.0), (1, 2.0, 3.0, 5.5, NAN)]))
        self.assertEqual((len(c), c[0].hip_id), (2, 32349))
        self.assertAlmostEqual(c[0].magnitude, -1.46, places=5)
        self.assertTrue(c[0].has_bv)
        self.assertFalse(c[1].has_bv)

    def test_rejects_bad_files(self):
        good = self.blob([(1, 2.0, 3.0, 5.5, 0.1)])
        for bad in (good[:8], good[:-1], good + b"\0", self.blob([], magic=b"XXXX"), self.blob([], version=2), self.blob([], rec_size=24)):
            with self.assertRaises(ValueError):
                awst.StarCatalogBinary(self.write(bad))

    def write(self, blob):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "bad.awst")
        with open(p, "wb") as f:
            f.write(blob)
        return p

    def test_empty_catalogue(self):
        self.assertEqual(len(self.open(self.blob([]))), 0)


if __name__ == "__main__":
    unittest.main()
