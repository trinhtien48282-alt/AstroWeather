"""Sky chart with constellation layers: no crash, hit-testing unchanged (offscreen Qt)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui.app import AstroApp


class SkyLayerRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_all_layer_combinations_draw_and_keep_hits(self):
        w = AstroApp()
        sky = w.cfg["sky"]
        saved = dict(sky)
        try:
            w.show()
            w.show_page("sky")
            self.qt_app.processEvents()
            seen = {}
            for lines in (False, True):
                for names in (False, True):
                    sky["constellation_lines"], sky["constellation_names"] = lines, names
                    w.draw_sky()  # must not raise
                    seen[(lines, names)] = (len(w.sky_canvas.items), [h[3] for h in w.sky_hits])
            base_items, base_hits = seen[(False, False)]
            for combo, (items, hits) in seen.items():
                self.assertEqual(hits, base_hits, f"hit list changed with layers {combo}")
                self.assertGreaterEqual(items, base_items)
        finally:
            sky.update(saved)
            w.close()
            self.qt_app.processEvents()


if __name__ == "__main__":
    unittest.main()