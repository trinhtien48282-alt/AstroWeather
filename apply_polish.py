"""AstroWeather polish, steps 1-4. Run from the repo root:  python apply_polish.py

 1. weather/analysis.py   dso/planet are 0 outside their dark thresholds (Sun < -12 / < -6, same as the heat map)
 2. gui/tonight_page.py   "Advanced" expandable hourly weather table (reads analysis["tonight"]["hours"], no new calculation)
 3. gui/altitude_graph.py REPLACED: follows canvas size, wheel zoom / drag pan on the time axis, Fit; interpolates the
                          already computed plan arrays (no astronomy recomputed). planner_page.py / app.py: wiring only
 4. gui/sky_page.py       Legend tab (static text about what draw_sky already draws)
 tests/test_scores.py, tests/test_altitude_graph.py   NEW

Every edit must match exactly once; if any fails NOTHING is written. Keeps each file's line endings. Refuses if the new tests exist.
"""
import os
import sys

E = []  # (path, old, new)


def R(path, old, new):
    E.append((path, old, new))


# ---------------------------------------------------------------- 1. daylight scores
R("weather/analysis.py",
  r'''        dso = (0.32 * sc_trans + 0.30 * sc_moon + 0.14 * sc_wind + 0.12 * sc_dew + 0.12 * sc_seeing) * gate
        planet = (0.45 * sc_seeing + 0.20 * sc_trans + 0.15 * sc_wind + 0.10 * sc_dew + 10.0) * gate
''',
  r'''        # same thresholds as the heat map and Tonight: deep-sky needs Sun < -12, planets Sun < -6; otherwise 0 (not an observing score)
        dso = (0.32 * sc_trans + 0.30 * sc_moon + 0.14 * sc_wind + 0.12 * sc_dew + 0.12 * sc_seeing) * gate if s_alt < -12 else 0.0
        planet = (0.45 * sc_seeing + 0.20 * sc_trans + 0.15 * sc_wind + 0.10 * sc_dew + 10.0) * gate if s_alt < -6 else 0.0
''')

# ---------------------------------------------------------------- 2. Tonight: Advanced
R("gui/tonight_page.py",
  '        c = self.card(body, "Sun, Moon and planets tonight")\n',
  '''        c = self.card(body)
        self.adv_open = False
        self.btn_adv = ctk.CTkButton(c, text="Advanced: hourly weather data  [show]", anchor="w", height=34, font=self.f_ui,
                                     fg_color="transparent", hover_color="#232830", command=self.toggle_adv)
        self.btn_adv.pack(fill="x", padx=10, pady=8)
        self.box_adv = ctk.CTkTextbox(c, height=300, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        c = self.card(body, "Sun, Moon and planets tonight")
''')
R("gui/tonight_page.py", "    def fill_targets(self):\n",
  r'''    def toggle_adv(self):
        self.adv_open = not self.adv_open
        if self.adv_open:
            self.box_adv.pack(fill="x", padx=14, pady=(0, 14))
        else:
            self.box_adv.pack_forget()
        self.btn_adv.configure(text="Advanced: hourly weather data  [hide]" if self.adv_open else "Advanced: hourly weather data  [show]")

    def fill_advanced(self):
        """Hourly table for tonight's window from the data analyze() already holds ('-' = not provided)."""
        a, u = self.analysis, self.cfg["units"]
        hours, off = a["tonight"]["hours"], a["offset"]
        if not hours:
            self.set_text(self.box_adv, "No forecast hours in tonight's window.")
            return
        v = lambda x, spec="{:.0f}": "-" if x is None else spec.format(x)
        lines = [f"{'Time':<6}{'Cloud%':>7}{'Low':>5}{'Mid':>5}{'High':>5}{'Temp':>6}{'RH%':>5}{'Wind':>6}{'Gust':>6}{'Vis km':>8}{'Rain%':>7}{'mm':>6}"]
        for hr in hours:
            lines.append(f"{fmt_clock(hr['ts'], off):<6}{v(hr['cloud']):>7}{v(hr['low']):>5}{v(hr['mid']):>5}{v(hr['high']):>5}"
                         f"{fmt_temp(hr['temp'], u):>6}{v(hr['rh']):>5}{conv_wind(hr['wind'], u):>6.0f}{conv_wind(hr['gust'], u):>6.0f}"
                         f"{v(hr['vis_km']):>8}{v(hr['pp']):>7}{v(hr['precip'], '{:.1f}'):>6}")
        lines += ["", f"Wind and gusts in {u.get('wind', 'km/h')}. Local time. '-' = not provided for this place and hour."]
        self.set_text(self.box_adv, "\n".join(lines))

    def fill_targets(self):
''')
R("gui/tonight_page.py",
  r'''        self.set_text(self.box_planets, "\n".join(lines))
        self.fill_targets()
''',
  r'''        self.set_text(self.box_planets, "\n".join(lines))
        self.fill_advanced()
        self.fill_targets()
''')
R("gui/tonight_page.py", '        self.set_text(self.box_targets, "")\n',
  '        self.set_text(self.box_targets, "")\n        self.set_text(self.box_adv, "")\n')

