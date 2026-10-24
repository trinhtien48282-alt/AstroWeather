"""Colours and shapes for the sky chart (pure functions, no GUI, no NumPy).

These are STYLISED approximations for a pleasant chart, not radiative-transfer results.
"""
import math
from functools import lru_cache

MOON_BASE = (236, 230, 200)
SKY_STOPS = (  # Sun altitude (deg) -> (zenith RGB, horizon RGB); by day the horizon is paler (haze), at dusk it glows
    (20.0, ((40, 100, 190), (130, 175, 225))),
    (6.0, ((46, 96, 175), (150, 170, 205))),
    (0.0, ((44, 74, 140), (236, 140, 90))),    # sunrise/sunset: orange rim, mauve in between
    (-6.0, ((24, 38, 92), (112, 70, 120))),    # civil twilight end: violet-pink rim
    (-12.0, ((10, 20, 56), (40, 48, 100))),    # nautical: residual blue glow
    (-18.0, ((4, 8, 22), (16, 26, 60))),       # astronomical night: faint blue horizon glow
)
# B-V colour index -> RGB, kept pale so the tint is subtle
BV_STOPS = ((-0.3, (155, 176, 255)), (0.0, (202, 215, 255)), (0.6, (255, 244, 234)),
            (1.0, (255, 222, 180)), (1.6, (255, 190, 120)))
STAR_NEUTRAL = "#c9d3f0"


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


@lru_cache(maxsize=64)
def _bv_hex(tenths):
    bv = max(BV_STOPS[0][0], min(BV_STOPS[-1][0], tenths / 10.0))
    for (x0, c0), (x1, c1) in zip(BV_STOPS, BV_STOPS[1:]):
        if bv <= x1:
            return "#%02x%02x%02x" % tuple(round(v) for v in _lerp(c0, c1, (bv - x0) / (x1 - x0)))
    return "#%02x%02x%02x" % BV_STOPS[-1][1]


def bv_color(bv):
    """Hex colour for a B-V index (quantised to 0.1); None/NaN -> neutral, never an invented colour."""
    if bv is None or bv != bv:
        return STAR_NEUTRAL
    return _bv_hex(round(bv * 10))


def moon_color(alt):
    """RGB of the Moon at altitude `alt` (deg): white-yellow high up, orange-red near the horizon.
    Relative reddening 10**(-0.4*dk*(X-1)) with dk = (0, 0.08, 0.22) mag/airmass for R, G, B and X capped at 10."""
    x = min(10.0, 1.0 / math.sin(math.radians(max(alt, 5.0))) - 0.0)
    x = max(1.0, x)
    t = (1.0, 10 ** (-0.4 * 0.08 * (x - 1)), 10 ** (-0.4 * 0.22 * (x - 1)))
    return tuple(max(0, min(255, round(MOON_BASE[i] * t[i]))) for i in range(3))


def sky_colors(sun_alt, n):
    """n RGB colours from the zenith (index 0) to the horizon (index n-1) for a given Sun altitude."""
    if sun_alt >= SKY_STOPS[0][0]:
        z, h = SKY_STOPS[0][1]
    elif sun_alt <= SKY_STOPS[-1][0]:
        z, h = SKY_STOPS[-1][1]
    else:
        for (a0, (z0, h0)), (a1, (z1, h1)) in zip(SKY_STOPS, SKY_STOPS[1:]):
            if a1 <= sun_alt <= a0:
                t = (a0 - sun_alt) / (a0 - a1)
                z, h = _lerp(z0, z1, t), _lerp(h0, h1, t)
                break
    return [tuple(round(c) for c in _lerp(z, h, (i / (n - 1)) ** 1.5 if n > 1 else 0.0)) for i in range(n)]


def layer_colors(sun_alt):
    """(line colour, label colour) for constellation overlays that stay readable against the sky at that Sun altitude."""
    if sun_alt > 0:
        return "#c8d8f4", "#f4f8ff"
    if sun_alt > -12:
        return "#8fa6d6", "#d4e0fa"
    return "#31508a", "#7f9bd6"


def moon_phase_spans(radius, illum, rows=None):
    """Lit part of the Moon disc as horizontal spans [(y, x0, x1)] in a frame where the lit side is +x.
    illum is the lit fraction 0..1. The terminator is an ellipse with semi-axis (2k-1)*w per row, so lit area = k * disc.
    The caller rotates the spans towards the Sun and mirrors them if needed."""
    rows = rows or max(8, int(radius * 2))
    out = []
    for i in range(rows):
        y = -radius + (i + 0.5) * (2.0 * radius / rows)
        w = math.sqrt(max(0.0, radius * radius - y * y))
        x0 = -(2.0 * illum - 1.0) * w
        if x0 < w:
            out.append((y, x0, w))
    return out
