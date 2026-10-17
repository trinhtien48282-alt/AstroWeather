"""Canvas text anchoring and scroll-time rendering (offscreen Qt).

Bug 1: the anchor test was a substring match, so "center" matched "e" and centred numbers were right-anchored
       (drawn about half their width to the left of x).
Bug 2: every paint rebuilt a QFont and font metrics for every text item, visible or not.
Run: uv run python -m pytest tests/test_canvas_text_scroll.py -v
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication

from gui import qt

BG = "#0b1020"


def ink_span(img):
    """(first, last) pixel column that differs from the background."""
    cols = [x for x in range(img.width()) if any(img.pixelColor(x, y).name() != BG for y in range(img.height()))]
    return min(cols), max(cols)


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def canvas(self, w=200, h=60):
        self.root = qt.Frame(None)  # keep the parent alive
        c = qt.Canvas(self.root, width=w, height=h, bg=BG)
        c.resize(w, h)
        return c


class TextRectAnchors(_Base):
    def test_anchor_maths(self):
        fm = QFontMetricsF(QFont())
        rect = lambda a: qt.Canvas._text_rect(100.0, 50.0, a, "88", fm)
        self.assertAlmostEqual(rect("center").center().x(), 100.0)  # the regression: was right-anchored
        self.assertAlmostEqual(rect("center").center().y(), 50.0)
        self.assertAlmostEqual(rect("e").right(), 100.0)
        self.assertAlmostEqual(rect("w").left(), 100.0)
        self.assertAlmostEqual(rect("nw").left(), 100.0)
        self.assertAlmostEqual(rect("nw").top(), 50.0)
        self.assertAlmostEqual(rect("se").right(), 100.0)
        self.assertAlmostEqual(rect("se").bottom(), 50.0)


class RenderedTextPosition(_Base):
    def draw(self, anchor):
        c = self.canvas()
        kw = {} if anchor is None else {"anchor": anchor}
        c.create_text(100, 30, text="8888", fill="#ffffff", font=("Segoe UI", 14, "bold"), **kw)
        return ink_span(c.grab().toImage())

    def test_default_text_is_centred_on_x(self):  # heat-map numbers use the default anchor
        lo, hi = self.draw(None)
        self.assertAlmostEqual((lo + hi) / 2, 100, delta=2)

    def test_west_anchor_starts_at_x(self):
        lo, _hi = self.draw("w")
        self.assertTrue(99 <= lo <= 104, lo)

    def test_east_anchor_ends_at_x(self):
        _lo, hi = self.draw("e")
        self.assertTrue(96 <= hi <= 101, hi)


class ScrollRendering(_Base):
    def build(self):
        c = self.canvas()
        for i in range(400):  # like the heat map: a rectangle and a number per cell
            c.create_rectangle(i * 30, 5, i * 30 + 25, 55, fill="#123456", outline="")
            c.create_text(i * 30 + 12, 30, text=str(i % 10), fill="#ffffff", font=("Segoe UI", 9))
        c.configure(scrollregion=(0, 0, 12000, 60))
        return c

    def test_scrolled_paint_reuses_cached_geometry_and_draws_only_visible_items(self):
        c = self.build()
        c.grab()  # first paint computes and stores every item's box
        self.assertTrue(all("box" in i for i in c.items))
        with mock.patch.object(qt, "_cached_font", side_effect=AssertionError("font/metrics rebuilt while scrolling")):
            c.xview_moveto(0.5)  # xoff = 6000
            img = c.grab().toImage()
        self.assertTrue(10 <= c.last_paint_count <= 20, c.last_paint_count)  # ~7 cells x (rect + number), of 800 items
        self.assertEqual(img.pixelColor(5, 10).name(), "#123456")           # the visible cell really rendered

    def test_cached_box_matches_a_fresh_one(self):
        c = self.build()
        c.grab()
        item = c.items[1]  # a text item
        cached = item["box"]
        item.pop("box")
        self.assertEqual(c._item_box(item), cached)


if __name__ == "__main__":
    unittest.main()
