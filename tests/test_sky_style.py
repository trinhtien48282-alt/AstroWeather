"""Sky-chart colour and Moon-phase helpers (stdlib unittest). Run: python -m unittest tests.test_sky_style -v"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astro import sky_style as st  # noqa: E402


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


class MoonColor(unittest.TestCase):
    def test_high_moon_is_near_white_and_low_moon_is_redder(self):
        hi, mid, lo = st.moon_color(80), st.moon_color(25), st.moon_color(3)
        self.assertGreater(hi[2] / hi[0], mid[2] / mid[0])
        self.assertGreater(mid[2] / mid[0], lo[2] / lo[0])
        self.assertGreater(lo[0], lo[2] * 3)  # clearly orange at the horizon
        self.assertTrue(all(0 <= v <= 255 for v in lo + mid + hi))

    def test_below_horizon_is_clamped_not_an_error(self):
        self.assertEqual(st.moon_color(-20), st.moon_color(0))


class SkyGradient(unittest.TestCase):
    def test_night_is_dark_and_day_is_bright(self):
        self.assertLess(lum(st.sky_colors(-30, 5)[0]), 20)
        self.assertGreater(lum(st.sky_colors(40, 5)[0]), 70)

    def test_day_horizon_is_paler_than_zenith_and_endpoints_match_stops(self):
        g = st.sky_colors(30, 6)
        self.assertGreater(lum(g[-1]), lum(g[0]))
        self.assertEqual(g[0], tuple(st.SKY_STOPS[0][1][0]))
        self.assertEqual(g[-1], tuple(st.SKY_STOPS[0][1][1]))

    def test_sunset_rim_is_orange(self):
        rim = st.sky_colors(0.0, 6)[-1]
        self.assertGreater(rim[0], rim[2] + 100)

    def test_twilight_has_a_warm_rim(self):
        rim = st.sky_colors(-1.0, 6)[-1]
        self.assertGreater(rim[0], rim[2])  # red above blue

    def test_midnight_horizon_glows_blue_not_flat_black(self):
        g = st.sky_colors(-40, 6)
        self.assertGreater(g[-1][2], g[0][2] + 20)
        self.assertGreater(lum(g[-1]), lum(g[0]))

    def test_continuous_across_sun_altitudes(self):
        prev = st.sky_colors(25, 4)
        a = 25.0
        while a > -25:
            a -= 0.25
            cur = st.sky_colors(a, 4)
            for p, c in zip(prev, cur):
                self.assertLess(max(abs(p[i] - c[i]) for i in range(3)), 9)
            prev = cur


class StarColor(unittest.TestCase):
    def test_missing_index_is_neutral(self):
        self.assertEqual(st.bv_color(None), st.STAR_NEUTRAL)
        self.assertEqual(st.bv_color(float("nan")), st.STAR_NEUTRAL)

    def test_blue_to_orange_and_clamped(self):
        def rgb(h):
            return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        hot, cool = rgb(st.bv_color(-0.3)), rgb(st.bv_color(1.5))
        self.assertGreater(hot[2], hot[0])
        self.assertGreater(cool[0], cool[2])
        self.assertEqual(st.bv_color(-5.0), st.bv_color(-0.3))
        self.assertEqual(st.bv_color(9.0), st.bv_color(1.6))


class LayerColors(unittest.TestCase):
    def test_daytime_overlay_is_light_enough_for_a_blue_sky(self):
        line, label = st.layer_colors(30)
        self.assertGreater(int(label[1:3], 16), 200)


class PhaseSpans(unittest.TestCase):
    def test_lit_area_matches_the_illuminated_fraction(self):
        r = 100.0
        for k in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            rows = 2000
            dy = 2 * r / rows
            area = sum((x1 - x0) * dy for _y, x0, x1 in st.moon_phase_spans(r, k, rows))
            self.assertAlmostEqual(area / (math.pi * r * r), k, delta=0.005, msg=k)

    def test_new_moon_has_no_spans_and_full_moon_covers_the_disc(self):
        self.assertEqual(st.moon_phase_spans(50, 0.0), [])
        y, x0, x1 = st.moon_phase_spans(50, 1.0)[len(st.moon_phase_spans(50, 1.0)) // 2]
        self.assertAlmostEqual(x0, -x1, places=6)


if __name__ == "__main__":
    unittest.main()
