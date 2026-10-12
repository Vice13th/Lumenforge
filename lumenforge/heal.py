# SPDX-License-Identifier: MIT
"""Click-to-heal spot removal tool."""

from tkinter import messagebox
from .config import APP_NAME
from .engine import heal_pick_source
from .theme import T

HEAL_RADIUS = .012


class HealMixin:
    """Spot healing: click a blemish, a clean nearby patch is cloned over it."""

    def heal_toggle(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        self._heal_picking = not getattr(self, "_heal_picking", False)
        self.cnv.configure(cursor="circle" if self._heal_picking else "arrow")
        self._st.configure(
            text="✚ Heal: click each blemish (Heal Spot again to stop)"
                 if self._heal_picking else "Heal Spot finished",
            fg=T["accent_fg"] if self._heal_picking else T["text_dim"])

    def heal_clear(self):
        if self.spots:
            self.spots.clear()
            self._scd("spots")
            self._st.configure(text="Healing spots cleared", fg=T["text_dim"])

    def _heal_at(self, cx, cy):
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        ix = (cx-ox)/dw if dw > 1e-6 else -1
        iy = (cy-oy)/dh if dh > 1e-6 else -1
        if not (0 <= ix <= 1 and 0 <= iy <= 1):
            return
        sx, sy = heal_pick_source(self.pv, ix, iy, HEAL_RADIUS)
        self.spots.append({"x": ix, "y": iy, "r": HEAL_RADIUS, "sx": sx, "sy": sy})
        self._scd("spots")
        self._st.configure(text=f"✚ Healed {len(self.spots)} spot(s)", fg=T["green"])
