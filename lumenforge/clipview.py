# SPDX-License-Identifier: MIT
"""Clipping warning overlay (J)."""

from .engine import clipping_overlay
from .theme import T


class ClipViewMixin:
    """Toggle a red/blue overlay for blown highlights and crushed shadows."""

    _clip_view = False

    def clip_toggle(self):
        self._clip_view = not self._clip_view
        self._disp_key = None
        self._disp_cache = None
        if self._lo is not None:
            self._paint()
        self._st.configure(
            text="Clipping overlay ON — red: highlights, blue: shadows"
                 if self._clip_view else "Clipping overlay off",
            fg=T["accent_fg"] if self._clip_view else T["text_dim"])

    def _clip_array(self, a):
        return clipping_overlay(a) if self._clip_view else a
