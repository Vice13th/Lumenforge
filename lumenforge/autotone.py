# SPDX-License-Identifier: MIT
"""Auto tone action."""

from tkinter import messagebox
from .config import APP_NAME
from .engine import auto_tone_params, prep_scene
from .theme import T


class AutoToneMixin:
    """Auto tone: sets exposure and tonal sliders from the image histogram."""

    def auto_tone(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        try:
            x = self.pv
            if self.v_prep.get():
                x = prep_scene(x)
            vals = auto_tone_params(x)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Auto tone failed:\n{ex}")
            return
        for k, v in vals.items():
            self.vars[k].set(v)
        self._scd("exposure")
        self._st.configure(
            text=f"◐ Auto Tone — Exposure {vals['exposure']:+.2f} EV • "
                 f"Highlights {vals['highlights']:+.0f} • Shadows {vals['shadows']:+.0f}",
            fg=T["green"])
