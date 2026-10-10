"""Forecast page: the hour-by-hour heat map and the per-hour detail box."""
import tkinter as tk
from datetime import datetime, timedelta, timezone

import customtkinter as ctk

from astronomy.scoring import score_wind, seeing_fwhm
from gui.theme import (BAND_COLORS, BAND_NAMES, CARD, conv_wind, CW, DEEP, fmt_temp, HDR, HEAT_ROWS, LBLW, RH,
                       score_color, text_on)
from mathutil import clamp, piecewise


class ForecastPage:
    """Forecast page: the hour-by-hour heat map and the per-hour detail box."""

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
