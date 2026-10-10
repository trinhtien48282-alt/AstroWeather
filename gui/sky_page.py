"""Sky chart page: live alt-az chart with a time slider."""
import math
import time
import tkinter as tk
from datetime import datetime, timedelta, timezone

import customtkinter as ctk

from astro.catalog import BRIGHT_STARS
from astro.core import altaz, jd_from_ts
from astro.numpy_engine import star_altaz
from astro.planets import planet_state, PLANETS
from astro.sun_moon import moon_info, sun_pos
from astronomy.optics import build_combos, fmt_angle
from astronomy.scoring import BORTLE_NELM
from gui.theme import DEEP, PLANET_COLORS
from mathutil import rad
from weather.analysis import rank_targets


class SkyPage:
    """Sky chart page: live alt-az chart with a time slider."""

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
