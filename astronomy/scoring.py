"""Observing-condition scoring: seeing, transparency, dew, wind, sky brightness (NELM) and Moon interference.

Stdlib only (depends on mathutil). No GUI presentation, no NumPy: the vectorised Moon-drop twin lives in
astro.numpy_engine, which imports MOON_K and ang_sep from here.
"""
import math

from mathutil import clamp, deg, piecewise, rad

BORTLE_NELM = {1: 7.6, 2: 7.1, 3: 6.6, 4: 6.2, 5: 5.6, 6: 5.1, 7: 4.6, 8: 4.3, 9: 4.0}


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
