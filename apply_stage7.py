"""Stage 7 edit: creates weather/ and planner/ FROM main.py's own text and removes that code from main.py.
Stages 1-6 must already be applied. Nothing is retyped: the module bodies are the exact slices of main.py.

  weather/api.py        API_FORECAST, API_AIR, BASE_VARS, UPPER_VARS, http_json, fetch_weather
  weather/geocoding.py  API_GEO, geocode
  weather/analysis.py   build_hours, tonight_window, planet_rows, suggest_combo, rank_targets, pick_window, analyze,
                        fmt_clock, build_insights            (the whole "ANALYSIS" section)
  planner/planner.py    the whole "OBSERVING PLANNER (engine)" section + HAVE_ASTROPY

main.py keeps all AstroApp methods (GUI, threads, cache read/write); only the section code above is replaced by imports.
Handles LF or CRLF and preserves main.py's line endings. Every marker must match exactly once. Each generated module is
compiled and its global names are checked (nothing undefined) BEFORE anything is written; existing target files are never
overwritten. Usage: python apply_stage7.py path/to/main.py   (run from anywhere; modules are created next to main.py)
"""
import ast
import builtins
import dis
import os
import sys

path = sys.argv[1]
root = os.path.dirname(os.path.abspath(path))
with open(path, "rb") as f:
    src = f.read().decode("utf-8")

crlf, lf = src.count("\r\n"), src.count("\n")
if crlf == 0:
    NL = "\n"
elif crlf == lf:
    NL = "\r\n"
else:
    sys.exit("refusing: mixed line endings (%d CRLF of %d lines); nothing changed" % (crlf, lf))
assert src.count("\r") == crlf, "refusing: stray CR characters; nothing changed"


def nl(s):
    return s.replace("\n", NL)


TARGETS = ["weather/__init__.py", "weather/api.py", "weather/geocoding.py", "weather/analysis.py",
           "planner/__init__.py", "planner/planner.py"]
for t in TARGETS:
    if os.path.exists(os.path.join(root, t)):
        sys.exit(f"refusing: {t} already exists (Stage 7 already applied?); nothing changed")

ANCHOR = nl("from astronomy.optics import build_combos, drift_seconds, fmt_angle, quality_note, scope_numbers  # noqa: F401\n")
assert src.count(ANCHOR) == 1, "Stage 6 import not found exactly once (is Stage 6 applied?)"
assert "from weather." not in src and "from planner." not in src, "Stage 7 already applied"

# ---- 1. cut the contiguous region: WEATHER DATA .. engine_check ------------------------------------------------------
m = nl("# WEATHER DATA (Open-Meteo)\n")
assert src.count(m) == 1, "WEATHER DATA header not unique/found"
k = src.index(m)
i = src.rfind(NL, 0, k - len(NL)) + len(NL)
assert set(src[i:k].strip()) == {"#", " ", "="}, "unexpected line above the WEATHER DATA header"
assert src.count(nl("def engine_check(")) == 1, "def engine_check not unique/found"
e0 = src.index(nl("def engine_check("))
end = nl('    return "\\n".join(lines)\n\n\n')
assert src.count(end, e0) >= 1, "engine_check end not found"
j = src.index(end, e0) + len(end)
region = src[i:j].replace("\r\n", "\n")
src = src[:i] + src[j:]

# ---- 2. split the region into its three sections -----------------------------------------------------------------
TITLES = ["# WEATHER DATA (Open-Meteo)", "# ANALYSIS", "# OBSERVING PLANNER (engine): pure functions, no GUI calls, safe for a worker thread"]
idx = []
for t in TITLES:
    assert region.count(t + "\n") == 1, f"section header not unique/found: {t}"
    idx.append(region.index(t + "\n"))
assert idx == sorted(idx), "sections are not in the expected order"


def body(n):
    start = region.index("\n", region.index("\n", idx[n]) + 1) + 1            # after the closing separator line
    stop = region.rfind("\n", 0, idx[n + 1] - 1) + 1 if n < 2 else len(region)  # before the next opening separator
    return region[start:stop].strip("\n")


wx_b, an_b, pl_b = body(0), body(1), body(2)


def top(b):
    tree = ast.parse(b)
    funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assigns = [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    others = [type(n).__name__ for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.Assign))]
    return funcs, assigns, others


