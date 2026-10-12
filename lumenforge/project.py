# SPDX-License-Identifier: MIT
"""Project and image file I/O."""

from tkinter import filedialog
from .config import APP_NAME
import json
from .engine import PRES, ROTATE_270, _raw_postprocess, load_src
import os
from .theme import T
from tkinter import messagebox


class ProjectMixin:
    """Project and image file I/O."""

    def _project_dict(self):
        """Everything needed to reconstruct the current edit state — the
        .lfproj sidecar format. The source image itself is NOT embedded,
        only its path (same approach as Lightroom XMP sidecars) — keeps
        project files tiny and re-openable if the image is still there."""
        return {
            "format": "lfproj", "version": 1,
            "source_path": getattr(self, "_src_path", None),
            "cr": list(self.cr) if self.cr else None,
            "srot": self._srot,
            "curve_pts": self.curve_pts or (self.ap or {}).get("tone_curve_pts"),
            "masks": self.masks,
            "spots": self.spots,
            "ap_name": self.ap.get("name") if self.ap else None,
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "prep": self.v_prep.get(), "pr": self.v_pr.get(),
            "ps": self.v_ps.get(), "ss": self.v_ss.get(),
            "aces": self.v_aces.get(),
            "cm_on": self.v_cm_on.get(), "cm_mode": self.v_cm_mode.get(),
            "cm_source": self.v_cm_source.get(),
            "cm_target": self.v_cm_target.get(),
            "cm_strength": self.v_cm_strength.get(),
        }

    def save_project(self):
        if self._o is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        p = filedialog.asksaveasfilename(
            title="Save Project", defaultextension=".lfproj",
            filetypes=[("LumenForge Project", "*.lfproj")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self._project_dict(), f, indent=2)
            self._st.configure(text=f"✓ Project saved: {os.path.basename(p)}",
                               fg=T["text_dim"])
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Save failed:\n{ex}")

    def load_project(self):
        p = filedialog.askopenfilename(
            title="Load Project",
            filetypes=[("LumenForge Project", "*.lfproj"), ("All", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Load failed:\n{ex}")
            return
        src = d.get("source_path")
        if not src or not os.path.exists(src):
            messagebox.showinfo(
                APP_NAME, "The original image wasn't found at its saved "
                "location — pick it manually.")
            src = filedialog.askopenfilename(
                title="Locate the original image for this project")
            if not src:
                return
        if not self._open_path(src):
            return
        self.cr = tuple(d["cr"]) if d.get("cr") else None
        self._srot = float(d.get("srot", 0.0))
        tcp = d.get("curve_pts")
        if tcp:
            self.curve_pts = {ch: [tuple(pt) for pt in pts]
                              for ch, pts in tcp.items()}
            if hasattr(self, "_curve_w"):
                self._curve_w.set_curves(self.curve_pts)
        self.masks = d.get("masks", [])
        self.spots = d.get("spots", [])
        ap_name = d.get("ap_name")
        if ap_name:
            match = next((x for x in PRES if x["name"] == ap_name), None)
            if match:
                self.ap = match
        for k, val in d.get("vars", {}).items():
            if k in self.vars:
                self.vars[k].set(val)
        self.v_prep.set(d.get("prep", 1))
        self.v_pr.set(d.get("pr", 0))
        self.v_ps.set(d.get("ps", 1))
        self.v_ss.set(d.get("ss", 1.0))
        self.v_aces.set(d.get("aces", 0))
        self.v_cm_on.set(d.get("cm_on", 0))
        self.v_cm_mode.set(d.get("cm_mode", "character"))
        self.v_cm_source.set(d.get("cm_source", ""))
        self.v_cm_target.set(d.get("cm_target", ""))
        self.v_cm_strength.set(d.get("cm_strength", 1.0))
        self._acs()
        self._rz()
        self._rl()
        self._mark_active()
        self._ck = None
        self._reset_undo_history()
        self.req()
        self._st.configure(text=f"✓ Project loaded: {os.path.basename(p)}",
                           fg=T["text_dim"])

    def _open_path(self, p):
        """Shared image-loading logic behind both 'Open' and 'Load
        Project' — loads the file, resets all per-image state, and
        refreshes every panel. Returns True on success."""
        try:
            im, mt = load_src(p)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not open:\n{ex}")
            self._toast("Could not open image", "error")
            return False
        self._src_path = p
        self._o = im
        self._raw_geom_ops = []
        self.mt = mt
        self.cr = None
        self._srot = 0.0
        self.masks = []
        self.spots = []
        if getattr(self, "_mask_tool", None):
            self._mask_tool.close()
        if getattr(self, "_history_panel", None):
            self._history_panel.close()
        self.cm_detected = None
        self._neutralize()
        self._rz()
        self._acs()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._bsp.set_en(True)
        if hasattr(self, "_bh"):
            self._bh.set_en(True)
        self._be.set_en(True)
        self._bb.set_en(True)
        self._st.configure(text=f"● {os.path.basename(p)}  "
                           f"{im.width}x{im.height}px"
                           + ("  [RAW]" if mt.get("raw") else ""),
                           fg=T["text_dim"])
        self._rl()
        if self.v_cm_mode.get() == "auto":
            self._cm_auto_detect()
        self._ck = None
        self._reset_undo_history()
        self.req()
        return True

    def oi(self):
        p = filedialog.askopenfilename(
            title="Open image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp "
                                "*.arw *.cr2 *.cr3 *.nef *.nrw *.raf "
                                "*.orf *.rw2 *.dng *.pef *.srw *.3fr "
                                "*.raw"),
                       ("All", "*.*")])
        if not p:
            return
        self._open_path(p)

    def _ensure_raw_full_source(self):
        if not self.mt.get("raw") or not self.mt.get("raw_proxy"):
            return
        path = self.mt.get("path")
        if not path:
            return
        im = _raw_postprocess(path, preview=False)
        for op, arg in self._raw_geom_ops:
            if op == "rot90":
                im = im.transpose(ROTATE_270)
            elif op == "flip":
                im = im.transpose(arg)
        self._o = im
        self.mt["raw_proxy"] = False
