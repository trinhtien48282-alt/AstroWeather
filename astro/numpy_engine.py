"""NumPy acceleration layer for the astronomy engine.

The same formulas as the scalar code in astro.core / astro.sun_moon / astro.planets, vectorised over arrays.
The scalar functions stay as the fallback (NumPy missing or switched off) and as the reference these vector
versions are tested against. NumPy is optional: without it this module still imports, HAVE_NUMPY is False and
the scan/event/star helpers use the pure-Python path.

Depends on astro.catalog, astro.core, astro.planets, astro.sun_moon (never on main, config or any GUI).
"""
import math

from astro.catalog import BRIGHT_STARS, CATALOG
from astro.core import AU_KM, altaz, jd_from_ts, precess
from astro.planets import PLANET_DIAM_KM, PLANET_ELEMENTS, find_events, planet_state
from astro.sun_moon import moon_altitude, sun_altitude

try:
    import numpy as np
except Exception:  # optional: the pure-Python engine keeps every original feature working
    np = None
HAVE_NUMPY = np is not None

PERF = {"numpy": True, "astropy": False}


def apply_perf(cfg):
    p = cfg.get("perf", {}) if isinstance(cfg, dict) else {}
    PERF["numpy"] = bool(p.get("numpy", True))
    PERF["astropy"] = bool(p.get("astropy", False))


def use_numpy():
    return HAVE_NUMPY and PERF["numpy"]


if HAVE_NUMPY:
    CAT_RA = np.array([o["ra"] * 15.0 for o in CATALOG])
    CAT_DEC = np.array([o["dec"] for o in CATALOG])
    STAR_RA = np.array([b[1] * 15.0 for b in BRIGHT_STARS])
    STAR_DEC = np.array([b[2] for b in BRIGHT_STARS])


def np_jd(ts):
    return np.asarray(ts, dtype=float) / 86400.0 + 2440587.5


def np_gmst(jd):
    d = jd - 2451545.0
    t = d / 36525.0
    return (280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - t ** 3 / 38710000.0) % 360.0


def np_altaz(ra, dec, jd, lat, lon):
    """Broadcasting RA/Dec -> Alt/Az, e.g. ra,dec shape (M,1) with jd shape (1,N) gives (M,N)."""
    h = np.radians((np_gmst(jd) + lon - ra) % 360.0)
    phi, d = math.radians(lat), np.radians(dec)
    sin_alt = math.sin(phi) * np.sin(d) + math.cos(phi) * np.cos(d) * np.cos(h)
    alt = np.arcsin(np.clip(sin_alt, -1.0, 1.0))
    az = np.arctan2(np.sin(h), np.cos(h) * math.sin(phi) - np.tan(d) * math.cos(phi)) + math.pi
    return np.degrees(alt), np.degrees(az) % 360.0


def np_precess(ra, dec, jd):
    t = (np.asarray(jd, dtype=float) - 2451545.0) / 36525.0
    zeta = np.radians((2306.2181 * t + 0.30188 * t * t + 0.017998 * t ** 3) / 3600.0)
    z = np.radians((2306.2181 * t + 1.09468 * t * t + 0.018203 * t ** 3) / 3600.0)
    theta = np.radians((2004.3109 * t - 0.42665 * t * t - 0.041833 * t ** 3) / 3600.0)
    a, d = np.radians(ra), np.radians(dec)
    A = np.cos(d) * np.sin(a + zeta)
    B = np.cos(theta) * np.cos(d) * np.cos(a + zeta) - np.sin(theta) * np.sin(d)
    C = np.sin(theta) * np.cos(d) * np.cos(a + zeta) + np.cos(theta) * np.sin(d)
    return np.degrees(np.arctan2(A, B) + z) % 360.0, np.degrees(np.arcsin(np.clip(C, -1.0, 1.0)))


def np_sep(ra1, dec1, ra2, dec2):
    d1, d2 = np.radians(dec1), np.radians(dec2)
    c = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(np.radians(ra1 - ra2))
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def np_sun(jd):
    n = jd - 2451545.0
    big_l = (280.460 + 0.9856474 * n) % 360.0
    g = np.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = np.radians((big_l + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) % 360.0)
    eps = np.radians(23.439 - 0.0000004 * n)
    return {"ra": np.degrees(np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))) % 360.0,
            "dec": np.degrees(np.arcsin(np.sin(eps) * np.sin(lam))), "lon": np.degrees(lam) % 360.0,
            "dist": 1.00014 - 0.01671 * np.cos(g) - 0.00014 * np.cos(2 * g)}


