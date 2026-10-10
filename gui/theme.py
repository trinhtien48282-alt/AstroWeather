"""Colours, sizes, table layouts and small presentation helpers shared by the GUI pages."""
from mathutil import clamp


CARD = "#1b1b1b"
DEEP = "#0b1020"
ACCENT = "#1f6aa5"

PLANET_COLORS = {"Mercury": "#b8b0a0", "Venus": "#fff2c0", "Mars": "#ff8a5c", "Jupiter": "#f0d9a8",
                 "Saturn": "#e8d28a", "Uranus": "#9be8e8", "Neptune": "#7ea0ff"}


def score_color(s):
    s = clamp(s)
    stops = [(0, (176, 52, 52)), (35, (214, 120, 52)), (60, (214, 186, 62)), (100, (52, 160, 96))]
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if s <= x1:
            t = (s - x0) / (x1 - x0)
            return "#%02x%02x%02x" % tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
    return "#34a060"


def text_on(hexcolor):
    r, g, b = int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)
    return "#101010" if (0.299 * r + 0.587 * g + 0.114 * b) > 135 else "#f4f4f4"


ALT_W, ALT_H = 600, 300
ALT_BANDS = ["#3d6a9e", "#2a3a6a", "#1a2650", "#101a3a", "#0a0d18"]
ALT_COLORS = ["#5ec8ff", "#ff9f5e", "#7ee787", "#ff7ab8", "#c9a7ff", "#f2e05e", "#6fe3d0", "#ff6b6b"]
CAM_MODES = ["Prime focus (camera at the focuser)", "Phone at the eyepiece (afocal)"]
BAND_COLORS = ["#d8b24a", "#b9783c", "#455a8f", "#27345f", "#0f1630"]
BAND_NAMES = ["day", "civil twilight", "nautical twilight", "astronomical twilight", "full night"]
HEAT_ROWS = [("Light", "band"), ("Moon altitude", "moon"), ("Cloud total %", "cloud"), ("   low %", "low"),
             ("   mid %", "mid"), ("   high %", "high"), ("Rain chance %", "rain"), ("Transparency", "trans"),
             ("Seeing (est.)", "seeing"), ("Wind", "wind"), ("Gusts", "gust"), ("Humidity %", "rh"),
             ("Dew margin", "dew"), ("Temperature", "temp"), ("DEEP-SKY score", "dso"), ("PLANETARY score", "planet")]
CW, RH, HDR, LBLW = 31, 25, 42, 132
LEVEL_COLORS = {"good": "#4cc38a", "info": "#a9b8d6", "warn": "#e0b84c", "bad": "#e06c6c"}


def fmt_temp(c, units):
    return f"{c * 9 / 5 + 32:.0f}F" if units.get("temp") == "F" else f"{c:.0f}C"


def conv_wind(kmh, units):
    u = units.get("wind", "km/h")
    return kmh / 3.6 if u == "m/s" else kmh * 0.621371 if u == "mph" else kmh
