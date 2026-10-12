# SPDX-License-Identifier: MIT
"""Toasts and render HUD."""

from .theme import F, MOTION, REDUCE_MOTION, T, _mix
import time
import tkinter as tk
from .widgets import rnd


class FeedbackMixin:
    """Toasts and render HUD."""

    def _toast(self, message, kind="info", duration=None):
        """Compact, transient UI feedback; intentionally presentation-only."""
        try:
            if self._toast_job:
                self.after_cancel(self._toast_job)
        except Exception:
            pass
        if self._toast_id is None:
            self._toast_id = tk.Canvas(self, width=420, height=48,
                                       bg=T["bg"], highlightthickness=0)
        c = self._toast_id
        c.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-44)
        c.delete("all")
        color = {"success": T["green"], "warning": T["gold"],
                 "error": T["red"]}.get(kind, T["accent2"])
        rnd(c, 0, 0, 418, 46, T["radius_lg"], fill=T["card"],
            outline=T["stroke"])
        rnd(c, 3, 3, 7, 43, 2, fill=color, outline="")
        # Severity is stated in text, not by the stripe color alone.
        glyph = {"success": "✓ ", "warning": "⚠ ", "error": "✕ "}.get(kind, "")
        c.create_text(18, 23, text=glyph + message, fill=T["text"],
                      font=(F["ui"], F["base"], "bold"), anchor="w", width=382)
        if kind in ("warning", "error"):
            # Problems stay readable after the toast fades (4.1.3).
            try:
                self._st.configure(text=glyph + message, fg=color)
            except Exception:
                pass
            duration = duration or MOTION["toast"] * 2
        self._toast_job = self.after(duration or MOTION["toast"], self._toast_hide)

    def _toast_hide(self):
        if self._toast_id is not None:
            try:
                self._toast_id.place_forget()
            except Exception:
                pass

    def _render_hud_show(self, label="Rendering"):
        """Professional indeterminate render HUD; never invents percentages.

        Export/batch operations use the real `_epr()` progress path, while
        interactive preview work stays indeterminate by design.
        """
        if self._render_hud is not None:
            return
        cv = tk.Canvas(self.cnv, width=340, height=54, bg=T["bg"],
                       highlightthickness=0, takefocus=0)
        cv.place(relx=.5, rely=.035, anchor="n")
        rnd(cv, 1, 1, 338, 53, T["radius_sm"], fill=T["glass"],
            outline=T["stroke_hi"])
        cv.create_oval(12, 14, 18, 20, fill=T["processing"], outline="")
        cv.create_text(27, 15, text=label.upper(), fill=T["text"],
                       font=(F["ui"], F["sm"], "bold"), anchor="w", tags="label")
        cv.create_text(27, 31, text="PROCESSING — LIVE FEEDBACK", fill=T["text_dim"],
                       font=(F["mono"], F["xs"]), anchor="w", tags="sub")
        rnd(cv, 160, 16, 318, 22, 3, fill=T["stroke"], outline="")
        cv.create_text(160, 39, text="Preview updates will appear as the render completes",
                       fill=T["text_dim"], font=(F["ui"], F["xs"]), anchor="w", tags="hint")
        self._render_hud = cv
        self._render_scan_job = 0
        self._render_hud_scan()

    def _render_hud_scan(self):
        if self._render_hud is None:
            return
        c = self._render_hud
        c.delete("scan")
        if REDUCE_MOTION:
            rnd(c, 160, 16, 318, 22, 3,
                fill=_mix(T["accent"], T["white"], .12), outline="", tags="scan")
            return
        phase = int((time.time() * 120) % 176)
        x = 160 + phase
        seg = 34
        if x <= 318-seg:
            rnd(c, x, 16, x+seg, 22, 3,
                fill=_mix(T["accent"], T["white"], .12), outline="", tags="scan")
            c.create_line(x+5, 17, x+seg-5, 17,
                          fill=_mix(T["accent"], T["white"], .24), tags="scan")
        else:
            x2 = x-(318-160)
            rnd(c, 160, 16, 160+x2, 22, 3,
                fill=_mix(T["accent"], T["white"], .12), outline="", tags="scan")
            rnd(c, x, 16, 318, 22, 3,
                fill=_mix(T["accent"], T["white"], .12), outline="", tags="scan")
        self._render_scan_job = self.after(MOTION["scan"], self._render_hud_scan)

    def _render_hud_hide(self):
        if self._render_scan_job:
            try:
                self.after_cancel(self._render_scan_job)
            except Exception:
                pass
        self._render_scan_job = None
        if self._render_hud is not None:
            try:
                self._render_hud.destroy()
            except Exception:
                pass
        self._render_hud = None
