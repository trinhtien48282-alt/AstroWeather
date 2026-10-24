"""Sky chart drag lag fix. Run from the repo root:  python apply_sky_smooth.py

Cause (from reading gui/sky_page.py): on_sky_slider cancelled and re-armed its 30 ms redraw job on EVERY slider event
(a debounce), so while the slider keeps moving the chart never redraws; it jumps only when the mouse pauses. The comment
there already says "at most every ~30 ms" (a throttle). This makes the code do that.
Every edit must match exactly once. If any edit fails, NOTHING is written. Keeps line endings (CRLF or LF).
"""
import os
import sys

E = []  # (path, old, new)


def R(path, old, new):
    E.append((path, old, new))


R("gui/sky_page.py", '''        self.sky_ts = time.time() + float(value) * 3600.0
        if self._sky_job:
            self.after_cancel(self._sky_job)
        if self._sky_job2:
            self.after_cancel(self._sky_job2)
        self._sky_job = self.after(30, lambda: self.draw_sky(table=False))
        self._sky_job2 = self.after(300, self.draw_sky)
''', '''        self.sky_ts = time.time() + float(value) * 3600.0
        if not self._sky_job:  # throttle: cancelling here would starve the redraw while events keep arriving
            self._sky_job = self.after(30, self._sky_fast)
        if self._sky_job2:  # the table, in contrast, waits for the drag to settle
            self.after_cancel(self._sky_job2)
        self._sky_job2 = self.after(300, self._sky_full)

    def _sky_fast(self):
        self._sky_job = None
        self.draw_sky(table=False)

    def _sky_full(self):
        self._sky_job2 = None
        self.draw_sky()
''')


def main():
    texts, nl = {}, {}
    for path, old, new in E:
        if path not in texts:
            if not os.path.exists(path):
                sys.exit(f"missing file: {path} (run from the repo root)")
            with open(path, "r", encoding="utf-8", newline="") as f:
                texts[path] = f.read()
            nl[path] = "\r\n" if "\r\n" in texts[path] else "\n"
        o, n = old.replace("\n", nl[path]), new.replace("\n", nl[path])
        c = texts[path].count(o)
        if c != 1:
            sys.exit(f"NOTHING WRITTEN. {path}: expected 1 match, found {c} for:\n{old}")
        texts[path] = texts[path].replace(o, n)
    for path, text in texts.items():
        compile(text, path, "exec")
    for path, text in texts.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print(f"ok: {len(E)} edit, {len(texts)} file")


main()
