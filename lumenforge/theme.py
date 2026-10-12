# SPDX-License-Identifier: MIT
"""Design tokens (colour, spacing, type scale, icons) and DPI/motion helpers."""

import os
import sys
from PIL import Image, ImageDraw, ImageTk


ICON = {
    # Brand-derived controls use the version-1 LumenForge mark only where
    # a product identity cue is useful; action icons remain semantic.
    "brand": None,
    "open": "□", "import": "↓", "save": "□", "load": "□",
    "crop": "+", "straighten": "↻", "mask": "▤", "reset": "↺",
    "undo": "↶", "redo": "↷", "fit": "↔", "split": "◑",
    "before_after": "◐", "export": "↑", "batch": "▦",
    "focus": "□", "exit_focus": "×",
}


def _dpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_dpi()


# Design tokens.
T = {"bg":"#0B0B10","panel":"#131219","card":"#1A1824","card_hi":"#1F1C2E",
     "stroke":"#2A2638","stroke_hi":"#3B3552","text":"#EAEAF1",
     "text_dim":"#B7B3C8","accent":"#7B5CFF","accent2":"#8D6CFF",
     "gold":"#F59E0B","green":"#22C55E","red":"#EF4444","glass":"#16141E",
     # Semantic accessibility tokens (WCAG 2.1 AA). ``accent``/``accent2``
     # stay fill colors; use ``accent_fg`` for text and icons drawn on dark
     # surfaces, ``on_accent`` for text on solid accent fills, ``stroke_ui``
     # for control boundaries (>=3:1) and ``focus`` for the focus ring.
     "accent_fg":"#A78BFF","on_accent":"#FFFFFF","on_accent_dark":"#0B0B10",
     "stroke_ui":"#6F6A86","focus":"#A78BFF",
      "canvas":"#08080C","scrim":"#040408",
     "font":("Segoe UI",10),"font_sm":("Segoe UI",9),
     "title":("Segoe UI",15,"bold"),
     # Central design-system geometry tokens. Presentation only.
     "radius":8,"radius_sm":6,"radius_lg":12,
     "ctrl_h":36,"pad":8,"pad_sm":4,
     "muted":"#8E8AA1","disabled":"#5A5670","info":"#38BDF8","processing":"#8D6CFF",
      "accent_hi":"#A78BFF","grad_a":"#8D6CFF","grad_b":"#4F46E5",
      "white":"#ffffff","black":"#000000"}


# Geometric design system: a modular 8px base with a 4px sub-grid.
# Layouts must derive spacing, control heights, radii, and panel proportions
# from these invariants rather than isolated pixel guesses.
G = {
    "u": 4,          # sub-grid quantum
    "base": 8,       # primary spacing module
    "ctrl": 36,      # compact control height = 3.5 * base
    "row": 32,
    "section": 40,
    "rail": 68,
    "min_panel": 228,
    "max_left": 300,
    "max_right": 320,
    "gap": 8,
    "outer": 16,
    # Spacing scale (xs..2xl) from the visual specification.
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}


# Type scale: values match the previous literals.
F = {"ui": "Segoe UI", "mono": "Consolas",
     # Spec px -> Tk pt (x0.75): caption 11px, label 12px, body 14px, button 14px,
     # H3 16px, H2 18px, H1 22px, display 28px.
     "xs": 8, "sm": 9, "base": 10, "md": 11, "lg": 12, "h2": 14, "xl": 16, "display": 21}


def grid_px(n):
    """Snap a scalar to the 4px geometric grid."""
    return int(round(float(n) / G["u"])) * G["u"]


def grid_clamp(value, lo, hi):
    # Snap to the 4px grid. ``hi`` is a normal-layout cap; once the viewport
    # becomes too small, the minimum remains authoritative so geometry does
    # not collapse into off-grid fractional sizes.
    q = grid_px(value)
    return max(int(lo), min(int(hi), q))


