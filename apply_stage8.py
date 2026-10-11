"""Stage 8 (GUI extraction): splits main.py's AstroApp into gui/ modules and reduces main.py to the entry point.
Stages 1-7 must already be applied. Nothing is retyped: every method is the exact text of main.py's AstroApp method.

  gui/theme.py              colours, sizes, table layouts and the small presentation helpers
                            (CARD, DEEP, ACCENT, PLANET_COLORS, score_color, text_on, ALT_*, CAM_MODES, BAND_*, HEAT_ROWS,
                             CW/RH/HDR/LBLW, LEVEL_COLORS, fmt_temp, conv_wind)
  gui/tonight_page.py       TonightPage         build_tonight, draw_gauge, fill_tonight, fill_targets
  gui/forecast_page.py      ForecastPage        build_forecast, cell, draw_heatmap, on_heat_click, select_col
  gui/sky_page.py           SkyPage             build_sky, on_sky_slider, sky_now, draw_sky
  gui/calculators_page.py   CalculatorsPage     build_scope ... update_calcs   (the Telescope page; update_calcs is unchanged)
  gui/planner_page.py       PlannerPage         build_planner ... plot_preset
  gui/altitude_graph.py     AltitudeGraph       draw_alt_graph, on_alt_motion
  gui/settings_page.py      SettingsPage        build_settings ... save_gear
  gui/app.py                AstroApp(<the 7 page classes>, ctk.CTk): window shell, data flow, worker/event-queue plumbing
  main.py                   rewritten: original docstring + main() + the __main__ guard

Pages are mixin classes, so every method keeps its name, signature and `self` state exactly as before. Imports of each new module
are derived from the names its code actually uses and resolved from main.py's own import lines; the script refuses (writing
nothing) if a name cannot be resolved, if main.py has unexpected top-level code, or if a target file already exists.
Section banner comments between methods inside the class are not carried over. main.py keeps its line endings; new files use LF.
Usage: python apply_stage8.py path/to/main.py
"""
import ast
import builtins
import dis
import os
import sys
import textwrap

path = sys.argv[1]
root = os.path.dirname(os.path.abspath(path))
with open(path, "rb") as f:
    raw = f.read().decode("utf-8")
crlf, lf = raw.count("\r\n"), raw.count("\n")
if crlf == 0:
    NL = "\n"
elif crlf == lf:
    NL = "\r\n"
else:
    sys.exit("refusing: mixed line endings (%d CRLF of %d lines); nothing changed" % (crlf, lf))
assert raw.count("\r") == crlf, "refusing: stray CR characters; nothing changed"
T = raw.replace("\r\n", "\n")
lines = T.split("\n")

TARGETS = ["gui/__init__.py", "gui/theme.py", "gui/tonight_page.py", "gui/forecast_page.py", "gui/sky_page.py",
           "gui/calculators_page.py", "gui/planner_page.py", "gui/altitude_graph.py", "gui/settings_page.py", "gui/app.py"]
for t in TARGETS:
    if os.path.exists(os.path.join(root, t)):
        sys.exit(f"refusing: {t} already exists (Stage 8 already applied?); nothing changed")

GROUPS = [  # module, class, docstring, methods (original order)
    ("tonight_page", "TonightPage", "Tonight page: score gauges, best window, stat cards, insights and tables.",
     ["build_tonight", "draw_gauge", "fill_tonight", "fill_targets"]),
    ("forecast_page", "ForecastPage", "Forecast page: the hour-by-hour heat map and the per-hour detail box.",
     ["build_forecast", "cell", "draw_heatmap", "on_heat_click", "select_col"]),
    ("sky_page", "SkyPage", "Sky chart page: live alt-az chart with a time slider.",
     ["build_sky", "on_sky_slider", "sky_now", "draw_sky"]),
    ("calculators_page", "CalculatorsPage", "Telescope page: setup, calculators and the camera calculator.",
     ["build_scope", "entry_row", "out_label", "num", "apply_cam_preset", "on_cam_preset", "eyepiece_afov", "preset_moon",
      "schedule_calcs", "_run_calcs", "update_calcs"]),
    ("planner_page", "PlannerPage", "Planner page: controls, ranked list, plan detail and the planner worker hand-off.",
     ["build_planner", "plan_page_refresh", "plan_preset", "run_plan", "planner_worker", "show_plan", "refresh_plan_list",
      "select_plan", "show_plan_detail", "plot_preset"]),
    ("altitude_graph", "AltitudeGraph", "Planner altitude graph: canvas drawing and the hover read-out.",
     ["draw_alt_graph", "on_alt_motion"]),
    ("settings_page", "SettingsPage", "Settings page: location search, units, performance switches and gear.",
     ["build_settings", "on_perf", "run_engine_check", "do_search", "show_geo_results", "set_location", "use_coords",
      "on_bortle", "on_units", "save_gear"]),
]
APP_METHODS = ["__init__", "report_callback_exception", "build_ui", "show_page", "flush_dirty", "update_location_label", "card",
               "set_text", "load_cache", "refresh", "worker", "geo_worker", "tick", "pump", "apply_analysis"]