def np_moon(jd):
    t = (jd - 2451545.0) / 36525.0
    s = lambda a, b: np.sin(np.radians(a + b * t))
    c = lambda a, b: np.cos(np.radians(a + b * t))
    lon = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
           + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03))
    lat = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15)
           - 0.17 * s(217.6, -407332.21))
    par = (0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36)
           + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74))
    l, b = np.radians(lon), np.radians(lat)
    eps = np.radians(23.439291 - 0.0130042 * t)
    x = np.cos(b) * np.cos(l)
    y = np.cos(eps) * np.cos(b) * np.sin(l) - np.sin(eps) * np.sin(b)
    z = np.sin(eps) * np.cos(b) * np.sin(l) + np.cos(eps) * np.sin(b)
    return {"ra": np.degrees(np.arctan2(y, x)) % 360.0, "dec": np.degrees(np.arcsin(np.clip(z, -1.0, 1.0))),
            "lon": lon % 360.0, "lat": lat, "par": par, "dist": 6378.14 / np.sin(np.radians(par))}


def np_moon_state(jd, lat, lon):
    """-> (moon dict, illuminated fraction, topocentric altitude, azimuth) for an array of JDs."""
    m, s = np_moon(jd), np_sun(jd)
    psi = np.arccos(np.clip(np.cos(np.radians(m["lat"])) * np.cos(np.radians(m["lon"] - s["lon"])), -1.0, 1.0))
    rs = s["dist"] * AU_KM
    inc = np.arctan2(rs * np.sin(psi), m["dist"] - rs * np.cos(psi))
    alt, az = np_altaz(m["ra"], m["dec"], jd, lat, lon)
    return m, (1.0 + np.cos(inc)) / 2.0, alt - m["par"] * np.cos(np.radians(alt)), az


def _np_kepler(m_deg, e):
    m = np.radians(((m_deg + 180.0) % 360.0) - 180.0)
    big_e = m + e * np.sin(m) * (1.0 + e * np.cos(m))
    for _ in range(10):
        big_e = big_e - (big_e - e * np.sin(big_e) - m) / (1.0 - e * np.cos(big_e))
    return big_e


def _np_helio(name, t):
    (a0, a1), (e0, e1), (i0, i1), (l0, l1), (w0, w1), (o0, o1) = PLANET_ELEMENTS[name]
    a, e = a0 + a1 * t, e0 + e1 * t
    inc, big_l, w, om = np.radians(i0 + i1 * t), l0 + l1 * t, w0 + w1 * t, o0 + o1 * t
    arg = np.radians(w - om)
    big_e = _np_kepler(big_l - w, e)
    xp = a * (np.cos(big_e) - e)
    yp = a * np.sqrt(1.0 - e * e) * np.sin(big_e)
    om = np.radians(om)
    ca, sa, co, so, ci, si = np.cos(arg), np.sin(arg), np.cos(om), np.sin(om), np.cos(inc), np.sin(inc)
    return ((ca * co - sa * so * ci) * xp + (-sa * co - ca * so * ci) * yp,
            (ca * so + sa * co * ci) * xp + (-sa * so + ca * co * ci) * yp,
            (sa * si) * xp + (ca * si) * yp)


def np_planet(name, jd):
    jd = np.asarray(jd, dtype=float)
    t = (jd - 2451545.0) / 36525.0
    px, py, pz = _np_helio(name, t)
    ex, ey, ez = _np_helio("Earth", t)
    gx, gy, gz = px - ex, py - ey, pz - ez
    d = np.sqrt(gx * gx + gy * gy + gz * gz)
    r = np.sqrt(px * px + py * py + pz * pz)
    big_r = np.sqrt(ex * ex + ey * ey + ez * ez)
    eps = math.radians(23.43928)
    xe, ye, ze = gx, gy * math.cos(eps) - gz * math.sin(eps), gy * math.sin(eps) + gz * math.cos(eps)
    ra, dec = np_precess(np.degrees(np.arctan2(ye, xe)) % 360.0, np.degrees(np.arcsin(np.clip(ze / d, -1.0, 1.0))), jd)
    inc = np.degrees(np.arccos(np.clip((r * r + d * d - big_r * big_r) / (2 * r * d), -1.0, 1.0)))
    elong = np.degrees(np.arccos(np.clip((big_r * big_r + d * d - r * r) / (2 * big_r * d), -1.0, 1.0)))
    east = ((np.degrees(np.arctan2(gy, gx) - np.arctan2(-ey, -ex)) + 180.0) % 360.0) - 180.0 > 0
    lg = 5.0 * np.log10(r * d)
    if name == "Mercury":
        mag = -0.42 + lg + 0.0380 * inc - 0.000273 * inc ** 2 + 0.000002 * inc ** 3
    elif name == "Venus":
        mag = -4.40 + lg + 0.0009 * inc + 0.000239 * inc ** 2 - 0.00000065 * inc ** 3
    elif name == "Mars":
        mag = -1.52 + lg + 0.016 * inc
    elif name == "Jupiter":
        mag = -9.40 + lg + 0.005 * inc
    elif name == "Saturn":
        pr, pd = math.radians(40.589), math.radians(83.537)
        pole = (math.cos(pd) * math.cos(pr), math.cos(pd) * math.sin(pr), math.sin(pd))
        sin_b = pole[0] * (-xe / d) + pole[1] * (-ye / d) + pole[2] * (-ze / d)
        mag = -8.88 + lg - 2.60 * np.abs(sin_b) + 1.25 * sin_b ** 2
    elif name == "Uranus":
        mag = -7.19 + lg
    else:
        mag = -6.87 + lg
    return {"ra": ra, "dec": dec, "dist": d, "elong": elong, "east": east, "phase": (1.0 + np.cos(np.radians(inc))) / 2.0,
            "mag": mag, "diam": 206265.0 * PLANET_DIAM_KM[name] / (d * AU_KM)}


