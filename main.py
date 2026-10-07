#THIS IS THE MAIN CODE CLAUDE!
"""
ASTROWEATHER - observing forecast + telescope toolkit

  pip install customtkinter
  python astro_weather.py

Pages
  Tonight    deep-sky and planetary scores, best window, insights, planets, targets
  Forecast   hour-by-hour heat map: light, moon, 3 cloud layers, rain, transparency,
             seeing, wind, gusts, humidity, dew margin, temperature, scores
  Planner    rank targets over a date/time range, with reasons, eyepiece advice and an altitude graph
  Sky        live alt-az sky chart with a time slider (sun, moon, planets, stars, deep sky)
  Telescope  specs, eyepiece table, magnification / field / arcs / resolution /
             drift-time calculators and a camera (imaging) calculator
  Settings   location search, units, light pollution (Bortle), your gear

Data: Open-Meteo (free, no API key) for weather + air quality. Sun, Moon, planets and
sky positions are computed locally (no internet needed for those).
Honest note: no free service gives a true "seeing" forecast, so Seeing and
Transparency here are scientifically-motivated proxies (jet-stream wind, ground wind,
thermal change, CAPE / aerosols, humidity, visibility). See Settings > How scores work.
"""
import copy
import json
import math
import os
import queue
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

import importlib.util
import warnings

from config import (APP_NAME, CACHE_PATH, CONFIG_DIR, CONFIG_PATH, DEFAULT_CONFIG, LOG_PATH,  # noqa: F401
                    load_config, log_error, save_config)
from mathutil import D2R, R2D, clamp, deg, mean, piecewise, rad  # noqa: F401
from astro.core import AU_KM, altaz, gmst_deg, jd_from_ts, precess  # noqa: F401
from astro.sun_moon import (moon_altitude, moon_info, moon_pos, next_phase_time, phase_name,  # noqa: F401
                            sun_altitude, sun_pos)
from astro.catalog import BRIGHT_STARS, CATALOG, KIND_NAMES, _o  # noqa: F401
from astro.planets import (PLANET_DIAM_KM, PLANET_ELEMENTS, PLANETS, _helio, _kepler,  # noqa: F401
                           find_events, planet_state)

try:
    import numpy as np
except Exception:  # optional: the pure-Python engine keeps every original feature working
    np = None
HAVE_NUMPY = np is not None
HAVE_ASTROPY = importlib.util.find_spec("astropy") is not None  # imported lazily, only if enabled

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

CARD = "#1b1b1b"
DEEP = "#0b1020"
ACCENT = "#1f6aa5"

BORTLE_NELM = {1: 7.6, 2: 7.1, 3: 6.6, 4: 6.2, 5: 5.6, 6: 5.1, 7: 4.6, 8: 4.3, 9: 4.0}

# ===========================================================================
# ASTRONOMY (pure python, no ephemeris download)
# ===========================================================================
PLANET_COLORS = {"Mercury": "#b8b0a0", "Venus": "#fff2c0", "Mars": "#ff8a5c", "Jupiter": "#f0d9a8",
                 "Saturn": "#e8d28a", "Uranus": "#9be8e8", "Neptune": "#7ea0ff"}


# ===========================================================================
# NUMPY ENGINE: the same formulas as the scalar code above, vectorised over arrays.
# The scalar functions stay as the fallback (NumPy missing or switched off) and as the
# reference these vector versions are tested against.
# ===========================================================================
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


def np_moon_drop(illum, alt, sep):
    a = np.degrees(np.arccos(np.clip(2.0 * illum - 1.0, -1.0, 1.0)))
    flux = 10.0 ** (-0.4 * (0.026 * a + 4e-9 * a ** 4))
    c2 = np.cos(np.radians(sep)) ** 2
    sepf = (10 ** 5.36 * (1.06 + c2) + 10 ** (6.15 - sep / 40.0)) / (10 ** 5.36 * 2.06 + 10 ** 6.15)
    r = MOON_K * flux * sepf * np.sin(np.radians(np.maximum(alt, 0.0))) ** 0.7
    return np.where(alt > 0, 1.4 * np.log10(1.0 + r), 0.0)


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


def catalog_altaz_sep(jd, lat, lon, mpos):
    """Alt, az and Moon separation for every catalog object at one instant."""
    if use_numpy():
        ra, dec = np_precess(CAT_RA, CAT_DEC, jd)
        alt, az = np_altaz(ra, dec, jd, lat, lon)
        return alt.tolist(), az.tolist(), np_sep(ra, dec, mpos["ra"], mpos["dec"]).tolist()
    alts, azs, seps = [], [], []
    for o in CATALOG:
        ra, dec = precess(o["ra"] * 15.0, o["dec"], jd)
        a, z = altaz(ra, dec, jd, lat, lon)
        alts.append(a)
        azs.append(z)
        seps.append(ang_sep(ra, dec, mpos["ra"], mpos["dec"]))
    return alts, azs, seps


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------
def score_color(s):
    s = clamp(s)
    stops = [(0, (176, 52, 52)), (35, (214, 120, 52)), (60, (214, 186, 62)), (100, (52, 160, 96))]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if s <= x1:
            t = (s - x0) / (x1 - x0)
            return "#%02x%02x%02x" % tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
    return "#34a060"


def text_on(hexcolor):
    r, g, b = int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)
    return "#101010" if (0.299 * r + 0.587 * g + 0.114 * b) > 135 else "#f4f4f4"


def verdict(score):
    if score is None:
        return "no data", "(・_・)"
    if score >= 80:
        return "Excellent", "(ﾉ◕ヮ◕)ﾉ"
    if score >= 65:
        return "Good", "(•‿•)"
    if score >= 45:
        return "Fair", "(・_・)"
    if score >= 25:
        return "Poor", "(´･_･`)"
    return "Stay in", "(╥﹏╥)"


def seeing_fwhm(score):
    return 0.8 + (100.0 - clamp(score)) / 100.0 * 3.2


def seeing_label(score):
    f = seeing_fwhm(score)
    if f < 1.2:
        return "excellent"
    if f < 1.8:
        return "good"
    if f < 2.6:
        return "average"
    if f < 3.4:
        return "poor"
    return "bad"


def score_transparency(rh, aod, pm25, vis_km):
    rh_pen = piecewise(rh, [(0, 0), (60, 0), (80, 15), (90, 32), (100, 50)]) if rh is not None else 10
    aod_pen = piecewise(aod, [(0, 0), (0.1, 0), (0.25, 20), (0.5, 45), (1.0, 70)]) if aod is not None else 0
    pm_pen = piecewise(pm25, [(0, 0), (12, 0), (35, 12), (75, 25), (150, 40)]) if pm25 is not None else 0
    vis_pen = piecewise(vis_km, [(0, 45), (2, 35), (5, 20), (10, 8), (20, 0)]) if vis_km is not None else 0
    return clamp(100 - max(aod_pen, pm_pen) - 0.8 * rh_pen - 0.5 * vis_pen)


def score_seeing(jet_ms, wind_kmh, gust_kmh, dtdt, cape):
    jet_pen = piecewise(jet_ms, [(0, 0), (15, 0), (25, 15), (35, 35), (50, 60), (70, 80)]) if jet_ms is not None else 12
    w = max(wind_kmh or 0, 0.6 * (gust_kmh or 0))
    wind_pen = piecewise(w, [(0, 0), (8, 0), (15, 8), (25, 20), (40, 40)])
    th_pen = piecewise(abs(dtdt or 0), [(0, 0), (0.5, 0), (1.5, 10), (3, 25)])
    cape_pen = piecewise(cape or 0, [(0, 0), (100, 5), (500, 20), (1500, 40)])
    return clamp(100 - jet_pen - wind_pen - th_pen - cape_pen)


def score_dew(spread):
    return piecewise(spread, [(0, 0), (1, 15), (2, 40), (3.5, 70), (6, 95), (10, 100)]) if spread is not None else 60


def score_wind(wind_kmh, gust_kmh):
    w = max(wind_kmh or 0, 0.7 * (gust_kmh or 0))
    return piecewise(w, [(0, 100), (8, 100), (15, 80), (25, 50), (40, 15), (60, 0)])


def sky_nelm(nelm, moon_alt, illum):
    return nelm - 2.0 * illum * max(0.0, math.sin(rad(moon_alt))) ** 0.7


# Moon interference. Brightness vs phase follows the Krisciunas & Schaefer shape (a quarter
# Moon is about 10x fainter than a full one, not 2x); scattering vs separation has the same
# shape (strong near the Moon, minimum near 90 degrees). MOON_K is calibrated so a full Moon
# 60 degrees from the target at high altitude costs about 2 magnitudes of sky limit.
MOON_K = 139.0


def moon_flux_rel(illum):
    a = deg(math.acos(clamp(2.0 * illum - 1.0, -1.0, 1.0)))  # phase angle, 0 = full
    return 10.0 ** (-0.4 * (0.026 * a + 4e-9 * a ** 4))


def moon_sepf(sep):
    c2 = math.cos(rad(sep)) ** 2
    f = 10 ** 5.36 * (1.06 + c2) + 10 ** (6.15 - sep / 40.0)
    return f / (10 ** 5.36 * 2.06 + 10 ** 6.15)


def moon_drop(illum, moon_alt, sep):
    """Magnitudes of sky limit lost to scattered Moonlight (0 when the Moon is down)."""
    if moon_alt <= 0:
        return 0.0
    r = MOON_K * moon_flux_rel(illum) * moon_sepf(sep) * math.sin(rad(moon_alt)) ** 0.7
    return 1.4 * math.log10(1.0 + r)


def moon_score_from_drop(d):
    return piecewise(d, [(0, 100), (0.3, 90), (1, 65), (2, 30), (3, 0)])


def ang_sep(ra1, dec1, ra2, dec2):
    """Great-circle separation in degrees (all inputs in degrees)."""
    d1, d2 = rad(dec1), rad(dec2)
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(rad(ra1 - ra2))
    return deg(math.acos(clamp(c, -1.0, 1.0)))


# ===========================================================================
# WEATHER DATA (Open-Meteo)
# ===========================================================================
API_FORECAST = "https://api.open-meteo.com/v1/forecast"
API_AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
API_GEO = "https://geocoding-api.open-meteo.com/v1/search"
BASE_VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "surface_pressure",
             "precipitation_probability", "precipitation", "cloud_cover", "cloud_cover_low",
             "cloud_cover_mid", "cloud_cover_high", "visibility", "wind_speed_10m", "wind_direction_10m",
             "wind_gusts_10m", "cape"]
UPPER_VARS = ["wind_speed_250hPa", "wind_speed_300hPa"]


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "AstroWeather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_weather(lat, lon):
    def url(vars_):
        q = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "hourly": ",".join(vars_),
             "timezone": "auto", "forecast_days": 5, "timeformat": "unixtime", "wind_speed_unit": "kmh"}
        return API_FORECAST + "?" + urllib.parse.urlencode(q, safe=",")

    try:
        wx = http_json(url(BASE_VARS + UPPER_VARS))
    except urllib.error.HTTPError:
        wx = http_json(url(BASE_VARS))  # upper-air winds not available: fall back
    aq = None
    try:
        q = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": "auto", "forecast_days": 5,
             "timeformat": "unixtime", "hourly": "pm10,pm2_5,aerosol_optical_depth,dust,us_aqi"}
        aq = http_json(API_AIR + "?" + urllib.parse.urlencode(q, safe=","))
    except Exception as e:
        log_error(f"air quality fetch failed: {e}")
    return wx, aq


def geocode(name):
    q = {"name": name, "count": 6, "language": "en", "format": "json"}
    data = http_json(API_GEO + "?" + urllib.parse.urlencode(q))
    out = []
    for r in data.get("results", []) or []:
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append({"name": label, "lat": r["latitude"], "lon": r["longitude"]})
    return out


# ===========================================================================
# ANALYSIS
# ===========================================================================
def build_hours(wx, aq, lat, lon):
    h = wx.get("hourly", {})
    times = h.get("time", [])
    n = len(times)

    def col(src, name):
        arr = src.get(name) if src else None
        return arr if isinstance(arr, list) and len(arr) == n else [None] * n

    aq_h = (aq or {}).get("hourly", {}) if aq else {}
    aq_index = {int(t): i for i, t in enumerate(aq_h.get("time", []))}

    def aq_val(name, ts):
        arr = aq_h.get(name)
        i = aq_index.get(ts)
        return arr[i] if arr and i is not None and i < len(arr) else None

    cols = {k: col(h, k) for k in BASE_VARS + UPPER_VARS}
    pre = None
    if use_numpy() and n:  # one vectorised pass instead of a Sun + Moon calculation per hour
        pre = sky_series(np.array([int(t) for t in times], dtype=float), lat, lon)
    hours, prev_temp = [], None
    for i in range(n):
        ts = int(times[i])
        t, cloud = cols["temperature_2m"][i], cols["cloud_cover"][i]
        if t is None or cloud is None:
            continue
        rh, dew = cols["relative_humidity_2m"][i], cols["dew_point_2m"][i]
        wind, gust = cols["wind_speed_10m"][i] or 0.0, cols["wind_gusts_10m"][i] or 0.0
        vis = cols["visibility"][i]
        vis_km = vis / 1000.0 if vis is not None else None
        jets = [cols[k][i] for k in UPPER_VARS if cols[k][i] is not None]
        jet_ms = max(jets) / 3.6 if jets else None
        aod, pm25 = aq_val("aerosol_optical_depth", ts), aq_val("pm2_5", ts)
        spread = (t - dew) if dew is not None else None
        dtdt = (t - prev_temp) if prev_temp is not None else 0.0
        prev_temp = t
        jd = jd_from_ts(ts)
        if pre is not None:
            s_alt = float(pre["sun_alt"][i])
            mi = {"illum": float(pre["moon_illum"][i]), "alt": float(pre["moon_alt"][i])}
        else:
            s_alt = sun_altitude(ts, lat, lon)
            mi = moon_info(ts, lat, lon)
        pp = cols["precipitation_probability"][i] or 0.0
        precip = cols["precipitation"][i] or 0.0

        sc_trans = score_transparency(rh, aod, pm25, vis_km)
        sc_seeing = score_seeing(jet_ms, wind, gust, dtdt, cols["cape"][i])
        sc_dew, sc_wind = score_dew(spread), score_wind(wind, gust)
        sc_moon = moon_score_from_drop(moon_drop(mi["illum"], mi["alt"], 60.0))  # typical 60 deg separation
        gate = (1.0 - clamp(cloud, 0, 100) / 100.0) ** 1.2
        gate *= 1.0 - 0.8 * clamp(pp / 70.0, 0.0, 1.0)
        if precip > 0.1:
            gate *= 0.2
        dso = (0.32 * sc_trans + 0.30 * sc_moon + 0.14 * sc_wind + 0.12 * sc_dew + 0.12 * sc_seeing) * gate
        planet = (0.45 * sc_seeing + 0.20 * sc_trans + 0.15 * sc_wind + 0.10 * sc_dew + 10.0) * gate
        hours.append({
            "ts": ts, "temp": t, "rh": rh, "dew": dew, "spread": spread, "press": cols["surface_pressure"][i],
            "pp": pp, "precip": precip, "cloud": cloud, "low": cols["cloud_cover_low"][i],
            "mid": cols["cloud_cover_mid"][i], "high": cols["cloud_cover_high"][i], "vis_km": vis_km,
            "wind": wind, "gust": gust, "wdir": cols["wind_direction_10m"][i], "cape": cols["cape"][i],
            "jet": jet_ms, "aod": aod, "pm25": pm25, "dtdt": dtdt,
            "sun_alt": s_alt, "moon_alt": mi["alt"], "moon_illum": mi["illum"],
            "dark": 0 if s_alt > -0.833 else 1 if s_alt > -6 else 2 if s_alt > -12 else 3 if s_alt > -18 else 4,
            "sc_trans": sc_trans, "sc_seeing": sc_seeing, "sc_dew": sc_dew, "sc_wind": sc_wind,
            "sc_moon": sc_moon, "dso": dso, "planet": planet, "gate": gate,
        })
    return hours


def tonight_window(lat, lon, now_ts):
    events = body_events("sun", now_ts - 18 * 3600, now_ts + 36 * 3600, 600, -0.833, lat, lon)
    if sun_altitude(now_ts, lat, lon) < -0.833:
        sets = [t for k, t in events if k == "set" and t <= now_ts]
        rises = [t for k, t in events if k == "rise" and t >= now_ts]
        start = sets[-1] if sets else now_ts - 6 * 3600
        end = rises[0] if rises else now_ts + 6 * 3600
    else:
        sets = [t for k, t in events if k == "set" and t >= now_ts]
        if not sets:
            return {"start": now_ts, "end": now_ts + 12 * 3600, "dusk": None, "dawn": None, "polar": True}
        start = sets[0]
        rises = [t for k, t in events if k == "rise" and t >= start]
        end = rises[0] if rises else start + 12 * 3600
    tw = body_events("sun", start - 600, end + 600, 600, -18.0, lat, lon)
    dusk = next((t for k, t in tw if k == "set"), None)
    dawn = next((t for k, t in reversed(tw) if k == "rise"), None)
    return {"start": start, "end": end, "dusk": dusk, "dawn": dawn, "polar": False}


