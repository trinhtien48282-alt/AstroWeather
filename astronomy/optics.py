"""Telescope / eyepiece optics (pure calculations): eyepiece + Barlow combinations, exit-pupil notes, scope numbers,
drift time and angle formatting.

Stdlib only (depends on mathutil). No GUI, no NumPy.
"""
import math

from mathutil import rad


def build_combos(scope, eyepieces, barlows):
    ap, fl = float(scope["aperture"]), float(scope["focal_length"])
    options = [("", 1.0)] + [(b["name"], float(b["factor"])) for b in barlows]
    combos = []
    for ep in eyepieces:
        for bname, bf in options:
            mag = fl * bf / float(ep["fl"])
            combos.append({"label": ep["name"] + (f" + {bname}" if bname else ""), "mag": mag,
                           "pupil": ap / mag, "tfov": float(ep["afov"]) / mag, "barlow": bf})
    combos.sort(key=lambda c: c["mag"])
    return combos


def quality_note(mag, pupil, ap):
    if pupil > 7.0:
        return "pupil > 7 mm (light wasted)"
    if pupil > 4.5:
        return "widest field / big targets"
    if pupil > 2.0:
        return "general viewing"
    if pupil > 1.0:
        return "high power: Moon, planets"
    if mag <= 2.0 * ap:
        return "very high: needs steady air"
    return "beyond useful magnification"


def scope_numbers(sc, nelm):
    ap, fl = float(sc["aperture"]), float(sc["focal_length"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    return {"ap": ap, "fl": fl, "obs": obs, "ap_eff": ap_eff, "f": fl / ap,
            "min_mag": ap / 7.0, "max_mag": 2.0 * ap, "comfort": 1.5 * ap,
            "dawes": 116.0 / ap, "rayleigh": 138.0 / ap, "gather": (ap_eff / 7.0) ** 2,
            "lim": nelm + 5.0 * math.log10(ap_eff / 7.0), "lim_ideal": 6.5 + 5.0 * math.log10(ap_eff / 7.0),
            "scale_mm": 206265.0 / fl, "moon_mm": fl * math.tan(rad(0.52)), "airy": 2.44 * 0.55e-3 * (fl / ap)}


def drift_seconds(tfov_deg, dec_deg):
    return tfov_deg * 3600.0 / (15.041 * max(0.05, math.cos(rad(dec_deg))))


def fmt_angle(arcsec):
    if arcsec >= 3600:
        return f"{arcsec / 3600.0:.3g} deg"
    if arcsec >= 60:
        return f"{arcsec / 60.0:.3g} arcmin"
    return f"{arcsec:.3g} arcsec"
