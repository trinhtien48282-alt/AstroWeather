"""Telescope page: setup, calculators and the camera calculator."""
import time

import customtkinter as ctk

from astro.sun_moon import moon_info
from astronomy.camera import camera_numbers, PHONE_PRESETS
from astronomy.optics import build_combos, drift_seconds, fmt_angle, quality_note, scope_numbers
from astronomy.scoring import BORTLE_NELM
from config import save_config
from gui.theme import CAM_MODES, DEEP


class CalculatorsPage:
    """Telescope page: setup, calculators and the camera calculator."""

    def build_scope(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        tabs = ctk.CTkTabview(page)
        tabs.grid(row=0, column=0, sticky="nsew", padx=20, pady=(0, 14))
        for name in ("Your setup", "Calculators", "Camera"):
            tabs.add(name)
        # ---- setup
        t = ctk.CTkScrollableFrame(tabs.tab("Your setup"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Optics")
        self.out["specs"] = ctk.CTkLabel(c, text="", font=self.f_mono, justify="left", anchor="w")
        self.out["specs"].pack(anchor="w", padx=16, pady=(0, 12))
        c = self.card(t, "Eyepiece and Barlow combinations")
        self.box_combos = ctk.CTkTextbox(c, height=330, font=self.f_mono, fg_color=DEEP, state="disabled", wrap="none")
        self.box_combos.pack(fill="x", padx=14, pady=(0, 14))
        # ---- calculators
        t = ctk.CTkScrollableFrame(tabs.tab("Calculators"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Magnification, exit pupil and field of view")
        self.entry_row(c, "ep_fl", "Eyepiece focal length (mm)", 12.5)
        self.entry_row(c, "ep_afov", "Eyepiece apparent FOV (deg)", 35)
        self.entry_row(c, "ep_barlow", "Barlow factor (1 = none)", 1)
        self.out_label(c, "mag")
        c = self.card(t, "Will it fit? (target size vs. true field)")
        self.entry_row(c, "fit_size", "Target size (arcmin)", 30)
        self.out_label(c, "fit")
        c = self.card(t, "Angles and arcs")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Convert an angle", width=190, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=80, font=self.f_ui)
        e.insert(0, "1")
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent["ang_val"] = e
        om = ctk.CTkOptionMenu(row, values=["degrees", "arcminutes", "arcseconds", "radians"], width=120,
                               command=lambda v: self.update_calcs())
        om.set("degrees")
        om.pack(side="left", padx=8)
        self.opt["ang_unit"] = om
        self.out_label(c, "ang")
        self.entry_row(c, "phys_size", "Real size of object (km)", 100)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Distance (km)", width=190, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=110, font=self.f_ui)
        e.insert(0, "384400")
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent["phys_dist"] = e
        ctk.CTkButton(row, text="Moon (now)", width=90, font=self.f_small, fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=self.preset_moon).pack(side="left", padx=8)
        self.out_label(c, "phys")
        c = self.card(t, "Resolution and splitting double stars")
        self.entry_row(c, "dbl_sep", "Double star separation (arcsec)", 4)
        self.entry_row(c, "feat", "Smallest feature to see (arcsec)", 2)
        self.out_label(c, "res")
        c = self.card(t, "Drift time (manual tracking on an AZ mount)")
        self.entry_row(c, "drift_dec", "Target declination (deg)", 0)
        self.out_label(c, "drift")
        # ---- camera
        t = ctk.CTkScrollableFrame(tabs.tab("Camera"), fg_color="transparent")
        t.pack(fill="both", expand=True)
        c = self.card(t, "Imaging through the telescope")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Camera preset", width=230, anchor="w", font=self.f_ui).pack(side="left")
        om = ctk.CTkOptionMenu(row, values=list(PHONE_PRESETS), width=340, command=self.on_cam_preset)
        om.set(self.cfg.get("camera", {}).get("preset", "Custom"))
        om.pack(side="left")
        self.opt["cam_preset"] = om
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text="Mode", width=230, anchor="w", font=self.f_ui).pack(side="left")
        om = ctk.CTkOptionMenu(row, values=CAM_MODES, width=340, command=lambda v: self.update_calcs())
        om.set(CAM_MODES[0])
        om.pack(side="left")
        self.opt["cam_mode"] = om
        self.cam_note = ctk.CTkLabel(c, text="", font=self.f_small, text_color="#8a93a6", anchor="w", justify="left", wraplength=760)
        self.cam_note.pack(anchor="w", padx=16, pady=(2, 4))
        self.entry_row(c, "cam_pix", "Pixel size (um)", 3.75)
        self.entry_row(c, "cam_w", "Sensor width (pixels)", 1280)
        self.entry_row(c, "cam_h", "Sensor height (pixels)", 960)
        self.entry_row(c, "cam_lens", "Camera / phone lens focal length (mm)", 6.8)
        self.entry_row(c, "cam_fno", "Lens f-number", 1.8)
        self.entry_row(c, "cam_ep", "Eyepiece used for afocal (mm)", 20)
        self.entry_row(c, "cam_barlow", "Barlow / reducer factor", 1)
        self.entry_row(c, "cam_seeing", "Seeing FWHM (arcsec)", 2.5)
        self.entry_row(c, "cam_dec", "Target declination (deg)", 0)
        self.out_label(c, "cam")
        if self.cfg.get("camera", {}).get("preset", "Custom") != "Custom":
            self.apply_cam_preset(self.cfg["camera"]["preset"])

    def entry_row(self, parent, key, label, default, width=90):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text=label, width=230, anchor="w", font=self.f_ui).pack(side="left")
        e = ctk.CTkEntry(row, width=width, font=self.f_ui)
        e.insert(0, str(default))
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.schedule_calcs())
        self.ent[key] = e
        return e

    def out_label(self, parent, key):
        lbl = ctk.CTkLabel(parent, text="", font=self.f_mono, justify="left", anchor="w")
        lbl.pack(anchor="w", padx=16, pady=(6, 12))
        self.out[key] = lbl

    def num(self, key, default=None):
        try:
            return float(str(self.ent[key].get()).strip().replace(",", "."))
        except (ValueError, TypeError, KeyError):
            return default

    def apply_cam_preset(self, name):
        p = PHONE_PRESETS.get(name)
        if p:
            for key, val in (("cam_pix", p["pix"]), ("cam_w", p["w"]), ("cam_h", p["h"]), ("cam_lens", p["lens"]), ("cam_fno", p["fno"])):
                self.ent[key].delete(0, "end")
                self.ent[key].insert(0, f"{val:g}")
            self.opt["cam_mode"].set(CAM_MODES[1])  # phones are used behind an eyepiece
        self.cam_note.configure(text=(p["note"] + "  (focal lengths are derived from Apple's 35 mm equivalents: edit if you know better)") if p else "")

    def on_cam_preset(self, name):
        self.apply_cam_preset(name)
        self.cfg.setdefault("camera", {})["preset"] = name
        save_config(self.cfg)
        self.update_calcs()

    def eyepiece_afov(self, fl_mm):
        best = min(self.cfg["eyepieces"], key=lambda e: abs(float(e["fl"]) - fl_mm), default=None)
        return float(best["afov"]) if best and abs(float(best["fl"]) - fl_mm) < 1.0 else 35.0

    def preset_moon(self):
        dist = self.analysis["moon"]["now"]["dist_km"] if self.analysis else moon_info(time.time(), 0, 0)["dist_km"]
        self.ent["phys_dist"].delete(0, "end")
        self.ent["phys_dist"].insert(0, f"{dist:.0f}")
        self.update_calcs()

    def schedule_calcs(self):
        if self._calc_job:
            self.after_cancel(self._calc_job)
        self._calc_job = self.after(120, self._run_calcs)

    def _run_calcs(self):
        self._calc_job = None
        self.update_calcs()

    def update_calcs(self):
        cfg = self.cfg
        nelm = BORTLE_NELM.get(int(cfg["bortle"]), 5.6)
        try:
            sn = scope_numbers(cfg["scope"], nelm)
        except Exception:
            return
        ap, fl = sn["ap"], sn["fl"]
        obs_txt = f"  (secondary shadow {sn['obs']:.0f} mm, effective {sn['ap_eff']:.0f} mm)" if sn["obs"] else ""
        self.out["specs"].configure(text="\n".join([
            f"{cfg['scope'].get('name', 'Scope')}:  {ap:.0f} mm aperture, {fl:.0f} mm focal length, f/{sn['f']:.1f}, {cfg['scope'].get('mount', '')} mount{obs_txt}",
            f"Light grasp:       {sn['gather']:.0f}x the dark-adapted eye (7 mm pupil)",
            f"Limiting magnitude about {sn['lim']:.1f} at your sky (Bortle {cfg['bortle']}, naked eye {nelm:.1f}), {sn['lim_ideal']:.1f} under a perfect sky",
            f"Resolution:        Dawes {sn['dawes']:.2f} arcsec,  Rayleigh {sn['rayleigh']:.2f} arcsec,  Airy disk {sn['airy'] * 1000:.1f} um at focus",
            f"Magnification:     min {sn['min_mag']:.0f}x (7 mm pupil),  comfortable up to {sn['comfort']:.0f}x,  practical max {sn['max_mag']:.0f}x (2x aperture in mm)",
            f"Image scale:       {sn['scale_mm']:.1f} arcsec per mm at the focal plane;  the Moon is {sn['moon_mm']:.2f} mm wide at prime focus",
        ]))
        combos = build_combos(cfg["scope"], cfg["eyepieces"], cfg["barlows"])
        lines = [f"{'Combination':<26}{'Mag':>6}{'Exit pupil':>12}{'True field':>13}   Good for"]
        for cb in combos:
            lines.append(f"{cb['label']:<26}{cb['mag']:>5.0f}x{cb['pupil']:>9.2f} mm{cb['tfov']:>9.2f} deg   {quality_note(cb['mag'], cb['pupil'], ap)}")
        lines.append("")
        lines.append("True field = apparent FOV / magnification. Stock 0.965 inch eyepieces often have narrower real fields than their label.")
        self.set_text(self.box_combos, "\n".join(lines))

        # magnification card
        efl, afov, bl = self.num("ep_fl"), self.num("ep_afov"), self.num("ep_barlow", 1.0)
        tfov_deg = None
        if efl and efl > 0 and afov and afov > 0 and bl and bl > 0:
            mag = fl * bl / efl
            pupil = ap / mag
            tfov_deg = afov / mag
            self.out["mag"].configure(text="\n".join([
                f"Magnification:  {mag:.1f}x   ({mag / sn['max_mag'] * 100:.0f}% of the practical maximum)",
                f"Exit pupil:     {pupil:.2f} mm   -> {quality_note(mag, pupil, ap)}",
                f"True field:     {tfov_deg:.2f} deg  =  {tfov_deg * 60:.0f} arcmin   (Moon is 31 arcmin wide)",
                f"Effective f/:   f/{sn['f'] * bl:.1f}   focal length {fl * bl:.0f} mm",
            ]))
        else:
            self.out["mag"].configure(text="Enter positive numbers.")

        size = self.num("fit_size")
        if size and size > 0:
            lines = []
            for cb in combos:
                tf = cb["tfov"] * 60.0
                pct = size / tf * 100.0
                verdict_txt = "fits" if pct <= 90 else "too big"
                lines.append(f"{cb['label']:<26} field {tf:>5.0f}'   target fills {pct:>4.0f}%   {verdict_txt}")
            self.out["fit"].configure(text="\n".join(lines))
        else:
            self.out["fit"].configure(text="Enter a size in arcmin.")

        v = self.num("ang_val")
        unit = self.opt["ang_unit"].get()
        if v is not None:
            arcsec = v * {"degrees": 3600.0, "arcminutes": 60.0, "arcseconds": 1.0, "radians": 206264.806}.get(unit, 1.0)
            self.out["ang"].configure(text=f"= {arcsec / 3600.0:.6g} deg  =  {arcsec / 60.0:.6g} arcmin  =  {arcsec:.6g} arcsec  =  {arcsec / 206264.806:.6g} rad")
        else:
            self.out["ang"].configure(text="")
        size_km, dist_km = self.num("phys_size"), self.num("phys_dist")
        if size_km and dist_km and size_km > 0 and dist_km > 0:
            ang = 206264.806 * size_km / dist_km
            extra = ""
            if tfov_deg:
                extra = f"\nIn the eyepiece above it fills {ang / 3600.0 / tfov_deg * 100:.1f}% of the field, and looks {ang * (fl * bl / efl) / 3600.0:.2f} deg wide to your eye."
            self.out["phys"].configure(text=f"Angular size: {fmt_angle(ang)}   ({ang:.3g} arcsec)\n"
                                            f"Magnification so the eye sees it as 1 arcmin (barely resolved): {60.0 / ang:.0f}x   "
                                            f"for a comfortable 2 arcmin: {120.0 / ang:.0f}x{extra}")
        else:
            self.out["phys"].configure(text="")
        sep, feat = self.num("dbl_sep"), self.num("feat")
        res = [f"Aperture limits: Dawes {sn['dawes']:.2f}\"  Rayleigh {sn['rayleigh']:.2f}\"  (nothing finer, whatever the magnification)"]
        if sep and sep > 0:
            if sep < sn["dawes"] * 0.9:
                res.append(f"A {sep:.1f}\" pair is below Dawes limit: you will not split it with {ap:.0f} mm.")
            else:
                res.append(f"A {sep:.1f}\" pair can be split. Use at least about {120.0 / sep:.0f}x" +
                           (" (and steady air)." if sep < sn["dawes"] * 2 else "."))
        if feat and feat > 0:
            if feat < sn["dawes"]:
                res.append(f"A {feat:.1f}\" feature is finer than the Dawes limit: not resolvable.")
            else:
                res.append(f"A {feat:.1f}\" feature needs about {120.0 / feat:.0f}x to be comfortable (barely visible at {60.0 / feat:.0f}x).")
        self.out["res"].configure(text="\n".join(res))
        dec = self.num("drift_dec", 0.0)
        if tfov_deg:
            full = drift_seconds(tfov_deg, dec)
            self.out["drift"].configure(text=f"With the eyepiece above ({tfov_deg:.2f} deg field):\n"
                                             f"edge to edge: {full:.0f} s ({full / 60:.1f} min).  Re-centre every {full / 2:.0f} s ({full / 120:.1f} min) to stay in the middle half.\n"
                                             f"At {mag:.0f}x a star leaves the field in about {full:.0f} s: higher power means more nudging.")
        else:
            self.out["drift"].configure(text="Fill in the eyepiece above first.")

        pix, w, h = self.num("cam_pix"), self.num("cam_w"), self.num("cam_h")
        cb, fwhm, cdec = self.num("cam_barlow", 1.0), self.num("cam_seeing", 2.5), self.num("cam_dec", 0.0)
        lens, fno, epf = self.num("cam_lens"), self.num("cam_fno"), self.num("cam_ep")
        afocal = self.opt["cam_mode"].get() == CAM_MODES[1]
        ok = pix and w and h and cb and fwhm and pix > 0 and cb > 0 and w > 0 and h > 0
        if ok and afocal:
            ok = bool(lens and epf and lens > 0 and epf > 0)
        if ok:
            efl = fl * cb * lens / epf if afocal else fl * cb  # afocal: telescope x (phone lens / eyepiece)
            cn = camera_numbers(efl, ap, pix, w, h, fwhm, cdec)
            samp = "oversampled (a shorter focal length or 2x2 binning would lose nothing)" if cn["sampling"] > 3.5 else \
                "well sampled" if cn["sampling"] >= 2 else "undersampled (add a Barlow if seeing allows)"
            moon_px = 1872.0 / cn["scale"]
            lines = [
                f"Effective:       {efl:.0f} mm,  f/{cn['n']:.1f}" + ("   (telescope x phone lens / eyepiece)" if afocal else ""),
                f"Image scale:     {cn['scale']:.2f} arcsec per pixel",
                f"Field of view:   {cn['fov_w']:.2f} x {cn['fov_h']:.2f} deg  ({cn['fov_w'] * 60:.0f}' x {cn['fov_h'] * 60:.0f}')",
                f"Sampling:        {cn['sampling']:.1f} pixels per seeing FWHM -> {samp}",
                f"Moon (31'):      {moon_px:.0f} px across  ({moon_px / w * 100:.0f}% of the frame width)",
                f"Jupiter (45\"):   about {45.0 / cn['scale']:.0f} px across",
                f"Ideal f-ratio:   about f/{cn['ideal_lo']:.0f} to f/{cn['ideal_hi']:.0f} for planets with this pixel size",
                f"Longest exposure without star trails on a fixed mount:  {cn['npf']:.2f} s (NPF rule), {cn['rule500']:.2f} s (500 rule)",
                "On an AZ mount, long exposures also suffer field rotation: use short frames and stack them.",
            ]
            if afocal:
                mag_ep = fl * cb / epf
                exit_pupil = ap / mag_ep
                tf = self.eyepiece_afov(epf) / mag_ep
                lines.append("")
                lines.append(f"Afocal setup:    {epf:g} mm eyepiece = {mag_ep:.0f}x, true field {tf:.2f} deg, exit pupil {exit_pupil:.1f} mm")
                if tf < cn["fov_w"]:
                    lines.append(f"Framing:         the eyepiece circle fills only {tf / cn['fov_w'] * 100:.0f}% of the frame width: zoom the phone about "
                                 f"{cn['fov_w'] / tf:.1f}x (or crop) to remove the black ring")
                else:
                    lines.append("Framing:         the frame is smaller than the eyepiece field, so nothing is wasted")
                if fno and fno > 0:
                    entrance = lens / fno
                    lines.append(f"Light match:     phone lens opening about {entrance:.1f} mm vs exit pupil {exit_pupil:.1f} mm -> " +
                                 ("corners will vignette: use a higher-power eyepiece" if exit_pupil > entrance else "all the light enters the lens"))
            self.out["cam"].configure(text="\n".join(lines))
        else:
            self.out["cam"].configure(text="Fill in the camera numbers." if not afocal else "Fill in the camera numbers, the phone lens and the eyepiece.")
