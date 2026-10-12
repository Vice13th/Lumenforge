# SPDX-License-Identifier: MIT
"""Application window and entry point."""

import json
import numpy as np
import os
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk
from .config import ASSET_DIR, APP_NAME, IMPORTED_FILE, PREVIEW_MAX, VERSION
from .deps import HAVE_OCIO
from .engine import ENG, IMPS, PRES, RenderGeneration, _rotate_straight
from .params import DEF, GORD, GRP, PARAM_INFO, SPEC
from .theme import apply_fonts, F, G, ICON, T, _lumenforge_icon, grid_clamp
from .dialogs import Splash
from .editors import CurveEditor, HSLMixer
from .tools import MaskTool
from .widgets import Btn, Param, Tip, _autowrap, _glass_edge, sep, styles
from .autotone import AutoToneMixin
from .camera import CameraMixin
from .clipview import ClipViewMixin
from .heal import HealMixin
from .huepick import HuePickMixin
from .export import ExportMixin
from .feedback import FeedbackMixin
from .layout import LayoutMixin
from .presets import PresetMixin
from .project import ProjectMixin
from .selftest import self_tests
from .compare import CompareMixin
from .sections import SectionsMixin
from .winchrome import apply_dark_titlebar
from .shortcuts import ShortcutsMixin
from .snapshots import SnapshotMixin
from .undo import UndoMixin
from .crop import CropMixin
from .rendering import RenderMixin
from .view import ViewMixin
from .whitebal import WhiteBalanceMixin