THEME = ["CARD", "DEEP", "ACCENT", "PLANET_COLORS", "score_color", "text_on", "ALT_W", "ALT_H", "ALT_BANDS", "ALT_COLORS", "CAM_MODES",
         "BAND_COLORS", "BAND_NAMES", "HEAT_ROWS", "CW", "RH", "HDR", "LBLW", "LEVEL_COLORS", "fmt_temp", "conv_wind"]
PRELUDE = ['ctk.set_appearance_mode("Dark")', 'ctk.set_default_color_theme("dark-blue")']

tree = ast.parse(T)
seg = lambda n: "\n".join(lines[n.lineno - 1:n.end_lineno])

# ---- 1. classify main.py's top level ---------------------------------------------------------------------------------
doc = None
NAME_MAP, theme_stmts, prelude, app_cls, main_fn, guard = {}, [], [], None, None, None


def add_imports(stmts):
    for n in stmts:
        if isinstance(n, ast.Import):
            for a in n.names:
                NAME_MAP[(a.asname or a.name).split(".")[0]] = ("import", a.name, a.asname)
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                NAME_MAP[a.asname or a.name] = ("from", n.module, a.name, a.asname)


def targets(n):
    if isinstance(n, ast.FunctionDef):
        return [n.name]
    out = []
    for t in n.targets:
        out += [e.id for e in (t.elts if isinstance(t, ast.Tuple) else [t])]
    return out


for k, n in enumerate(tree.body):
    if k == 0 and isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
        doc = n
    elif isinstance(n, (ast.Import, ast.ImportFrom)):
        add_imports([n])
    elif isinstance(n, ast.If) and not n.orelse and all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in n.body):
        add_imports(n.body)
    elif isinstance(n, ast.Expr) and seg(n) in PRELUDE:
        prelude.append(seg(n))
    elif isinstance(n, ast.ClassDef) and n.name == "AstroApp":
        app_cls = n
    elif isinstance(n, ast.FunctionDef) and n.name == "main":
        main_fn = n
    elif isinstance(n, ast.If) and seg(n).startswith('if __name__ == "__main__":'):
        guard = n
    elif isinstance(n, (ast.Assign, ast.FunctionDef)) and set(targets(n)) <= set(THEME):
        theme_stmts.append(n)
    else:
        sys.exit(f"refusing: unexpected top-level code at line {n.lineno} ({type(n).__name__}: {seg(n)[:60]!r}); nothing changed")
assert doc is not None and app_cls is not None and main_fn is not None and guard is not None, "main.py structure not recognised"
assert prelude == PRELUDE, f"expected the two ctk.set_* calls, found {prelude}"
head = lines[:doc.lineno - 1]
assert all(l.strip() == "" or l.startswith("#") for l in head), "unexpected code before the module docstring"
got = [x for n in theme_stmts for x in targets(n)]
assert sorted(got) == sorted(THEME), f"theme names differ: missing {sorted(set(THEME) - set(got))}, extra {sorted(set(got) - set(THEME))}"
assert [ast.unparse(b) for b in app_cls.bases] == ["ctk.CTk"], f"AstroApp bases changed: {[ast.unparse(b) for b in app_cls.bases]}"
assert all(isinstance(m, ast.FunctionDef) and not m.decorator_list for m in app_cls.body), "AstroApp body has non-method members"
methods = {m.name: m for m in app_cls.body}
expected = APP_METHODS + [m for g in GROUPS for m in g[3]]
assert sorted(methods) == sorted(expected) and len(methods) == len(app_cls.body), \
    f"AstroApp methods differ: missing {sorted(set(expected) - set(methods))}, extra {sorted(set(methods) - set(expected))}"

# ---- 2. name resolution -----------------------------------------------------------------------------------------------
for t in THEME:
    NAME_MAP[t] = ("from", "gui.theme", t, None)
for mod, cls, _doc, _m in GROUPS:
    NAME_MAP[cls] = ("from", f"gui.{mod}", cls, None)
NAME_MAP["AstroApp"] = ("from", "gui.app", "AstroApp", None)


def global_loads(code):
    out = set()
    for ins in dis.get_instructions(code):
        if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME"):
            out.add(ins.argval)
    for c in code.co_consts:
        if hasattr(c, "co_code"):
            out |= global_loads(c)
    return out


