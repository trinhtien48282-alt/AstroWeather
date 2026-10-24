"""Extra deep-sky objects for the sky chart from the AWDS binaries (no GUI).

The hand-made astro.catalog.CATALOG keeps its names, sizes and scope ratings; objects that are already there
(same place, within MATCH_DEG) are left out here. Types come from d3-celestial; only types that map onto the
chart's KIND_NAMES are kept. Objects without a magnitude (999) are not drawn. Positions are J2000, no proper motion.
Depends on astro.dso_catalog_binary; astro.core / astro.numpy_engine / astro.constellations load lazily.
"""
import bisect
import math
import os

from astro.dso_catalog_binary import DsoCatalogBinary

MATCH_DEG = 0.1
CELLS = round(360.0 / MATCH_DEG)  # RA grid cells, so a neighbour across 0/360 deg is found
BINARY_DIR = "binary"
# (deepest magnitude the file covers, file): the shallowest file that is deep enough is loaded
FILES = ((6.0, "dsos.6.awds"), (14.0, "dsos.14.awds"))
KIND_OF = {"g": "GX", "gg": "GX", "s": "GX", "s0": "GX", "sd": "GX", "i": "GX", "e": "GX", "oc": "OC", "gc": "GC",
           "bn": "EN", "en": "EN", "rn": "EN", "sfr": "EN", "pn": "PN", "snr": "SNR"}  # dn (dark nebula) has no chart kind


def rows_from(records):
    """DsoRecord iterable -> ([row dicts], n_dropped). Dropped: unmapped type, no magnitude, non-finite or out-of-range position."""
    rows, dropped = [], 0
    for r in records:
        kind = KIND_OF.get(r.type)
        if (kind is None or not r.has_mag or not (math.isfinite(r.ra) and math.isfinite(r.dec))
                or not (0.0 <= r.ra < 360.0 and -90.0 <= r.dec <= 90.0)):
            dropped += 1
            continue
        rows.append({"id": r.desig or r.feature_id, "kind": kind, "ra": r.ra, "dec": r.dec, "mag": r.mag,
                     "size": r.dim_major if r.has_dim else 0.0})
    return rows, dropped


class DsoSet:
    """Rows sorted by magnitude (a limit is a prefix), de-duplicated by position against `named` and against each other."""

    def __init__(self, rows, named=()):
        grid, kept = {}, []

        def near(ra, dec):
            cosd = max(0.01, math.cos(math.radians(dec)))
            cx, cy = int(ra // MATCH_DEG), int((dec + 90.0) // MATCH_DEG)
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for ra2, dec2 in grid.get((gx % CELLS, gy), ()):
                        if math.hypot((((ra - ra2) + 180.0) % 360.0 - 180.0) * cosd, dec - dec2) < MATCH_DEG:
                            return True
            return False

        def add(ra, dec):
            grid.setdefault((int(ra // MATCH_DEG) % CELLS, int((dec + 90.0) // MATCH_DEG)), []).append((ra, dec))

        for ra, dec in named:
            add(ra % 360.0, dec)
        for row in sorted(rows, key=lambda r: r["mag"]):
            if near(row["ra"], row["dec"]):
                continue
            add(row["ra"], row["dec"])
            kept.append(row)
        self.rows, self.mags = kept, [r["mag"] for r in kept]
        self.n_skipped = len(rows) - len(kept)

    def visible(self, jd, lat, lon, mag_limit):
        """[(alt, az, row)] for objects up to mag_limit above the horizon."""
        from astro.core import altaz, precess
        n = bisect.bisect_right(self.mags, mag_limit)
        out = []
        for row in self.rows[:n]:
            a, z = altaz(*precess(row["ra"], row["dec"], jd), jd, lat, lon)
            if a > 0:
                out.append((a, z, row))
        return out


EMPTY = DsoSet([])
_CACHE = {}


def load_set(name, directory=None, named=()):
    """Missing file -> EMPTY (not an error). Corrupt file -> ValueError."""
    if directory is None:
        from astro.constellations import data_dir
        directory = data_dir()
    path = os.path.join(directory, BINARY_DIR, name)
    if not os.path.exists(path):
        return EMPTY
    rows, _dropped = rows_from(DsoCatalogBinary(path))
    return DsoSet(rows, named)


def get_dsos(named=(), mag_limit=9.0):
    """Lazy, cached per file. -> (DsoSet, error text or ''). Never raises: the chart just shows no extra objects."""
    name = next((f for depth, f in FILES if mag_limit <= depth), FILES[-1][1])
    if name not in _CACHE:
        try:
            _CACHE[name] = (load_set(name, named=named), "")
        except (ValueError, OSError) as e:
            _CACHE[name] = (EMPTY, f"deep-sky data unusable ({name}): {e}")
    return _CACHE[name]
