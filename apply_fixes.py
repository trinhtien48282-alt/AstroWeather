"""Apply the AstroWeather bug fixes. Run from the repo root:  python apply_fixes.py

Every edit must match exactly once. If any edit fails, NOTHING is written.
Keeps each file's line endings (CRLF or LF).
"""
import os
import sys

E = []  # (path, old, new)


def R(path, old, new):
    E.append((path, old, new))


# ---------------------------------------------------------------- mathutil: unit helpers (shared by weather + gui)
R("mathutil.py", '''    return sum(vals) / len(vals) if vals else None
''', '''    return sum(vals) / len(vals) if vals else None


def conv_wind(kmh, units):
    u = units.get("wind", "km/h")
    return kmh / 3.6 if u == "m/s" else kmh * 0.621371 if u == "mph" else kmh


def conv_temp(c, units):
    return c * 9 / 5 + 32 if units.get("temp") == "F" else c


def conv_dtemp(dc, units):
    """A temperature DIFFERENCE (dew-point margin): scale only, no +32."""
    return dc * 9 / 5 if units.get("temp") == "F" else dc
''')

R("gui/theme.py", "from mathutil import clamp\n",
  "from mathutil import clamp, conv_dtemp, conv_temp, conv_wind  # noqa: F401  (re-exported for the pages)\n")
R("gui/theme.py", '''

def conv_wind(kmh, units):
    u = units.get("wind", "km/h")
    return kmh / 3.6 if u == "m/s" else kmh * 0.621371 if u == "mph" else kmh
''', "")

# ---------------------------------------------------------------- bug 1: Astropy switch ignored HAVE_ASTROPY
R("planner/planner.py", '    if PERF["astropy"]:\n', '    if PERF["astropy"] and HAVE_ASTROPY:\n')

# ---------------------------------------------------------------- bug 2: "None%" humidity
R("gui/forecast_page.py", "humidity {h['rh'] if h['rh'] is None else round(h['rh'])}%",
  "humidity {'-' if h['rh'] is None else round(h['rh'])}%")

# ---------------------------------------------------------------- bug 6: mixed C/F in forecast page
R("gui/forecast_page.py", "CARD, conv_wind, CW,", "CARD, conv_dtemp, conv_temp, conv_wind, CW,")
R("gui/forecast_page.py", '''(f"{h['spread']:.1f}", score_color''', '''(f"{conv_dtemp(h['spread'], u):.1f}", score_color''')
R("gui/forecast_page.py", "('%.1f deg' % h['dew'])", "('%.1f deg' % conv_temp(h['dew'], u))")
R("gui/forecast_page.py", "('%.1f' % h['spread'])", "('%.1f' % conv_dtemp(h['spread'], u))")
R("gui/tonight_page.py", "from gui.theme import CARD, conv_wind,", "from gui.theme import CARD, conv_dtemp, conv_wind,")
R("gui/tonight_page.py", "closest approach {sp:.1f} deg to dew point", "closest approach {conv_dtemp(sp, u):.1f} deg to dew point")

# ---------------------------------------------------------------- bug 3: Tonight page cleared on location change
R("gui/tonight_page.py", "    def fill_tonight(self):\n", '''    def clear_tonight(self):
        self.draw_gauge(self.g_dso, None, "Deep-sky score")
        self.draw_gauge(self.g_pl, None, "Planetary score")
        self.lbl_best.configure(text="-")
        self.lbl_best_sub.configure(text="")
        self.lbl_dark.configure(text="")
        for v, s in self.stat.values():
            v.configure(text="-", text_color="#ffffff")
            s.configure(text="")
        for w in self.ins_frame.winfo_children():
            w.destroy()
        self.lbl_targets.configure(text="")
        self.set_text(self.box_planets, "")
        self.set_text(self.box_targets, "")

    def fill_tonight(self):
''')

# ---------------------------------------------------------------- bugs 3+4 (+ stale plan range): set_location
R("gui/settings_page.py", '''        self.analysis = None
        self.plan = None
        self.refresh(force=True)
''', '''        self.analysis = None
        self.plan, self.plot_set, self.plan_sel = None, [], None
        self.plan_req += 1  # a planner run still in flight belongs to the old place: drop its answer
        self.plan_busy = False
        self.btn_plan.configure(state="normal")
        self.plan_status.configure(text="Local time, format YYYY-MM-DD HH:MM")
        for e in (self.plan_from, self.plan_to):  # old range may be in another timezone
            e.delete(0, "end")
        self.clear_tonight()
        self.hm_labels.delete("all")
        self.hm_data.delete("all")
        self.refresh_plan_list()
        self.show_plan_detail()
        self.draw_alt_graph()
        self.refresh(force=True)
''')

# ---------------------------------------------------------------- bug 5: venv from BUILDING.md
# (.gitignore handled below)

