# SPDX-License-Identifier: MIT
"""Undo/redo history."""

import copy
from .engine import ENG
from .params import DEF
from .theme import T
import time


class UndoMixin:
    """Undo/redo history."""

    def _snapshot(self):
        """Everything Undo/Redo tracks: applied preset, every editable
        control, and the crop rect / straighten angle. Zoom/pan stay
        excluded — those are viewport navigation, not an edit."""
        return {
            "ap": self.ap,
            "cr": self.cr,
            "srot": self._srot,
            "raw_geom_ops": copy.deepcopy(self._raw_geom_ops),
            "curve_pts": self.curve_pts,
            "masks": copy.deepcopy(self.masks),
            "spots": copy.deepcopy(self.spots),
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "prep": self.v_prep.get(), "pr": self.v_pr.get(),
            "ps": self.v_ps.get(), "ss": self.v_ss.get(),
            "aces": self.v_aces.get(),
            "cm_on": self.v_cm_on.get(), "cm_mode": self.v_cm_mode.get(),
            "cm_source": self.v_cm_source.get(),
            "cm_target": self.v_cm_target.get(),
            "cm_strength": self.v_cm_strength.get(),
        }

    def _restore_snapshot(self, snap):
        self._raw_geom_ops = copy.deepcopy(snap.get("raw_geom_ops", []))
        if snap.get("cr") != self.cr or snap.get("srot", 0) != self._srot:
            # Crop or straighten angle changed: rebuild src/preview from
            # the original image, then re-fit the viewport (dimensions
            # changed, so the old pan/zoom no longer make sense) and
            # refresh preset thumbnails (they were cached against the
            # old crop/straighten's preview).
            self.cr = snap["cr"]
            self._srot = snap.get("srot", 0.0)
            self._acs()
            self._rz()
            self._rl()
        self.ap = snap["ap"]
        self.curve_pts = snap.get("curve_pts")
        self.masks = copy.deepcopy(snap.get("masks", []))
        self.spots = copy.deepcopy(snap.get("spots", []))
        if self._mask_tool:
            self._mask_tool.refresh_list()
        if hasattr(self, "_curve_w"):
            self._curve_w.set_curves(
                self.curve_pts or (self.ap or {}).get(
                    "tone_curve_pts", DEF["tone_curve_pts"]))
        for k, val in snap["vars"].items():
            if k in self.vars:
                self.vars[k].set(val)
        self.v_prep.set(snap["prep"]); self.v_pr.set(snap["pr"])
        self.v_ps.set(snap["ps"]); self.v_ss.set(snap["ss"])
        self.v_aces.set(snap.get("aces", 0))
        self.v_cm_on.set(snap["cm_on"]); self.v_cm_mode.set(snap["cm_mode"])
        self.v_cm_source.set(snap["cm_source"])
        self.v_cm_target.set(snap["cm_target"])
        self.v_cm_strength.set(snap["cm_strength"])
        self._ck = None
        ENG._lc.clear()
        if self.ap:
            self._st.configure(
                text=f"● {self.ap['name']} — {self.ap.get('description','')}",
                fg=T["text_dim"])
        else:
            self._st.configure(text="Reset to neutral", fg=T["text_dim"])
        self._sync_strength_label()

    def _track_undo(self):
        """Called at the top of every req() — the single choke-point every
        committed edit already passes through (slider release, keyboard
        nudge, checkbox/combobox change, preset apply, reset, crop apply).
        Debounces rapid successive tweaks of the same control (a slider
        drag, repeated mouse-wheel ticks) into one undo step, instead of
        one step per intermediate value."""
        snap = self._snapshot()
        if self._undo_baseline is not None and snap != self._undo_baseline:
            now = time.time()
            if not self._undo or (now-self._undo_last_t) > self.UNDO_DEBOUNCE:
                self._undo.append(self._undo_baseline)
                if len(self._undo) > self.UNDO_MAX:
                    self._undo.pop(0)
                self._redo.clear()
            self._undo_last_t = now
        self._undo_baseline = snap
        self._sync_undo_buttons()

    def _sync_undo_buttons(self):
        if hasattr(self, "_bu"):
            self._bu.set_en(bool(self._undo))
        if hasattr(self, "_bre"):
            self._bre.set_en(bool(self._redo))

    def undo(self):
        if not self._undo or self.pv is None:
            return
        self._redo.append(self._undo_baseline)
        snap = self._undo.pop()
        self._restore_snapshot(snap)
        self._undo_baseline = snap
        self._sync_undo_buttons()
        self.req()

    def redo(self):
        if not self._redo or self.pv is None:
            return
        self._undo.append(self._undo_baseline)
        snap = self._redo.pop()
        self._restore_snapshot(snap)
        self._undo_baseline = snap
        self._sync_undo_buttons()
        self.req()

    def _reset_undo_history(self):
        self._undo.clear()
        self._redo.clear()
        self._undo_baseline = self._snapshot() if self.pv is not None else None
        self._sync_undo_buttons()
