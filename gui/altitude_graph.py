"""Planner altitude graph: canvas drawing and the hover read-out."""
import time
from datetime import datetime, timedelta, timezone

from gui.theme import ALT_BANDS, ALT_COLORS, ALT_H, ALT_W
from weather.analysis import fmt_clock


class AltitudeGraph:
    """Planner altitude graph: canvas drawing and the hover read-out."""

    def draw_alt_graph(self):
        c = self.alt_canvas
        c.delete("all")
        W, H, L, R, T, B = ALT_W, ALT_H, 40, 10, 12, 30
        res = self.plan
        if not res:
            c.create_text(W / 2, H / 2, text="Run the planner, then click targets to plot their altitude", fill="#6b7390", font=("Segoe UI", 10))
            self.alt_geom = None
            return
        ts = res["ts"].tolist()
        t0, t1 = ts[0], ts[-1]
        X = lambda t: L + (t - t0) / (t1 - t0) * (W - L - R)
        Y = lambda a: T + (90.0 - a) / 90.0 * (H - T - B)
        sun = res["sun_alt"].tolist()
        cls = [0 if v > -0.833 else 1 if v > -6 else 2 if v > -12 else 3 if v > -18 else 4 for v in sun]
        start = 0
        for k in range(1, len(cls) + 1):
            if k == len(cls) or cls[k] != cls[start]:
                c.create_rectangle(X(ts[start]), T, X(ts[min(k, len(ts) - 1)]), H - B, fill=ALT_BANDS[cls[start]], outline="")
                start = k
        for a in (0, 30, 60, 90):
            c.create_line(L, Y(a), W - R, Y(a), fill="#2a3558")
            c.create_text(L - 5, Y(a), text=f"{a}", anchor="e", fill="#8fa3c8", font=("Segoe UI", 8))
        ma = res["min_alt"]
        c.create_line(L, Y(ma), W - R, Y(ma), fill="#e0b84c", dash=(3, 3))
        span_h = (t1 - t0) / 3600.0
        step_h = 1 if span_h <= 10 else 2 if span_h <= 20 else 3 if span_h <= 36 else 6 if span_h <= 80 else 12
        tz = timezone(timedelta(seconds=res["offset"]))
        tick = datetime.fromtimestamp(t0, tz).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        while tick.hour % step_h:
            tick += timedelta(hours=1)
        tt = tick.timestamp()
        while tt < t1:
            dt = datetime.fromtimestamp(tt, tz)
            c.create_line(X(tt), T, X(tt), H - B, fill="#1f2a4a")
            c.create_text(X(tt), H - B + 10, text=f"{dt.hour:02d}", fill="#cfd6e4", font=("Segoe UI", 8))
            if dt.hour == 0:
                c.create_text(X(tt), H - 8, text=dt.strftime("%a %d %b"), fill="#8fa3c8", font=("Segoe UI", 8, "bold"))
            tt += step_h * 3600

        def runs(arr):
            cur = []
            for k, a in enumerate(arr):
                if a >= 0:
                    cur.append((X(ts[k]), Y(a)))
                else:
                    if len(cur) > 1:
                        yield cur
                    cur = []
            if len(cur) > 1:
                yield cur
        for pts in runs(res["moon_alt"].tolist()):
            c.create_line(*[v for xy in pts for v in xy], fill="#d8d2a8", dash=(5, 4), width=1)
        legend_x = L + 6
        for n, ti in enumerate(self.plot_set):
            col = ALT_COLORS[n % len(ALT_COLORS)]
            for pts in runs(res["alt"][ti].tolist()):
                c.create_line(*[v for xy in pts for v in xy], fill=col, width=2)
            o = res["targets"][ti]
            label = o["id"]
            c.create_text(legend_x, T + 24, text=label, anchor="w", fill=col, font=("Segoe UI", 9, "bold"))
            legend_x += 8 + 7 * len(label)
        c.create_text(W - R - 4, T + 8, text="Moon (dashed)", anchor="e", fill="#d8d2a8", font=("Segoe UI", 8))
        now = res.get("now") or time.time()
        if t0 <= now <= t1:
            c.create_line(X(now), T, X(now), H - B, fill="#5ec8ff", width=2)
        self.alt_geom = (t0, t1, L, R, W, T, H, B)

    def on_alt_motion(self, event):
        g = getattr(self, "alt_geom", None)
        if not g or not self.plan:
            return
        t0, t1, L, R, W, T, H, B = g
        c = self.alt_canvas
        c.delete("cross")
        if not (L <= event.x <= W - R):
            return
        ts = self.plan["ts"]
        k = max(0, min(len(ts) - 1, int(round((event.x - L) / (W - L - R) * (len(ts) - 1)))))
        c.create_line(event.x, T, event.x, H - B, fill="#ffffff", dash=(2, 2), tags="cross")
        parts = [fmt_clock(float(ts[k]), self.plan["offset"])]
        for ti in self.plot_set[:6]:
            parts.append(f"{self.plan['targets'][ti]['id']} {self.plan['alt'][ti][k]:.0f}d")
        parts.append(f"Moon {self.plan['moon_alt'][k]:.0f}d")
        c.create_text(L + 6, T + 8, text="   ".join(parts), anchor="w", fill="#e8eefc", font=("Segoe UI", 8, "bold"), tags="cross")
