"""Camera / imaging calculations: phone and camera presets and the image-scale / FOV / sampling numbers.

Stdlib only (depends on mathutil). No GUI, no NumPy.
"""
import math

from mathutil import rad

PHONE_PRESETS = {
    "Custom": None,
    "iPhone XS Max - wide 12 MP (f/1.8)": {"pix": 1.4, "w": 4032, "h": 3024, "lens": 4.25, "fno": 1.8,
                                           "note": "Best all-round lens for the eyepiece. 1.4 um pixels, about 4.25 mm real focal length."},
    "iPhone XS Max - telephoto 12 MP (f/2.4)": {"pix": 1.0, "w": 4032, "h": 3024, "lens": 6.0, "fno": 2.4,
                                                "note": "2x lens: fills the eyepiece circle better, smaller entrance pupil."},
    "iPhone 16 Pro Max - main 48 MP (f/1.8)": {"pix": 1.22, "w": 8064, "h": 6048, "lens": 6.8, "fno": 1.78,
                                               "note": "48 MP mode (ProRAW/HEIF). Pixels are tiny: expect them to oversample, bin to 12 MP for the Moon and planets."},
    "iPhone 16 Pro Max - main 12 MP binned": {"pix": 2.44, "w": 4032, "h": 3024, "lens": 6.8, "fno": 1.78,
                                              "note": "2x2 binned: 2.44 um effective pixels, cleaner for planets and the Moon."},
    "iPhone 16 Pro Max - ultra wide 48 MP (f/2.2)": {"pix": 0.7, "w": 8064, "h": 6048, "lens": 2.1, "fno": 2.2,
                                                    "note": "Very wide and tiny pixels: usually vignettes badly at an eyepiece."},
    "iPhone 16 Pro Max - 5x telephoto 12 MP (f/2.8)": {"pix": 1.12, "w": 4032, "h": 3024, "lens": 15.6, "fno": 2.8,
                                                      "note": "Long lens: great at filling the frame with a 20 mm eyepiece, but a larger exit pupil match is needed."},
}


def camera_numbers(fl, ap, pixel_um, w_px, h_px, fwhm, dec):
    scale = 206.265 * pixel_um / fl
    n = fl / ap
    return {"scale": scale, "fov_w": scale * w_px / 3600.0, "fov_h": scale * h_px / 3600.0, "n": n,
            "sampling": fwhm / scale if scale > 0 else 0.0,
            "npf": (16.856 * n + 0.0997 * fl + 13.713 * pixel_um) / (fl * max(0.05, math.cos(rad(dec)))),
            "rule500": 500.0 / fl, "ideal_lo": 3.0 * pixel_um, "ideal_hi": 5.0 * pixel_um}