def own_names(tree_):
    s = set()
    for n in tree_.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            s.add(n.name)
        elif isinstance(n, ast.Assign):
            s |= set(targets(n))
    return s


def category(mod):
    top = mod.split(".")[0]
    if os.path.exists(os.path.join(root, top + ".py")) or os.path.isdir(os.path.join(root, top)) or top == "gui":
        return 2
    return 0 if top in getattr(sys, "stdlib_module_names", ()) or top in ("tkinter",) else 1


def render_imports(body_text, label):
    code = compile(body_text, label, "exec")
    need = global_loads(code) - set(dir(builtins)) - own_names(ast.parse(body_text)) - {"__name__"}
    missing = sorted(n for n in need if n not in NAME_MAP)
    assert not missing, f"{label}: names used but not resolvable from main.py's imports: {missing}"
    plain, froms = {}, {}
    for n in sorted(need):
        e = NAME_MAP[n]
        if e[0] == "import":
            plain[f"import {e[1]}" + (f" as {e[2]}" if e[2] else "")] = category(e[1])
        else:
            froms.setdefault(e[1], set()).add(e[2] + (f" as {e[3]}" if e[3] else ""))
    blocks = {0: [], 1: [], 2: []}
    for ln, cat in sorted(plain.items(), key=lambda kv: kv[0].split()[1]):
        blocks[cat].append(ln)
    for mod in sorted(froms):
        names = sorted(froms[mod], key=lambda s: s.lower())
        one = f"from {mod} import {', '.join(names)}"
        if len(one) <= 118:
            blocks[category(mod)].append(one)
        else:
            pre = f"from {mod} import ("
            wrapped = textwrap.wrap(", ".join(names), width=118 - len(pre))
            blocks[category(mod)].append(pre + ("\n" + " " * len(pre)).join(wrapped) + ")")
    return "\n\n".join("\n".join(b) for b in (blocks[0], blocks[1], blocks[2]) if b)


def method_text(name):
    return seg(methods[name])


def build_module(docstring, body_text, label):
    imps = render_imports(body_text, label)
    return f'"""{docstring}"""\n' + (imps + "\n\n\n" if imps else "\n") + body_text.rstrip("\n") + "\n"


MODULES = {}
# theme.py (statements in original order; two blank lines around functions, original grouping between assignments)
parts = []
prev = None
for n in theme_stmts:
    if prev is not None:
        gap = lines[prev.end_lineno:n.lineno - 1]
        blank = sum(1 for g in gap if g.strip() == "")
        parts.append("\n\n\n" if isinstance(n, ast.FunctionDef) or isinstance(prev, ast.FunctionDef) else ("\n" if blank == 0 else "\n\n"))
    parts.append(seg(n))
    prev = n
MODULES["gui/theme.py"] = build_module("Colours, sizes, table layouts and small presentation helpers shared by the GUI pages.",
                                       "".join(parts), "gui/theme.py")
for mod, cls, cdoc, names in GROUPS:
    body = f'class {cls}:\n    """{cdoc}"""\n\n' + "\n\n".join(method_text(m) for m in names)
    MODULES[f"gui/{mod}.py"] = build_module(cdoc, body, f"gui/{mod}.py")
bases = ", ".join(g[1] for g in GROUPS) + ", ctk.CTk"
app_body = "\n".join(PRELUDE) + f"\n\n\nclass AstroApp({bases}):\n" + "\n\n".join(method_text(m) for m in APP_METHODS)
MODULES["gui/app.py"] = build_module("The AstroWeather window: shell, page switching and the data-flow / worker / event-queue plumbing.",
                                     app_body, "gui/app.py")
MODULES["gui/__init__.py"] = '"""AstroWeather GUI (CustomTkinter): the application window and its pages."""\n'
for name, text in MODULES.items():
    ast.parse(text)

main_body = seg(main_fn) + "\n\n\n" + seg(guard)
main_text = "\n".join(head) + ("\n" if head else "") + seg(doc) + "\n" + render_imports(main_body, "main.py") + "\n\n\n" + main_body + "\n"
ast.parse(main_text)

# every original method must be present, once, verbatim
all_text = "\n".join(MODULES.values())
for name in methods:
    assert all_text.count(method_text(name)) == 1, f"{name} not present exactly once in the generated modules"

# ---- 3. write: new files first, main.py last -------------------------------------------------------------------------
for name, text in MODULES.items():
    p = os.path.join(root, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
with open(path, "wb") as f:
    f.write(main_text.replace("\n", NL).encode("utf-8"))
print("ok (%s line endings preserved in main.py); created %d files; main.py is now %d lines" % (
    "CRLF" if NL == "\r\n" else "LF", len(MODULES), main_text.count("\n")))
for name in TARGETS:
    print("  %-26s %4d lines" % (name, MODULES[name].count("\n")))
