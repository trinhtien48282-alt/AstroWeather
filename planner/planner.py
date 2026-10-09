"""Observing planner engine: target positions (Astropy / NumPy / pure Python), scoring, ranking and view advice.

Pure functions, no GUI calls, safe for a worker thread. NumPy and Astropy stay optional.
"""
import importlib.util
import math
import time
import traceback
import warnings

from astro.catalog import CATALOG, KIND_NAMES
from astro.core import altaz, jd_from_ts, precess
from astro.numpy_engine import (HAVE_NUMPY, PERF, np, np_altaz, np_jd, np_moon_drop, np_moon_state, np_planet,
                                np_precess, np_sep, np_sun, sky_series, use_numpy)
from astro.planets import PLANETS, planet_state
from astro.sun_moon import moon_info, moon_pos, sun_altitude
from astronomy.optics import build_combos
from astronomy.scoring import BORTLE_NELM, ang_sep, seeing_fwhm
from config import log_error
from mathutil import clamp, deg, mean, rad
from weather.analysis import fmt_clock

if HAVE_NUMPY:  # these arrays only exist when NumPy does
    from astro.numpy_engine import CAT_DEC, CAT_RA

HAVE_ASTROPY = importlib.util.find_spec("astropy") is not None  # imported lazily, only if enabled


DEEP_KINDS = ("GC", "OC", "EN", "PN", "GX", "SNR", "SC")
PLAN_KINDS = {"All targets": None, "Deep-sky": DEEP_KINDS, "Planets & Moon": ("PL", "MOON"), "Double stars": ("DS",)}
# weights: altitude, detectability, conditions (weather), Moon interference
PLAN_WEIGHTS = {"DSO": (0.25, 0.30, 0.20, 0.25), "PL": (0.25, 0.30, 0.35, 0.10),
                "DS": (0.25, 0.25, 0.35, 0.15), "MOON": (0.30, 0.30, 0.40, 0.0)}
PLANET_NOTES = {
    "Mercury": "a tiny phase disc, low in twilight where the air is unsteady",
    "Venus": "a brilliant phase disc (crescent when close to us), no surface detail",
    "Mars": "an orange disc; dark markings and the polar cap show only when it is above ~10 arcsec",
    "Jupiter": "cloud belts and the four Galilean moons, even in a small scope",
    "Saturn": "the rings and Titan; the Cassini division needs steady air and about 100x",
    "Uranus": "a tiny blue-green disc; use a chart to confirm it",
    "Neptune": "a faint blue dot; needs a chart and a dark sky",
}


def plan_group(kind):
    return kind if kind in ("DS", "PL", "MOON") else "DSO"


def plan_targets():
    t = [dict(o) for o in CATALOG]
    for pn in PLANETS:
        t.append({"id": pn, "name": "", "kind": "PL", "ra": None, "dec": None, "mag": 0.0, "size": 0.0, "sep": None})
    t.append({"id": "Moon", "name": "", "kind": "MOON", "ra": None, "dec": None, "mag": -12.0, "size": 31.0, "sep": None})
    return t


def plan_info(t_mid, lat, lon):
    """Magnitude / disc size / phase of the planets and Moon in the middle of the range."""
    jd = jd_from_ts(t_mid)
    info = {}
    for pn in PLANETS:
        st = planet_state(pn, jd)
        info[pn] = {"mag": st["mag"], "diam": st["diam"], "phase": st["phase"], "elong": st["elong"] * (1 if st["east"] else -1)}
    mi = moon_info(t_mid, lat, lon)
    pa = deg(math.acos(clamp(2.0 * mi["illum"] - 1.0, -1.0, 1.0)))
    info["Moon"] = {"mag": -12.74 + 0.026 * pa + 4e-9 * pa ** 4, "diam": mi["ang_diam"], "phase": mi["illum"], "elong": None}
    return info


def _pack(ts, sun_alt, m_alt, illum, A, Z, S, info, engine):
    return {"ts": ts, "sun_alt": sun_alt, "moon_alt": m_alt, "moon_illum": illum, "alt": np.vstack(A),
            "az": np.vstack(Z), "sep": np.vstack(S), "info": info, "engine": engine}


