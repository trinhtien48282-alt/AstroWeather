"""Stage 6 edit for main.py: removes the telescope/camera calculation code (now in astronomy/optics.py and
astronomy/camera.py) and adds one import block. Stages 1-5 must already be applied.
AstroApp.update_calcs() is NOT touched: it already calls these functions by name, so only the names' source changes.
CAM_MODES (UI option labels) deliberately STAYS in main.py.
Handles LF or CRLF and preserves the file's existing line endings (no normalisation).
Every cut is located by exact markers and must match exactly once; the code being removed must be byte-for-byte the
code now in astronomy/optics.py / astronomy/camera.py (first differing lines are reported).
Nothing is written unless all checks pass.
Usage: python apply_stage6.py path/to/main.py   (astronomy/ must sit next to main.py)
"""
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


def read_mod(name):
    with open(os.path.join(root, "astronomy", name), "rb") as f:
        return f.read().decode("utf-8").replace("\r\n", "\n")


def must_contain(mod, block, label):
    if mod.count(block) == 1:
        return
    mod_lines = set(mod.splitlines())
    bad = [l for l in block.splitlines() if l not in mod_lines][:3]
    sys.exit(f"refusing: {label} in main.py differs from the new module copy; nothing changed. First differing lines: {bad}")


def cut(text, start, end_marker):
    start, end_marker = nl(start), nl(end_marker)
    assert text.count(start) == 1, f"marker not unique/found: {start!r}"
    i = text.index(start)
    assert text.count(end_marker, i) >= 1, f"end marker not found: {end_marker!r}"
    j = text.index(end_marker, i) + len(end_marker)
    return text[:i] + text[j:], text[i:j].replace("\r\n", "\n")


def names_of(block):
    return [l.split("(")[0][4:] for l in block.splitlines() if l.startswith("def ")]


ANCHOR = nl("                               seeing_fwhm, seeing_label, sky_nelm, verdict)\n")
assert src.count(ANCHOR) == 1 and "from astronomy.scoring import" in src, "Stage 5 import not found exactly once (is Stage 5 applied?)"
assert "from astronomy.optics" not in src and "from astronomy.camera" not in src, "Stage 6 already applied"
optics, camera = read_mod("optics.py"), read_mod("camera.py")

# 1. build_combos + quality_note (eyepiece / Barlow math; suggest_combo stays)
src, a = cut(src, "def build_combos(scope, eyepieces, barlows):\n", '    return "beyond useful magnification"\n\n\n')
assert names_of(a) == ["build_combos", "quality_note"], f"unexpected functions: {names_of(a)}"
must_contain(optics, a.strip("\n"), "build_combos/quality_note")

# 2. the TELESCOPE / OPTICS MATH section: header + scope_numbers, drift_seconds, camera_numbers, fmt_angle
marker = nl("# TELESCOPE / OPTICS MATH\n")
assert src.count(marker) == 1, "TELESCOPE / OPTICS MATH header not unique/found"
k = src.index(marker)
i = src.rfind(NL, 0, k - len(NL)) + len(NL)
assert set(src[i:k].strip()) == {"#", " ", "="}, "unexpected line above the OPTICS header"
end = nl('    return f"{arcsec:.3g} arcsec"\n\n\n')
assert src.count(end, k) == 1, "fmt_angle end not unique/found"
j = src.index(end, k) + len(end)
b = src[i:j].replace("\r\n", "\n")
src = src[:i] + src[j:]
lines = b.split("\n")
assert lines[0].startswith("# ===") and lines[1] == "# TELESCOPE / OPTICS MATH" and lines[2].startswith("# ===") \
    and lines[3].startswith("def scope_numbers"), "unexpected section header"
rest = "\n".join(lines[3:])
assert names_of(rest) == ["scope_numbers", "drift_seconds", "camera_numbers", "fmt_angle"], f"unexpected functions: {names_of(rest)}"
parts = rest.strip("\n").split("\n\n\ndef ")
blocks = [parts[0]] + ["def " + p for p in parts[1:]]
must_contain(optics, blocks[0] + "\n\n\n" + blocks[1], "scope_numbers/drift_seconds")
must_contain(camera, blocks[2], "camera_numbers")
must_contain(optics, blocks[3], "fmt_angle")

# 3. PHONE_PRESETS (CAM_MODES stays)
src, c = cut(src, "PHONE_PRESETS = {\n", '"note": "Long lens: great at filling the frame with a 20 mm eyepiece, but a larger exit pupil match is needed."},\n}\n')
must_contain(camera, c.strip("\n"), "PHONE_PRESETS")

for n in ["build_combos", "quality_note", "scope_numbers", "drift_seconds", "camera_numbers", "fmt_angle"]:
    assert ("def " + n + "(") not in src, f"{n} still defined in main.py"
assert "def suggest_combo(" in src and "CAM_MODES = " in src, "suggest_combo / CAM_MODES should have stayed"

src = src.replace(ANCHOR, ANCHOR + nl(
    "from astronomy.camera import PHONE_PRESETS, camera_numbers  # noqa: F401\n"
    "from astronomy.optics import build_combos, drift_seconds, fmt_angle, quality_note, scope_numbers  # noqa: F401\n"), 1)

out = src.encode("utf-8")
assert (b"\r\n" in out) == (NL == "\r\n") and out.count(b"\n") == (out.count(b"\r\n") if NL == "\r\n" else out.count(b"\n"))
with open(path, "wb") as f:
    f.write(out)
print("ok (%s line endings preserved)" % ("CRLF" if NL == "\r\n" else "LF"))
