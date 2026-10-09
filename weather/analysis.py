"""Forecast analysis: hourly scoring of the weather, tonight window, planets/targets tables and insights.

Pure calculations (no GUI). NumPy is optional, as in astro.numpy_engine.
"""
import math
import time
from datetime import datetime, timedelta, timezone

from astro.catalog import CATALOG
from astro.core import jd_from_ts
from astro.numpy_engine import body_events, catalog_altaz_sep, np, scan_body, sky_series, use_numpy
from astro.planets import PLANETS, planet_state
from astro.sun_moon import moon_info, moon_pos, next_phase_time, sun_altitude
from astronomy.optics import build_combos
from astronomy.scoring import (BORTLE_NELM, moon_drop, moon_score_from_drop, score_dew, score_seeing,
                               score_transparency, score_wind, seeing_fwhm, seeing_label)
from mathutil import clamp, deg, mean
from weather.api import BASE_VARS, UPPER_VARS


def build_hours(wx, aq, lat, lon):
    h = wx.get("hourly", {})
    times = h.get("time", [])
    n = len(times)

    def col(src, name):
        arr = src.get(name) if src else None
        return arr if isinstance(arr, list) and len(arr) == n else [None] * n

    aq_h = (aq or {}).get("hourly", {}) if aq else {}
    aq_index = {int(t): i for i, t in enumerate(aq_h.get("time", []))}

    def aq_val(name, ts):
        arr = aq_h.get(name)
        i = aq_index.get(ts)
        return arr[i] if arr and i is not None and i < len(arr) else None

    cols = {k: col(h, k) for k in BASE_VARS + UPPER_VARS}
    pre = None
    if use_numpy() and n:  # one vectorised pass instead of a Sun + Moon calculation per hour
        pre = sky_series(np.array([int(t) for t in times], dtype=float), lat, lon)
    hours, prev_temp = [], None
    for i in range(n):
        ts = int(times[i])
        t, cloud = cols["temperature_2m"][i], cols["cloud_cover"][i]
        if t is None or cloud is None:
            continue
        rh, dew = cols["relative_humidity_2m"][i], cols["dew_point_2m"][i]
        wind, gust = cols["wind_speed_10m"][i] or 0.0, cols["wind_gusts_10m"][i] or 0.0
        vis = cols["visibility"][i]
        vis_km = vis / 1000.0 if vis is not None else None
        jets = [cols[k][i] for k in UPPER_VARS if cols[k][i] is not None]
        jet_ms = max(jets) / 3.6 if jets else None
        aod, pm25 = aq_val("aerosol_optical_depth", ts), aq_val("pm2_5", ts)
        spread = (t - dew) if dew is not None else None
        dtdt = (t - prev_temp) if prev_temp is not None else 0.0
        prev_temp = t
        jd = jd_from_ts(ts)
        if pre is not None:
            s_alt = float(pre["sun_alt"][i])
            mi = {"illum": float(pre["moon_illum"][i]), "alt": float(pre["moon_alt"][i])}
        else:
            s_alt = sun_altitude(ts, lat, lon)
            mi = moon_info(ts, lat, lon)
        pp = cols["precipitation_probability"][i] or 0.0
        precip = cols["precipitation"][i] or 0.0

        sc_trans = score_transparency(rh, aod, pm25, vis_km)
        sc_seeing = score_seeing(jet_ms, wind, gust, dtdt, cols["cape"][i])
        sc_dew, sc_wind = score_dew(spread), score_wind(wind, gust)
        sc_moon = moon_score_from_drop(moon_drop(mi["illum"], mi["alt"], 60.0))  # typical 60 deg separation
        gate = (1.0 - clamp(cloud, 0, 100) / 100.0) ** 1.2
        gate *= 1.0 - 0.8 * clamp(pp / 70.0, 0.0, 1.0)
        if precip > 0.1:
            gate *= 0.2
        dso = (0.32 * sc_trans + 0.30 * sc_moon + 0.14 * sc_wind + 0.12 * sc_dew + 0.12 * sc_seeing) * gate
        planet = (0.45 * sc_seeing + 0.20 * sc_trans + 0.15 * sc_wind + 0.10 * sc_dew + 10.0) * gate
        hours.append({
            "ts": ts, "temp": t, "rh": rh, "dew": dew, "spread": spread, "press": cols["surface_pressure"][i],
            "pp": pp, "precip": precip, "cloud": cloud, "low": cols["cloud_cover_low"][i],
            "mid": cols["cloud_cover_mid"][i], "high": cols["cloud_cover_high"][i], "vis_km": vis_km,
            "wind": wind, "gust": gust, "wdir": cols["wind_direction_10m"][i], "cape": cols["cape"][i],
            "jet": jet_ms, "aod": aod, "pm25": pm25, "dtdt": dtdt,
            "sun_alt": s_alt, "moon_alt": mi["alt"], "moon_illum": mi["illum"],
            "dark": 0 if s_alt > -0.833 else 1 if s_alt > -6 else 2 if s_alt > -12 else 3 if s_alt > -18 else 4,
            "sc_trans": sc_trans, "sc_seeing": sc_seeing, "sc_dew": sc_dew, "sc_wind": sc_wind,
            "sc_moon": sc_moon, "dso": dso, "planet": planet, "gate": gate,
        })
    return hours


