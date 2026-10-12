# SPDX-License-Identifier: MIT
"""Colour-mixer and tone-curve editors."""

import numpy as np
import tkinter as tk
from .engine import HSL_BANDS, IDENTITY_CURVE, _curve_fn
from .params import DEF, PARAM_INFO, _HSL_LABELS
from .theme import F, T
from .widgets import Btn, Param, Tip, rnd


_HSL_SWATCH = {"red":"#e04a44","orange":"#e8823a","yellow":"#d8c62e",
              "green":"#4caf50","aqua":"#26c6b0","blue":"#3f7fe0",
              "purple":"#8a5fd1","magenta":"#d1479f"}


class HSLMixer(tk.Frame):
    """Lightroom-style Color Mixer: one selected band's Hue/Saturation/
    Luminance sliders at a time, chosen via a row of color chips —
    replaces a flat 24-slider dump with the same interaction model as
    every current color-grading tool (Lightroom, Capture One, DaVinci)."""
    def __init__(self, master, app):
        super().__init__(master, bg=T["card"])
        self.app = app
        self.band = HSL_BANDS[0]
        chips = tk.Frame(self, bg=T["card"])
        chips.pack(fill="x", pady=(2, 6))
        self._chip_w = {}
        for b in HSL_BANDS:
            c = tk.Label(chips, text="", bg=_HSL_SWATCH[b], width=3, height=1,
                        relief="flat", cursor="hand2",
                        highlightthickness=2,
                        highlightbackground=T["card"])
            c.pack(side="left", padx=2)
            c.bind("<Button-1>", lambda e, b=b: self._select(b))
            Tip.bind(c, _HSL_LABELS[b])
            self._chip_w[b] = c
        top = tk.Frame(self, bg=T["card"])
        top.pack(fill="x")
        self._lbl = tk.Label(top, text="", bg=T["card"], fg=T["text"],
                             font=(F["ui"], F["base"], "bold"), anchor="w")
        self._lbl.pack(side="left")
        Btn(top, "Reset Color", self._reset_band, w=100, h=22, fs=8,
           icon="↺").pack(side="right")
        self._body = tk.Frame(self, bg=T["card"])
        self._body.pack(fill="x")
        Btn(self, "Reset All Colors", self._reset_all, w=140, h=24, fs=8,
           icon="⟲").pack(pady=(6, 2))
        self._select(self.band)
    def _select(self, band):
        self.band = band
        for b, w in self._chip_w.items():
            w.configure(highlightbackground=T["accent"] if b == band
                       else T["card"])
        self._lbl.configure(text=_HSL_LABELS[band])
        for w in self._body.winfo_children():
            w.destroy()
        for comp, label in (("hue", "Hue"), ("sat", "Saturation"),
                            ("lum", "Luminance")):
            key = f"hsl_{band}_{comp}"
            Param(self._body, label, self.app.vars[key], self.app._scd,
                 -100, 100, "{:+.0f}", DEF.get(key, 0), key=key,
                 info=PARAM_INFO.get(key)).pack(fill="x", pady=2)
    def _reset_band(self):
        for comp in ("hue", "sat", "lum"):
            key = f"hsl_{self.band}_{comp}"
            self.app.vars[key].set(DEF.get(key, 0))
        self._select(self.band)
        self.app._scd(f"hsl_{self.band}_hue")
    def _reset_all(self):
        for b in HSL_BANDS:
            for comp in ("hue", "sat", "lum"):
                key = f"hsl_{b}_{comp}"
                self.app.vars[key].set(DEF.get(key, 0))
        self._select(self.band)
        self.app._scd("hsl_red_hue")


