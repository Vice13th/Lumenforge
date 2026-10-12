# SPDX-License-Identifier: MIT
"""Render scheduling and state assembly."""

import numpy as np
from .config import PREVIEW_ZOOM_MAX
from .engine import BILINEAR, RenderCancelled, RenderGeneration
import threading
from .engine import _rotate_straight, ensure_rgb
from .params import DEF
from .engine import to_pil
from .engine import ENG
from PIL import ImageTk


class RenderMixin:
    """Render scheduling and state assembly."""

    def _stg(self):
        t = {**DEF, **(self.ap or {})}
        for k, v in self.vars.items():
            t[k] = float(v.get())
        if self.curve_pts is not None:
            t["tone_curve_pts"] = self.curve_pts
        t["masks"] = self.masks
        t["spots"] = self.spots
        t["scene_prep"] = bool(self.v_prep.get())
        t["print_stock"] = bool(self.v_pr.get())
        t["print_strength"] = float(np.clip(self.v_ps.get(), 0, 1))
        t["aces_display"] = bool(self.v_aces.get())
        t.update(self._cm_params())
        s = float(np.clip(self.v_ss.get(), 0, 1))
        if t.get("lut3d_path"):
            t["lut3d_strength"] = s
        if s < .999:
            p = dict(t)
            for k, n in DEF.items():
                if isinstance(n, (int, float)) and not isinstance(n, bool):
                    p[k] = float(n)+(float(t[k])-float(n))*s
            t = p
        return t

    def _scd(self, key=None):
        if key is not None:
            self._ck = key
        if self._rj:
            try:
                self.after_cancel(self._rj)
            except Exception:
                pass
        self._rj = self.after(70, lambda: self.req())

    def req(self):
        if self.pv is None:
            return
        if not hasattr(self, "_render_generation"):
            self._render_generation = RenderGeneration()
        self._render_generation_id = self._render_generation.next()
        generation = self._render_generation_id
        if self._rb:
            # Newer requests invalidate the older worker. It may finish, but
            # its result is never committed to the UI.
            self._rp = True
            return
        self._track_undo()
        st = self._stg()
        rgb = self.pv
        ch = self._ck
        self._ck = None
        self._rb = True
        self._render_hud_show("Rendering")

        def work():
            try:
                self._render_generation.checkpoint(generation)
                o = ENG.render(rgb, st, changed_key=ch)
                self._render_generation.checkpoint(generation)
            except RenderCancelled:
                o = None
            except Exception:
                o = None
            self.after(0, lambda g=generation, out=o: self._rd(out, g))

        threading.Thread(target=work, daemon=True).start()

    def _rd(self, o, generation=None):
        if generation is not None and not self._render_generation.is_current(generation):
            # Stale completion: do not mutate render/UI state.
            self._rb = False
            if self._rp:
                self._rp = False
                self.after(10, self.req)
            return
        self._rb = False
        self._render_hud_hide()
        if o is not None:
            self._lo = o
            self._ph = ImageTk.PhotoImage(to_pil(o))
            self._disp_key = None
            self._disp_cache = None
            self._paint()
            self._hist(o)
        if self._rp:
            self._rp = False
            self.after(10, self.req)

    def _mk_preview(self, target_max):
        """Build self.pv at a resolution matching what's actually needed
        on screen: PREVIEW_MAX while fit-to-window, scaled up toward the
        full source resolution (capped at PREVIEW_ZOOM_MAX) as the user
        zooms in. Everything renders/regrades from this array, so this
        is what determines how sharp a zoomed-in preview looks — before,
        zooming just stretched the same small fit-to-window preview
        instead of drawing on more real source detail."""
        if self.src is None:
            return
        target_max = min(target_max, PREVIEW_ZOOM_MAX)
        if (self.mt.get("raw") and self.mt.get("raw_proxy") and
                target_max > max(self.src.size)):
            self._ensure_raw_full_source()
            base = self._o
            if abs(self._srot) > 1e-6:
                base = _rotate_straight(base, self._srot)
            if self.cr:
                w, h = base.size
                x0, y0, x1, y1 = self.cr
                self.src = base.crop((int(x0*w), int(y0*h), int(x1*w), int(y1*h)))
            else:
                self.src = base.copy()
        s = min(1, target_max/max(self.src.size))
        pvv = self.src if s >= 1 else self.src.resize(
            (max(1, int(self.src.width*s)),
             max(1, int(self.src.height*s))), BILINEAR)
        self.pv = ensure_rgb(pvv)
        self._pv_max = target_max
        self._tc.clear()
        ENG.inval_img()