def tonight_window(lat, lon, now_ts):
    events = body_events("sun", now_ts - 18 * 3600, now_ts + 36 * 3600, 600, -0.833, lat, lon)
    if sun_altitude(now_ts, lat, lon) < -0.833:
        sets = [t for k, t in events if k == "set" and t <= now_ts]
        rises = [t for k, t in events if k == "rise" and t >= now_ts]
        start = sets[-1] if sets else now_ts - 6 * 3600
        end = rises[0] if rises else now_ts + 6 * 3600
    else:
        sets = [t for k, t in events if k == "set" and t >= now_ts]
        if not sets:
            return {"start": now_ts, "end": now_ts + 12 * 3600, "dusk": None, "dawn": None, "polar": True}
        start = sets[0]
        rises = [t for k, t in events if k == "rise" and t >= start]
        end = rises[0] if rises else start + 12 * 3600
    tw = body_events("sun", start - 600, end + 600, 600, -18.0, lat, lon)
    dusk = next((t for k, t in tw if k == "set"), None)
    dawn = next((t for k, t in reversed(tw) if k == "rise"), None)
    return {"start": start, "end": end, "dusk": dusk, "dawn": dawn, "polar": False}


def planet_rows(lat, lon, win):
    rows = []
    t0, t1 = win["start"], win["end"]
    steps = max(2, int((t1 - t0) // 1200))
    for name in PLANETS + ["Moon"]:
        best, vis = scan_body(name, t0, t1, steps, lat, lon)
        jd = jd_from_ts(win["start"])
        if name == "Moon":
            mi = moon_info(win["start"], lat, lon)
            pa = deg(math.acos(clamp(2.0 * mi["illum"] - 1.0, -1.0, 1.0)))  # phase angle, 0 = full
            rows.append({"name": name, "mag": -12.74 + 0.026 * pa + 4e-9 * pa ** 4, "diam": mi["ang_diam"],
                         "phase": mi["illum"], "elong": None, "best_alt": best[0], "best_ts": best[1],
                         "vis": (vis[0], vis[-1]) if vis else None})
        else:
            st = planet_state(name, jd)
            rows.append({"name": name, "mag": st["mag"], "diam": st["diam"], "phase": st["phase"],
                         "elong": st["elong"] * (1 if st["east"] else -1), "best_alt": best[0], "best_ts": best[1],
                         "vis": (vis[0], vis[-1]) if vis else None})
    return rows


def suggest_combo(obj, combos, ap, cap):
    usable = [c for c in combos if c["mag"] <= cap and c["pupil"] <= 7.5] or combos[:1]
    if not usable:
        return None
    if obj["kind"] == "DS":
        need = 120.0 / max(obj["sep"], 0.5)
        ok = [c for c in usable if c["mag"] >= need]
        return min(ok, key=lambda c: c["mag"]) if ok else max(usable, key=lambda c: c["mag"])
    size = obj["size"]
    if size >= 15:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 1.1]
        return max(fit, key=lambda c: c["mag"]) if fit else min(usable, key=lambda c: c["mag"])
    if size >= 3:
        fit = [c for c in usable if c["tfov"] * 60.0 >= size * 2.0]
        return max(fit, key=lambda c: c["mag"]) if fit else min(usable, key=lambda c: c["mag"])
    pool = [c for c in usable if c["mag"] <= min(cap, ap * 1.6)] or usable
    return max(pool, key=lambda c: c["mag"])


def rank_targets(ts, lat, lon, ap_eff, nelm, combos, cap):
    jd = jd_from_ts(ts)
    mi = moon_info(ts, lat, lon)
    lim_dark = nelm + 5.0 * math.log10(ap_eff / 7.0)
    dawes = 116.0 / (ap_eff if ap_eff > 0 else 76.0)
    alts, azs, seps = catalog_altaz_sep(jd, lat, lon, moon_pos(jd))
    rows = []
    for i, o in enumerate(CATALOG):
        alt, az, sep = alts[i], azs[i], seps[i]
        drop = moon_drop(mi["illum"], mi["alt"], sep)  # depends on Moon phase, height AND distance from the target
        lim = lim_dark - drop
        if o["kind"] == "DS":
            margin = lim - o["mag"]
            if o["sep"] < dawes * 0.9:
                margin = -1.0
            elif o["sep"] < dawes * 1.5:
                margin = min(margin, 1.0)
        else:
            margin = lim - (o["mag"] + 2.2 * math.log10(max(1.0, o["size"])))
        rating = "Easy" if margin >= 3 else "Moderate" if margin >= 1.2 else "Hard" if margin >= 0 else "Beyond"
        combo = suggest_combo(o, combos, ap_eff, cap) if combos else None
        rows.append({"obj": o, "alt": alt, "az": az, "margin": margin, "rating": rating, "combo": combo,
                     "lim": lim, "lim_dark": lim_dark, "sep": sep, "drop": drop})
    return rows


def pick_window(hours, now_ts, length=2):
    ok = [h for h in hours if h["sun_alt"] < -12 and h["ts"] + 3600 > now_ts]
    best = None
    for i in range(len(ok) - length + 1):
        chunk = ok[i:i + length]
        if chunk[-1]["ts"] - chunk[0]["ts"] != (length - 1) * 3600:
            continue
        avg = sum(c["dso"] for c in chunk) / length
        if best is None or avg > best[0]:
            best = (avg, chunk[0]["ts"], chunk[-1]["ts"] + 3600)
    return best


def analyze(wx, aq, cfg, now_ts):
    lat, lon = float(cfg["location"]["lat"]), float(cfg["location"]["lon"])
    nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
    off = int(wx.get("utc_offset_seconds", 0) or 0)
    hours = build_hours(wx, aq, lat, lon)
    if not hours:
        raise ValueError("The weather service returned no usable hourly data.")
    win = tonight_window(lat, lon, now_ts)
    in_night = [h for h in hours if win["start"] - 1800 <= h["ts"] < win["end"]]
    dark = [h for h in in_night if h["sun_alt"] < -12]
    twil = [h for h in in_night if h["sun_alt"] < -6]
    sc = cfg["scope"]
    ap, fl = float(sc["aperture"]), float(sc["focal_length"])
    obs = float(sc.get("obstruction_mm", 0) or 0)
    ap_eff = math.sqrt(max(ap * ap - obs * obs, 1.0))
    combos = build_combos(sc, cfg["eyepieces"], cfg["barlows"])

    tn = {"win": win, "dark": dark, "hours": in_night,
          "dso": mean([h["dso"] for h in dark]), "planet": mean([h["planet"] for h in twil]),
          "cloud": mean([h["cloud"] for h in dark]), "trans": mean([h["sc_trans"] for h in dark]),
          "seeing": mean([h["sc_seeing"] for h in dark]), "wind": mean([h["wind"] for h in dark]),
          "gust": max([h["gust"] for h in dark], default=None),
          "spread": min([h["spread"] for h in dark if h["spread"] is not None], default=None),
          "tmin": min([h["temp"] for h in dark], default=None), "tmax": max([h["temp"] for h in dark], default=None),
          "pp": max([h["pp"] for h in dark], default=None), "jet": mean([h["jet"] for h in dark]),
          "rh": mean([h["rh"] for h in dark]), "aod": mean([h["aod"] for h in dark])}
    tn["fwhm"] = seeing_fwhm(tn["seeing"]) if tn["seeing"] is not None else None
    tn["best"] = pick_window(hours, now_ts)
    tn["cap"] = min(2.0 * ap_eff, 200.0 / tn["fwhm"]) if tn["fwhm"] else 2.0 * ap_eff

    # Moon
    mnow = moon_info(now_ts, lat, lon)
    mid = (win["start"] + win["end"]) / 2
    mmid = moon_info(mid, lat, lon)
    mev = body_events("moon", win["start"] - 6 * 3600, win["end"] + 6 * 3600, 600, -0.83, lat, lon)
    moon = {"now": mnow, "mid": mmid, "events": mev,
            "next_new": next_phase_time(now_ts, 0.0), "next_full": next_phase_time(now_ts, 180.0),
            "moonfree": [h for h in dark if h["moon_alt"] < -0.5]}

    eval_ts = (tn["best"][1] + 1800) if tn["best"] else (dark[len(dark) // 2]["ts"] if dark else now_ts)
    targets = rank_targets(eval_ts, lat, lon, ap_eff, nelm, combos, tn["cap"])
    planets = planet_rows(lat, lon, win)
    insights = build_insights(tn, moon, cfg, combos, off, ap_eff)
    return {"hours": hours, "offset": off, "now": now_ts, "tonight": tn, "moon": moon, "planets": planets,
            "targets": targets, "eval_ts": eval_ts, "insights": insights, "combos": combos,
            "elevation": wx.get("elevation"), "has_jet": any(h["jet"] is not None for h in hours),
            "has_aq": any(h["aod"] is not None for h in hours), "fetched": time.time()}


def fmt_clock(ts, off):
    return datetime.fromtimestamp(ts, timezone(timedelta(seconds=off))).strftime("%H:%M")


def build_insights(tn, moon, cfg, combos, off, ap_eff):
    ins = []
    dark = tn["dark"]
    if not dark:
        return [("bad", "No real darkness tonight at this location (sun stays above -12 degrees).")]
    cl = tn["cloud"]
    if cl < 15:
        ins.append(("good", f"Mostly clear: {cl:.0f}% average cloud during the dark hours."))
    elif cl < 40:
        ins.append(("info", f"Patchy cloud: {cl:.0f}% on average. Watch for gaps and stay flexible."))
    else:
        ins.append(("bad", f"Cloudy: {cl:.0f}% average cover during the dark hours."))
    cloudy = [h for h in dark if h["cloud"] > 60]
    clear = [h for h in dark if h["cloud"] < 25]
    if cloudy and clear and cloudy[0]["ts"] < clear[-1]["ts"]:
        later = [h for h in clear if h["ts"] > cloudy[0]["ts"]]
        if later:
            ins.append(("info", f"Clouds thin out around {fmt_clock(later[0]['ts'], off)}: a later session may beat the early evening."))
    if dark and max(h["high"] or 0 for h in dark) > 50 and cl < 40:
        ins.append(("info", "Thin high cloud (cirrus) is around: stars look dimmer and the Moon gets halos."))
    if tn["pp"] is not None and tn["pp"] >= 30:
        ins.append(("bad", f"Rain chance up to {tn['pp']:.0f}%: keep the scope under cover."))
    tr = tn["trans"]
    note = ""
    if tn["aod"] is not None:
        note = f" (aerosol optical depth about {tn['aod']:.2f})"
    ins.append(("good" if tr >= 70 else "info" if tr >= 45 else "bad",
                f"Transparency {tr:.0f}/100{note}. " + ("Faint nebulae and galaxies should pop." if tr >= 70 else
                                                       "Haze will wash out faint objects; favour bright targets." if tr < 45 else
                                                       "Decent, but not perfect for faint fuzzies.")))
    se = tn["seeing"]
    jet = f", jet stream about {tn['jet']:.0f} m/s" if tn["jet"] is not None else ""
    ins.append(("good" if se >= 70 else "info" if se >= 45 else "warn",
                f"Seeing estimate {seeing_label(se)} (about {tn['fwhm']:.1f} arcsec){jet}."))
    cap = tn["cap"]
    useful = [c for c in combos if c["mag"] <= cap]
    if useful:
        top = max(useful, key=lambda c: c["mag"])
        ins.append(("info", f"Tonight's air supports about {cap:.0f}x. Your best high-power combo: {top['label']} ({top['mag']:.0f}x)."))
    if tn["gust"] is not None and tn["gust"] >= 25:
        ins.append(("warn", f"Gusts to {tn['gust']:.0f} km/h: a light {cfg['scope'].get('mount', 'AZ')} mount will shake. "
                            "Use low power or find a windbreak."))
    elif tn["wind"] is not None and tn["wind"] < 12:
        ins.append(("good", "Calm wind: steady views and an easy time with a lightweight tripod."))
    sp = tn["spread"]
    if sp is not None:
        if sp < 1.5:
            ins.append(("warn", f"Dew will form (temperature only {sp:.1f} degrees above dew point). Bring a dew shield or keep the mirror capped between uses."))
        elif sp < 3:
            ins.append(("info", f"Dew risk moderate (spread {sp:.1f} degrees)."))
    m = moon["mid"]
    free = len(moon["moonfree"])
    if m["illum"] < 0.15:
        ins.append(("good", f"Moon is {m['name'].lower()} ({m['illum'] * 100:.0f}% lit): dark skies for faint objects."))
    else:
        txt = f"Moon {m['name'].lower()}, {m['illum'] * 100:.0f}% lit at midnight. "
        txt += f"{free} Moon-free dark hour(s) tonight." if free else "It is up all night: stick to bright targets, the Moon and planets."
        ins.append(("warn" if m["illum"] > 0.6 and not free else "info", txt))
    return ins
