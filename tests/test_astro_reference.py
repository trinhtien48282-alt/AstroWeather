"""Reference-value checks for the pure-Python astronomy core (stdlib unittest, no NumPy, no GUI).

Run from the repo root:  python -m unittest tests.test_astro_reference -v
References: Meeus, "Astronomical Algorithms" 2nd ed. (examples 12.a, 13.b, 25.a, 33.a, 47.a) and well-known phase times.
Tolerances match the stated accuracy of each low-precision model (Sun ~0.05 deg, Moon ~0.3 deg, planets ~0.1 deg).
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro.core import altaz, gmst_deg, jd_from_ts, precess  # noqa: E402
from astro.planets import planet_state  # noqa: E402
from astro.sun_moon import moon_pos, next_phase_time, sun_pos  # noqa: E402

UTC = timezone.utc


class CoreTests(unittest.TestCase):
    def test_jd_j2000(self):
        self.assertAlmostEqual(jd_from_ts(946728000), 2451545.0, places=9)

    def test_gmst_meeus_12a(self):  # 1987-04-10 0h UT -> 13h10m46.3668s
        self.assertAlmostEqual(gmst_deg(2446895.5), 197.693195, places=4)

    def test_altaz_meeus_13b(self):  # Venus from Washington; azimuth here is from north (Meeus: from south)
        ra, dec = (23 + 9 / 60 + 16.641 / 3600) * 15, -(6 + 43 / 60 + 11.61 / 3600)
        lat, lon = 38 + 55 / 60 + 17 / 3600, -(77 + 3 / 60 + 56 / 3600)  # east-positive longitude
        alt, az = altaz(ra, dec, 2446896.30625, lat, lon)
        self.assertAlmostEqual(alt, 15.1249, delta=0.01)
        self.assertAlmostEqual(az, 68.0337 + 180.0, delta=0.01)

    def test_precess_identity_and_rate(self):
        self.assertAlmostEqual(precess(41.05, 49.23, 2451545.0)[0], 41.05, places=9)
        ra, dec = precess(0.0, 0.0, 2451545.0 + 365.25)  # general precession: 46.124 s/yr in RA, 20.043 s/yr in Dec
        self.assertAlmostEqual(ra, 46.1244 / 3600, delta=2e-5)
        self.assertAlmostEqual(dec, 20.0431 / 3600, delta=2e-5)


class BodyTests(unittest.TestCase):
    def test_sun_meeus_25a(self):
        s = sun_pos(2448908.5)
        self.assertAlmostEqual(s["ra"], 198.38083, delta=0.05)
        self.assertAlmostEqual(s["dec"], -7.78507, delta=0.05)
        self.assertAlmostEqual(s["dist"], 0.99766, delta=0.0005)

    def test_moon_meeus_47a(self):
        m = moon_pos(2448724.5)
        self.assertAlmostEqual(m["lon"], 133.162655, delta=0.3)
        self.assertAlmostEqual(m["lat"], -3.229126, delta=0.2)
        self.assertAlmostEqual(m["ra"], 134.688470, delta=0.3)
        self.assertAlmostEqual(m["dec"], 13.768368, delta=0.2)
        self.assertAlmostEqual(m["dist"], 368409.7, delta=3000)

    def test_venus_meeus_33a(self):
        v = planet_state("Venus", 2448976.5)
        self.assertAlmostEqual(v["ra"], (21 + 4 / 60 + 41.454 / 3600) * 15, delta=0.1)
        self.assertAlmostEqual(v["dec"], -(18 + 53 / 60 + 16.84 / 3600), delta=0.1)
        self.assertAlmostEqual(v["dist"], 0.910845, delta=0.002)

    def test_moon_phase_times(self):  # UT; model is good to ~0.6 h, allow 1.5 h
        for start, target, expected in (
                (datetime(2000, 1, 1, tzinfo=UTC), 0.0, datetime(2000, 1, 6, 18, 14, tzinfo=UTC)),
                (datetime(2000, 1, 1, tzinfo=UTC), 180.0, datetime(2000, 1, 21, 4, 40, tzinfo=UTC)),
                (datetime(2024, 4, 1, tzinfo=UTC), 0.0, datetime(2024, 4, 8, 18, 21, tzinfo=UTC)),
                (datetime(2024, 4, 1, tzinfo=UTC), 180.0, datetime(2024, 4, 23, 23, 49, tzinfo=UTC))):
            got = next_phase_time(start.timestamp(), target)
            self.assertLess(abs(got - expected.timestamp()) / 3600.0, 1.5, (target, expected))


if __name__ == "__main__":
    unittest.main()