# ---------------------------------------------------------------- 3. altitude graph wiring
R("gui/app.py",
  "        self.plan, self.plan_busy, self.plan_req, self.plan_sel, self.plot_set = None, False, 0, None, []\n",
  "        self.plan, self.plan_busy, self.plan_req, self.plan_sel, self.plot_set = None, False, 0, None, []\n"
  "        self.alt_view, self._alt_job, self._alt_drag = None, None, None  # altitude graph: zoom window, resize throttle, pan start\n")
R("gui/planner_page.py", "        right.grid_rowconfigure(0, weight=1)\n",
  "        right.grid_rowconfigure(0, weight=1)\n        right.grid_rowconfigure(2, weight=2)  # the graph takes the larger share of spare height\n")
R("gui/planner_page.py",
  '        ctk.CTkLabel(tools, text="click a target to add/remove it", font=self.f_small, text_color="#6b7390").pack(side="left", padx=8)\n',
  '''        ctk.CTkButton(tools, text="Fit", width=44, height=26, font=self.f_small, fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=self.alt_fit).pack(side="left", padx=4)
        ctk.CTkLabel(tools, text="click a target to add/remove it; wheel zooms, drag pans", font=self.f_small, text_color="#6b7390").pack(side="left", padx=8)
''')
R("gui/planner_page.py",
  '''        self.alt_canvas.grid(row=2, column=0, sticky="n", pady=(4, 0))
        self.alt_canvas.bind("<Motion>", self.on_alt_motion)
''',
  '''        self.alt_canvas.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        self.alt_canvas.bind("<Motion>", self.on_alt_motion)
        self.alt_canvas.bind("<Configure>", self.on_alt_resize)
        self.alt_canvas.bind("<MouseWheel>", self.on_alt_wheel)
        self.alt_canvas.bind("<ButtonPress-1>", self.on_alt_press)
        self.alt_canvas.bind("<B1-Motion>", self.on_alt_drag)
        self.alt_canvas.bind("<Double-Button-1>", lambda e: self.alt_fit())
''')
R("gui/planner_page.py",
  '        self.plan = res\n        self.plot_set = [r["ti"] for r in res["rows"][:3]]\n',
  '        self.plan = res\n        self.alt_view = None  # a new plan shows its whole range\n        self.plot_set = [r["ti"] for r in res["rows"][:3]]\n')

# ---------------------------------------------------------------- 4. sky legend
LEGEND = r'''SKY_LEGEND = (
    "READING THE CHART\n"
    "Looking up: the centre is the zenith, the rim is the horizon. N top, S bottom, E left, W right.\n"
    "Dashed rings: altitude 30 and 60 deg. Background: bright blue = day, then darker for civil, nautical and astronomical "
    "twilight, black = Sun below -18 deg.\n\n"
    "SYMBOLS\n"
    "White dot       star (bigger = brighter). Name shown for mag < 1.3, or for all when zoomed 2x or more.\n"
    "Square          deep-sky object or double star from the catalog. Its colour is the rating in your scope:\n"
    "                green Easy, yellow Moderate, orange Hard, grey Beyond. Shapes do not encode the object type: click one "
    "to read its type.\n"
    "Coloured disc  planet, with its name. Size follows brightness.\n"
    "Pale disc       Moon, with the percent of the disc lit.\n"
    "Yellow disc     Sun. Never view it without a certified solar filter.\n"
    "White ring      the object you selected. Click empty sky to clear it.\n\n"
    "NOTATION\n"
    "Alt             altitude, degrees above the horizon (0 horizon, 90 zenith).\n"
    "Az              azimuth, degrees from north through east (N 0, E 90, S 180, W 270).\n"
    "mag             magnitude: smaller is brighter. A margin of +2 mag means 2 mag brighter than your scope's limit.\n"
    "Rating          Easy margin >= 3, Moderate >= 1.2, Hard >= 0, Beyond < 0 (estimate for your aperture, Bortle class and Moon).\n"
    "Moon column     separation from the Moon in degrees / magnitudes of sky limit lost to its glare.\n"
    "RA, Dec         right ascension and declination, J2000.\n"
    "Units           ' arcminute, \" arcsecond, d degrees, x magnification.\n"
)


'''
R("gui/sky_page.py", "def _ra_text(ra_h):\n", LEGEND + "def _ra_text(ra_h):\n")
R("gui/sky_page.py",
  '''        self.box_sky = ctk.CTkTextbox(right, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_sky.grid(row=2, column=0, sticky="nsew")
''',
  '''        tabs = ctk.CTkTabview(right)
        tabs.grid(row=2, column=0, sticky="nsew")
        tabs.add("Visible now")
        tabs.add("Legend")
        self.box_sky = ctk.CTkTextbox(tabs.tab("Visible now"), font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_sky.pack(fill="both", expand=True)
        box_leg = ctk.CTkTextbox(tabs.tab("Legend"), font=self.f_mono, fg_color=DEEP, state="disabled", wrap="word")
        box_leg.pack(fill="both", expand=True)
        self.set_text(box_leg, SKY_LEGEND)
''')

