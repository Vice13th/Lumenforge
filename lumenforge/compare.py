# SPDX-License-Identifier: MIT
"""Original / Processed switch over the image (the specification's viewer tabs)."""

import tkinter as tk

from .theme import F, T


class CompareMixin:
    """Segmented control: Original shows the untouched preview, Processed the edit."""

    _orig_hold = False

    def _seg_build(self):
        fr = tk.Frame(self.cnv, bg=T["glass"], highlightthickness=1,
                      highlightbackground=T["stroke"])
        self._seg_btn = {}
        for name, orig in (("Original", True), ("Processed", False)):
            b = tk.Label(fr, text=name, font=(F["ui"], F["sm"], "bold"), padx=12, pady=4,
                         cursor="hand2", takefocus=1)
            b.pack(side="left", padx=2, pady=2)
            b.bind("<Button-1>", lambda e, o=orig: self._seg_set(o))
            b.bind("<Return>", lambda e, o=orig: self._seg_set(o))
            b.bind("<space>", lambda e, o=orig: (self._seg_set(o), "break")[1])
            self._seg_btn[orig] = b
        self._seg = fr
        self._seg_style()

    def _seg_style(self):
        for orig, b in self._seg_btn.items():
            on = orig == self._orig_hold
            b.configure(bg=T["accent"] if on else T["glass"],
                        fg=T["on_accent"] if on else T["text_dim"])

    def _seg_set(self, orig):
        if self.pv is None:
            return
        self._orig_hold = orig
        self._seg_style()
        if orig:
            self._so(True)
        else:
            self._so(False)

    def _seg_sync(self):
        """Show the control only while an image is loaded."""
        if self._ph is None:
            if getattr(self, "_seg", None) is not None:
                self._seg.place_forget()
            return
        if getattr(self, "_seg", None) is None:
            self._seg_build()
        self._seg.place(relx=.015, rely=.03, anchor="nw")
        self._seg.lift()
