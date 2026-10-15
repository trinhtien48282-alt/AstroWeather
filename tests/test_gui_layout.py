"""Regression tests for the Tk-compat layer in gui/qt.py (offscreen Qt).

Each test pins a real bug: inner-vs-outer padding, CTk pixel fonts, stretched pack children, right-pack pinning,
ghost margin boxes, invisible-until-placed, exact widths, column minsize, Slider.set side effect, hover tracking.
Run: uv run pytest tests/test_gui_layout.py -v
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui import qt


def show(w, width=400, height=400):
    w.resize(width, height)
    w.show()
    QApplication.processEvents()
    w.layout().activate()
    QApplication.processEvents()


class LayoutSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_padding_is_outer_and_cards_keep_natural_height(self):
        root = qt.Frame(None)
        cards = []
        for i in range(2):
            c = qt.Frame(root, fg_color="#1b1b1b")
            c.pack(fill="x", padx=6, pady=6)
            qt.Label(c, text=f"card {i}").pack(anchor="w", padx=16, pady=8)
            cards.append(c)
        show(root, 400, 600)
        a, b = cards[0].geometry(), cards[1].geometry()
        self.assertEqual(a.left(), 6)                      # outer margin, not inner
        self.assertEqual(a.width(), 400 - 12)
        self.assertLess(a.height(), 100)                   # not stretched to share the 600 px
        self.assertGreaterEqual(b.top() - (a.top() + a.height()), 12)  # 6 + 6 gap, no extra Qt spacing

    def test_right_packed_items_pin_to_the_right_edge(self):
        root = qt.Frame(None)
        bar = qt.Frame(root)
        bar.pack(fill="x")
        left = qt.Label(bar, text="left")
        left.pack(side="left")
        btn = qt.Button(bar, text="R", width=60)
        btn.pack(side="right")
        status = qt.Label(bar, text="s")
        status.pack(side="right", padx=12)
        show(root, 600, 200)
        self.assertLess(left.geometry().left(), 5)
        self.assertGreater(btn.geometry().right(), 595)
        self.assertLess(status.geometry().right(), btn.geometry().left())

    def test_unplaced_widget_is_invisible_and_width_is_exact(self):
        root = qt.Frame(None)
        ent = qt.Entry(root, width=90)
        ent.pack(side="left")
        ghost = qt.Label(root, text="never packed")
        show(root, 600, 100)
        self.assertEqual(ent.width(), 90)
        self.assertFalse(ghost.isVisible())

    def test_destroy_leaves_no_ghost_margin_boxes(self):
        root = qt.Frame(None)
        for _ in range(3):
            for w in root.winfo_children():
                w.destroy()
            for i in range(4):
                qt.Label(root, text=str(i)).pack(anchor="w", padx=4, pady=2)
            lay = root.layout()
            self.assertEqual(lay.count() - 1, len(root.winfo_children()))  # minus the tail spacer
            self.assertEqual(root._n_start, 4)

    def test_grid_column_minsize_is_not_a_widget_minimum(self):
        page = qt.Frame(None)
        page.grid_columnconfigure(1, weight=1, minsize=380)
        qt.Label(page, text="x").grid(row=0, column=1)
        self.assertEqual(page.minimumWidth(), 0)
        self.assertEqual(page.layout().columnMinimumWidth(1), 380)

    def test_slider_set_does_not_fire_command(self):
        calls = []
        root = qt.Frame(None)  # keep a reference, same reason as the canvas test
        s = qt.Slider(root, from_=-3, to=36, number_of_steps=156, command=calls.append)
        s.set(5)
        self.assertEqual(calls, [])
        self.assertAlmostEqual(s.get(), 5.0, delta=0.25)

    def test_canvas_tracks_mouse_and_hints_requested_size(self):
        root = qt.Frame(None)  # keep a reference: an unreferenced Frame(None) is GC'd and deletes its children
        c = qt.Canvas(root, width=230, height=200)
        self.assertTrue(c.hasMouseTracking())
        self.assertEqual((c.sizeHint().width(), c.sizeHint().height()), (230, 200))

    def test_ctk_font_sizes_are_pixels(self):
        self.assertEqual(qt.Font(size=22, weight="bold").pixelSize(), 22)


class AppLevel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fonts_sidebar_and_gauges_survive_resize(self):
        from gui.app import AstroApp
        w = AstroApp()
        try:
            w.show()
            self.app.processEvents()
            # fonts: the global stylesheet must not override setFont()
            w.lbl_loc.ensurePolished()
            self.assertEqual(w.lbl_loc.font().pixelSize(), 15)  # QFontInfo reports -1 here; font() is what setFont/QSS decide
            self.assertGreater(w.lbl_loc.sizeHint().height(), w.lbl_status.sizeHint().height())
            # sidebar keeps its 190 px
            self.assertEqual(w.nav["tonight"].parentWidget().width(), 190)
            # gauges keep 230x200 when the window grows
            w.show_page("tonight")
            w.resize(1600, 900)
            self.app.processEvents()
            self.assertEqual((w.g_dso.width(), w.g_dso.height()), (230, 200))
            self.assertEqual((w.g_pl.width(), w.g_pl.height()), (230, 200))
        finally:
            w.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
