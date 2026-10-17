"""Sky chart page: live alt-az chart with a time slider, wheel zoom, drag pan, click-to-inspect and Wikipedia look-ups."""
import math
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from astro.constellations import get_constellations
from config import log_error, save_config

from gui import qt

import wiki
from astro.catalog import BRIGHT_STARS, KIND_NAMES
from astro.core import altaz, jd_from_ts
from astro.numpy_engine import star_altaz
from astro.planets import planet_state, PLANETS
from astro.sun_moon import moon_info, sun_pos
from astronomy.optics import build_combos, fmt_angle
from astronomy.scoring import BORTLE_NELM
from gui.theme import DEEP, PLANET_COLORS
from mathutil import clamp, rad
from weather.analysis import rank_targets

ZOOM_MAX = 8.0
# Wikipedia titles that differ from the catalog name (the plain name is a disambiguation page or another article)
WIKI_TITLES = {"Mercury": ["Mercury (planet)"], "Castor": ["Castor (star)"], "Pollux": ["Pollux (star)"],
               "Mimosa": ["Beta Crucis"], "Rigil Kent": ["Alpha Centauri"], "Kaus Aus.": ["Kaus Australis"],
               "Hadar": ["Beta Centauri"], "Eps Lyr": ["Epsilon Lyrae"]}


