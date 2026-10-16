"""Constellation line figures and name labels for the sky chart (no GUI).

Data: d3-celestial by Olaf Frohn (BSD 3-Clause), files `constellations.lines.json` and `constellations.json`.
Both are GeoJSON. Per the upstream readme (read on github.com/ofrohn/d3-celestial): positions are J2000, longitude is
right ascension in degrees folded to -180..180 (0..12 h -> 0..180, 12..24 h -> -180..0), latitude is declination in
degrees; line features are MultiLineString. This module folds RA back into 0..360. The feature `id`/`properties` keys
used for names are NOT yet confirmed against the real files (see tests.BundledDataTests).
Line figures are traditional stick figures; they are NOT IAU boundaries and carry no proper motion.
Positions of date come from astro.core.precess (IAU 1976 precession, no nutation, no proper motion):
good to a few arcminutes, far below what a chart needs.

Depends on astro.core and astro.numpy_engine only. NumPy is optional (scalar fallback gives the same numbers).
"""
import json
import math
import os
import sys

from astro.core import altaz, precess
from astro.numpy_engine import np, np_altaz, np_precess, use_numpy

LINES_FILE = "constellations.lines.json"
NAMES_FILE = "constellations.json"


def data_dir():
    """`data/` next to the sources, or inside the PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "data")


def _features(doc, what):
    if not isinstance(doc, dict) or not isinstance(doc.get("features"), list):
        raise ValueError(f"{what}: not a GeoJSON FeatureCollection")
    return doc["features"]


def _fid(f, what):
    cid = f.get("id") or (f.get("properties") or {}).get("desig")
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"{what}: feature without an id")
    return cid


def _point(lon, lat, what):
    lon, lat = float(lon), float(lat)
    if not (-180.0 <= lon <= 360.0 and -90.0 <= lat <= 90.0):
        raise ValueError(f"{what}: coordinate out of range ({lon}, {lat})")
    return lon % 360.0, lat


def parse_lines(doc):
    """GeoJSON lines document -> {id: [polyline, ...]}, polyline = [(ra_deg, dec_deg), ...] (J2000)."""
    out = {}
    for f in _features(doc, "lines"):
        cid = _fid(f, "lines")
        g = f.get("geometry") or {}
        if g.get("type") == "MultiLineString":
            raw = g.get("coordinates")
        elif g.get("type") == "LineString":
            raw = [g.get("coordinates")]
        else:
            raise ValueError(f"lines: {cid}: unsupported geometry {g.get('type')!r}")
        if not isinstance(raw, list):
            raise ValueError(f"lines: {cid}: no coordinates")
        out[cid] = [pl for pl in ([_point(p[0], p[1], f"lines {cid}") for p in line] for line in raw) if len(pl) >= 2]
    return out


def parse_names(doc):
    """GeoJSON names document -> {id: (name, ra_deg, dec_deg)}: label anchor in J2000."""
    out = {}
    for f in _features(doc, "names"):
        cid = _fid(f, "names")
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            raise ValueError(f"names: {cid}: unsupported geometry {g.get('type')!r}")
        props = f.get("properties") or {}
        name = props.get("en") or props.get("name") or cid
        ra, dec = _point(g["coordinates"][0], g["coordinates"][1], f"names {cid}")
        out[cid] = (str(name), ra, dec)
    return out


class ConstellationSet:
    """All figures flattened once, so each redraw is one vectorised precession + Alt/Az pass."""

    def __init__(self, lines, names):
        self.pts_ra, self.pts_dec, self.segs = [], [], []
        for polylines in lines.values():
            for pl in polylines:
                base = len(self.pts_ra)
                for ra, dec in pl:
                    self.pts_ra.append(ra)
                    self.pts_dec.append(dec)
                self.segs.extend((base + k, base + k + 1) for k in range(len(pl) - 1))
        self.labels = [(n, ra, dec) for n, ra, dec in names.values()]
        self.n_lines = len(lines)

    def _altaz(self, ra, dec, jd, lat, lon):
        if not ra:
            return [], []
        if use_numpy():
            a, z = np_altaz(*np_precess(np.asarray(ra, float), np.asarray(dec, float), jd), jd, lat, lon)
            return a.tolist(), z.tolist()
        alts, azs = [], []
        for r, d in zip(ra, dec):
            a, z = altaz(*precess(r, d, jd), jd, lat, lon)
            alts.append(a)
            azs.append(z)
        return alts, azs

    def segments(self, jd, lat, lon):
        """[(alt1, az1, alt2, az2)] for the parts of segments above the horizon (degrees, azimuth from north).
        A segment crossing the horizon is cut exactly at alt = 0 along its great-circle arc."""
        alts, azs = self._altaz(self.pts_ra, self.pts_dec, jd, lat, lon)
        out = []
        for i, j in self.segs:
            a1, a2 = alts[i], alts[j]
            if a1 > 0 and a2 > 0:
                out.append((a1, azs[i], a2, azs[j]))
            elif a1 > 0 or a2 > 0:
                up, dn = (i, j) if a1 > 0 else (j, i)
                cut = _horizon_cut(alts[up], azs[up], alts[dn], azs[dn])
                out.append((alts[up], azs[up], 0.0, cut) if up == i else (0.0, cut, alts[up], azs[up]))
        return out

    def label_positions(self, jd, lat, lon):
        """[(name, alt, az)] for labels above the horizon."""
        alts, azs = self._altaz([l[1] for l in self.labels], [l[2] for l in self.labels], jd, lat, lon)
        return [(l[0], a, z) for l, a, z in zip(self.labels, alts, azs) if a > 0]


def _horizon_cut(alt_up, az_up, alt_dn, az_dn):
    """Azimuth where the great-circle arc from a point above the horizon to one at or below it reaches alt = 0.
    Unit vectors v = (cos a sin z, cos a cos z, sin a); the chord between them crosses z = 0 at t = z1 / (z1 - z2),
    and normalising does not move that crossing, so the point stays on the arc."""
    def vec(a, z):
        a, z = math.radians(a), math.radians(z)
        return math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a)
    v1, v2 = vec(alt_up, az_up), vec(alt_dn, az_dn)
    t = v1[2] / (v1[2] - v2[2])
    x, y = v1[0] + t * (v2[0] - v1[0]), v1[1] + t * (v2[1] - v1[1])
    return math.degrees(math.atan2(x, y)) % 360.0


EMPTY = ConstellationSet({}, {})
_CACHE = {}


def load_set(directory=None):
    """Read both files. A missing file is not an error (empty part); a malformed one raises ValueError."""
    directory = directory or data_dir()

    def read(name):
        try:
            with open(os.path.join(directory, name), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            raise ValueError(f"{name}: invalid JSON ({e})") from e
    lines, names = read(LINES_FILE), read(NAMES_FILE)
    return ConstellationSet(parse_lines(lines) if lines else {}, parse_names(names) if names else {})


def get_constellations():
    """Lazy, cached. -> (ConstellationSet, error text or ''). Never raises: the chart just shows no figures."""
    if "set" not in _CACHE:
        try:
            _CACHE["set"], _CACHE["err"] = load_set(), ""
        except (ValueError, OSError) as e:
            _CACHE["set"], _CACHE["err"] = EMPTY, f"constellation data unusable: {e}"
    return _CACHE["set"], _CACHE["err"]
