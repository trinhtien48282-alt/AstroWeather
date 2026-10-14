"""Planner altitude graph: canvas drawing, time-axis zoom/pan and the hover read-out."""
import bisect
import time
from datetime import datetime, timedelta, timezone

from gui.theme import ALT_BANDS, ALT_COLORS, ALT_H, ALT_W
from weather.analysis import fmt_clock

MIN_SPAN = 7200.0  # shortest zoom window, seconds


def fit_view(v0, v1, full0, full1):
    """Clamp the window [v0, v1] into [full0, full1] keeping its span (between MIN_SPAN and the full range).
    Returns None when the window covers everything (the unzoomed state)."""
    full = full1 - full0
    span = min(max(v1 - v0, min(MIN_SPAN, full)), full)
    v0 = max(full0, min(v0, full1 - span))
    return None if span >= full - 1e-6 else (v0, v0 + span)


def zoom_view(view, full0, full1, frac, factor):
    """Zoom by factor (>1 = in) keeping the time at fraction frac (0..1) of the window where it is."""
    v0, v1 = view or (full0, full1)
    t = v0 + frac * (v1 - v0)
    span = (v1 - v0) / factor
    n0 = t - frac * span
    return fit_view(n0, n0 + span, full0, full1)


def lerp(ts, arr, t):
    """Value of the sampled curve (ts ascending) at time t, linearly interpolated: the plan's arrays are reused, nothing is recomputed."""
    k = min(max(bisect.bisect_right(ts, t) - 1, 0), len(ts) - 2)
    f = (t - ts[k]) / (ts[k + 1] - ts[k])
    return arr[k] + f * (arr[k + 1] - arr[k])


