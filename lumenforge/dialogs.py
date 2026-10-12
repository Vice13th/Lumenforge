# SPDX-License-Identifier: MIT
"""Dialogs and the splash screen."""

import math
import numpy as np
import tkinter as tk
from tkinter import messagebox
from .config import APP_NAME, VERSION
from .theme import F, T, _mix, _lumenforge_icon_image, REDUCE_MOTION
from .widgets import gradient_bar, Btn, _auto_icon, rnd


class Dlg(tk.Toplevel):
    def __init__(self, master, title, lines, btns, w=360, acc=None):
        super().__init__(master)
        acc = acc or T["accent"]
        self.configure(bg=T["bg"])
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.transient(master)
        H = 130+36*len(btns)+20*len(lines)
        cv = tk.Canvas(self, width=w, height=H, bg=T["bg"],
                       highlightthickness=1,
                       highlightbackground=T["stroke_hi"])
        cv.pack()
        rnd(cv, 2, 2, w-4, H-4, 10, fill=T["glass"], outline=acc, width=2)
        cv.create_text(w//2, 30, text=title, fill=T["text"],
                       font=(F["ui"], 13, "bold"))
        y = 58
        for l in lines:
            cv.create_text(w//2, y, text=l, fill=T["text_dim"],
                           font=T["font_sm"])
            y += 20
        by = H-36*len(btns)-10
        self._btns = []
        try:
            self.title(title)
        except Exception:
            pass
        for t, c, fl in btns:
            ic, lbl = _auto_icon(t)
            b = Btn(self, lbl, lambda c=c: self._r(c), w=170, h=30,
                    kind="solid" if fl else "ghost", accent=acc, bg=T["bg"],
                    icon=ic)
            b.place(x=(w-int(b["width"]))//2, y=by)
            self._btns.append(b)
            by += 36
        # Keyboard: Tab/Shift+Tab cycle the buttons (they are the only
        # focusable widgets in this window), Space/Enter activate the
        # focused one, Enter elsewhere runs the first (primary) button and
        # Escape cancels.
        self._default = next((b for b, (_t, _c, fl) in zip(self._btns, btns)
                              if fl), None)
        self.bind("<Return>", lambda e: (self._default._c(e), "break")[1]
                  if self._default is not None else None)
        self.bind("<Escape>", lambda e: (self._d(), "break")[1])
        self.bind("<Button-1>", lambda e: self._d())
        cv.bind("<Button-1>", lambda e: self._d())
        self.update_idletasks()
        mx = master.winfo_rootx()+master.winfo_width()//2
        my = master.winfo_rooty()+master.winfo_height()//2
        self.geometry(f"+{mx-w//2}+{my-H//2}")
        try:
            self.focus_force()
            if self._btns:
                (self._default or self._btns[0]).focus_set()
        except Exception:
            pass
    def _r(self, c):
        if c is None:
            self._d()
            return
        try:
            if c() is not False:
                self._d()
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)
    def _d(self):
        try:
            self.destroy()
        except Exception:
            pass




class Splash(tk.Toplevel):
    """Borderless glass-card splash shown while the main window builds
    its (fairly heavy) widget tree. Progress is real, not simulated:
    set_status() is called at each actual construction checkpoint in
    App.__init__, so the bar's position always reflects genuine boot
    progress rather than a fixed-duration animation."""
    W, H = 500, 276
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg=T["bg"])
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw-self.W)//2, (sh-self.H)//2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self._cv = tk.Canvas(self, width=self.W, height=self.H,
                             bg=T["bg"], highlightthickness=0)
        self._cv.pack(fill="both", expand=True)
        # Use a transient toplevel with the canonical app mark when supported.
        try:
            from PIL import ImageTk
            self._window_icon = ImageTk.PhotoImage(_lumenforge_icon_image(64))
            self.iconphoto(True, self._window_icon)
        except Exception:
            self._window_icon = None
        # Reuse one PhotoImage throughout the animation. Rebuilding this
        # image inside every 60ms draw caused needless image churn and flicker.
        self._brand_icon = self._window_icon
        if self._brand_icon is None:
            try:
                from PIL import ImageTk
                self._brand_icon = ImageTk.PhotoImage(_lumenforge_icon_image(64))
            except Exception:
                self._brand_icon = None
        self._frac = 0.0
        self._status = "Starting…"
        self._pulse = 0.0
        self._draw()
        self._anim()
    def _draw(self):
        cv = self._cv
        cv.delete("all")
        m = 10
        rnd(cv, m, m, self.W-m, self.H-m, T["radius_lg"], fill=T["card"],
           outline=T["stroke_hi"])
        glow = _mix(T["accent"], T["card"], .55+.25*math.sin(self._pulse))
        rnd(cv, m, m, self.W-m, self.H-m, T["radius_lg"], fill="",
           outline=glow, width=2)
        cy = 78
        if self._brand_icon is not None:
            cv.create_image(self.W//2, cy, image=self._brand_icon)
        cv.create_text(self.W//2, cy+40, text="LUMENFORGE",
                        fill=T["text"], font=(F["ui"], 17, "bold"))
        cv.create_text(self.W//2, cy+62, text="IMAGE LAB  •  LOOK APPLIED",
                        fill=T["text_dim"], font=(F["ui"], F["sm"], "bold"))
        bw, bh = self.W-2*40, 6
        bx, by = 40, cy+94
        rnd(cv, bx, by, bx+bw, by+bh, bh//2, fill=T["stroke"], outline="")
        fw = max(bh, int(bw*np.clip(self._frac, 0, 1)))
        if fw > 1:
            gradient_bar(cv, bx, by, bx+fw, by+bh)
        pct = int(round(100*np.clip(self._frac, 0, 1)))
        cv.create_text(bx, by+22, text=self._status,
                       fill=T["text_dim"], font=(F["ui"], F["base"]), anchor="w")
        cv.create_text(bx+bw, by+22, text=f"{pct:02d}%",
                       fill=T["text_dim"], font=(F["mono"], F["sm"], "bold"),
                       anchor="e")
        cv.create_text(self.W-24, self.H-18, text=f"v{VERSION}",
                       fill=T["text_dim"], font=(F["ui"], F["xs"]),
                       anchor="e")
    def _anim(self):
        if REDUCE_MOTION:
            self._draw()
            self._anim_job = None
            return
        self._pulse += .25
        self._draw()
        self._anim_job = self.after(60, self._anim)
    def set_status(self, text, frac):
        self._status = text
        self._frac = frac
        self._draw()
        self.update_idletasks()
        self.update()
    def close(self):
        try:
            if self._anim_job is not None:
                self.after_cancel(self._anim_job)
        except Exception:
            pass
        self.destroy()
