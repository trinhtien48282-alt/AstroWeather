"""Run from the repo root AFTER apply_sky_patch.py: python apply_dso_patch.py. Every edit must match exactly once or nothing is written."""
import sys

EDITS = {
    "astro/stars.py": [
        ("    path = os.path.join(directory or data_dir(), STARS_FILE)\n",
         "    base = directory or data_dir()\n"
         '    binary = os.path.join(base, "binary", STARS_FILE.replace(".json", ".awst"))\n'
         "    if os.path.exists(binary):  # validated binary first; a corrupt file raises ValueError, no silent JSON fallback\n"
         "        from astro.star_catalog_binary import StarCatalogBinary\n"
         "        with StarCatalogBinary(binary) as cat:\n"
         "            return StarSet([(r.hip_id, r.ra, r.dec, r.magnitude, r.bv if r.has_bv else None) for r in cat], named)\n"
         "    path = os.path.join(base, STARS_FILE)\n"),
    ],
    "config.py": [
        ('"sky": {"constellation_lines": False, "constellation_names": False, "star_mag_limit": 5.0},',
         '"sky": {"constellation_lines": False, "constellation_names": False, "star_mag_limit": 5.0, "dso": False, "dso_mag_limit": 9.0},'),
    ],
    "scripts/convert_catalogs.py": [
        ('                                f"{message}",\n',
         "                                f\"feature {index} id={feature.get('id')!r}: {message}\",\n"),
    ],
    "AstroWeather.spec": [
        ('if os.path.isdir(os.path.join(SPECPATH, "data")):\n    datas.append((os.path.join(SPECPATH, "data"), "data"))\n',
         '# runtime data only: binary catalogues, constellation files and the star JSON fallback (not the large source JSONs)\n'
         'for _f in ("binary", "constellations.json", "constellations.lines.json", "stars.6.json"):\n'
         '    _p = os.path.join(SPECPATH, "data", _f)\n'
         '    if os.path.exists(_p):\n'
         '        datas.append((_p, os.path.join("data", _f)))\n'),
    ],
    "gui/sky_page.py": [
        ("import wiki\n", "import wiki\nfrom astro.dso_layer import get_dsos\n"),
        ("from astro.catalog import BRIGHT_STARS, KIND_NAMES", "from astro.catalog import BRIGHT_STARS, CATALOG, KIND_NAMES"),
        ('(("constellation_lines", "Lines"), ("constellation_names", "Names"))',
         '(("constellation_lines", "Lines"), ("constellation_names", "Names"), ("dso", "DSO"))'),
        ('        if kind == "star":\n            name, ra_h, dec, mag, alt, az = p\n',
         '        if kind == "xdso":\n'
         "            o, alt, az = p\n"
         "            size = f\"size {o['size']:.1f}'\" if o[\"size\"] > 0 else \"size unknown\"\n"
         "            lines = [o[\"id\"], f\"{KIND_NAMES[o['kind']]}, mag {o['mag']:.1f}, {size}\",\n"
         "                     f\"RA {_ra_text(o['ra'] / 15.0)}  Dec {o['dec']:+.1f} deg  (J2000)\",\n"
         "                     f\"At chart time: altitude {alt:.0f} deg, azimuth {az:.0f} deg\"]\n"
         '            titles = [o["id"]] + (["Messier " + o["id"][1:]] if o["id"][0] == "M" and o["id"][1:].isdigit() else [])\n'
         "            return lines, titles\n"
         '        if kind == "star":\n            name, ra_h, dec, mag, alt, az = p\n'),
        ('        planet_list = state["planets"]\n',
         '        if sky.get("dso"):  # extra objects from the AWDS binaries; the hand-made catalogue above keeps its ratings\n'
         '            dso_lim = float(sky.get("dso_mag_limit", 9.0))\n'
         '            dset, derr = get_dsos([(o["ra"] * 15.0, o["dec"]) for o in CATALOG], dso_lim)\n'
         '            if derr and derr != getattr(self, "_dso_err", None):\n'
         "                self._dso_err = derr\n"
         "                log_error(derr)\n"
         "            for alt, az, row in dset.visible(jd, lat, lon, dso_lim):\n"
         "                x, y = project(alt, az)\n"
         "                if not vis(x, y):\n"
         "                    continue\n"
         "                m = 2.5 * fs\n"
         '                if row["kind"] in ("OC", "GC"):\n'
         '                    c.create_oval(x - m, y - m, x + m, y + m, outline="#7f8fb8")\n'
         '                elif row["kind"] == "GX":\n'
         '                    c.create_line(x - m, y, x, y - m, x + m, y, x, y + m, x - m, y, fill="#7f8fb8")\n'
         "                else:\n"
         '                    c.create_rectangle(x - m, y - m, x + m, y + m, outline="#7f8fb8")\n'
         "                if z >= 2.5:\n"
         '                    c.create_text(x + m + 3, y, text=row["id"], anchor="w", fill="#7f8fb8", font=font(8))\n'
         '                hits.append((x, y, max(7.0, m + 4), ("xdso", row["id"]), (row, alt, az)))\n'
         '        planet_list = state["planets"]\n'),
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
