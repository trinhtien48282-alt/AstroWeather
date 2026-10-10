"""Tonight page: score gauges, best window, stat cards, insights and tables."""
import tkinter as tk
from datetime import datetime, timedelta, timezone

import customtkinter as ctk

from astro.catalog import KIND_NAMES
from astronomy.optics import fmt_angle
from astronomy.scoring import score_dew, score_wind, seeing_label, verdict
from gui.theme import CARD, conv_wind, DEEP, fmt_temp, LEVEL_COLORS, score_color
from mathutil import clamp
from weather.analysis import fmt_clock


class TonightPage:
    """Tonight page: score gauges, best window, stat cards, insights and tables."""

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
