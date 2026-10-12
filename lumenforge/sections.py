# SPDX-License-Identifier: MIT
"""Collapsible inspector sections with modified markers and per-section reset."""

from .params import DEF
from .theme import F, T

DEFAULT_OPEN = ("LIGHT", "WHITE BALANCE", "COLOUR")


class SectionsMixin:
    """Accordion behaviour for the inspector's parameter groups."""

    def _sec_state(self):
        return self.__dict__.setdefault("_sec", {"open": {}, "w": {}})

    def _sec_make_header(self, parent, g, keys, py):
        """Build one section header; returns (header_frame, body_frame)."""
        import tkinter as tk
        st = self._sec_state()
        opened = st["open"].setdefault(g, g in DEFAULT_OPEN)
        hd = tk.Frame(parent, bg=T["card"], cursor="hand2")
        hd.pack(fill="x", pady=(10 if py == 2 else 7, 3))
        chev = tk.Label(hd, text="▾" if opened else "▸", bg=T["card"], fg=T["accent_fg"],
                        font=(F["ui"], F["base"]), width=2)
        chev.pack(side="left")
        ttl = tk.Label(hd, text=g, bg=T["card"], fg=T["accent_fg"],
                       font=(F["ui"], F["base"], "bold"))
        ttl.pack(side="left")
        dot = tk.Label(hd, text="●", bg=T["card"], fg=T["gold"], font=(F["ui"], F["xs"]))
        rst = tk.Label(hd, text="↺", bg=T["card"], fg=T["text_dim"], cursor="hand2",
                       font=(F["ui"], F["base"]), padx=4)
        rst.pack(side="right")
        tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x", side="left", expand=True,
                                                    padx=T["pad"], pady=T["pad"])
        body = tk.Frame(parent, bg=T["card"])
        if opened:
            body.pack(fill="x")
        for w in (hd, chev, ttl):
            w.bind("<Button-1>", lambda e, g=g, b=body, h=hd, c=chev: self._sec_toggle(g, b, h, c))
        rst.bind("<Button-1>", lambda e, g=g: self._sec_reset(g))
        rst.bind("<Enter>", lambda e, r=rst: r.configure(fg=T["accent_fg"]))
        rst.bind("<Leave>", lambda e, r=rst: r.configure(fg=T["text_dim"]))
        st["w"][g] = (dot, ttl, keys)
        st.setdefault("ctl", {})[g] = (body, hd, chev)
        for w in (hd, chev, ttl):
            w.bind("<Alt-Button-1>", lambda e, g=g: (self._sec_solo(g), "break")[1])
        for k in keys:
            try:
                self.vars[k].trace_add("write", lambda *a: self._sec_refresh())
            except Exception:
                pass
        self._sec_refresh()
        return hd, body

    def _sec_toggle(self, g, body, hd, chev):
        st = self._sec_state()
        st["open"][g] = not st["open"].get(g, True)
        if st["open"][g]:
            body.pack(fill="x", after=hd)
            chev.configure(text="▾")
        else:
            body.pack_forget()
            chev.configure(text="▸")

    def _sec_solo(self, g):
        """Alt-click: open this section and collapse every other one."""
        st = self._sec_state()
        for g2, (body, hd, chev) in st.get("ctl", {}).items():
            want = g2 == g
            if st["open"].get(g2, True) != want:
                self._sec_toggle(g2, body, hd, chev)

    def _sec_modified(self, keys):
        for k in keys:
            v = self.vars.get(k)
            try:
                if v is not None and abs(float(v.get())-float(DEF.get(k, 0))) > 1e-6:
                    return True
            except Exception:
                pass
        return False

    def _sec_refresh(self):
        for g, (dot, ttl, keys) in self._sec_state()["w"].items():
            try:
                if self._sec_modified(keys):
                    if not dot.winfo_ismapped():
                        dot.pack(side="left", padx=(4, 0), after=ttl)
                else:
                    dot.pack_forget()
            except Exception:
                pass

    def _sec_reset(self, g):
        keys = self._sec_state()["w"][g][2]
        for k in keys:
            if k in self.vars:
                self.vars[k].set(DEF.get(k, 0))
        if keys:
            self._scd(keys[0])
        self._sec_refresh()