def _mix(c1, c2, t):
    """Interpolate between two ``#rrggbb`` colors by ``t``."""
    c1 = c1.lstrip("#"); c2 = c2.lstrip("#")
    r1,g1,b1 = int(c1[0:2],16),int(c1[2:4],16),int(c1[4:6],16)
    r2,g2,b2 = int(c2[0:2],16),int(c2[2:4],16),int(c2[4:6],16)
    r = int(r1+(r2-r1)*t); g = int(g1+(g2-g1)*t); b = int(b1+(b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _rel_lum(c):
    """WCAG relative luminance of a ``#rrggbb`` color."""
    c = c.lstrip("#")
    out = []
    for i in (0, 2, 4):
        v = int(c[i:i+2], 16) / 255.0
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    """WCAG contrast ratio between two ``#rrggbb`` colors."""
    la, lb = _rel_lum(a), _rel_lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def legible(fg, bg, ratio=4.5):
    """Return ``fg`` lightened toward white just enough to reach ``ratio``
    against ``bg`` (unchanged when it already passes)."""
    if contrast(fg, bg) >= ratio:
        return fg
    for i in range(1, 21):
        c = _mix(fg, "#ffffff", i / 20.0)
        if contrast(c, bg) >= ratio:
            return c
    return "#ffffff"


def ink_on(bg, prefer=None, ratio=4.5):
    """Best text color for a solid ``bg`` fill: ``prefer`` when it is
    legible, otherwise the light/dark token with the higher contrast."""
    if prefer and contrast(prefer, bg) >= ratio:
        return prefer
    light, dark = T["on_accent"], T["on_accent_dark"]
    return light if contrast(light, bg) >= contrast(dark, bg) else dark


def _lumenforge_icon_image(size=128):
    """Render the purple L monogram used by the in-app header."""
    size = max(16, int(size))
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    scale = size / 64.0
    px = lambda n: int(round(n * scale))
    d.rounded_rectangle((px(2), px(2), px(61), px(61)),
                        radius=px(12), fill="#101018",
                        outline="#51466F", width=max(1, px(2)))
    # Brighter, bold monogram with a subtle two-stage highlight so it remains
    # recognisable at 16px in the Windows caption and taskbar.
    left, top, right, bottom = px(17), px(11), px(28), px(51)
    foot_right = px(49)
    d.rounded_rectangle((left, top, right, bottom), radius=max(1, px(2)),
                        fill="#C4B5FD")
    d.rounded_rectangle((left, px(39), foot_right, bottom),
                        radius=max(1, px(2)), fill="#A78BFA")
    d.line((px(19), px(14), px(19), px(36)), fill="#EDE9FE", width=max(1, px(1)))
    return im


def _lumenforge_icon():
    """Return the canonical monogram as a Tk PhotoImage."""
    return ImageTk.PhotoImage(_lumenforge_icon_image(64))


def _lumenforge_icon_sizes():
    """Return PIL icon sizes suitable for ICO generation (Windows shell)."""
    return [_lumenforge_icon_image(size) for size in (16, 24, 32, 48, 64, 128, 256)]


def _reduce_motion():
    """True when the user asked the OS (or LUMENFORGE_REDUCE_MOTION=1) for
    reduced animation. Decorative looping motion is then replaced by a
    static state indicator."""
    if os.environ.get("LUMENFORGE_REDUCE_MOTION", "") not in ("", "0"):
        return True
    if sys.platform.startswith("win"):
        try:
            import ctypes
            flag = ctypes.c_int(1)
            # SPI_GETCLIENTAREAANIMATION
            if ctypes.windll.user32.SystemParametersInfoW(
                    0x1042, 0, ctypes.byref(flag), 0):
                return flag.value == 0
        except Exception:
            pass
    return False


REDUCE_MOTION = _reduce_motion()


MOTION = {
    "micro": 90,
    "panel": 150,
    "dialog": 180,
    "toast": 2400,
    "scan": 55,
    # Cinematic reveal timings. These are presentation-only; the render
    # engine and image-processing cadence remain untouched.
}


UI_FONTS = ("Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial")
MONO_FONTS = ("SF Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")


def apply_fonts(root):
    """Pick the first installed family from the specification's stacks
    (Inter, else system sans; SF Mono / Consolas for numerals) and update
    the shared font tokens in place. Call once, right after the root exists."""
    try:
        import tkinter.font as _tkfont
        have = set(_tkfont.families(root))
    except Exception:
        return
    ui = next((f for f in UI_FONTS if f in have), F["ui"])
    mono = next((f for f in MONO_FONTS if f in have), F["mono"])
    F["ui"], F["mono"] = ui, mono
    T["font"], T["font_sm"] = (ui, F["base"]), (ui, F["sm"])
    T["title"] = (ui, F["xl"], "bold")
