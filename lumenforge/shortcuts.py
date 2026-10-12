# SPDX-License-Identifier: MIT
"""Single-key tool shortcuts, tool strip and the shortcut cheat sheet."""

import tkinter as tk

from .theme import F, G, T
from .widgets import Btn
from .winchrome import apply_dark_titlebar

SHORTCUTS = (
    ("Tools", (("R", "Crop / straighten"), ("Q", "Heal spot"), ("M", "Local masks"),
               ("W", "White-balance picker"), ("A", "Auto tone"), ("J", "Clipping overlay"))),
    ("View", (("Space (hold)", "Show original"), ("Y", "Split before / after"),
              ("Mouse wheel", "Adjust hovered slider"), ("Ctrl + wheel", "Zoom"),
              ("Esc", "Leave focus workspace"))),
    ("Edit", (("Ctrl + O", "Open image"), ("Ctrl + E", "Export"), ("Ctrl + K", "Command palette"),
              ("Ctrl + Z / Y", "Undo / redo"), ("Alt + 1-6", "Switch workspace"))),
    ("Sliders", (("F2 / Enter", "Type a value"), ("Del", "Reset slider"),
                 ("Double-click label", "Reset slider"), ("Alt + click header", "Solo a section"))),
)


class ShortcutsMixin:
    """Lightroom-style one-key tools plus a discoverable cheat sheet (?)."""

    def _install_shortcuts(self):
        keys = {"r": self.tc, "q": self.heal_toggle, "m": self.mask_tool,
                "w": self._wb_pick_toggle, "a": self.auto_tone, "y": self._ts}
        for k, fn in keys.items():
            self.bind_all("<KeyPress-%s>" % k, lambda e, fn=fn: self._tool_key(e, fn))
        for k in ("question", "slash"):
            self.bind_all("<KeyPress-%s>" % k, lambda e: self._tool_key(e, self.show_shortcuts))

    def _tool_key(self, e, fn):
        if e.state & 0x0004 or e.state & 0x20000 or e.state & 0x0008:  # Ctrl / Alt
            return None
        try:
            if self._typing():
                return None
        except Exception:
            return None
        fn()
        return "break"

    def _tool_strip(self, parent):
        """Icon strip of the main tools; every button repeats a keyboard shortcut."""
        row = tk.Frame(parent, bg=T["card"])
        row.pack(fill="x", pady=(0, G["u"]*2))
        for icon, tip, cmd in (
                ("✂", "Crop / straighten  (R)", self.tc),
                ("✚", "Heal spot  (Q)", self.heal_toggle),
                ("◍", "Local masks  (M)", self.mask_tool),
                ("◎", "White-balance picker  (W)", self._wb_pick_toggle),
                ("◐", "Auto tone  (A)", self.auto_tone),
                ("☀", "Clipping overlay  (J)", self.clip_toggle),
                ("⇄", "Split before / after  (Y)", self._ts),
                ("?", "Keyboard shortcuts  (?)", self.show_shortcuts)):
            Btn(row, "", cmd, w=32, h=30, fs=F["md"], icon=icon, tip=tip,
                bg=T["card"]).pack(side="left", padx=(0, 2))
        return row

    def show_shortcuts(self):
        old = self.__dict__.get("_shortcut_win")
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
            self._shortcut_win = None
            return
        win = tk.Toplevel(self, bg=T["panel"], highlightthickness=1,
                          highlightbackground=T["stroke_hi"])
        win.title("Keyboard shortcuts")
        win.transient(self)
        win.resizable(False, False)
        self._shortcut_win = win
        tk.Label(win, text="KEYBOARD SHORTCUTS", bg=T["panel"], fg=T["accent_fg"],
                 font=(F["ui"], F["lg"], "bold")).grid(row=0, column=0, columnspan=4,
                                                       sticky="w", padx=20, pady=(16, 8))
        for i, (title, rows) in enumerate(SHORTCUTS):
            col = (i % 2)*2
            r0 = 1+(i//2)*10
            tk.Label(win, text=title.upper(), bg=T["panel"], fg=T["text_dim"],
                     font=(F["ui"], F["xs"], "bold")).grid(row=r0, column=col, sticky="w",
                                                           padx=(20, 8), pady=(8, 2))
            for j, (k, d) in enumerate(rows):
                tk.Label(win, text=k, bg=T["card"], fg=T["accent_fg"], padx=6,
                         font=(F["mono"], F["base"], "bold")).grid(row=r0+1+j, column=col,
                                                                    sticky="w", padx=(20, 8), pady=2)
                tk.Label(win, text=d, bg=T["panel"], fg=T["text"],
                         font=(F["ui"], F["base"])).grid(row=r0+1+j, column=col+1,
                                                         sticky="w", padx=(0, 24))
        tk.Label(win, text="Press ? or Esc to close", bg=T["panel"], fg=T["text_dim"],
                 font=(F["ui"], F["sm"])).grid(row=30, column=0, columnspan=4,
                                               sticky="w", padx=20, pady=(12, 16))
        win.bind("<Escape>", lambda e: self.show_shortcuts())
        apply_dark_titlebar(win)
        win.focus_set()