# ---------------------------------------------------------------- bug 7: insight units
R("weather/analysis.py", "from mathutil import clamp, deg, mean\n", "from mathutil import clamp, conv_dtemp, conv_wind, deg, mean\n")
R("weather/analysis.py", "def build_insights(tn, moon, cfg, combos, off, ap_eff):\n    ins = []\n",
  'def build_insights(tn, moon, cfg, combos, off):\n    units = cfg.get("units", {})\n    ins = []\n')
R("weather/analysis.py", "insights = build_insights(tn, moon, cfg, combos, off, ap_eff)", "insights = build_insights(tn, moon, cfg, combos, off)")
R("weather/analysis.py", "Gusts to {tn['gust']:.0f} km/h:", "Gusts to {conv_wind(tn['gust'], units):.0f} {units.get('wind', 'km/h')}:")
R("weather/analysis.py", "(temperature only {sp:.1f} degrees above dew point)", "(temperature only {conv_dtemp(sp, units):.1f} degrees above dew point)")
R("weather/analysis.py", "(spread {sp:.1f} degrees)", "(spread {conv_dtemp(sp, units):.1f} degrees)")
# keep the raw download so Bortle / gear / engine changes re-score without the network
R("weather/analysis.py", '"has_aq": any(h["aod"] is not None for h in hours), "fetched": time.time()}',
  '"has_aq": any(h["aod"] is not None for h in hours), "fetched": time.time(), "wx": wx, "aq": aq}')
# insights are text built at analysis time: rebuild them when the units change
R("gui/settings_page.py", "from planner.planner import engine_check, HAVE_ASTROPY\n",
  "from planner.planner import engine_check, HAVE_ASTROPY\nfrom weather.analysis import build_insights\n")
R("gui/settings_page.py", '''        save_config(self.cfg)
        if self.analysis:
            self.fill_tonight()
''', '''        save_config(self.cfg)
        if self.analysis:
            a = self.analysis
            a["insights"] = build_insights(a["tonight"], a["moon"], self.cfg, a["combos"], a["offset"])
            self.fill_tonight()
''')

# ---------------------------------------------------------------- bug 8: Dawes/Rayleigh use the same aperture as the planner
R("astronomy/optics.py", '"dawes": 116.0 / ap, "rayleigh": 138.0 / ap,', '"dawes": 116.0 / ap_eff, "rayleigh": 138.0 / ap_eff,')

# ---------------------------------------------------------------- no network re-download for Bortle / gear / engine
R("gui/app.py", "    def apply_analysis(self, a, status):\n", '''    def reanalyze(self):
        """Re-score the data already downloaded (Bortle, gear or engine changed): no network."""
        a = self.analysis
        if a:
            new = analyze(a["wx"], a["aq"], self.cfg, time.time())
            new["fetched"] = a["fetched"]
            self.apply_analysis(new, self.lbl_status.cget("text"))

    def apply_analysis(self, a, status):
''')
R("gui/settings_page.py", '''        apply_perf(self.cfg)
        save_config(self.cfg)
        if self.analysis:
            self.refresh(force=True)
''', '''        apply_perf(self.cfg)
        save_config(self.cfg)
        self.reanalyze()
''')
R("gui/settings_page.py", '''        self.cfg["bortle"] = int(value)
        save_config(self.cfg)
        if self.analysis:
            self.refresh(force=True)
''', '''        self.cfg["bortle"] = int(value)
        save_config(self.cfg)
        self.reanalyze()
''')
R("gui/settings_page.py", '''        save_config(self.cfg)
        self.update_calcs()
        if self.analysis:
            self.refresh(force=True)
''', '''        save_config(self.cfg)
        self.update_calcs()
        self.reanalyze()
''')

# ---------------------------------------------------------------- cache.json: atomic write, one temp file per request
R("gui/app.py", '''                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump({"lat": loc["lat"], "lon": loc["lon"], "fetched": time.time(), "wx": wx, "aq": aq}, f)
''', '''                tmp = f"{CACHE_PATH}.{req}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"lat": loc["lat"], "lon": loc["lon"], "fetched": time.time(), "wx": wx, "aq": aq}, f)
                os.replace(tmp, CACHE_PATH)
''')

# ---------------------------------------------------------------- stale geocode answers
R("gui/app.py", "        self.req_id, self.dirty = 0, set()\n",
  "        self.req_id, self.dirty = 0, set()\n        self.geo_req, self.last_try = 0, 0.0\n")
R("gui/app.py", '''    def geo_worker(self, name):
        try:
            self.events.put(("geo", geocode(name)))
        except Exception as e:
            self.events.put(("geo_error", str(e)))
''', '''    def geo_worker(self, name, req):
        try:
            self.events.put(("geo", req, geocode(name)))
        except Exception as e:
            self.events.put(("geo_error", req, str(e)))
''')
R("gui/app.py", '''                elif kind == "geo":
                    self.show_geo_results(ev[1])
                elif kind == "geo_error":
                    self.geo_status.configure(text="search failed: " + ev[1][:80])
''', '''                elif kind == "geo":
                    if ev[1] == self.geo_req:
                        self.show_geo_results(ev[2])
                elif kind == "geo_error":
                    if ev[1] == self.geo_req:
                        self.geo_status.configure(text="search failed: " + ev[2][:80])
''')
R("gui/settings_page.py", "        threading.Thread(target=self.geo_worker, args=(name,), daemon=True).start()\n",
  "        self.geo_req += 1\n        threading.Thread(target=self.geo_worker, args=(name, self.geo_req), daemon=True).start()\n")

