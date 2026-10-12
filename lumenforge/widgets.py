# SPDX-License-Identifier: MIT
"""Reusable Tk widgets and styling."""

import numpy as np
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from .config import APP_NAME
from .theme import F, ICON, T, _mix, ink_on, legible


def styles(root):
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except Exception:
        pass
    s.configure(".", background=T["bg"], foreground=T["text"],
                font=T["font"], borderwidth=0)
    s.configure("TScale", background=T["card"], troughcolor=T["panel"],
                lightcolor=T["accent"], darkcolor=T["accent"],
                bordercolor=T["stroke"], slidersize=(14, 22))
    s.map("TScale", background=[("active", T["card"])],
          lightcolor=[("active", T["accent2"])],
          darkcolor=[("active", T["accent2"])])
    s.configure("TEntry", fieldbackground=T["panel"], foreground=T["text"],
                insertcolor=T["text"], bordercolor=T["stroke"],
                lightcolor=T["stroke"], darkcolor=T["stroke"],
                padding=(8, 5))
    s.map("TEntry", fieldbackground=[("focus", T["card_hi"])],
          bordercolor=[("focus", T["accent"])])
    s.configure("TCombobox", fieldbackground=T["panel"],
                foreground=T["text"], arrowcolor=T["text_dim"],
                bordercolor=T["stroke"], lightcolor=T["stroke"],
                darkcolor=T["stroke"], padding=(7, 4))
    s.map("TCombobox", fieldbackground=[("readonly", T["panel"])],
          foreground=[("readonly", T["text"])],
          bordercolor=[("focus", T["accent"])])
    s.configure("Vertical.TScrollbar", background=T["panel"],
                troughcolor=T["bg"], bordercolor=T["bg"],
                arrowcolor=T["text_dim"], width=9)
    s.map("Vertical.TScrollbar", background=[("active", T["stroke_hi"])])


