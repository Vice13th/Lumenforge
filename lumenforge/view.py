# SPDX-License-Identifier: MIT
"""Canvas geometry, zoom/pan and painting."""

from .theme import T
import numpy as np
from .config import PREVIEW_MAX, ZOOM_MAX
from .engine import LANCZOS
from .widgets import rnd
from .engine import to_pil
from PIL import Image, ImageTk
from .theme import F, _mix


class ViewMixin:
    """Canvas geometry, zoom/pan and painting."""

    def _geom(self, z, pan):
        """Single source of truth for preview placement: exact same
        formula (including the edge clamp) used by _paint() to actually
        draw the image, and by _zs()/pan logic to know where the image
        really is on screen. Previously _zs() re-derived the 'before
        zoom' position without applying this clamp, so once the image
        had been panned to an edge (or was smaller than the canvas on
        one axis) the zoom anchor math silently drifted from what was
        actually on screen — that mismatch, compounding over repeated
        zooms, is what produced the drift toward the top-left corner.

        Uses the stable _fit_wh reference (the fit-to-window size at
        z=1) rather than self._ph's actual pixel size — self.pv (and
        so self._ph) now grows in resolution as the user zooms in, and
        that must never feed back into the fit/zoom math itself."""
        cw = max(1, self.cnv.winfo_width())
        ch = max(1, self.cnv.winfo_height())
        pw, ph = self._fit_wh
        base = min(cw/pw, ch/ph, 1)
        s = base*z
        dw, dh = max(1, int(pw*s)), max(1, int(ph*s))
        fx, fy = (cw-dw)//2, (ch-dh)//2
        ox = min(max(fx+pan[0], cw-dw), 0) if dw > cw else fx
        oy = min(max(fy+pan[1], ch-dh), 0) if dh > ch else fy
        return cw, ch, dw, dh, fx, fy, ox, oy

    def _wh(self, e):
        if e.state & 4:
            return self._wheel_zoom(e)
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            w = None
        t = None
        while w is not None and w is not self:
            if w is getattr(self, "_pc", None):
                t = self._pc
                break
            if w is getattr(self, "_pci", None):
                t = self._pci
                break
            if w is getattr(self, "_sc", None):
                t = self._sc
                break
            w = w.master
        if t is not None:
            try:
                t.yview_scroll(int(-e.delta/120), "units")
            except Exception:
                pass

    def _wheel_zoom(self, e):
        """Route wheel input through the existing canonical zoom path."""
        if getattr(e, "num", None) == 4:
            direction = 1
        elif getattr(e, "num", None) == 5:
            direction = -1
        else:
            direction = 1 if e.delta > 0 else -1
        try:
            cx = e.x_root - self.cnv.winfo_rootx()
            cy = e.y_root - self.cnv.winfo_rooty()
        except Exception:
            cx = cy = None
        self._zs(1.15 if direction > 0 else 1/1.15, cx, cy)
        return "break"

    def _zs(self, f, cx=None, cy=None):
        """Zoom by factor f, anchored on canvas point (cx, cy) if given,
        else on the canvas center. Reads the actual on-screen geometry
        via _geom() (clamp included) so the anchor math always matches
        what is really drawn — no more drift toward a corner."""
        o = self._z
        n = float(np.clip(o*f, 1, ZOOM_MAX))
        if n == o:
            return
        if self._ph is None:
            self._z = n
            return
        cw, ch, dw_o, dh_o, fx_o, fy_o, ox_o, oy_o = self._geom(o, self._pan)
        if cx is None or cy is None:
            cx, cy = cw/2.0, ch/2.0
        # Fractional image-space position under the anchor point, based
        # on where the image ACTUALLY is right now (post-clamp)
        ix = (cx-ox_o)/dw_o if dw_o > 1e-6 else .5
        iy = (cy-oy_o)/dh_o if dh_o > 1e-6 else .5
        ix, iy = float(np.clip(ix, 0, 1)), float(np.clip(iy, 0, 1))
        # Geometry AFTER zoom (unclamped center fx_n/fy_n) — solve the
        # desired pan so the same image point lands back under the
        # anchor; _paint()/_geom() will (re-)clamp this at draw time,
        # exactly as it does for a manually dragged pan.
        self._z = n
        _, _, dw_n, dh_n, fx_n, fy_n, _, _ = self._geom(n, (0, 0))
        ox_n, oy_n = cx-ix*dw_n, cy-iy*dh_n
        self._pan = (int(ox_n-fx_n), int(oy_n-fy_n))
        self._paint()
        self._schedule_zoom_preview()

    def _schedule_zoom_preview(self):
        """Debounced: while the user is actively spinning the mouse
        wheel, _paint() alone (an upscaled draw of whatever self.pv
        already is) keeps the view responsive. Once zooming settles,
        rebuild self.pv at a resolution matching the new zoom level and
        re-render, so the view sharpens up instead of staying a
        stretched, low-res preview."""
        if self._zj:
            try:
                self.after_cancel(self._zj)
            except Exception:
                pass
        self._zj = self.after(180, self._sync_zoom_preview)

    def _sync_zoom_preview(self):
        self._zj = None
        if self.src is None:
            return
        if self._z <= 1.001:
            if self._pv_max > PREVIEW_MAX:
                self._mk_preview(PREVIEW_MAX)
                self.req()
            return
        target = PREVIEW_MAX*self._z
        # Only rebuild on a meaningful change — avoids a re-render for
        # every tiny zoom step, and never needlessly downgrades quality
        # mid-zoom.
        if target > self._pv_max*1.05:
            self._mk_preview(target)
            self.req()

    def _rz(self):
        self._z = 1
        self._pan = (0, 0)
        if self._zj:
            try:
                self.after_cancel(self._zj)
            except Exception:
                pass
            self._zj = None
        if self.src is not None and self._pv_max > PREVIEW_MAX:
            self._mk_preview(PREVIEW_MAX)
            self.req()
        self._paint()

    def _bp(self):
        self.cnv.bind("<Button-1>", self._pp)
        self.cnv.bind("<B1-Motion>", self._pm)
        self.cnv.bind("<ButtonRelease-1>", lambda e:
                      setattr(self, "_pd", None))
        self.cnv.bind("<Double-Button-1>", lambda e: self._rz())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cnv.bind(seq, self._wheel_zoom)

    def _pp(self, e):
        if self._hue_picking:
            self._hue_pick_at(e.x, e.y)
            return
        if getattr(self, "_heal_picking", False):
            self._heal_at(e.x, e.y)
            return
        if self._wb_picking:
            self._wb_pick_at(e.x, e.y)
            return
        if self._sp:
            cw = self.cnv.winfo_width()
            if cw > 2:
                self._sx = float(np.clip(e.x/cw, .02, .98))
                self._paint()
            return
        if self._ph is None or self._mod:
            return
        self._pd = (e.x, e.y, self._pan[0], self._pan[1])

    def _pm(self, e):
        if not self._pd or self._ph is None:
            return
        sx, sy, px, py = self._pd
        self._pan = (px+(e.x-sx), py+(e.y-sy))
        self._paint()

    def _disp_img(self, dw, dh):
        """PhotoImage of the current render at the actual on-screen
        target size (dw, dh), high-quality resampled. Cached by
        (dw, dh, id(self._lo)) so repeated _paint() calls during a pan
        drag — where neither the render nor the zoom level changed —
        don't pay for a fresh resize every frame.

        Previously _paint() drew self._ph (native preview resolution)
        straight onto the canvas with no resize at all, so the 'zoom'
        level only changed where the image was positioned, not its
        actual on-screen size or sharpness — that mismatch, on top of
        self.pv being capped at a small fixed resolution, is what made
        the zoomed-in preview look so poor."""
        key = (dw, dh, id(self._lo), self._clip_view)
        if self._disp_key == key and self._disp_cache is not None:
            return self._disp_cache
        img = to_pil(self._clip_array(self._lo)) if self._lo is not None \
            else ImageTk.getimage(self._ph)
        if img.size != (dw, dh):
            img = img.resize((dw, dh), LANCZOS)
        ph = ImageTk.PhotoImage(img)
        self._disp_key = key
        self._disp_cache = ph
        return ph

    def _status_zoom(self):
        lbl = getattr(self, "_zoom_lbl", None)
        if lbl is not None and self.pv is not None:
            lbl.configure(text=f"ZOOM  FIT \u00d7{float(self._z):.1f}")

    def _paint(self):
        self._status_zoom()
        self._seg_sync()
        if self._orig_hold and self.pv is not None:
            return self._so(True)
        if self._ph is None:
            self.cnv.delete("all")
            if hasattr(self, "_empty_open"):
                self._empty_open.place(relx=.5, rely=.61, anchor="center")
            cw = max(1, self.cnv.winfo_width())
            ch = max(1, self.cnv.winfo_height())
            if cw > 200 and ch > 120:
                # Empty canvas is treated as a darkroom entrance, not an
                # empty dashboard. The image remains the future hero.
                mx, my = cw//2, ch//2
                frame_w = min(620, cw-120)
                frame_h = min(330, max(220, ch-150))
                x0, y0 = mx-frame_w//2, my-frame_h//2-4
                x1, y1 = mx+frame_w//2, my+frame_h//2-4
                self.cnv.create_rectangle(x0, y0, x1, y1,
                                          outline=_mix(T["stroke"], T["accent"], .28))
                self.cnv.create_rectangle(x0+9, y0+9, x1-9, y1-9,
                                          outline=_mix(T["stroke"], T["gold"], .10))
                # The empty/loading state uses the exact same generated L
                # monogram as the titlebar and splash, not a separate diamond.
                try:
                    from PIL import ImageTk
                    from .theme import _lumenforge_icon_image
                    self._empty_brand_icon = ImageTk.PhotoImage(_lumenforge_icon_image(44))
                    self.cnv.create_image(mx, y0+36, image=self._empty_brand_icon)
                except Exception:
                    self.cnv.create_text(mx, y0+34, text="L",
                                          fill=T["accent_fg"],
                                          font=(F["ui"], 22, "bold"))
                self.cnv.create_text(mx, y0+82, text="LUMENFORGE",
                                      fill=T["text"], font=(F["ui"], F["display"], "bold"))
                self.cnv.create_line(mx-92, y0+101, mx+92, y0+101,
                                     fill=_mix(T["accent"], T["white"], .12))
                self.cnv.create_text(mx, y0+124, text="IMAGE LAB  •  LOOK APPLIED",
                                      fill=T["accent_fg"], font=(F["mono"], F["sm"], "bold"))
                self.cnv.create_text(mx, y0+155,
                                      text="Open a photograph to begin.",
                                      fill=T["text_dim"], font=(F["ui"], F["md"]))
                self.cnv.create_text(mx, y1-24,
                                      text="CTRL+O  OPEN     •     CTRL+K  COMMANDS     •     CTRL+WHEEL  ZOOM",
                                      fill=T["text_dim"], font=(F["mono"], F["xs"]))
            return
        if hasattr(self, "_empty_open"):
            self._empty_open.place_forget()
        self.cnv.delete("all")
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        self._off = (ox, oy)
        disp = self._disp_img(dw, dh)
        self.cnv.create_image(ox, oy, image=disp, anchor="nw")
        if self._z > 1.001:
            self.cnv.create_text(cw-58, ch-16, text=f"{self._z:.1f}x",
                                 fill=T["accent"],
                                 font=(F["mono"], F["md"], "bold"))
        if self._sp and self.pv is not None:
            op = Image.fromarray((np.clip(self.pv, 0, 1)*255)
                                 .astype(np.uint8))
            if op.size != (dw, dh):
                op = op.resize((dw, dh), LANCZOS)
            cut = max(1, int(dw*self._sx))
            crp = op.crop((0, 0, cut, dh))
            self._sph = ImageTk.PhotoImage(crp)
            sw = max(2, int(dw*self._sx))
            self.cnv.create_image(ox, oy, image=self._sph, anchor="nw")
            self.cnv.create_rectangle(ox+sw-1, oy, ox+sw+1, oy+dh,
                                      fill=T["accent"], outline="")
            self.cnv.create_text(ox+sw+8, oy+15, text="after",
                                 fill=T["accent"],
                                 font=(F["mono"], F["base"], "bold"))
            self.cnv.create_text(ox+sw-8, oy+15, text="before",
                                 fill=T["text"],
                                 font=(F["mono"], F["base"], "bold"))

    def _hist(self, a):
        """Modern RGB+Luma histogram: filled, semi-blended channel
        curves over a metallic glass card, plus small shadow/highlight
        clipping indicators — replacing the old plain 3-line plot on a
        flat dark background."""
        try:
            cv = self._hc
            cv.delete("all")
            W = cv.winfo_width()
            H = int(cv["height"])
            if W < 4:
                return
            rnd(cv, 1, 1, W-2, H-2, T["radius_sm"], fill=T["card"],
               outline=T["stroke"])
            top_c = _mix(T["card"], T["white"], .08)
            for i in range(H//2):
                t2 = 1-(i/max(1, H//2))
                cv.create_line(2, 2+i, W-2, 2+i,
                               fill=_mix(T["card"], top_c, t2))
            pad_t, pad_b = 14, 6
            ih = max(4, H-pad_t-pad_b)
            x = np.clip(np.asarray(a, np.float32), 0, 1)
            luma = x[..., 0]*.299+x[..., 1]*.587+x[..., 2]*.114
            bs = np.zeros((4, 128), np.float32)
            for c in range(3):
                hh_, _ = np.histogram(x[..., c], bins=128, range=(0, 1))
                bs[c] = np.log1p(hh_)
            bs[3], _ = np.histogram(luma, bins=128, range=(0, 1))
            bs[3] = np.log1p(bs[3])
            mx = float(bs[:3].max())
            if mx < 1e-6:
                return
            bs = bs/mx
            cols = (T["red"], T["green"], T["accent2"])
            for c, col in enumerate(cols):
                base_y = H-pad_b
                pts = [2, base_y]
                for i in range(128):
                    pts.extend((2+int(i*(W-4)/128),
                               base_y-int(bs[c, i]*ih)))
                pts.extend((W-2, base_y))
                cv.create_polygon(*pts, fill=_mix(T["card"], col, .30),
                                  outline=col, width=1, smooth=True)
            # Luma outline drawn last, on top, as a plain reference line.
            pts = []
            for i in range(128):
                pts.extend((2+int(i*(W-4)/128),
                           H-pad_b-int(min(1, bs[3, i])*ih)))
            if len(pts) >= 4:
                cv.create_line(*pts, fill=T["text"], width=1, smooth=True)
            # Clipping warnings: a meaningful pile-up in the very first
            # or last bin of any channel means crushed shadows / blown
            # highlights — flag it instead of leaving it to guesswork.
            clip_lo = bs[:3, 0].max() > .55
            clip_hi = bs[:3, -1].max() > .55
            if clip_lo:
                cv.create_oval(4, 4, 10, 10, fill=T["red"], outline="")
            if clip_hi:
                cv.create_oval(W-10, 4, W-4, 10, fill=T["gold"], outline="")
            cv.create_text(W/2, 8, text="RGB + LUMA", fill=T["text_dim"],
                           font=(F["mono"], F["xs"], "bold"))
        except Exception:
            pass

    def _ts(self):
        if self._ph is None:
            return
        self._sp = not self._sp
        self._bs.set_active(self._sp)
        self._paint()

    def _so(self, s):
        if self.pv is None:
            return
        if s:
            self.cnv.delete("all")
            _, _, dw, dh, _, _, ox, oy = self._geom(self._z, self._pan)
            img = to_pil(self.pv)
            if img.size != (dw, dh):
                img = img.resize((dw, dh), LANCZOS)
            self._oph = ImageTk.PhotoImage(img)
            self.cnv.create_image(ox, oy, image=self._oph, anchor="nw")
        else:
            self._orig_hold = False
            if getattr(self, "_seg", None) is not None:
                self._seg_style()
            self._paint()