def planet_rows(lat, lon, win):
    rows = []
    t0, t1 = win["start"], win["end"]
    steps = max(2, int((t1 - t0) // 1200))
    for name in PLANETS + ["Moon"]:
        best, vis = scan_body(name, t0, t1, steps, lat, lon)
        jd = jd_from_ts(win["start"])
        if name == "Moon":
            mi = moon_info(win["start"], lat, lon)
            pa = deg(math.acos(clamp(2.0 * mi["illum"] - 1.0, -1.0, 1.0)))  # phase angle, 0 = full
            rows.append({"name": name, "mag": -12.74 + 0.026 * pa + 4e-9 * pa ** 4, "diam": mi["ang_diam"],
                         "phase": mi["illum"], "elong": None, "best_alt": best[0], "best_ts": best[1],
                         "vis": (vis[0], vis[-1]) if vis else None})
        else:
            st = planet_state(name, jd)
            rows.append({"name": name, "mag": st["mag"], "diam": st["diam"], "phase": st["phase"],
                         "elong": st["elong"] * (1 if st["east"] else -1), "best_alt": best[0], "best_ts": best[1],
                         "vis": (vis[0], vis[-1]) if vis else None})
    return rows


def build_combos(scope, eyepieces, barlows):
    ap, fl = float(scope["aperture"]), float(scope["focal_length"])
    options = [("", 1.0)] + [(b["name"], float(b["factor"])) for b in barlows]
    combos = []
    for ep in eyepieces:
        for bname, bf in options:
            mag = fl * bf / float(ep["fl"])
            combos.append({"label": ep["name"] + (f" + {bname}" if bname else ""), "mag": mag,
                           "pupil": ap / mag, "tfov": float(ep["afov"]) / mag, "barlow": bf})
    combos.sort(key=lambda c: c["mag"])
    return combos


def quality_note(mag, pupil, ap):
    if pupil > 7.0:
        return "pupil > 7 mm (light wasted)"
    if pupil > 4.5:
        return "widest field / big targets"
    if pupil > 2.0:
        return "general viewing"
    if pupil > 1.0:
        return "high power: Moon, planets"
    if mag <= 2.0 * ap:
        return "very high: needs steady air"
    return "beyond useful magnification"


def suggest_combo(obj, combos, ap, cap):
    usable = [c for c in combos if c["mag"] <= cap and c["pupil"] <= 7.5] or combos[:1]
    if not usable:
        return None
    if obj["kind"] == "DS":
        need = 120.0 / max(obj["sep"], 0.5)
        ok = [c for c in usable if c["mag"] >= need]
        return min(ok, key=lambda c: c["mag"]) if ok else max(usable, key=lambda c: c["mag"])
    size = obj["size"]
    if size >= 15:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 1.1]
        return max(fit, key=lambda c: c["mag"]) if fit else min(usable, key=lambda c: c["mag"])
    if size >= 3:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 2.0]
        return max(fit, key=lambda c: c["mag"]) if fit else min(usable, key=lambda c: c["mag"])
    pool = [c for c in usable if c["mag"] <= min(cap, ap * 1.6)] or usable
    return max(pool, key=lambda c: c["mag"])


def rank_targets(ts, lat, lon, ap_eff, nelm, combos, cap):
    jd = jd_from_ts(ts)
    mi = moon_info(ts, lat, lon)
    lim_dark = nelm + 5.0 * math.log10(ap_eff / 7.0)
    dawes = 116.0 / (ap_eff if ap_eff > 0 else 76.0)
    alts, azs, seps = catalog_altaz_sep(jd, lat, lon, moon_pos(jd))
    rows = []
    for i, o in enumerate(CATALOG):
        alt, az, sep = alts[i], azs[i], seps[i]
        drop = moon_drop(mi["illum"], mi["alt"], sep)  # depends on Moon phase, height AND distance from the target
        lim = lim_dark - drop
        if o["kind"] == "DS":
            margin = lim - o["mag"]
            if o["sep"] < dawes * 0.9:
                margin = -1.0
            elif o["sep"] < dawes * 1.5:
                margin = min(margin, 1.0)
        else:
            margin = lim - (o["mag"] + 2.2 * math.log10(max(1.0, o["size"])))
        rating = "Easy" if margin >= 3 else "Moderate" if margin >= 1.2 else "Hard" if margin >= 0 else "Beyond"
        combo = suggest_combo(o, combos, ap_eff, cap) if combos else None
        rows.append({"obj": o, "alt": alt, "az": az, "margin": margin, "rating": rating, "combo": combo,
                     "lim": lim, "lim_dark": lim_dark, "sep": sep, "drop": drop})
    return rows


def pick_window(hours, now_ts, length=2):
    ok = [h for h in hours if h["sun_alt"] < -12 and h["ts"] + 3600 > now_ts]
    best = None
    for i in range(len(ok) - length + 1):
        chunk = ok[i:i + length]
        if chunk[-1]["ts"] - chunk[0]["ts"] != (length - 1) * 3600:
            continue
        avg = sum(c["dso"] for c in chunk) / length
        if best is None or avg > best[0]:
            best = (avg, chunk[0]["ts"], chunk[-1]["ts"] + 3600)
    return best


