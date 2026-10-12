# SPDX-License-Identifier: MIT
"""Canvas tools: crop, straighten and local masks."""

import math
import numpy as np
import tkinter as tk
from PIL import ImageTk
from tkinter import messagebox, ttk
from .config import APP_NAME
from .engine import BILINEAR, detect_sky_mask, to_pil
from .theme import F, T, ink_on
from .widgets import Btn, Tip


RTS = [("Free",None),("1:1",1),("4:3",4/3),("3:2",3/2),
       ("16:9",16/9),("9:16",9/16),("5:4",5/4),("4:5",4/5),("2:3",2/3),
       ("3:4",3/4),("2.39:1",2.39)]


class Crop:
    HN = 9
    def __init__(self, cv, sz, off, oa, oc, on_straighten=None,
                 on_rotate=None, on_flip_h=None, on_flip_v=None):
        self.cv = cv
        self.iw, self.ih = sz
        self.ox, self.oy = off
        self.oa, self.oc = oa, oc
        self.on_straighten = on_straighten
        self.on_rotate = on_rotate
        self.on_flip_h = on_flip_h
        self.on_flip_v = on_flip_v
        self.rt = None
        self.dg = None
        self.rc = [.12,.12,.88,.88]
        self._its = []
        self._bar()
        self.cv.configure(cursor="crosshair")
        self.cv.bind("<Button-1>", self._pr)
        self.cv.bind("<B1-Motion>", self._mv)
        self.cv.bind("<ButtonRelease-1>", lambda e: setattr(self, "dg", None))
        self.draw()
    def _bar(self):
        self._tb = tk.Frame(self.cv, bg=T["glass"], highlightthickness=1,
                            highlightbackground=T["stroke_hi"])
        self._i = tk.Label(self._tb, text="", bg=T["glass"],
                           fg=T["accent_fg"], font=(F["mono"], F["base"], "bold"))
        self._i.pack(side="left", padx=8)
        for n, r in RTS:
            b = tk.Label(self._tb, text=n, bg=T["card"], fg=T["text_dim"],
                         font=(F["ui"], F["sm"], "bold"), padx=7, pady=2,
                         cursor="hand2")
            b.pack(side="left", padx=2, pady=3)
            b.bind("<Button-1>", lambda e, r=r: self.sr(r))
        tk.Frame(self._tb, bg=T["stroke_hi"], width=1
                ).pack(side="left", fill="y", padx=4, pady=3)
        for txt, cb, tip in (
                ("╱ Straighten", self.on_straighten, "Fix horizon tilt"),
                ("⟳ Rotate", self.on_rotate, "Rotate 90° clockwise"),
                ("⇋ Flip H", self.on_flip_h, "Flip horizontally"),
                ("⇅ Flip V", self.on_flip_v, "Flip vertically")):
            if cb is None:
                continue
            gb = tk.Label(self._tb, text=txt, bg=T["card"],
                         fg=T["text_dim"], font=(F["ui"], F["sm"], "bold"),
                         padx=7, pady=2, cursor="hand2")
            gb.pack(side="left", padx=2, pady=3)
            gb.bind("<Button-1>", lambda e, cb=cb: cb())
            Tip.bind(gb, tip)
        a_ = tk.Label(self._tb, text="✓", bg=T["accent"], fg=T["on_accent"],
                      font=(F["ui"], F["base"], "bold"), padx=10, pady=3,
                      cursor="hand2")
        a_.pack(side="right", padx=(5,7), pady=3)
        a_.bind("<Button-1>", lambda e: self.ap())
        c_ = tk.Label(self._tb, text="✕", bg=T["red"], fg=ink_on(T["red"]),
                      font=(F["ui"], F["base"], "bold"), padx=8, pady=3,
                      cursor="hand2")
        c_.pack(side="right", pady=3)
        c_.bind("<Button-1>", lambda e: self.ca())
        self._tb.place(x=6, y=6)
    def sr(self, r):
        self.rt = r
        if r:
            cx = (self.rc[0]+self.rc[2])/2
            cy = (self.rc[1]+self.rc[3])/2
            ai = self.iw/self.ih
            if r > ai:
                w, h = .9, .9*self.iw/(r*self.ih)
            else:
                h, w = .9, .9*r*self.ih/self.iw
            self.rc = [cx-w/2, cy-h/2, cx+w/2, cy+h/2]
        self.draw()
    def _px(self):
        return [self.rc[0]*self.iw+self.ox, self.rc[1]*self.ih+self.oy,
                self.rc[2]*self.iw+self.ox, self.rc[3]*self.ih+self.oy]
    def draw(self):
        for i in self._its:
            self.cv.delete(i)
        self._its = []
        x0, y0, x1, y1 = self._px()
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        for (a, b, c, d) in [(0,0,cw,y0),(0,y1,cw,ch),(0,y0,x0,y1),
                             (x1,y0,cw,y1)]:
            self._its.append(self.cv.create_rectangle(
                a, b, c, d, fill=T["scrim"], stipple="gray50", outline=""))
        for i in (1, 2):
            gx, gy = x0+(x1-x0)*i/3, y0+(y1-y0)*i/3
            self._its.append(self.cv.create_line(gx, y0, gx, y1,
                               fill=T["accent2"], dash=(2,5)))
            self._its.append(self.cv.create_line(x0, gy, x1, gy,
                               fill=T["accent2"], dash=(2,5)))
        self._its.append(self.cv.create_rectangle(x0, y0, x1, y1,
                           outline=T["accent"], width=2))
        for (hx, hy) in [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]:
            self._its.append(self.cv.create_oval(hx-4.5, hy-4.5,
                               hx+4.5, hy+4.5, fill=T["accent"],
                               outline="#fff"))
        self._i.configure(text=f" {int((x1-x0)/self.iw*100)}% x "
                               f"{int((y1-y0)/self.ih*100)}%   "
                               f"{int(x1-x0)}x{int(y1-y0)}px")
    def _ha(self, px, py):
        px, py = px-self.ox, py-self.oy
        x0, y0 = self.rc[0]*self.iw, self.rc[1]*self.ih
        x1, y1 = self.rc[2]*self.iw, self.rc[3]*self.ih
        hs = self.HN+6
        for i, (hx, hy) in enumerate([(x0,y0),(x1,y0),(x0,y1),(x1,y1)]):
            if abs(px-hx) < hs and abs(py-hy) < hs:
                return i
        if x0 < px < x1 and y0 < py < y1:
            return 4
        return -1
    def _pr(self, e):
        self.dg = (self._ha(e.x, e.y), list(self.rc), e.x, e.y)
    def _mv(self, e):
        if not self.dg:
            return
        h, b, sx, sy = self.dg
        dx, dy = (e.x-sx)/self.iw, (e.y-sy)/self.ih
        r = list(b)
        if h in (0, 2):
            r[0] = b[0]+dx
        if h in (1, 3):
            r[2] = b[2]+dx
        if h in (0, 1):
            r[1] = b[1]+dy
        if h in (2, 3):
            r[3] = b[3]+dy
        if h == 4:
            w, hg = b[2]-b[0], b[3]-b[1]
            r[0] = min(max(b[0]+dx, 0), 1-w)
            r[2] = r[0]+w
            r[1] = min(max(b[1]+dy, 0), 1-hg)
            r[3] = r[1]+hg
        if self.rt and h in (0, 1, 2, 3):
            hg = (r[2]-r[0])*self.iw/(self.rt*self.ih)
            if h in (0, 1):
                r[1] = r[3]-hg
            else:
                r[3] = r[1]+hg
        r = [max(0, r[0]), max(0, r[1]), min(1, r[2]), min(1, r[3])]
        if r[2]-r[0] > .03 and r[3]-r[1] > .03:
            self.rc = r
            self.draw()
    def kill(self):
        for i in self._its:
            try:
                self.cv.delete(i)
            except Exception:
                pass
        try:
            self._tb.destroy()
        except Exception:
            pass
        for s_ in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.cv.unbind(s_)
        self.cv.configure(cursor="arrow")
    def ap(self):
        r = tuple(self.rc)
        self.kill()
        self.oa(r)
    def ca(self):
        self.kill()
        self.oc()


