# SPDX-License-Identifier: MIT
"""White-balance picker and auto white balance."""

from tkinter import messagebox
from .config import APP_NAME
from .engine import prep_scene
from .theme import T
from .engine import wb_from_point, wb_gray_world


class WhiteBalanceMixin:
    """White-balance picker and auto white balance."""

    def _wb_pick_toggle(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        self._wb_picking = not self._wb_picking
        if self._wb_pick_btn is not None:
            self._wb_pick_btn.set_active(self._wb_picking)
        self.cnv.configure(cursor="tcross" if self._wb_picking else "arrow")
        self._st.configure(
            text="🎯 Click a neutral gray or white area in the image"
                 if self._wb_picking else "Pick Gray Point cancelled",
            fg=T["accent_fg"] if self._wb_picking else T["text_dim"])

    def _wb_pick_at(self, cx, cy):
        self._wb_picking = False
        if self._wb_pick_btn is not None:
            self._wb_pick_btn.set_active(False)
        self.cnv.configure(cursor="arrow")
        if self.pv is None:
            return
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        ix = (cx-ox)/dw if dw > 1e-6 else .5
        iy = (cy-oy)/dh if dh > 1e-6 else .5
        if not (0 <= ix <= 1 and 0 <= iy <= 1):
            self._st.configure(text="Pick Gray Point — click was outside "
                               "the image", fg=T["red"])
            return
        h, w = self.pv.shape[:2]
        px, py = ix*(w-1), iy*(h-1)
        try:
            x = self.pv
            if self.v_prep.get():
                x = prep_scene(x)
            temp, tint = wb_from_point(x, px, py)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"White balance failed:\n{ex}")
            return
        self.vars["temperature"].set(temp)
        self.vars["tint"].set(tint)
        self._scd("temperature")
        self._st.configure(
            text=f"🎯 White Balance set from sample — "
                 f"Temperature {temp:+.0f} • Tint {tint:+.0f}",
            fg=T["green"])

    def auto_wb(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        try:
            x = self.pv
            if self.v_prep.get():
                x = prep_scene(x)
            temp, tint = wb_gray_world(x)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"White balance failed:\n{ex}")
            return
        self.vars["temperature"].set(temp)
        self.vars["tint"].set(tint)
        self._scd("temperature")
        self._st.configure(
            text=f"⚪ Auto White Balance — "
                 f"Temperature {temp:+.0f} • Tint {tint:+.0f}",
            fg=T["green"])