def analyze(wx, aq, cfg, now_ts):
    lat, lon = float(cfg["location"]["lat"]), float(cfg["location"]["lon"])
    nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
    off = int(wx.get("utc_offset_seconds", 0) or 0)
    hours = build_hours(wx, aq, lat, lon)
    if not hours:
        raise ValueError("The weather service returned no usable hourly data.")
    win = tonight_window(lat, lon, now_ts)
    in_night = [h for h in hours if win["start"] - 1800 <= h["ts"] < win["end"]]
    dark = [h for h in in_night if h["sun_alt"] < -12]
    twil = [h for h in in_night if h["sun_alt"] < -6]
    sc = cfg["scope"]
    ap, fl = float(sc["aperture"]), float(sc["focal_length"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])

    tn = {"win": win, "dark": dark, "hours": in_night,
          "dso": mean([h["dso"] for h in dark]), "planet": mean([h["planet"] for h in twil]),
          "cloud": mean([h["cloud"] for h in dark]), "trans": mean([h["sc_trans"] for h in dark]),
          "seeing": mean([h["sc_seeing"] for h in dark]), "wind": mean([h["wind"] for h in dark]),
          "gust": max([h["gust"] for h in dark], default=None),
          "spread": min([h["spread"] for h in dark if h["spread"] is not None], default=None),
          "tmin": min([h["temp"] for h in dark], default=None), "tmax": max([h["temp"] for h in dark], default=None),
          "pp": max([h["pp"] for h in dark], default=None), "jet": mean([h["jet"] for h in dark]),
          "rh": mean([h["rh"] for h in dark]), "aod": mean([h["aod"] for h in dark])}
    tn["fwhm"] = seeing_fwhm(tn["seeing"]) if tn["seeing"] is not None else None
    tn["best"] = pick_window(hours, now_ts)
    tn["cap"] = min(2.0 * ap_eff, 200.0 / tn["fwhm"]) if tn["fwhm"] else 2.0 * ap_eff

    # Moon
    mnow = moon_info(now_ts, lat, lon)
    mid = (win["start"] + win["end"]) / 2
    mmid = moon_info(mid, lat, lon)
    mev = body_events("moon", win["start"] - 6 * 3600, win["end"] + 6 * 3600, 600, -0.83, lat, lon)
    moon = {"now": mnow, "mid": mmid, "events": mev,
            "next_new": next_phase_time(now_ts, 0.0), "next_full": next_phase_time(now_ts, 180.0),
            "moonfree": [h for h in dark if h["moon_alt"] < -0.5]}

    eval_ts = (tn["best"][1] + 1800) if tn["best"] else (dark[len(dark) // 2]["ts"] if dark else now_ts)
    targets = rank_targets(eval_ts, lat, lon, ap_eff, nelm, combos, tn["cap"])
    planets = planet_rows(lat, lon, win)
    insights = build_insights(tn, moon, cfg, combos, off, ap_eff)
    return {"hours": hours, "offset": off, "now": now_ts, "tonight": tn, "moon": moon, "planets": planets,
            "targets": targets, "eval_ts": eval_ts, "insights": insights, "combos": combos,
            "elevation": wx.get("elevation"), "has_jet": any(h["jet"] is not None for h in hours),
            "has_aq": any(h["aod"] is not None for h in hours), "fetched": time.time()}


def fmt_clock(ts, off):
    return datetime.fromtimestamp(ts, timezone(timedelta(seconds=off))).strftime("%H:%M")


def build_insights(tn, moon, cfg, combos, off, ap_eff):
    ins = []
    dark = tn["dark"]
    if not dark:
        return [("bad", "No real darkness tonight at this location (sun stays above -12 degrees).")]
    cl = tn["cloud"]
    if cl < 15:
        ins.append(("good", f"Mostly clear: {cl:.0f}% average cloud during the dark hours."))
    elif cl < 40:
        ins.append(("info", f"Patchy cloud: {cl:.0f}% on average. Watch for gaps and stay flexible."))
    else:
        ins.append(("bad", f"Cloudy: {cl:.0f}% average cover during the dark hours."))
    cloudy = [h for h in dark if h["cloud"] > 60]
    clear = [h for h in dark if h["cloud"] < 25]
    if cloudy and clear and cloudy[0]["ts"] < clear[-1]["ts"]:
        later = [h for h in clear if h["ts"] > cloudy[0]["ts"]]
        if later:
            ins.append(("info", f"Clouds thin out around {fmt_clock(later[0]['ts'], off)}: a later session may beat the early evening."))
    if dark and max(h["high"] or 0 for h in dark) > 50 and cl < 40:
        ins.append(("info", "Thin high cloud (cirrus) is around: stars look dimmer and the Moon gets halos."))
    if tn["pp"] is not None and tn["pp"] >= 30:
        ins.append(("bad", f"Rain chance up to {tn['pp']:.0f}%: keep the scope under cover."))
    tr = tn["trans"]
    note = ""
    if tn["aod"] is not None:
        note = f" (aerosol optical depth about {tn['aod']:.2f})"
    ins.append(("good" if tr >= 70 else "info" if tr >= 45 else "bad",
                f"Transparency {tr:.0f}/100{note}. " + ("Faint nebulae and galaxies should pop." if tr >= 70 else
                                                       "Haze will wash out faint objects; favour bright targets." if tr < 45 else
                                                       "Decent, but not perfect for faint fuzzies.")))
    se = tn["seeing"]
    jet = f", jet stream about {tn['jet']:.0f} m/s" if tn["jet"] is not None else ""
    ins.append(("good" if se >= 70 else "info" if se >= 45 else "warn",
                f"Seeing estimate {seeing_label(se)} (about {tn['fwhm']:.1f} arcsec){jet}."))
    cap = tn["cap"]
    useful = [c for c in combos if c["mag"] <= cap]
    if useful:
        top = max(useful, key=lambda c: c["mag"])
        ins.append(("info", f"Tonight's air supports about {cap:.0f}x. Your best high-power combo: {top['label']} ({top['mag']:.0f}x)."))
    if tn["gust"] is not None and tn["gust"] >= 25:
        ins.append(("warn", f"Gusts to {tn['gust']:.0f} km/h: a light {cfg['scope'].get('mount', 'AZ')} mount will shake. "
                            "Use low power or find a windbreak."))
    elif tn["wind"] is not None and tn["wind"] < 12:
        ins.append(("good", "Calm wind: steady views and an easy time with a lightweight tripod."))
    sp = tn["spread"]
    if sp is not None:
        if sp < 1.5:
            ins.append(("warn", f"Dew will form (temperature only {sp:.1f} degrees above dew point). Bring a dew shield or keep the mirror capped between uses."))
        elif sp < 3:
            ins.append(("info", f"Dew risk moderate (spread {sp:.1f} degrees)."))
    m = moon["mid"]
    free = len(moon["moonfree"])
    if m["illum"] < 0.15:
        ins.append(("good", f"Moon is {m['name'].lower()} ({m['illum'] * 100:.0f}% lit): dark skies for faint objects."))
    else:
        txt = f"Moon {m['name'].lower()}, {m['illum'] * 100:.0f}% lit at midnight. "
        txt += f"{free} Moon-free dark hour(s) tonight." if free else "It is up all night: stick to bright targets, the Moon and planets."
        ins.append(("warn" if m["illum"] > 0.6 and not free else "info", txt))
    return ins


# ===========================================================================
# OBSERVING PLANNER (engine): pure functions, no GUI calls, safe for a worker thread
# ===========================================================================
DEEP_KINDS = ("GC", "OC", "EN", "PN", "GX", "SNR", "SC")
PLAN_KINDS = {"All targets": None, "Deep-sky": DEEP_KINDS, "Planets & Moon": ("PL", "MOON"), "Double stars": ("DS",)}
# weights: altitude, detectability, conditions (weather), Moon interference
PLAN_WEIGHTS = {"DSO": (0.25, 0.30, 0.20, 0.25), "PL": (0.25, 0.30, 0.35, 0.10),
                "DS": (0.25, 0.25, 0.35, 0.15), "MOON": (0.30, 0.30, 0.40, 0.0)}
PLANET_NOTES = {
    "Mercury": "a tiny phase disc, low in twilight where the air is unsteady",
    "Venus": "a brilliant phase disc (crescent when close to us), no surface detail",
    "Mars": "an orange disc; dark markings and the polar cap show only when it is above ~10 arcsec",
    "Jupiter": "cloud belts and the four Galilean moons, even in a small scope",
    "Saturn": "the rings and Titan; the Cassini division needs steady air and about 100x",
    "Uranus": "a tiny blue-green disc; use a chart to confirm it",
    "Neptune": "a faint blue dot; needs a chart and a dark sky",
}


def plan_group(kind):
    return kind if kind in ("DS", "PL", "MOON") else "DSO"


def plan_targets():
    t = [dict(o) for o in CATALOG]
    for pn in PLANETS:
        t.append({"id": pn, "name": "", "kind": "PL", "ra": None, "dec": None, "mag": 0.0, "size": 0.0, "sep": None})
    t.append({"id": "Moon", "name": "", "kind": "MOON", "ra": None, "dec": None, "mag": -12.0, "size": 31.0, "sep": None})
    return t


def plan_info(t_mid, lat, lon):
    """Magnitude / disc size / phase of the planets and Moon in the middle of the range."""
    jd = jd_from_ts(t_mid)
    info = {}
    for pn in PLANETS:
        st = planet_state(pn, jd)
        info[pn] = {"mag": st["mag"], "diam": st["diam"], "phase": st["phase"], "elong": st["elong"] * (1 if st["east"] else -1)}
    mi = moon_info(t_mid, lat, lon)
    pa = deg(math.acos(clamp(2.0 * mi["illum"] - 1.0, -1.0, 1.0)))
    info["Moon"] = {"mag": -12.74 + 0.026 * pa + 4e-9 * pa ** 4, "diam": mi["ang_diam"], "phase": mi["illum"], "elong": None}
    return info


def _pack(ts, sun_alt, m_alt, illum, A, Z, S, info, engine):
    return {"ts": ts, "sun_alt": sun_alt, "moon_alt": m_alt, "moon_illum": illum, "alt": np.vstack(A),
            "az": np.vstack(Z), "sep": np.vstack(S), "info": info, "engine": engine}


def positions_numpy(ts, lat, lon):
    n = len(ts)
    jd = np_jd(ts)
    sun = np_sun(jd)
    sun_alt = np_altaz(sun["ra"], sun["dec"], jd, lat, lon)[0]
    m, illum, m_alt, m_az = np_moon_state(jd, lat, lon)
    ra, dec = np_precess(CAT_RA, CAT_DEC, float(jd[n // 2]))  # precession is constant over a few days
    alt, az = np_altaz(ra[:, None], dec[:, None], jd[None, :], lat, lon)
    A, Z = [alt], [az]
    S = [np_sep(ra[:, None], dec[:, None], m["ra"][None, :], m["dec"][None, :])]
    for pn in PLANETS:
        st = np_planet(pn, jd)
        a, z = np_altaz(st["ra"], st["dec"], jd, lat, lon)
        A.append(a[None, :])
        Z.append(z[None, :])
        S.append(np_sep(st["ra"], st["dec"], m["ra"], m["dec"])[None, :])
    A.append(m_alt[None, :])
    Z.append(m_az[None, :])
    S.append(np.full((1, n), 180.0))
    return _pack(ts, sun_alt, m_alt, illum, A, Z, S, plan_info(float(ts[n // 2]), lat, lon), "NumPy")


def positions_scalar(ts, lat, lon):
    """Same output as positions_numpy, computed one value at a time (the 'acceleration off' path)."""
    n = len(ts)
    tsl = [float(t) for t in ts]
    jd_mid = jd_from_ts(tsl[n // 2])
    cat = [precess(o["ra"] * 15.0, o["dec"], jd_mid) for o in CATALOG]
    m_cnt = len(CATALOG)
    total = m_cnt + len(PLANETS) + 1
    alt, az, sep = np.zeros((total, n)), np.zeros((total, n)), np.full((total, n), 180.0)
    sun_alt, m_alt, illum = np.zeros(n), np.zeros(n), np.zeros(n)
    for k, t in enumerate(tsl):
        jd = jd_from_ts(t)
        sun_alt[k] = sun_altitude(t, lat, lon)
        mp, mi = moon_pos(jd), moon_info(t, lat, lon)
        m_alt[k], illum[k] = mi["alt"], mi["illum"]
        for i, (ra, dec) in enumerate(cat):
            alt[i, k], az[i, k] = altaz(ra, dec, jd, lat, lon)
            sep[i, k] = ang_sep(ra, dec, mp["ra"], mp["dec"])
        for j, pn in enumerate(PLANETS):
            st = planet_state(pn, jd)
            alt[m_cnt + j, k], az[m_cnt + j, k] = altaz(st["ra"], st["dec"], jd, lat, lon)
            sep[m_cnt + j, k] = ang_sep(st["ra"], st["dec"], mp["ra"], mp["dec"])
        alt[-1, k], az[-1, k] = mi["alt"], mi["az"]
    return {"ts": ts, "sun_alt": sun_alt, "moon_alt": m_alt, "moon_illum": illum, "alt": alt, "az": az, "sep": sep,
            "info": plan_info(tsl[n // 2], lat, lon), "engine": "pure Python"}


_AP = None


def _astropy():
    """Lazy, defensive Astropy import (never blocks on the network)."""
    global _AP
    if _AP is not None:
        return _AP or None
    try:
        import astropy.units as u
        from astropy.time import Time
        from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body
        from astropy.utils import iers
        iers.conf.auto_download = False  # use the bundled tables; out-of-range dates degrade gracefully
        iers.conf.auto_max_age = None
        _AP = {"u": u, "Time": Time, "EarthLocation": EarthLocation, "AltAz": AltAz, "SkyCoord": SkyCoord, "get_body": get_body}
    except Exception as e:
        log_error(f"astropy import failed: {e}")
        _AP = False
    return _AP or None


def positions_astropy(ts, lat, lon, elev=0.0, pressure=0.0):
    """High-precision positions: built-in ephemeris + full ICRS->AltAz (nutation, aberration, refraction)."""
    ap = _astropy()
    if not ap:
        raise RuntimeError("Astropy is not installed")
    u, n = ap["u"], len(ts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = ap["Time"](np.asarray(ts, dtype=float), format="unix")
        loc = ap["EarthLocation"](lat=lat * u.deg, lon=lon * u.deg, height=elev * u.m)
        press = max(0.0, float(pressure)) * u.hPa
        frame = ap["AltAz"](obstime=t, location=loc, pressure=press)

        def body(name):
            c = ap["get_body"](name, t, loc)
            aa = c.transform_to(frame)
            return (np.asarray(aa.alt.deg, float), np.asarray(aa.az.deg, float),
                    np.asarray(c.ra.deg, float), np.asarray(c.dec.deg, float))
        sun_alt = body("sun")[0]
        m_alt, m_az, m_ra, m_dec = body("moon")
        _m, illum, _a, _z = np_moon_state(np_jd(ts), lat, lon)  # phase geometry needs no Astropy
        cat = ap["SkyCoord"](ra=CAT_RA[:, None] * u.deg, dec=CAT_DEC[:, None] * u.deg, frame="icrs")
        caa = cat.transform_to(ap["AltAz"](obstime=t.reshape(1, n), location=loc, pressure=press))
        A, Z = [np.asarray(caa.alt.deg, float)], [np.asarray(caa.az.deg, float)]
        S = [np_sep(CAT_RA[:, None], CAT_DEC[:, None], m_ra[None, :], m_dec[None, :])]
        for pn in PLANETS:
            a, z, r, d = body(pn.lower())
            A.append(a[None, :])
            Z.append(z[None, :])
            S.append(np_sep(r, d, m_ra, m_dec)[None, :])
        A.append(m_alt[None, :])
        Z.append(m_az[None, :])
        S.append(np.full((1, n), 180.0))
    ref = sky_series(np.asarray(ts[:3], dtype=float), lat, lon)  # refuse to return nonsense
    if (np.max(np.abs(ref["sun_alt"] - sun_alt[:3])) > 2.0 or np.max(np.abs(ref["moon_alt"] - m_alt[:3])) > 2.0
            or np.asarray(A[0]).shape != (len(CATALOG), n)):
        raise RuntimeError("Astropy output disagrees with the built-in engine")
    return _pack(ts, sun_alt, m_alt, illum, A, Z, S, plan_info(float(ts[n // 2]), lat, lon), "Astropy")


def compute_positions(ts, lat, lon, elev=0.0, pressure=1013.0):
    """Pick the engine: Astropy (if enabled and working) > NumPy > pure Python. Returns (positions, name, note)."""
    note = ""
    if PERF["astropy"]:
        try:
            return positions_astropy(ts, lat, lon, elev, pressure), "Astropy", ""
        except Exception as e:
            log_error(f"astropy positions failed: {traceback.format_exc()}")
            note = f"Astropy unavailable ({type(e).__name__}: {str(e)[:70]}), used the built-in engine instead"
    if use_numpy():
        return positions_numpy(ts, lat, lon), "NumPy", note
    return positions_scalar(ts, lat, lon), "pure Python", note


def airmass(alt):
    h = max(alt, 1.0)
    return 1.0 / math.sin(rad(h + 244.0 / (165.0 + 47.0 * h ** 1.1)))


def recommend_view(obj, combos, ap, cap, drop=0.0):
    """Choose an eyepiece / Barlow combination for this target under tonight's conditions."""
    if not combos:
        return None, ""
    usable = [c for c in combos if c["mag"] <= cap and c["pupil"] <= 7.5] or combos[:1]
    by_mag = lambda c: c["mag"]
    kind = obj["kind"]
    if kind == "MOON":
        whole = [c for c in usable if c["tfov"] >= 0.56]
        pick = max(whole, key=by_mag) if whole else min(usable, key=by_mag)
        higher = [c for c in usable if c["mag"] > pick["mag"]]
        why = f"the whole disc fits at {pick['mag']:.0f}x ({pick['tfov']:.2f} deg field)"
        if higher:
            why += f"; step up to {max(higher, key=by_mag)['label']} for crater detail when the air is steady"
        return pick, why
    if kind == "PL":
        pick = max(usable, key=by_mag)
        return pick, f"planets reward the highest power the air allows (about {cap:.0f}x tonight); the disc is only {obj.get('diam', 0):.0f} arcsec"
    if kind == "DS":
        need = 120.0 / max(obj["sep"], 0.5)
        ok = [c for c in usable if c["mag"] >= need]
        if ok:
            return min(ok, key=by_mag), f"a {obj['sep']:.1f}\" pair wants {need:.0f}x or more; this is the lowest power that gets there"
        return max(usable, key=by_mag), f"a {obj['sep']:.1f}\" pair wants {need:.0f}x but tonight's air allows about {cap:.0f}x, so it may look blended"
    size = obj["size"]
    if size >= 15:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 1.1]
        if fit:
            pick = max(fit, key=by_mag)
            return pick, f"{size:.0f}' wide: the most magnification that still frames it ({pick['tfov'] * 60:.0f}' field)"
        pick = min(usable, key=by_mag)
        return pick, f"{size:.0f}' wide is bigger than any of your fields; use the widest ({pick['tfov'] * 60:.0f}') and sweep across it"
    fit = [c for c in usable if c["tfov"] * 60.0 >= size * (2.0 if size >= 3 else 0.0)]
    pool = fit if size >= 3 else [c for c in usable if c["mag"] <= min(cap, ap * 1.6)] or usable
    pick = max(pool or usable, key=by_mag)
    why = (f"{size:.0f}' target: about half the field at {pick['mag']:.0f}x" if size >= 3
           else f"small target ({size * 60:.0f}\"): high power, limited by the air to about {cap:.0f}x")
    if drop > 1.0 and size < 15:
        higher = [c for c in usable if c["mag"] > pick["mag"] and c["tfov"] * 60.0 >= size * 1.3]
        if higher:
            pick = min(higher, key=by_mag)
            why += f"; stepped up to {pick['mag']:.0f}x because Moon glare ({drop:.1f} mag) is brightening the background"
    return pick, why


def run_planner(t0, t1, hours, cfg, off, min_alt=30.0, step_s=600.0, elev=0.0, kind_filter=None):
    """Rank every target over [t0, t1]. Vectorised over targets x time samples."""
    if not HAVE_NUMPY:
        raise RuntimeError("The planner needs NumPy: pip install numpy")
    tc = time.perf_counter()
    lat, lon = float(cfg["location"]["lat"]), float(cfg["location"]["lon"])
    nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
    sc = cfg["scope"]
    ap = float(sc["aperture"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])
    t0, t1 = max(t0, hours[0]["ts"]), min(t1, hours[-1]["ts"] + 3599)
    if t1 - t0 < 1800:
        raise ValueError("Pick a range of at least 30 minutes inside the forecast window.")
    step_s = max(step_s, (t1 - t0) / 2500.0)
    ts = np.arange(t0, t1, step_s, dtype=float)
    pressure = mean([h["press"] for h in hours if h.get("press")]) or 1013.0
    tp = time.perf_counter()
    pos, engine, note = compute_positions(ts, lat, lon, elev, pressure)
    t_pos = time.perf_counter() - tp

    hts = np.array([h["ts"] for h in hours], dtype=float)

    def wx(key, default=0.0):
        return np.interp(ts, hts, np.array([default if h.get(key) is None else h[key] for h in hours], dtype=float))
    cloud, trans, seeing, gate = wx("cloud"), wx("sc_trans"), wx("sc_seeing"), wx("gate", 1.0)
    side = 0.6 * wx("sc_wind", 100.0) + 0.4 * wx("sc_dew", 60.0)

    targets = plan_targets()
    n_t, n_cat = len(targets), len(CATALOG)
    for name, inf in pos["info"].items():
        for o in targets:
            if o["id"] == name and o["kind"] in ("PL", "MOON"):
                o.update(mag=inf["mag"], diam=inf["diam"], size=inf["diam"] / 60.0, phase=inf["phase"], elong=inf["elong"])
    group = [plan_group(o["kind"]) for o in targets]
    w = np.array([PLAN_WEIGHTS[g] for g in group])
    is_deep = np.array([g == "DSO" for g in group])
    is_pl = np.array([g == "PL" for g in group])
    is_moon = np.array([g == "MOON" for g in group])
    dawes = 116.0 / ap_eff
    eff, det_cap, interest = np.zeros(n_t), np.full(n_t, 100.0), np.zeros(n_t)
    for i, o in enumerate(targets):
        if o["kind"] == "DS":
            eff[i] = o["mag"]
            det_cap[i] = 0.0 if o["sep"] < dawes * 0.9 else 55.0 if o["sep"] < dawes * 1.5 else 100.0
        elif group[i] in ("PL", "MOON"):
            eff[i] = o["mag"]
            interest[i] = float(np.interp(o["diam"], [2, 5, 10, 20, 40], [10, 35, 60, 85, 100]))
        else:
            eff[i] = o["mag"] + 2.2 * math.log10(max(1.0, o["size"]))

    alt = pos["alt"]
    sun = pos["sun_alt"][None, :]
    obs_sun = np.where(is_deep[:, None], sun < -12.0, sun < -6.0)  # faint objects need a properly dark sky
    mask = obs_sun & (alt >= min_alt)
    drop = np_moon_drop(pos["moon_illum"][None, :], pos["moon_alt"][None, :], pos["sep"])
    drop[is_moon, :] = 0.0
    lim = nelm + 5.0 * math.log10(ap_eff / 7.0) - drop
    margin = lim - eff[:, None]
    det_m = np.interp(margin, [-2, 0, 1.2, 3, 5], [0, 25, 55, 85, 100])
    det = np.where(is_pl[:, None], 0.7 * interest[:, None] + 0.3 * det_m, det_m)
    det = np.where(is_moon[:, None], 100.0, det)
    det = np.minimum(det, det_cap[:, None])
    alt_sc = np.interp(alt, [10, 20, 30, 45, 60, 75, 90], [0, 15, 40, 70, 90, 98, 100])
    moon_sc = np.interp(drop, [0, 0.3, 1, 2, 3], [100, 90, 65, 30, 0])
    cond = np.where(is_deep[:, None], (0.8 * trans + 0.2 * seeing)[None, :], (0.7 * seeing + 0.3 * trans)[None, :])
    cond = 0.85 * cond + 0.15 * side[None, :]
    base = w[:, 0:1] * alt_sc + w[:, 1:2] * det + w[:, 2:3] * cond + w[:, 3:4] * moon_sc
    total = np.where(mask, base * gate[None, :], -1.0)
    best_i = total.argmax(axis=1)
    idx = np.arange(n_t)
    best_val = total[idx, best_i]
    hours_up = mask.sum(axis=1) * step_s / 3600.0
    dur = np.interp(hours_up, [0, 0.5, 1, 2, 4], [0, 30, 55, 85, 100])
    score = np.where(best_val >= 0, 0.88 * best_val + 0.12 * dur, 0.0)
    alt_obs = np.where(obs_sun, alt, -90.0)
    peak_i = alt_obs.argmax(axis=1)
    clock = lambda t: fmt_clock(t, off)
    rating_of = lambda mg: "Easy" if mg >= 3 else "Moderate" if mg >= 1.2 else "Hard" if mg >= 0 else "Beyond"

    rows, hidden = [], 0
    for i, o in enumerate(targets):
        if kind_filter and o["kind"] not in kind_filter:
            continue
        if score[i] <= 0:
            hidden += 1
            continue
        bi, pi = int(best_i[i]), int(peak_i[i])
        g = group[i]
        drop_b, sep_b = float(drop[i, bi]), float(pos["sep"][i, bi])
        c_b, tr_b, se_b, g_b = float(cloud[bi]), float(trans[bi]), float(seeing[bi]), float(gate[bi])
        illum_b, malt_b = float(pos["moon_illum"][bi]), float(pos["moon_alt"][bi])
        mg_b = float(margin[i, bi])
        rating = "Beyond" if det_cap[i] == 0 else rating_of(mg_b)
        fwhm_b = seeing_fwhm(se_b)
        cap_b = min(2.0 * ap_eff, 200.0 / fwhm_b)
        combo, why = recommend_view(dict(o, diam=o.get("diam", 0.0)), combos, ap_eff, cap_b, drop_b)
        pk, pk_ts = float(alt_obs[i, pi]), float(ts[pi])
        R = []
        R.append(("good" if pk >= 60 else "info" if pk >= 45 else "warn",
                  f"Peaks at {pk:.0f} deg around {clock(pk_ts)} (airmass {airmass(pk):.2f}); {hours_up[i]:.1f} h above {min_alt:.0f} deg in a dark enough sky."))
        R.append(("good" if c_b < 20 else "info" if c_b < 50 else "bad",
                  f"Around {clock(float(ts[bi]))}: cloud {c_b:.0f}%, transparency {tr_b:.0f}/100, seeing about {fwhm_b:.1f} arcsec."))
        if g_b < 0.6:
            R.append(("warn", f"Cloud and rain chance cut the score to {g_b * 100:.0f}% of its potential at that time."))
        if g != "MOON":
            if malt_b <= 0:
                R.append(("good", "The Moon is below the horizon then: no glare."))
            else:
                lvl = "good" if drop_b < 0.3 else "info" if drop_b < 1.0 else "warn" if drop_b < 2.0 else "bad"
                near = "very close" if sep_b < 20 else "far" if sep_b > 90 else "moderately far"
                R.append((lvl, f"Moon {illum_b * 100:.0f}% lit, {sep_b:.0f} deg away ({near}): costs about {drop_b:.1f} mag of sky limit."))
        if g == "PL":
            R.append(("info", f"{o['diam']:.0f}\" disc, {o['phase'] * 100:.0f}% lit, mag {o['mag']:.1f}: expect {PLANET_NOTES[o['id']]}."))
        elif g == "MOON":
            R.append(("info", f"Moon {o['phase'] * 100:.0f}% lit: best detail is along the terminator."))
        elif g == "DS":
            R.append(("good" if rating in ("Easy", "Moderate") else "warn",
                      f"Double star, primary mag {o['mag']:.1f}, separation {o['sep']:.1f}\" (your Dawes limit is {dawes:.2f}\"): {rating}."
                      + (" Too tight to split." if det_cap[i] == 0 else "")))
        else:
            R.append(("good" if rating in ("Easy", "Moderate") else "warn",
                      f"{KIND_NAMES[o['kind']]}, mag {o['mag']:.1f}, {o['size']:.0f}' across: {rating} in {ap:.0f} mm ({mg_b:+.1f} mag margin)."))
        parts = {"altitude": float(alt_sc[i, bi]), "detectability": float(det[i, bi]), "conditions": float(cond[i, bi]),
                 "moon": float(moon_sc[i, bi])}
        loss = {"altitude": w[i, 0] * (100 - parts["altitude"]), "detectability": w[i, 1] * (100 - parts["detectability"]),
                "conditions": w[i, 2] * (100 - parts["conditions"]), "Moon glare": w[i, 3] * (100 - parts["moon"]),
                "cloud / rain": float(base[i, bi]) * (1.0 - g_b)}
        lim_name = max(loss, key=loss.get)
        if loss[lim_name] >= 6:
            R.append(("info", f"Biggest drag on the score: {lim_name} (about -{loss[lim_name]:.0f} points)."))
        rows.append({"ti": i, "id": o["id"], "name": o["name"], "kind": o["kind"], "score": float(score[i]),
                     "best_ts": float(ts[bi]), "peak_alt": pk, "peak_ts": pk_ts, "hours_up": float(hours_up[i]),
                     "sep": sep_b, "drop": drop_b, "mag": o["mag"], "size": o["size"], "rating": rating,
                     "view": combo, "view_why": why, "reasons": R, "parts": parts, "gate": g_b})
    rows.sort(key=lambda r: -r["score"])
    return {"ts": ts, "sun_alt": pos["sun_alt"], "moon_alt": pos["moon_alt"], "alt": pos["alt"], "targets": targets,
            "rows": rows, "hidden": hidden, "engine": engine, "note": note, "offset": off, "min_alt": min_alt,
            "t_pos_ms": t_pos * 1000.0, "t_total_ms": (time.perf_counter() - tc) * 1000.0, "step_s": step_s,
            "now": time.time()}


def engine_check(lat, lon, now_ts, elev=0.0):
    """Compare the three engines on a 3-night grid: agreement and speed."""
    if not HAVE_NUMPY:
        return "NumPy is not installed: only the pure-Python engine is available."
    ts = np.arange(now_ts, now_ts + 3 * 86400, 600.0)
    lines, res = [f"Grid: {len(ts)} times x {len(CATALOG) + len(PLANETS) + 1} targets"], {}
    for name, fn in (("pure Python", positions_scalar), ("NumPy", positions_numpy)):
        t = time.perf_counter()
        res[name] = fn(ts, lat, lon)
        lines.append(f"{name:<12} {(time.perf_counter() - t) * 1000:8.1f} ms")
    d = np.abs(res["pure Python"]["alt"] - res["NumPy"]["alt"])
    lines.append(f"NumPy vs pure Python: max altitude difference {float(d.max()):.2e} deg")
    if not HAVE_ASTROPY:
        lines.append("Astropy: not installed (pip install astropy to enable precision mode)")
    else:
        try:
            t = time.perf_counter()
            ap = positions_astropy(ts, lat, lon, elev, 0.0)
            lines.append(f"{'Astropy':<12} {(time.perf_counter() - t) * 1000:8.1f} ms")
            da = np.abs(ap["alt"] - res["NumPy"]["alt"])
            lines.append(f"Astropy vs NumPy: mean {float(da.mean()) * 60:.1f} arcmin, max {float(da.max()):.3f} deg "
                         f"(Moon max {float(np.abs(ap['moon_alt'] - res['NumPy']['moon_alt']).max()) * 60:.1f} arcmin)")
        except Exception as e:
            lines.append(f"Astropy failed: {type(e).__name__}: {str(e)[:90]}")
    return "\n".join(lines)


# ===========================================================================
# TELESCOPE / OPTICS MATH
# ===========================================================================
def scope_numbers(sc, nelm):
    ap, fl = float(sc["aperture"]), float(sc["focal_length"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    return {"ap": ap, "fl": fl, "obs": obs, "ap_eff": ap_eff, "f": fl / ap,
            "min_mag": ap / 7.0, "max_mag": 2.0 * ap, "comfort": 1.5 * ap,
            "dawes": 116.0 / ap, "rayleigh": 138.0 / ap, "gather": (ap_eff / 7.0) ** 2,
            "lim": nelm + 5.0 * math.log10(ap_eff / 7.0), "lim_ideal": 6.5 + 5.0 * math.log10(ap_eff / 7.0),
            "scale_mm": 206265.0 / fl, "moon_mm": fl * math.tan(rad(0.52)), "airy": 2.44 * 0.55e-3 * (fl / ap)}


def drift_seconds(tfov_deg, dec_deg):
    return tfov_deg * 3600.0 / (15.041 * max(0.05, math.cos(rad(dec_deg))))


def camera_numbers(fl, ap, pixel_um, w_px, h_px, fwhm, dec):
    scale = 206.265 * pixel_um / fl
    n = fl / ap
    return {"scale": scale, "fov_w": scale * w_px / 3600.0, "fov_h": scale * h_px / 3600.0, "n": n,
            "sampling": fwhm / scale if scale > 0 else 0.0,
            "npf": (16.856 * n + 0.0997 * fl + 13.713 * pixel_um) / (fl * max(0.05, math.cos(rad(dec)))),
            "rule500": 500.0 / fl, "ideal_lo": 3.0 * pixel_um, "ideal_hi": 5.0 * pixel_um}


def fmt_angle(arcsec):
    if arcsec >= 3600:
        return f"{arcsec / 3600.0:.3g} deg"
    if arcsec >= 60:
        return f"{arcsec / 60.0:.3g} arcmin"
    return f"{arcsec:.3g} arcsec"


# ===========================================================================
# UI
# ===========================================================================
ALT_W, ALT_H = 600, 300
ALT_BANDS = ["#3d6a9e", "#2a3a6a", "#1a2650", "#101a3a", "#0a0d18"]
ALT_COLORS = ["#5ec8ff", "#ff9f5e", "#7ee787", "#ff7ab8", "#c9a7ff", "#f2e05e", "#6fe3d0", "#ff6b6b"]
CAM_MODES = ["Prime focus (camera at the focuser)", "Phone at the eyepiece (afocal)"]
PHONE_PRESETS = {
    "Custom": None,
    "iPhone XS Max - wide 12 MP (f/1.8)": {"pix": 1.4, "w": 4032, "h": 3024, "lens": 4.25, "fno": 1.8,
                                           "note": "Best all-round lens for the eyepiece. 1.4 um pixels, about 4.25 mm real focal length."},
    "iPhone XS Max - telephoto 12 MP (f/2.4)": {"pix": 1.0, "w": 4032, "h": 3024, "lens": 6.0, "fno": 2.4,
                                                "note": "2x lens: fills the eyepiece circle better, smaller entrance pupil."},
    "iPhone 16 Pro Max - main 48 MP (f/1.8)": {"pix": 1.22, "w": 8064, "h": 6048, "lens": 6.8, "fno": 1.78,
                                               "note": "48 MP mode (ProRAW/HEIF). Pixels are tiny: expect them to oversample, bin to 12 MP for the Moon and planets."},
    "iPhone 16 Pro Max - main 12 MP binned": {"pix": 2.44, "w": 4032, "h": 3024, "lens": 6.8, "fno": 1.78,
                                              "note": "2x2 binned: 2.44 um effective pixels, cleaner for planets and the Moon."},
    "iPhone 16 Pro Max - ultra wide 48 MP (f/2.2)": {"pix": 0.7, "w": 8064, "h": 6048, "lens": 2.1, "fno": 2.2,
                                                    "note": "Very wide and tiny pixels: usually vignettes badly at an eyepiece."},
    "iPhone 16 Pro Max - 5x telephoto 12 MP (f/2.8)": {"pix": 1.12, "w": 4032, "h": 3024, "lens": 15.6, "fno": 2.8,
                                                      "note": "Long lens: great at filling the frame with a 20 mm eyepiece, but a larger exit pupil match is needed."},
}
BAND_COLORS = ["#d8b24a", "#b9783c", "#455a8f", "#27345f", "#0f1630"]
BAND_NAMES = ["day", "civil twilight", "nautical twilight", "astronomical twilight", "full night"]
HEAT_ROWS = [("Light", "band"), ("Moon altitude", "moon"), ("Cloud total %", "cloud"), ("   low %", "low"),
             ("   mid %", "mid"), ("   high %", "high"), ("Rain chance %", "rain"), ("Transparency", "trans"),
             ("Seeing (est.)", "seeing"), ("Wind", "wind"), ("Gusts", "gust"), ("Humidity %", "rh"),
             ("Dew margin", "dew"), ("Temperature", "temp"), ("DEEP-SKY score", "dso"), ("PLANETARY score", "planet")]
CW, RH, HDR, LBLW = 31, 25, 42, 132
LEVEL_COLORS = {"good": "#4cc38a", "info": "#a9b8d6", "warn": "#e0b84c", "bad": "#e06c6c"}


def fmt_temp(c, units):
    return f"{c * 9 / 5 + 32:.0f}F" if units.get("temp") == "F" else f"{c:.0f}C"


def conv_wind(kmh, units):
    u = units.get("wind", "km/h")
    return kmh / 3.6 if u == "m/s" else kmh * 0.621371 if u == "mph" else kmh


class AstroApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        apply_perf(self.cfg)
        self.events = queue.Queue()
        self.analysis = None
        self.busy = False
        self.sky_ts = time.time()
        self.sel_col = None
        self.ent, self.out, self.opt = {}, {}, {}
        self.req_id, self.dirty = 0, set()
        self._calc_job = self._sky_job = self._sky_job2 = None
        self.plan, self.plan_busy, self.plan_req, self.plan_sel, self.plot_set = None, False, 0, None, []
        self.title("AstroWeather")
        self.geometry("1260x820")
        self.minsize(1120, 720)
        self.f_title = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        self.f_h2 = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.f_ui = ctk.CTkFont(family="Segoe UI", size=13)
        self.f_small = ctk.CTkFont(family="Segoe UI", size=11)
        self.f_mono = ctk.CTkFont(family="Consolas", size=12)
        self.f_mono_s = ctk.CTkFont(family="Consolas", size=11)
        self.f_big = ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        self.build_ui()
        self.update_location_label()
        self.update_calcs()
        self.load_cache()
        self.after(150, self.pump)
        self.after(300, self.refresh)
        self.after(60000, self.tick)

    def report_callback_exception(self, exc, val, tb):
        log_error("".join(traceback.format_exception(exc, val, tb)))

    # ------------------------------------------------------------------ shell
    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, width=190, corner_radius=0, fg_color="#101216")
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="AstroWeather", font=self.f_title).pack(anchor="w", padx=20, pady=(24, 0))
        ctk.CTkLabel(side, text="observing planner", font=self.f_small, text_color="#777").pack(anchor="w", padx=21, pady=(0, 20))
        self.nav = {}
        for key, label in (("tonight", "Tonight"), ("forecast", "Forecast"), ("planner", "Planner"), ("sky", "Sky chart"),
                           ("scope", "Telescope"), ("settings", "Settings")):
            b = ctk.CTkButton(side, text=label, anchor="w", height=38, corner_radius=8, fg_color="transparent",
                              hover_color="#232830", text_color="#d0d4dc", font=self.f_ui,
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=12, pady=3)
            self.nav[key] = b

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(content, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 2))
        self.lbl_loc = ctk.CTkLabel(bar, text="", font=self.f_h2)
        self.lbl_loc.pack(side="left")
        self.btn_refresh = ctk.CTkButton(bar, text="Refresh", width=90, font=self.f_ui, command=self.refresh)
        self.btn_refresh.pack(side="right")
        self.lbl_status = ctk.CTkLabel(bar, text="", font=self.f_small, text_color="#8a93a6")
        self.lbl_status.pack(side="right", padx=12)

        host = ctk.CTkFrame(content, fg_color="transparent")
        host.grid(row=1, column=0, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        self.pages = {}
        for key, builder in (("tonight", self.build_tonight), ("forecast", self.build_forecast), ("planner", self.build_planner),
                             ("sky", self.build_sky), ("scope", self.build_scope), ("settings", self.build_settings)):
            page = ctk.CTkFrame(host, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self.pages[key] = page
        self.show_page("tonight")

    def show_page(self, key):
        self.current = key
        self.pages[key].tkraise()
        for k, b in self.nav.items():
            b.configure(fg_color="#232a36" if k == key else "transparent")
        if key == "sky":
            self.dirty.add("sky")
        self.flush_dirty()

    def flush_dirty(self):
        """Draw the expensive pages only when they are on screen (the heat map alone is ~3,800 canvas items)."""
        cur = getattr(self, "current", None)
        if cur in self.dirty:
            self.dirty.discard(cur)
            if cur == "forecast":
                self.draw_heatmap()
            elif cur == "sky":
                self.draw_sky()
            elif cur == "planner":
                self.plan_page_refresh()

    def update_location_label(self):
        loc = self.cfg["location"]
        self.lbl_loc.configure(text=f"{loc['name']}   ({loc['lat']:.3f}, {loc['lon']:.3f})")

    def card(self, parent, title=None, pady=6):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        f.pack(fill="x", padx=6, pady=pady)
        if title:
            ctk.CTkLabel(f, text=title, font=self.f_h2).pack(anchor="w", padx=16, pady=(12, 4))
        return f

    def set_text(self, box, text):
        if getattr(box, "_aw_text", None) == text:
            return  # rewriting an identical text widget is surprisingly slow
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")
        box._aw_text = text

    # ------------------------------------------------------------- data flow
    def load_cache(self):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            loc = self.cfg["location"]
            if abs(c["lat"] - loc["lat"]) < 0.05 and abs(c["lon"] - loc["lon"]) < 0.05:
                self.apply_analysis(analyze(c["wx"], c["aq"], self.cfg, time.time()),
                                    f"cached data from {datetime.fromtimestamp(c['fetched']):%H:%M %d %b}")
        except Exception:
            pass

    def refresh(self, force=False):
        if self.busy and not force:
            return
        self.busy = True
        self.req_id += 1
        self.btn_refresh.configure(state="disabled")
        self.lbl_status.configure(text="updating...")
        # the worker gets its own copy of the settings, so edits in the UI can't race with the analysis
        threading.Thread(target=self.worker, args=(self.req_id, copy.deepcopy(self.cfg)), daemon=True).start()

    def worker(self, req, cfg):
        loc = dict(cfg["location"])
        try:
            wx, aq = fetch_weather(float(loc["lat"]), float(loc["lon"]))
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump({"lat": loc["lat"], "lon": loc["lon"], "fetched": time.time(), "wx": wx, "aq": aq}, f)
            except OSError:
                pass
            result = analyze(wx, aq, cfg, time.time())
            self.events.put(("data", result, "updated " + datetime.now().strftime("%H:%M"), req))
        except Exception as e:
            log_error(traceback.format_exc())
            self.events.put(("error", f"{type(e).__name__}: {e}", req))

    def geo_worker(self, name):
        try:
            self.events.put(("geo", geocode(name)))
        except Exception as e:
            self.events.put(("geo_error", str(e)))

    def tick(self):
        mins = max(10, int(self.cfg.get("auto_refresh_min", 30)))
        if time.time() - (self.analysis["fetched"] if self.analysis else 0) > mins * 60:
            self.refresh()
        self.after(60000, self.tick)

    def pump(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind in ("data", "error"):
                    if ev[-1] != self.req_id:
                        continue  # stale answer for an older request (location changed meanwhile)
                    self.busy = False
                    self.btn_refresh.configure(state="normal")
                    if kind == "data":
                        self.apply_analysis(ev[1], ev[2])
                    else:
                        note = "offline: " + ev[1]
                        self.lbl_status.configure(text=note[:90] + (" (showing last data)" if self.analysis else ""))
                elif kind == "geo":
                    self.show_geo_results(ev[1])
                elif kind == "geo_error":
                    self.geo_status.configure(text="search failed: " + ev[1][:80])
                elif kind == "plan":
                    if ev[1] == self.plan_req:
                        self.plan_busy = False
                        self.btn_plan.configure(state="normal")
                        self.show_plan(ev[2])
                elif kind == "plan_error":
                    if ev[1] == self.plan_req:
                        self.plan_busy = False
                        self.btn_plan.configure(state="normal")
                        self.plan_status.configure(text=ev[2][:110])
                elif kind == "engine":
                    self.lbl_engine.configure(text=ev[1])
                    self.btn_engine.configure(state="normal")
        except queue.Empty:
            pass
        except Exception:
            log_error(traceback.format_exc())
        self.after(150, self.pump)

    def apply_analysis(self, a, status):
        self.analysis = a
        self.lbl_status.configure(text=status)
        self.fill_tonight()
        self.dirty |= {"forecast", "sky", "planner"}
        self.flush_dirty()
        self.update_calcs()

    # =========================================================== TONIGHT PAGE
    def build_tonight(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=18, pady=(0, 14))

        top = self.card(body)
        top.grid_columnconfigure(2, weight=1)
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=10)
        self.g_dso = tk.Canvas(row, width=230, height=200, bg=CARD, highlightthickness=0)
        self.g_dso.pack(side="left", padx=6)
        self.g_pl = tk.Canvas(row, width=230, height=200, bg=CARD, highlightthickness=0)
        self.g_pl.pack(side="left", padx=6)
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=14)
        ctk.CTkLabel(right, text="Best window to observe", font=self.f_h2).pack(anchor="w")
        self.lbl_best = ctk.CTkLabel(right, text="-", font=self.f_big, anchor="w")
        self.lbl_best.pack(anchor="w", pady=(2, 0))
        self.lbl_best_sub = ctk.CTkLabel(right, text="", font=self.f_ui, text_color="#a9b8d6", justify="left", anchor="w")
        self.lbl_best_sub.pack(anchor="w", pady=(2, 8))
        self.lbl_dark = ctk.CTkLabel(right, text="", font=self.f_ui, justify="left", anchor="w")
        self.lbl_dark.pack(anchor="w")

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", padx=0, pady=2)
        self.stat = {}
        names = [("cloud", "Clouds (dark hours)"), ("trans", "Transparency"), ("seeing", "Seeing (estimate)"),
                 ("wind", "Wind / gusts"), ("dew", "Dew risk"), ("temp", "Temperature"),
                 ("moon", "Moon"), ("rain", "Rain chance"), ("jet", "Jet stream / humidity")]
        for i, (key, title) in enumerate(names):
            grid.grid_columnconfigure(i % 3, weight=1, uniform="st")
            c = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=12)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(c, text=title, font=self.f_small, text_color="#8a93a6").pack(anchor="w", padx=14, pady=(10, 0))
            v = ctk.CTkLabel(c, text="-", font=self.f_big, anchor="w")
            v.pack(anchor="w", padx=14)
            s = ctk.CTkLabel(c, text="", font=self.f_small, text_color="#a9b8d6", justify="left", anchor="w")
            s.pack(anchor="w", padx=14, pady=(0, 10))
            self.stat[key] = (v, s)

        c = self.card(body, "What to know tonight")
        self.ins_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.ins_frame.pack(fill="x", padx=16, pady=(0, 12))
        c = self.card(body, "Sun, Moon and planets tonight")
        self.box_planets = ctk.CTkTextbox(c, height=250, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_planets.pack(fill="x", padx=14, pady=(0, 14))
        c = self.card(body, "Top targets for your scope")
        self.lbl_targets = ctk.CTkLabel(c, text="", font=self.f_small, text_color="#8a93a6", anchor="w")
        self.lbl_targets.pack(anchor="w", padx=16)
        self.box_targets = ctk.CTkTextbox(c, height=330, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_targets.pack(fill="x", padx=14, pady=(2, 14))
        self.draw_gauge(self.g_dso, None, "Deep-sky score")
        self.draw_gauge(self.g_pl, None, "Planetary score")

    def draw_gauge(self, c, score, title):
        c.delete("all")
        cx, cy, r = 115, 98, 76
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270, style="arc", width=14, outline="#2a2e36")
        word, face = verdict(score)
        if score is not None:
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=225, extent=-270 * clamp(score) / 100.0,
                         style="arc", width=14, outline=score_color(score))
            c.create_text(cx, cy - 8, text=f"{score:.0f}", fill="#ffffff", font=("Segoe UI", 36, "bold"))
        else:
            c.create_text(cx, cy - 8, text="--", fill="#777777", font=("Segoe UI", 36, "bold"))
        c.create_text(cx, cy + 32, text=word, fill="#d0d4dc", font=("Segoe UI", 12, "bold"))
        c.create_text(cx, cy + 52, text=face, fill="#a9b8d6", font=("Segoe UI", 11))
        c.create_text(cx, 190, text=title, fill="#8a93a6", font=("Segoe UI", 10))

    def fill_tonight(self):
        a, u, off = self.analysis, self.cfg["units"], self.analysis["offset"]
        tn, win = a["tonight"], a["tonight"]["win"]
        self.draw_gauge(self.g_dso, tn["dso"], "Deep-sky score")
        self.draw_gauge(self.g_pl, tn["planet"], "Planetary score")
        if tn["best"]:
            avg, t0, t1 = tn["best"]
            self.lbl_best.configure(text=f"{fmt_clock(t0, off)} - {fmt_clock(t1, off)}")
            self.lbl_best_sub.configure(text=f"average deep-sky score {avg:.0f}/100 in the best 2-hour block")
        else:
            self.lbl_best.configure(text="none left")
            self.lbl_best_sub.configure(text="no dark hours remain in the forecast window")
        dusk = fmt_clock(win["dusk"], off) if win.get("dusk") else "-"
        dawn = fmt_clock(win["dawn"], off) if win.get("dawn") else "-"
        self.lbl_dark.configure(text=f"Sunset {fmt_clock(win['start'], off)}   |   astronomical dark {dusk} - {dawn}   |   sunrise {fmt_clock(win['end'], off)}")

        def setv(key, big, sub, score=None):
            v, s = self.stat[key]
            v.configure(text=big, text_color=score_color(score) if score is not None else "#ffffff")
            s.configure(text=sub)

        if not tn["dark"]:
            for k in self.stat:
                setv(k, "-", "no dark hours")
        else:
            setv("cloud", f"{tn['cloud']:.0f}%", "average, sun below -12 deg", 100 - tn["cloud"])
            setv("trans", f"{tn['trans']:.0f}/100", f"humidity {tn['rh']:.0f}%" if tn["rh"] is not None else "", tn["trans"])
            setv("seeing", seeing_label(tn["seeing"]), f"about {tn['fwhm']:.1f} arcsec  ({tn['seeing']:.0f}/100)", tn["seeing"])
            unit = u.get("wind", "km/h")
            setv("wind", f"{conv_wind(tn['wind'], u):.0f} {unit}", f"gusts up to {conv_wind(tn['gust'], u):.0f} {unit}", score_wind(tn["wind"], tn["gust"]))
            sp = tn["spread"]
            if sp is None:
                setv("dew", "-", "")
            else:
                label = "high" if sp < 1.5 else "moderate" if sp < 3 else "low"
                setv("dew", label, f"closest approach {sp:.1f} deg to dew point", score_dew(sp))
            setv("temp", f"{fmt_temp(tn['tmin'], u)} - {fmt_temp(tn['tmax'], u)}", "during the dark hours")
            setv("rain", f"{tn['pp']:.0f}%", "highest chance tonight", 100 - tn["pp"])
            setv("jet", f"{tn['jet']:.0f} m/s" if tn["jet"] is not None else "n/a",
                 "upper-air wind (250-300 hPa)" if tn["jet"] is not None else "not provided for this place")
        m = a["moon"]["mid"]
        evs = []
        for kind, ts in a["moon"]["events"]:
            if win["start"] - 3600 <= ts <= win["end"] + 3600:
                evs.append(f"{'rises' if kind == 'rise' else 'sets'} {fmt_clock(ts, off)}")
        v, s = self.stat["moon"]
        v.configure(text=f"{m['illum'] * 100:.0f}%", text_color="#ffffff")
        s.configure(text=m["name"] + ("\n" + ", ".join(evs) if evs else ""))

        for w in self.ins_frame.winfo_children():
            w.destroy()
        for level, text in a["insights"]:
            ctk.CTkLabel(self.ins_frame, text="•  " + text, font=self.f_ui, text_color=LEVEL_COLORS[level],
                         justify="left", anchor="w", wraplength=880).pack(anchor="w", pady=2)

        mn = a["moon"]
        lines = [f"{'Body':<9}{'Mag':>6}{'Size':>10}{'Phase':>8}{'Elong':>8}   {'Best alt':>8}  {'at':<6}  Visible (alt>10, dark)"]
        for p in a["planets"]:
            el = f"{p['elong']:+.0f}" if p["elong"] is not None else "-"
            vis = f"{fmt_clock(p['vis'][0], off)} - {fmt_clock(p['vis'][1], off)}" if p["vis"] else "not up tonight"
            lines.append(f"{p['name']:<9}{p['mag']:>6.1f}{fmt_angle(p['diam']):>10}{p['phase'] * 100:>7.0f}%{el:>8}   "
                         f"{p['best_alt']:>7.0f}d  {fmt_clock(p['best_ts'], off):<6}  {vis}")
        nn, nf = mn["next_new"], mn["next_full"]
        lines.append("")
        lines.append("Next new Moon: " + (datetime.fromtimestamp(nn, timezone(timedelta(seconds=off))).strftime("%a %d %b %H:%M") if nn else "-")
                     + "    next full Moon: " + (datetime.fromtimestamp(nf, timezone(timedelta(seconds=off))).strftime("%a %d %b %H:%M") if nf else "-"))
        lines.append("Elong = degrees from the Sun (+ east/evening, - west/morning). Never point a telescope at the Sun without a certified solar filter.")
        self.set_text(self.box_planets, "\n".join(lines))
        self.fill_targets()

    def fill_targets(self):
        a, off = self.analysis, self.analysis["offset"]
        rows = [r for r in a["targets"] if r["alt"] >= 25 and r["rating"] != "Beyond"]
        order = {"Easy": 0, "Moderate": 1, "Hard": 2}
        rows.sort(key=lambda r: (order[r["rating"]], -(r["alt"] // 15), r["obj"]["mag"]))
        sc = self.cfg["scope"]
        self.lbl_targets.configure(text=f"Evaluated for {fmt_clock(a['eval_ts'], off)}, sky limit about mag {rows[0]['lim_dark']:.1f} before Moon glare "
                                        f"({sc['aperture']:.0f} mm, rough estimate)" if rows else "Nothing suitable is high enough then.")
        lines = [f"{'Object':<10}{'Name':<24}{'Type':<15}{'Mag':>5}{'Size':>9}{'Alt':>5}{'Moon':>11}  {'Rating':<9}Suggested view"]
        for r in rows[:16]:
            o = r["obj"]
            size = f"{o['sep']:.1f}\"" if o["kind"] == "DS" else (f"{o['size']:.0f}'" if o["size"] >= 1 else f"{o['size'] * 60:.0f}\"")
            combo = r["combo"]
            view = f"{combo['label']} ({combo['mag']:.0f}x, {combo['tfov'] * 60:.0f}' field)" if combo else "-"
            lines.append(f"{o['id'][:9]:<10}{o['name'][:23]:<24}{KIND_NAMES[o['kind']]:<15}{o['mag']:>5.1f}{size:>9}{r['alt']:>4.0f}d{(f"{r['sep']:.0f}d/-{r['drop']:.1f}m" if r['drop'] > 0.05 else '-'):>11}  {r['rating']:<9}{view}")
        self.set_text(self.box_targets, "\n".join(lines))

    # =========================================================== FORECAST PAGE
    def build_forecast(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(page, text="Hour-by-hour (local time). Click a column for full details.   "
                                "Green = good for observing, red = bad.", font=self.f_small, text_color="#8a93a6").grid(
            row=0, column=0, sticky="w", padx=26, pady=(2, 4))
        wrap = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        wrap.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 8))
        wrap.grid_columnconfigure(1, weight=1)
        wrap.grid_rowconfigure(0, weight=0)
        h = HDR + len(HEAT_ROWS) * RH
        self.hm_labels = tk.Canvas(wrap, width=LBLW, height=h, bg=CARD, highlightthickness=0)
        self.hm_labels.grid(row=0, column=0, sticky="n", padx=(8, 0), pady=8)
        self.hm_data = tk.Canvas(wrap, height=h, bg=CARD, highlightthickness=0, xscrollincrement=CW)
        self.hm_data.grid(row=0, column=1, sticky="ew", padx=0, pady=8)
        sb = ctk.CTkScrollbar(wrap, orientation="horizontal", command=self.hm_data.xview)
        sb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        self.hm_data.configure(xscrollcommand=sb.set)
        self.hm_data.bind("<Button-1>", self.on_heat_click)
        self.hm_data.bind("<MouseWheel>", lambda e: self.hm_data.xview_scroll(-3 if e.delta > 0 else 3, "units"))
        self.box_detail = ctk.CTkTextbox(page, height=180, font=self.f_mono, fg_color=DEEP, state="disabled")
        self.box_detail.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))
        self.set_text(self.box_detail, "Click an hour above to see every value for it.")

    def cell(self, h, kind):
        u = self.cfg["units"]
        dim = "#20242e"
        if kind == "band":
            return "", BAND_COLORS[h["dark"]]
        if kind == "moon":
            if h["moon_alt"] <= 0:
                return "", "#141826"
            k = clamp(h["moon_illum"], 0, 1)
            col = "#%02x%02x%02x" % (int(42 + 190 * k), int(53 + 175 * k), int(80 + 112 * k))
            return f"{h['moon_alt']:.0f}", col
        if kind == "cloud":
            return f"{h['cloud']:.0f}", score_color(100 - h["cloud"])
        if kind in ("low", "mid", "high"):
            v = h[kind]
            return ("", dim) if v is None else (f"{v:.0f}", score_color(100 - v))
        if kind == "rain":
            return f"{h['pp']:.0f}", score_color(piecewise(h["pp"], [(0, 100), (10, 95), (30, 60), (60, 20), (100, 0)]))
        if kind == "trans":
            return f"{h['sc_trans']:.0f}", score_color(h["sc_trans"])
        if kind == "seeing":
            return f"{seeing_fwhm(h['sc_seeing']):.1f}\"", score_color(h["sc_seeing"])
        if kind == "wind":
            return f"{conv_wind(h['wind'], u):.0f}", score_color(score_wind(h["wind"], 0))
        if kind == "gust":
            return f"{conv_wind(h['gust'], u):.0f}", score_color(piecewise(h["gust"], [(0, 100), (15, 100), (30, 60), (50, 20), (70, 0)]))
        if kind == "rh":
            return ("", dim) if h["rh"] is None else (f"{h['rh']:.0f}", score_color(piecewise(h["rh"], [(0, 100), (60, 100), (80, 70), (90, 40), (100, 15)])))
        if kind == "dew":
            return ("", dim) if h["spread"] is None else (f"{h['spread']:.1f}", score_color(h["sc_dew"]))
        if kind == "temp":
            return f"{h['temp'] * 9 / 5 + 32:.0f}" if u.get("temp") == "F" else f"{h['temp']:.0f}", "#2b3a55"
        if kind == "dso":
            return ("-", dim) if h["sun_alt"] >= -12 else (f"{h['dso']:.0f}", score_color(h["dso"]))
        if kind == "planet":
            return ("-", dim) if h["sun_alt"] >= -6 else (f"{h['planet']:.0f}", score_color(h["planet"]))
        return "", dim

    def draw_heatmap(self):
        lc, dc = self.hm_labels, self.hm_data
        lc.delete("all")
        dc.delete("all")
        a = self.analysis
        if not a:
            return
        hours, off = a["hours"], a["offset"]
        tz = timezone(timedelta(seconds=off))
        n = len(hours)
        total_h = HDR + len(HEAT_ROWS) * RH
        dc.configure(scrollregion=(0, 0, n * CW, total_h))
        for i, h in enumerate(hours):
            x = i * CW
            dt = datetime.fromtimestamp(h["ts"], tz)
            dc.create_text(x + CW / 2, HDR - 12, text=f"{dt.hour:02d}", fill="#cfd6e4", font=("Segoe UI", 9))
            if dt.hour == 0 or i == 0:
                dc.create_text(x + 3, 11, text=dt.strftime("%a %d %b"), anchor="w", fill="#8fa3c8", font=("Segoe UI", 9, "bold"))
        for r, (label, kind) in enumerate(HEAT_ROWS):
            y = HDR + r * RH
            bold = kind in ("dso", "planet")
            lc.create_text(6, y + RH / 2, text=label, anchor="w", fill="#e4e8f0" if bold else "#b9c0cf",
                           font=("Segoe UI", 9, "bold" if bold else "normal"))
            for i, h in enumerate(hours):
                text, color = self.cell(h, kind)
                x = i * CW
                dc.create_rectangle(x + 1, y + 1, x + CW - 1, y + RH - 1, fill=color, outline="")
                if text:
                    dc.create_text(x + CW / 2, y + RH / 2, text=text, fill=text_on(color), font=("Segoe UI", 8))
        now_i = max([i for i, h in enumerate(hours) if h["ts"] <= a["now"]] or [0])
        dc.create_rectangle(now_i * CW, HDR - 2, (now_i + 1) * CW, total_h, outline="#5ec8ff", width=2)
        dc.xview_moveto(max(0, (now_i - 1) * CW) / float(max(1, n * CW)))
        self.sel_col = None

    def on_heat_click(self, event):
        a = self.analysis
        if not a:
            return
        i = int(self.hm_data.canvasx(event.x) // CW)
        if 0 <= i < len(a["hours"]):
            self.select_col(i)

    def select_col(self, i):
        a, u = self.analysis, self.cfg["units"]
        dc = self.hm_data
        dc.delete("sel")
        total_h = HDR + len(HEAT_ROWS) * RH
        dc.create_rectangle(i * CW, 0, (i + 1) * CW, total_h, outline="#ffffff", width=2, tags="sel")
        h = a["hours"][i]
        tz = timezone(timedelta(seconds=a["offset"]))
        dt = datetime.fromtimestamp(h["ts"], tz)
        wu = u.get("wind", "km/h")
        lines = [
            f"{dt:%A %d %b, %H:%M} local     {BAND_NAMES[h['dark']]} (sun {h['sun_alt']:+.0f} deg)     "
            f"Moon {h['moon_alt']:+.0f} deg up, {h['moon_illum'] * 100:.0f}% lit",
            f"Clouds   total {h['cloud']:.0f}%   low {h['low'] if h['low'] is not None else '-'}   mid {h['mid'] if h['mid'] is not None else '-'}   "
            f"high {h['high'] if h['high'] is not None else '-'}     rain chance {h['pp']:.0f}%   precipitation {h['precip']:.1f} mm",
            f"Air      transparency {h['sc_trans']:.0f}/100   humidity {h['rh'] if h['rh'] is None else round(h['rh'])}%   "
            f"visibility {('%.0f km' % h['vis_km']) if h['vis_km'] is not None else '-'}   "
            f"aerosol depth {('%.2f' % h['aod']) if h['aod'] is not None else '-'}   PM2.5 {('%.0f' % h['pm25']) if h['pm25'] is not None else '-'}",
            f"Seeing   about {seeing_fwhm(h['sc_seeing']):.1f} arcsec ({h['sc_seeing']:.0f}/100)   jet stream "
            f"{('%.0f m/s' % h['jet']) if h['jet'] is not None else 'n/a'}   CAPE {('%.0f' % h['cape']) if h['cape'] is not None else '-'}   "
            f"temp change {h['dtdt']:+.1f} deg/h",
            f"Wind     {conv_wind(h['wind'], u):.0f} {wu}, gusts {conv_wind(h['gust'], u):.0f} {wu}"
            + (f", from {h['wdir']:.0f} deg" if h['wdir'] is not None else ""),
            f"Dew      temp {fmt_temp(h['temp'], u)}, dew point {('%.1f deg' % h['dew']) if h['dew'] is not None else '-'}, "
            f"margin {('%.1f' % h['spread']) if h['spread'] is not None else '-'} deg   pressure {('%.0f hPa' % h['press']) if h['press'] else '-'}",
            f"Scores   deep-sky {h['dso']:.0f}   planetary {h['planet']:.0f}   (moon {h['sc_moon']:.0f}, wind {h['sc_wind']:.0f}, dew {h['sc_dew']:.0f})",
        ]
        self.set_text(self.box_detail, "\n".join(lines))

    # =============================================================== SKY PAGE
    def build_sky(self, page):
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctrl = ctk.CTkFrame(page, fg_color="transparent")
        ctrl.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 6))
        self.lbl_skytime = ctk.CTkLabel(ctrl, text="", font=self.f_h2, width=210, anchor="w")
        self.lbl_skytime.pack(side="left")
        self.sky_slider = ctk.CTkSlider(ctrl, from_=-3, to=36, number_of_steps=156, width=480, command=self.on_sky_slider)
        self.sky_slider.set(0)
        self.sky_slider.pack(side="left", padx=10)
        ctk.CTkButton(ctrl, text="Now", width=60, font=self.f_ui, command=self.sky_now).pack(side="left")
        self.lbl_skyinfo = ctk.CTkLabel(ctrl, text="", font=self.f_small, text_color="#8a93a6")
        self.lbl_skyinfo.pack(side="left", padx=14)
        self.sky_canvas = tk.Canvas(page, width=620, height=620, bg="#0a0d18", highlightthickness=0)
        self.sky_canvas.grid(row=1, column=0, sticky="n", padx=(24, 8), pady=(0, 10))
        self.box_sky = ctk.CTkTextbox(page, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_sky.grid(row=1, column=1, sticky="nsew", padx=(6, 24), pady=(0, 14))
        self.sky_base = time.time()

    def on_sky_slider(self, value):
        # a drag fires dozens of events: redraw the chart at most every ~30 ms and the table once the drag settles
        self.sky_ts = self.sky_base + float(value) * 3600.0
        if self._sky_job:
            self.after_cancel(self._sky_job)
        if self._sky_job2:
            self.after_cancel(self._sky_job2)
        self._sky_job = self.after(30, lambda: self.draw_sky(table=False))
        self._sky_job2 = self.after(300, self.draw_sky)

    def sky_now(self):
        self.sky_base = time.time()
        self.sky_ts = self.sky_base
        self.sky_slider.set(0)
        self.draw_sky()

    def draw_sky(self, table=True):
        c = self.sky_canvas
        c.delete("all")
        loc = self.cfg["location"]
        lat, lon = float(loc["lat"]), float(loc["lon"])
        ts = self.sky_ts
        jd = jd_from_ts(ts)
        off = self.analysis["offset"] if self.analysis else 0
        cx = cy = 310
        R = 282
        s = sun_pos(jd)
        sun_alt, sun_az = altaz(s["ra"], s["dec"], jd, lat, lon)
        bg = "#0a0d18" if sun_alt < -18 else "#101a3a" if sun_alt < -12 else "#1a2650" if sun_alt < -6 else "#2a3a6a" if sun_alt < -0.8 else "#3d6a9e"
        c.create_oval(cx - R, cy - R, cx + R, cy + R, fill=bg, outline="#4a5d8f", width=2)
        for alt in (30, 60):
            r = R * (90 - alt) / 90.0
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#26335a", dash=(2, 4))
        c.create_line(cx, cy - R, cx, cy + R, fill="#1d2848")
        c.create_line(cx - R, cy, cx + R, cy, fill="#1d2848")
        for txt, x, y in (("N", cx, cy - R - 12), ("S", cx, cy + R + 12), ("E", cx - R - 12, cy), ("W", cx + R + 12, cy)):
            c.create_text(x, y, text=txt, fill="#9fb2e0", font=("Segoe UI", 12, "bold"))
        c.create_text(cx + 4, cy - 4, text="zenith", fill="#3a4a78", font=("Segoe UI", 8), anchor="w")

        def project(alt, az):
            r = R * (90.0 - alt) / 90.0
            return cx - r * math.sin(rad(az)), cy - r * math.cos(rad(az))

        s_alts, s_azs = star_altaz(jd, lat, lon)
        for (name, ra_h, dec, mag), alt, az in zip(BRIGHT_STARS, s_alts, s_azs):
            if alt <= 0:
                continue
            x, y = project(alt, az)
            r = max(1.4, 3.3 - 0.85 * mag)
            c.create_oval(x - r, y - r, x + r, y + r, fill="#e9eeff", outline="")
            if mag < 1.3:
                c.create_text(x + r + 3, y, text=name, anchor="w", fill="#8e9bc4", font=("Segoe UI", 8))

        cfg = self.cfg
        nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
        sc = cfg["scope"]
        obs = float(sc.get("obstruction_mm", 0) or 0)
        ap_eff = math.sqrt(max(float(sc["aperture"]) ** 2 - obs * obs, 1.0))
        combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])
        cap = self.analysis["tonight"]["cap"] if self.analysis else 2 * ap_eff
        rows = rank_targets(ts, lat, lon, ap_eff, nelm, combos, cap)
        colors = {"Easy": "#4cc38a", "Moderate": "#e0b84c", "Hard": "#d98a52", "Beyond": "#6b7390"}
        for r in rows:
            if r["alt"] <= 3:
                continue
            x, y = project(r["alt"], r["az"])
            col = colors[r["rating"]]
            c.create_rectangle(x - 3, y - 3, x + 3, y + 3, outline=col)
            if r["rating"] in ("Easy", "Moderate") and r["alt"] > 12:
                c.create_text(x + 6, y, text=r["obj"]["id"], anchor="w", fill=col, font=("Segoe UI", 8))

        planet_list = []
        for name in PLANETS:
            st = planet_state(name, jd)
            alt, az = altaz(st["ra"], st["dec"], jd, lat, lon)
            planet_list.append((name, st, alt, az))
            if alt > 0:
                x, y = project(alt, az)
                r = max(3.0, 6.5 - 0.8 * st["mag"]) if st["mag"] < 3 else 3.0
                c.create_oval(x - r, y - r, x + r, y + r, fill=PLANET_COLORS[name], outline="")
                c.create_text(x + r + 3, y, text=name, anchor="w", fill=PLANET_COLORS[name], font=("Segoe UI", 9, "bold"))
        mi = moon_info(ts, lat, lon)
        if mi["alt"] > 0:
            x, y = project(mi["alt"], mi["az"])
            c.create_oval(x - 9, y - 9, x + 9, y + 9, fill="#e8e2c0", outline="#fff6c0")
            c.create_text(x + 13, y, text=f"Moon {mi['illum'] * 100:.0f}%", anchor="w", fill="#f2ecc8", font=("Segoe UI", 9, "bold"))
        if sun_alt > -10:
            x, y = project(max(sun_alt, 0), sun_az)
            if sun_alt > 0:
                c.create_oval(x - 9, y - 9, x + 9, y + 9, fill="#ffd34a", outline="")
                c.create_text(x + 13, y, text="Sun: never view without a solar filter", anchor="w", fill="#ffe08a", font=("Segoe UI", 8))

        tz = timezone(timedelta(seconds=off))
        self.lbl_skytime.configure(text=datetime.fromtimestamp(ts, tz).strftime("%a %d %b  %H:%M"))
        self.lbl_skyinfo.configure(text=f"sun {sun_alt:+.0f} deg   Moon {mi['alt']:+.0f} deg, {mi['illum'] * 100:.0f}% lit   "
                                        "green=easy yellow=moderate orange=hard in your scope")

        if not table:
            return
        visible = [r for r in rows if r["alt"] >= 10 and r["rating"] != "Beyond"]
        order = {"Easy": 0, "Moderate": 1, "Hard": 2}
        visible.sort(key=lambda r: (order[r["rating"]], r["obj"]["mag"]))
        lines = [f"{'Object':<10}{'Name':<22}{'Mag':>5}{'Alt':>5}{'Az':>5}{'Moon':>11}  {'Rating':<9}View"]
        for r in visible[:40]:
            o = r["obj"]
            combo = r["combo"]
            moon = f"{r['sep']:.0f}d/-{r['drop']:.1f}m" if r["drop"] > 0.05 else "-"
            lines.append(f"{o['id'][:9]:<10}{o['name'][:21]:<22}{o['mag']:>5.1f}{r['alt']:>4.0f}d{r['az']:>4.0f}d{moon:>11}  {r['rating']:<9}"
                         + (f"{combo['mag']:.0f}x" if combo else ""))
        lines.append("")
        lines.append("Moon column: separation from the Moon / sky-limit magnitudes lost to its glare.")
        lines.append("")
        lines.append("Planets now:")
        for name, st, alt, az in planet_list:
            lines.append(f"  {name:<9} mag {st['mag']:>5.1f}   {fmt_angle(st['diam']):>10}   alt {alt:>4.0f}d  az {az:>4.0f}d" + ("" if alt > 0 else "   (below horizon)"))
        self.set_text(self.box_sky, "\n".join(lines))

    # ========================================================== TELESCOPE PAGE
    def build_scope(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        tabs = ctk.CTkTabview(page)
        tabs.grid(row=0, column=0, sticky="nsew", padx=20, pady=(0, 14))
        for name in ("Your setup", "Calculators", "Camera"):
            tabs.add(name)
        # ---- setup
        t = ctk.CTkScrollableFrame(tabs.tab("Your setup"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Optics")
        self.out["specs"] = ctk.CTkLabel(c, text="", font=self.f_mono, justify="left", anchor="w")
        self.out["specs"].pack(anchor="w", padx=16, pady=(0, 12))
        c = self.card(t, "Eyepiece and Barlow combinations")
        self.box_combos = ctk.CTkTextbox(c, height=330, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_combos.pack(fill="x", padx=14, pady=(0, 14))
        # ---- calculators
        t = ctk.CTkScrollableFrame(tabs.tab("Calculators"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Magnification, exit pupil and field of view")
        self.entry_row(c, "ep_fl", "Eyepiece focal length (mm)", 12.5)
        self.entry_row(c, "ep_afov", "Eyepiece apparent FOV (deg)", 35)
        self.entry_row(c, "ep_barlow", "Barlow factor (1 = none)", 1)
        self.out_label(c, "mag")
        c = self.card(t, "Will it fit? (target size vs. true field)")
        self.entry_row(c, "fit_size", "Target size (arcmin)", 30)
        self.out_label(c, "fit")
        c = self.card(t, "Angles and arcs")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Convert an angle", width=190, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=80, font=self.f_ui)
        e.insert(0, "1")
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent["ang_val"] = e
        om = ctk.CTkOptionMenu(row, values=["degrees", "arcminutes", "arcseconds", "radians"], width=120,
                               command=lambda v: self.update_calcs())
        om.set("degrees")
        om.pack(side="left", padx=8)
        self.opt["ang_unit"] = om
        self.out_label(c, "ang")
        self.entry_row(c, "phys_size", "Real size of object (km)", 100)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Distance (km)", width=190, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=110, font=self.f_ui)
        e.insert(0, "384400")
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent["phys_dist"] = e
        ctk.CTkButton(row, text="Moon (now)", width=90, font=self.f_small, fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=self.preset_moon).pack(side="left", padx=8)
        self.out_label(c, "phys")
        c = self.card(t, "Resolution and splitting double stars")
        self.entry_row(c, "dbl_sep", "Double star separation (arcsec)", 4)
        self.entry_row(c, "feat", "Smallest feature to see (arcsec)", 2)
        self.out_label(c, "res")
        c = self.card(t, "Drift time (manual tracking on an AZ mount)")
        self.entry_row(c, "drift_dec", "Target declination (deg)", 0)
        self.out_label(c, "drift")
        # ---- camera
        t = ctk.CTkScrollableFrame(tabs.tab("Camera"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Imaging through the telescope")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Camera preset", width=230, anchor="w", font=self.f_ui).pack(side="left")
        om = ctk.CTkOptionMenu(row, values=list(PHONE_PRESETS), width=340, command=self.on_cam_preset)
        om.set(self.cfg.get("camera", {}).get("preset", "Custom"))
        om.pack(side="left")
        self.opt["cam_preset"] = om
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Mode", width=230, anchor="w", font=self.f_ui).pack(side="left")
        om = ctk.CTkOptionMenu(row, values=CAM_MODES, width=340, command=lambda v: self.update_calcs())
        om.set(CAM_MODES[0])
        om.pack(side="left")
        self.opt["cam_mode"] = om
        self.cam_note = ctk.CTkLabel(c, text="", font=self.f_small, text_color="#8a93a6", anchor="w", justify="left", wraplength=760)
        self.cam_note.pack(anchor="w", padx=16, pady=(2, 4))
        self.entry_row(c, "cam_pix", "Pixel size (um)", 3.75)
        self.entry_row(c, "cam_w", "Sensor width (pixels)", 1280)
        self.entry_row(c, "cam_h", "Sensor height (pixels)", 960)
        self.entry_row(c, "cam_lens", "Camera / phone lens focal length (mm)", 6.8)
        self.entry_row(c, "cam_fno", "Lens f-number", 1.8)
        self.entry_row(c, "cam_ep", "Eyepiece used for afocal (mm)", 20)
        self.entry_row(c, "cam_barlow", "Barlow / reducer factor", 1)
        self.entry_row(c, "cam_seeing", "Seeing FWHM (arcsec)", 2.5)
        self.entry_row(c, "cam_dec", "Target declination (deg)", 0)
        self.out_label(c, "cam")
        if self.cfg.get("camera", {}).get("preset", "Custom") != "Custom":
            self.apply_cam_preset(self.cfg["camera"]["preset"])

    def entry_row(self, parent, key, label, default, width=90):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text=label, width=230, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=width, font=self.f_ui)
        e.insert(0, str(default))
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent[key] = e
        return e

    def out_label(self, parent, key):
        lbl = ctk.CTkLabel(parent, text="", font=self.f_mono, justify="left", anchor="w")
        lbl.pack(anchor="w", padx=16, pady=(6, 12))
        self.out[key] = lbl

    def num(self, key, default=None):
        try:
            return float(str(self.ent[key].get()).strip().replace(",", "."))
        except (ValueError, TypeError, KeyError):
            return default

    def apply_cam_preset(self, name):
        p = PHONE_PRESETS.get(name)
        if p:
            for key, val in (("cam_pix", p["pix"]), ("cam_w", p["w"]), ("cam_h", p["h"]), ("cam_lens", p["lens"]), ("cam_fno", p["fno"])):
                self.ent[key].delete(0, "end")
                self.ent[key].insert(0, f"{val:g}")
            self.opt["cam_mode"].set(CAM_MODES[1])  # phones are used behind an eyepiece
        self.cam_note.configure(text=(p["note"] + "  (focal lengths are derived from Apple's 35 mm equivalents: edit if you know better)") if p else "")

    def on_cam_preset(self, name):
        self.apply_cam_preset(name)
        self.cfg.setdefault("camera", {})["preset"] = name
        save_config(self.cfg)
        self.update_calcs()

    def eyepiece_afov(self, fl_mm):
        best = min(self.cfg["eyepieces"], key=lambda e: abs(float(e["fl"]) - fl_mm), default=None)
        return float(best["afov"]) if best and abs(float(best["fl"]) - fl_mm) < 1.0 else 35.0

    def preset_moon(self):
        dist = self.analysis["moon"]["now"]["dist_km"] if self.analysis else moon_info(time.time(), 0, 0)["dist_km"]
        self.ent["phys_dist"].delete(0, "end")
        self.ent["phys_dist"].insert(0, f"{dist:.0f}")
        self.update_calcs()

    def schedule_calcs(self):
        if self._calc_job:
            self.after_cancel(self._calc_job)
        self._calc_job = self.after(120, self._run_calcs)

    def _run_calcs(self):
        self._calc_job = None
        self.update_calcs()

    def update_calcs(self):
        cfg = self.cfg
        nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
        try:
            sn = scope_numbers(cfg["scope"], nelm)
        except Exception:
            return
        ap, fl = sn["ap"], sn["fl"]
        obs_txt = f"  (secondary shadow {sn['obs']:.0f} mm, effective {sn['ap_eff']:.0f} mm)" if sn["obs"] else ""
        self.out["specs"].configure(text="\n".join([
            f"{cfg['scope'].get('name', 'Scope')}:  {ap:.0f} mm aperture, {fl:.0f} mm focal length, f/{sn['f']:.1f}, {cfg['scope'].get('mount', '')} mount{obs_txt}",
            f"Light grasp:       {sn['gather']:.0f}x the dark-adapted eye (7 mm pupil)",
            f"Limiting magnitude about {sn['lim']:.1f} at your sky (Bortle {cfg['bortle']}, naked eye {nelm:.1f}), {sn['lim_ideal']:.1f} under a perfect sky",
            f"Resolution:        Dawes {sn['dawes']:.2f} arcsec,  Rayleigh {sn['rayleigh']:.2f} arcsec,  Airy disk {sn['airy'] * 1000:.1f} um at focus",
            f"Magnification:     min {sn['min_mag']:.0f}x (7 mm pupil),  comfortable up to {sn['comfort']:.0f}x,  practical max {sn['max_mag']:.0f}x (2x aperture in mm)",
            f"Image scale:       {sn['scale_mm']:.1f} arcsec per mm at the focal plane;  the Moon is {sn['moon_mm']:.2f} mm wide at prime focus",
        ]))
        combos = build_combos(cfg["scope"], cfg["eyepieces"], cfg["barlows"])
        lines = [f"{'Combination':<26}{'Mag':>6}{'Exit pupil':>12}{'True field':>13}   Good for"]
        for cb in combos:
            lines.append(f"{cb['label']:<26}{cb['mag']:>5.0f}x{cb['pupil']:>9.2f} mm{cb['tfov']:>9.2f} deg   {quality_note(cb['mag'], cb['pupil'], ap)}")
        lines.append("")
        lines.append("True field = apparent FOV / magnification. Stock 0.965 inch eyepieces often have narrower real fields than their label.")
        self.set_text(self.box_combos, "\n".join(lines))

        # magnification card
        efl, afov, bl = self.num("ep_fl"), self.num("ep_afov"), self.num("ep_barlow", 1.0)
        tfov_deg = None
        if efl and efl > 0 and afov and afov > 0 and bl and bl > 0:
            mag = fl * bl / efl
            pupil = ap / mag
            tfov_deg = afov / mag
            self.out["mag"].configure(text="\n".join([
                f"Magnification:  {mag:.1f}x   ({mag / sn['max_mag'] * 100:.0f}% of the practical maximum)",
                f"Exit pupil:     {pupil:.2f} mm   -> {quality_note(mag, pupil, ap)}",
                f"True field:     {tfov_deg:.2f} deg  =  {tfov_deg * 60:.0f} arcmin   (Moon is 31 arcmin wide)",
                f"Effective f/:   f/{sn['f'] * bl:.1f}   focal length {fl * bl:.0f} mm",
            ]))
        else:
            self.out["mag"].configure(text="Enter positive numbers.")

        size = self.num("fit_size")
        if size and size > 0:
            lines = []
            for cb in combos:
                tf = cb["tfov"] * 60.0
                pct = size / tf * 100.0
                verdict_txt = "fits" if pct <= 90 else "too big"
                lines.append(f"{cb['label']:<26} field {tf:>5.0f}'   target fills {pct:>4.0f}%   {verdict_txt}")
            self.out["fit"].configure(text="\n".join(lines))
        else:
            self.out["fit"].configure(text="Enter a size in arcmin.")

        v = self.num("ang_val")
        unit = self.opt["ang_unit"].get()
        if v is not None:
            arcsec = v * {"degrees": 3600.0, "arcminutes": 60.0, "arcseconds": 1.0, "radians": 206264.806}.get(unit, 1.0)
            self.out["ang"].configure(text=f"= {arcsec / 3600.0:.6g} deg  =  {arcsec / 60.0:.6g} arcmin  =  {arcsec:.6g} arcsec  =  {arcsec / 206264.806:.6g} rad")
        else:
            self.out["ang"].configure(text="")
        size_km, dist_km = self.num("phys_size"), self.num("phys_dist")
        if size_km and dist_km and size_km > 0 and dist_km > 0:
            ang = 206264.806 * size_km / dist_km
            extra = ""
            if tfov_deg:
                extra = f"\nIn the eyepiece above it fills {ang / 3600.0 / tfov_deg * 100:.1f}% of the field, and looks {ang * (fl * bl / efl) / 3600.0:.2f} deg wide to your eye."
            self.out["phys"].configure(text=f"Angular size: {fmt_angle(ang)}   ({ang:.3g} arcsec)\n"
                                            f"Magnification so the eye sees it as 1 arcmin (barely resolved): {60.0 / ang:.0f}x   "
                                            f"for a comfortable 2 arcmin: {120.0 / ang:.0f}x{extra}")
        else:
            self.out["phys"].configure(text="")
        sep, feat = self.num("dbl_sep"), self.num("feat")
        res = [f"Aperture limits: Dawes {sn['dawes']:.2f}\"  Rayleigh {sn['rayleigh']:.2f}\"  (nothing finer, whatever the magnification)"]
        if sep and sep > 0:
            if sep < sn["dawes"] * 0.9:
                res.append(f"A {sep:.1f}\" pair is below Dawes limit: you will not split it with {ap:.0f} mm.")
            else:
                res.append(f"A {sep:.1f}\" pair can be split. Use at least about {120.0 / sep:.0f}x" +
                           (" (and steady air)." if sep < sn["dawes"] * 2 else "."))
        if feat and feat > 0:
            if feat < sn["dawes"]:
                res.append(f"A {feat:.1f}\" feature is finer than the Dawes limit: not resolvable.")
            else:
                res.append(f"A {feat:.1f}\" feature needs about {120.0 / feat:.0f}x to be comfortable (barely visible at {60.0 / feat:.0f}x).")
        self.out["res"].configure(text="\n".join(res))
        dec = self.num("drift_dec", 0.0)
        if tfov_deg:
            full = drift_seconds(tfov_deg, dec)
            self.out["drift"].configure(text=f"With the eyepiece above ({tfov_deg:.2f} deg field):\n"
                                             f"edge to edge: {full:.0f} s ({full / 60:.1f} min).  Re-centre every {full / 2:.0f} s ({full / 120:.1f} min) to stay in the middle half.\n"
                                             f"At {mag:.0f}x a star leaves the field in about {full:.0f} s: higher power means more nudging.")
        else:
            self.out["drift"].configure(text="Fill in the eyepiece above first.")

        pix, w, h = self.num("cam_pix"), self.num("cam_w"), self.num("cam_h")
        cb, fwhm, cdec = self.num("cam_barlow", 1.0), self.num("cam_seeing", 2.5), self.num("cam_dec", 0.0)
        lens, fno, epf = self.num("cam_lens"), self.num("cam_fno"), self.num("cam_ep")
        afocal = self.opt["cam_mode"].get() == CAM_MODES[1]
        ok = pix and w and h and cb and fwhm and pix > 0 and cb > 0 and w > 0 and h > 0
        if ok and afocal:
            ok = bool(lens and epf and lens > 0 and epf > 0)
        if ok:
            efl = fl * cb * lens / epf if afocal else fl * cb  # afocal: telescope x (phone lens / eyepiece)
            cn = camera_numbers(efl, ap, pix, w, h, fwhm, cdec)
            samp = "oversampled (a shorter focal length or 2x2 binning would lose nothing)" if cn["sampling"] > 3.5 else \
                "well sampled" if cn["sampling"] >= 2 else "undersampled (add a Barlow if seeing allows)"
            moon_px = 1872.0 / cn["scale"]
            lines = [
                f"Effective:       {efl:.0f} mm,  f/{cn['n']:.1f}" + ("   (telescope x phone lens / eyepiece)" if afocal else ""),
                f"Image scale:     {cn['scale']:.2f} arcsec per pixel",
                f"Field of view:   {cn['fov_w']:.2f} x {cn['fov_h']:.2f} deg  ({cn['fov_w'] * 60:.0f}' x {cn['fov_h'] * 60:.0f}')",
                f"Sampling:        {cn['sampling']:.1f} pixels per seeing FWHM -> {samp}",
                f"Moon (31'):      {moon_px:.0f} px across  ({moon_px / w * 100:.0f}% of the frame width)",
                f"Jupiter (45\"):   about {45.0 / cn['scale']:.0f} px across",
                f"Ideal f-ratio:   about f/{cn['ideal_lo']:.0f} to f/{cn['ideal_hi']:.0f} for planets with this pixel size",
                f"Longest exposure without star trails on a fixed mount:  {cn['npf']:.2f} s (NPF rule), {cn['rule500']:.2f} s (500 rule)",
                "On an AZ mount, long exposures also suffer field rotation: use short frames and stack them.",
            ]
            if afocal:
                mag_ep = fl * cb / epf
                exit_pupil = ap / mag_ep
                tf = self.eyepiece_afov(epf) / mag_ep
                lines.append("")
                lines.append(f"Afocal setup:    {epf:g} mm eyepiece = {mag_ep:.0f}x, true field {tf:.2f} deg, exit pupil {exit_pupil:.1f} mm")
                if tf < cn["fov_w"]:
                    lines.append(f"Framing:         the eyepiece circle fills only {tf / cn['fov_w'] * 100:.0f}% of the frame width: zoom the phone about "
                                 f"{cn['fov_w'] / tf:.1f}x (or crop) to remove the black ring")
                else:
                    lines.append("Framing:         the frame is smaller than the eyepiece field, so nothing is wasted")
                if fno and fno > 0:
                    entrance = lens / fno
                    lines.append(f"Light match:     phone lens opening about {entrance:.1f} mm vs exit pupil {exit_pupil:.1f} mm -> " +
                                 ("corners will vignette: use a higher-power eyepiece" if exit_pupil > entrance else "all the light enters the lens"))
            self.out["cam"].configure(text="\n".join(lines))
        else:
            self.out["cam"].configure(text="Fill in the camera numbers." if not afocal else "Fill in the camera numbers, the phone lens and the eyepiece.")

    # ============================================================== PLANNER PAGE
    def build_planner(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctrl = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        ctrl.grid(row=0, column=0, sticky="ew", padx=24, pady=(0, 8))
        r1 = ctk.CTkFrame(ctrl, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(r1, text="From", font=self.f_ui).pack(side="left")
        self.plan_from = ctk.CTkEntry(r1, width=140, font=self.f_ui)
        self.plan_from.pack(side="left", padx=(6, 12))
        ctk.CTkLabel(r1, text="To", font=self.f_ui).pack(side="left")
        self.plan_to = ctk.CTkEntry(r1, width=140, font=self.f_ui)
        self.plan_to.pack(side="left", padx=(6, 12))
        for text, key in (("Tonight", "tonight"), ("Tomorrow night", "tomorrow"), ("Next 3 nights", "3nights"), ("Whole forecast", "all")):
            ctk.CTkButton(r1, text=text, width=100, height=28, font=self.f_small, fg_color="#2b2b2b", hover_color="#3a3a3a",
                          command=lambda k=key: self.plan_preset(k)).pack(side="left", padx=3)
        r2 = ctk.CTkFrame(ctrl, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(2, 10))
        ctk.CTkLabel(r2, text="Min altitude (deg)", font=self.f_ui).pack(side="left")
        self.plan_minalt = ctk.CTkEntry(r2, width=55, font=self.f_ui)
        self.plan_minalt.insert(0, str(self.cfg.get("planner", {}).get("min_alt", 30)))
        self.plan_minalt.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(r2, text="Show", font=self.f_ui).pack(side="left")
        self.plan_kind = ctk.CTkOptionMenu(r2, values=list(PLAN_KINDS), width=150)
        self.plan_kind.set(self.cfg.get("planner", {}).get("kind", "All targets"))
        self.plan_kind.pack(side="left", padx=(6, 14))
        self.btn_plan = ctk.CTkButton(r2, text="Plan", width=90, font=self.f_ui, command=self.run_plan)
        self.btn_plan.pack(side="left")
        self.plan_status = ctk.CTkLabel(r2, text="Local time, format YYYY-MM-DD HH:MM", font=self.f_small, text_color="#8a93a6")
        self.plan_status.pack(side="left", padx=14)

        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=6)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text=f"{' #':<4}{'Target':<21}{'Score':>5}{'Peak':>5}  Best", font=self.f_mono_s, anchor="w",
                     text_color="#8a93a6").grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        self.plan_list = ctk.CTkScrollableFrame(left, fg_color=DEEP, width=380)
        self.plan_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=6)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        self.box_plan = ctk.CTkTextbox(right, height=250, font=self.f_mono_s, fg_color=DEEP, state="disabled", wrap="word")
        self.box_plan.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        tools = ctk.CTkFrame(right, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(tools, text="Altitude graph:", font=self.f_small, text_color="#8a93a6").pack(side="left")
        for text, key in (("Top 5", "top"), ("Planets", "planets"), ("Clear", "clear")):
            ctk.CTkButton(tools, text=text, width=70, height=26, font=self.f_small, fg_color="#2b2b2b", hover_color="#3a3a3a",
                          command=lambda k=key: self.plot_preset(k)).pack(side="left", padx=4)
        ctk.CTkLabel(tools, text="click a target to add/remove it", font=self.f_small, text_color="#6b7390").pack(side="left", padx=8)
        self.alt_canvas = tk.Canvas(right, width=ALT_W, height=ALT_H, bg="#0b1020", highlightthickness=0)
        self.alt_canvas.grid(row=2, column=0, sticky="n", pady=(4, 0))
        self.alt_canvas.bind("<Motion>", self.on_alt_motion)
        self.draw_alt_graph()

    def plan_page_refresh(self):
        if self.analysis and not self.plan_from.get().strip():
            self.plan_preset("tonight")
        self.draw_alt_graph()

    def plan_preset(self, key):
        a = self.analysis
        if not a:
            return
        win = a["tonight"]["win"]
        if key == "tonight":
            t0, t1 = win["start"], win["end"]
        elif key == "tomorrow":
            t0, t1 = win["start"] + 86400, win["end"] + 86400
        elif key == "3nights":
            t0, t1 = win["start"], win["end"] + 2 * 86400
        else:
            t0, t1 = a["hours"][0]["ts"], a["hours"][-1]["ts"]
        tz = timezone(timedelta(seconds=a["offset"]))
        for entry, t in ((self.plan_from, t0), (self.plan_to, t1)):
            entry.delete(0, "end")
            entry.insert(0, datetime.fromtimestamp(t, tz).strftime("%Y-%m-%d %H:%M"))

    def run_plan(self):
        a = self.analysis
        if not a:
            self.plan_status.configure(text="Waiting for the forecast...")
            return
        if not HAVE_NUMPY:
            messagebox.showerror("AstroWeather", "The planner needs NumPy:  pip install numpy")
            return
        if self.plan_busy:
            return
        try:
            tz = timezone(timedelta(seconds=a["offset"]))
            parse = lambda e: datetime.strptime(e.get().strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz).timestamp()
            t0, t1 = parse(self.plan_from), parse(self.plan_to)
            min_alt = float(self.plan_minalt.get())
            if not (0 <= min_alt <= 80) or t1 <= t0:
                raise ValueError
        except ValueError:
            messagebox.showerror("AstroWeather", "Use  YYYY-MM-DD HH:MM  for both times (To after From) and a minimum altitude of 0-80.")
            return
        kind = self.plan_kind.get()
        self.cfg.setdefault("planner", {}).update({"min_alt": min_alt, "kind": kind})
        save_config(self.cfg)
        self.plan_busy = True
        self.plan_req += 1
        self.btn_plan.configure(state="disabled")
        self.plan_status.configure(text="computing...")
        threading.Thread(target=self.planner_worker, args=(self.plan_req, t0, t1, a["hours"], copy.deepcopy(self.cfg), a["offset"],
                                                           min_alt, kind, a.get("elevation") or 0.0), daemon=True).start()

    def planner_worker(self, req, t0, t1, hours, cfg, off, min_alt, kind, elev):
        try:
            res = run_planner(t0, t1, hours, cfg, off, min_alt, 600.0, elev, PLAN_KINDS.get(kind))
            self.events.put(("plan", req, res))
        except Exception as e:
            log_error(traceback.format_exc())
            self.events.put(("plan_error", req, f"{type(e).__name__}: {e}"))

    def show_plan(self, res):
        self.plan = res
        self.plot_set = [r["ti"] for r in res["rows"][:3]]
        self.plan_sel = 0 if res["rows"] else None
        txt = (f"{len(res['rows'])} ranked, {res['hidden']} never observable | {res['engine']}: {res['t_total_ms']:.0f} ms "
               f"({res['t_pos_ms']:.0f} ms positions, {len(res['ts'])} time steps)")
        if res["note"]:
            txt += " | " + res["note"]
        self.plan_status.configure(text=txt[:170])
        self.refresh_plan_list()
        self.show_plan_detail()
        self.draw_alt_graph()

    def refresh_plan_list(self):
        for w in self.plan_list.winfo_children():
            w.destroy()
        if not self.plan:
            return
        off = self.plan["offset"]
        for k, r in enumerate(self.plan["rows"][:60]):
            mark = "●" if r["ti"] in self.plot_set else " "
            label = f"{r['id']} {r['name']}".strip()[:20]
            text = f"{mark}{k + 1:>2} {label:<20}{r['score']:>5.0f}{r['peak_alt']:>4.0f}d {fmt_clock(r['best_ts'], off)}"
            ctk.CTkButton(self.plan_list, text=text, anchor="w", height=26, font=self.f_mono_s,
                          fg_color="#26324a" if k == self.plan_sel else "transparent", hover_color="#232a36",
                          text_color=score_color(r["score"]), command=lambda i=k: self.select_plan(i)).pack(fill="x", pady=1)
        if not self.plan["rows"]:
            ctk.CTkLabel(self.plan_list, text="Nothing reaches the minimum altitude in a dark enough sky.\nTry a lower altitude or a longer range.",
                         font=self.f_small, text_color="#8a93a6").pack(pady=20)

    def select_plan(self, i):
        ti = self.plan["rows"][i]["ti"]
        if self.plan_sel == i and ti in self.plot_set:
            self.plot_set.remove(ti)
        else:
            self.plan_sel = i
            if ti not in self.plot_set:
                self.plot_set.append(ti)
                if len(self.plot_set) > len(ALT_COLORS):
                    self.plot_set.pop(0)
        self.refresh_plan_list()
        self.show_plan_detail()
        self.draw_alt_graph()

    def show_plan_detail(self):
        if not self.plan or self.plan_sel is None or self.plan_sel >= len(self.plan["rows"]):
            self.set_text(self.box_plan, "Pick a time range and press Plan.\n\nEach target gets a score from altitude, how detectable it is in your "
                                         "scope, the weather at its best moment, and Moon glare (phase, height and distance from the target).")
            return
        r, off = self.plan["rows"][self.plan_sel], self.plan["offset"]
        ap = float(self.cfg["scope"]["aperture"])
        kind = KIND_NAMES.get(r["kind"], "Planet" if r["kind"] == "PL" else "Moon")
        sym = {"good": "+", "info": "-", "warn": "!", "bad": "x"}
        lines = [f"{r['id']}  {r['name']}   [{kind}]",
                 f"Score {r['score']:.0f}/100    best at {fmt_clock(r['best_ts'], off)}    {r['rating']} in {ap:.0f} mm", ""]
        lines += [f"{sym[lv]} {tx}" for lv, tx in r["reasons"]]
        v = r["view"]
        if v:
            lines += ["", f"Eyepiece: {v['label']} = {v['mag']:.0f}x, {v['tfov'] * 60:.0f}' field, exit pupil {v['pupil']:.1f} mm",
                      f"Why: {r['view_why']}."]
        p = r["parts"]
        lines += ["", f"Score parts at the best moment: altitude {p['altitude']:.0f}, detectability {p['detectability']:.0f}, "
                      f"conditions {p['conditions']:.0f}, Moon {p['moon']:.0f}, weather factor {r['gate'] * 100:.0f}%"]
        self.set_text(self.box_plan, "\n".join(lines))

    def plot_preset(self, which):
        if not self.plan:
            return
        if which == "top":
            self.plot_set = [r["ti"] for r in self.plan["rows"][:5]]
        elif which == "planets":
            self.plot_set = [i for i, o in enumerate(self.plan["targets"]) if o["kind"] == "PL"]
        else:
            self.plot_set = []
        self.refresh_plan_list()
        self.draw_alt_graph()

    def draw_alt_graph(self):
        c = self.alt_canvas
        c.delete("all")
        W, H, L, R, T, B = ALT_W, ALT_H, 40, 10, 12, 30
        res = self.plan
        if not res:
            c.create_text(W / 2, H / 2, text="Run the planner, then click targets to plot their altitude", fill="#6b7390", font=("Segoe UI", 10))
            self.alt_geom = None
            return
        ts = res["ts"].tolist()
        t0, t1 = ts[0], ts[-1]
        X = lambda t: L + (t - t0) / (t1 - t0) * (W - L - R)
        Y = lambda a: T + (90.0 - a) / 90.0 * (H - T - B)
        sun = res["sun_alt"].tolist()
        cls = [0 if v > -0.833 else 1 if v > -6 else 2 if v > -12 else 3 if v > -18 else 4 for v in sun]
        start = 0
        for k in range(1, len(cls) + 1):
            if k == len(cls) or cls[k] != cls[start]:
                c.create_rectangle(X(ts[start]), T, X(ts[min(k, len(ts) - 1)]), H - B, fill=ALT_BANDS[cls[start]], outline="")
                start = k
        for a in (0, 30, 60, 90):
            c.create_line(L, Y(a), W - R, Y(a), fill="#2a3558")
            c.create_text(L - 5, Y(a), text=f"{a}", anchor="e", fill="#8fa3c8", font=("Segoe UI", 8))
        ma = res["min_alt"]
        c.create_line(L, Y(ma), W - R, Y(ma), fill="#e0b84c", dash=(3, 3))
        span_h = (t1 - t0) / 3600.0
        step_h = 1 if span_h <= 10 else 2 if span_h <= 20 else 3 if span_h <= 36 else 6 if span_h <= 80 else 12
        tz = timezone(timedelta(seconds=res["offset"]))
        tick = datetime.fromtimestamp(t0, tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while tick.hour % step_h:
            tick += timedelta(hours=1)
        tt = tick.timestamp()
        while tt < t1:
            dt = datetime.fromtimestamp(tt, tz)
            c.create_line(X(tt), T, X(tt), H - B, fill="#1f2a4a")
            c.create_text(X(tt), H - B + 10, text=f"{dt.hour:02d}", fill="#cfd6e4", font=("Segoe UI", 8))
            if dt.hour == 0:
                c.create_text(X(tt), H - 8, text=dt.strftime("%a %d %b"), fill="#8fa3c8", font=("Segoe UI", 8, "bold"))
            tt += step_h * 3600

        def runs(arr):
            cur = []
            for k, a in enumerate(arr):
                if a >= 0:
                    cur.append((X(ts[k]), Y(a)))
                else:
                    if len(cur) > 1:
                        yield cur
                    cur = []
            if len(cur) > 1:
                yield cur
        for pts in runs(res["moon_alt"].tolist()):
            c.create_line(*[v for xy in pts for v in xy], fill="#d8d2a8", dash=(5, 4), width=1)
        legend_x = L + 6
        for n, ti in enumerate(self.plot_set):
            col = ALT_COLORS[n % len(ALT_COLORS)]
            for pts in runs(res["alt"][ti].tolist()):
                c.create_line(*[v for xy in pts for v in xy], fill=col, width=2)
            o = res["targets"][ti]
            label = o["id"]
            c.create_text(legend_x, T + 24, text=label, anchor="w", fill=col, font=("Segoe UI", 9, "bold"))
            legend_x += 8 + 7 * len(label)
        c.create_text(W - R - 4, T + 8, text="Moon (dashed)", anchor="e", fill="#d8d2a8", font=("Segoe UI", 8))
        now = res.get("now") or time.time()
        if t0 <= now <= t1:
            c.create_line(X(now), T, X(now), H - B, fill="#5ec8ff", width=2)
        self.alt_geom = (t0, t1, L, R, W, T, H, B)

    def on_alt_motion(self, event):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        t0, t1, L, R, W, T, H, B = g
        c = self.alt_canvas
        c.delete("cross")
        if not (L <= event.x <= W - R):
            return
        ts = self.plan["ts"]
        k = max(0, min(len(ts) - 1, int(round((event.x - L) / (W - L - R) * (len(ts) - 1)))))
        c.create_line(event.x, T, event.x, H - B, fill="#ffffff", dash=(2, 2), tags="cross")
        parts = [fmt_clock(float(ts[k]), self.plan["offset"])]
        for ti in self.plot_set[:6]:
            parts.append(f"{self.plan['targets'][ti]['id']} {self.plan['alt'][ti][k]:.0f}d")
        parts.append(f"Moon {self.plan['moon_alt'][k]:.0f}d")
        c.create_text(L + 6, T + 8, text="   ".join(parts), anchor="w", fill="#e8eefc", font=("Segoe UI", 8, "bold"), tags="cross")

    # ============================================================ SETTINGS PAGE
    def build_settings(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=18, pady=(0, 14))
        c = self.card(body, "Location")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        self.search_entry = ctk.CTkEntry(row, width=300, placeholder_text="Search a city or town", font=self.f_ui)
        self.search_entry.pack(side="left")
        ctk.CTkButton(row, text="Search", width=80, font=self.f_ui, command=self.do_search).pack(side="left", padx=8)
        self.geo_status = ctk.CTkLabel(row, text="", font=self.f_small, text_color="#8a93a6")
        self.geo_status.pack(side="left", padx=8)
        self.geo_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.geo_frame.pack(fill="x", padx=16, pady=4)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 12))
        loc = self.cfg["location"]
        self.ent_lat = ctk.CTkEntry(row, width=110, font=self.f_ui)
        self.ent_lat.insert(0, f"{loc['lat']:.4f}")
        self.ent_lon = ctk.CTkEntry(row, width=110, font=self.f_ui)
        self.ent_lon.insert(0, f"{loc['lon']:.4f}")
        ctk.CTkLabel(row, text="Latitude", font=self.f_ui).pack(side="left")
        self.ent_lat.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(row, text="Longitude", font=self.f_ui).pack(side="left")
        self.ent_lon.pack(side="left", padx=(6, 14))
        ctk.CTkButton(row, text="Use these coordinates", width=170, font=self.f_ui, command=self.use_coords).pack(side="left")

        c = self.card(body, "Sky and units")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 12))
        ctk.CTkLabel(row, text="Bortle class (light pollution)", font=self.f_ui).pack(side="left")
        self.opt_bortle = ctk.CTkOptionMenu(row, values=[str(i) for i in range(1, 10)], width=70, command=self.on_bortle)
        self.opt_bortle.set(str(self.cfg["bortle"]))
        self.opt_bortle.pack(side="left", padx=(8, 24))
        ctk.CTkLabel(row, text="Temperature", font=self.f_ui).pack(side="left")
        self.opt_temp = ctk.CTkOptionMenu(row, values=["C", "F"], width=70, command=self.on_units)
        self.opt_temp.set(self.cfg["units"]["temp"])
        self.opt_temp.pack(side="left", padx=(8, 24))
        ctk.CTkLabel(row, text="Wind", font=self.f_ui).pack(side="left")
        self.opt_wind = ctk.CTkOptionMenu(row, values=["km/h", "m/s", "mph"], width=80, command=self.on_units)
        self.opt_wind.set(self.cfg["units"]["wind"])
        self.opt_wind.pack(side="left", padx=8)

        c = self.card(body, "Performance")
        self.var_np = ctk.BooleanVar(value=bool(self.cfg["perf"].get("numpy", True)) and HAVE_NUMPY)
        self.var_ap = ctk.BooleanVar(value=bool(self.cfg["perf"].get("astropy", False)) and HAVE_ASTROPY)
        sw = ctk.CTkSwitch(c, text="Hardware-accelerated math (NumPy vector engine, uses your CPU's SIMD units)", variable=self.var_np, command=self.on_perf, font=self.f_ui)
        sw.pack(anchor="w", padx=16, pady=(2, 4))
        if not HAVE_NUMPY:
            sw.configure(state="disabled", text="Hardware-accelerated math: needs  pip install numpy")
        sw2 = ctk.CTkSwitch(c, text="High-precision positions (Astropy, optional: Moon to arcseconds, refraction)", variable=self.var_ap, command=self.on_perf, font=self.f_ui)
        sw2.pack(anchor="w", padx=16, pady=4)
        if not HAVE_ASTROPY:
            sw2.configure(state="disabled", text="High-precision positions: needs  pip install astropy")
        ctk.CTkLabel(c, text="No GPU is used: these arrays are far too small to benefit from one, and the speed-up comes from vectorised CPU math. "
                             "Switch it off to compare with the plain-Python engine.", font=self.f_small, text_color="#8a93a6", wraplength=860,
                     justify="left", anchor="w").pack(anchor="w", padx=16)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(6, 12))
        self.btn_engine = ctk.CTkButton(row, text="Run engine check", width=150, font=self.f_ui, command=self.run_engine_check)
        self.btn_engine.pack(side="left")
        self.lbl_engine = ctk.CTkLabel(row, text="", font=self.f_mono_s, justify="left", anchor="w")
        self.lbl_engine.pack(side="left", padx=14)

        c = self.card(body, "Your telescope")
        self.gear = {}
        sc = self.cfg["scope"]
        for key, label, val in (("name", "Name", sc.get("name", "")), ("aperture", "Aperture (mm)", sc["aperture"]),
                                ("focal_length", "Focal length (mm)", sc["focal_length"]),
                                ("obstruction_mm", "Secondary mirror shadow (mm, 0 if unknown)", sc.get("obstruction_mm", 0)),
                                ("mount", "Mount", sc.get("mount", "AZ"))):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row, text=label, width=330, anchor="w", font=self.f_ui).pack(side="left")
            e = ctk.CTkEntry(row, width=160, font=self.f_ui)
            e.insert(0, str(val))
            e.pack(side="left")
            self.gear[key] = e
        ctk.CTkLabel(c, text="Eyepieces, one per line:  name, focal length mm, apparent FOV deg", font=self.f_small,
                     text_color="#8a93a6").pack(anchor="w", padx=16, pady=(10, 0))
        self.box_eps = ctk.CTkTextbox(c, height=90, font=self.f_mono, fg_color=DEEP)
        self.box_eps.pack(fill="x", padx=16, pady=4)
        self.box_eps.insert("1.0", "\n".join(f"{e['name']}, {e['fl']:g}, {e['afov']:g}" for e in self.cfg["eyepieces"]))
        ctk.CTkLabel(c, text="Barlows / reducers, one per line:  name, factor", font=self.f_small, text_color="#8a93a6").pack(anchor="w", padx=16, pady=(6, 0))
        self.box_bl = ctk.CTkTextbox(c, height=64, font=self.f_mono, fg_color=DEEP)
        self.box_bl.pack(fill="x", padx=16, pady=4)
        self.box_bl.insert("1.0", "\n".join(f"{b['name']}, {b['factor']:g}" for b in self.cfg["barlows"]))
        ctk.CTkButton(c, text="Save gear", width=120, font=self.f_ui, command=self.save_gear).pack(anchor="w", padx=16, pady=(6, 14))

        c = self.card(body, "How the scores work")
        ctk.CTkLabel(c, justify="left", anchor="w", wraplength=900, font=self.f_small, text_color="#b6bfd1", text=(
            "Cloud cover (total, low, mid, high), rain chance, humidity, dew point, visibility, wind, gusts, CAPE and upper-air wind come from Open-Meteo. "
            "Aerosol depth and PM2.5 come from its air-quality feed.\n\n"
            "Transparency (0-100) starts at 100 and loses points for aerosols or PM2.5, humidity above 60%, and poor visibility.\n"
            "Seeing is a PROXY, not a measurement: it loses points for strong 250-300 hPa jet-stream wind, ground wind and gusts, fast temperature change, and convective energy (CAPE). "
            "The arcsec figure maps that score onto 0.8-4 arcsec. Real seeing can differ, especially from local heat sources and your own roof or tube currents.\n"
            "Deep-sky score = transparency 32%, Moon 30%, wind 14%, dew 12%, seeing 12%, then multiplied by a cloud and rain factor. "
            "Planetary score weights seeing 45% and ignores the Moon. Sun, Moon and planet positions are calculated on your PC "
            "(Moon accurate to about 0.3 deg, planets to a few arcminutes). Visibility ratings for deep-sky objects are rough estimates.\n\n"
            "Moon interference depends on the Moon's phase (a quarter Moon is roughly 10x fainter than a full one), its height, and how far it is from the target: "
            "scattered light peaks close to the Moon and bottoms out near 90 degrees away. The Planner combines altitude, detectability in your scope, weather, and Moon glare, "
            "weighted by object type (planets care about seeing, faint deep-sky objects about transparency and the Moon)."))\
            .pack(anchor="w", padx=16, pady=(0, 14))

    def on_perf(self):
        self.cfg["perf"] = {"numpy": bool(self.var_np.get()), "astropy": bool(self.var_ap.get())}
        apply_perf(self.cfg)
        save_config(self.cfg)
        if self.analysis:
            self.refresh(force=True)

    def run_engine_check(self):
        self.btn_engine.configure(state="disabled")
        self.lbl_engine.configure(text="measuring...")
        loc = self.cfg["location"]
        elev = (self.analysis or {}).get("elevation") or 0.0

        def work():
            try:
                self.events.put(("engine", engine_check(float(loc["lat"]), float(loc["lon"]), time.time(), elev)))
            except Exception as e:
                log_error(traceback.format_exc())
                self.events.put(("engine", f"check failed: {type(e).__name__}: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def do_search(self):
        name = self.search_entry.get().strip()
        if not name:
            return
        self.geo_status.configure(text="searching...")
        threading.Thread(target=self.geo_worker, args=(name,), daemon=True).start()

    def show_geo_results(self, results):
        for w in self.geo_frame.winfo_children():
            w.destroy()
        self.geo_status.configure(text="" if results else "no matches")
        for r in results:
            ctk.CTkButton(self.geo_frame, text=f"{r['name']}   ({r['lat']:.3f}, {r['lon']:.3f})", anchor="w", font=self.f_ui,
                          fg_color="#252a33", hover_color="#323946", height=30,
                          command=lambda r=r: self.set_location(r["name"], r["lat"], r["lon"])).pack(fill="x", pady=2)

    def set_location(self, name, lat, lon):
        self.cfg["location"] = {"name": name, "lat": float(lat), "lon": float(lon)}
        save_config(self.cfg)
        self.ent_lat.delete(0, "end")
        self.ent_lat.insert(0, f"{lat:.4f}")
        self.ent_lon.delete(0, "end")
        self.ent_lon.insert(0, f"{lon:.4f}")
        for w in self.geo_frame.winfo_children():
            w.destroy()
        self.update_location_label()
        self.analysis = None
        self.plan = None
        self.refresh(force=True)

    def use_coords(self):
        try:
            lat, lon = float(self.ent_lat.get()), float(self.ent_lon.get())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except ValueError:
            messagebox.showerror("AstroWeather", "Latitude must be -90..90 and longitude -180..180.")
            return
        self.set_location(f"{lat:.3f}, {lon:.3f}", lat, lon)

    def on_bortle(self, value):
        self.cfg["bortle"] = int(value)
        save_config(self.cfg)
        if self.analysis:
            self.refresh(force=True)
        self.update_calcs()

    def on_units(self, _value):
        self.cfg["units"] = {"temp": self.opt_temp.get(), "wind": self.opt_wind.get()}
        save_config(self.cfg)
        if self.analysis:
            self.fill_tonight()
            self.dirty.add("forecast")
            self.flush_dirty()

    def save_gear(self):
        try:
            sc = {"name": self.gear["name"].get().strip() or "Scope",
                  "aperture": float(self.gear["aperture"].get()), "focal_length": float(self.gear["focal_length"].get()),
                  "obstruction_mm": float(self.gear["obstruction_mm"].get() or 0), "mount": self.gear["mount"].get().strip() or "AZ"}
            if sc["aperture"] <= 0 or sc["focal_length"] <= 0 or sc["obstruction_mm"] < 0 or sc["obstruction_mm"] >= sc["aperture"]:
                raise ValueError("aperture / focal length / obstruction out of range")
            eps = []
            for line in self.box_eps.get("1.0", "end").splitlines():
                if line.strip():
                    n, f, a = [p.strip() for p in line.split(",")]
                    eps.append({"name": n, "fl": float(f), "afov": float(a)})
            bls = []
            for line in self.box_bl.get("1.0", "end").splitlines():
                if line.strip():
                    n, f = [p.strip() for p in line.split(",")]
                    bls.append({"name": n, "factor": float(f)})
            if not eps or any(e["fl"] <= 0 or e["afov"] <= 0 for e in eps) or any(b["factor"] <= 0 for b in bls):
                raise ValueError("need at least one eyepiece and only positive numbers")
        except Exception as e:
            messagebox.showerror("AstroWeather", f"Could not read the gear: {e}\nUse the format  name, number, number")
            return
        self.cfg["scope"], self.cfg["eyepieces"], self.cfg["barlows"] = sc, eps, bls
        save_config(self.cfg)
        self.update_calcs()
        if self.analysis:
            self.refresh(force=True)


def main():
    app = AstroApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error(traceback.format_exc())
        raise
