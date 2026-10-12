# SPDX-License-Identifier: MIT
"""Crop, straighten, rotate and flip tools."""

from .theme import T
from .engine import FLIP_LEFT_RIGHT, FLIP_TOP_BOTTOM
from .engine import ROTATE_270
from .tools import Crop, Straighten


class CropMixin:
    """Crop, straighten, rotate and flip tools."""

    def tc(self):
        if self.src is None or self._ph is None or self._mask_tool:
            return
        if self._ov:
            self._ov.ca()
            return
        self._paint()
        _, _, dw, dh, _, _, _, _ = self._geom(self._z, self._pan)
        self._ov = Crop(self.cnv, (dw, dh), self._off,
                        self._ca, self._cc,
                        on_straighten=self._crop_straighten,
                        on_rotate=self._crop_rotate,
                        on_flip_h=self._crop_flip_h,
                        on_flip_v=self._crop_flip_v)
        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)

    def _crop_straighten(self):
        if self._ov:
            self._ov.ca()
        self.ts_tool()

    def _crop_rotate(self):
        if self._ov:
            self._ov.ca()
        self.rotate90()

    def _crop_flip_h(self):
        if self._ov:
            self._ov.ca()
        self.flip_axis(FLIP_LEFT_RIGHT)

    def _crop_flip_v(self):
        if self._ov:
            self._ov.ca()
        self.flip_axis(FLIP_TOP_BOTTOM)

    def rotate90(self):
        """Discrete 90° clockwise rotation, distinct from Straighten's
        fine-angle horizon fix. Any existing crop is cleared since a
        normalized crop rect defined for the old orientation no longer
        lines up once width and height swap."""
        if self._o is None:
            return
        self._o = self._o.transpose(ROTATE_270)
        if self.mt.get("raw") and self.mt.get("raw_proxy"):
            self._raw_geom_ops.append(("rot90", None))
        self.cr = None
        self._srot = 0.0
        self._rz()
        self._acs()
        self._rl()
        self._st.configure(text="✓ Rotated 90°", fg=T["text_dim"])
        self._ck = None
        self.req()

    def flip_axis(self, mode):
        """Flip does not change image dimensions, so any existing crop
        rect (normalized 0..1) still lines up and is intentionally kept."""
        if self._o is None:
            return
        self._o = self._o.transpose(mode)
        if self.mt.get("raw") and self.mt.get("raw_proxy"):
            self._raw_geom_ops.append(("flip", mode))
        self._acs()
        self._rz()
        self._rl()
        label = "Flipped horizontally" if mode == FLIP_LEFT_RIGHT \
            else "Flipped vertically"
        self._st.configure(text=f"✓ {label}", fg=T["text_dim"])
        self._ck = None
        self.req()

    def _ca(self, r):
        self._ov = None
        self._bp()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self.cr = r
        self._rz()
        self._acs()
        self._rl()
        self._st.configure(text="✓ Crop applied", fg=T["text_dim"])
        self._ck = None
        self.req()

    def _cc(self):
        self._ov = None
        self._bp()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._paint()

    def ts_tool(self):
        if self.src is None or self._ph is None or self._ov_str is not None \
                or self._mask_tool:
            return
        if self._ov:
            return
        self._ov_str = Straighten(self, self._ts_apply, self._ts_cancel)
        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)

    def _ts_apply(self, angle):
        self._ov_str = None
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._srot = float(angle)
        self._acs()
        self._rz()
        self._rl()
        self._st.configure(text=f"✓ Straightened {angle:+.1f}°",
                           fg=T["text_dim"])
        self._ck = None
        self.req()

    def _ts_cancel(self):
        self._ov_str = None
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._paint()