def rnd(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
           x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def gradient_bar(cv, x0, y0, x1, y1, c0=None, c1=None, step=2):
    """Horizontal brand gradient (spec: #8D6CFF -> #4F46E5) with rounded ends."""
    c0, c1 = c0 or T["grad_a"], c1 or T["grad_b"]
    h = y1-y0
    rnd(cv, x0, y0, x1, y1, h//2, fill=c0, outline="")
    span = max(1, x1-x0-h)
    for x in range(int(x0+h//2), int(x1-h//2), step):
        cv.create_line(x, y0+1, x, y1-1, fill=_mix(c0, c1, (x-x0-h//2)/span), width=step)
    return None


def _glass_edge(panel, tint):
    """A hairline gradient strip along a panel's top edge — center
    brighter (tinted toward the given accent), fading to the panel's
    own stroke color at both ends. Gives the card a faint 'glass edge'
    highlight instead of a flat top border."""
    strip = tk.Canvas(panel, height=2, bg=T["card"], highlightthickness=0)
    strip.pack(fill="x", side="top", pady=(0, 6))
    def _draw(e=None):
        strip.delete("all")
        w = strip.winfo_width() or 1
        mid = w//2
        for x in range(0, w, 2):
            t = 1-abs(x-mid)/max(1, mid)
            strip.create_line(x, 0, x, 2,
                              fill=_mix(T["stroke"], tint, t*.6))
    strip.bind("<Configure>", _draw)
    return strip


class Tip:
    """Lightweight shared tooltip: one borderless Toplevel, reused for
    every widget that registers via Tip.bind(widget, text). Avoids any
    new dependency — pure tkinter. Wraps longer text (e.g. full slider
    explanations) instead of stretching off-screen."""
    _tw = None
    @staticmethod
    def bind(widget, text):
        widget.bind("<Enter>", lambda e: Tip._show(widget, text), add="+")
        widget.bind("<Leave>", lambda e: Tip._hide(), add="+")
        widget.bind("<Button-1>", lambda e: Tip._hide(), add="+")
    @staticmethod
    def _show(widget, text):
        Tip._hide()
        try:
            x = widget.winfo_rootx()+widget.winfo_width()//2
            y = widget.winfo_rooty()+widget.winfo_height()+6
        except Exception:
            return
        tw = tk.Toplevel(widget)
        tw.overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        wrap = 260 if len(text) > 40 else 0
        tk.Label(tw, text=text, bg=T["accent"], fg=T["on_accent"],
                 font=(F["ui"], F["sm"], "bold" if wrap == 0 else "normal"),
                 padx=7, pady=4, justify="left",
                 wraplength=wrap if wrap else 10000
                 ).pack()
        tw.update_idletasks()
        tw_w = tw.winfo_width()
        sw = tw.winfo_screenwidth()
        x = min(max(0, x-tw_w//2), max(0, sw-tw_w))
        tw.geometry(f"+{x}+{y}")
        Tip._tw = tw
    @staticmethod
    def _hide():
        if Tip._tw is not None:
            try:
                Tip._tw.destroy()
            except Exception:
                pass
            Tip._tw = None


def sep(master, h=24):
    """Thin vertical separator used to group toolbar buttons visually.
    Rendered as a tiny 2-stop vertical gradient (bright center, fading
    to the panel color at each end) for a subtle brushed-metal look."""
    c = tk.Canvas(master, width=2, height=h, bg=T["panel"],
                 highlightthickness=0)
    mid = h//2
    for y in range(h):
        t = 1-abs(y-mid)/max(1,mid)
        c.create_line(0, y, 2, y, fill=_mix(T["panel"], T["stroke_hi"], t))
    return c


_ICON_BY_LABEL = {
    "Open": "open", "Import": "import", "Save Proj": "save",
    "Load Proj": "load", "Crop": "crop", "Straighten": "straighten",
    "Masks": "mask", "Reset": "reset", "Undo": "undo", "Redo": "redo",
    "Split": "split", "Batch": "batch", "EXPORT": "export",
    "FOCUS": "focus", "EXIT FOCUS": "exit_focus",
}


class Btn(tk.Canvas):
    """Canvas-drawn button.

    Presentation only: command wiring is unchanged. It is keyboard
    operable (Tab, Space, Enter), draws a visible focus ring, sizes itself
    from measured text so labels are never clipped, and can collapse to an
    icon-only form for narrow windows (its tooltip then carries the name).
    """
    def __init__(self, master, text, cmd=None, w=110, h=T["ctrl_h"],
                 kind="ghost", accent=None, fs=9, bg=None, tip=None,
                 icon=None):
        bg = bg or T["panel"]
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, cursor="hand2", takefocus=1)
        self._t, self._cmd, self._k = text, cmd, kind
        self._icon = icon
        self._a = accent or T["accent"]
        self._en = True
        self._active = False
        self._focus = False
        self._compact = False
        self._pref_w = w
        self._tip = tip
        self._bg = bg
        self._f = ("Segoe UI", fs, "bold")
        self._fi = ("Segoe UI Symbol", 14)
        self._fobj = None
        self.bind("<Enter>", lambda e: self._p(True))
        self.bind("<Leave>", lambda e: self._p(False))
        self.bind("<Button-1>", self._c)
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        for seq in ("<space>", "<Return>", "<KP_Enter>"):
            self.bind(seq, self._key)
        self.bind("<Escape>", lambda e: Tip._hide(), add="+")
        if tip:
            Tip.bind(self, tip)
        self._apply_w()
        self._p(False)

    # -- geometry ---------------------------------------------------
    def need_w(self):
        """Minimum width that fits the icon chip, label and padding."""
        h = int(self["height"])
        if self._fobj is None:
            try:
                self._fobj = tkfont.Font(root=self, font=self._f)
            except Exception:
                return 0
        tw = self._fobj.measure(self._t) if self._t else 0
        if self._icon:
            cs = h - 12
            return (6 + cs + 7 + tw + 8) if self._t else h + 6
        return tw + 24
    def _apply_w(self):
        h = int(self["height"])
        if self._compact and self._icon:
            w = h + 6
        else:
            w = max(self._pref_w, self.need_w())
        self.configure(width=w)
    def _refresh(self):
        # Redraws either state; disabled buttons skip _p(), so a resize of a
        # disabled button must go through set_en to avoid a stale drawing.
        self.set_en(self._en)
    def set_width(self, w):
        self._pref_w = int(w)
        old = int(self["width"])
        self._apply_w()
        if int(self["width"]) != old:
            self._refresh()
    def set_compact(self, on):
        on = bool(on) and bool(self._icon)
        if on != self._compact:
            self._compact = on
            self._apply_w()
            self._refresh()

    # -- keyboard / focus -------------------------------------------
    def _focus_in(self, _=None):
        self._focus = True
        self._p(False)
        if self._tip:
            Tip._show(self, self._tip)
    def _focus_out(self, _=None):
        self._focus = False
        self._p(False)
        Tip._hide()
    def _key(self, e):
        self._c(e)
        return "break"

    # -- drawing ----------------------------------------------------
    def _glyph(self):
        key = _ICON_BY_LABEL.get(self._t)
        return ICON[key] if key else self._icon
    def _p(self, hov):
        if not self._en:
            return
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        # Active (toggled-on) state takes visual priority over hover so a
        # pressed toggle (e.g. Split compare) stays legible as "on" even
        # while the mouse sits elsewhere in the group.
        if self._active:
            # Active controls use a darkened accent surface with light ink.
            # This keeps the state legible without making every active control
            # look like a primary CTA.
            f = _mix(self._a, T["bg"], .28)
            t = ink_on(f, prefer=T["text"])
            ln = self._a
        elif self._k == "solid":
            # Solid buttons are reserved for primary actions (Open/Export).
            # They carry more contrast but remain compact.
            f = _mix(self._a, T["white"], .18) if hov else self._a
            t = ink_on(f, prefer=T["text"])
            ln = _mix(self._a, T["white"], .10)
        else:
            f = T["card_hi"] if hov else self._bg
            # A button is an instrument, not a tile: default state is quiet;
            # hover lifts the surface by one visual step; focus is the only
            # strong ring.
            t = T["text"] if hov else legible(self._a, f)
            ln = _mix(T["stroke_ui"], self._a, .30) if hov else T["stroke_ui"]
        rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill=f, outline=ln)
        if self._icon:
            # Unified monochrome icon treatment. Render every toolbar icon
            # from the same optical box and text metrics.
            cs = h-12
            cx0 = (w-cs)//2 if (not self._t or self._compact) else 6
            cy0 = (h-cs)//2
            chip_fill = (_mix(f, T["black"], .22) if self._k == "solid"
                        else _mix(f, self._a, .22))
            rnd(self, cx0, cy0, cx0+cs, cy0+cs, T["radius_sm"],
               fill=chip_fill, outline="")
            icon_c = t if self._k == "solid" or self._active else legible(self._a, chip_fill)
            self.create_text(cx0+cs//2, cy0+cs//2+1, text=self._glyph(),
                             fill=icon_c, font=self._fi)
            if self._t and not self._compact:
                self.create_text(cx0+cs+7, h//2, text=self._t, fill=t,
                                 font=self._f, anchor="w")
        else:
            self.create_text(w//2, h//2, text=self._t, fill=t, font=self._f)
        if self._focus:
            rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill="",
                outline=T["focus"], width=2)
    def _c(self, _):
        if self._en and self._cmd:
            try:
                self._cmd()
            except Exception as ex:
                messagebox.showerror(APP_NAME, str(ex))
    def set_active(self, on):
        self._active = bool(on)
        self._p(False)
    def set_en(self, en):
        self._en = bool(en)
        self["cursor"] = "hand2" if en else "arrow"
        self.configure(takefocus=1 if en else 0)
        if not en:
            self.delete("all")
            w, h = int(self["width"]), int(self["height"])
            rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill=T["panel"],
                outline=T["stroke"])
            if self._icon:
                cs = h-12
                cx0 = (w-cs)//2 if (not self._t or self._compact) else 6
                cy0 = (h-cs)//2
                rnd(self, cx0, cy0, cx0+cs, cy0+cs, T["radius_sm"],
                   fill=T["card"], outline="")
                self.create_text(cx0+cs//2, cy0+cs//2+1, text=self._glyph(),
                                 fill=T["text_dim"], font=self._fi)
                if self._t and not self._compact:
                    self.create_text(cx0+cs+7, h//2, text=self._t,
                                     fill=T["text_dim"], font=self._f,
                                     anchor="w")
            else:
                self.create_text(w//2, h//2, text=self._t,
                                 fill=T["text_dim"], font=self._f)
        else:
            self._p(False)


class Param(tk.Frame):
    def __init__(self, master, label, var, cb, lo=-100, hi=100,
                 fmt="{:+.0f}", default=None, key=None, info=None):
        super().__init__(master, bg=T["card"])
        self._v, self._cb, self._f = var, cb, fmt
        self._lo, self._hi = float(lo), float(hi)
        self._d = float(default) if default is not None else float(var.get())
        self._key = key
        self._lf = 0
        self._e = None
        tp = tk.Frame(self, bg=T["card"])
        tp.pack(fill="x")
        lb = tk.Label(tp, text=label, bg=T["card"], fg=T["text_dim"],
                      font=T["font_sm"], anchor="w", cursor="hand2")
        lb.pack(side="left")
        self._lb = lb
        lb.bind("<Double-Button-1>", lambda e: self._st(self._d))
        if info:
            ic = tk.Label(tp, text="ⓘ", bg=T["card"], fg=T["text_dim"],
                          font=(F["ui"], F["sm"]), padx=3)
            try:
                ic.configure(cursor="question_arrow")
            except Exception:
                try:
                    ic.configure(cursor="hand2")
                except Exception:
                    pass
            ic.pack(side="left")
            Tip.bind(ic, info)
            ic.bind("<Enter>", lambda e: ic.configure(fg=T["accent_fg"]),
                    add="+")
            ic.bind("<Leave>", lambda e: ic.configure(fg=T["text_dim"]),
                    add="+")
        self._ch = tk.Label(tp, text=fmt.format(float(var.get())),
                            bg=T["glass"], fg=T["accent_fg"],
                            font=(F["mono"], F["base"], "bold"), padx=6,
                            cursor="xterm")
        self._ch.pack(side="right")
        self._ch.bind("<Button-1>", self._ty)
        # The focus ring lives on a thin wrapper because ttk's clam Scale
        # draws no focus indicator of its own (WCAG 2.4.7).
        # A 2px padded frame whose background switches to the focus color:
        # Tk's own highlight ring is not reliably painted when focus sits on
        # a child widget, so the ring is drawn as plain background fill.
        self._sf = tk.Frame(self, bg=T["card"], padx=2, pady=2)
        self._sf.pack(fill="x", pady=(0, 1))
        self._s = ttk.Scale(self._sf, from_=lo, to=hi, variable=var,
                            command=self._oc)
        self._s.pack(fill="x")
        self._info = info
        self._s.bind("<FocusIn>", self._focus_in)
        self._s.bind("<FocusOut>", self._focus_out)
        self._s.bind("<Escape>", lambda e: Tip._hide(), add="+")
        self._s.bind("<F2>", lambda e: (self._ty(), "break")[1])
        self._s.bind("<Return>", lambda e: (self._ty(), "break")[1])
        for k in ("<Delete>", "<BackSpace>"):
            self._s.bind(k, lambda e: (self._st(self._d), "break")[1])
        self._s.bind("<ButtonRelease-1>", lambda e: self._fire())
        for k, m in (("<Up>",1),("<Down>",-1),("<Prior>",10),("<Next>",-10)):
            self._s.bind(k, lambda e, m=m: self._ng(m))
        # Mouse-wheel support: hovering the slider scrolls its value
        # (matches the Up/Down step). Bound directly on the widget and
        # returns "break" so it never falls through to a scrollable
        # parent's panel-scroll binding or the app's global Ctrl+Wheel
        # zoom handler — each widget gets exactly one behavior.
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._s.bind(seq, self._on_wheel)
            self._sf.bind(seq, self._on_wheel)
            self.bind(seq, self._on_wheel)
    def _focus_in(self, _=None):
        self._sf.configure(bg=T["focus"])
        hint = "F2 edit value  •  Del reset"
        Tip._show(self._s, (self._info + "\n" + hint) if self._info else hint)
    def _focus_out(self, _=None):
        self._sf.configure(bg=T["card"])
        Tip._hide()
    def _on_wheel(self, e):
        if getattr(e, "num", None) == 4:
            d = 1
        elif getattr(e, "num", None) == 5:
            d = -1
        else:
            d = 1 if e.delta > 0 else -1
        self._ng(d)
        return "break"
    def _ty(self, _=None):
        if self._e:
            return
        self._e = tk.Entry(self._ch.master, bg=T["glass"], fg=T["accent_fg"],
                           font=(F["mono"], F["base"], "bold"), width=7,
                           insertbackground=T["accent"], relief="flat",
                           highlightthickness=1,
                           highlightbackground=T["accent"])
        self._e.insert(0, self._f.format(float(self._v.get())))
        self._e.pack(side="right")
        self._e.focus_set()
        self._e.select_range(0, "end")
        self._e.bind("<Return>", lambda e: (self._ok(), "break")[1])
        self._e.bind("<Escape>", lambda e: (self._cn(True), "break")[1])
        self._e.bind("<FocusOut>", lambda e: self._ok(True))
        self._ch.pack_forget()
    def _cn(self, refocus=False):
        if self._e:
            self._e.destroy()
            self._e = None
            self._ch.pack(side="right")
            Tip._hide()
            if refocus:
                self._s.focus_set()
    def _ok(self, lost_focus=False):
        if not self._e:
            return
        try:
            v = float(self._e.get().strip().replace("−","-")
                      .replace(",","."))
        except ValueError:
            if lost_focus:
                self._cn()
                return
            # Keep the box open and say what is wrong in words (3.3.1),
            # not only with a color change.
            self._e.configure(highlightbackground=T["red"], highlightcolor=T["red"])
            Tip._show(self._e, "Enter a number from %g to %g  (Esc to cancel)"
                      % (self._lo, self._hi))
            return
        self._st(v)
        self._cn(not lost_focus)
    def _st(self, v):
        v = float(np.clip(v, self._lo, self._hi))
        self._v.set(v)
        self._ch.configure(text=self._f.format(v))
        self._fire()
    def _ng(self, m):
        self._st(float(self._v.get())+(self._hi-self._lo)/100*m)
        return "break"
    def _oc(self, _=None):
        try:
            self._ch.configure(text=self._f.format(float(self._v.get())))
        except Exception:
            pass
        n = time.time()
        if n-self._lf > .2:
            self._lf = n
            self._fire()
    def _fire(self):
        if self._cb:
            self._cb(self._key)






class PRow(tk.Canvas):
    """Modern glass/metallic preset card: rounded canvas card with a
    brushed-metal gradient, an accent glow ring on hover, and a
    persistent accent ring + dot marker when this preset is the one
    currently applied — replacing the old flat bordered tk.Frame row."""
    def __init__(self, master, p, th, oc, on_delete=None, on_rename=None,
                 active=False, favorite=False, on_favorite=None):
        super().__init__(master, height=60, bg=T["card"],
                         highlightthickness=0, cursor="hand2")
        self._p, self._oc, self._img, self._del = p, oc, th, on_delete
        self._ren = on_rename
        self._active = active
        self._favorite = bool(favorite)
        self._on_favorite = on_favorite
        self._hov = False
        self._del_box = None
        self._ren_box = None
        self._fav_box = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._sh(True))
        self.bind("<Leave>", lambda e: self._sh(False))
        self.bind("<Button-1>", self._click)
        self.bind("<Double-Button-1>", self._dclick)
        if on_delete is not None:
            self.bind("<Button-3>", lambda e: on_delete(self._p))
        self._draw()
    def _sh(self, h):
        self._hov = h
        self._draw()
    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = int(self["height"])
        hov = self._hov
        f = T["card_hi"] if (hov or self._active) else T["card"]
        ln = T["accent"] if (hov or self._active) else T["stroke"]
        if hov or self._active:
            rnd(self, 0, 0, w, h, T["radius_lg"], fill="",
               outline=T["accent"] if hov else T["accent2"])
        rnd(self, 1, 1, w-2, h-2, T["radius"], fill=f, outline=ln)
        # Brushed-metal top gradient band, same language as the toolbar
        # buttons, so preset cards read as part of the same UI system.
        top_c = _mix(f, T["white"], .10)
        band = max(2, (h-2)//2)
        for i in range(band):
            t2 = 1-(i/band)
            self.create_line(2, 2+i, w-2, 2+i, fill=_mix(f, top_c, t2))
        x = 10
        if self._img is not None:
            try:
                iw = self._img.width()
            except Exception:
                iw = 0
            self.create_image(x, h//2, image=self._img, anchor="w")
            x += iw+10
        if self._active:
            self.create_text(x, h//2, text="●", fill=T["accent"],
                             font=(F["ui"], F["sm"]))
            x += 12
        tx_w = max(40, w-x-(22 if self._del is not None else 10)
                  -(18 if self._ren is not None else 0)
                  -(22 if self._on_favorite is not None else 0))
        self.create_text(x, h//2-10, text=self._p["name"][:44],
                         fill=T["text"], font=(F["ui"], F["base"], "bold"),
                         anchor="w", width=tx_w)
        sub = self._p.get("process") or self._p.get("family", "")
        self.create_text(x, h//2+10, text=sub, fill=T["text_dim"],
                         font=(F["ui"], F["xs"]), anchor="w", width=tx_w)
        nx = w-6
        if self._del is not None:
            dx0, dy0, dx1, dy1 = nx-18, h//2-10, nx, h//2+10
            self._del_box = (dx0, dy0, dx1, dy1)
            self.create_text((dx0+dx1)//2, (dy0+dy1)//2, text="✕",
                             fill=T["red"] if hov else T["text_dim"],
                             font=(F["ui"], F["base"], "bold"))
            nx = dx0-2
        if self._ren is not None:
            rx0, ry0, rx1, ry1 = nx-18, h//2-10, nx, h//2+10
            self._ren_box = (rx0, ry0, rx1, ry1)
            self.create_text((rx0+rx1)//2, (ry0+ry1)//2, text="✎",
                             fill=T["accent2"] if hov else T["text_dim"],
                             font=(F["ui"], F["base"], "bold"))
            nx = rx0-2
        if self._on_favorite is not None:
            fx0, fy0, fx1, fy1 = nx-20, h//2-10, nx, h//2+10
            self._fav_box = (fx0, fy0, fx1, fy1)
            self.create_text((fx0+fx1)//2, (fy0+fy1)//2,
                             text="★" if self._favorite else "☆",
                             fill=T["accent"] if self._favorite else T["text_dim"],
                             font=("Segoe UI Symbol", 10, "bold"))
    def _dclick(self, e):
        if self._ren is not None:
            self._ren(self._p)
    def _click(self, e):
        if self._del_box:
            x0, y0, x1, y1 = self._del_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._del(self._p)
                return
        if self._ren_box:
            x0, y0, x1, y1 = self._ren_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._ren(self._p)
                return
        if self._fav_box and self._on_favorite:
            x0, y0, x1, y1 = self._fav_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._on_favorite(self._p)
                return
        self._oc(self._p)


def _autowrap(label, pad=6):
    """Make a Label's wraplength follow its allotted width (no clipping)."""
    def _w(e):
        wl = max(60, e.width - pad)
        if int(label.cget("wraplength") or 0) != wl:
            label.configure(wraplength=wl)
    label.bind("<Configure>", _w)
    return label


def _auto_icon(text):
    """Best-effort coherent glyph for a dialog button from its label,
    so every confirm/cancel popup across the app (which pass plain,
    varied strings) still gets the same chip-icon language as the
    toolbar instead of staying bare text or ad-hoc emoji."""
    t = text.strip()
    for ch in ("📂", "⚪", "⚡", "✂", "⬇", "👁", "⊘"):
        t = t.replace(ch, "").strip()
    low = t.lower()
    if "open" in low: return "▣", t
    if "close" in low: return "✕", t
    if "cancel" in low: return "✕", t
    if "remove" in low or "delete" in low: return "⌫", t
    if "reset" in low: return "↺", t
    if "save" in low: return "◈", t
    if "export" in low: return "⇧", t
    if "overwrite" in low or "replace" in low: return "⇄", t
    if low == "ok" or "yes" in low or "confirm" in low: return "✓", t
    if "no" in low: return "✕", t
    return None, t


















