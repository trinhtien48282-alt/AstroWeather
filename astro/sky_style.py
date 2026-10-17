"""Colours and shapes for the sky chart (pure functions, no GUI, no NumPy).

These are STYLISED approximations for a pleasant chart, not radiative-transfer results.
"""
import math

MOON_BASE = (236, 230, 200)
SKY_STOPS = (  # Sun altitude (deg) -> (zenith RGB, horizon RGB); horizon is deliberately darker than the zenith
    (20.0, ((52, 112, 190), (36, 82, 142))),
    (6.0, ((46, 98, 170), (40, 78, 130))),
    (0.0, ((38, 70, 132), (112, 62, 70))),     # sunrise/sunset: warm, dim rim
    (-6.0, ((22, 40, 92), (62, 38, 66))),      # civil twilight end: violet rim
    (-12.0, ((10, 20, 56), (22, 24, 52))),     # nautical
    (-18.0, ((4, 8, 22), (6, 8, 18))),         # astronomical night
)


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


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