ALT = r'''"""Planner altitude graph: canvas drawing, time-axis zoom/pan and the hover read-out."""
import bisect
import time
from datetime import datetime, timedelta, timezone

from gui.theme import ALT_BANDS, ALT_COLORS, ALT_H, ALT_W
from weather.analysis import fmt_clock

MIN_SPAN = 7200.0  # shortest zoom window, seconds


def fit_view(v0, v1, full0, full1):
    """Clamp the window [v0, v1] into [full0, full1] keeping its span (between MIN_SPAN and the full range).
    Returns None when the window covers everything (the unzoomed state)."""
    full = full1 - full0
    span = min(max(v1 - v0, min(MIN_SPAN, full)), full)
    v0 = max(full0, min(v0, full1 - span))
    return None if span >= full - 1e-6 else (v0, v0 + span)


def zoom_view(view, full0, full1, frac, factor):
    """Zoom by factor (>1 = in) keeping the time at fraction frac (0..1) of the window where it is."""
    v0, v1 = view or (full0, full1)
    t = v0 + frac * (v1 - v0)
    span = (v1 - v0) / factor
    n0 = t - frac * span
    return fit_view(n0, n0 + span, full0, full1)


def lerp(ts, arr, t):
    """Value of the sampled curve (ts ascending) at time t, linearly interpolated: the plan's arrays are reused, nothing is recomputed."""
    k = min(max(bisect.bisect_right(ts, t) - 1, 0), len(ts) - 2)
    f = (t - ts[k]) / (ts[k + 1] - ts[k])
    return arr[k] + f * (arr[k + 1] - arr[k])


class AltitudeGraph:
    """Planner altitude graph: canvas drawing, time-axis zoom/pan and the hover read-out."""

    def draw_alt_graph(self):
        c = self.alt_canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 200 or H < 120:  # not laid out yet
            W, H = ALT_W, ALT_H
        L, R, T, B = 40, 10, 12, 30
        res = self.plan
        if not res:
            self.alt_view = None
            c.create_text(W / 2, H / 2, text="Run the planner, then click targets to plot their altitude", fill="#6b7390", font=("Segoe UI", 10))
            self.alt_geom = None
            return
        ts = res["ts"].tolist()
        t0, t1 = ts[0], ts[-1]
        v0, v1 = self.alt_view or (t0, t1)
        X = lambda t: L + (t - v0) / (v1 - v0) * (W - L - R)
        Y = lambda a: T + (90.0 - a) / 90.0 * (H - T - B)
        tv = [v0] + ts[bisect.bisect_right(ts, v0):bisect.bisect_left(ts, v1)] + [v1]  # window edges + the samples between
        series = lambda arr: [lerp(ts, arr, t) for t in tv]
        sun = series(res["sun_alt"].tolist())
        cls = [0 if v > -0.833 else 1 if v > -6 else 2 if v > -12 else 3 if v > -18 else 4 for v in sun]
        start = 0
        for k in range(1, len(cls) + 1):
            if k == len(cls) or cls[k] != cls[start]:
                c.create_rectangle(X(tv[start]), T, X(tv[min(k, len(tv) - 1)]), H - B, fill=ALT_BANDS[cls[start]], outline="")
                start = k
        for a in (0, 30, 60, 90):
            c.create_line(L, Y(a), W - R, Y(a), fill="#2a3558")
            c.create_text(L - 5, Y(a), text=f"{a}", anchor="e", fill="#8fa3c8", font=("Segoe UI", 8))
        ma = res["min_alt"]
        c.create_line(L, Y(ma), W - R, Y(ma), fill="#e0b84c", dash=(3, 3))
        span_h = (v1 - v0) / 3600.0
        step_h = 1 if span_h <= 10 else 2 if span_h <= 20 else 3 if span_h <= 36 else 6 if span_h <= 80 else 12
        tz = timezone(timedelta(seconds=res["offset"]))
        tick = datetime.fromtimestamp(v0, tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while tick.hour % step_h:
            tick += timedelta(hours=1)
        tt = tick.timestamp()
        while tt < v1:
            dt = datetime.fromtimestamp(tt, tz)
            c.create_line(X(tt), T, X(tt), H - B, fill="#1f2a4a")
            c.create_text(X(tt), H - B + 10, text=f"{dt.hour:02d}", fill="#cfd6e4", font=("Segoe UI", 8))
            if dt.hour == 0:
                c.create_text(X(tt), H - 8, text=dt.strftime("%a %d %b"), fill="#8fa3c8", font=("Segoe UI", 8, "bold"))
            tt += step_h * 3600

        def runs(vals):
            cur = []
            for k, a in enumerate(vals):
                if a >= 0:
                    cur.append((X(tv[k]), Y(a)))
                else:
                    if len(cur) > 1:
                        yield cur
                    cur = []
            if len(cur) > 1:
                yield cur
        for pts in runs(series(res["moon_alt"].tolist())):
            c.create_line(*[v for xy in pts for v in xy], fill="#d8d2a8", dash=(5, 4), width=1)
        legend_x = L + 6
        for n, ti in enumerate(self.plot_set):
            col = ALT_COLORS[n % len(ALT_COLORS)]
            for pts in runs(series(res["alt"][ti].tolist())):
                c.create_line(*[v for xy in pts for v in xy], fill=col, width=2)
            o = res["targets"][ti]
            label = o["id"]
            c.create_text(legend_x, T + 24, text=label, anchor="w", fill=col, font=("Segoe UI", 9, "bold"))
            legend_x += 8 + 7 * len(label)
        c.create_text(W - R - 4, T + 8, text="Moon (dashed)" + ("   zoomed: Fit resets" if self.alt_view else ""), anchor="e", fill="#d8d2a8", font=("Segoe UI", 8))
        now = res.get("now") or time.time()
        if v0 <= now <= v1:
            c.create_line(X(now), T, X(now), H - B, fill="#5ec8ff", width=2)
        self.alt_geom = (v0, v1, L, R, W, T, H, B)

    def on_alt_motion(self, event):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        v0, v1, L, R, W, T, H, B = g
        c = self.alt_canvas
        c.delete("cross")
        if not (L <= event.x <= W - R):
            return
        p, ts = self.plan, self.plan["ts"]
        t = v0 + (event.x - L) / (W - L - R) * (v1 - v0)
        c.create_line(event.x, T, event.x, H - B, fill="#ffffff", dash=(2, 2), tags="cross")
        parts = [fmt_clock(t, p["offset"])]
        for ti in self.plot_set[:6]:
            parts.append(f"{p['targets'][ti]['id']} {lerp(ts, p['alt'][ti], t):.0f}d")
        parts.append(f"Moon {lerp(ts, p['moon_alt'], t):.0f}d")
        c.create_text(L + 6, T + 8, text="   ".join(parts), anchor="w", fill="#e8eefc", font=("Segoe UI", 8, "bold"), tags="cross")

    def _alt_full(self):
        ts = self.plan["ts"]
        return float(ts[0]), float(ts[-1])

    def on_alt_resize(self, _event):
        if not self._alt_job:  # throttle: a window drag fires many Configure events
            self._alt_job = self.after(50, self._alt_redraw)

    def _alt_redraw(self):
        self._alt_job = None
        self.draw_alt_graph()

    def on_alt_wheel(self, e):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        frac = min(1.0, max(0.0, (e.x - g[2]) / (g[4] - g[2] - g[3])))
        self.alt_view = zoom_view(self.alt_view, *self._alt_full(), frac, 1.25 ** (e.delta / 120.0))
        self.draw_alt_graph()

    def on_alt_press(self, e):
        g = getattr(self, "alt_geom", None)
        self._alt_drag = (e.x, g[0], g[1]) if g else None

    def on_alt_drag(self, e):
        d, g = self._alt_drag, getattr(self, "alt_geom", None)
        if not d or not g or not self.alt_view or not self.plan:
            return
        x0, v0, v1 = d
        dt = (x0 - e.x) / (g[4] - g[2] - g[3]) * (v1 - v0)
        self.alt_view = fit_view(v0 + dt, v1 + dt, *self._alt_full())
        self.draw_alt_graph()

    def alt_fit(self):
        self.alt_view = None
        self.draw_alt_graph()
'''

