# SPDX-License-Identifier: MIT
"""Preset browsing and application."""

from tkinter import simpledialog
from .config import APP_NAME
from .engine import ENG, PRES, staged, thumb, to_pil
from .params import DEF
from PIL import ImageTk
from .theme import F, T
import tkinter as tk
from tkinter import messagebox
from .widgets import PRow, _autowrap


def _is_modern(p):
    """Modern tab: the Modern / Unique film family and the genre Modern Looks."""
    return "Modern" in str(p.get("family")) or p.get("process") == "Modern Look"


class PresetMixin:
    """Preset browsing and application."""

    def _preset_search_changed(self):
        self._preset_query = self._preset_q.get().strip().lower() if hasattr(self, "_preset_q") else ""
        self._rl()

    def _clear_preset_search(self):
        if hasattr(self, "_preset_q"):
            self._preset_q.set("")
        self._preset_query = ""
        self._rl()

    def _toggle_favorite(self, p):
        name = p.get("name", "")
        if not name:
            return
        if name in self._favorites:
            self._favorites.remove(name)
            self._toast("Removed from favorites", "info")
        else:
            self._favorites.add(name)
            self._toast("Saved to favorites", "success")
        self._rl()

    def _rl(self):
        for w in self._in.winfo_children():
            w.destroy()
        m = self._flt.get() if hasattr(self, "_flt") else "all"
        q = getattr(self, "_preset_query", "").lower().strip()
        fav_only = bool(self._fav_only.get()) if hasattr(self, "_fav_only") else False
        ps = list(PRES)
        if m == "phones":
            ps = [p for p in ps if "iPhone" in str(p.get("family"))
                  or "Samsung" in str(p.get("family"))]
        elif m == "cinematic_cameras":
            ps = [p for p in ps if str(p.get("family")) == "Cinema Cameras"]
        elif m == "vintage":
            ps = [p for p in ps if "Vintage" in str(p.get("family"))]
        elif m == "modern":
            ps = [p for p in ps if _is_modern(p)]
        elif m == "film":
            ps = [p for p in ps if "Mobile" not in str(p.get("family"))
                  and "Vintage" not in str(p.get("family"))
                  and not _is_modern(p)
                  and str(p.get("family")) != "Cinema Cameras"]
        if q:
            ps = [p for p in ps
                  if q in str(p.get("name", "")).lower()
                  or q in str(p.get("family", "")).lower()
                  or q in str(p.get("process", "")).lower()]
        if fav_only:
            ps = [p for p in ps if p.get("name") in self._favorites]
        self._hdr.configure(text=f"PRESET LIBRARY — {len(ps)}")
        for i, p in enumerate(ps):
            PRow(self._in, p, self._th(p), self.apl,
                 active=(self.ap is not None and self.ap.get("name") == p["name"]),
                 favorite=(p.get("name") in self._favorites),
                 on_favorite=self._toggle_favorite
                 ).grid(row=i, column=0, padx=2, pady=2, sticky="ew")
        self._in.grid_columnconfigure(0, weight=1)
        self._in.update_idletasks()
        self._pc.configure(scrollregion=self._pc.bbox("all"))
        self._pc.yview_moveto(0)
        self._rl_imp()

    def _rl_imp(self):
        if not hasattr(self, "_ini"):
            return
        for w in self._ini.winfo_children():
            w.destroy()
        q = getattr(self, "_preset_query", "").lower().strip()
        fav_only = bool(self._fav_only.get()) if hasattr(self, "_fav_only") else False
        ps = list(self.imp)
        if q:
            ps = [p for p in ps
                  if q in str(p.get("name", "")).lower()
                  or q in str(p.get("family", "")).lower()
                  or q in str(p.get("process", "")).lower()]
        if fav_only:
            ps = [p for p in ps if p.get("name") in self._favorites]
        self._hdr_imp.configure(text=f"IMPORTED — {len(ps)}")
        for i, p in enumerate(ps):
            PRow(self._ini, p, self._th(p), self.apl,
                 on_delete=self._del_imp, on_rename=self._ren_imp,
                 active=(self.ap is not None and self.ap.get("name") == p["name"]),
                 favorite=(p.get("name") in self._favorites),
                 on_favorite=self._toggle_favorite
                 ).grid(row=i, column=0, padx=2, pady=2, sticky="ew")
        self._ini.grid_columnconfigure(0, weight=1)
        self._ini.update_idletasks()
        self._pci.configure(scrollregion=self._pci.bbox("all"))
        self._pci.yview_moveto(0)
        if not ps:
            _autowrap(tk.Label(self._ini, text="No matching imported looks.\n"
                     "Import a preset or LUT to grow this library.",
                     bg=T["panel"], fg=T["text_dim"],
                     font=(F["ui"], F["base"]), wraplength=210, anchor="w",
                     justify="left")).grid(row=0, column=0, padx=6, pady=10,
                                          sticky="ew")

    def _ren_imp(self, p):
        if p not in self.imp:
            return
        new = simpledialog.askstring(APP_NAME, "Rename preset:",
                                     initialvalue=p["name"], parent=self)
        if new is None:
            return
        new = new.strip()
        if not new or new == p["name"]:
            return
        existing = {x["name"] for x in self.imp if x is not p}
        if new in existing:
            base, n = new, 2
            while f"{base} ({n})" in existing:
                n += 1
            new = f"{base} ({n})"
        old_name = p["name"]
        p["name"] = new
        self._tc.pop(old_name, None)
        self._svi()
        self._rl_imp()

    def _del_imp(self, p):
        if p not in self.imp:
            return
        if not messagebox.askyesno(APP_NAME, f"Remove imported \"{p['name']}\"?"):
            return
        if self.ap is p:
            self.rs()
        self.imp.remove(p)
        self._tc.pop(p["name"], None)
        self._svi()
        self._rl()

    def apl(self, p):
        # Single source of truth for "current preset" state: self.ap is
        # replaced wholesale (never merged), so any per-preset extra like
        # an imported LUT's lut3d_path/lut3d_strength cannot leak from the
        # previous preset into this one. Anything that lives OUTSIDE self.ap
        # (the Preset Strength slider) must be reset explicitly here —
        # that was the actual source of state bleeding between presets.
        self.ap = p
        ENG._lc.clear()  # full preset swap: don't trust per-layer hash shortcuts
        self.curve_pts = None  # preset's own curve (if any) takes over
        if hasattr(self, "_curve_w"):
            self._curve_w.set_curves(p.get("tone_curve_pts",
                                           DEF["tone_curve_pts"]))
        for k, v in self.vars.items():
            if k in p:
                try:
                    v.set(float(p[k]))
                except (TypeError, ValueError):
                    pass
        # Imported LUTs default to 50% amount (a strong LUT applied at
        # full strength is often overpowering as a starting point);
        # ordinary presets still default to 100% strength.
        self.v_ss.set(0.5 if p.get("lut3d_path") else 1.0)
        self._st.configure(text=f"● {p['name']} — {p.get('description','')}",
                           fg=T["text_dim"])
        self._mode_lbl.configure(text="IMAGE LAB  •  LOOK APPLIED") if hasattr(self, "_mode_lbl") else None
        self._toast(f"Applied  •  {p['name']}", "success")
        self._ck = None
        self._sync_strength_label()
        self._mark_active()
        self.req()

    def _mark_active(self):
        """Update which preset card shows the accent 'active' ring/dot
        without rebuilding the whole list (avoids losing scroll
        position on every apply)."""
        name = self.ap.get("name") if self.ap else None
        for parent in (getattr(self, "_in", None), getattr(self, "_ini", None)):
            if parent is None:
                continue
            for w in parent.winfo_children():
                if isinstance(w, PRow):
                    is_a = name is not None and w._p.get("name") == name
                    if is_a != w._active:
                        w._active = is_a
                        w._draw()

    def _th(self, p):
        k = p["name"]
        if k in self._tc:
            return self._tc[k]
        if self.pv is None:
            return None
        try:
            s = thumb(self.pv, 56)
            o = staged(s, {**DEF, **p})
            ph = ImageTk.PhotoImage(to_pil(o))
        except Exception:
            return None
        self._tc[k] = ph
        return ph

    def _sync_strength_label(self):
        """The Preset Strength slider IS the LUT Amount control when an
        imported .cube LUT is the active preset (same underlying
        lut3d_strength) — relabel it in place so the UI names it for
        what it's actually doing instead of a generic term."""
        if not hasattr(self, "_pss"):
            return
        is_lut = bool(self.ap and self.ap.get("lut3d_path"))
        self._pss._lb.configure(text="LUT Amount" if is_lut
                                else "Preset Strength")