class _CurveCanvas(tk.Canvas):
    """Draggable parametric curve editor for ONE channel: click empty
    space to add a control point, drag a point to reshape the curve
    (endpoints stay pinned to x=0/x=1), right-click a middle point to
    remove it. Curve shape/sampling matches _curve_fn exactly, so
    what's drawn here is exactly what the render engine applies."""
    def __init__(self, master, on_change, h=170, line_color=None):
        super().__init__(master, height=h, bg=T["card"],
                         highlightthickness=2, highlightbackground=T["card"],
                         highlightcolor=T["focus"], cursor="crosshair",
                         takefocus=1)
        self._cb = on_change
        self._sel = 0
        self._line_c = line_color or T["accent"]
        self.pts = [(0.0, 0.0), (1.0, 1.0)]
        self._drag = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._down)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Button-3>", self._del_pt)
        # Keyboard model: Left/Right choose a point, Up/Down move it
        # vertically, Shift+Left/Right move it horizontally, Insert adds a
        # point after the selection, Delete removes it. Ctrl multiplies the
        # step by 5.
        self.bind("<FocusIn>", lambda e: self._draw())
        self.bind("<FocusOut>", lambda e: self._draw())
        self.bind("<Left>", lambda e: self._key_sel(-1))
        self.bind("<Right>", lambda e: self._key_sel(1))
        self.bind("<Up>", lambda e: self._key_move(0, 1, e))
        self.bind("<Down>", lambda e: self._key_move(0, -1, e))
        self.bind("<Shift-Left>", lambda e: self._key_move(-1, 0, e))
        self.bind("<Shift-Right>", lambda e: self._key_move(1, 0, e))
        self.bind("<Control-Up>", lambda e: self._key_move(0, 1, e))
        self.bind("<Control-Down>", lambda e: self._key_move(0, -1, e))
        self.bind("<Insert>", lambda e: self._key_add())
        self.bind("<Return>", lambda e: self._key_add())
        self.bind("<Delete>", lambda e: self._key_del())
        self.bind("<BackSpace>", lambda e: self._key_del())
        self._draw()
    def _key_sel(self, d):
        self._sel = int(np.clip(self._sel + d, 0, len(self.pts)-1))
        self._draw()
        return "break"
    def _key_move(self, dx, dy, e):
        step = .01 * (5 if (e.state & 0x4) else 1)
        i = self._sel = int(np.clip(self._sel, 0, len(self.pts)-1))
        x, y = self.pts[i]
        if dx and 0 < i < len(self.pts)-1:
            x = float(np.clip(x + dx*step, self.pts[i-1][0]+.01,
                              self.pts[i+1][0]-.01))
        y = float(np.clip(y + dy*step, 0, 1))
        self.pts[i] = (x, y)
        self._draw()
        self._cb(self.get_points())
        return "break"
    def _key_add(self):
        i = int(np.clip(self._sel, 0, len(self.pts)-1))
        if len(self.pts) >= 10 or i >= len(self.pts)-1:
            return "break"
        x = (self.pts[i][0] + self.pts[i+1][0]) / 2
        if x - self.pts[i][0] < .02:
            return "break"
        y = float(_curve_fn(self.pts)(np.array([x]))[0])
        self.pts.insert(i+1, (x, float(np.clip(y, 0, 1))))
        self._sel = i+1
        self._draw()
        self._cb(self.get_points())
        return "break"
    def _key_del(self):
        i = self._sel
        if 0 < i < len(self.pts)-1:
            del self.pts[i]
            self._sel = i-1
            self._draw()
            self._cb(self.get_points())
        return "break"
    def set_line_color(self, c):
        self._line_c = c
        self._draw()
    def set_points(self, pts):
        self.pts = sorted(tuple(p) for p in pts) if pts else \
            [(0.0, 0.0), (1.0, 1.0)]
        self._draw()
    def get_points(self):
        return list(self.pts)
    def _m(self, w, h):
        return 8, w-16, h-16
    def _to_c(self, x, y, w, h):
        m, iw, ih = self._m(w, h)
        return m+x*iw, (h-m)-y*ih
    def _to_xy(self, cx, cy, w, h):
        m, iw, ih = self._m(w, h)
        return (float(np.clip((cx-m)/max(1, iw), 0, 1)),
                float(np.clip(((h-m)-cy)/max(1, ih), 0, 1)))
    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = int(self["height"])
        rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill=T["card"],
           outline=T["stroke"])
        m, iw, ih = self._m(w, h)
        for i in (1, 2):
            gx, gy = m+iw*i/3, m+ih*i/3
            self.create_line(gx, m, gx, h-m, fill=T["stroke"])
            self.create_line(m, gy, w-m, gy, fill=T["stroke"])
        self.create_line(m, h-m, w-m, m, fill=T["stroke_hi"], dash=(2, 2))
        fn = _curve_fn(self.pts)
        xs = np.linspace(0, 1, 80)
        ys = fn(xs)
        line = []
        for xv, yv in zip(xs, ys):
            cx, cy = self._to_c(float(xv), float(yv), w, h)
            line.extend((cx, cy))
        self.create_line(*line, fill=self._line_c, width=2, smooth=True)
        try:
            focused = self.focus_get() is self
        except Exception:
            focused = False
        self._sel = int(np.clip(self._sel, 0, len(self.pts)-1))
        for n, (x, y) in enumerate(self.pts):
            cx, cy = self._to_c(x, y, w, h)
            if focused and n == self._sel:
                rnd(self, cx-8, cy-8, cx+8, cy+8, 8, fill="",
                    outline=T["focus"], width=2)
            rnd(self, cx-4, cy-4, cx+4, cy+4, 4, fill=self._line_c,
               outline=T["text"])
        if focused:
            sx, sy = self.pts[self._sel]
            self.create_text(12, 10, anchor="nw", fill=T["text_dim"],
                             font=(F["mono"], F["sm"]),
                             text="point %d/%d  in %.0f%%  out %.0f%%" % (
                                 self._sel+1, len(self.pts), sx*100, sy*100))
    def _hit(self, cx, cy, w, h):
        for i, (x, y) in enumerate(self.pts):
            px, py = self._to_c(x, y, w, h)
            if (px-cx)**2+(py-cy)**2 <= 81:
                return i
        return None
    def _down(self, e):
        w, h = self.winfo_width(), int(self["height"])
        self.focus_set()
        i = self._hit(e.x, e.y, w, h)
        if i is None:
            x, y = self._to_xy(e.x, e.y, w, h)
            if any(abs(x-p[0]) < .02 for p in self.pts) or len(self.pts) >= 10:
                return
            self.pts.append((x, y))
            self.pts.sort()
            i = self.pts.index((x, y))
        self._drag = self._sel = i
        self._draw()
    def _move(self, e):
        if self._drag is None:
            return
        w, h = self.winfo_width(), int(self["height"])
        x, y = self._to_xy(e.x, e.y, w, h)
        i = self._drag
        if i == 0:
            x = 0.0
        elif i == len(self.pts)-1:
            x = 1.0
        else:
            x = float(np.clip(x, self.pts[i-1][0]+.01,
                              self.pts[i+1][0]-.01))
        self.pts[i] = (x, y)
        self._draw()
        self._cb(self.get_points())
    def _del_pt(self, e):
        w, h = self.winfo_width(), int(self["height"])
        i = self._hit(e.x, e.y, w, h)
        if i is not None and 0 < i < len(self.pts)-1:
            del self.pts[i]
            self._draw()
            self._cb(self.get_points())