T_SCORES = r'''"""Daylight / twilight scoring boundaries (stdlib unittest). Run from the repo root:  python -m unittest tests.test_scores -v"""
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
'''

T_GRAPH = r'''"""Altitude-graph zoom/pan/interpolation logic (stdlib unittest, no GUI). Run: python -m unittest tests.test_altitude_graph -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.altitude_graph import MIN_SPAN, fit_view, lerp, zoom_view  # noqa: E402

F0, F1 = 0.0, 36000.0  # a 10 h plan


class ViewTests(unittest.TestCase):
    def test_full_window_is_none(self):
        self.assertIsNone(fit_view(F0, F1, F0, F1))
        self.assertIsNone(fit_view(-500, F1 + 500, F0, F1))

    def test_clamped_into_range_keeps_span(self):
        self.assertEqual(fit_view(-1000, 9000, F0, F1), (0.0, 10000.0))
        self.assertEqual(fit_view(30000, 40000, F0, F1), (26000.0, 36000.0))

    def test_min_span(self):
        v = fit_view(1000, 1100, F0, F1)
        self.assertAlmostEqual(v[1] - v[0], MIN_SPAN)

    def test_zoom_keeps_time_under_cursor(self):
        v = zoom_view(None, F0, F1, 0.25, 2.0)  # cursor at t = 9000
        self.assertAlmostEqual(v[1] - v[0], 18000.0)
        self.assertAlmostEqual(v[0] + 0.25 * (v[1] - v[0]), 9000.0)

    def test_zoom_out_returns_to_fit(self):
        v = zoom_view(None, F0, F1, 0.5, 4.0)
        self.assertIsNone(zoom_view(v, F0, F1, 0.5, 0.1))

    def test_zoom_stops_at_min_span(self):
        v = None
        for _ in range(40):
            v = zoom_view(v, F0, F1, 0.5, 1.25) or v
        self.assertGreaterEqual(v[1] - v[0], MIN_SPAN - 1e-6)


class LerpTests(unittest.TestCase):
    ts, arr = [0.0, 10.0, 20.0], [0.0, 10.0, 40.0]

    def test_samples_and_midpoints(self):
        self.assertEqual(lerp(self.ts, self.arr, 0.0), 0.0)
        self.assertEqual(lerp(self.ts, self.arr, 5.0), 5.0)
        self.assertEqual(lerp(self.ts, self.arr, 15.0), 25.0)
        self.assertEqual(lerp(self.ts, self.arr, 20.0), 40.0)


if __name__ == "__main__":
    unittest.main()
'''


