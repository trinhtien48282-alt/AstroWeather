import os
import statistics
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from gui.app import AstroApp

app = QApplication.instance() or QApplication([])
w = AstroApp()
w.resize(1260, 820)
w.show()
w.show_page("sky")
app.processEvents()
sky = w.cfg["sky"]
N = 30
for lines, names in ((False, False), (True, False), (False, True), (True, True)):
    sky["constellation_lines"], sky["constellation_names"] = lines, names
    w.draw_sky(); w.sky_canvas.grab()  # warm-up
    build, paint = [], []
    for _ in range(N):
        t = time.perf_counter(); w.draw_sky(); build.append(time.perf_counter() - t)
        t = time.perf_counter(); w.sky_canvas.grab(); paint.append(time.perf_counter() - t)
    print(f"lines={lines!s:5} names={names!s:5} items={len(w.sky_canvas.items):5} "
          f"build median {statistics.median(build)*1000:6.1f} ms  paint median {statistics.median(paint)*1000:6.1f} ms")
w.close()