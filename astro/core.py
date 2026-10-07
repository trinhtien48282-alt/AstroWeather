"""Foundational astronomy primitives (pure Python): Julian date, sidereal time, Alt/Az, precession.

Depends only on mathutil. No GUI, no NumPy.
"""
import math

from mathutil import clamp, deg, rad

AU_KM = 149597870.7


def jd_from_ts(ts):
    return ts / 86400.0 + 2440587.5


def gmst_deg(jd):
    d = jd - 2451545.0
    t = d / 36525.0
    return (280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - t ** 3 / 38710000.0) % 360.0


def altaz(ra, dec, jd, lat, lon):
    """RA/Dec (degrees, of date) -> altitude, azimuth (degrees, azimuth from north through east)."""
    h = rad((gmst_deg(jd) + lon - ra) % 360.0)
    phi, d = rad(lat), rad(dec)
    sin_alt = math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.cos(h)
    alt = math.asin(clamp(sin_alt, -1.0, 1.0))
    az = math.atan2(math.sin(h), math.cos(h) * math.sin(phi) - math.tan(d) * math.cos(phi)) + math.pi
    return deg(alt), deg(az) % 360.0


def precess(ra, dec, jd):
    """J2000 RA/Dec (degrees) -> RA/Dec of date (degrees)."""
    t = (jd - 2451545.0) / 36525.0
    zeta = rad((2306.2181 * t + 0.30188 * t * t + 0.017998 * t ** 3) / 3600.0)
    z = rad((2306.2181 * t + 1.09468 * t * t + 0.018203 * t ** 3) / 3600.0)
    theta = rad((2004.3109 * t - 0.42665 * t * t - 0.041833 * t ** 3) / 3600.0)
    a, d = rad(ra), rad(dec)
    A = math.cos(d) * math.sin(a + zeta)
    B = math.cos(theta) * math.cos(d) * math.cos(a + zeta) - math.sin(theta) * math.sin(d)
    C = math.sin(theta) * math.cos(d) * math.cos(a + zeta) + math.cos(theta) * math.sin(d)
    return (deg(math.atan2(A, B) + z)) % 360.0, deg(math.asin(clamp(C, -1.0, 1.0)))
