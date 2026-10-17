"""Faint-star layer for the sky chart (no GUI).

Data: d3-celestial `stars.6.json` by Olaf Frohn (BSD 3-Clause): 5044 Hipparcos stars to magnitude 6, GeoJSON points,
feature `id` = HIP number, `properties` = {"mag": apparent V magnitude, "bv": B-V colour index as a string},
`coordinates` = [RA in degrees folded to -180..180, Dec in degrees], J2000 (checked against the 35 bright stars in
astro.catalog: every one matches within 0.008 deg and 0.3 mag). RA is folded back to 0..360 here.
No proper motion: positions of date come from astro.core.precess, good to a few arcminutes.

Depends on astro.core, astro.constellations (data_dir) and astro.numpy_engine only. NumPy is optional.
"""
import bisect
import json
import math
import os

from astro.constellations import data_dir
from astro.core import altaz, precess
from astro.numpy_engine import np, np_altaz, np_precess, use_numpy

STARS_FILE = "stars.6.json"
MATCH_DEG = 0.05  # a file star this close to a named catalog star is the same star


def parse_stars(doc):
    """GeoJSON stars document -> [(hip, ra_deg, dec_deg, mag, bv or None)] (J2000)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("features"), list):
        raise ValueError("stars: not a GeoJSON FeatureCollection")
    out = []
    for f in doc["features"]:
        g, p = f.get("geometry") or {}, f.get("properties") or {}
        if g.get("type") != "Point":
            raise ValueError(f"stars: {f.get('id')}: unsupported geometry {g.get('type')!r}")
        lon, lat, mag = float(g["coordinates"][0]), float(g["coordinates"][1]), float(p["mag"])
        if not (-180.0 <= lon <= 360.0 and -90.0 <= lat <= 90.0 and -3.0 <= mag <= 15.0):
            raise ValueError(f"stars: {f.get('id')}: value out of range ({lon}, {lat}, {mag})")
        try:
            bv = float(p.get("bv"))
        except (TypeError, ValueError):
            bv = None
        out.append((f.get("id"), lon % 360.0, lat, mag, bv))
    return out


class StarSet:
    """Stars sorted by magnitude, so a magnitude limit is a prefix slice and one vectorised pass does the rest."""

    def __init__(self, rows, named=()):
        """named: [(ra_deg, dec_deg)] of stars the chart already draws and makes clickable; they are left out here."""
        skip = set()
        for ra0, dec0 in named:
            cosd = math.cos(math.radians(dec0))
            best, best_d = None, MATCH_DEG
            for i, (_h, ra, dec, _m, _b) in enumerate(rows):
                d = math.hypot((((ra - ra0) + 180.0) % 360.0 - 180.0) * cosd, dec - dec0)
                if d < best_d:
                    best, best_d = i, d
            if best is not None:
                skip.add(best)
        kept = sorted((r for i, r in enumerate(rows) if i not in skip), key=lambda r: r[3])
        self.rows = kept
        self.mags = [r[3] for r in kept]
        self.ra = [r[1] for r in kept]
        self.dec = [r[2] for r in kept]
        self.n_skipped = len(skip)

    def visible(self, jd, lat, lon, mag_limit):
        """[(alt, az, mag)] for stars up to mag_limit that are above the horizon (degrees, azimuth from north)."""
        n = bisect.bisect_right(self.mags, mag_limit)
        if n == 0:
            return []
        if use_numpy():
            a, z = np_altaz(*np_precess(np.asarray(self.ra[:n], float), np.asarray(self.dec[:n], float), jd), jd, lat, lon)
            idx = np.nonzero(a > 0)[0]
            return [(float(a[i]), float(z[i]), self.mags[i]) for i in idx]
        out = []
        for r, d, m in zip(self.ra[:n], self.dec[:n], self.mags[:n]):
            a, z = altaz(*precess(r, d, jd), jd, lat, lon)
            if a > 0:
                out.append((a, z, m))
        return out


EMPTY = StarSet([])
_CACHE = {}


def load_set(directory=None, named=()):
    """Read the file. A missing file gives an empty set (not an error); a malformed one raises ValueError."""
    path = os.path.join(directory or data_dir(), STARS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return EMPTY
    except json.JSONDecodeError as e:
        raise ValueError(f"{STARS_FILE}: invalid JSON ({e})") from e
    return StarSet(parse_stars(doc), named)


def get_stars(named=()):
    """Lazy, cached. -> (StarSet, error text or ''). Never raises: the chart just shows no faint stars."""
    if "set" not in _CACHE:
        try:
            _CACHE["set"], _CACHE["err"] = load_set(named=named), ""
        except (ValueError, OSError, KeyError, TypeError) as e:
            _CACHE["set"], _CACHE["err"] = EMPTY, f"star data unusable: {e}"
    return _CACHE["set"], _CACHE["err"]