class App(CompareMixin, ShortcutsMixin, SectionsMixin, ViewMixin, CropMixin, WhiteBalanceMixin, RenderMixin, HuePickMixin, SnapshotMixin, ClipViewMixin, HealMixin, AutoToneMixin, UndoMixin, ExportMixin, ProjectMixin, LayoutMixin, CameraMixin, FeedbackMixin, PresetMixin, tk.Tk):

    def __init__(self):
        super().__init__()
        apply_fonts(self)
        self._app_icon = None
        # Set the ICO first; apply iconphoto last because Windows may let
        # iconbitmap replace an image configured earlier in startup.
        self._app_icon_path = os.path.join(ASSET_DIR, "assets", "lumenforge.ico")
        if os.path.isfile(self._app_icon_path):
            try:
                self.iconbitmap(default=self._app_icon_path)
            except Exception:
                pass
        try:
            self._app_icon = _lumenforge_icon()
            self.iconphoto(False, self._app_icon)
            self.iconphoto(True, self._app_icon)
            if os.path.isfile(self._app_icon_path):
                try:
                    self.iconbitmap(default=self._app_icon_path)
                except Exception:
                    # iconphoto is the portable fallback when native ICO is unavailable.
                    pass
        except Exception:
            self._app_icon = None
        self.title(f"{APP_NAME} — v{VERSION}")
        self.configure(bg=T["bg"])
        self.withdraw()
        self._splash_started_at = time.monotonic()
        self._boot_splash = Splash(self)
        self._boot_splash.set_status("Starting engine…", .04)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1560, sw-60)}x{min(950, sh-90)}+30+30")
        # Do not enforce a minimum wider than the available desktop work area:
        # on smaller/lower-DPI screens the responsive toolbar and side panels
        # must be allowed to compact instead of forcing controls off-screen.
        self.minsize(min(1120, max(800, sw-40)),
                     min(680, max(560, sh-80)))
        styles(self)

        self._boot_splash.set_status("Preparing workspace…", .12)
        self._o = None
        self.src = None
        self.cr = None
        self._srot = 0.0   # straighten angle (degrees), applied in _acs()
        self._raw_geom_ops = []
        self._ov_str = None
        self.curve_pts = None  # None = use preset/DEF curve; else user override
        self.masks = []  # local adjustment masks (radial/linear/brush)
        self.spots = []  # spot-heal clones
        self._heal_picking = False
        self._mask_tool = None
        self.pv = None
        self.mt = {}
        self.imp = []
        self.ap = None
        self.vars = {}
        # UI-only state: presentation preferences never enter the render pipeline.
        self._workspace = "Edit"
        self._workspace_rail = {}
        self._focus_mode = False
        self._focus_return_workspace = "Edit"
        self._favorites = set()
        self._preset_query = ""
        self._palette = None
        self._toast_id = None
        self._toast_job = None
        self._render_hud = None
        self._render_scan_job = None
        self._tc = {}
        self._rj = None
        self._ph = None
        self._oph = None
        self._off = (0, 0)
        self._ov = None
        self._z = 1
        self._pan = (0, 0)
        self._pd = None
        self._mod = False
        self._rb = False
        self._rp = False
        self._sp = False
        self._sx = .5
        self._sph = None
        self._lo = None
        self._bt = 0
        self._bd = 0
        self._ck = None
        self._wb_picking = False
        self._wb_pick_btn = None
        self._fit_wh = (1, 1)   # stable "fit-to-canvas" reference size —
                                 # decoupled from self.pv's actual pixel
                                 # resolution, which now grows with zoom
        self._pv_max = PREVIEW_MAX
        self._zj = None
        self._render_generation = RenderGeneration()
        self._render_generation_id = 0
        self._disp_key = None
        self._disp_cache = None
        self._undo, self._redo = [], []
        self._undo_baseline = None
        self._undo_last_t = 0.0
        self.UNDO_MAX = 60
        self.UNDO_DEBOUNCE = .6

        self._boot_splash.set_status("Building parameters…", .18)
        self._mkv()
        self._mku()
        self.bind("<Configure>", self._adapt_ui_density, add="+")
        self.bind("<Map>", self._on_app_map, add="+")
        self._adapt_ui_density()
        # Initial Configure events can occur while withdrawn; fit after mapping.
        self.after_idle(self._schedule_toolbar_fit)
        self._ldi()
        self.bind_all("<MouseWheel>", self._wh)
        self.bind_all("<KeyPress-j>", lambda e: self.clip_toggle() if not isinstance(e.widget, (tk.Entry, tk.Text)) else None)
        self.bind_all("<Escape>", lambda e: (self._exit_focus_workspace(), "break")[1])
        self.bind_all("<KeyPress-space>", lambda e: (
            self._so(True) if self._focus_mode and self.pv is not None
            and not self._typing() else None))
        self.bind_all("<KeyRelease-space>", lambda e: (
            self._so(False) if self._focus_mode and self.pv is not None
            and not self._typing() else None))
        for _n, _ws in enumerate(("Edit", "Color", "Tone", "Refine",
                                  "Camera", "Film"), 1):
            self.bind_all("<Alt-Key-%d>" % _n,
                          lambda e, w=_ws: (self._set_workspace(w), "break")[1])
        self.bind_all("<Control-k>", lambda e: (self.command_palette(), "break")[1])
        self.bind_all("<Control-o>", lambda e: (self.oi(), "break")[1])
        self.bind_all("<Control-e>", lambda e: (self.ex(), "break")[1])
        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-Z>", lambda e: self.undo())
        self.bind_all("<Control-y>", lambda e: self.redo())
        self.bind_all("<Control-Shift-Z>", lambda e: self.redo())
        self.bind_all("<Control-Shift-z>", lambda e: self.redo())
        self._install_shortcuts()

        self._boot_splash.set_status("Ready", 1.0)
        self.after(150, self._finish_boot)

    def _typing(self):
        """True while a text-entry widget owns the keyboard, so single-key
        shortcuts (WCAG 2.1.4) must not fire."""
        try:
            w = self.focus_get()
        except Exception:
            return False
        return w is not None and w.winfo_class() in (
            "Entry", "TEntry", "TCombobox", "Text", "Listbox", "Spinbox")

    def _finish_boot(self):
        """Launch maximized after the branded splash has been visible briefly."""
        # Fast machines used to close the splash almost immediately, making
        # its logo/progress state effectively invisible. Keep it visible for a
        # short, non-blocking minimum interval; do not sleep or freeze Tk.
        elapsed = time.monotonic() - getattr(self, "_splash_started_at", time.monotonic())
        remaining_ms = int(max(0.0, 1.40 - elapsed) * 1000)
        if remaining_ms:
            self.after(remaining_ms, self._finish_boot)
            return
        self._boot_splash.close()
        apply_dark_titlebar(self)
        # Reapply after native window creation: Windows can replace the icon
        # while the root is withdrawn or when native chrome is refreshed.
        if self._app_icon is not None:
            try:
                self.iconphoto(False, self._app_icon)
                self.iconphoto(True, self._app_icon)
            except Exception:
                pass
        self.bind("<Map>", lambda e: apply_dark_titlebar(self) if e.widget is self else None, add="+")
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                self.geometry(f"{sw}x{sh}+0+0")
        self.deiconify()
        self.lift()
        self.focus_force()
        # Window manager has assigned final geometry; fit after mapping instead
        # of relying on Configure events emitted while the root was withdrawn.
        self.after(220, self._toolbar_fit)

    def _mkv(self):
        for k, _, lo, hi, _ in SPEC:
            self.vars[k] = tk.DoubleVar(value=DEF.get(k, 0))
        self.v_prep = tk.IntVar(value=1)
        self.v_pr = tk.IntVar(value=0)
        self.v_ps = tk.DoubleVar(value=1)
        self.v_aces = tk.IntVar(value=0)
        self.v_ss = tk.DoubleVar(value=1)
        # Camera Match (Camera DNA 2.0) — separate system, own vars
        self.v_cm_on = tk.IntVar(value=0)
        self.v_cm_mode = tk.StringVar(value="character")
        self.v_cm_source = tk.StringVar(value="")   # "" = Auto Detect
        self.v_cm_target = tk.StringVar(value="")
        self.v_cm_strength = tk.DoubleVar(value=1.0)
        self.cm_detected = None   # last CameraMatchResult list from Auto





























    def _on_app_map(self, event=None):
        if event is None or event.widget is self:
            self.after_idle(self._schedule_toolbar_fit)

    def _schedule_toolbar_fit(self):
        if not hasattr(self, "_tb_top"):
            return
        try:
            if self._tb_job:
                self.after_cancel(self._tb_job)
        except Exception:
            pass
        try:
            self._tb_job = self.after(80, self._toolbar_fit)
        except Exception:
            self._tb_job = None

    def _mku(self):
        """Build the window: toolbar, preset library, canvas, inspector."""
        bd = self._mku_toolbar()
        left = self._mku_presets(bd)
        self._mku_canvas(bd)
        self._mku_inspector(bd, left)
        self._mku_finish()

    def _mku_toolbar(self):
        # One deterministic top-shell owns both the command toolbar and
        # transient focus context. Nothing in this shell is allowed to
        # float over another root-level panel.
        self._top_shell = tk.Frame(self, bg=T["panel"])
        self._top_shell.pack(fill="x", side="top")
        # 36px buttons plus vertical padding need at least 66px; 56px clipped them.
        top = tk.Frame(self._top_shell, bg=T["panel"], height=72)
        top.pack(fill="x")
        top.pack_propagate(False)
        top.configure(highlightthickness=1, highlightbackground=T["stroke"])

        # LEFT: identity + current workspace state
        logo = tk.Frame(top, bg=T["panel"], width=168)
        logo.pack(side="left", fill="y", padx=(16, 10))
        logo.pack_propagate(False)
        # Version-1 brand mark from the public GitHub asset, kept as a
        # raster-backed Tk image so the exact silhouette/colors are reused.
        self._brand_mark_img = None
        brand_path = os.path.join(ASSET_DIR, "assets", "lumenforge_logo.png")
        if not os.path.isfile(brand_path):
            brand_path = os.path.join(ASSET_DIR, "lumenforge_logo.png")
        if os.path.isfile(brand_path):
            try:
                im = Image.open(brand_path).convert("RGBA")
                im.thumbnail((30, 30), Image.Resampling.LANCZOS)
                self._brand_mark_img = ImageTk.PhotoImage(im)
            except Exception:
                self._brand_mark_img = None
        if self._brand_mark_img is not None:
            tk.Label(logo, image=self._brand_mark_img, bg=T["panel"]).pack(
                side="left", padx=(2, 7), pady=16)
        else:
            tk.Label(logo, text="L", font=(F["ui"], 17, "bold"),
                     bg=T["panel"], fg=T["accent_fg"]).pack(side="left", padx=(0, 7))
        idf = tk.Frame(logo, bg=T["panel"])
        idf.pack(side="left", pady=8)
        tk.Label(idf, text="LUMENFORGE", font=(F["ui"], F["lg"], "bold"),
                 bg=T["panel"], fg=T["text"]).pack(anchor="w")
        self._mode_lbl = tk.Label(idf, text="IMAGE LAB  •  READY",
                                  font=(F["ui"], F["sm"], "bold"),
                                  bg=T["panel"], fg=T["text_dim"])
        self._mode_lbl.pack(anchor="w", pady=(1, 0))

        # Dedicated status/control row below the command toolbar.
        # It is a child of the root layout, never a floating child of the
        # window, so it cannot overlap the toolbar or steal its hit area.
        self._focus_bar = tk.Frame(self._top_shell, bg=T["panel"],
                                   highlightthickness=1,
                                   highlightbackground=T["stroke_hi"],
                                   padx=10, pady=3)
        self._focus_title = tk.Label(self._focus_bar, text="", bg=T["panel"],
                                     fg=T["accent_fg"], font=(F["ui"], F["sm"], "bold"))
        self._focus_title.pack(side="left")
        self._focus_hint = tk.Label(self._focus_bar, text="", bg=T["panel"],
                                    fg=T["text_dim"], font=(F["mono"], F["sm"]))
        self._focus_hint.pack(side="left", padx=(14, 0))

        # Explicit mouse exit affordance for Focus. It intentionally calls
        # the exact same function used by the global Escape binding so the
        # two exit paths cannot drift apart.
        self._focus_exit = Btn(
            self._focus_bar, "EXIT FOCUS", self._exit_focus_workspace,
            w=112, h=30, fs=9, kind="solid", accent=T["accent2"],
            icon=ICON["exit_focus"], tip="Exit Focus (Esc)")
        self._focus_exit.pack(side="right", padx=(18, 0))

        self._focus_bar.pack_forget()

        # RIGHT: reserve Export/Batch space first. Tk pack allocates expansion
        # in packing order; packing the expanding center first lets it intrude
        # beneath the right group on narrower windows.
        rf = tk.Frame(top, bg=T["panel"])
        rf.pack(side="right", fill="y", padx=(8, 16))

        # CENTER: the remaining width belongs to the command row only.
        bf = tk.Frame(top, bg=T["panel"])
        bf.pack(side="left", fill="x", expand=True)
        self._bo = Btn(bf, "Open", self.oi, w=94, kind="solid",
                       icon=ICON["open"], tip="Open an image (Ctrl+O)")
        self._bo.pack(side="left", padx=3, pady=10)
        self._bi = Btn(bf, "Import", self.ip, w=92,
                       accent=T["accent2"], icon=ICON["import"],
                       tip="Import preset(s) or .cube LUTs")
        self._bi.pack(side="left", padx=3, pady=10)
        self._bsp = Btn(bf, "Save Proj", self.save_project, w=100,
                        accent=T["accent2"], icon=ICON["save"],
                        tip="Save a .lfproj sidecar (all current edits, "
                        "re-openable non-destructively)")
        self._bsp.pack(side="left", padx=3, pady=10)
        self._blp = Btn(bf, "Load Proj", self.load_project, w=100,
                        accent=T["accent2"], icon=ICON["load"],
                        tip="Load a .lfproj project file")
        self._blp.pack(side="left", padx=3, pady=10)
        sep(bf).pack(side="left", padx=8, pady=12)

        self._bc = Btn(bf, "Crop", self.tc, w=76, icon=ICON["crop"],
                       tip="Crop, Straighten, Rotate, Flip")
        self._bc.pack(side="left", padx=3, pady=10)
        self._bst = Btn(bf, "Straighten", self.ts_tool, w=102, icon=ICON["straighten"],
                        tip="Straighten / fix horizon tilt")
        # Kept alive for existing enable/disable integration, but deliberately
        # hidden from the primary toolbar. Crop owns the tool entry point.
        self._bm = Btn(bf, "Masks", self.mask_tool, w=82, icon=ICON["mask"],
                       tip="Local adjustment masks")
        self._bm.pack(side="left", padx=3, pady=10)
        self._br = Btn(bf, "Reset", self.rs, w=82, icon=ICON["reset"],
                       tip="Reset all edits")
        self._br.pack(side="left", padx=3, pady=10)
        self._bu = Btn(bf, "Undo", self.undo, w=78, icon=ICON["undo"],
                       tip="Undo (Ctrl+Z)")
        self._bu.pack(side="left", padx=3, pady=10)
        self._bu.set_en(False)
        self._bre = Btn(bf, "Redo", self.redo, w=78, icon=ICON["redo"],
                        tip="Redo (Ctrl+Shift+Z)")
        self._bre.pack(side="left", padx=3, pady=10)
        self._bre.set_en(False)

        sep(bf).pack(side="left", padx=8, pady=12)
        self._bf = Btn(bf, "", self._rz, w=40, icon=ICON["fit"],
                       tip="Fit / reset zoom")
        self._bf.pack(side="left", padx=3, pady=10)
        self._bs = Btn(bf, "Split", self._ts, w=82, icon=ICON["split"],
                       tip="Before/after split view")
        self._bs.pack(side="left", padx=3, pady=10)
        self._ba = Btn(bf, "", None, w=44, accent=T["accent2"], icon=ICON["before_after"],
                       tip="Hold to preview original")
        self._ba.bind("<ButtonPress-1>", lambda e: self._so(True))
        self._ba.bind("<ButtonRelease-1>", lambda e: self._so(False))
        # Keyboard equivalent: hold Space/Enter on the focused button.
        self._ba_held = False
        def _ba_down(e):
            if not self._ba_held:
                self._ba_held = True
                self._so(True)
            return "break"
        def _ba_up(e):
            if self._ba_held:
                self._ba_held = False
                self._so(False)
            return "break"
        for _k in ("space", "Return"):
            self._ba.bind("<KeyPress-%s>" % _k, _ba_down)
            self._ba.bind("<KeyRelease-%s>" % _k, _ba_up)
        self._ba.pack(side="left", padx=3, pady=10)

        # Compact, intentional clusters: keep related commands adjacent,
        # then let the center frame own spare width rather than stretching
        # every inter-button gap across the entire display.
        self._tb_groups = (
            (self._bo, self._bi, self._bsp, self._blp),
            (self._bc, self._bm, self._br),
            (self._bu, self._bre),
            (self._bf, self._bs, self._ba),
        )
        # Pack's default expand=False is intentional. Reconfiguring existing
        # slaves here reorders Tk's pack list and can move Redo/Fit into earlier
        # slots; _toolbar_fit only adjusts compact mode and padding.

        # Export/Batch controls are attached to the right group reserved above.
        self._tb_top, self._tb_logo = top, logo
        self._tb_center, self._tb_right = bf, rf
        self._tb_last_w = 0
        self._tb_busy = False

        self._be = Btn(rf, "EXPORT", self.ex, w=132, h=38, fs=10,
                       kind="solid", icon=ICON["export"], tip="Export current image (Ctrl+E)")
        self._be.pack(side="left", pady=11)
        self._bb = Btn(rf, "Batch", self.bt, w=82, icon=ICON["batch"],
                       tip="Batch export")
        self._bb.pack(side="left", padx=(7, 0), pady=15)
        self._bb.set_en(False)

        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)
        self._bsp.set_en(False)

        bd = tk.Frame(self, bg=T["bg"])
        bd.pack(fill="both", expand=True)
        self._body_host = bd

        self._boot_splash.set_status("Loading presets…", .40)
        return bd

    def _mku_presets(self, bd):
        # LEFT — premium preset library.
        lw = grid_clamp(min(self.winfo_screenwidth()*.17, G["max_right"] - G["rail"]), G["min_panel"], G["max_left"])
        left = tk.Frame(bd, bg=T["card"], highlightthickness=1,
                        highlightbackground=T["stroke"], padx=T["pad"], pady=T["pad"])
        left.pack(side="left", fill="y", padx=(G["base"], G["u"]), pady=G["base"])
        self._left_panel = left
        left.configure(width=lw)
        left.pack_propagate(False)
        _glass_edge(left, T["accent"])

        self._hdr = tk.Label(left, text="PRESET LIBRARY",
                             font=(F["ui"], F["md"], "bold"), bg=T["card"],
                             fg=T["text"], anchor="w")
        self._hdr.pack(fill="x")
        tk.Label(left, text="LOOKS • CAMERA • FILM • YOURS",
                 font=(F["ui"], F["xs"], "bold"), bg=T["card"],
                 fg=T["text_dim"], anchor="w").pack(fill="x", pady=(0, 5))

        search_row = tk.Frame(left, bg=T["card"])
        search_row.pack(fill="x", pady=(0, 6))
        self._preset_q = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self._preset_q,
                          font=(F["ui"], F["base"]))
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, "")
        entry.bind("<KeyRelease>", lambda e: self._preset_search_changed())
        Tip.bind(entry, "Search presets by name, family, or process")
        Btn(search_row, "", self._clear_preset_search, w=30, h=28,
            accent=T["accent2"], icon="×",
            tip="Clear preset search").pack(side="left", padx=(5, 0))

        fr = tk.Frame(left, bg=T["card"])
        fr.pack(fill="x", pady=(0, 7))
        self._flt = tk.StringVar(value="all")
        self._cat_display = tk.StringVar(value="All categories")
        cat_map = {
            "All categories": "all", "Film": "film",
            "Cinematic Cameras": "cinematic_cameras",
            "Phones": "phones", "Vintage": "vintage", "Modern": "modern"}
        cat_cb = ttk.Combobox(
            fr, textvariable=self._cat_display,
            values=tuple(cat_map.keys()), state="readonly",
            font=(F["ui"], F["sm"]))
        cat_cb.pack(side="left", fill="x", expand=True)
        cat_cb.set("All categories")
        cat_cb.bind("<<ComboboxSelected>>",
                    lambda e: (self._flt.set(cat_map.get(
                        self._cat_display.get(), "all")), self._rl()))
        Tip.bind(cat_cb, "Filter presets by category")

        self._fav_only = tk.IntVar(value=0)
        tk.Checkbutton(left, text="★ Favorites only", variable=self._fav_only,
                       command=self._rl, bg=T["card"], fg=T["text_dim"],
                       selectcolor=T["panel"], activebackground=T["card_hi"],
                       activeforeground=T["accent_fg"], font=(F["ui"], F["sm"], "bold"),
                       anchor="w", relief="flat", bd=0, highlightthickness=2, highlightbackground=T["card"], highlightcolor=T["focus"]).pack(fill="x", pady=(0, 6))

        # Keep the preset list and imported list in independent full-width
        # containers. Packing the preset scrollbar directly on left used
        # to steal 15 px from the later bottom container, shifting its
        # scrollbar left and breaking the sidebar right-edge alignment.
        imp_wrap = tk.Frame(left, bg=T["card"],
                            height=int(np.clip(self.winfo_screenheight()*.28,
                                               190, 320)))
        imp_wrap.pack(side="bottom", fill="x")
        imp_wrap.pack_propagate(False)
        self._pci = tk.Canvas(imp_wrap, bg=T["panel"], highlightthickness=0)
        sbi = ttk.Scrollbar(imp_wrap, orient="vertical",
                            command=self._pci.yview)
        self._pci.configure(yscrollcommand=sbi.set)
        sbi.pack(side="right", fill="y")
        self._pci.pack(fill="both", expand=True)
        self._ini = tk.Frame(self._pci, bg=T["panel"])
        self._ini.bind("<Configure>", lambda e: self._pci.configure(
            scrollregion=self._pci.bbox("all")))
        _pci_win = self._pci.create_window((0, 0), window=self._ini, anchor="nw")
        self._pci.bind("<Configure>",
                       lambda e: self._pci.itemconfig(_pci_win, width=e.width))

        self._hdr_imp = tk.Label(left, text="IMPORTED — 0",
                                 font=(F["ui"], F["sm"], "bold"),
                                 bg=T["card"], fg=T["text_dim"], anchor="w")
        self._hdr_imp.pack(side="bottom", fill="x", pady=(0, 2))
        tk.Frame(left, bg=T["stroke"], height=1
                ).pack(side="bottom", fill="x", pady=(6, 4))

        preset_wrap = tk.Frame(left, bg=T["card"])
        preset_wrap.pack(fill="both", expand=True)
        self._preset_wrap = preset_wrap
        self._pc = tk.Canvas(preset_wrap, bg=T["panel"], highlightthickness=0)
        sb = ttk.Scrollbar(preset_wrap, orient="vertical", command=self._pc.yview)
        self._pc.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._pc.pack(fill="both", expand=True)
        self._in = tk.Frame(self._pc, bg=T["panel"])
        self._in.bind("<Configure>", lambda e: self._pc.configure(
            scrollregion=self._pc.bbox("all")))
        _pc_win = self._pc.create_window((0, 0), window=self._in, anchor="nw")
        self._pc.bind("<Configure>",
                      lambda e: self._pc.itemconfig(_pc_win, width=e.width))

        self._boot_splash.set_status("Preparing canvas…", .62)
        return left

    def _mku_canvas(self, bd):
        # CENTER — image first, controls quiet when not needed.
        ct = tk.Frame(bd, bg=T["bg"])
        ct.pack(side="left", fill="both", expand=True, padx=4, pady=9)
        self._center_panel = ct
        self.cnv = tk.Canvas(ct, bg=T["canvas"], highlightthickness=1,
                             highlightbackground=T["stroke"])
        self.cnv.pack(fill="both", expand=True)
        self._empty_open = Btn(self.cnv, "OPEN IMAGE", self.oi, w=156, h=36,
                                kind="solid", icon="▣",
                                tip="Open an image (Ctrl+O)")
        self._empty_open.place(relx=.5, rely=.62, anchor="center")

        self._hc = tk.Canvas(ct, bg=T["card"],
                             height=74 if self.winfo_screenheight() > 800 else 60,
                             highlightthickness=1,
                             highlightbackground=T["stroke"])
        self._hc.pack(fill="x", pady=(3, 0))
        # Workspace context is presented in the inspector header, not
        # as a floating placeholder over the image/histogram boundary.
        self.cnv.bind("<Configure>", lambda e: self._paint())
        self._bp()

        self._boot_splash.set_status("Building settings panel…", .82)

    def _mku_inspector(self, bd, left):
        # RIGHT — professional controls.
        rw = grid_clamp(self.winfo_screenwidth()*.19, 268, G["max_right"])
        right = tk.Frame(bd, bg=T["card"], highlightthickness=1,
                         highlightbackground=T["stroke"], padx=T["pad"], pady=T["pad"])
        right.pack(side="right", fill="y", padx=(G["u"], G["base"]), pady=G["base"])
        self._right_panel = right
        right.configure(width=rw)
        right.pack_propagate(False)
        _glass_edge(right, T["accent2"])
        self._workspace_context_label = tk.Label(
            right, text="EDIT  •  BASIC", bg=T["card"],
            fg=T["text"], font=(F["ui"], F["base"], "bold"), anchor="w")
        self._workspace_context_label.pack(fill="x", pady=(0, 5))
        self._tool_strip(right)
        self._bs_(right)

        self._boot_splash.set_status("Finishing up…", .95)
        sb = tk.Frame(self, bg=T["panel"])
        sb.pack(fill="x", side="bottom")
        self._st = tk.Label(sb, text="READY",
                            bg=T["panel"], fg=T["text_dim"],
                            font=(F["ui"], F["sm"], "bold"), anchor="w", padx=12, pady=5)
        self._st.pack(fill="x", side="left", expand=True)
        self._zoom_lbl = tk.Label(sb, text="", bg=T["panel"], fg=T["muted"],
                                  font=(F["mono"], F["sm"]), anchor="e", padx=12)
        self._zoom_lbl.pack(side="right")

        # Workspace navigation belongs to the work surface, not the
        # application status/footer. A fixed vertical rail keeps the
        # navigation visible without consuming image-viewer height.
        ws = tk.Frame(bd, bg=T["panel"], width=G["rail"])
        ws.pack(side="left", fill="y", padx=(9, 4), pady=9, before=left)
        self._workspace_panel = ws
        ws.pack_propagate(False)
        tk.Label(ws, text="WORK\nSPACE", bg=T["panel"], fg=T["text_dim"],
                 font=(F["ui"], F["xs"], "bold"), justify="center"
                 ).pack(fill="x", pady=(2, 8))
        for name in ("Edit", "Color", "Tone", "Refine", "Camera", "Film"):
            b = Btn(ws, name, lambda n=name: self._set_workspace(n),
                    w=58, h=36, fs=8, accent=T["accent"])
            b.pack(fill="x", padx=5, pady=3)
            self._workspace_rail[name] = b
        self._workspace_rail["Edit"].set_active(True)
        tk.Frame(ws, bg=T["stroke"], height=1).pack(fill="x", padx=8, pady=10)
        self._focus_button = Btn(ws, "FOCUS", lambda: self._enter_focus_workspace(self._workspace),
                                 w=58, h=32, fs=8, accent=T["accent2"])
        self._focus_button.pack(fill="x", padx=5, pady=3)

    def _mku_finish(self):
        # Populate the real preset library before the first frame is shown.
        # Without this explicit initial refresh, the library starts empty
        # until another action happens to call _rl().
        self._rl()

        # Establish a real initial workspace state and scroll the inspector
        # to the first relevant control group.
        self._set_workspace("Edit")
        # Run after every rail control exists; early Configure events may
        # arrive before _focus_button and leave the fixed-width pass incomplete.
        self._fit_fixed_containers()










    def command_palette(self):
        if self._palette is not None and self._palette.winfo_exists():
            try:
                self._palette.focus_force()
            except Exception:
                pass
            return
        d = tk.Toplevel(self)
        self._palette = d
        d.overrideredirect(True)
        d.configure(bg=T["bg"])
        d.transient(self)
        d.geometry("650x460+%d+%d" % (
            self.winfo_rootx() + max(40, self.winfo_width()//2 - 325),
            self.winfo_rooty() + 78))
        wrap = tk.Frame(d, bg=T["card"], highlightthickness=1,
                        highlightbackground=T["stroke_hi"], padx=14, pady=14)
        wrap.pack(fill="both", expand=True)
        top = tk.Frame(wrap, bg=T["card"])
        top.pack(fill="x")
        tk.Label(top, text="COMMAND", bg=T["card"], fg=T["accent_fg"],
                 font=(F["ui"], F["sm"], "bold")).pack(side="left")
        tk.Label(top, text="Ctrl+K  •  Escape to close",
                 bg=T["card"], fg=T["text_dim"],
                 font=(F["ui"], F["xs"])).pack(side="right")
        q = tk.StringVar()
        e = ttk.Entry(wrap, textvariable=q, font=(F["ui"], F["lg"]))
        e.pack(fill="x", pady=(8, 10))
        Tip.bind(e, "Search actions and presets")
        lb = tk.Listbox(wrap, bg=T["panel"], fg=T["text"],
                        selectbackground=T["accent"], selectforeground=T["white"],
                        highlightthickness=0, relief="flat",
                        font=(F["ui"], F["base"]), activestyle="none")
        lb.pack(fill="both", expand=True)

        actions = [
            ("Open Image", self.oi),
            ("Import Presets / LUTs", self.ip),
            ("Export Current Image", self.ex),
            ("Batch Export", self.bt),
            ("Reset All Edits", self.rs),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Fit Canvas", self._rz),
            ("Toggle Split Before / After", self._ts),
            ("Crop / Straighten", self.tc),
            ("Local Masks", self.mask_tool),
            ("Auto Tone", self.auto_tone),
            ("Save Snapshot", self.snapshot_save),
            ("Next Snapshot", self.snapshot_next),
            ("Toggle Clipping Overlay (J)", self.clip_toggle),
            ("Heal Spot (click)", self.heal_toggle),
            ("Clear Healing Spots", self.heal_clear),
            ("Auto White Balance", self.auto_wb),
            ("Pick Gray Point", self._wb_pick_toggle),
        ]
        for p in PRES:
            actions.append((f"Preset  •  {p.get('name','')}", lambda p=p: self.apl(p)))
        for p in self.imp:
            actions.append((f"Imported  •  {p.get('name','')}", lambda p=p: self.apl(p)))

        current = {"items": []}
        def populate(*_):
            needle = q.get().strip().lower()
            items = [(lbl, fn) for lbl, fn in actions
                     if not needle or needle in lbl.lower()]
            current["items"] = items
            lb.delete(0, "end")
            for lbl, _ in items[:120]:
                lb.insert("end", lbl)
            if items:
                lb.selection_set(0)

        def run_selected(*_):
            i = lb.curselection()
            if not i or not current["items"]:
                return "break"
            fn = current["items"][i[0]][1]
            d.destroy()
            self._palette = None
            try:
                fn()
            except Exception as ex:
                messagebox.showerror(APP_NAME, str(ex), parent=self)
            return "break"

        q.trace_add("write", populate)
        lb.bind("<Double-Button-1>", run_selected)
        e.bind("<Return>", run_selected)
        e.bind("<Down>", lambda ev: (lb.focus_set(),
                                     lb.selection_set(min(
                                         max(lb.size()-1, 0),
                                         (lb.curselection()[0]+1 if lb.curselection() else 0))),
                                     "break")[2])
        lb.bind("<Return>", run_selected)
        def close(_=None):
            try:
                d.destroy()
            finally:
                self._palette = None
            return "break"
        d.bind("<Escape>", close)
        d.bind("<FocusOut>", lambda ev: None)
        populate()
        e.focus_set()
        d.update_idletasks()

    def _bs_(self, parent):
        c = tk.Canvas(parent, bg=T["card"], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=c.yview)
        c.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        c.pack(side="left", fill="both", expand=True)
        inn = tk.Frame(c, bg=T["card"])
        self._inspector_inner = inn
        _c_win = c.create_window((0, 0), window=inn, anchor="nw")
        inn.bind("<Configure>", lambda e: c.configure(
            scrollregion=c.bbox("all")))
        c.bind("<Configure>", lambda e: c.itemconfig(_c_win, width=e.width))
        self._sc = c

        hd = tk.Frame(inn, bg=T["card"])
        hd.pack(fill="x", pady=(2, 3))
        tk.Label(hd, text="PIPELINE", font=(F["ui"], F["base"], "bold"),
                 bg=T["card"], fg=T["accent_fg"]).pack(side="left")
        tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x", side="left",
                                                    padx=T["pad"], pady=T["pad"])
        for t, v in [("Scene Prep — linear WB", self.v_prep),
                     ("Print Stock 2383", self.v_pr),
                     (f"ACES Display Transform{' (OCIO)' if HAVE_OCIO else ' (fallback fit)'}",
                      self.v_aces)]:
            _autowrap(tk.Checkbutton(inn, text=t, variable=v, bg=T["card"],
                           fg=T["text"], selectcolor=T["panel"],
                           activebackground=T["card_hi"],
                           activeforeground=T["accent_fg"], font=T["font_sm"],
                           anchor="w",
                           command=lambda: self._scd(None), highlightthickness=2, highlightbackground=T["card"], highlightcolor=T["focus"], justify="left"), pad=34).pack(fill="x",
                                                                 pady=1)
        Param(inn, "Print Strength", self.v_ps,
              lambda k: self._scd(k), 0, 1, "{:.2f}", 1,
              key="print_strength",
              info="میزان تاثیر شبیه‌سازی چاپ فیلم سینمایی روی نگاتیو "
                   "دیجیتال (پروفایل 2383) را کنترل می‌کند؛ فقط وقتی "
                   "Print Stock فعال باشد اثر دارد. صفر یعنی بدون تاثیر و "
                   "۱ یعنی تاثیر کامل شبیه‌سازی چاپ."
              ).pack(fill="x", pady=2)
        self._pss = Param(inn, "Preset Strength", self.v_ss,
              lambda k: self._scd(k), 0, 1, "{:.0%}", 1,
              key="lut3d_strength",
              info="شدت کلی اعمال پریست یا LUT انتخاب‌شده را کنترل می‌کند. "
                   "۱۰۰٪ یعنی پریست به‌طور کامل اعمال شود و درصدهای کمتر آن "
                   "را با تصویر اصلی مخلوط می‌کنند (برای گرفتن جلوه‌ای ملایم‌تر).")
        self._pss.pack(fill="x", pady=2)

        self._bs_camera_match(inn)

        gr = {}
        for k, l, lo, hi, f in SPEC:
            gr.setdefault(GRP[k], []).append((k, l, lo, hi, f))
        py = 2 if len(SPEC) < 26 else 1
        for g in GORD:
            rows = gr.get(g, [])
            if not rows:
                continue
            hd, box = self._sec_make_header(inn, g, [r[0] for r in rows], py)
            _cg_sub = ["Shadows"]*3+["Midtones"]*3+["Highlights"]*3+ \
                ["Global"]*3+["Blending"]
            for i, (k, l, lo, hi, f) in enumerate(rows):
                if g == "HSL":
                    continue
                if g == "COLOR GRADE" and i < len(_cg_sub) and \
                        (i == 0 or _cg_sub[i] != _cg_sub[i-1]):
                    tk.Label(box, text=_cg_sub[i], bg=T["card"],
                            fg=T["accent_fg"], font=(F["ui"], F["sm"], "bold"),
                            anchor="w").pack(fill="x", pady=(6 if i else 0, 0))
                Param(box, l, self.vars[k], self._scd, lo, hi, f,
                      DEF.get(k, 0), key=k, info=PARAM_INFO.get(k)).pack(fill="x", pady=py)
            if g == "HSL":
                HSLMixer(box, self).pack(fill="x", pady=(0, 4))
            if g == "LIGHT":
                chd = tk.Frame(box, bg=T["card"])
                chd.pack(fill="x", pady=(6, 2))
                tk.Label(chd, text="Tone Curve", bg=T["card"],
                         fg=T["text_dim"], font=T["font_sm"],
                         anchor="w").pack(side="left")
                Btn(chd, "Reset", self._curve_reset, w=64, h=22, fs=8,
                   icon="↺").pack(side="right")
                self._curve_w = CurveEditor(box, self._curve_changed)
                self._curve_w.pack(fill="x", pady=(0, 4))
                _autowrap(tk.Label(box, text="drag, or arrows to move  •  click / Insert add  •  "
                        "right-click / Del remove", bg=T["card"],
                        fg=T["text_dim"], font=(F["ui"], F["sm"]),
                        wraplength=250, justify="left", anchor="w"
                        )).pack(fill="x", pady=(0, 4))
            if g == "WHITE BALANCE":
                wbr = tk.Frame(box, bg=T["card"])
                wbr.pack(fill="x", pady=(3, 5))
                self._wb_pick_btn = Btn(
                    wbr, "Pick Gray Point", self._wb_pick_toggle,
                    w=150, accent=T["accent2"], icon="◎",
                    tip="Click a neutral gray/white area in the image")
                self._wb_pick_btn.pack(side="left")
                Btn(wbr, "Auto WB", self.auto_wb, w=100, icon="◐",
                    accent=T["accent"],
                    tip="Gray-world automatic white balance"
                    ).pack(side="left", padx=(6, 0))
        tk.Frame(inn, bg=T["card"], height=12).pack()











    def _neutralize(self):
        """Everything a preset/edit/Camera-Match apply can touch, back
        to defaults in one place — shared by Reset-all and by opening
        a new image, so a new image always starts from a clean slate
        instead of inheriting the previous image's grade."""
        self.ap = None
        self.spots = []
        self._snaps = []
        self._heal_picking = False
        ENG._lc.clear()
        self.curve_pts = None
        for k, v in self.vars.items():
            v.set(DEF.get(k, 0))
        self.v_prep.set(1)
        self.v_pr.set(0)
        self.v_ps.set(1)
        self.v_ss.set(1.0)
        self._reset_cm_ui()
        self._ck = None
        self._sync_strength_label()
        if hasattr(self, "_curve_w"):
            self._curve_w.set_curves(DEF["tone_curve_pts"])

    def _curve_changed(self, curves):
        self.curve_pts = curves
        self._scd("tone_curve_pts")
        self.req()

    def _curve_reset(self):
        self.curve_pts = {c: list(v) for c, v in
                          DEF["tone_curve_pts"].items()}
        if hasattr(self, "_curve_w"):
            self._curve_w.set_curves(self.curve_pts)
        self._scd("tone_curve_pts")

    def rs(self):
        self._neutralize()
        self._mark_active()
        self.req()
        self._st.configure(text="Reset to neutral", fg=T["text_dim"])
        self._mode_lbl.configure(text="IMAGE LAB  •  READY") if hasattr(self, "_mode_lbl") else None
        self._toast("Edits reset to neutral", "info")

    # ---- White balance: gray-point picker + gray-world auto ----










    def _acs(self):
        if self._o is None:
            return
        base = self._o
        if abs(self._srot) > 1e-6:
            base = _rotate_straight(base, self._srot)
        if self.cr:
            w, h = base.size
            x0, y0, x1, y1 = self.cr
            self.src = base.crop((int(x0*w), int(y0*h),
                                  int(x1*w), int(y1*h)))
        else:
            self.src = base.copy()
        fs = min(1, PREVIEW_MAX/max(self.src.size))
        self._fit_wh = (max(1, int(self.src.width*fs)),
                        max(1, int(self.src.height*fs)))
        self._mk_preview(PREVIEW_MAX)














    def mask_tool(self):
        if self.src is None or self._ph is None or self._ov or self._ov_str:
            return
        if self._mask_tool:
            self._mask_tool.close()
            return
        self._paint()
        self._mask_tool = MaskTool(self)
        self._bc.set_en(False)
        self._bst.set_en(False)









    def ip(self):
        paths = filedialog.askopenfilenames(
            title="Import preset(s)",
            filetypes=[("Presets", "*.xmp *.cube *.json"),
                       ("XMP", "*.xmp"), ("CUBE", "*.cube"),
                       ("JSON", "*.json"), ("All", "*.*")])
        if not paths:
            return
        existing = {x["name"] for x in self.imp}
        ok, failed = [], []
        for p in paths:
            ex = os.path.splitext(p)[1].lower()
            pr = IMPS.get(ex)
            if pr is None:
                failed.append(f"{os.path.basename(p)} (unsupported {ex})")
                continue
            try:
                ps = pr(p)
            except Exception as e:
                failed.append(f"{os.path.basename(p)}: {e}")
                continue
            # Duplicate-name handling: never silently overwrite/collide —
            # auto-suffix so every imported LUT/preset stays selectable,
            # including duplicates within the same multi-file batch.
            if ps["name"] in existing:
                base, n = ps["name"], 2
                while f"{base} ({n})" in existing:
                    n += 1
                ps["name"] = f"{base} ({n})"
            existing.add(ps["name"])
            self.imp.append(ps)
            ok.append(ps["name"])
        if ok:
            self._svi()
            self._rl()
        msg = ""
        if ok:
            shown = ", ".join(ok[:6])+("…" if len(ok) > 6 else "")
            msg += f"✓ Imported {len(ok)}: {shown}"
        if failed:
            shown = "\n".join(failed[:6])+("\n…" if len(failed) > 6 else "")
            msg += ("\n\n" if msg else "")+f"Failed ({len(failed)}):\n{shown}"
        if msg:
            (messagebox.showinfo if ok and not failed else
             messagebox.showwarning if ok else
             messagebox.showerror)(APP_NAME, msg)

    def _ldi(self):
        try:
            with open(IMPORTED_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, list):
                self.imp = [p for p in d if isinstance(p, dict)]
        except Exception:
            self.imp = []
    def _svi(self):
        try:
            with open(IMPORTED_FILE, "w", encoding="utf-8") as f:
                json.dump(self.imp, f, indent=2, ensure_ascii=False)
        except Exception:
            pass




















def main():
    """Start the Tkinter application and run startup self-tests."""
    app = App()
    app._hc.bind("<Configure>",
                 lambda e: app._hist(app._lo) if app._lo is not None
                 else None)

    def _t():
        t0 = time.time()
        F = self_tests()
        dt = time.time()-t0
        if F:
            s = " | ".join(F[:4])
            app._post(lambda: app._st.configure(
                text=f"⚠ Self-test: {len(F)} FAILED — {s}",
                fg=T["red"]))
        else:
            app._post(lambda: app._st.configure(
                text=f"✓ Self-test passed — {dt:.1f}s • {len(PRES)} "
                     f"presets • v12 engine • layered cache • fused "
                     f"LUT", fg=T["green"]))

    threading.Thread(target=_t, daemon=True).start()
    app.mainloop()