class AltitudeGraph:
    """Planner altitude graph: canvas drawing, time-axis zoom/pan and the hover read-out."""

    def draw_alt_graph(self):
        c = self.alt_canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 200 or H < 120:  # not laid out yet
            W, H = ALT_W, ALT_H
        L, R, T, B = 40, 10, 12, 30
        res = self.plan
        if not res:
            self.alt_view = None
            c.create_text(W / 2, H / 2, text="Run the planner, then click targets to plot their altitude", fill="#6b7390", font=("Segoe UI", 10))
            self.alt_geom = None
            return
        ts = res["ts"].tolist()
        t0, t1 = ts[0], ts[-1]
        v0, v1 = self.alt_view or (t0, t1)
        X = lambda t: L + (t - v0) / (v1 - v0) * (W - L - R)
        Y = lambda a: T + (90.0 - a) / 90.0 * (H - T - B)
        tv = [v0] + ts[bisect.bisect_right(ts, v0):bisect.bisect_left(ts, v1)] + [v1]  # window edges + the samples between
        series = lambda arr: [lerp(ts, arr, t) for t in tv]
        sun = series(res["sun_alt"].tolist())
        cls = [0 if v > -0.833 else 1 if v > -6 else 2 if v > -12 else 3 if v > -18 else 4 for v in sun]
        start = 0
        for k in range(1, len(cls) + 1):
            if k == len(cls) or cls[k] != cls[start]:
                c.create_rectangle(X(tv[start]), T, X(tv[min(k, len(tv) - 1)]), H - B, fill=ALT_BANDS[cls[start]], outline="")
                start = k
        for a in (0, 30, 60, 90):
            c.create_line(L, Y(a), W - R, Y(a), fill="#2a3558")
            c.create_text(L - 5, Y(a), text=f"{a}", anchor="e", fill="#8fa3c8", font=("Segoe UI", 8))
        ma = res["min_alt"]
        c.create_line(L, Y(ma), W - R, Y(ma), fill="#e0b84c", dash=(3, 3))
        span_h = (v1 - v0) / 3600.0
        step_h = 1 if span_h <= 10 else 2 if span_h <= 20 else 3 if span_h <= 36 else 6 if span_h <= 80 else 12
        tz = timezone(timedelta(seconds=res["offset"]))
        tick = datetime.fromtimestamp(v0, tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while tick.hour % step_h:
            tick += timedelta(hours=1)
        tt = tick.timestamp()
        while tt < v1:
            dt = datetime.fromtimestamp(tt, tz)
            c.create_line(X(tt), T, X(tt), H - B, fill="#1f2a4a")
            c.create_text(X(tt), H - B + 10, text=f"{dt.hour:02d}", fill="#cfd6e4", font=("Segoe UI", 8))
            if dt.hour == 0:
                c.create_text(X(tt), H - 8, text=dt.strftime("%a %d %b"), fill="#8fa3c8", font=("Segoe UI", 8, "bold"))
            tt += step_h * 3600

        def runs(vals):
            cur = []
            for k, a in enumerate(vals):
                if a >= 0:
                    cur.append((X(tv[k]), Y(a)))
                else:
                    if len(cur) > 1:
                        yield cur
                    cur = []
            if len(cur) > 1:
                yield cur
        for pts in runs(series(res["moon_alt"].tolist())):
            c.create_line(*[v for xy in pts for v in xy], fill="#d8d2a8", dash=(5, 4), width=1)
        legend_x = L + 6
        for n, ti in enumerate(self.plot_set):
            col = ALT_COLORS[n % len(ALT_COLORS)]
            for pts in runs(series(res["alt"][ti].tolist())):
                c.create_line(*[v for xy in pts for v in xy], fill=col, width=2)
            o = res["targets"][ti]
            label = o["id"]
            c.create_text(legend_x, T + 24, text=label, anchor="w", fill=col, font=("Segoe UI", 9, "bold"))
            legend_x += 8 + 7 * len(label)
        c.create_text(W - R - 4, T + 8, text="Moon (dashed)" + ("   zoomed: Fit resets" if self.alt_view else ""), anchor="e", fill="#d8d2a8", font=("Segoe UI", 8))
        now = res.get("now") or time.time()
        if v0 <= now <= v1:
            c.create_line(X(now), T, X(now), H - B, fill="#5ec8ff", width=2)
        self.alt_geom = (v0, v1, L, R, W, T, H, B)

    def on_alt_motion(self, event):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        v0, v1, L, R, W, T, H, B = g
        c = self.alt_canvas
        c.delete("cross")
        if not (L <= event.x <= W - R):
            return
        p, ts = self.plan, self.plan["ts"]
        t = v0 + (event.x - L) / (W - L - R) * (v1 - v0)
        c.create_line(event.x, T, event.x, H - B, fill="#ffffff", dash=(2, 2), tags="cross")
        parts = [fmt_clock(t, p["offset"])]
        for ti in self.plot_set[:6]:
            parts.append(f"{p['targets'][ti]['id']} {lerp(ts, p['alt'][ti], t):.0f}d")
        parts.append(f"Moon {lerp(ts, p['moon_alt'], t):.0f}d")
        c.create_text(L + 6, T + 8, text="   ".join(parts), anchor="w", fill="#e8eefc", font=("Segoe UI", 8, "bold"), tags="cross")

    def _alt_full(self):
        ts = self.plan["ts"]
        return float(ts[0]), float(ts[-1])

    def on_alt_resize(self, _event):
        if not self._alt_job:  # throttle: a window drag fires many Configure events
            self._alt_job = self.after(50, self._alt_redraw)

    def _alt_redraw(self):
        self._alt_job = None
        self.draw_alt_graph()

    def on_alt_wheel(self, e):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        frac = min(1.0, max(0.0, (e.x - g[2]) / (g[4] - g[2] - g[3])))
        self.alt_view = zoom_view(self.alt_view, *self._alt_full(), frac, 1.25 ** (e.delta / 120.0))
        self.draw_alt_graph()

    def on_alt_press(self, e):
        g = getattr(self, "alt_geom", None)
        self._alt_drag = (e.x, g[0], g[1]) if g else None

    def on_alt_drag(self, e):
        d, g = self._alt_drag, getattr(self, "alt_geom", None)
        if not d or not g or not self.alt_view or not self.plan:
            return
        x0, v0, v1 = d
        dt = (x0 - e.x) / (g[4] - g[2] - g[3]) * (v1 - v0)
        self.alt_view = fit_view(v0 + dt, v1 + dt, *self._alt_full())
        self.draw_alt_graph()

    def alt_fit(self):
        self.alt_view = None
        self.draw_alt_graph()