SKY_LEGEND = (
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


def _ra_text(ra_h):
    h, m = divmod(round(ra_h * 60.0, 1), 60.0)
    return f"{int(h)}h {m:04.1f}m"


class SkyPage:
    """Sky chart page: live alt-az chart with a time slider, wheel zoom, drag pan, click-to-inspect and Wikipedia look-ups."""

    def build_sky(self, page):
        self.sky_zoom, self.sky_pan = 1.0, [0.0, 0.0]
        self.sky_hits, self.sky_sel, self.sky_press, self.sky_lines = [], None, None, []
        self.wiki_req, self.wiki_cache, self.wiki_url = 0, {}, ""
        page.grid_columnconfigure(0, weight=3)  # the chart takes the spare width, the info column keeps a readable minimum
        page.grid_columnconfigure(1, weight=1, minsize=380)
        page.grid_rowconfigure(2, weight=1)
        ctrl = qt.Frame(page, fg_color="transparent")
        ctrl.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 2))
        self.lbl_skytime = qt.Label(ctrl, text="", font=self.f_h2, width=210, anchor="w")
        self.lbl_skytime.pack(side="left")
        self.sky_slider = qt.Slider(ctrl, from_=-3, to=36, number_of_steps=156, width=360, command=self.on_sky_slider)
        self.sky_slider.set(0)
        self.sky_slider.pack(side="left", padx=10)
        qt.Button(ctrl, text="Now", width=60, font=self.f_ui, command=self.sky_now).pack(side="left")
        for text, f in (("-", 1 / 1.5), ("+", 1.5)):
            qt.Button(ctrl, text=text, width=34, font=self.f_ui, command=lambda f=f: self.sky_zoom_step(f)).pack(side="left", padx=(8, 0))
        qt.Button(ctrl, text="Fit", width=44, font=self.f_ui, command=self.sky_fit).pack(side="left", padx=(8, 0))
        for key, text in (("constellation_lines", "Lines"), ("constellation_names", "Names")):
            var = qt.BoolVar(value=bool(self.cfg["sky"][key]))
            qt.Switch(ctrl, text=text, variable=var, font=self.f_small,
        command=lambda k=key, v=var: self.on_sky_layer(k, v.get())).pack(side="left", padx=(12, 0))
        self.lbl_skyinfo = qt.Label(page, text="", font=self.f_small, text_color="#8a93a6", anchor="w")
        self.lbl_skyinfo.grid(row=1, column=0, columnspan=2, sticky="w", padx=26, pady=(0, 4))
        self.sky_canvas = qt.Canvas(page, width=380, height=380, bg="#0a0d18", highlightthickness=0)
        self.sky_canvas.grid(row=2, column=0, sticky="nsew", padx=(24, 8), pady=(0, 14))
        self.sky_canvas.bind("<Configure>", self.on_sky_resize)
        self.sky_canvas.bind("<MouseWheel>", self.on_sky_wheel)
        self.sky_canvas.bind("<ButtonPress-1>", self.on_sky_press)
        self.sky_canvas.bind("<B1-Motion>", self.on_sky_drag)
        self.sky_canvas.bind("<ButtonRelease-1>", self.on_sky_release)
        right = qt.Frame(page, fg_color="transparent")
        right.grid(row=2, column=1, sticky="nsew", padx=(6, 24), pady=(0, 14))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        self.box_info = qt.TextBox(right, height=250, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="word")
        self.box_info.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.btn_wiki = qt.Button(right, text="Open the Wikipedia article", width=190, font=self.f_small, state="disabled",
                                      command=self.open_wiki)
        self.btn_wiki.grid(row=1, column=0, sticky="w", pady=(0, 6))
        tabs = qt.TabView(right)
        tabs.grid(row=2, column=0, sticky="nsew")
        tabs.add("Visible now")
        tabs.add("Legend")
        self.box_sky = qt.TextBox(tabs.tab("Visible now"), font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_sky.pack(fill="both", expand=True)
        box_leg = qt.TextBox(tabs.tab("Legend"), font=self.f_mono, fg_color=DEEP, state="disabled", wrap="word")
        box_leg.pack(fill="both", expand=True)
        self.set_text(box_leg, SKY_LEGEND)
        self.set_text(self.box_info, "Click an object on the chart to see its details and a Wikipedia summary.\n\n"
                                     "Mouse wheel zooms, dragging pans when zoomed in, Fit resets the view.")

    # ---- redraw scheduling -----------------------------------------------------------------------------------------
    def sky_kick(self):
        """Throttle: at most one chart redraw per ~30 ms, however many events (slider, wheel, drag, resize) arrive."""
        if not self._sky_job:
            self._sky_job = self.after(30, self._sky_fast)

    def _sky_fast(self):
        self._sky_job = None
        self.draw_sky(table=False)

    def _sky_full(self):
        self._sky_job2 = None
        self.draw_sky()

    def on_sky_slider(self, value):
        # a drag fires dozens of events: redraw the chart at most every ~30 ms and the table once the drag settles
        self.sky_ts = time.time() + float(value) * 3600.0
        self.sky_kick()
        if self._sky_job2:
            self.after_cancel(self._sky_job2)
        self._sky_job2 = self.after(300, self._sky_full)

    def sky_now(self):
        self.sky_ts = time.time()
        self.sky_slider.set(0)
        self.draw_sky()

    def on_sky_resize(self, _event):
        if getattr(self, "current", None) == "sky":  # the other pages sit under this one and must not redraw it
            self.sky_kick()

    # ---- view: size, zoom, pan ---------------------------------------------------------------------------------------
    def sky_geometry(self):
        """Canvas size, centre and dome radius. The dome fills the smaller side, leaving room for the N/E/S/W letters."""
        c = self.sky_canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 100:  # not laid out yet
            w, h = 620, 620
        return w, h, w / 2.0, h / 2.0, max(60.0, min(w, h) / 2.0 - 26.0)

    def sky_zoom_at(self, mx, my, factor):
        w, h, cx, cy, R = self.sky_geometry()
        z0 = self.sky_zoom
        z1 = clamp(z0 * factor, 1.0, ZOOM_MAX)
        if z1 == z0:
            return
        k, (px, py) = z1 / z0, self.sky_pan
        self.sky_zoom = z1
        self.sky_pan = [(mx - cx) - k * ((mx - cx) - px), (my - cy) - k * ((my - cy) - py)]  # keeps the point under the cursor fixed
        self.sky_clamp_pan()
        self.sky_kick()

    def sky_zoom_step(self, factor):
        w, h, cx, cy, R = self.sky_geometry()
        self.sky_zoom_at(cx, cy, factor)

    def sky_fit(self):
        self.sky_zoom, self.sky_pan = 1.0, [0.0, 0.0]
        self.sky_kick()

    def on_sky_layer(self, key, value):
        self.cfg["sky"][key] = bool(value)
        save_config(self.cfg)
        self.sky_kick()

    def sky_clamp_pan(self):
        w, h, cx, cy, R = self.sky_geometry()
        lim = self.sky_zoom * R
        self.sky_pan = [clamp(self.sky_pan[0], -lim, lim), clamp(self.sky_pan[1], -lim, lim)] if self.sky_zoom > 1.0 else [0.0, 0.0]

    def on_sky_wheel(self, e):
        self.sky_zoom_at(e.x, e.y, 1.25 ** (e.delta / 120.0))

    def on_sky_press(self, e):
        self.sky_press = (e.x, e.y, self.sky_pan[0], self.sky_pan[1], False)

    def on_sky_drag(self, e):
        p = self.sky_press
        if not p:
            return
        moved = p[4] or abs(e.x - p[0]) + abs(e.y - p[1]) > 4
        self.sky_press = p[:4] + (moved,)
        if moved and self.sky_zoom > 1.0:
            self.sky_pan = [p[2] + e.x - p[0], p[3] + e.y - p[1]]
            self.sky_clamp_pan()
            self.sky_kick()

    def on_sky_release(self, e):
        p, self.sky_press = self.sky_press, None
        if p and not p[4]:  # a click, not the end of a pan
            self.pick_sky(e.x, e.y)

    # ---- picking and object info -------------------------------------------------------------------------------------
    def pick_sky(self, x, y):
        best, best_d = None, 1e9
        for hx, hy, hr, key, payload in self.sky_hits:
            d = math.hypot(hx - x, hy - y)
            if d <= hr and d <= best_d:  # later entries (planets, Moon) win ties over catalog objects
                best, best_d = (key, payload), d
        if best is None:
            if self.sky_sel is not None:
                self.sky_sel = None
                self.sky_kick()
            return
        self.sky_sel = best[0]
        self.show_object(*best)
        self.sky_kick()

    def describe_sky(self, key, p):
        """-> (info lines, candidate Wikipedia titles) for a clicked chart object."""
        kind = key[0]
        if kind == "dso":
            o = p["obj"]
            size = (f"separation {o['sep']:.1f}\"" if o["kind"] == "DS" else f"size {o['size']:.0f}'" if o["size"] >= 1
                    else f"size {o['size'] * 60:.0f}\"")
            lines = [f"{o['id']}  {o['name']}".rstrip(), f"{KIND_NAMES[o['kind']]}, mag {o['mag']:.1f}, {size}",
                     f"RA {_ra_text(o['ra'])}  Dec {o['dec']:+.1f} deg  (J2000)",
                     f"At chart time: altitude {p['alt']:.0f} deg, azimuth {p['az']:.0f} deg",
                     f"In your scope: {p['rating']} ({p['margin']:+.1f} mag margin)"]
            if p["drop"] > 0.05:
                lines.append(f"Moon: {p['sep']:.0f} deg away, costs about {p['drop']:.1f} mag of sky limit")
            if p["combo"]:
                cb = p["combo"]
                lines.append(f"Suggested view: {cb['label']} = {cb['mag']:.0f}x, {cb['tfov'] * 60:.0f}' field")
            titles = list(WIKI_TITLES.get(o["id"]) or ([o["id"]] if o["kind"] == "DS" else []))
            if o["name"]:
                titles = titles + [o["name"]]
            if o["id"][0] == "M" and o["id"][1:].isdigit():
                titles.append("Messier " + o["id"][1:])
            titles.append(o["id"])
            return lines, list(dict.fromkeys(titles))
        if kind == "star":
            name, ra_h, dec, mag, alt, az = p
            return ([name, f"Star, magnitude {mag:.2f}", f"RA {_ra_text(ra_h)}  Dec {dec:+.1f} deg  (J2000)",
                     f"At chart time: altitude {alt:.0f} deg, azimuth {az:.0f} deg"], WIKI_TITLES.get(name) or [name])
        if kind == "planet":
            name, st, alt, az = p
            side = "east of the Sun (evening sky)" if st["east"] else "west of the Sun (morning sky)"
            return ([name, f"Planet, magnitude {st['mag']:.1f}, disc {fmt_angle(st['diam'])}, {st['phase'] * 100:.0f}% lit",
                     f"Distance {st['dist']:.2f} AU, {st['elong']:.0f} deg {side}",
                     f"At chart time: altitude {alt:.0f} deg, azimuth {az:.0f} deg"], WIKI_TITLES.get(name) or [name])
        if kind == "moon":
            return (["Moon", f"{p['name']}, {p['illum'] * 100:.0f}% lit, age {p['age']:.1f} days",
                     f"Distance {p['dist_km']:.0f} km, apparent size {fmt_angle(p['ang_diam'])}",
                     f"At chart time: altitude {p['alt']:.0f} deg, azimuth {p['az']:.0f} deg"], ["Moon"])
        alt, az = p
        return (["Sun", f"At chart time: altitude {alt:.0f} deg, azimuth {az:.0f} deg",
                 "Never point a telescope at the Sun without a certified solar filter."], ["Sun"])

    def show_object(self, key, payload):
        lines, titles = self.describe_sky(key, payload)
        self.sky_lines, self.wiki_url = lines, ""
        self.btn_wiki.configure(state="disabled")
        self.wiki_req += 1
        tk_key = tuple(titles)
        if tk_key in self.wiki_cache:
            self.show_wiki(self.wiki_req, tk_key, self.wiki_cache[tk_key])
            return
        self.set_text(self.box_info, "\n".join(lines) + "\n\nWikipedia: looking up...")
        threading.Thread(target=self.wiki_worker, args=(self.wiki_req, tk_key), daemon=True).start()

    def wiki_worker(self, req, titles):
        try:
            self.events.put(("wiki", req, titles, wiki.summary(titles)))
        except Exception as e:  # offline, timeout, bad JSON: shown in the panel, not fatal
            self.events.put(("wiki", req, titles, f"{type(e).__name__}: {e}"))

    def show_wiki(self, req, titles, res):
        if not isinstance(res, str):  # cache answers, never errors
            self.wiki_cache[titles] = res
        if req != self.wiki_req:  # the user clicked something else meanwhile
            return
        if isinstance(res, str):
            tail = "Wikipedia lookup failed (offline?): " + res[:120]
        elif res is None:
            tail = "Wikipedia: no matching article found."
        else:
            tail = f"Wikipedia - {res['title']}\n{res['extract']}"
            self.wiki_url = res["url"]
            self.btn_wiki.configure(state="normal" if res["url"] else "disabled")
        self.set_text(self.box_info, "\n".join(self.sky_lines) + "\n\n" + tail)

    def open_wiki(self):
        if self.wiki_url:
            webbrowser.open(self.wiki_url)

    # ---- drawing -----------------------------------------------------------------------------------------------------
    def draw_sky(self, table=True):
        c = self.sky_canvas
        c.delete("all")
        W, H, cx, cy, R = self.sky_geometry()
        z, (pan_x, pan_y) = self.sky_zoom, self.sky_pan
        fs = clamp(R / 282.0, 0.85, 1.6)  # markers and fonts follow the chart size
        font = lambda n, bold=False: ("Segoe UI", max(7, round(n * fs))) + (("bold",) if bold else ())
        ox, oy, Rz = cx + pan_x, cy + pan_y, R * z  # dome centre and radius on screen
        loc = self.cfg["location"]
        lat, lon = float(loc["lat"]), float(loc["lon"])
        ts = self.sky_ts
        jd = jd_from_ts(ts)
        off = self.analysis["offset"] if self.analysis else 0
        s = sun_pos(jd)
        sun_alt, sun_az = altaz(s["ra"], s["dec"], jd, lat, lon)
        bg = "#0a0d18" if sun_alt < -18 else "#101a3a" if sun_alt < -12 else "#1a2650" if sun_alt < -6 else "#2a3a6a" if sun_alt < -0.8 else "#3d6a9e"
        c.create_oval(ox - Rz, oy - Rz, ox + Rz, oy + Rz, fill=bg, outline="#4a5d8f", width=2)
        for alt in (30, 60):
            r = Rz * (90 - alt) / 90.0
            c.create_oval(ox - r, oy - r, ox + r, oy + r, outline="#26335a", dash=(2, 4))
        c.create_line(ox, oy - Rz, ox, oy + Rz, fill="#1d2848")
        c.create_line(ox - Rz, oy, ox + Rz, oy, fill="#1d2848")

        def vis(x, y, m=20):
            return -m <= x <= W + m and -m <= y <= H + m

        for txt, x, y in (("N", ox, oy - Rz - 12), ("S", ox, oy + Rz + 12), ("E", ox - Rz - 12, oy), ("W", ox + Rz + 12, oy)):
            if vis(x, y, 0):
                c.create_text(x, y, text=txt, fill="#9fb2e0", font=font(12, True))
        if vis(ox, oy):
            c.create_text(ox + 4, oy - 4, text="zenith", fill="#3a4a78", font=font(8), anchor="w")

        def project(alt, az):
            r = Rz * (90.0 - alt) / 90.0
            return ox - r * math.sin(rad(az)), oy - r * math.cos(rad(az))
        
        sky = self.cfg["sky"]
        if sky["constellation_lines"] or sky["constellation_names"]:
            cset, err = get_constellations()
            if err and err != getattr(self, "_con_err", None):
                self._con_err = err
                log_error(err)
            if sky["constellation_lines"]:
                for a1, z1, a2, z2 in cset.segments(jd, lat, lon):
                    (x1, y1), (x2, y2) = project(a1, z1), project(a2, z2)
                    c.create_line(x1, y1, x2, y2, fill="#2f4a7a")
            if sky["constellation_names"]:
                for name, a, z in cset.label_positions(jd, lat, lon):
                    x, y = project(a, z)
                    if vis(x, y):
                        c.create_text(x, y, text=name, fill="#4d6aa8", font=font(8))

        hits = []  # (x, y, hit radius, key, payload): what a click at that spot selects

        s_alts, s_azs = star_altaz(jd, lat, lon)
        for (name, ra_h, dec, mag), alt, az in zip(BRIGHT_STARS, s_alts, s_azs):
            if alt <= 0:
                continue
            x, y = project(alt, az)
            if not vis(x, y):
                continue
            r = max(1.4, 3.3 - 0.85 * mag) * fs
            c.create_oval(x - r, y - r, x + r, y + r, fill="#e9eeff", outline="")
            if mag < 1.3 or z >= 2.0:
                c.create_text(x + r + 3, y, text=name, anchor="w", fill="#8e9bc4", font=font(8))
            hits.append((x, y, max(8.0, r + 4), ("star", name), (name, ra_h, dec, mag, alt, az)))

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
            if not vis(x, y):
                continue
            col = colors[r["rating"]]
            m = 3 * fs
            c.create_rectangle(x - m, y - m, x + m, y + m, outline=col)
            if (r["rating"] in ("Easy", "Moderate") and r["alt"] > 12) or (z >= 2.5 and r["rating"] != "Beyond"):
                c.create_text(x + m + 3, y, text=r["obj"]["id"], anchor="w", fill=col, font=font(8))
            hits.append((x, y, max(8.0, m + 5), ("dso", r["obj"]["id"]), r))

        planet_list = []
        for name in PLANETS:
            st = planet_state(name, jd)
            alt, az = altaz(st["ra"], st["dec"], jd, lat, lon)
            planet_list.append((name, st, alt, az))
            if alt > 0:
                x, y = project(alt, az)
                if not vis(x, y):
                    continue
                r = (max(3.0, 6.5 - 0.8 * st["mag"]) if st["mag"] < 3 else 3.0) * fs
                c.create_oval(x - r, y - r, x + r, y + r, fill=PLANET_COLORS[name], outline="")
                c.create_text(x + r + 3, y, text=name, anchor="w", fill=PLANET_COLORS[name], font=font(9, True))
                hits.append((x, y, max(10.0, r + 4), ("planet", name), (name, st, alt, az)))
        mi = moon_info(ts, lat, lon)
        if mi["alt"] > 0:
            x, y = project(mi["alt"], mi["az"])
            if vis(x, y):
                m = 9 * fs
                c.create_oval(x - m, y - m, x + m, y + m, fill="#e8e2c0", outline="#fff6c0")
                c.create_text(x + m + 4, y, text=f"Moon {mi['illum'] * 100:.0f}%", anchor="w", fill="#f2ecc8", font=font(9, True))
                hits.append((x, y, m + 4, ("moon",), mi))
        if sun_alt > 0:
            x, y = project(sun_alt, sun_az)
            if vis(x, y):
                m = 9 * fs
                c.create_oval(x - m, y - m, x + m, y + m, fill="#ffd34a", outline="")
                c.create_text(x + m + 4, y, text="Sun: never view without a solar filter", anchor="w", fill="#ffe08a", font=font(8))
                hits.append((x, y, m + 4, ("sun",), (sun_alt, sun_az)))
        for x, y, hr, key, _p in hits:
            if key == self.sky_sel:
                c.create_oval(x - hr, y - hr, x + hr, y + hr, outline="#ffffff", width=2)
        self.sky_hits = hits

        tz = timezone(timedelta(seconds=off))
        self.lbl_skytime.configure(text=datetime.fromtimestamp(ts, tz).strftime("%a %d %b  %H:%M"))
        self.lbl_skyinfo.configure(text=f"sun {sun_alt:+.0f} deg   Moon {mi['alt']:+.0f} deg, {mi['illum'] * 100:.0f}% lit   "
                                        f"green=easy yellow=moderate orange=hard in your scope   zoom {z:.1f}x")

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
