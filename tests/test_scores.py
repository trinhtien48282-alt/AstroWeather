"""Daylight / twilight scoring boundaries (stdlib unittest). Run from the repo root:  python -m unittest tests.test_scores -v"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro.sun_moon import sun_altitude  # noqa: E402
from weather.analysis import build_hours  # noqa: E402

LAT, LON = 9.1769, 105.1524  # Ca Mau, UTC+7
EVENING = (int(datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc).timestamp()),  # 17:00 local, Sun up
           int(datetime(2026, 10, 14, 13, 30, tzinfo=timezone.utc).timestamp()))  # 20:30 local, full night


def hour(ts):
    wx = {"hourly": {"time": [ts], "temperature_2m": [28.0], "cloud_cover": [0.0]}}  # clear sky, no other data
    return build_hours(wx, None, LAT, LON)[0]


def first_below(level):
    """First whole minute of the evening where the Sun is below `level` degrees."""
    for ts in range(EVENING[0], EVENING[1], 60):
        if sun_altitude(ts, LAT, LON) < level:
            return ts
    raise AssertionError(f"Sun never went below {level}")


class DaylightScoreTests(unittest.TestCase):
    def test_noon_is_zero(self):
        h = hour(int(datetime(2026, 10, 14, 5, 0, tzinfo=timezone.utc).timestamp()))  # 12:00 local
        self.assertGreater(h["sun_alt"], 0)
        self.assertEqual((h["dso"], h["planet"]), (0.0, 0.0))

    def test_midnight_is_scored(self):
        h = hour(int(datetime(2026, 10, 13, 17, 0, tzinfo=timezone.utc).timestamp()))  # 00:00 local
        self.assertLess(h["sun_alt"], -18)
        self.assertGreater(h["dso"], 0)
        self.assertGreater(h["planet"], 0)

    def test_twilight_planets_only(self):
        h = hour(first_below(-9.0))
        self.assertGreaterEqual(h["sun_alt"], -12.0)  # explicit: the Sun really is in the nautical-twilight band
        self.assertLess(h["sun_alt"], -6.0)
        self.assertEqual(h["dso"], 0.0)
        self.assertGreater(h["planet"], 0)

    def test_deep_sky_boundary_minus_12(self):
        t = first_below(-12.0)
        before, after = hour(t - 60), hour(t)
        self.assertGreaterEqual(before["sun_alt"], -12.0)
        self.assertLess(after["sun_alt"], -12.0)
        self.assertEqual(before["dso"], 0.0)
        self.assertGreater(after["dso"], 0)

    def test_planet_boundary_minus_6(self):
        t = first_below(-6.0)
        before, after = hour(t - 60), hour(t)
        self.assertGreaterEqual(before["sun_alt"], -6.0)
        self.assertLess(after["sun_alt"], -6.0)
        self.assertEqual(before["planet"], 0.0)
        self.assertGreater(after["planet"], 0)


if __name__ == "__main__":
    unittest.main()
