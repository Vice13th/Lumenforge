# SPDX-License-Identifier: MIT
"""Workspace layout and focus mode."""

from .theme import G, grid_clamp, grid_px
import tkinter as tk


class LayoutMixin:
    """Workspace layout and focus mode."""

    def _set_workspace(self, name):
        """Switch presentation workspace without changing render state."""
        self._workspace = name
        if hasattr(self, "_mode_lbl"):
            self._mode_lbl.configure(text=f"{name.upper()}  •  READY")
        if hasattr(self, "_workspace_rail"):
            for key, btn in self._workspace_rail.items():
                btn.set_active(key == name)
        self._apply_workspace_presentation(name)
        if hasattr(self, "_sc"):
            self.after_idle(lambda n=name: self._scroll_workspace_to(n))

    def _scroll_workspace_to(self, name):
        """Move the real inspector viewport to the workspace's real controls."""
        targets = {
            "Edit": ("LIGHT",),
            "Color": ("COLOUR", "HSL", "COLOR GRADE"),
            "Tone": ("TONE CURVE",),
            "Refine": ("DETAIL", "SKIN"),
            "Camera": ("CAMERA MATCH",),
            "Film": ("FILM",),
        }
        wanted = targets.get(name, ())
        if not wanted or not hasattr(self, "_inspector_inner"):
            return

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    try:
                        text = str(child.cget("text")).strip().upper()
                    except Exception:
                        text = ""
                    if text in wanted:
                        yield child
                yield from walk(child)

        try:
            self.update_idletasks()
            target = next(walk(self._inspector_inner), None)
            if target is None:
                return
            max_scroll = max(
                1,
                self._inspector_inner.winfo_height() - self._sc.winfo_height())
            target_y = max(
                0,
                target.winfo_rooty() -
                self._inspector_inner.winfo_rooty() - 8)
            fraction = target_y / max_scroll
            self._sc.yview_moveto(max(0.0, min(1.0, fraction)))
        except Exception:
            return

    def _apply_workspace_presentation(self, name):
        """Presentation-only workspace routing; render state is preserved."""
        focus_targets = {
            "Edit": "EDIT  •  BASIC",
            "Color": "COLOR  •  MIXER / GRADE",
            "Tone": "TONE  •  CURVES",
            "Refine": "REFINE  •  DETAIL / MASKS",
            "Camera": "CAMERA  •  MATCH",
            "Film": "FILM  •  STOCK / GRAIN",
        }
        if hasattr(self, "_workspace_context_label"):
            self._workspace_context_label.configure(
                text=focus_targets.get(name, "WORKSPACE"))
        return

    def _adapt_ui_density(self, _event=None):
        """Keep the desktop shell usable below the maximized 1920px layout.
        Presentation geometry adapts; render/engine state is untouched."""
        try:
            w = int(self.winfo_width())
        except Exception:
            return
        if w <= 0 or not hasattr(self, "_left_panel"):
            return

        # Side panels remain large at the production/maximized size but
        # yield width to the viewer on smaller desktop windows. Both paths
        # use the same 4 px lattice as initial construction.
        left_w = grid_clamp(min(w * .17, G["max_right"] - G["rail"]), G["min_panel"], G["max_left"])
        right_w = grid_clamp(w * .19, 268, G["max_right"])
        self._left_panel.configure(width=left_w)
        self._right_panel.configure(width=right_w)

        compact = w < 1500
        widths = {
            "_bo": grid_px(20) if compact else grid_px(24),
            "_bi": grid_px(20) if compact else grid_px(24),
            "_bsp": grid_px(22) if compact else grid_px(26),
            "_blp": grid_px(22) if compact else grid_px(26),
            "_bc": grid_px(18) if compact else grid_px(20),
            "_bm": grid_px(18) if compact else grid_px(20),
            "_br": grid_px(18) if compact else grid_px(20),
            "_bu": grid_px(16) if compact else grid_px(20),
            "_bre": grid_px(16) if compact else grid_px(20),
            "_bf": grid_px(9) if compact else grid_px(10),
            "_bs": grid_px(18) if compact else grid_px(20),
            "_ba": grid_px(10) if compact else grid_px(12),
            "_be": grid_px(28) if compact else grid_px(34),
            "_bb": grid_px(18) if compact else grid_px(20),
        }
        for name, width in widths.items():
            b = getattr(self, name, None)
            if b is not None:
                b.set_width(width)
        self._fit_fixed_containers()
        if w != getattr(self, "_tb_last_w", None) or not getattr(self, "_tb_fitted", False):
            self._tb_last_w = w
            # Debounced: a window drag emits many Configure events; fit once
            # when they settle.
            if getattr(self, "_tb_job", None):
                try:
                    self.after_cancel(self._tb_job)
                except Exception:
                    pass
            self._tb_job = self.after(40, self._toolbar_fit)

    def _fit_fixed_containers(self):
        """Fixed-pixel frames (logo block, workspace rail) never clip their
        content: they grow to the measured width when fonts or DPI scale up."""
        try:
            rail = getattr(self, "_workspace_panel", None)
            if rail is not None:
                need = max([b.need_w() for b in self._workspace_rail.values()]
                           + [self._focus_button.need_w()]) + 12
                need = min(need, G["rail"])
                for c in rail.winfo_children():
                    if c.winfo_class() == "Label":
                        need = max(need, c.winfo_reqwidth() + 12)
                # WORKSPACE must remain a single-line rail heading even on narrow windows.
                want = grid_clamp(max(132, need), 132, 144)
                if int(rail["width"]) != want:
                    rail.configure(width=want)
            logo = getattr(self, "_tb_logo", None)
            if logo is not None:
                need = sum(c.winfo_reqwidth() + 10 for c in logo.winfo_children())
                want = grid_clamp(max(168, need), 168, 240)
                if int(logo["width"]) != want:
                    logo.configure(width=want)
        except Exception:
            pass

    def _toolbar_fit(self):
        """Keep the toolbar in its normal layout and compact widths only on narrow windows."""
        self._tb_job = None
        if not hasattr(self, "_tb_top"):
            return
        try:
            if not self._tb_top.winfo_ismapped() or self._tb_top.winfo_width() <= 1:
                return
            self._tb_center.update_idletasks()
            self._tb_right.update_idletasks()
            # The top shell can retain a stale requested width during a resize.
            # Use the smaller measured width so compact mode follows the actual
            # window and commands cannot clip outside its visible right edge.
            window_width = max(1, min(
                int(self.winfo_width()), int(self._tb_top.winfo_width())))
            available = max(1, window_width -
                            self._tb_logo.winfo_reqwidth() -
                            self._tb_right.winfo_reqwidth() - 44)
            center_need = self._tb_center.winfo_reqwidth()
            compact = available < center_need
            for group in getattr(self, "_tb_groups", ()):
                for button in group:
                    # Use the widget's true icon-only layout on tight windows;
                    # never force a text label into a width it cannot occupy.
                    button.set_compact(compact)
                    button.pack_configure(padx=1 if compact else 3)
            # The left brand and right export controls remain pinned; the
            # center command clusters keep natural width and grow no fake gaps.
            self._tb_fitted = True
        except (tk.TclError, AttributeError):
            self._tb_fitted = False

    def _enter_focus_workspace(self, name):
        """Enter a real image-first focus workspace."""
        if self._focus_mode:
            return
        if not hasattr(self, "_center_panel"):
            return
        self._focus_return_workspace = self._workspace
        self._focus_mode = True
        self._workspace = name
        self._focus_hidden_panels = True

        for panel in (
            getattr(self, "_workspace_panel", None),
            getattr(self, "_left_panel", None),
            getattr(self, "_right_panel", None),
        ):
            if panel is not None:
                panel.pack_forget()

        self._center_panel.pack_forget()
        self._center_panel.pack(
            side="left", fill="both", expand=True, padx=9, pady=9)
        self._paint_focus_shell(True, name)
        self.update_idletasks()

    def _exit_focus_workspace(self):
        if not self._focus_mode:
            return
        self._focus_mode = False
        self._workspace = self._focus_return_workspace
        self._focus_hidden_panels = False

        self._workspace_panel.pack(
            side="left", fill="y", padx=(9, 4), pady=9,
            before=self._center_panel)
        self._left_panel.pack(
            side="left", fill="y", padx=(9, 5), pady=9,
            before=self._center_panel)
        self._center_panel.configure(width=1)
        self._center_panel.pack(
            side="left", fill="both", expand=True, padx=4, pady=9)
        self._right_panel.pack(
            side="right", fill="y", padx=(5, 9), pady=9)
        self._paint_focus_shell(False, self._workspace)
        self._set_workspace(self._workspace)
        self.update_idletasks()

    def _paint_focus_shell(self, enabled, name):
        """Render focus context inside the dedicated top shell row."""
        if not hasattr(self, "_focus_bar"):
            return
        if enabled:
            self._focus_title.configure(text=f"{name.upper()}  /  FOCUS")
            self._focus_hint.configure(
                text="Esc  Exit Focus   •   Space  Before/After")
            self._focus_bar.pack(fill="x", padx=12, pady=(2, 4))
            self._workspace_context_label.configure(
                text={"Tone": "Curves", "Color": "Color Grade",
                      "Refine": "Masks"}.get(name, "Workspace"))
        else:
            self._focus_bar.pack_forget()