class Straighten(tk.Frame):
    """Floating glass panel for horizon straighten: a small live
    preview (rotated thumbnail + fixed rule-of-thirds guide lines so
    the tilt is easy to judge), an angle slider, and Apply/Cancel —
    committed via App._srot / _rotate_straight() so it's crop-free of
    black corners and fully undoable like Crop."""
    PW, PH = 300, 200
    def __init__(self, app, on_apply, on_cancel):
        super().__init__(app.cnv, bg=T["glass"], highlightthickness=1,
                         highlightbackground=T["stroke_hi"])
        self.app, self._oa, self._oc = app, on_apply, on_cancel
        self.angle = float(app._srot)
        hd = tk.Frame(self, bg=T["glass"])
        hd.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(hd, text="╱ STRAIGHTEN", bg=T["glass"], fg=T["accent_fg"],
                 font=(F["ui"], F["base"], "bold")).pack(side="left")
        self.pcv = tk.Canvas(self, width=self.PW, height=self.PH,
                             bg=T["scrim"], highlightthickness=0)
        self.pcv.pack(padx=8, pady=4)
        row = tk.Frame(self, bg=T["glass"])
        row.pack(fill="x", padx=8)
        tk.Label(row, text="Angle", bg=T["glass"], fg=T["text_dim"],
                 font=T["font_sm"]).pack(side="left")
        self._al = tk.Label(row, text="0.0°", bg=T["glass"],
                            fg=T["accent_fg"], font=(F["mono"], F["base"], "bold"))
        self._al.pack(side="right")
        self._sc = ttk.Scale(self, from_=-45, to=45, value=self.angle,
                             command=self._chg)
        self._sc.pack(fill="x", padx=8, pady=(0, 6))
        btns = tk.Frame(self, bg=T["glass"])
        btns.pack(fill="x", padx=8, pady=(0, 8))
        Btn(btns, "Apply", self._apply, w=100, h=28, icon="✓",
           kind="solid", tip="Apply straighten (crops out the tilt)"
           ).pack(side="left")
        Btn(btns, "Cancel", self._cancel, w=100, h=28, icon="✕"
           ).pack(side="right")
        self.place(x=6, y=6)
        self._render()
    def _chg(self, v):
        self.angle = float(v)
        self._al.configure(text=f"{self.angle:+.1f}°")
        self._render()
    def _render(self):
        self.pcv.delete("all")
        if self.app.pv is not None:
            try:
                im = to_pil(self.app.pv)
                if abs(self.angle) > 1e-6:
                    im = im.rotate(self.angle, resample=BILINEAR,
                                  expand=False, fillcolor=(15, 10, 14))
                iw, ih = im.size
                s = min(self.PW/iw, self.PH/ih)
                im = im.resize((max(1, int(iw*s)), max(1, int(ih*s))),
                              BILINEAR)
                self._ph = ImageTk.PhotoImage(im)
                self.pcv.create_image(self.PW//2, self.PH//2,
                                      image=self._ph)
            except Exception:
                pass
        # Fixed rule-of-thirds guide lines — stay put while the image
        # rotates under them, so the horizon's tilt against them is
        # what you're correcting.
        for gx in (self.PW/3, 2*self.PW/3):
            self.pcv.create_line(gx, 0, gx, self.PH, fill=T["accent"],
                                 dash=(2, 3))
        for gy in (self.PH/3, 2*self.PH/3):
            self.pcv.create_line(0, gy, self.PW, gy, fill=T["accent"],
                                 dash=(2, 3))
    def _apply(self):
        a = self.angle
        self.destroy()
        self._oa(a)
    def _cancel(self):
        self.destroy()
        self._oc()