class CurveEditor(tk.Frame):
    """Per-channel Tone Curve: RGB/R/G/B tabs, each with its own
    _CurveCanvas and its own point list — matching Lightroom's Point
    Curve (master + per-channel Red/Green/Blue curves)."""
    CH_COLOR = {"rgb": None, "r": None, "g": None, "b": None}  # filled below
    CH_LABEL = {"rgb": "RGB", "r": "R", "g": "G", "b": "B"}
    def __init__(self, master, on_change, h=170):
        super().__init__(master, bg=T["card"])
        CurveEditor.CH_COLOR.update({"rgb": T["text"], "r": T["red"],
                                     "g": T["green"], "b": T["accent2"]})
        self._cb = on_change
        self.curves = {c: list(IDENTITY_CURVE) for c in ("rgb", "r", "g", "b")}
        self.ch = "rgb"
        tabs = tk.Frame(self, bg=T["card"])
        tabs.pack(fill="x", pady=(0, 3))
        self._tabs = {}
        for c in ("rgb", "r", "g", "b"):
            b = Btn(tabs, self.CH_LABEL[c], lambda c=c: self._switch(c),
                   w=44, h=22, fs=8, accent=self.CH_COLOR[c])
            b.pack(side="left", padx=2)
            self._tabs[c] = b
        self._tabs["rgb"].set_active(True)
        self.cv = _CurveCanvas(self, self._changed, h=h,
                               line_color=self.CH_COLOR["rgb"])
        self.cv.pack(fill="x")
    def _switch(self, ch):
        self.ch = ch
        for c, b in self._tabs.items():
            b.set_active(c == ch)
        self.cv.set_line_color(self.CH_COLOR[ch])
        self.cv.set_points(self.curves[ch])
    def _changed(self, pts):
        self.curves[self.ch] = pts
        self._cb(dict(self.curves))
    def set_curves(self, curves):
        curves = curves or {}
        self.curves = {c: list(curves.get(c) or IDENTITY_CURVE)
                       for c in ("rgb", "r", "g", "b")}
        self.cv.set_points(self.curves[self.ch])
    def get_curves(self):
        return dict(self.curves)
