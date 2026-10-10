"""The AstroWeather window: shell, page switching and the data-flow / worker / event-queue plumbing."""
import copy
import json
import os
import queue
import threading
import time
import traceback
from datetime import datetime

import customtkinter as ctk

from astro.numpy_engine import apply_perf
from config import CACHE_PATH, CONFIG_DIR, load_config, log_error
from gui.altitude_graph import AltitudeGraph
from gui.calculators_page import CalculatorsPage
from gui.forecast_page import ForecastPage
from gui.planner_page import PlannerPage
from gui.settings_page import SettingsPage
from gui.sky_page import SkyPage
from gui.theme import CARD
from gui.tonight_page import TonightPage
from weather.analysis import analyze
from weather.api import fetch_weather
from weather.geocoding import geocode


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")


class AstroApp(TonightPage, ForecastPage, SkyPage, CalculatorsPage, PlannerPage, AltitudeGraph, SettingsPage, ctk.CTk):
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
