# SPDX-License-Identifier: MIT
"""Single and batch export."""

import concurrent.futures
import subprocess
from tkinter import filedialog
from .config import APP_NAME
import numpy as np
import threading
from .deps import HAVE_CV2, cv2
from .engine import SK, _cas, _rotate_straight, dithered, ensure_rgb, load_src, staged, staged_tile_safe
from .params import FMTS
import os
import sys
from .theme import F, T
import time
import tkinter as tk
from tkinter import messagebox
from .dialogs import Dlg
from .widgets import Btn, rnd


class ExportMixin:
    """Single and batch export."""

    def ex(self):
        if self.src is None:
            return
        d = tk.Toplevel(self)
        d.configure(bg=T["bg"])
        d.title("Export")
        d.resizable(False, False)
        d.geometry("+%d+%d" % (self.winfo_rootx()+420,
                               self.winfo_rooty()+220))
        f = tk.Frame(d, bg=T["card"], padx=16, pady=14,
                     highlightthickness=1,
                     highlightbackground=T["stroke"])
        f.pack(padx=12, pady=12)
        tk.Label(f, text="EXPORT SETTINGS", font=(F["ui"], F["lg"], "bold"),
                 bg=T["card"], fg=T["accent_fg"]).pack(pady=(0, 8))
        tk.Label(f, text=f"{self.src.width} x {self.src.height}px  •  "
                 f"{self.ap['name'] if self.ap else 'Custom'}",
                 bg=T["card"], fg=T["text_dim"],
                 font=T["font_sm"]).pack(pady=(0, 10))
        sel = tk.StringVar(value=FMTS[0][0])
        for l, _ in FMTS:
            tk.Radiobutton(f, text=l, variable=sel, value=l, bg=T["card"],
                           fg=T["text"], selectcolor=T["panel"],
                           activebackground=T["card_hi"],
                           activeforeground=T["accent_fg"], font=T["font_sm"],
                           anchor="w",
                           highlightthickness=0).pack(fill="x", pady=1)

        def go():
            fmt, q = dict(FMTS)[sel.get()]
            d.destroy()
            self._sx_(fmt, q)

        bf = tk.Frame(f, bg=T["card"])
        bf.pack(pady=(12, 0))
        Btn(bf, "Export…", go, w=112, kind="solid", icon="⇧"
           ).pack(side="left", padx=4)
        Btn(bf, "Cancel", d.destroy, w=96, icon="✕").pack(side="left", padx=4)

    def _sx_(self, fmt, q):
        dn = os.path.splitext(os.path.basename(
            self.mt.get("path", "export")))[0]+"_graded."+fmt
        ex = {"jpg": [("JPEG", "*.jpg *.jpeg")],
              "png": [("PNG", "*.png")],
              "tif": [("TIFF", "*.tif *.tiff")]}
        p = filedialog.asksaveasfilename(title="Save graded image",
                                         initialfile=dn,
                                         defaultextension="."+fmt,
                                         filetypes=ex[fmt])
        if not p:
            return
        self._ep = p
        self._ef, self._eq = fmt, q
        self._eov()
        threading.Thread(target=self._ew, daemon=True).start()

    def _post(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _ecb(self, t, nt):
        def cb(f, l):
            ff = (t+f)/nt*.85
            ll = f"tile {t+1}/{nt} — {l}"
            self._post(lambda: self._epr(ff, ll))
        return cb

    def _ew(self):
        t0 = time.time()
        try:
            if self.mt.get("raw") and self.mt.get("raw_proxy"):
                self._ensure_raw_full_source()
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
            rgb = ensure_rgb(self.src)
            st = self._stg()
            H, W = rgb.shape[:2]
            TP = 8*1024*1024//3
            rpt = max(64, TP//W)
            nt = max(1, (H+rpt-1)//rpt)
            out = np.empty_like(rgb)
            # Spatial/global stages are not yet halo-safe.  Do not silently
            # produce seam-bearing exports: keep those renders full-frame
            # until the halo-aware scheduler is implemented.
            if not staged_tile_safe(st):
                out[:] = staged(rgb, st, self._ecb(0, 1))
            else:
                # Tiles are independent row-slices -> safe to process concurrently.
                # Worker count self-adapts to the machine: 1 core behaves exactly
                # like the previous sequential loop (no behavior change), >1 core
                # runs tiles in parallel since numpy/cv2 release the GIL during
                # the heavy per-tile math.
                workers = min(nt, os.cpu_count() or 1)
                if HAVE_CV2:
                    try:
                        cv2.setNumThreads(1 if workers > 1 else
                                           max(cv2.getNumberOfCPUs()-1, 1))
                    except Exception:
                        pass
                if any(abs(st.get(k, 0)) > .5 for k in SK):
                    _cas()  # warm the lazy cascade singleton before workers start
                if workers > 1:
                    def _tile(t):
                        y0 = t*rpt
                        y1 = min(y0+rpt, H)
                        out[y0:y1] = staged(rgb[y0:y1], st, self._ecb(t, nt),
                                            full_h=H, y0=y0)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                        list(ex.map(_tile, range(nt)))
                else:
                    for t in range(nt):
                        y0 = t*rpt
                        y1 = min(y0+rpt, H)
                        out[y0:y1] = staged(rgb[y0:y1], st, self._ecb(t, nt),
                                            full_h=H, y0=y0)
            self._post(lambda: self._epr(.92, "Encoding & saving"))
            img = dithered(out, seed=int(t0*1000) % 99991)
            kw = {}
            if self._ef == "jpg":
                kw = dict(quality=self._eq,
                          subsampling=1 if self._eq >= 90 else 2,
                          optimize=False, progressive=False)
            elif self._ef == "png":
                kw = dict(optimize=False, compress_level=3)
            elif self._ef == "tif":
                kw = dict(compression="tiff_lzw")
            try:
                if self._o is not None:
                    xb = self._o.info.get("exif")
                    if xb and self._ef == "jpg":
                        kw["exif"] = xb
            except Exception:
                pass
            img.save(self._ep, **kw)
            el = time.time()-t0
            kb = os.path.getsize(self._ep)/1024
            self._post(lambda: self._edn(el, kb))
        except Exception as e:
            m = str(e)
            self._post(lambda: self._ef_(m))

    def _edn(self, el, kb):
        self._eh()
        p = self._ep

        def of():
            try:
                fo = os.path.dirname(os.path.abspath(p))
                if sys.platform.startswith("win"):
                    os.startfile(fo)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", fo])
                else:
                    subprocess.Popen(["xdg-open", fo])
            except Exception:
                pass
            return True

        self.after(60, lambda: Dlg(
            self, "✓ Export Complete",
            [f"File:  {os.path.basename(p)}",
             f"Size:  {kb:,.0f} KB",
             f"Time:  {el:.2f}s  —  {self._ef.upper()}"],
            [("📂  Open Folder", of, True), ("Close", None, False)]))
        self._st.configure(text=f"✓ Exported → {p}  ({el:.2f}s, "
                           f"{kb:,.0f} KB)", fg=T["green"])
        self._toast(f"Export complete  •  {os.path.basename(p)}", "success")

    def _ef_(self, m):
        self._eh()
        messagebox.showerror(APP_NAME, f"Export failed:\n{m}")

    def bt(self):
        if self.src is None:
            return
        fi = filedialog.askdirectory(title="Input folder")
        if not fi:
            return
        fo = filedialog.askdirectory(title="Output folder")
        if not fo:
            return
        exs = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
        fs = sorted(f for f in os.listdir(fi)
                    if os.path.splitext(f)[1].lower() in exs)
        if not fs:
            messagebox.showinfo("Batch", "No images found.")
            return
        self._bf = fs
        self._bfi, self._bfo = fi, fo
        self._bt = len(fs)
        self._bd = 0
        self._bs = self._stg()
        self._eov()
        threading.Thread(target=self._bw, daemon=True).start()

    def _bcb(self, d, t):
        def cb(f, l):
            ff = (d+f)/t
            ll = f"file {d+1}/{t} — {l}"
            self._post(lambda: self._epr(ff, ll))
        return cb

    def _bw(self):
        t0 = time.time()
        try:
            workers = min(len(self._bf), os.cpu_count() or 1) if self._bf else 1
            if HAVE_CV2:
                try:
                    cv2.setNumThreads(1 if workers > 1 else
                                       max(cv2.getNumberOfCPUs()-1, 1))
                except Exception:
                    pass
            if any(abs(self._bs.get(k, 0)) > .5 for k in SK):
                _cas()  # warm the lazy cascade singleton before any workers start

            lock = threading.Lock()
            stop = threading.Event()
            first_exc = [None]

            def process(n):
                if stop.is_set():
                    return
                p = os.path.join(self._bfi, n)
                try:
                    im, _ = load_src(p)
                except Exception:
                    with lock:
                        self._bd += 1
                    return
                try:
                    rgb = ensure_rgb(im)
                    with lock:
                        d, t = self._bd, self._bt
                    o = staged(rgb, self._bs, self._bcb(d, t))
                    pl = dithered(o, seed=d)
                    pl.save(os.path.join(
                        self._bfo, os.path.splitext(n)[0]+"_graded.jpg"),
                        quality=95, subsampling=1, optimize=False)
                except Exception as e:
                    stop.set()
                    with lock:
                        if first_exc[0] is None:
                            first_exc[0] = e
                    return
                with lock:
                    self._bd += 1

            # Files are fully independent (own load/process/save) -> safe to
            # run concurrently. 1 core = identical sequential behavior as
            # before; >1 core parallelizes since numpy/cv2 release the GIL.
            if workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = [ex.submit(process, n) for n in self._bf]
                    concurrent.futures.wait(futs)
            else:
                for n in self._bf:
                    process(n)

            if first_exc[0] is not None:
                raise first_exc[0]

            el = time.time()-t0
            self._post(lambda: self._bdn(el))
        except Exception as e:
            m = str(e)
            self._post(lambda: self._ef_(m))

    def _bdn(self, el):
        self._eh()
        self._st.configure(text=f"✓ Batch: {self._bd}/{self._bt} files "
                           f"({el:.1f}s) → {self._bfo}", fg=T["green"])
        self._toast(f"Batch export complete  •  {self._bd}/{self._bt}", "success")
        messagebox.showinfo("Batch Export",
                            f"✓ {self._bd}/{self._bt} files processed\n"
                            f"Time: {el:.1f}s\n→ {self._bfo}")

    def _eov(self):
        self._eh()
        cw = max(1, self.cnv.winfo_width())
        ch = max(1, self.cnv.winfo_height())
        W, H = 392, 132
        ox, oy = (cw-W)//2, (ch-H)//2
        self._ec = tk.Canvas(self.cnv, width=W, height=H, bg=T["bg"],
                             highlightthickness=0)
        self._ec.place(x=ox, y=oy)
        rnd(self._ec, 2, 2, W-4, H-4, T["radius_lg"], fill=T["glass"],
            outline=T["accent"], width=2)
        self._ec.create_text(W//2, 28, text="⚡ PROCESSING",
                             fill=T["text"], font=(F["ui"], 11, "bold"))
        self._es = self._ec.create_text(W//2, 52, text="Preparing…",
                                        fill=T["text_dim"],
                                        font=T["font_sm"])
        self._ec.create_rectangle(32, 78, W-32, 88, fill=T["panel"],
                                 outline=T["stroke"])
        self._eb = self._ec.create_rectangle(32, 78, 33, 88,
                                             fill=T["accent"], outline="")
        self._ep_ = self._ec.create_text(W//2, 103, text="0%",
                                         fill=T["accent"],
                                         font=(F["mono"], F["md"], "bold"))
        self._be.set_en(False)
        self._bb.set_en(False)

    def _epr(self, f, l):
        if not hasattr(self, "_ec"):
            return
        W = 392
        fw = int((W-64)*max(0, min(1, f)))
        self._ec.coords(self._eb, 32, 78, 32+max(1, fw), 84)
        self._ec.itemconfigure(self._es, text=l)
        self._ec.itemconfigure(self._ep_, text="working")

    def _eh(self):
        if hasattr(self, "_ec"):
            try:
                self._ec.destroy()
            except Exception:
                pass
            del self._ec
        self._be.set_en(self.src is not None)
        self._bb.set_en(self.src is not None)