def read(path):
    if not os.path.exists(path):
        sys.exit(f"missing file: {path} (run from the repo root)")
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def main():
    for t in ("tests/test_scores.py", "tests/test_altitude_graph.py"):
        if os.path.exists(t):
            sys.exit(f"NOTHING WRITTEN. {t} already exists (already applied?)")
    texts, nl = {}, {}
    for path, old, new in E:
        if path not in texts:
            texts[path] = read(path)
            nl[path] = "\r\n" if "\r\n" in texts[path] else "\n"
        o, n = old.replace("\n", nl[path]), new.replace("\n", nl[path])
        c = texts[path].count(o)
        if c != 1:
            sys.exit(f"NOTHING WRITTEN. {path}: expected 1 match, found {c} for:\n{old}")
        texts[path] = texts[path].replace(o, n)
    old_alt = read("gui/altitude_graph.py")
    if old_alt.count("class AltitudeGraph") != 1 or old_alt.count("def draw_alt_graph(") != 1:
        sys.exit("NOTHING WRITTEN. gui/altitude_graph.py is not the expected AltitudeGraph module")
    anl = "\r\n" if "\r\n" in old_alt else "\n"
    texts["gui/altitude_graph.py"] = ALT.replace("\n", anl)
    texts["tests/test_scores.py"] = T_SCORES.replace("\n", anl)
    texts["tests/test_altitude_graph.py"] = T_GRAPH.replace("\n", anl)
    for path, text in texts.items():
        compile(text, path, "exec")
    for path, text in texts.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print(f"ok: {len(E)} edits, {len(texts)} files written")


main()