def np_crossings(ts, alt, h0):
    """Rise/set style crossings of a sampled altitude curve, linearly interpolated."""
    v = np.asarray(alt, dtype=float) - h0
    neg = v < 0
    out = []
    for i in np.nonzero(neg[1:] != neg[:-1])[0]:
        v0, v1 = v[i], v[i + 1]
        frac = v0 / (v0 - v1) if v0 != v1 else 0.0
        out.append(("rise" if v1 >= 0 else "set", float(ts[i] + frac * (ts[i + 1] - ts[i]))))
    return out


def sky_series(ts, lat, lon):
    jd = np_jd(ts)
    sun = np_sun(jd)
    _m, illum, m_alt, m_az = np_moon_state(jd, lat, lon)
    return {"sun_alt": np_altaz(sun["ra"], sun["dec"], jd, lat, lon)[0], "moon_alt": m_alt,
            "moon_az": m_az, "moon_illum": illum}


def body_events(body, t0, t1, step, h0, lat, lon):
    """Times the Sun or Moon altitude crosses h0 (NumPy grid when enabled, bisection otherwise)."""
    if use_numpy():
        ts = np.arange(t0, t1 + 120.0, 120.0)
        jd = np_jd(ts)
        if body == "sun":
            sun = np_sun(jd)
            alt = np_altaz(sun["ra"], sun["dec"], jd, lat, lon)[0]
        else:
            alt = np_moon_state(jd, lat, lon)[2]
        return np_crossings(ts, alt, h0)
    fn = (lambda t: sun_altitude(t, lat, lon)) if body == "sun" else (lambda t: moon_altitude(t, lat, lon))
    return find_events(fn, t0, t1, step, h0)


def scan_body(name, t0, t1, steps, lat, lon):
    """Best altitude and the times a planet/Moon is above 10 deg in a dark-enough sky."""
    if use_numpy():
        ts = np.linspace(t0, t1, steps + 1)
        jd = np_jd(ts)
        if name == "Moon":
            alt = np_moon_state(jd, lat, lon)[2]
        else:
            st = np_planet(name, jd)
            alt = np_altaz(st["ra"], st["dec"], jd, lat, lon)[0]
        sun = np_sun(jd)
        sun_alt = np_altaz(sun["ra"], sun["dec"], jd, lat, lon)[0]
        k = int(np.argmax(alt))
        return (float(alt[k]), float(ts[k])), [float(ts[i]) for i in np.nonzero((alt > 10) & (sun_alt < -3))[0]]
    best, vis = (-90.0, t0), []
    for k in range(steps + 1):
        ts = t0 + (t1 - t0) * k / steps
        jd = jd_from_ts(ts)
        if name == "Moon":
            alt = moon_altitude(ts, lat, lon)
        else:
            st = planet_state(name, jd)
            alt = altaz(st["ra"], st["dec"], jd, lat, lon)[0]
        if alt > best[0]:
            best = (alt, ts)
        if alt > 10 and sun_altitude(ts, lat, lon) < -3:
            vis.append(ts)
    return best, vis


def star_altaz(jd, lat, lon):
    if use_numpy():
        ra, dec = np_precess(STAR_RA, STAR_DEC, jd)
        alt, az = np_altaz(ra, dec, jd, lat, lon)
        return alt.tolist(), az.tolist()
    alts, azs = [], []
    for _name, ra_h, dec, _mag in BRIGHT_STARS:
        ra, d = precess(ra_h * 15.0, dec, jd)
        a, z = altaz(ra, d, jd, lat, lon)
        alts.append(a)
        azs.append(z)
    return alts, azs
