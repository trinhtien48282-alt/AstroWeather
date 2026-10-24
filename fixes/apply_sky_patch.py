"""Run from the repo root: python apply_sky_patch.py. Each edit must match exactly once or the script stops before writing."""
import sys

EDITS = {
    "astro/stars.py": [
        ("        self.dec = [r[2] for r in kept]\n",
         "        self.dec = [r[2] for r in kept]\n        self.bv = [r[4] for r in kept]  # B-V or None\n"),
        ('"""[(alt, az, mag)] for stars', '"""[(alt, az, mag, bv or None)] for stars'),
        ("            return [(float(a[i]), float(z[i]), self.mags[i]) for i in idx]",
         "            return [(float(a[i]), float(z[i]), self.mags[i], self.bv[i]) for i in idx]"),
        ("        for r, d, m in zip(self.ra[:n], self.dec[:n], self.mags[:n]):\n"
         "            a, z = altaz(*precess(r, d, jd), jd, lat, lon)\n"
         "            if a > 0:\n"
         "                out.append((a, z, m))\n",
         "        for r, d, m, b in zip(self.ra[:n], self.dec[:n], self.mags[:n], self.bv[:n]):\n"
         "            a, z = altaz(*precess(r, d, jd), jd, lat, lon)\n"
         "            if a > 0:\n"
         "                out.append((a, z, m, b))\n"),
    ],
    "gui/sky_page.py": [
        ("from astro.sky_style import layer_colors, moon_color, moon_phase_spans, sky_colors",
         "from astro.sky_style import bv_color, layer_colors, moon_color, moon_phase_spans, sky_colors"),
        ("        self.sky_zoom, self.sky_pan = 1.0, [0.0, 0.0]\n        self.sky_hits,",
         "        self._sky_cache = None\n        self.sky_zoom, self.sky_pan = 1.0, [0.0, 0.0]\n        self.sky_hits,"),
        ("        n_ring = 16\n", "        n_ring = 24\n"),
        # old block of per-redraw ranking becomes a cached lookup; the setup lines move up to the star_altaz spot
        ('        cfg = self.cfg\n'
         '        nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)\n'
         '        sc = cfg["scope"]\n'
         '        obs = float(sc.get("obstruction_mm", 0) or 0)\n'
         '        ap_eff = math.sqrt(max(float(sc["aperture"]) ** 2 - obs * obs, 1.0))\n'
         '        combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])\n'
         '        cap = self.analysis["tonight"]["cap"] if self.analysis else 2 * ap_eff\n'
         '        rows = rank_targets(ts, lat, lon, ap_eff, nelm, combos, cap)\n',
         '        rows = state["rows"]\n'),
        ("        s_alts, s_azs = star_altaz(jd, lat, lon)\n",
         '        cfg = self.cfg\n'
         '        nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)\n'
         '        sc = cfg["scope"]\n'
         '        obs = float(sc.get("obstruction_mm", 0) or 0)\n'
         '        ap_eff = math.sqrt(max(float(sc["aperture"]) ** 2 - obs * obs, 1.0))\n'
         '        combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])\n'
         '        cap = self.analysis["tonight"]["cap"] if self.analysis else 2 * ap_eff\n'
         '        state = self._sky_state(ts, jd, lat, lon, ap_eff, nelm, combos, cap)\n'
         '        s_alts, s_azs = state["stars"]\n'),
        ("            for alt, az, mag in fset.visible(jd, lat, lon, mag_lim):",
         "            for alt, az, mag, bv in fset.visible(jd, lat, lon, mag_lim):"),
        ('fill="#c9d3f0",', "fill=bv_color(bv),"),
        ('        planet_list = []\n'
         '        for name in PLANETS:\n'
         '            st = planet_state(name, jd)\n'
         '            alt, az = altaz(st["ra"], st["dec"], jd, lat, lon)\n'
         '            planet_list.append((name, st, alt, az))\n'
         '            if alt > 0:\n',
         '        planet_list = state["planets"]\n'
         '        for name, st, alt, az in planet_list:\n'
         '            if alt > 0:\n'),
        ("        mi = moon_info(ts, lat, lon)\n", '        mi = state["moon"]\n'),
        ("            m = 3 * fs\n            c.create_rectangle(x - m, y - m, x + m, y + m, outline=col)\n",
         "            m = 3 * fs\n"
         '            kind = r["obj"]["kind"]\n'
         '            if kind in ("OC", "GC"):\n'
         "                c.create_oval(x - m, y - m, x + m, y + m, outline=col)\n"
         '            elif kind == "GX":\n'
         "                c.create_line(x - m, y, x, y - m, x + m, y, x, y + m, x - m, y, fill=col)\n"
         "            else:\n"
         "                c.create_rectangle(x - m, y - m, x + m, y + m, outline=col)\n"),
        ('"Square ', '"Marker '),
        ('Shapes do not encode the object type: click one "', 'Shape: circle = cluster, diamond = galaxy, square = other. Click one "'),
        ("    def draw_sky(self, table=True):\n",
         "    def _sky_state(self, ts, jd, lat, lon, ap_eff, nelm, combos, cap):\n"
         '        """Everything that depends only on time, place and gear (not on zoom, pan or toggles): cached, so those redraws skip it."""\n'
         '        key = (ts, lat, lon, round(ap_eff, 3), nelm, round(cap, 2), tuple((c["label"], round(c["mag"], 2)) for c in combos))\n'
         "        if self._sky_cache and self._sky_cache[0] == key:\n"
         "            return self._sky_cache[1]\n"
         "        planets = []\n"
         "        for name in PLANETS:\n"
         "            st = planet_state(name, jd)\n"
         '            alt, az = altaz(st["ra"], st["dec"], jd, lat, lon)\n'
         "            planets.append((name, st, alt, az))\n"
         '        state = {"stars": star_altaz(jd, lat, lon), "planets": planets, "moon": moon_info(ts, lat, lon),\n'
         '                 "rows": rank_targets(ts, lat, lon, ap_eff, nelm, combos, cap)}\n'
         "        self._sky_cache = (key, state)\n"
         "        return state\n\n"
         "    def draw_sky(self, table=True):\n"),
    ],
}

staged = {}
for path, edits in EDITS.items():
    text = open(path, encoding="utf-8").read()
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit(f"{path}: expected 1 match, found {text.count(old)} for:\n{old[:120]}")
        text = text.replace(old, new)
    staged[path] = text
for path, text in staged.items():
    open(path, "w", encoding="utf-8").write(text)
    print("patched", path)