f, a, o = top(wx_b)
assert f == ["http_json", "fetch_weather", "geocode"] and a == ["API_FORECAST", "API_AIR", "API_GEO", "BASE_VARS", "UPPER_VARS"] and not o, (f, a, o)
f, a, o = top(an_b)
assert f == ["build_hours", "tonight_window", "planet_rows", "suggest_combo", "rank_targets", "pick_window", "analyze",
             "fmt_clock", "build_insights"] and not a and not o, (f, a, o)
f, a, o = top(pl_b)
assert f == ["plan_group", "plan_targets", "plan_info", "_pack", "positions_numpy", "positions_scalar", "_astropy",
             "positions_astropy", "compute_positions", "airmass", "recommend_view", "run_planner", "engine_check"] \
    and a == ["DEEP_KINDS", "PLAN_KINDS", "PLAN_WEIGHTS", "PLANET_NOTES", "_AP"] and not o, (f, a, o)

geo_line = 'API_GEO = "https://geocoding-api.open-meteo.com/v1/search"\n'
assert wx_b.count(geo_line) == 1 and wx_b.count("def geocode(name):") == 1
g = wx_b.index("def geocode(name):")
api_b = wx_b[:g].replace(geo_line, "").strip("\n")
geo_b = geo_line + "\n\n" + wx_b[g:]

HAVE_ASTROPY = 'HAVE_ASTROPY = importlib.util.find_spec("astropy") is not None  # imported lazily, only if enabled\n'

MODULES = {
    "weather/__init__.py": '"""Weather services for AstroWeather: Open-Meteo access, geocoding and forecast analysis (no GUI)."""\n',
    "weather/api.py": (
        '"""Open-Meteo access: HTTP/JSON retrieval and the forecast + air-quality requests. Stdlib only, no GUI."""\n'
        "import json\nimport urllib.error\nimport urllib.parse\nimport urllib.request\n\nfrom config import log_error\n\n"
        + api_b + "\n"),
    "weather/geocoding.py": (
        '"""Open-Meteo place-name lookup. Stdlib only, no GUI."""\nimport urllib.parse\n\nfrom weather.api import http_json\n\n'
        + geo_b + "\n"),
    "weather/analysis.py": (
        '"""Forecast analysis: hourly scoring of the weather, tonight window, planets/targets tables and insights.\n\n'
        "Pure calculations (no GUI). NumPy is optional, as in astro.numpy_engine.\n"
        '"""\nimport math\nimport time\nfrom datetime import datetime, timedelta, timezone\n\n'
        "from astro.catalog import CATALOG\nfrom astro.core import jd_from_ts\n"
        "from astro.numpy_engine import body_events, catalog_altaz_sep, np, scan_body, sky_series, use_numpy\n"
        "from astro.planets import PLANETS, planet_state\n"
        "from astro.sun_moon import moon_info, moon_pos, next_phase_time, sun_altitude\n"
        "from astronomy.optics import build_combos\n"
        "from astronomy.scoring import (BORTLE_NELM, moon_drop, moon_score_from_drop, score_dew, score_seeing,\n"
        "                               score_transparency, score_wind, seeing_fwhm, seeing_label)\n"
        "from mathutil import clamp, deg, mean\nfrom weather.api import BASE_VARS, UPPER_VARS\n\n\n" + an_b + "\n"),
    "planner/__init__.py": '"""Observing planner for AstroWeather (no GUI)."""\n',
    "planner/planner.py": (
        '"""Observing planner engine: target positions (Astropy / NumPy / pure Python), scoring, ranking and view advice.\n\n'
        "Pure functions, no GUI calls, safe for a worker thread. NumPy and Astropy stay optional.\n"
        '"""\nimport importlib.util\nimport math\nimport time\nimport traceback\nimport warnings\n\n'
        "from astro.catalog import CATALOG, KIND_NAMES\nfrom astro.core import altaz, jd_from_ts, precess\n"
        "from astro.numpy_engine import (HAVE_NUMPY, PERF, np, np_altaz, np_jd, np_moon_drop, np_moon_state, np_planet,\n"
        "                                np_precess, np_sep, np_sun, sky_series, use_numpy)\n"
        "from astro.planets import PLANETS, planet_state\nfrom astro.sun_moon import moon_info, moon_pos, sun_altitude\n"
        "from astronomy.optics import build_combos\nfrom astronomy.scoring import BORTLE_NELM, ang_sep, seeing_fwhm\n"
        "from config import log_error\nfrom mathutil import clamp, deg, mean, rad\nfrom weather.analysis import fmt_clock\n\n"
        "if HAVE_NUMPY:  # these arrays only exist when NumPy does\n    from astro.numpy_engine import CAT_DEC, CAT_RA\n\n"
        + HAVE_ASTROPY + "\n\n" + pl_b + "\n"),
}


