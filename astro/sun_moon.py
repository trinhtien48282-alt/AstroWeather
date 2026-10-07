"""Sun and Moon (pure Python): positions, altitudes, Moon phase and the next phase time.

Depends only on astro.core and mathutil. No GUI, no NumPy.
"""
import math

from astro.core import AU_KM, altaz, jd_from_ts
from mathutil import clamp, deg, rad


def sun_pos(jd):
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360.0
    g = rad((357.528 + 0.9856003 * n) % 360.0)
    lam = rad((L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0)
    eps = rad(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    dist = 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2 * g)
    return {"ra": deg(ra) % 360.0, "dec": deg(dec), "lon": deg(lam) % 360.0, "dist": dist}


def moon_pos(jd):
    """Low-precision Moon (about 0.3 deg): good for phase, rise/set to a few minutes, sky chart."""
    t = (jd - 2451545.0) / 36525.0

    def s(a, b):
        return math.sin(rad(a + b * t))

    def c(a, b):
        return math.cos(rad(a + b * t))

    lon = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
           + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03))
    lat = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15)
           - 0.17 * s(217.6, -407332.21))
    par = (0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36)
           + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74))
    l, b = rad(lon), rad(lat)
    eps = rad(23.439291 - 0.0130042 * t)
    x = math.cos(b) * math.cos(l)
    y = math.cos(eps) * math.cos(b) * math.sin(l) - math.sin(eps) * math.sin(b)
    z = math.sin(eps) * math.cos(b) * math.sin(l) + math.cos(eps) * math.sin(b)
    return {"ra": deg(math.atan2(y, x)) % 360.0, "dec": deg(math.asin(clamp(z, -1.0, 1.0))),
            "lon": lon % 360.0, "lat": lat, "par": par, "dist": 6378.14 / math.sin(rad(par))}


def sun_altitude(ts, lat, lon):
    jd = jd_from_ts(ts)
    s = sun_pos(jd)
    return altaz(s["ra"], s["dec"], jd, lat, lon)[0]


def moon_altitude(ts, lat, lon):
    """Topocentric altitude of the Moon's centre (parallax applied)."""
    jd = jd_from_ts(ts)
    m = moon_pos(jd)
    alt, _ = altaz(m["ra"], m["dec"], jd, lat, lon)
    return alt - m["par"] * math.cos(rad(alt))


def moon_info(ts, lat, lon):
    jd = jd_from_ts(ts)
    m, s = moon_pos(jd), sun_pos(jd)
    psi = math.acos(clamp(math.cos(rad(m["lat"])) * math.cos(rad(m["lon"] - s["lon"])), -1.0, 1.0))
    rs = s["dist"] * AU_KM
    inc = math.atan2(rs * math.sin(psi), m["dist"] - rs * math.cos(psi))
    angle = (m["lon"] - s["lon"]) % 360.0
    alt, az = altaz(m["ra"], m["dec"], jd, lat, lon)
    alt -= m["par"] * math.cos(rad(alt))
    return {"illum": (1.0 + math.cos(inc)) / 2.0, "angle": angle, "age": angle / 360.0 * 29.530588,
            "alt": alt, "az": az, "dist_km": m["dist"], "name": phase_name(angle),
            "ang_diam": deg(2 * math.atan(1737.4 / m["dist"])) * 3600.0}


def phase_name(angle):
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon",
             "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return names[int(((angle + 22.5) % 360.0) // 45.0)]


def next_phase_time(ts, target_angle):
    """Next time the Moon-Sun ecliptic angle reaches target_angle (0 new, 90 FQ, 180 full, 270 LQ)."""
    def f(t):
        jd = jd_from_ts(t)
        ang = (moon_pos(jd)["lon"] - sun_pos(jd)["lon"]) % 360.0
        return ((ang - target_angle + 180.0) % 360.0) - 180.0

    step = 3 * 3600.0
    t, prev = ts, f(ts)
    for _ in range(int(36 * 86400 / step)):
        t2 = t + step
        cur = f(t2)
        if prev < 0 <= cur and (cur - prev) < 90:
            lo, hi = t, t2
            for _ in range(30):
                mid = (lo + hi) / 2
                if f(mid) < 0:
                    lo = mid
                else:
                    hi = mid
            return hi
        t, prev = t2, cur
    return None

