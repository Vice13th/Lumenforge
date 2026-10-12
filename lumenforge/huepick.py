# SPDX-License-Identifier: MIT
"""Click-to-sample colour for range masks."""

from .engine import hue_at
from .theme import T


class HuePickMixin:
    """Sample a colour from the image and add a colour-range mask for it."""

    _hue_picking = False

    def hue_pick_toggle(self):
        if self.pv is None:
            return
        self._hue_picking = not self._hue_picking
        self.cnv.configure(cursor="crosshair" if self._hue_picking else "arrow")
        self._st.configure(
            text="🎨 Click a colour in the image to mask it" if self._hue_picking
            else "Colour pick cancelled",
            fg=T["accent_fg"] if self._hue_picking else T["text_dim"])

    def _hue_pick_at(self, cx, cy):
        self._hue_picking = False
        self.cnv.configure(cursor="arrow")
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        ix = (cx-ox)/dw if dw > 1e-6 else -1
        iy = (cy-oy)/dh if dh > 1e-6 else -1
        if not (0 <= ix <= 1 and 0 <= iy <= 1):
            return
        hue = hue_at(self.pv, ix, iy)
        if hue is None or not getattr(self, "_mask_tool", None):
            self._st.configure(text="That spot is too grey to pick a colour",
                               fg=T["red"])
            return
        self._mask_tool.add_hue(f"Colour {hue:.0f}°", hue, 40)
        self._st.configure(text=f"🎨 Masked hue {hue:.0f}°", fg=T["green"])