def positions_numpy(ts, lat, lon):
    n = len(ts)
    jd = np_jd(ts)
    sun = np_sun(jd)
    sun_alt = np_altaz(sun["ra"], sun["dec"], jd, lat, lon)[0]
    m, illum, m_alt, m_az = np_moon_state(jd, lat, lon)
    ra, dec = np_precess(CAT_RA, CAT_DEC, float(jd[n // 2]))  # precession is constant over a few days
    alt, az = np_altaz(ra[:, None], dec[:, None], jd[None, :], lat, lon)
    A, Z = [alt], [az]
    S = [np_sep(ra[:, None], dec[:, None], m["ra"][None, :], m["dec"][None, :])]
    for pn in PLANETS:
        st = np_planet(pn, jd)
        a, z = np_altaz(st["ra"], st["dec"], jd, lat, lon)
        A.append(a[None, :])
        Z.append(z[None, :])
        S.append(np_sep(st["ra"], st["dec"], m["ra"], m["dec"])[None, :])
    A.append(m_alt[None, :])
    Z.append(m_az[None, :])
    S.append(np.full((1, n), 180.0))
    return _pack(ts, sun_alt, m_alt, illum, A, Z, S, plan_info(float(ts[n // 2]), lat, lon), "NumPy")


def positions_scalar(ts, lat, lon):
    """Same output as positions_numpy, computed one value at a time (the 'acceleration off' path)."""
    n = len(ts)
    tsl = [float(t) for t in ts]
    jd_mid = jd_from_ts(tsl[n // 2])
    cat = [precess(o["ra"] * 15.0, o["dec"], jd_mid) for o in CATALOG]
    m_cnt = len(CATALOG)
    total = m_cnt + len(PLANETS) + 1
    alt, az, sep = np.zeros((total, n)), np.zeros((total, n)), np.full((total, n), 180.0)
    sun_alt, m_alt, illum = np.zeros(n), np.zeros(n), np.zeros(n)
    for k, t in enumerate(tsl):
        jd = jd_from_ts(t)
        sun_alt[k] = sun_altitude(t, lat, lon)
        mp, mi = moon_pos(jd), moon_info(t, lat, lon)
        m_alt[k], illum[k] = mi["alt"], mi["illum"]
        for i, (ra, dec) in enumerate(cat):
            alt[i, k], az[i, k] = altaz(ra, dec, jd, lat, lon)
            sep[i, k] = ang_sep(ra, dec, mp["ra"], mp["dec"])
        for j, pn in enumerate(PLANETS):
            st = planet_state(pn, jd)
            alt[m_cnt + j, k], az[m_cnt + j, k] = altaz(st["ra"], st["dec"], jd, lat, lon)
            sep[m_cnt + j, k] = ang_sep(st["ra"], st["dec"], mp["ra"], mp["dec"])
        alt[-1, k], az[-1, k] = mi["alt"], mi["az"]
    return {"ts": ts, "sun_alt": sun_alt, "moon_alt": m_alt, "moon_illum": illum, "alt": alt, "az": az, "sep": sep,
            "info": plan_info(tsl[n // 2], lat, lon), "engine": "pure Python"}


_AP = None


def _astropy():
    """Lazy, defensive Astropy import (never blocks on the network)."""
    global _AP
    if _AP is not None:
        return _AP or None
    try:
        import astropy.units as u
        from astropy.time import Time
        from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body
        from astropy.utils import iers
        iers.conf.auto_download = False  # use the bundled tables; out-of-range dates degrade gracefully
        iers.conf.auto_max_age = None
        _AP = {"u": u, "Time": Time, "EarthLocation": EarthLocation, "AltAz": AltAz, "SkyCoord": SkyCoord, "get_body": get_body}
    except Exception as e:
        log_error(f"astropy import failed: {e}")
        _AP = False
    return _AP or None


def positions_astropy(ts, lat, lon, elev=0.0, pressure=0.0):
    """High-precision positions: built-in ephemeris + full ICRS->AltAz (nutation, aberration, refraction)."""
    ap = _astropy()
    if not ap:
        raise RuntimeError("Astropy is not installed")
    u, n = ap["u"], len(ts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = ap["Time"](np.asarray(ts, dtype=float), format="unix")
        loc = ap["EarthLocation"](lat=lat * u.deg, lon=lon * u.deg, height=elev * u.m)
        press = max(0.0, float(pressure)) * u.hPa
        frame = ap["AltAz"](obstime=t, location=loc, pressure=press)

        def body(name):
            c = ap["get_body"](name, t, loc)
            aa = c.transform_to(frame)
            return (np.asarray(aa.alt.deg, float), np.asarray(aa.az.deg, float),
                    np.asarray(c.ra.deg, float), np.asarray(c.dec.deg, float))
        sun_alt = body("sun")[0]
        m_alt, m_az, m_ra, m_dec = body("moon")
        _m, illum, _a, _z = np_moon_state(np_jd(ts), lat, lon)  # phase geometry needs no Astropy
        cat = ap["SkyCoord"](ra=CAT_RA[:, None] * u.deg, dec=CAT_DEC[:, None] * u.deg, frame="icrs")
        caa = cat.transform_to(ap["AltAz"](obstime=t.reshape(1, n), location=loc, pressure=press))
        A, Z = [np.asarray(caa.alt.deg, float)], [np.asarray(caa.az.deg, float)]
        S = [np_sep(CAT_RA[:, None], CAT_DEC[:, None], m_ra[None, :], m_dec[None, :])]
        for pn in PLANETS:
            a, z, r, d = body(pn.lower())
            A.append(a[None, :])
            Z.append(z[None, :])
            S.append(np_sep(r, d, m_ra, m_dec)[None, :])
        A.append(m_alt[None, :])
        Z.append(m_az[None, :])
        S.append(np.full((1, n), 180.0))
    ref = sky_series(np.asarray(ts[:3], dtype=float), lat, lon)  # refuse to return nonsense
    if (np.max(np.abs(ref["sun_alt"] - sun_alt[:3])) > 2.0 or np.max(np.abs(ref["moon_alt"] - m_alt[:3])) > 2.0
            or np.asarray(A[0]).shape != (len(CATALOG), n)):
        raise RuntimeError("Astropy output disagrees with the built-in engine")
    return _pack(ts, sun_alt, m_alt, illum, A, Z, S, plan_info(float(ts[n // 2]), lat, lon), "Astropy")


def compute_positions(ts, lat, lon, elev=0.0, pressure=1013.0):
    """Pick the engine: Astropy (if enabled and working) > NumPy > pure Python. Returns (positions, name, note)."""
    note = ""
    if PERF["astropy"]:
        try:
            return positions_astropy(ts, lat, lon, elev, pressure), "Astropy", ""
        except Exception as e:
            log_error(f"astropy positions failed: {traceback.format_exc()}")
            note = f"Astropy unavailable ({type(e).__name__}: {str(e)[:70]}), used the built-in engine instead"
    if use_numpy():
        return positions_numpy(ts, lat, lon), "NumPy", note
    return positions_scalar(ts, lat, lon), "pure Python", note


def airmass(alt):
    h = max(alt, 1.0)
    return 1.0 / math.sin(rad(h + 244.0 / (165.0 + 47.0 * h ** 1.1)))


def recommend_view(obj, combos, ap, cap, drop=0.0):
    """Choose an eyepiece / Barlow combination for this target under tonight's conditions."""
    if not combos:
        return None, ""
    usable = [c for c in combos if c["mag"] <= cap and c["pupil"] <= 7.5] or combos[:1]
    by_mag = lambda c: c["mag"]
    kind = obj["kind"]
    if kind == "MOON":
        whole = [c for c in usable if c["tfov"] >= 0.56]
        pick = max(whole, key=by_mag) if whole else min(usable, key=by_mag)
        higher = [c for c in usable if c["mag"] > pick["mag"]]
        why = f"the whole disc fits at {pick['mag']:.0f}x ({pick['tfov']:.2f} deg field)"
        if higher:
            why += f"; step up to {max(higher, key=by_mag)['label']} for crater detail when the air is steady"
        return pick, why
    if kind == "PL":
        pick = max(usable, key=by_mag)
        return pick, f"planets reward the highest power the air allows (about {cap:.0f}x tonight); the disc is only {obj.get('diam', 0):.0f} arcsec"
    if kind == "DS":
        need = 120.0 / max(obj["sep"], 0.5)
        ok = [c for c in usable if c["mag"] >= need]
        if ok:
            return min(ok, key=by_mag), f"a {obj['sep']:.1f}\" pair wants {need:.0f}x or more; this is the lowest power that gets there"
        return max(usable, key=by_mag), f"a {obj['sep']:.1f}\" pair wants {need:.0f}x but tonight's air allows about {cap:.0f}x, so it may look blended"
    size = obj["size"]
    if size >= 15:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 1.1]
        if fit:
            pick = max(fit, key=by_mag)
            return pick, f"{size:.0f}' wide: the most magnification that still frames it ({pick['tfov'] * 60:.0f}' field)"
        pick = min(usable, key=by_mag)
        return pick, f"{size:.0f}' wide is bigger than any of your fields; use the widest ({pick['tfov'] * 60:.0f}') and sweep across it"
    fit = [c for c in usable if c["tfov"] * 60.0 >= size * (2.0 if size >= 3 else 0.0)]
    pool = fit if size >= 3 else [c for c in usable if c["mag"] <= min(cap, ap * 1.6)] or usable
    pick = max(pool or usable, key=by_mag)
    why = (f"{size:.0f}' target: about half the field at {pick['mag']:.0f}x" if size >= 3
           else f"small target ({size * 60:.0f}\"): high power, limited by the air to about {cap:.0f}x")
    if drop > 1.0 and size < 15:
        higher = [c for c in usable if c["mag"] > pick["mag"] and c["tfov"] * 60.0 >= size * 1.3]
        if higher:
            pick = min(higher, key=by_mag)
            why += f"; stepped up to {pick['mag']:.0f}x because Moon glare ({drop:.1f} mag) is brightening the background"
    return pick, why


def run_planner(t0, t1, hours, cfg, off, min_alt=30.0, step_s=600.0, elev=0.0, kind_filter=None):
    """Rank every target over [t0, t1]. Vectorised over targets x time samples."""
    if not HAVE_NUMPY:
        raise RuntimeError("The planner needs NumPy: pip install numpy")
    tc = time.perf_counter()
    lat, lon = float(cfg["location"]["lat"]), float(cfg["location"]["lon"])
    nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
    sc = cfg["scope"]
    ap = float(sc["aperture"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])
    t0, t1 = max(t0, hours[0]["ts"]), min(t1, hours[-1]["ts"] + 3599)
    if t1 - t0 < 1800:
        raise ValueError("Pick a range of at least 30 minutes inside the forecast window.")
    step_s = max(step_s, (t1 - t0) / 2500.0)
    ts = np.arange(t0, t1, step_s, dtype=float)
    pressure = mean([h["press"] for h in hours if h.get("press")]) or 1013.0
    tp = time.perf_counter()
    pos, engine, note = compute_positions(ts, lat, lon, elev, pressure)
    t_pos = time.perf_counter() - tp

    hts = np.array([h["ts"] for h in hours], dtype=float)

    def wx(key, default=0.0):
        return np.interp(ts, hts, np.array([default if h.get(key) is None else h[key] for h in hours], dtype=float))
    cloud, trans, seeing, gate = wx("cloud"), wx("sc_trans"), wx("sc_seeing"), wx("gate", 1.0)
    side = 0.6 * wx("sc_wind", 100.0) + 0.4 * wx("sc_dew", 60.0)

    targets = plan_targets()
    n_t, n_cat = len(targets), len(CATALOG)
    for name, inf in pos["info"].items():
        for o in targets:
            if o["id"] == name and o["kind"] in ("PL", "MOON"):
                o.update(mag=inf["mag"], diam=inf["diam"], size=inf["diam"] / 60.0, phase=inf["phase"], elong=inf["elong"])
    group = [plan_group(o["kind"]) for o in targets]
    w = np.array([PLAN_WEIGHTS[g] for g in group])
    is_deep = np.array([g == "DSO" for g in group])
    is_pl = np.array([g == "PL" for g in group])
    is_moon = np.array([g == "MOON" for g in group])
    dawes = 116.0 / ap_eff
    eff, det_cap, interest = np.zeros(n_t), np.full(n_t, 100.0), np.zeros(n_t)
    for i, o in enumerate(targets):
        if o["kind"] == "DS":
            eff[i] = o["mag"]
            det_cap[i] = 0.0 if o["sep"] < dawes * 0.9 else 55.0 if o["sep"] < dawes * 1.5 else 100.0
        elif group[i] in ("PL", "MOON"):
            eff[i] = o["mag"]
            interest[i] = float(np.interp(o["diam"], [2, 5, 10, 20, 40], [10, 35, 60, 85, 100]))
        else:
            eff[i] = o["mag"] + 2.2 * math.log10(max(1.0, o["size"]))

    alt = pos["alt"]
    sun = pos["sun_alt"][None, :]
    obs_sun = np.where(is_deep[:, None], sun < -12.0, sun < -6.0)  # faint objects need a properly dark sky
    mask = obs_sun & (alt >= min_alt)
    drop = np_moon_drop(pos["moon_illum"][None, :], pos["moon_alt"][None, :], pos["sep"])
    drop[is_moon, :] = 0.0
    lim = nelm + 5.0 * math.log10(ap_eff / 7.0) - drop
    margin = lim - eff[:, None]
    det_m = np.interp(margin, [-2, 0, 1.2, 3, 5], [0, 25, 55, 85, 100])
    det = np.where(is_pl[:, None], 0.7 * interest[:, None] + 0.3 * det_m, det_m)
    det = np.where(is_moon[:, None], 100.0, det)
    det = np.minimum(det, det_cap[:, None])
    alt_sc = np.interp(alt, [10, 20, 30, 45, 60, 75, 90], [0, 15, 40, 70, 90, 98, 100])
    moon_sc = np.interp(drop, [0, 0.3, 1, 2, 3], [100, 90, 65, 30, 0])
    cond = np.where(is_deep[:, None], (0.8 * trans + 0.2 * seeing)[None, :], (0.7 * seeing + 0.3 * trans)[None, :])
    cond = 0.85 * cond + 0.15 * side[None, :]
    base = w[:, 0:1] * alt_sc + w[:, 1:2] * det + w[:, 2:3] * cond + w[:, 3:4] * moon_sc
    total = np.where(mask, base * gate[None, :], -1.0)
    best_i = total.argmax(axis=1)
    idx = np.arange(n_t)
    best_val = total[idx, best_i]
    hours_up = mask.sum(axis=1) * step_s / 3600.0
    dur = np.interp(hours_up, [0, 0.5, 1, 2, 4], [0, 30, 55, 85, 100])
    score = np.where(best_val >= 0, 0.88 * best_val + 0.12 * dur, 0.0)
    alt_obs = np.where(obs_sun, alt, -90.0)
    peak_i = alt_obs.argmax(axis=1)
    clock = lambda t: fmt_clock(t, off)
    rating_of = lambda mg: "Easy" if mg >= 3 else "Moderate" if mg >= 1.2 else "Hard" if mg >= 0 else "Beyond"

    rows, hidden = [], 0
    for i, o in enumerate(targets):
        if kind_filter and o["kind"] not in kind_filter:
            continue
        if score[i] <= 0:
            hidden += 1
            continue
        bi, pi = int(best_i[i]), int(peak_i[i])
        g = group[i]
        drop_b, sep_b = float(drop[i, bi]), float(pos["sep"][i, bi])
        c_b, tr_b, se_b, g_b = float(cloud[bi]), float(trans[bi]), float(seeing[bi]), float(gate[bi])
        illum_b, malt_b = float(pos["moon_illum"][bi]), float(pos["moon_alt"][bi])
        mg_b = float(margin[i, bi])
        rating = "Beyond" if det_cap[i] == 0 else rating_of(mg_b)
        fwhm_b = seeing_fwhm(se_b)
        cap_b = min(2.0 * ap_eff, 200.0 / fwhm_b)
        combo, why = recommend_view(dict(o, diam=o.get("diam", 0.0)), combos, ap_eff, cap_b, drop_b)
        pk, pk_ts = float(alt_obs[i, pi]), float(ts[pi])
        R = []
        R.append(("good" if pk >= 60 else "info" if pk >= 45 else "warn",
                  f"Peaks at {pk:.0f} deg around {clock(pk_ts)} (airmass {airmass(pk):.2f}); {hours_up[i]:.1f} h above {min_alt:.0f} deg in a dark enough sky."))
        R.append(("good" if c_b < 20 else "info" if c_b < 50 else "bad",
                  f"Around {clock(float(ts[bi]))}: cloud {c_b:.0f}%, transparency {tr_b:.0f}/100, seeing about {fwhm_b:.1f} arcsec."))
        if g_b < 0.6:
            R.append(("warn", f"Cloud and rain chance cut the score to {g_b * 100:.0f}% of its potential at that time."))
        if g != "MOON":
            if malt_b <= 0:
                R.append(("good", "The Moon is below the horizon then: no glare."))
            else:
                lvl = "good" if drop_b < 0.3 else "info" if drop_b < 1.0 else "warn" if drop_b < 2.0 else "bad"
                near = "very close" if sep_b < 20 else "far" if sep_b > 90 else "moderately far"
                R.append((lvl, f"Moon {illum_b * 100:.0f}% lit, {sep_b:.0f} deg away ({near}): costs about {drop_b:.1f} mag of sky limit."))
        if g == "PL":
            R.append(("info", f"{o['diam']:.0f}\" disc, {o['phase'] * 100:.0f}% lit, mag {o['mag']:.1f}: expect {PLANET_NOTES[o['id']]}."))
        elif g == "MOON":
            R.append(("info", f"Moon {o['phase'] * 100:.0f}% lit: best detail is along the terminator."))
        elif g == "DS":
            R.append(("good" if rating in ("Easy", "Moderate") else "warn",
                      f"Double star, primary mag {o['mag']:.1f}, separation {o['sep']:.1f}\" (your Dawes limit is {dawes:.2f}\"): {rating}."
                      + (" Too tight to split." if det_cap[i] == 0 else "")))
        else:
            R.append(("good" if rating in ("Easy", "Moderate") else "warn",
                      f"{KIND_NAMES[o['kind']]}, mag {o['mag']:.1f}, {o['size']:.0f}' across: {rating} in {ap:.0f} mm ({mg_b:+.1f} mag margin)."))
        parts = {"altitude": float(alt_sc[i, bi]), "detectability": float(det[i, bi]), "conditions": float(cond[i, bi]),
                 "moon": float(moon_sc[i, bi])}
        loss = {"altitude": w[i, 0] * (100 - parts["altitude"]), "detectability": w[i, 1] * (100 - parts["detectability"]),
                "conditions": w[i, 2] * (100 - parts["conditions"]), "Moon glare": w[i, 3] * (100 - parts["moon"]),
                "cloud / rain": float(base[i, bi]) * (1.0 - g_b)}
        lim_name = max(loss, key=loss.get)
        if loss[lim_name] >= 6:
            R.append(("info", f"Biggest drag on the score: {lim_name} (about -{loss[lim_name]:.0f} points)."))
        rows.append({"ti": i, "id": o["id"], "name": o["name"], "kind": o["kind"], "score": float(score[i]),
                     "best_ts": float(ts[bi]), "peak_alt": pk, "peak_ts": pk_ts, "hours_up": float(hours_up[i]),
                     "sep": sep_b, "drop": drop_b, "mag": o["mag"], "size": o["size"], "rating": rating,
                     "view": combo, "view_why": why, "reasons": R, "parts": parts, "gate": g_b})
    rows.sort(key=lambda r: -r["score"])
    return {"ts": ts, "sun_alt": pos["sun_alt"], "moon_alt": pos["moon_alt"], "alt": pos["alt"], "targets": targets,
            "rows": rows, "hidden": hidden, "engine": engine, "note": note, "offset": off, "min_alt": min_alt,
            "t_pos_ms": t_pos * 1000.0, "t_total_ms": (time.perf_counter() - tc) * 1000.0, "step_s": step_s,
            "now": time.time()}


def engine_check(lat, lon, now_ts, elev=0.0):
    """Compare the three engines on a 3-night grid: agreement and speed."""
    if not HAVE_NUMPY:
        return "NumPy is not installed: only the pure-Python engine is available."
    ts = np.arange(now_ts, now_ts + 3 * 86400, 600.0)
    lines, res = [f"Grid: {len(ts)} times x {len(CATALOG) + len(PLANETS) + 1} targets"], {}
    for name, fn in (("pure Python", positions_scalar), ("NumPy", positions_numpy)):
        t = time.perf_counter()
        res[name] = fn(ts, lat, lon)
        lines.append(f"{name:<12} {(time.perf_counter() - t) * 1000:8.1f} ms")
    d = np.abs(res["pure Python"]["alt"] - res["NumPy"]["alt"])
    lines.append(f"NumPy vs pure Python: max altitude difference {float(d.max()):.2e} deg")
    if not HAVE_ASTROPY:
        lines.append("Astropy: not installed (pip install astropy to enable precision mode)")
    else:
        try:
            t = time.perf_counter()
            ap = positions_astropy(ts, lat, lon, elev, 0.0)
            lines.append(f"{'Astropy':<12} {(time.perf_counter() - t) * 1000:8.1f} ms")
            da = np.abs(ap["alt"] - res["NumPy"]["alt"])
            lines.append(f"Astropy vs NumPy: mean {float(da.mean()) * 60:.1f} arcmin, max {float(da.max()):.3f} deg "
                         f"(Moon max {float(np.abs(ap['moon_alt'] - res['NumPy']['moon_alt']).max()) * 60:.1f} arcmin)")
        except Exception as e:
            lines.append(f"Astropy failed: {type(e).__name__}: {str(e)[:90]}")
    return "\n".join(lines)
