"""Planner page: controls, ranked list, plan detail and the planner worker hand-off."""
import copy
import threading
import tkinter as tk
import traceback
from datetime import datetime, timedelta, timezone
from tkinter import messagebox

import customtkinter as ctk

from astro.catalog import KIND_NAMES
from astro.numpy_engine import HAVE_NUMPY
from config import log_error, save_config
from gui.theme import ALT_COLORS, ALT_H, ALT_W, CARD, DEEP, score_color
from planner.planner import PLAN_KINDS, run_planner
from weather.analysis import fmt_clock


class PlannerPage:
    """Planner page: controls, ranked list, plan detail and the planner worker hand-off."""

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