# ---- 3. check every generated module: it compiles and has no undefined global name ------------------------------------
def defined_names(tree):
    names = set(dir(builtins)) | {"__name__", "__file__", "__doc__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                names.add((al.asname or al.name).split(".")[0])
    for n in tree.body + [s for st in tree.body if isinstance(st, ast.If) for s in st.body]:
        if isinstance(n, ast.Assign):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return names


def global_loads(code):
    out = set()
    for ins in dis.get_instructions(code):
        if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME"):
            out.add(ins.argval)
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            out |= global_loads(c)
    return out


for name, text in MODULES.items():
    tree = ast.parse(text)
    missing = sorted(global_loads(compile(text, name, "exec")) - defined_names(tree))
    assert not missing, f"{name}: names used but not defined/imported: {missing}"

# ---- 4. edit main.py ----------------------------------------------------------------------------------------------------
ha = nl(HAVE_ASTROPY + "\n")
assert src.count(ha) == 1, "HAVE_ASTROPY line not unique/found (or changed)"
src = src.replace(ha, "")
for n in [x for x in ("build_hours", "analyze", "fetch_weather", "geocode", "run_planner", "engine_check", "fmt_clock",
                      "rank_targets", "planet_rows", "positions_numpy", "recommend_view")]:
    assert ("def " + n + "(") not in src, f"{n} still defined in main.py"
for cname in ("DEEP_KINDS", "PLAN_KINDS", "PLAN_WEIGHTS", "PLANET_NOTES", "API_FORECAST", "BASE_VARS"):
    assert nl("\n" + cname + " = ") not in src, f"{cname} still defined in main.py"

notes = []
for token, lines in (("urllib.", ["import urllib.error\n", "import urllib.parse\n", "import urllib.request\n"]),
                     ("warnings.", ["import warnings\n"]), ("importlib.", ["import importlib.util\n"])):
    trial = src
    for l in lines:
        assert trial.count(nl(l)) == 1, f"{l.strip()} not found exactly once in main.py"
        trial = trial.replace(nl(l), "")
    if token in trial:
        notes.append(f"kept {lines[0].strip()}... (still used in main.py)")
    else:
        src = trial
        notes.append("removed now-unused " + ", ".join(l.strip() for l in lines))
src = src.replace(nl("\n\n\nfrom config import ("), nl("\n\nfrom config import ("), 1)   # tidy the blank line the removal left

src = src.replace(ANCHOR, ANCHOR + nl(
    "from planner.planner import (DEEP_KINDS, HAVE_ASTROPY, PLAN_KINDS, PLAN_WEIGHTS, PLANET_NOTES, _astropy,  # noqa: F401\n"
    "                             _pack, airmass, compute_positions, engine_check, plan_group, plan_info,\n"
    "                             plan_targets, positions_astropy, positions_numpy, positions_scalar,\n"
    "                             recommend_view, run_planner)\n"
    "from weather.analysis import (analyze, build_hours, build_insights, fmt_clock, pick_window,  # noqa: F401\n"
    "                              planet_rows, rank_targets, suggest_combo, tonight_window)\n"
    "from weather.api import API_AIR, API_FORECAST, BASE_VARS, UPPER_VARS, fetch_weather, http_json  # noqa: F401\n"
    "from weather.geocoding import API_GEO, geocode  # noqa: F401\n"), 1)

out = src.encode("utf-8")
assert (b"\r\n" in out) == (NL == "\r\n") and out.count(b"\n") == (out.count(b"\r\n") if NL == "\r\n" else out.count(b"\n"))

# ---- 5. write (new files first, then main.py) --------------------------------------------------------------------------
for name, text in MODULES.items():
    p = os.path.join(root, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
with open(path, "wb") as f:
    f.write(out)
print("ok (%s line endings preserved); created %d files" % ("CRLF" if NL == "\r\n" else "LF", len(MODULES)))
for n in notes:
    print("  main.py:", n)
