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
from datetime import datetime, timedelta, timezone

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

from config import (APP_NAME, CACHE_PATH, CONFIG_DIR, CONFIG_PATH, DEFAULT_CONFIG, LOG_PATH,  # noqa: F401
                    load_config, log_error, save_config)
from mathutil import D2R, R2D, clamp, deg, mean, piecewise, rad  # noqa: F401
from astro.core import AU_KM, altaz, gmst_deg, jd_from_ts, precess  # noqa: F401
from astro.sun_moon import (moon_altitude, moon_info, moon_pos, next_phase_time, phase_name,  # noqa: F401
                            sun_altitude, sun_pos)
from astro.catalog import BRIGHT_STARS, CATALOG, KIND_NAMES, _o  # noqa: F401
from astro.planets import (PLANET_DIAM_KM, PLANET_ELEMENTS, PLANETS, _helio, _kepler,  # noqa: F401
                           find_events, planet_state)
from astro.numpy_engine import (HAVE_NUMPY, PERF, _np_helio, _np_kepler, apply_perf, body_events,  # noqa: F401
                                np, np_altaz, np_crossings, np_gmst, np_jd, np_moon, np_moon_state,
                                np_planet, np_precess, np_sep, np_sun, scan_body, sky_series, star_altaz,
                                use_numpy)

if HAVE_NUMPY:  # these arrays only exist when NumPy does
    from astro.numpy_engine import CAT_DEC, CAT_RA, STAR_DEC, STAR_RA  # noqa: F401
from astro.numpy_engine import catalog_altaz_sep, np_moon_drop  # noqa: F401
from astronomy.scoring import (BORTLE_NELM, MOON_K, ang_sep, moon_drop, moon_flux_rel, moon_score_from_drop,  # noqa: F401
                               moon_sepf, score_dew, score_seeing, score_transparency, score_wind,
                               seeing_fwhm, seeing_label, sky_nelm, verdict)
from astronomy.camera import PHONE_PRESETS, camera_numbers  # noqa: F401
from astronomy.optics import build_combos, drift_seconds, fmt_angle, quality_note, scope_numbers  # noqa: F401
from planner.planner import (DEEP_KINDS, HAVE_ASTROPY, PLAN_KINDS, PLAN_WEIGHTS, PLANET_NOTES, _astropy,  # noqa: F401
                             _pack, airmass, compute_positions, engine_check, plan_group, plan_info,
                             plan_targets, positions_astropy, positions_numpy, positions_scalar,
                             recommend_view, run_planner)
from weather.analysis import (analyze, build_hours, build_insights, fmt_clock, pick_window,  # noqa: F401
                              planet_rows, rank_targets, suggest_combo, tonight_window)
from weather.api import API_AIR, API_FORECAST, BASE_VARS, UPPER_VARS, fetch_weather, http_json  # noqa: F401
from weather.geocoding import API_GEO, geocode  # noqa: F401

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

CARD = "#1b1b1b"
DEEP = "#0b1020"
ACCENT = "#1f6aa5"

# ===========================================================================
# ASTRONOMY (pure python, no ephemeris download)
# ===========================================================================
PLANET_COLORS = {"Mercury": "#b8b0a0", "Venus": "#fff2c0", "Mars": "#ff8a5c", "Jupiter": "#f0d9a8",
                 "Saturn": "#e8d28a", "Uranus": "#9be8e8", "Neptune": "#7ea0ff"}


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


# ===========================================================================
# UI
# ===========================================================================
ALT_W, ALT_H = 600, 300
ALT_BANDS = ["#3d6a9e", "#2a3a6a", "#1a2650", "#101a3a", "#0a0d18"]
ALT_COLORS = ["#5ec8ff", "#ff9f5e", "#7ee787", "#ff7ab8", "#c9a7ff", "#f2e05e", "#6fe3d0", "#ff6b6b"]
CAM_MODES = ["Prime focus (camera at the focuser)", "Phone at the eyepiece (afocal)"]
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
