"""Basic offscreen Qt startup and navigation check."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QWidget

from gui.app import AstroApp
from gui.qt import Canvas


class QtStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_all_pages_build_and_navigate(self):
        window = AstroApp()
        try:
            self.assertEqual(set(window.pages), {"tonight", "forecast", "planner", "sky", "scope", "settings"})
            window.show()
            for key in window.pages:
                window.show_page(key)
                self.assertEqual(window.current, key)
                self.assertIs(window.page_stack.currentWidget(), window.pages[key])
                self.assertIsInstance(window.pages[key], QWidget)
            self.qt_app.processEvents()
            self.assertEqual(window.built, set(window.pages))
            self.assertIsInstance(window.g_dso, Canvas)
            self.assertIsInstance(window.plan_from, QLineEdit)
            self.assertIsInstance(window.lbl_loc, QLabel)
            self.assertIsInstance(window.pages["settings"], QFrame)
            self.assertIn("20 mm", window.box_eps.get("1.0", "end"))
            window.nav["forecast"].click()
            self.assertEqual(window.current, "forecast")
            window.resize(1280, 820)
            self.qt_app.processEvents()
            self.assertGreater(window.pages["forecast"].width(), 900)
        finally:
            window.close()
            self.qt_app.processEvents()



class WidgetLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_destroy_removes_from_winfo_children_synchronously(self):
        """destroy() must immediately detach from parent so clear/rebuild loops work correctly.

        Regression: the original implementation called deleteLater() without setParent(None),
        so winfo_children() still returned the widget until the next event-loop tick.  This
        caused ghost widgets in fill_tonight insights, show_geo_results and refresh_plan_list.
        """
        from gui.qt import Frame, Label

        parent = Frame(None, fg_color="transparent")
        child = Label(parent, text="ghost")
        child.pack()

        before = len(parent.winfo_children())
        child.destroy()
        after = len(parent.winfo_children())

        self.assertEqual(before, 1, "child should be present before destroy()")
        self.assertEqual(after, 0,
                         "destroy() must remove child synchronously (setParent(None) before deleteLater)")

    def test_rebuild_loop_no_ghost_widgets(self):
        """Simulate the clear-then-add pattern used by fill_tonight, show_geo_results etc."""
        from gui.qt import Frame, Label

        parent = Frame(None, fg_color="transparent")

        for _cycle in range(3):
            # Clear
            for w in parent.winfo_children():
                w.destroy()
            self.assertEqual(len(parent.winfo_children()), 0, "clear must leave zero children")
            # Populate
            for i in range(4):
                Label(parent, text=f"item {i}").pack()
            self.assertEqual(len(parent.winfo_children()), 4)

        # Final clear
        for w in parent.winfo_children():
            w.destroy()
        self.assertEqual(len(parent.winfo_children()), 0)


if __name__ == "__main__":
    unittest.main()
