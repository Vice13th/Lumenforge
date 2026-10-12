"""Behavioral Tk tests for the main application's toolbar geometry."""
import importlib.util
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lumenforge_main_under_test", ROOT / "lumenforge.py")
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


class ToolbarLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display unavailable: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.destroy()

    def setUp(self):
        self.root = type(self).root
        for child in self.root.winfo_children():
            child.destroy()

    def _geometry(self, width, height=760):
        self.root.deiconify()
        self.root.geometry(f"{width}x{height}+0+0")
        self.root.update_idletasks()

    def test_toolbar_height_is_fixed_at_72_pixels(self):
        self._geometry(1920)
        toolbar = APP._make_toolbar_frame(self.root)
        self.root.update_idletasks()
        self.assertEqual(toolbar.winfo_height(), APP.TOOLBAR_HEIGHT)
        self.assertEqual(APP.TOOLBAR_HEIGHT, 72)
        self.assertEqual(toolbar.pack_info().get("fill"), "x")
        self.assertFalse(bool(toolbar.pack_propagate()))

    def test_export_and_batch_group_is_reserved_to_the_right(self):
        self._geometry(1920)
        toolbar = APP._make_toolbar_frame(self.root)
        right = tk.Frame(toolbar, width=230, height=40, name="export_batch")
        center = tk.Frame(toolbar, width=700, height=40, name="center_actions")
        right.pack_propagate(False)
        center.pack_propagate(False)
        APP._pack_toolbar_groups(center, right)
        self.root.update_idletasks()

        self.assertLess(right.winfo_x(), toolbar.winfo_width())
        self.assertEqual(
            right.winfo_x() + right.winfo_width(),
            toolbar.winfo_width() - 16,
        )
        self.assertLessEqual(
            center.winfo_x() + center.winfo_width(), right.winfo_x()
        )

    def test_narrow_window_keeps_right_actions_visible_and_non_overlapping(self):
        self._geometry(1120)
        toolbar = APP._make_toolbar_frame(self.root)
        right = tk.Frame(toolbar, width=230, height=40, name="export_batch")
        center = tk.Frame(toolbar, width=950, height=40, name="center_actions")
        right.pack_propagate(False)
        center.pack_propagate(False)
        APP._pack_toolbar_groups(center, right)
        self.root.update_idletasks()

        self.assertEqual(toolbar.winfo_width(), 1120)
        self.assertGreaterEqual(right.winfo_x(), 0)
        self.assertEqual(
            right.winfo_x() + right.winfo_width(),
            toolbar.winfo_width() - 16,
        )
        self.assertLessEqual(
            center.winfo_x() + center.winfo_width(), right.winfo_x()
        )


if __name__ == "__main__":
    unittest.main()