class MaskTool:
    """Local adjustment masks: Radial / Linear / Brush, each drawn
    directly on the main canvas and carrying its own reduced slider
    set (Exposure/Contrast/Temperature/Saturation/Clarity) plus
    Feather and Invert. A floating glass panel lists existing masks
    (toggle/select/delete) and shows the selected mask's sliders.
    Scope cut: geometry isn't re-editable after creation — delete and
    redraw to reposition/resize."""
    MODES = (("radial", "Radial", "◎"), ("linear", "Linear", "▤"),
            ("brush", "Brush", "✎"))
    LPARAMS = [("exposure", "Exposure", -2, 2, "{:+.2f}"),
              ("contrast", "Contrast", -100, 100, "{:+.0f}"),
              ("temperature", "Temperature", -100, 100, "{:+.0f}"),
              ("saturation", "Saturation", -100, 100, "{:+.0f}"),
              ("clarity", "Clarity", -100, 100, "{:+.0f}")]
    def __init__(self, app):
        self.app = app
        self.mode = "radial"
        self.drag0 = None
        self.pending_brush = None
        self.sel = None
        self.tmp_ids = []
        self._build()
        self._bind_canvas()
        self.refresh_list()
    def _geom(self):
        _, _, dw, dh, _, _, _, _ = self.app._geom(self.app._z, self.app._pan)
        return dw, dh, self.app._off[0], self.app._off[1]
    def _to_norm(self, cx, cy):
        iw, ih, ox, oy = self._geom()
        return (float(np.clip((cx-ox)/max(iw, 1), 0, 1)),
                float(np.clip((cy-oy)/max(ih, 1), 0, 1)))
    def _build(self):
        self.panel = tk.Frame(self.app.cnv, bg=T["glass"],
                              highlightthickness=1,
                              highlightbackground=T["stroke_hi"])
        hd = tk.Frame(self.panel, bg=T["glass"])
        hd.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(hd, text="▨ LOCAL MASKS", bg=T["glass"], fg=T["accent_fg"],
                 font=(F["ui"], F["base"], "bold")).pack(side="left")
        Btn(hd, "Close", self.close, w=64, h=22, fs=8,
           icon="✕").pack(side="right")
        modes = tk.Frame(self.panel, bg=T["glass"])
        modes.pack(fill="x", padx=8)
        self._mode_btns = {}
        for key, label, icon in self.MODES:
            b = Btn(modes, label, lambda k=key: self._set_mode(k),
                   w=76, h=26, fs=8, icon=icon)
            b.pack(side="left", padx=2)
            self._mode_btns[key] = b
        self._mode_btns["radial"].set_active(True)
        auto_row = tk.Frame(self.panel, bg=T["glass"])
        auto_row.pack(fill="x", padx=8, pady=(4, 0))
        Btn(auto_row, "Auto Sky", self.detect_sky, w=150, h=24, fs=8,
           icon="☁", tip="Auto-detect and mask the sky (classical "
           "color/position/texture heuristic, not ML)").pack(side="left")
        for nm, ic, lo, hi in (("Shadows", "◐", 0.0, .35), ("Highlights", "◑", .65, 1.0)):
            Btn(auto_row, nm, lambda n=nm, a=lo, b=hi: self.add_range(n, a, b),
                w=96, h=24, fs=8, icon=ic,
                tip=f"Mask the {nm.lower()} (luminance range)").pack(side="left", padx=(4, 0))
        hue_row = tk.Frame(self.panel, bg=T["glass"])
        hue_row.pack(fill="x", padx=8, pady=(4, 0))
        for nm, ic, hc, wd in (("Skin", "☺", 25, 40), ("Greens", "❦", 110, 70), ("Blues", "≈", 215, 60)):
            Btn(hue_row, nm, lambda n=nm, c=hc, d=wd: self.add_hue(n, c, d),
                w=96, h=24, fs=8, icon=ic,
                tip=f"Mask {nm.lower()} by colour range").pack(side="left", padx=(0, 4))
        Btn(hue_row, "Pick", self.app.hue_pick_toggle, w=70, h=24, fs=8, icon="🎨",
            tip="Click a colour in the image to mask it").pack(side="left")
        self.list_fr = tk.Frame(self.panel, bg=T["glass"])
        self.list_fr.pack(fill="x", padx=8, pady=(6, 2))
        self.param_fr = tk.Frame(self.panel, bg=T["glass"])
        self.param_fr.pack(fill="x", padx=8, pady=(4, 4))
        tk.Label(self.panel, text="drag on image to draw • brush: drag "
                "multiple strokes, then pick it below to adjust",
                bg=T["glass"], fg=T["text_dim"], font=(F["ui"], F["xs"]),
                wraplength=230, justify="left").pack(fill="x",
                                                     padx=8, pady=(0, 8))
        self.panel.place(x=6, y=6)
    def _set_mode(self, k):
        self.mode = k
        for kk, b in self._mode_btns.items():
            b.set_active(kk == k)
        self.pending_brush = None
    def _bind_canvas(self):
        cv = self.app.cnv
        cv.configure(cursor="tcross")
        cv.bind("<Button-1>", self._down)
        cv.bind("<B1-Motion>", self._drag)
        cv.bind("<ButtonRelease-1>", self._up)
    def _unbind_canvas(self):
        cv = self.app.cnv
        for s in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            cv.unbind(s)
        cv.configure(cursor="arrow")
    def _clear_tmp(self):
        for i in self.tmp_ids:
            try:
                self.app.cnv.delete(i)
            except Exception:
                pass
        self.tmp_ids = []
    def _down(self, e):
        if self.mode == "brush":
            if self.pending_brush is None:
                m = {"type": "brush", "enabled": True, "invert": False,
                    "feather": .5, "radius": .04, "strokes": [],
                    "params": {k: 0 for k, *_ in self.LPARAMS}}
                self.app.masks.append(m)
                self.pending_brush = len(self.app.masks)-1
                self.sel = self.pending_brush
            x, y = self._to_norm(e.x, e.y)
            self.app.masks[self.pending_brush]["strokes"].append([(x, y)])
            self._stroke_px = [(e.x, e.y)]
        else:
            self.drag0 = (e.x, e.y)
    def _drag(self, e):
        if self.mode == "brush" and self.pending_brush is not None:
            x, y = self._to_norm(e.x, e.y)
            self.app.masks[self.pending_brush]["strokes"][-1].append((x, y))
            self._stroke_px.append((e.x, e.y))
            self._clear_tmp()
            if len(self._stroke_px) >= 2:
                flat = [c for pt in self._stroke_px for c in pt]
                self.tmp_ids.append(self.app.cnv.create_line(
                    *flat, fill=T["accent"], width=3, smooth=True,
                    capstyle="round"))
            return
        if self.drag0 is None:
            return
        self._clear_tmp()
        x0, y0 = self.drag0
        if self.mode == "radial":
            r = math.hypot(e.x-x0, e.y-y0)
            self.tmp_ids.append(self.app.cnv.create_oval(
                x0-r, y0-r, x0+r, y0+r, outline=T["accent"], width=2,
                dash=(4, 3)))
        elif self.mode == "linear":
            self.tmp_ids.append(self.app.cnv.create_line(
                x0, y0, e.x, e.y, fill=T["accent"], width=2, dash=(4, 3)))
    def _up(self, e):
        if self.mode == "brush":
            self._clear_tmp()
            self._after_change()
            return
        if self.drag0 is None:
            return
        x0, y0 = self.drag0
        self._clear_tmp()
        self.drag0 = None
        iw, ih, ox, oy = self._geom()
        nx0, ny0 = self._to_norm(x0, y0)
        if self.mode == "radial":
            r = math.hypot(e.x-x0, e.y-y0)
            if r < 4:
                return
            m = {"type": "radial", "enabled": True, "invert": False,
                "cx": nx0, "cy": ny0, "rx": r/max(iw, 1), "ry": r/max(ih, 1),
                "angle": 0, "feather": .5,
                "params": {k: 0 for k, *_ in self.LPARAMS}}
        elif self.mode == "linear":
            nx1, ny1 = self._to_norm(e.x, e.y)
            if abs(nx1-nx0) < .01 and abs(ny1-ny0) < .01:
                return
            m = {"type": "linear", "enabled": True, "invert": False,
                "x0": nx0, "y0": ny0, "x1": nx1, "y1": ny1, "feather": .4,
                "params": {k: 0 for k, *_ in self.LPARAMS}}
        else:
            return
        self.app.masks.append(m)
        self.sel = len(self.app.masks)-1
        self._after_change()
    def _after_change(self):
        self.app._ck = None
        self.app.req()
        self.refresh_list()
        self._show_params(self.sel)
    def add_hue(self, name, centre, width):
        if self.app.pv is None:
            return
        m = {"type": "range", "enabled": True, "invert": False, "feather": 0,
             "hue_range": [centre, width], "label": name,
             "params": {k: 0 for k, *_ in self.LPARAMS}}
        self.app.masks.append(m)
        self.sel = len(self.app.masks)-1
        self._after_change()

    def add_range(self, name, lo, hi):
        if self.app.pv is None:
            return
        m = {"type": "range", "enabled": True, "invert": False, "feather": 0,
             "lum_range": [lo, hi], "lum_feather": .12, "label": name,
             "params": {k: 0 for k, *_ in self.LPARAMS}}
        self.app.masks.append(m)
        self.sel = len(self.app.masks)-1
        self._after_change()

    def detect_sky(self):
        if self.app.pv is None:
            return
        try:
            wgt = detect_sky_mask(self.app.pv)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Sky detection failed:\n{e}")
            return
        m = {"type": "auto", "enabled": True, "invert": False, "feather": 0,
            "weight_map": wgt.tolist(),
            "params": {k: 0 for k, *_ in self.LPARAMS}}
        self.app.masks.append(m)
        self.sel = len(self.app.masks)-1
        self._after_change()
    def refresh_list(self):
        for w in self.list_fr.winfo_children():
            w.destroy()
        icon = {"radial": "◎", "linear": "▤", "brush": "✎", "auto": "☁", "range": "◐"}
        for i, m in enumerate(self.app.masks):
            row = tk.Frame(self.list_fr, bg=T["card"])
            row.pack(fill="x", pady=1)
            en = m.get("enabled", True)
            lbl = tk.Label(row, text=f"{icon.get(m['type'],'?')} "
                          f"{m['type'].capitalize()} {i+1}",
                          bg=T["card"], fg=T["text"] if en else T["text_dim"],
                          font=(F["ui"], F["sm"]), anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True, padx=6, pady=3)
            lbl.bind("<Button-1>", lambda e, i=i: self._show_params(i))
            eye = tk.Label(row, text="●" if en else "○", bg=T["card"],
                          fg=T["accent_fg"] if en else T["text_dim"],
                          font=(F["ui"], F["sm"]), cursor="hand2")
            eye.pack(side="right", padx=4)
            eye.bind("<Button-1>", lambda e, i=i: self._toggle(i))
            dele = tk.Label(row, text="✕", bg=T["card"], fg=T["red"],
                           font=(F["ui"], F["sm"], "bold"), cursor="hand2")
            dele.pack(side="right", padx=4)
            dele.bind("<Button-1>", lambda e, i=i: self._delete(i))
    def _toggle(self, i):
        self.app.masks[i]["enabled"] = not self.app.masks[i].get("enabled", True)
        self.app._ck = None
        self.app.req()
        self.refresh_list()
    def _delete(self, i):
        del self.app.masks[i]
        if self.pending_brush == i:
            self.pending_brush = None
        if self.sel == i:
            self.sel = None
        self.app._ck = None
        self.app.req()
        self.refresh_list()
        self._show_params(None)
    def _show_params(self, i):
        self.sel = i
        for w in self.param_fr.winfo_children():
            w.destroy()
        if i is None or i >= len(self.app.masks):
            return
        m = self.app.masks[i]
        hd = tk.Frame(self.param_fr, bg=T["glass"])
        hd.pack(fill="x")
        tk.Label(hd, text=f"Editing {m['type'].capitalize()} {i+1}",
                bg=T["glass"], fg=T["accent_fg"],
                font=(F["ui"], F["sm"], "bold")).pack(side="left")
        inv = tk.Label(hd, text="Invert: ON" if m.get("invert")
                      else "Invert: off", bg=T["glass"], fg=T["text_dim"],
                      font=(F["ui"], F["xs"]), cursor="hand2")
        inv.pack(side="right")
        def _tog(e=None, i=i, lbl=inv):
            self.app.masks[i]["invert"] = not self.app.masks[i].get(
                "invert", False)
            lbl.configure(text="Invert: ON" if self.app.masks[i]["invert"]
                          else "Invert: off")
            self.app._ck = None
            self.app.req()
        inv.bind("<Button-1>", _tog)
        self._slider(self.param_fr, "Feather", m, "feather", 0, 1, "{:.2f}")
        for k, l, lo, hi, f in self.LPARAMS:
            self._slider(self.param_fr, l, m["params"], k, lo, hi, f)
    def _slider(self, master, label, target, key, lo, hi, fmt):
        row = tk.Frame(master, bg=T["glass"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=T["glass"], fg=T["text_dim"],
                font=(F["ui"], F["xs"]), width=11, anchor="w").pack(side="left")
        vl = tk.Label(row, text=fmt.format(target.get(key, 0)),
                     bg=T["glass"], fg=T["accent_fg"],
                     font=(F["mono"], F["xs"], "bold"), width=6)
        vl.pack(side="right")
        sc = ttk.Scale(row, from_=lo, to=hi, value=target.get(key, 0),
                       command=lambda v, t=target, k=key, vl=vl, f=fmt:
                       self._on_slide(t, k, v, vl, f))
        sc.pack(side="left", fill="x", expand=True, padx=4)
    def _on_slide(self, target, key, v, lbl, fmt):
        target[key] = float(v)
        lbl.configure(text=fmt.format(float(v)))
        self.app._ck = None
        self.app.req()
    def close(self):
        self._unbind_canvas()
        try:
            self.panel.destroy()
        except Exception:
            pass
        self.app._mask_tool = None
        self.app._bc.set_en(True)
        self.app._bst.set_en(True)
        self.app._paint()
