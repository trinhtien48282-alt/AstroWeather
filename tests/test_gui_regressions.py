"""Focused regressions: heat-map click offset, Canvas paint culling, responsive score gauges (offscreen Qt).

The gauge and click tests need the matching edits in gui/tonight_page.py and gui/forecast_page.py.
Run: uv run python -m pytest tests/test_gui_regressions.py -v
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui import qt
from gui.forecast_page import ForecastPage
from gui.theme import CW
from gui.tonight_page import TonightPage


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])


class HeatClickOffset(_Base):
    def test_click_maps_to_column_under_cursor_when_scrolled(self):
        root = qt.Frame(None)  # keep the parent referenced
        c = qt.Canvas(root, width=200, height=100, xscrollincrement=CW)
        c.resize(200, 100)
        c.configure(scrollregion=(0, 0, 50 * CW, 100))
        c.xview_scroll(3, "units")  # xoff = 3 columns
        self.assertEqual(c.xoff, 3 * CW)
        calls = []
        page = SimpleNamespace(analysis={"hours": [0] * 50}, hm_data=c, select_col=calls.append)
        c.bind("<Button-1>", lambda e: ForecastPage.on_heat_click(page, e))
        c.show()
        self.app.processEvents()
        QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(10, 5))  # absolute x = 10 + 3*CW -> column 3
        self.assertEqual(calls, [3])  # the double-offset bug gave 6


class CanvasCulling(_Base):
    def test_offscreen_items_are_skipped_and_visible_ones_render(self):
        root = qt.Frame(None)
        c = qt.Canvas(root, width=200, height=100)
        c.resize(200, 100)
        c.create_rectangle(40, 40, 60, 60, fill="#ff0000", outline="")      # visible
        c.create_rectangle(5000, 40, 5020, 60, fill="#00ff00", outline="")  # far right: skipped
        c.create_text(260, 50, text="x" * 40, anchor="e", fill="#ffffff", font=("Segoe UI", 9))  # right-anchored, reaches in
        c.create_text(260, 50, text="a", anchor="e", fill="#ffffff", font=("Segoe UI", 9))       # right-anchored, stays outside
        img = c.grab().toImage()
        self.assertEqual(c.last_paint_count, 2)
        self.assertEqual(img.pixelColor(50, 50).name(), "#ff0000")

    def test_scroll_offset_decides_visibility(self):
        root = qt.Frame(None)
        c = qt.Canvas(root, width=200, height=100)
        c.resize(200, 100)
        c.configure(scrollregion=(0, 0, 6000, 100))
        c.xview_moveto(0.8)  # xoff 4800
        c.create_rectangle(40, 40, 60, 60, fill="#ff0000", outline="")        # now off the left edge
        c.create_rectangle(4900, 40, 4920, 60, fill="#00ff00", outline="")    # visible at x = 100..120
        img = c.grab().toImage()
        self.assertEqual(c.last_paint_count, 1)
        self.assertEqual(img.pixelColor(110, 50).name(), "#00ff00")


class GaugeGeometry(_Base):
    def test_gauge_is_centred_and_unclipped_at_several_sizes(self):
        root = qt.Frame(None)
        for w, h in ((230, 200), (300, 260), (160, 140)):
            c = qt.Canvas(root, width=w, height=h)
            c.resize(w, h)
            TonightPage.draw_gauge(None, c, 72.0, "Deep-sky score")
            arcs = [i for i in c.items if i["kind"] == "arc"]
            self.assertEqual(len(arcs), 2)
            for a in arcs:
                x0, y0, x1, y1 = a["coords"]
                half = float(a["opts"]["width"]) / 2
                self.assertAlmostEqual((x0 + x1) / 2, w / 2)
                self.assertGreaterEqual(x0 - half, 0)
                self.assertGreaterEqual(y0 - half, 0)
                self.assertLessEqual(x1 + half, w)
                self.assertLessEqual(y1 + half, h)
            texts = [i for i in c.items if i["kind"] == "text"]
            title = texts[-1]
            self.assertEqual(title["opts"]["text"], "Deep-sky score")
            self.assertEqual(title["coords"], (w / 2, h - 10))      # title strip below the circle
            self.assertTrue(all(0 <= t["coords"][1] <= h for t in texts))
            self.assertTrue(all(t["coords"][0] == w / 2 for t in texts))

    def test_requested_size_keeps_original_geometry(self):
        root = qt.Frame(None)
        c = qt.Canvas(root, width=230, height=200)
        c.resize(230, 200)
        TonightPage.draw_gauge(None, c, None, "Planetary score")
        x0, y0, x1, y1 = c.items[0]["coords"]
        self.assertEqual((x0, y0, x1, y1), (115 - 76, 98 - 76, 115 + 76, 98 + 76))


if __name__ == "__main__":
    unittest.main()
