# SPDX-License-Identifier: MIT
"""Native Windows window chrome: dark title bar, caption and border colours."""

import sys

from .theme import T

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
_SWP_REFRESH = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # nomove|nosize|nozorder|noactivate|framechanged


def colorref(hex_color):
    """'#RRGGBB' -> Win32 COLORREF (0x00BBGGRR)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_dark_titlebar(win, caption=None, text=None, border=None):
    """Make the OS title bar dark and tint it with the theme (Windows 10 1809+;
    caption/text/border colours need Windows 11). Safe no-op elsewhere.
    Returns True when the dark-mode attribute was accepted."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        win.update_idletasks()
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        hwnd = wintypes.HWND(hwnd)

        def put(attr, value):
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0

        ok = put(DWMWA_USE_IMMERSIVE_DARK_MODE, 1) or put(DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1)
        put(DWMWA_CAPTION_COLOR, colorref(caption or T["bg"]))
        put(DWMWA_TEXT_COLOR, colorref(text or T["text"]))
        put(DWMWA_BORDER_COLOR, colorref(border or T["stroke"]))
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_REFRESH)
        return bool(ok)
    except Exception:
        return False