# ---------------------------------------------------------------- offline: retry once per interval, not every minute
R("gui/app.py", "        self.busy = True\n        self.req_id += 1\n", "        self.busy = True\n        self.last_try = time.time()\n        self.req_id += 1\n")
R("gui/app.py", '        if time.time() - (self.analysis["fetched"] if self.analysis else 0) > mins * 60:\n',
  '        if time.time() - max(self.analysis["fetched"] if self.analysis else 0, self.last_try) > mins * 60:\n')

# ---------------------------------------------------------------- bad config values
R("config.py", '''        log_error(f"config load failed: {e}")
    return cfg
''', '''        log_error(f"config load failed: {e}")
    try:
        cfg["bortle"] = min(9, max(1, int(cfg["bortle"])))
    except (TypeError, ValueError):
        cfg["bortle"] = DEFAULT_CONFIG["bortle"]
    try:
        loc = cfg["location"]
        loc["lat"], loc["lon"] = float(loc["lat"]), float(loc["lon"])
        if not (-90 <= loc["lat"] <= 90 and -180 <= loc["lon"] <= 180):
            raise ValueError
    except (TypeError, ValueError, KeyError):
        cfg["location"] = copy.deepcopy(DEFAULT_CONFIG["location"])
    return cfg
''')

# ---------------------------------------------------------------- error.log cap
R("config.py", '''        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
''', '''        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 512 * 1024:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
''')

# ---------------------------------------------------------------- sky slider: relative to now, not to app start
R("gui/sky_page.py", "        self.sky_ts = self.sky_base + float(value) * 3600.0\n",
  "        self.sky_ts = time.time() + float(value) * 3600.0\n")
R("gui/sky_page.py", '''        self.box_sky.grid(row=1, column=1, sticky="nsew", padx=(6, 24), pady=(0, 14))
        self.sky_base = time.time()
''', '''        self.box_sky.grid(row=1, column=1, sticky="nsew", padx=(6, 24), pady=(0, 14))
''')
R("gui/sky_page.py", "        self.sky_base = time.time()\n        self.sky_ts = self.sky_base\n", "        self.sky_ts = time.time()\n")

# ---------------------------------------------------------------- packaging / docs
R("requirements.txt", "customtkinter\nnumpy", "customtkinter>=5.2\nnumpy>=1.26")
R("main.py", "import traceback\n\nfrom config import log_error\n",
  'import sys\nimport traceback\n\nif sys.version_info < (3, 12):  # the GUI code uses 3.12-only f-string syntax\n    sys.exit("AstroWeather needs Python 3.12 or newer.")\n\nfrom config import log_error\n')
R("README.md", "- Internet access for weather forecasts and location search\n",
  "- Internet access for weather forecasts and location search\n- Windows for the GUI as shipped: it uses Segoe UI / Consolas fonts and Windows mouse-wheel events (data paths and the calculation code are portable)\n")
R("astro/__init__.py", '"""Pure-Python astronomy for AstroWeather (no GUI, no NumPy)."""',
  '"""Astronomy for AstroWeather: pure-Python scalar code plus the optional NumPy engine (no GUI)."""')
R("docs/archive/ASTROWEATHER_CONTEXT.md", "**Phase 0 / Initial inspection unless repository evidence shows otherwise.**",
  "**Stages 1-8 done: config, astro, astronomy, weather, planner, gui and the PyInstaller spec are extracted. The packaged build is not yet verified on Windows (see BUILDING.md).**")


def main():
    texts, nl = {}, {}
    for path, old, new in E:
        if path not in texts:
            if not os.path.exists(path):
                sys.exit(f"missing file: {path} (run from the repo root)")
            with open(path, "r", encoding="utf-8", newline="") as f:
                texts[path] = f.read()
            nl[path] = "\r\n" if "\r\n" in texts[path] else "\n"
        o, n = old.replace("\n", nl[path]), new.replace("\n", nl[path])
        c = texts[path].count(o)
        if c != 1:
            sys.exit(f"NOTHING WRITTEN. {path}: expected 1 match, found {c} for:\n{old}")
        texts[path] = texts[path].replace(o, n)
    gi = ".gitignore"
    with open(gi, "r", encoding="utf-8", newline="") as f:
        g = f.read()
    if ".venv-build/" not in g:
        eol = "\r\n" if "\r\n" in g else "\n"
        texts[gi] = g + ("" if g.endswith(("\n", "\r")) else eol) + ".venv-build/" + eol
    for path, text in texts.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print(f"ok: {len(E)} edits, {len(texts)} files")


main()
