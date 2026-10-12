"""Design-token gate: exact match with the visual specification + WCAG checks."""
import os, sys, types, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:  # headless CI: stub just enough for theme import
    class _D:
        def __init__(self, *a, **k): pass
        def __getattr__(self, n): return _D()
        def __call__(self, *a, **k): return _D()
    for n in ("tkinter", "tkinter.ttk", "tkinter.font", "PIL.ImageTk"):
        m = types.ModuleType(n); m.__getattr__ = lambda a: _D; sys.modules[n] = m
    import PIL; PIL.ImageTk = sys.modules["PIL.ImageTk"]
from lumenforge.theme import T, G, F

SPEC = {"bg": "#0B0B10", "panel": "#131219", "card": "#1A1824", "card_hi": "#1F1C2E",
        "stroke": "#2A2638", "text": "#EAEAF1", "text_dim": "#B7B3C8", "muted": "#8E8AA1",
        "disabled": "#5A5670", "accent": "#7B5CFF", "accent2": "#8D6CFF", "accent_hi": "#A78BFF",
        "grad_a": "#8D6CFF", "grad_b": "#4F46E5", "green": "#22C55E", "gold": "#F59E0B",
        "red": "#EF4444", "info": "#38BDF8"}


def lum(h):
    h = h.lstrip("#"); c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    c = [v/12.92 if v <= .03928 else ((v+.055)/1.055)**2.4 for v in c]
    return .2126*c[0]+.7152*c[1]+.0722*c[2]


def ratio(a, b):
    x, y = sorted((lum(T[a]), lum(T[b])), reverse=True)
    return (x+.05)/(y+.05)


class ThemeSpec(unittest.TestCase):
    def test_tokens_match_visual_specification(self):
        for k, v in SPEC.items():
            self.assertEqual(T[k].upper(), v, k)

    def test_geometry_and_type_match_specification(self):
        self.assertEqual((T["radius_sm"], T["radius"], T["radius_lg"], T["ctrl_h"]), (6, 8, 12, 36))
        self.assertEqual([G[k] for k in ("xs", "sm", "md", "lg", "xl", "xxl")], [4, 8, 12, 16, 24, 32])
        self.assertEqual((F["xs"], F["sm"], F["base"], F["lg"], F["xl"], F["display"]), (8, 9, 10, 12, 16, 21))


class ThemeContrast(unittest.TestCase):
    def test_text_pairs_meet_aa(self):
        for fg, bg in (("text", "bg"), ("text", "card"), ("text_dim", "panel"), ("text_dim", "card"),
                       ("text_dim", "card_hi"), ("muted", "card"), ("muted", "card_hi"),
                       ("accent_fg", "card"), ("accent_fg", "card_hi"), ("on_accent_dark", "accent_fg"),
                       ("red", "card"), ("green", "card"), ("gold", "card"), ("info", "card")):
            self.assertGreaterEqual(ratio(fg, bg), 4.5, f"{fg} on {bg}")

    def test_brand_fills_keep_large_text_contrast(self):
        # Fixed by the specification: white on #7B5CFF is 4.36:1, on #8D6CFF 3.67:1.
        for bg in ("accent", "accent2"):
            self.assertGreaterEqual(ratio("on_accent", bg), 3.0, bg)

    def test_ui_boundaries_and_focus_meet_non_text_aa(self):
        for fg, bg in (("stroke_ui", "bg"), ("stroke_ui", "card"), ("focus", "bg")):
            self.assertGreaterEqual(ratio(fg, bg), 3.0, f"{fg} on {bg}")


if __name__ == "__main__":
    unittest.main()
