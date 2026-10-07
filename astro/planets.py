"""Planets (pure Python): JPL approximate Keplerian elements, heliocentric state, geocentric planet_state,
and the generic rise/set crossing finder.

Depends only on astro.core and mathutil. No GUI, no NumPy.
"""
import math

from astro.core import AU_KM, precess
from mathutil import clamp, deg, rad

# JPL "Keplerian elements for approximate positions" (1800-2050): value, rate per century
PLANET_ELEMENTS = {
    "Mercury": ((0.38709927, 0.00000037), (0.20563593, 0.00001906), (7.00497902, -0.00594749),
                (252.25032350, 149472.67411175), (77.45779628, 0.16047689), (48.33076593, -0.12534081)),
    "Venus": ((0.72333566, 0.00000390), (0.00677672, -0.00004107), (3.39467605, -0.00078890),
              (181.97909950, 58517.81538729), (131.60246718, 0.00268329), (76.67984255, -0.27769418)),
    "Earth": ((1.00000261, 0.00000562), (0.01671123, -0.00004392), (-0.00001531, -0.01294668),
              (100.46457166, 35999.37244981), (102.93768193, 0.32327364), (0.0, 0.0)),
    "Mars": ((1.52371034, 0.00001847), (0.09339410, 0.00007882), (1.84969142, -0.00813131),
             (-4.55343205, 19140.30268499), (-23.94362959, 0.44441088), (49.55953891, -0.29257343)),
    "Jupiter": ((5.20288700, -0.00011607), (0.04838624, -0.00013253), (1.30439695, -0.00183714),
                (34.39644051, 3034.74612775), (14.72847983, 0.21252668), (100.47390909, 0.20469106)),
    "Saturn": ((9.53667594, -0.00125060), (0.05386179, -0.00050991), (2.48599187, 0.00193609),
               (49.95424423, 1222.49362201), (92.59887831, -0.41897216), (113.66242448, -0.28867794)),
    "Uranus": ((19.18916464, -0.00196176), (0.04725744, -0.00004397), (0.77263783, -0.00242939),
               (313.23810451, 428.48202785), (170.95427630, 0.40805281), (74.01692503, 0.04240589)),
    "Neptune": ((30.06992276, 0.00026291), (0.00859048, 0.00005105), (1.77004347, 0.00035372),
                (-55.12002969, 218.45945325), (44.96476227, -0.32241464), (131.78422574, -0.00508664)),
}
PLANET_DIAM_KM = {"Mercury": 4879, "Venus": 12104, "Mars": 6779, "Jupiter": 142984,
                  "Saturn": 120536, "Uranus": 51118, "Neptune": 49528}
PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]


def _kepler(m_deg, e):
    m = rad(((m_deg + 180.0) % 360.0) - 180.0)
    big_e = m + e * math.sin(m) * (1.0 + e * math.cos(m))
    for _ in range(40):
        d = (big_e - e * math.sin(big_e) - m) / (1.0 - e * math.cos(big_e))
        big_e -= d
        if abs(d) < 1e-11:
            break
    return big_e


def _helio(name, t):
    (a0, a1), (e0, e1), (i0, i1), (l0, l1), (w0, w1), (o0, o1) = PLANET_ELEMENTS[name]
    a, e = a0 + a1 * t, e0 + e1 * t
    inc, big_l, w, om = rad(i0 + i1 * t), l0 + l1 * t, w0 + w1 * t, o0 + o1 * t
    arg = rad(w - om)
    big_e = _kepler(big_l - w, e)
    xp = a * (math.cos(big_e) - e)
    yp = a * math.sqrt(1.0 - e * e) * math.sin(big_e)
    om = rad(om)
    ca, sa, co, so, ci, si = math.cos(arg), math.sin(arg), math.cos(om), math.sin(om), math.cos(inc), math.sin(inc)
    x = (ca * co - sa * so * ci) * xp + (-sa * co - ca * so * ci) * yp
    y = (ca * so + sa * co * ci) * xp + (-sa * so + ca * co * ci) * yp
    z = (sa * si) * xp + (ca * si) * yp
    return x, y, z


def planet_state(name, jd):
    t = (jd - 2451545.0) / 36525.0
    px, py, pz = _helio(name, t)
    ex, ey, ez = _helio("Earth", t)
    gx, gy, gz = px - ex, py - ey, pz - ez
    d = math.sqrt(gx * gx + gy * gy + gz * gz)
    r = math.sqrt(px * px + py * py + pz * pz)
    big_r = math.sqrt(ex * ex + ey * ey + ez * ez)
    eps = rad(23.43928)
    xe, ye, ze = gx, gy * math.cos(eps) - gz * math.sin(eps), gy * math.sin(eps) + gz * math.cos(eps)
    ra0, dec0 = deg(math.atan2(ye, xe)) % 360.0, deg(math.asin(clamp(ze / d, -1.0, 1.0)))
    ra, dec = precess(ra0, dec0, jd)
    cos_i = clamp((r * r + d * d - big_r * big_r) / (2 * r * d), -1.0, 1.0)
    cos_e = clamp((big_r * big_r + d * d - r * r) / (2 * big_r * d), -1.0, 1.0)
    inc = deg(math.acos(cos_i))
    elong = deg(math.acos(cos_e))
    lam_p = math.atan2(gy, gx)
    lam_s = math.atan2(-ey, -ex)
    east = ((deg(lam_p - lam_s) + 180.0) % 360.0) - 180.0 > 0
    lg = 5.0 * math.log10(r * d)
    if name == "Mercury":
        mag = -0.42 + lg + 0.0380 * inc - 0.000273 * inc ** 2 + 0.000002 * inc ** 3
    elif name == "Venus":
        mag = -4.40 + lg + 0.0009 * inc + 0.000239 * inc ** 2 - 0.00000065 * inc ** 3
    elif name == "Mars":
        mag = -1.52 + lg + 0.016 * inc
    elif name == "Jupiter":
        mag = -9.40 + lg + 0.005 * inc
    elif name == "Saturn":
        pr, pd = rad(40.589), rad(83.537)  # Saturn's north pole (J2000)
        pole = (math.cos(pd) * math.cos(pr), math.cos(pd) * math.sin(pr), math.sin(pd))
        u = (-xe / d, -ye / d, -ze / d)
        sin_b = pole[0] * u[0] + pole[1] * u[1] + pole[2] * u[2]
        mag = -8.88 + lg - 2.60 * abs(sin_b) + 1.25 * sin_b ** 2
    elif name == "Uranus":
        mag = -7.19 + lg
    else:
        mag = -6.87 + lg
    return {"name": name, "ra": ra, "dec": dec, "dist": d, "r": r, "elong": elong, "east": east,
            "phase": (1.0 + math.cos(rad(inc))) / 2.0, "mag": mag,
            "diam": 206265.0 * PLANET_DIAM_KM[name] / (d * AU_KM)}


def find_events(fn, t0, t1, step, h0=0.0):
    """Times when fn(ts) crosses h0. Returns [('rise'|'set', ts)]."""
    events = []
    t = t0
    prev = fn(t0) - h0
    while t < t1:
        t2 = min(t + step, t1)
        cur = fn(t2) - h0
        if (prev < 0) != (cur < 0):
            lo, hi = t, t2
            for _ in range(24):
                mid = (lo + hi) / 2
                if (fn(mid) - h0 < 0) == (prev < 0):
                    lo = mid
                else:
                    hi = mid
            events.append(("rise" if cur >= 0 else "set", (lo + hi) / 2))
        prev, t = cur, t2
    return events
