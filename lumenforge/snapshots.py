# SPDX-License-Identifier: MIT
"""Named edit snapshots for quick A/B/C comparison within a session."""

import copy
import time

from .theme import T


class SnapshotMixin:
    """Save the current edit state, then cycle back through saved states."""

    def snapshot_save(self):
        if self.pv is None:
            return
        snaps = self.__dict__.setdefault("_snaps", [])
        name = f"Snapshot {len(snaps)+1} · {time.strftime('%H:%M')}"
        snaps.append((name, copy.deepcopy(self._snapshot())))
        self._snap_i = len(snaps)-1
        self._st.configure(text=f"📌 Saved {name} — use Next Snapshot to cycle",
                           fg=T["green"])

    def snapshot_next(self):
        snaps = self.__dict__.get("_snaps") or []
        if not snaps or self.pv is None:
            self._st.configure(text="No snapshots yet — use Save Snapshot",
                               fg=T["text_dim"])
            return
        self._snap_i = (self.__dict__.get("_snap_i", -1)+1) % len(snaps)
        name, snap = snaps[self._snap_i]
        self._restore_snapshot(copy.deepcopy(snap))
        self.req()
        self._st.configure(text=f"📌 {name} ({self._snap_i+1}/{len(snaps)})",
                           fg=T["accent_fg"])
