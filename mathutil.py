"""Small generic math helpers shared across AstroWeather. Stdlib only, no astronomy."""
import math

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def rad(x):
    return x * D2R


def deg(x):
    return x * R2D


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def piecewise(x, pts):
    """Linear interpolation through (x, y) points; clamps outside the range."""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None
