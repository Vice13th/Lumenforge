import os, sys, types, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    class _D:
        def __init__(self, *a, **k): pass
        def __getattr__(self, n): return _D()
        def __call__(self, *a, **k): return _D()
    for n in ("tkinter", "tkinter.ttk", "tkinter.font", "PIL.ImageTk"):
        m = types.ModuleType(n); m.__getattr__ = lambda a: _D; sys.modules[n] = m
    import PIL; PIL.ImageTk = sys.modules["PIL.ImageTk"]
from lumenforge import winchrome


class WinChrome(unittest.TestCase):
    def test_colorref_is_bgr(self):
        self.assertEqual(winchrome.colorref("#0B0B10"), 0x100B0B)
        self.assertEqual(winchrome.colorref("#FF0000"), 0x0000FF)

    def test_noop_off_windows(self):
        if not sys.platform.startswith("win"):
            self.assertFalse(winchrome.apply_dark_titlebar(object()))


if __name__ == "__main__":
    unittest.main()
