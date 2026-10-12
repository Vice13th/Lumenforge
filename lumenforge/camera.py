# SPDX-License-Identifier: MIT
"""Camera DNA matching UI."""

import numpy as np
from .engine import CAMERA_MODELS, CONFIDENCE_LOW_THRESHOLD, cd_detect_gamma_gamut, cd_match_camera, cd_meta_analyze
from .theme import F, T
import tkinter as tk
from tkinter import ttk
from .widgets import Btn, Param


class CameraMixin:
    """Camera DNA matching UI."""

    def _cm_params(self):
        """Resolve Camera Match UI state into the cd_* params consumed
        by Eng.render/staged. Auto mode resolves 'source' from the
        cached detection result; strength=0/disabled is a clean no-op."""
        if not self.v_cm_on.get():
            return {"cm_enabled": False}
        target = self.v_cm_source.get() or None  # placeholder, fixed below
        mode = self.v_cm_mode.get()
        source_id = self.v_cm_source.get() or None
        target_id = self.v_cm_target.get() or None
        if mode == "auto" and source_id is None and self.cm_detected:
            top = self.cm_detected[0]
            if top.confidence >= CONFIDENCE_LOW_THRESHOLD:
                source_id = top.profile.id
        meta_info = cd_meta_analyze(self.mt) if self.mt else {}
        gamma, _ = cd_detect_gamma_gamut(meta_info, None)
        return {
            "cm_enabled": bool(target_id),
            "cm_mode": "character",
            "cm_source": source_id,
            "cm_target": target_id,
            "cm_strength": float(np.clip(self.v_cm_strength.get(), 0, 1)),
            "cm_input_gamma": gamma,
            "cm_film_sim": None,
        }

    def _cm_auto_detect(self):
        """AUTO mode: run cd_match_camera on the current preview and
        cache the ranked results for display + as an Auto source."""
        if self.pv is None:
            return
        try:
            self.cm_detected = cd_match_camera(self.pv, self.mt)
        except Exception:
            self.cm_detected = None
        self._cm_refresh_detected_label()

    def _cm_refresh_detected_label(self):
        if not hasattr(self, "_cm_det_lbl"):
            return
        if not self.cm_detected:
            self._cm_det_lbl.configure(text="Detected: —", fg=T["text_dim"])
            return
        top = self.cm_detected[0]
        if top.confidence < CONFIDENCE_LOW_THRESHOLD:
            self._cm_det_lbl.configure(
                text="Low confidence — metadata unavailable",
                fg=T["text_dim"])
        else:
            self._cm_det_lbl.configure(
                text=f"{top.basis}: {top.profile.display_name()}  "
                     f"({top.confidence*100:.0f}%)",
                fg=T["green"] if top.basis == "Detected" else T["gold"])

    def _reset_cm_ui(self):
        """Reset Camera Match state AND the visible combobox text
        together — used by the panel's own Reset button, and by the
        full neutralize on Reset-all / opening a new image, so the
        dropdowns never show a stale camera after either."""
        self.v_cm_on.set(0)
        self.v_cm_source.set("")
        self.v_cm_target.set("")
        self.v_cm_mode.set("character")
        self.v_cm_strength.set(1.0)
        if hasattr(self, "_cm_src_cb"):
            self._cm_src_cb.set("Auto Detect")
        if hasattr(self, "_cm_tgt_cb"):
            self._cm_tgt_cb.set("")
        self.cm_detected = None
        self._cm_refresh_detected_label()

    def _bs_camera_match(self, inn):
        """CAMERA MATCH section (Camera DNA 2.0) — spec section 17.
        Integrated with the existing right-panel style; doesn't touch
        the rest of the UI layout."""
        hd = tk.Frame(inn, bg=T["card"])
        hd.pack(fill="x", pady=(10, 3))
        tk.Label(hd, text="CAMERA MATCH", font=(F["ui"], F["base"], "bold"),
                 bg=T["card"], fg=T["accent_fg"]).pack(side="left")
        tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x", side="left",
                                                    padx=T["pad"], pady=T["pad"])
        tk.Checkbutton(inn, text="Enable Camera Match",
                       variable=self.v_cm_on, bg=T["card"], fg=T["text"],
                       selectcolor=T["panel"], activebackground=T["card_hi"],
                       activeforeground=T["accent_fg"], font=T["font_sm"],
                       anchor="w",
                       command=lambda: self._scd(None), highlightthickness=2, highlightbackground=T["card"], highlightcolor=T["focus"]).pack(fill="x", pady=1)

        names_by_id = {p.id: p.display_name() for p in CAMERA_MODELS}
        id_by_name = {v: k for k, v in names_by_id.items()}
        src_names = ["Auto Detect"] + sorted(names_by_id.values())
        tgt_names = sorted(names_by_id.values())

        tk.Label(inn, text="Source Camera", bg=T["card"], fg=T["text_dim"],
                 font=T["font_sm"], anchor="w").pack(fill="x", pady=(6, 1))
        src_cb = ttk.Combobox(inn, values=src_names, state="readonly",
                              font=T["font_sm"])
        src_cb.set("Auto Detect")
        src_cb.pack(fill="x", pady=1)
        self._cm_src_cb = src_cb

        self._cm_det_lbl = tk.Label(inn, text="Detected: —",
                                    bg=T["card"], fg=T["text_dim"],
                                    font=T["font_sm"], anchor="w")
        self._cm_det_lbl.pack(fill="x", pady=(2, 6))

        def on_src(_e=None):
            v = src_cb.get()
            if v == "Auto Detect":
                self.v_cm_source.set("")
                self.v_cm_mode.set("auto")
                self._cm_auto_detect()
            else:
                self.v_cm_source.set(id_by_name.get(v, ""))
                self.v_cm_mode.set("character")
            self._scd(None)
        src_cb.bind("<<ComboboxSelected>>", on_src)

        tk.Label(inn, text="Target Camera", bg=T["card"], fg=T["text_dim"],
                 font=T["font_sm"], anchor="w").pack(fill="x", pady=(2, 1))
        tgt_cb = ttk.Combobox(inn, values=tgt_names, state="readonly",
                              font=T["font_sm"])
        tgt_cb.pack(fill="x", pady=1)
        self._cm_tgt_cb = tgt_cb

        def on_tgt(_e=None):
            self.v_cm_target.set(id_by_name.get(tgt_cb.get(), ""))
            self._scd(None)
        tgt_cb.bind("<<ComboboxSelected>>", on_tgt)

        Param(inn, "Camera Match Strength", self.v_cm_strength,
              lambda k: self._scd(k), 0, 1, "{:.0%}", 1,
              key="cm_strength",
              info="شدت اعمال تبدیل رنگی Camera Match (تطبیق رنگ بین دوربین "
                   "مبدا و مقصد یا شبیه‌سازی فیلم) را کنترل می‌کند. ۱۰۰٪ یعنی "
                   "تبدیل کامل و درصد کمتر آن را با تصویر اصلی مخلوط می‌کند."
              ).pack(fill="x", pady=2)

        bf = tk.Frame(inn, bg=T["card"])
        bf.pack(fill="x", pady=(4, 8))

        def auto_best():
            src_cb.set("Auto Detect")
            on_src()
            if self.cm_detected:
                top = self.cm_detected[0]
                if top.confidence >= CONFIDENCE_LOW_THRESHOLD:
                    tgt_cb.set(top.profile.display_name())
                    on_tgt()

        def reset_cm():
            self._reset_cm_ui()
            self._scd(None)

        Btn(bf, "Auto Best Match", auto_best, w=140, icon="◈",
            accent=T["accent2"]).pack(side="left", padx=(0, 4))
        Btn(bf, "Reset", reset_cm, w=80, icon="↺").pack(side="left")
