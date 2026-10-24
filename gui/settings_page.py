"""Settings page: location search, units, performance switches and gear."""
import threading
import time
import traceback
from gui.qt import messagebox

from gui import qt

from astro.numpy_engine import apply_perf, HAVE_NUMPY
from config import log_error, save_config
from gui.theme import DEEP
from planner.planner import engine_check, HAVE_ASTROPY
from weather.analysis import build_insights


class SettingsPage:
    """Settings page: location search, units, performance switches and gear."""

    def build_settings(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        body = qt.ScrollableFrame(page, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=18, pady=(0, 14))
        c = self.card(body, "Location")
        row = qt.Frame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        self.search_entry = qt.Entry(row, width=300, placeholder_text="Search a city or town", font=self.f_ui)
        self.search_entry.pack(side="left")
        qt.Button(row, text="Search", width=80, font=self.f_ui, command=self.do_search).pack(side="left", padx=8)
        self.geo_status = qt.Label(row, text="", font=self.f_small, text_color="#8a93a6")
        self.geo_status.pack(side="left", padx=8)
        self.geo_frame = qt.Frame(c, fg_color="transparent")
        self.geo_frame.pack(fill="x", padx=16, pady=4)
        row = qt.Frame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 12))
        loc = self.cfg["location"]
        self.ent_lat = qt.Entry(row, width=110, font=self.f_ui)
        self.ent_lat.insert(0, f"{loc['lat']:.4f}")
        self.ent_lon = qt.Entry(row, width=110, font=self.f_ui)
        self.ent_lon.insert(0, f"{loc['lon']:.4f}")
        qt.Label(row, text="Latitude", font=self.f_ui).pack(side="left")
        self.ent_lat.pack(side="left", padx=(6, 14))
        qt.Label(row, text="Longitude", font=self.f_ui).pack(side="left")
        self.ent_lon.pack(side="left", padx=(6, 14))
        qt.Button(row, text="Use these coordinates", width=170, font=self.f_ui, command=self.use_coords).pack(side="left")

        c = self.card(body, "Sky and units")
        row = qt.Frame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(2, 12))
        qt.Label(row, text="Bortle class (light pollution)", font=self.f_ui).pack(side="left")
        self.opt_bortle = qt.ComboBox(row, values=[str(i) for i in range(1, 10)], width=70, command=self.on_bortle)
        self.opt_bortle.set(str(self.cfg["bortle"]))
        self.opt_bortle.pack(side="left", padx=(8, 24))
        qt.Label(row, text="Temperature", font=self.f_ui).pack(side="left")
        self.opt_temp = qt.ComboBox(row, values=["C", "F"], width=70, command=self.on_units)
        self.opt_temp.set(self.cfg["units"]["temp"])
        self.opt_temp.pack(side="left", padx=(8, 24))
        qt.Label(row, text="Wind", font=self.f_ui).pack(side="left")
        self.opt_wind = qt.ComboBox(row, values=["km/h", "m/s", "mph"], width=80, command=self.on_units)
        self.opt_wind.set(self.cfg["units"]["wind"])
        self.opt_wind.pack(side="left", padx=8)

        c = self.card(body, "Performance")
        self.var_np = qt.BoolVar(value=bool(self.cfg["perf"].get("numpy", True)) and HAVE_NUMPY)
        self.var_ap = qt.BoolVar(value=bool(self.cfg["perf"].get("astropy", False)) and HAVE_ASTROPY)
        sw = qt.Switch(c, text="Hardware-accelerated math (NumPy vector engine, uses your CPU's SIMD units)", variable=self.var_np, command=self.on_perf, font=self.f_ui)
        sw.pack(anchor="w", padx=16, pady=(2, 4))
        if not HAVE_NUMPY:
            sw.configure(state="disabled", text="Hardware-accelerated math: needs  pip install numpy")
        sw2 = qt.Switch(c, text="High-precision positions (Astropy, optional: Moon to arcseconds, refraction)", variable=self.var_ap, command=self.on_perf, font=self.f_ui)
        sw2.pack(anchor="w", padx=16, pady=4)
        if not HAVE_ASTROPY:
            sw2.configure(state="disabled", text="High-precision positions: needs  pip install astropy")
        qt.Label(c, text="No GPU is used: these arrays are far too small to benefit from one, and the speed-up comes from vectorised CPU math. "
                            "Switch it off to compare with the plain-Python engine.", font=self.f_small, text_color="#8a93a6", wraplength=860,
                    justify="left", anchor="w").pack(anchor="w", padx=16)
        row = qt.Frame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(6, 12))
        self.btn_engine = qt.Button(row, text="Run engine check", width=150, font=self.f_ui, command=self.run_engine_check)
        self.btn_engine.pack(side="left")
        self.lbl_engine = qt.Label(row, text="", font=self.f_mono_s, justify="left", anchor="w")
        self.lbl_engine.pack(side="left", padx=14)

        c = self.card(body, "Your telescope")
        self.gear = {}
        sc = self.cfg["scope"]
        for key, label, val in (("name", "Name", sc.get("name", "")), ("aperture", "Aperture (mm)", sc["aperture"]),
                                ("focal_length", "Focal length (mm)", sc["focal_length"]),
                                ("obstruction_mm", "Secondary mirror shadow (mm, 0 if unknown)", sc.get("obstruction_mm", 0)),
                                ("mount", "Mount", sc.get("mount", "AZ"))):
            row = qt.Frame(c, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            qt.Label(row, text=label, width=330, anchor="w", font=self.f_ui).pack(side="left")
            e = qt.Entry(row, width=160, font=self.f_ui)
            e.insert(0, str(val))
            e.pack(side="left")
            self.gear[key] = e
        qt.Label(c, text="Eyepieces, one per line:  name, focal length mm, apparent FOV deg", font=self.f_small,
                    text_color="#8a93a6").pack(anchor="w", padx=16, pady=(10, 0))
        self.box_eps = qt.TextBox(c, height=90, font=self.f_mono, fg_color=DEEP)
        self.box_eps.pack(fill="x", padx=16, pady=4)
        self.box_eps.insert("1.0", "\n".join(f"{e['name']}, {e['fl']:g}, {e['afov']:g}" for e in self.cfg["eyepieces"]))
        qt.Label(c, text="Barlows / reducers, one per line:  name, factor", font=self.f_small, text_color="#8a93a6").pack(anchor="w", padx=16, pady=(6, 0))
        self.box_bl = qt.TextBox(c, height=64, font=self.f_mono, fg_color=DEEP)
        self.box_bl.pack(fill="x", padx=16, pady=4)
        self.box_bl.insert("1.0", "\n".join(f"{b['name']}, {b['factor']:g}" for b in self.cfg["barlows"]))
        qt.Button(c, text="Save gear", width=120, font=self.f_ui, command=self.save_gear).pack(anchor="w", padx=16, pady=(6, 14))

        c = self.card(body, "How the scores work")
        qt.Label(c, justify="left", anchor="w", wraplength=900, font=self.f_small, text_color="#b6bfd1", text=(
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
        self.reanalyze()

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
        self.geo_req += 1
        threading.Thread(target=self.geo_worker, args=(name, self.geo_req), daemon=True).start()

    def show_geo_results(self, results):
        for w in self.geo_frame.winfo_children():
            w.destroy()
        self.geo_status.configure(text="" if results else "no matches")
        for r in results:
            qt.Button(self.geo_frame, text=f"{r['name']}   ({r['lat']:.3f}, {r['lon']:.3f})", anchor="w", font=self.f_ui,
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
        self.plan, self.plot_set, self.plan_sel = None, [], None
        self.plan_req += 1  # a planner run still in flight belongs to the old place: drop its answer
        self.plan_busy = False
        if "planner" in self.built:  # these widgets exist only after the page was visited
            self.btn_plan.configure(state="normal")
            self.plan_status.configure(text="Local time, format YYYY-MM-DD HH:MM")
            for e in (self.plan_from, self.plan_to):  # old range may be in another timezone
                e.delete(0, "end")
            self.refresh_plan_list()
            self.show_plan_detail()
            self.draw_alt_graph()
        self.clear_tonight()
        if "forecast" in self.built:
            self.hm_labels.delete("all")
            self.hm_data.delete("all")
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
        self.reanalyze()
        self.update_calcs()

    def on_units(self, _value):
        self.cfg["units"] = {"temp": self.opt_temp.get(), "wind": self.opt_wind.get()}
        save_config(self.cfg)
        if self.analysis:
            a = self.analysis
            a["insights"] = build_insights(a["tonight"], a["moon"], self.cfg, a["combos"], a["offset"])
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
        self.reanalyze()
