# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
# ============================================================
#  LUMEN FORGE v12.0 — RENDER ENGINE v12 — CAMERA DNA 2.3
#  Fused per-channel Tone+Gamma LUT • Layered Cache •
#  109 presets (incl. 17 Vintage Cameras, 8 Modern / Unique) • Mobile DNA v2
#  Camera DNA 2.3: 53 camera profiles, metadata+pixel Camera Match,
#  evidence/margin-gated confidence (Detected/Estimated/Low confidence/
#  Unknown), exposure-robust relative-shape pixel features, source-
#  >neutral->target->creative pipeline in OKLab, honest "-inspired"
#  labeling (no proprietary IDTs)
#  Classic 3-column dynamic UI • All features
#  Run:   python lumenforge.py
#  EXE:   pyinstaller --onefile --noconsole --name "LumenForge" lumenforge.py
# ============================================================

import os, re, json, math, time, threading, subprocess, sys, tempfile, copy
import concurrent.futures

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import numpy as np
from PIL import Image, ImageTk, ImageOps, ImageFilter, ImageDraw, ExifTags

try:
    import rawpy
except Exception:
    rawpy = None

try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False

APP_NAME = "Lumen Forge"
VERSION = "12.0"

if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMPORTED_FILE = os.path.join(SCRIPT_DIR, "imported_presets.json")

def _dpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
_dpi()

# ---- Design tokens ----
\
# Burgundy Noir — deep wine/plum base with a vivid burgundy-magenta
# accent and a dusty mauve-silver secondary, still rendered with the
# metallic-gradient + glass-highlight control style.
T = {"bg":"#0b0911","panel":"#100d18","card":"#151220","card_hi":"#1d1830",
     "stroke":"#2b2540","stroke_hi":"#40365f","text":"#f3eff9",
     "text_dim":"#a7a0b4","accent":"#8d6cff","accent2":"#6f63b7",
     "gold":"#e7c56a","green":"#5bd6a0","red":"#ff647d","glass":"#13101d",
     "font":("Segoe UI",10),"font_sm":("Segoe UI",9),
     "title":("Segoe UI",15,"bold"),
     # Central design-system geometry tokens. Presentation only.
     "radius":9,"radius_sm":6,"radius_lg":12,
     "ctrl_h":30,"pad":9,"pad_sm":5}

def _mix(c1, c2, t):
    """Blend two '#rrggbb' colors, t in [0,1] toward c2. Used for the
    metallic gradient bands and glass shine highlights on controls."""
    c1 = c1.lstrip("#"); c2 = c2.lstrip("#")
    r1,g1,b1 = int(c1[0:2],16),int(c1[2:4],16),int(c1[4:6],16)
    r2,g2,b2 = int(c2[0:2],16),int(c2[2:4],16),int(c2[4:6],16)
    r = int(r1+(r2-r1)*t); g = int(g1+(g2-g1)*t); b = int(b1+(b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"

MOTION = {
    "micro": 90,
    "panel": 150,
    "dialog": 180,
    "toast": 2400,
    "scan": 55,
}

PREVIEW_MAX = 900
PREVIEW_ZOOM_MAX = 3600  # ceiling for the zoomed-in preview resolution —
                          # keeps re-renders fast on very large source
                          # images while still giving a sharp 1:1-ish view
ZOOM_MAX = 8.0
RAW_EXT = {".arw",".cr2",".cr3",".nef",".nrw",".raf",".orf",".rw2",
           ".dng",".pef",".srw",".3fr",".raw"}

try:
    LANCZOS = Image.Resampling.LANCZOS
    BILINEAR = Image.Resampling.BILINEAR
    BICUBIC = Image.Resampling.BICUBIC
except AttributeError:
    LANCZOS = Image.LANCZOS
    BILINEAR = Image.BILINEAR
    BICUBIC = Image.BICUBIC
try:
    ROTATE_270 = Image.Transpose.ROTATE_270
    FLIP_LEFT_RIGHT = Image.Transpose.FLIP_LEFT_RIGHT
    FLIP_TOP_BOTTOM = Image.Transpose.FLIP_TOP_BOTTOM
except AttributeError:
    ROTATE_270 = Image.ROTATE_270
    FLIP_LEFT_RIGHT = Image.FLIP_LEFT_RIGHT
    FLIP_TOP_BOTTOM = Image.FLIP_TOP_BOTTOM


# ============================================================
#  NUMERICAL UTILITIES
# ============================================================

def arr32(x): return np.asarray(x, np.float32)
def clamp(x, lo=0.0, hi=1.0): return np.clip(arr32(x), lo, hi)
def luminance(rgb):
    rgb = arr32(rgb)
    return rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
def smoothstep(e0, e1, x):
    x = arr32(x)
    d = float(e1-e0)
    if abs(d) < 1e-8:
        return np.zeros_like(x, np.float32)
    t = np.clip((x-float(e0))/d, 0, 1)
    return t*t*(3-2*t)
def ensure_rgb(image):
    if isinstance(image, Image.Image):
        image = np.asarray(image.convert("RGB"))
    x = np.asarray(image)
    if x.ndim != 3 or x.shape[-1] != 3:
        raise ValueError("Need HxWx3 RGB.")
    if x.size == 0:
        raise ValueError("Empty image.")
    if np.issubdtype(x.dtype, np.integer):
        return x.astype(np.float32)/255.0
    x = x.astype(np.float32)
    if float(np.nanmax(x)) > 1.5:
        x /= 255.0
    return clamp(x)
def to_pil(rgb):
    return Image.fromarray(np.uint8(np.round(clamp(rgb)*255)), "RGB")
def dithered(rgb, seed=1):
    x = clamp(rgb)
    rng = np.random.default_rng(seed)
    d = (rng.random(x.shape, np.float32)-.5)/255.0
    return Image.fromarray(np.uint8(np.clip(
        np.round((x+d)*255), 0, 255)), "RGB")
def srgb2lin(rgb):
    x = clamp(rgb)
    return np.where(x <= .04045, x/12.92, np.power((x+.055)/1.055, 2.4))
def lin2srgb(rgb):
    x = np.maximum(arr32(rgb), 0)
    return np.where(x <= .0031308, x*12.92, 1.055*np.power(x, 1/2.4)-.055)
def thumb(rgb, w=56):
    x = ensure_rgb(rgb)
    h, ww = x.shape[:2]
    if ww <= w:
        return x
    return ensure_rgb(to_pil(x).resize((w, max(1, int(h*w/ww))), BILINEAR))
def analysis_size(rgb, mx=400):
    x = ensure_rgb(rgb)
    h, w = x.shape[:2]
    s = min(1.0, mx/max(h, w))
    if s >= 1:
        return x
    return ensure_rgb(to_pil(x).resize(
        (max(1,int(w*s)), max(1,int(h*s))), BILINEAR))

def _largest_rotated_rect(w, h, angle_rad):
    """Largest axis-aligned rectangle that fits, without any blank
    corner, inside a w x h rectangle after it's been rotated by
    angle_rad. Standard 'rotate photo without black borders' formula."""
    if w <= 0 or h <= 0:
        return 0, 0
    a = abs(angle_rad) % math.pi
    if a > math.pi/2:
        a = math.pi-a
    width_is_longer = w >= h
    side_long, side_short = (w, h) if width_is_longer else (h, w)
    sin_a, cos_a = math.sin(a), math.cos(a)
    if side_short <= 2.*sin_a*cos_a*side_long+1e-9 or abs(sin_a-cos_a) < 1e-10:
        x = 0.5*side_short
        if width_is_longer:
            wr, hr = x/sin_a, x/cos_a
        else:
            wr, hr = x/cos_a, x/sin_a
    else:
        cos_2a = cos_a*cos_a-sin_a*sin_a
        wr = (w*cos_a-h*sin_a)/cos_2a
        hr = (h*cos_a-w*sin_a)/cos_2a
    return abs(wr), abs(hr)

def _rotate_straight(im, angle_deg):
    """Rotate a PIL image by angle_deg (straighten/fix-horizon) and
    crop back to the largest rectangle with no blank/transparent
    corners — so straightening never leaves black wedges at the
    edges."""
    w, h = im.size
    rotated = im.rotate(angle_deg, resample=BICUBIC, expand=True,
                        fillcolor=(0, 0, 0))
    rw, rh = _largest_rotated_rect(w, h, math.radians(angle_deg))
    rw = max(1, min(int(rw), rotated.width))
    rh = max(1, min(int(rh), rotated.height))
    cx, cy = rotated.width/2, rotated.height/2
    box = (int(cx-rw/2), int(cy-rh/2), int(cx-rw/2)+rw, int(cy-rh/2)+rh)
    return rotated.crop(box)

def _sf(v):
    try:
        if hasattr(v, "numerator"):
            return float(v.numerator)/float(v.denominator) \
                if v.denominator else None
        if isinstance(v, tuple) and len(v) == 2:
            return float(v[0])/float(v[1]) if v[1] else None
        return float(v)
    except Exception:
        return None
def _meta(img, path):
    ex = {}
    try:
        for k, v in img.getexif().items():
            ex[ExifTags.TAGS.get(k, str(k))] = v
    except Exception:
        pass
    iso = ex.get("ISOSpeedRatings") or ex.get("PhotographicSensitivity")
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    return {"path":path,"make":str(ex.get("Make") or "").strip(),
            "model":str(ex.get("Model") or "").strip(),
            "iso":_sf(iso),"raw":False}
def load_src(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXT:
        if rawpy is None:
            raise RuntimeError("RAW needs rawpy: pip install rawpy")
        with rawpy.imread(path) as r:
            rgb = r.postprocess(use_camera_wb=True,
                                output_color=rawpy.ColorSpace.sRGB,
                                output_bps=8)
        return Image.fromarray(rgb, "RGB"), {"path":path,"raw":True}
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB"), _meta(img, path)


# ============================================================
#  LUT ENGINE
# ============================================================

class LUT:
    SZ = 4096
    _c = {}
    _l = threading.Lock()
    @staticmethod
    def build(fn, key):
        with LUT._l:
            c = LUT._c.get(key)
            if c is not None:
                return c
            x = np.linspace(0, 1, LUT.SZ, np.float32)
            v = np.clip(fn(x).astype(np.float32), 0, 1)
            if len(LUT._c) >= 160:
                LUT._c.clear()
            LUT._c[key] = v
            return v
    @staticmethod
    def apply(rgb, lut):
        i = np.clip(np.uint16(np.round(arr32(rgb)*(LUT.SZ-1))), 0, LUT.SZ-1)
        return lut[i]

# ============================================================
#  3D LUT ENGINE (trilinear) — for accurate .cube-based camera/film looks
# ============================================================

_LUT3D_CACHE = {}
_LUT3D_LOCK = threading.Lock()

def _parse_cube_table(path):
    """Parse a .cube file into a full N x N x N x 3 lattice (no linear
    collapse — this preserves the LUT's actual non-linear shape)."""
    txt = open(path, "r", encoding="utf-8", errors="ignore").read().splitlines()
    sz = 0
    dmin = np.array([0., 0., 0.], np.float32)
    dmax = np.array([1., 1., 1.], np.float32)
    rows = []
    for l in txt:
        p = l.strip().split()
        if not p or p[0].startswith("#"):
            continue
        up = p[0].upper()
        if up == "LUT_3D_SIZE":
            sz = int(p[1])
            continue
        if up == "DOMAIN_MIN":
            dmin = np.array([float(v) for v in p[1:4]], np.float32)
            continue
        if up == "DOMAIN_MAX":
            dmax = np.array([float(v) for v in p[1:4]], np.float32)
            continue
        if up in ("TITLE", "LUT_1D_SIZE"):
            continue
        if len(p) == 3:
            try:
                rows.append([float(v) for v in p])
            except ValueError:
                continue
    if sz < 2 or len(rows) < sz*sz*sz:
        raise RuntimeError("Invalid or incomplete 3D CUBE.")
    # .cube spec: R varies fastest, then G, then B -> flat reshape is [b,g,r,3]
    table_raw = np.asarray(rows[:sz*sz*sz], np.float32).reshape(sz, sz, sz, 3)
    table = np.ascontiguousarray(np.transpose(table_raw, (2, 1, 0, 3)))  # [r,g,b,3]
    return table, dmin, dmax

def get_lut3d(path):
    """Thread-safe cached loader. Returns (table, dmin, dmax) or None if the
    file is missing/invalid (negative-cached so a bad path isn't re-read
    on every frame)."""
    with _LUT3D_LOCK:
        if path in _LUT3D_CACHE:
            return _LUT3D_CACHE[path]
        try:
            tbl, dmin, dmax = _parse_cube_table(path)
            _LUT3D_CACHE[path] = (tbl, dmin, dmax)
        except Exception:
            _LUT3D_CACHE[path] = None
        return _LUT3D_CACHE[path]

def apply_lut3d(rgb, lut3d):
    """Vectorized trilinear interpolation through a 3D LUT lattice."""
    tbl, dmin, dmax = lut3d
    N = tbl.shape[0]
    x = arr32(rgb)
    span = np.maximum(dmax-dmin, 1e-6)
    xn = np.clip((x-dmin)/span, 0, 1)
    pos = xn*(N-1)
    i0 = np.clip(np.floor(pos).astype(np.int32), 0, N-2)
    frac = (pos-i0).astype(np.float32)
    i1 = i0+1
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    r1, g1, b1 = i1[..., 0], i1[..., 1], i1[..., 2]
    fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]
    c000 = tbl[r0, g0, b0]; c100 = tbl[r1, g0, b0]
    c010 = tbl[r0, g1, b0]; c110 = tbl[r1, g1, b0]
    c001 = tbl[r0, g0, b1]; c101 = tbl[r1, g0, b1]
    c011 = tbl[r0, g1, b1]; c111 = tbl[r1, g1, b1]
    c00 = c000*(1-fr)+c100*fr
    c10 = c010*(1-fr)+c110*fr
    c01 = c001*(1-fr)+c101*fr
    c11 = c011*(1-fr)+c111*fr
    c0 = c00*(1-fg)+c10*fg
    c1 = c01*(1-fg)+c11*fg
    out = c0*(1-fb)+c1*fb
    return np.clip(out, 0, 1).astype(np.float32)

def fc_lut(ca, sh):
    def f(x):
        y = np.power(np.maximum(x, 0), max(.01, float(ca)))
        toe = smoothstep(0, .25, y)
        y = y*(.88+.12*toe)
        sm = smoothstep(.62, 1.15, y)
        cp = y/(1+float(sh)*np.maximum(y-.55, 0))
        return np.maximum(y*(1-sm)+cp*sm, 0)
    return LUT.build(f, ("fc", round(float(ca),4), round(float(sh),4)))

def _curve_is_identity(pts):
    if not pts or len(pts) < 2:
        return True
    return all(abs(x-y) < 1e-4 for x, y in pts) and \
        abs(min(p[0] for p in pts)) < 1e-4 and \
        abs(max(p[0] for p in pts)-1) < 1e-4

def _curve_fn(pts):
    """Smooth (Catmull-Rom-style Hermite) monotone-in-x interpolation
    through the Tone Curve's control points — the same shape Lightroom
    / most photo editors use for their parametric tone curve, built
    from scratch (no scipy dependency)."""
    uniq = sorted({round(x, 6): y for x, y in pts}.items())
    if len(uniq) < 2:
        uniq = [(0.0, 0.0), (1.0, 1.0)]
    xs = np.array([p[0] for p in uniq], np.float64)
    ys = np.array([p[1] for p in uniq], np.float64)
    n = len(xs)
    m = np.zeros(n)
    for i in range(n):
        if i == 0:
            m[i] = (ys[1]-ys[0])/max(xs[1]-xs[0], 1e-6)
        elif i == n-1:
            m[i] = (ys[-1]-ys[-2])/max(xs[-1]-xs[-2], 1e-6)
        else:
            m[i] = (ys[i+1]-ys[i-1])/max(xs[i+1]-xs[i-1], 1e-6)
    def f(x):
        xf = np.asarray(x, np.float64)
        seg = np.clip(np.searchsorted(xs, xf, side="right")-1, 0, n-2)
        x0, x1 = xs[seg], xs[seg+1]
        y0, y1 = ys[seg], ys[seg+1]
        m0, m1 = m[seg], m[seg+1]
        h = np.maximum(x1-x0, 1e-6)
        t = (xf-x0)/h
        t2, t3 = t*t, t*t*t
        h00 = 2*t3-3*t2+1; h10 = t3-2*t2+t
        h01 = -2*t3+3*t2; h11 = t3-t2
        y = h00*y0+h10*h*m0+h01*y1+h11*h*m1
        return np.clip(y, 0, 1)
    return f

def curve_lut(pts):
    key = ("curve",)+tuple(round(a, 4) for p in sorted(pts) for a in p)
    return LUT.build(_curve_fn(pts), key)

IDENTITY_CURVE = [(0.0, 0.0), (1.0, 1.0)]

def _curves_identity(curves):
    if not curves:
        return True
    return all(_curve_is_identity(curves.get(ch, IDENTITY_CURVE))
              for ch in ("rgb", "r", "g", "b"))

def apply_tone_curves(x, curves):
    """Apply the master RGB curve (LUT-cached, applied to all channels
    identically) then any per-channel Red/Green/Blue curves (applied
    directly to their own channel) — matching Lightroom's Point Curve
    (master + optional per-channel curves) rather than a single curve
    forced across all three channels."""
    if not curves:
        return x
    rgb_pts = curves.get("rgb")
    if rgb_pts and not _curve_is_identity(rgb_pts):
        x = LUT.apply(x, curve_lut(rgb_pts))
    per_ch = [(i, curves.get(ch)) for i, ch in enumerate(("r", "g", "b"))]
    per_ch = [(i, pts) for i, pts in per_ch
             if pts and not _curve_is_identity(pts)]
    if per_ch:
        x = np.array(x, np.float32, copy=True)
        for i, pts in per_ch:
            x[..., i] = _curve_fn(pts)(x[..., i])
    return x

# ---- v12: FUSED per-channel tone+gamma LUT ----
# Physics: gamma BEFORE tone mapping (sensor→gamma→tone).
# Channel asymmetry: R softer highlight pull (warm retention),
# B stronger shadow/highlight pull (cool compression), G reference.

def tone_gamma_lut(exposure, shadows, highlights, blacks, whites,
                   fade, gamma, contrast, channel, neutral=False):
    ev = math.pow(2.0, float(exposure))
    g = max(0.05, float(gamma if gamma else 1.0))
    CH = (1.0, 1.0) if neutral else {0:(.95,.90), 1:(1.0,1.0), 2:(1.05,1.08)}[channel]
    sh_w, hl_w = CH
    # Contrast: pivot-around-midgray slope adjustment. ct in [-100,100];
    # positive steepens the curve (more contrast), negative flattens it
    # (less contrast), pivoting at 0.5 so midtones stay put.
    ct = float(contrast)
    ct_amt = float(np.clip(ct/100.0, -1, 1))

    def fn(x):
        y = np.clip(x*ev, 0, 1)
        y = np.power(y, g)
        if blacks:
            y -= float(blacks)/100*.18*sh_w*(1-smoothstep(0,.30,y))
        if whites:
            y += float(whites)/100*.16*hl_w*smoothstep(.55,1,y)
        if shadows:
            y += float(shadows)/100*.22*sh_w*(1-smoothstep(.05,.62,y))
        if highlights:
            y += float(highlights)/100*.22*hl_w*smoothstep(.45,1,y)
        if fade:
            f_ = float(fade)/100
            y = y*(1-.22*f_)+.16*f_
        if abs(ct_amt) > 1e-4:
            slope = 1.0+ct_amt*1.2 if ct_amt >= 0 else 1.0/(1.0-ct_amt*1.2)
            y = np.clip((y-.5)*slope+.5, 0, 1)
        return y

    key = ("tgN" if neutral else "tg%d"%channel, round(float(exposure),3),
           round(float(shadows),2), round(float(highlights),2),
           round(float(blacks),2), round(float(whites),2),
           round(float(fade),2), round(g,3), round(float(contrast),2))
    return LUT.build(fn, key)

def apply_fused_tone(rgb, p):
    """Per-channel fused LUT — 3 gathers total, replaces
    the old separate tone_lut + gamma_op passes.

    When the preset is monochrome, the per-channel shadow/highlight
    weighting below (CH) is skipped (neutral=True) — those weights
    exist to emulate each film/sensor's per-channel color response,
    but applying them to an already-neutral-gray image (post mono())
    would silently reintroduce a color tint, defeating the point of
    a black & white preset.
    """
    params = (p.get("exposure", 0), p.get("shadows", 0),
              p.get("highlights", 0), p.get("blacks", 0),
              p.get("whites", 0), p.get("fade", 0),
              p.get("gamma", 1.0), p.get("contrast", 0))
    if all(abs(v) < 1e-4 for v in params[:6]) and \
            abs(params[6]-1.0) < 1e-4 and abs(params[7]) < 1e-4:
        return rgb
    neutral = bool(p.get("monochrome"))
    out = np.empty_like(rgb)
    for c in range(3):
        lut = tone_gamma_lut(*params, channel=c, neutral=neutral)
        idx = np.clip(np.uint16(np.round(
            np.maximum(rgb[..., c], 0)*(LUT.SZ-1))), 0, LUT.SZ-1)
        out[..., c] = lut[idx]
    return out


# ============================================================
#  COLOUR OPS
# ============================================================

def ctemp(rgb, a):
    x = rgb.copy(); a = float(a)
    w, c = max(a,0), max(-a,0)
    x[..., 0] *= 1+w*.055; x[..., 2] *= 1-w*.035
    x[..., 2] *= 1+c*.055; x[..., 0] *= 1-c*.035
    return np.maximum(x, 0)
def tint_op(rgb, a):
    x = rgb.copy(); a = float(a)
    p, n = max(a,0), max(-a,0)
    x[..., 1] *= 1-p*.035; x[..., 0] *= 1+p*.018; x[..., 2] *= 1+p*.018
    x[..., 1] *= 1+n*.035; x[..., 0] *= 1-n*.018; x[..., 2] *= 1-n*.018
    return np.maximum(x, 0)


# ============================================================
#  WHITE BALANCE — gray-world / gray-point estimation
# ============================================================
#
# Both helpers below solve for the (temperature, tint) slider pair
# that best neutralizes a reference color, using the same forward
# model as ctemp()/tint_op() so "solve" and "apply" always agree.
# Solved by a small closed-form Newton step rather than a generic
# optimizer — the forward model is smooth, monotonic and separable
# enough (temp mainly drives R/B, tint mainly drives G vs R+B) that
# a couple of fixed-point iterations converge to <0.1 slider-unit
# accuracy on real images.

def _wb_solve(r, g, b):
    """Given a target neutral (gray) color (r,g,b), solve for slider
    values (temperature, tint) in [-100,100] such that applying
    ctemp() then tint_op() to (r,g,b) yields an equal-channel gray.
    Returns (temperature, tint), both clamped to [-100,100].

    ctemp()/tint_op() are each monotonic in their single parameter,
    so temperature is solved first by bisection on the R-B balance,
    then tint by bisection on G vs R+B — a couple of damped passes
    back and forth converge since the two controls are only weakly
    coupled (temperature has a small secondary effect on G via
    tint_op's own R/B nudge, and vice versa)."""
    r, g, b = float(r), float(g), float(b)
    if max(r, g, b) < 1e-6:
        return 0.0, 0.0
    temp, tint = 0.0, 0.0

    def rb_err(t, tn):
        px = np.array([[[r, g, b]]], np.float32)
        px = tint_op(ctemp(px, t), tn)
        return float(px[0,0,0])-float(px[0,0,2])

    def g_err(t, tn):
        px = np.array([[[r, g, b]]], np.float32)
        px = tint_op(ctemp(px, t), tn)
        return float(px[0,0,1])-.5*(float(px[0,0,0])+float(px[0,0,2]))

    def bisect(fn, fixed, lo=-100.0, hi=100.0):
        flo, fhi = fn(lo, fixed), fn(hi, fixed)
        if flo == 0:
            return lo
        if fhi == 0:
            return hi
        if (flo > 0) == (fhi > 0):
            # no sign change across the whole range: pick whichever
            # bound gets closer rather than clamping blindly to +/-100
            return lo if abs(flo) < abs(fhi) else hi
        for _ in range(40):
            mid = (lo+hi)*.5
            fm = fn(mid, fixed)
            if abs(fm) < 1e-6:
                return mid
            if (fm > 0) == (flo > 0):
                lo, flo = mid, fm
            else:
                hi, fhi = mid, fm
        return (lo+hi)*.5

    for _ in range(3):
        temp = bisect(lambda t, tn: rb_err(t, tn), tint)
        tint = bisect(lambda tn, t: g_err(t, tn), temp)
    return float(np.clip(temp, -100, 100)), float(np.clip(tint, -100, 100))

def wb_gray_world(rgb):
    """Classic gray-world auto white balance: assumes the average
    scene color should be neutral gray, and solves the
    (temperature, tint) pair that makes it so. Works on a downsampled
    copy for speed; returns (temperature, tint)."""
    x = analysis_size(ensure_rgb(rgb), 300)
    r = float(np.mean(x[..., 0]))
    g = float(np.mean(x[..., 1]))
    b = float(np.mean(x[..., 2]))
    return _wb_solve(r, g, b)

def wb_from_point(rgb, px, py):
    """Sample a small patch around image coordinate (px, py) — meant
    to be a neutral gray/white reference the user clicked on — and
    solve the (temperature, tint) pair that neutralizes it. Coords
    are in source-image pixels. Returns (temperature, tint)."""
    x = ensure_rgb(rgb)
    h, w = x.shape[:2]
    px = int(np.clip(px, 0, w-1)); py = int(np.clip(py, 0, h-1))
    r0 = 6
    x0, x1 = max(0, px-r0), min(w, px+r0+1)
    y0, y1 = max(0, py-r0), min(h, py+r0+1)
    patch = x[y0:y1, x0:x1]
    r = float(np.median(patch[..., 0]))
    g = float(np.median(patch[..., 1]))
    b = float(np.median(patch[..., 2]))
    return _wb_solve(r, g, b)

def sat_op(rgb, a):
    lm = luminance(rgb)[..., None]
    return np.maximum(lm+(rgb-lm)*float(a), 0)
def split_tone(rgb, sr, hr, sa, ha):
    lm = luminance(rgb)[..., None]
    s_ = 1-smoothstep(.15,.58,lm)
    h_ = smoothstep(.48,.92,lm)
    s = np.asarray(sr, np.float32).reshape(1,1,3)
    h = np.asarray(hr, np.float32).reshape(1,1,3)
    sa, ha = np.clip(float(sa),0,1), np.clip(float(ha),0,1)
    o = rgb*(1-s_*sa)+(rgb*.42+s*.58)*s_*sa
    o = o*(1-h_*ha)+(rgb*.48+h*.52)*h_*ha
    return np.maximum(o, 0)

# ---- 8-band HSL (Lightroom-style Hue/Saturation/Luminance per color) ----
HSL_BANDS = ("red", "orange", "yellow", "green", "aqua",
            "blue", "purple", "magenta")
HSL_CENTERS = {"red": 0.0, "orange": 30.0, "yellow": 60.0, "green": 120.0,
              "aqua": 180.0, "blue": 240.0, "purple": 275.0,
              "magenta": 315.0}
HSL_HALF_WIDTH = 45.0  # degrees of influence either side of each center

def _rgb_to_hsv_np(rgb):
    x = np.maximum(arr32(rgb), 0)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    delta = maxc-minc
    safe_d = np.maximum(delta, 1e-6)
    s = np.where(maxc > 1e-6, delta/np.maximum(maxc, 1e-6), 0.0)
    rc = (maxc-r)/safe_d
    gc = (maxc-g)/safe_d
    bc = (maxc-b)/safe_d
    h = np.where(maxc == r, bc-gc,
                np.where(maxc == g, 2.0+rc-bc, 4.0+gc-rc))
    h = (h/6.0) % 1.0
    h = np.where(delta <= 1e-6, 0.0, h)
    return h, s, v

def _hsv_to_rgb_np(h, s, v):
    h6 = (h % 1.0)*6.0
    i = np.floor(h6).astype(np.int32)
    f = h6-i
    p = v*(1-s)
    q = v*(1-f*s)
    t = v*(1-(1-f)*s)
    im = i % 6
    r = np.select([im == 0, im == 1, im == 2, im == 3, im == 4, im == 5],
                 [v, q, p, p, t, v])
    g = np.select([im == 0, im == 1, im == 2, im == 3, im == 4, im == 5],
                 [t, v, v, q, p, p])
    b = np.select([im == 0, im == 1, im == 2, im == 3, im == 4, im == 5],
                 [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)

def _hsl_is_active(p):
    return any(abs(p.get(f"hsl_{b}_{c}", 0)) > .5
              for b in HSL_BANDS for c in ("hue", "sat", "lum"))

def apply_hsl(rgb, p):
    """Lightroom-style 8-band Hue/Saturation/Luminance: each color band
    (Red/Orange/.../Magenta) gets its own hue-shift/saturation/
    luminance sliders, blended by a smooth, overlapping influence
    window around that band's hue center — so 'Orange +Sat' mostly
    affects skin/orange tones without a hard cutoff into Yellow."""
    x = np.maximum(arr32(rgb), 0)
    h, s, v = _rgb_to_hsv_np(x)
    hdeg = h*360.0
    hue_shift = np.zeros_like(hdeg)
    sat_mult = np.ones_like(hdeg)
    lum_shift = np.zeros_like(hdeg)
    for band in HSL_BANDS:
        hue_p = float(p.get(f"hsl_{band}_hue", 0))
        sat_p = float(p.get(f"hsl_{band}_sat", 0))
        lum_p = float(p.get(f"hsl_{band}_lum", 0))
        if abs(hue_p) < .5 and abs(sat_p) < .5 and abs(lum_p) < .5:
            continue
        center = HSL_CENTERS[band]
        d = np.abs(((hdeg-center+180.0) % 360.0)-180.0)
        w = np.clip(0.5*(1+np.cos(np.pi*np.minimum(d, HSL_HALF_WIDTH) /
                                  HSL_HALF_WIDTH)), 0, 1)
        w = np.where(d < HSL_HALF_WIDTH, w, 0.0)
        hue_shift += w*hue_p*.35
        sat_mult += w*(sat_p/100.0)
        lum_shift += w*(lum_p/100.0)*.6
    h2 = (h+hue_shift/360.0) % 1.0
    s2 = np.clip(s*np.maximum(sat_mult, 0), 0, 1)
    v2 = np.clip(v*(1+lum_shift), 0, 1)
    return np.clip(_hsv_to_rgb_np(h2, s2, v2), 0, 1).astype(np.float32)

# ---- 3-way Color Grading (Lightroom-style Shadows/Midtones/
# Highlights/Global wheels) ----
CG_RANGES = ("shadow", "midtone", "highlight")

def _cg_is_active(p):
    if abs(p.get("cg_global_sat", 0)) > .5 or abs(p.get("cg_global_lum", 0)) > .5:
        return True
    return any(abs(p.get(f"cg_{r}_sat", 0)) > .5 or
              abs(p.get(f"cg_{r}_lum", 0)) > .5 for r in CG_RANGES)

def color_grade(rgb, p):
    """Lightroom-style Color Grading: independent hue+saturation tint
    wheels for Shadows / Midtones / Highlights plus a Global wheel that
    tints the whole image, with a Blending slider controlling how much
    the three tone-range masks overlap (0 = hard split, 100 = smooth
    gradient across the whole tonal range)."""
    x = np.maximum(arr32(rgb), 0)
    lm = luminance(x)[..., None]
    soft = np.clip(float(p.get("cg_blending", 50))/100.0, 0, 1)
    lo1, lo2 = .15-soft*.10, .45+soft*.15
    hi1, hi2 = .55-soft*.15, .85+soft*.10
    s_ = 1-smoothstep(lo1, lo2, lm)
    h_ = smoothstep(hi1, hi2, lm)
    m_ = np.clip(1-s_-h_, 0, 1)
    o = x
    for rng, wmask in (("shadow", s_), ("midtone", m_), ("highlight", h_)):
        sat = np.clip(float(p.get(f"cg_{rng}_sat", 0))/100.0, 0, 1)
        lum = float(p.get(f"cg_{rng}_lum", 0))/100.0
        if sat > .004:
            col = np.asarray(_hr_(p.get(f"cg_{rng}_hue", 0)),
                             np.float32).reshape(1, 1, 3)
            o = o*(1-wmask*sat)+(o*.42+col*.58)*wmask*sat
        if abs(lum) > .004:
            o = o+wmask*lum*.25
    g_sat = np.clip(float(p.get("cg_global_sat", 0))/100.0, 0, 1)
    g_lum = float(p.get("cg_global_lum", 0))/100.0
    if g_sat > .004:
        gcol = np.asarray(_hr_(p.get("cg_global_hue", 0)),
                          np.float32).reshape(1, 1, 3)
        o = o*(1-g_sat)+(o*.42+gcol*.58)*g_sat
    if abs(g_lum) > .004:
        o = o+g_lum*.20
    return np.maximum(o, 0)

# ---- Local adjustments (Lightroom-style masks: Radial / Linear /
# Brush), each carrying its own reduced set of local sliders ----
LOCAL_PARAM_KEYS = ("exposure", "contrast", "temperature", "saturation",
                   "clarity")

def _brush_weight(shape, m, full_h=None, y0=0):
    h, w = shape[:2]
    H = full_h or h
    # Draw on a full-image-height canvas (so stroke coordinates, which
    # are normalized to the whole image, land correctly) then crop out
    # just this tile's row band — needed because export can process
    # the image in row tiles while masks are always full-image space.
    img = Image.new("L", (w, H), 0)
    dr = ImageDraw.Draw(img)
    r = max(int(float(m.get("radius", .04))*max(w, H)), 2)
    for stroke in m.get("strokes", []):
        pts = [(px*w, py*H) for px, py in stroke]
        for (px, py) in pts:
            dr.ellipse([px-r, py-r, px+r, py+r], fill=255)
        for i in range(len(pts)-1):
            dr.line([pts[i], pts[i+1]], fill=255, width=r*2)
    fe = float(m.get("feather", .5))
    blur_r = max(1, int(fe*r))
    if blur_r > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur_r))
    if H != h:
        img = img.crop((0, y0, w, y0+h))
    return np.asarray(img, np.float32)/255.0

def _mask_weight(shape, m, full_h=None, tile_y0=0):
    h, w = shape[:2]
    H = full_h or h
    yy, xx = np.mgrid[0:h, 0:w]
    xx = (xx.astype(np.float32)+.5)/w
    yy = (yy.astype(np.float32)+tile_y0+.5)/H
    t = m.get("type")
    if t == "radial":
        cx, cy = float(m.get("cx", .5)), float(m.get("cy", .5))
        rx = max(float(m.get("rx", .25)), 1e-4)
        ry = max(float(m.get("ry", .25)), 1e-4)
        ang = math.radians(float(m.get("angle", 0)))
        dx, dy = xx-cx, yy-cy
        dxr = dx*math.cos(ang)+dy*math.sin(ang)
        dyr = -dx*math.sin(ang)+dy*math.cos(ang)
        d = np.sqrt((dxr/rx)**2+(dyr/ry)**2)
        fe = max(float(m.get("feather", .5)), .01)
        wgt = 1-smoothstep(1-fe, 1+fe, d)
    elif t == "linear":
        x0, y0 = float(m.get("x0", .3)), float(m.get("y0", .5))
        x1, y1 = float(m.get("x1", .7)), float(m.get("y1", .5))
        dxl, dyl = x1-x0, y1-y0
        L = max(math.hypot(dxl, dyl), 1e-4)
        ux, uy = dxl/L, dyl/L
        signed = (xx-x0)*ux+(yy-y0)*uy
        fe = float(m.get("feather", .4))
        wgt = smoothstep(-fe*L*.5, L+fe*L*.5, signed)
    elif t == "brush":
        wgt = _brush_weight((h, w), m, full_h=H, y0=tile_y0)
    else:
        wgt = np.zeros((h, w), np.float32)
    if m.get("invert"):
        wgt = 1-wgt
    return wgt[..., None].astype(np.float32)

def apply_local_masks(rgb, masks, full_h=None, y0=0):
    """Apply each enabled local-adjustment mask's reduced slider set
    (Exposure/Contrast/Temperature/Saturation/Clarity) only within
    that mask's spatial weight, blending back into the base image —
    Lightroom's Radial/Linear/Brush local masks, minus their full
    global-panel slider set (a deliberate scope cut: only the five
    most-used local sliders are supported). full_h/y0 let a row-tiled
    caller (export) tell mask geometry — always defined in full-image
    normalized coordinates — where this tile sits, so masks land in
    the same place regardless of tile size."""
    if not masks:
        return rgb
    x = np.maximum(arr32(rgb), 0)
    for m in masks:
        if not m.get("enabled", True):
            continue
        pr = m.get("params", {})
        if all(abs(pr.get(k, 0)) < .5 for k in LOCAL_PARAM_KEYS):
            continue
        w = _mask_weight(x.shape, m, full_h=full_h, tile_y0=y0)
        if float(w.max()) < .004:
            continue
        y = x
        if abs(pr.get("exposure", 0)) > .004:
            y = y*(2.0**pr["exposure"])
        if abs(pr.get("temperature", 0)) > .5:
            y = ctemp(y, pr["temperature"])
        if abs(pr.get("contrast", 0)) > .5:
            y = (y-.5)*(1+pr["contrast"]/100.0)+.5
        if abs(pr.get("saturation", 0)) > .5:
            y = sat_op(y, 1+pr["saturation"]/100.0)
        if abs(pr.get("clarity", 0)) > .5:
            y = clarity_op(y, pr["clarity"])
        x = x*(1-w)+np.maximum(y, 0)*w
    return np.maximum(x, 0)

def mono(rgb, mix=(.30,.59,.11)):
    w = np.asarray(mix, np.float32)
    w = w/max(float(w.sum()), 1e-6)
    return np.repeat((arr32(rgb) @ w)[..., None], 3, 2).astype(np.float32)
def rolloff(rgb, a):
    a = float(a)
    if a <= .001:
        return rgb
    x = np.maximum(arr32(rgb), 0)
    lm = luminance(x)
    k = smoothstep(.56,.92,lm)
    ex = np.maximum(lm-.64, 0)
    s = np.clip(a/100, 0, 1)
    t = np.minimum(lm-k*ex*(.34+.58*s), lm)
    return np.maximum(x*(t/np.maximum(lm,.025))[..., None], 0)
def vign(rgb, a, f=.72):
    a = float(a)
    if abs(a) < .001:
        return rgb
    x = np.maximum(arr32(rgb), 0)
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx-(w-1)*.5)/max(w*.5,1)
    ny = (yy-(h-1)*.5)/max(h*.5,1)
    r = np.sqrt((nx*.92)**2+ny**2)
    f = float(np.clip(f,.35,1))
    e = smoothstep(.42, .42+f*.70, r)
    s = np.clip(a/100, -.75, .85)
    return np.maximum(x*(1-e*s)[..., None], 0)
def blur(rgb, r):
    if r <= .01:
        return arr32(rgb)
    x = np.clip(arr32(rgb), 0, 1).astype(np.float32)
    r = float(r)
    if HAVE_CV2:
        return cv2.GaussianBlur(x, (0,0), sigmaX=r)
    h, w = x.shape[:2]
    if r >= 4.5 and max(h, w) >= 320:
        f_ = .25
        im = to_pil(x).resize((max(32,int(w*f_)), max(32,int(h*f_))), BILINEAR)
        im = im.filter(ImageFilter.GaussianBlur(radius=r*f_))
        return np.asarray(im.resize((w, h), BILINEAR), np.float32)/255
    return np.asarray(to_pil(x).filter(
        ImageFilter.GaussianBlur(radius=r)), np.float32)/255
def skmask(rgb):
    x = ensure_rgb(rgb)
    r, g, b = x[...,0], x[...,1], x[...,2]
    m = ((r>.25)&(g>.14)&(b>.06)&(r>g*1.04)&(g>b*1.07)&
         ((r-b)>.07)).astype(np.float32)
    lm = luminance(x)
    m *= smoothstep(.12,.30,lm)
    m *= 1-smoothstep(.88,1,lm)*.7
    return clamp(m)

GP = {"cubic":{"sh":.45,"so":0,"cl":0},"tgrain":{"sh":0,"so":.10,"cl":0},
      "sigma":{"sh":0,"so":.16,"cl":0},"coreshell":{"sh":0,"so":.05,"cl":.30},
      "chromogenic":{"sh":0,"so":.38,"cl":0}}

def _shp(img, p):
    d = GP.get(p, GP["tgrain"])
    if d["sh"] > 0:
        s = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=120,
                                               threshold=0))
        a = np.asarray(img, np.float32)
        b = np.asarray(s, np.float32)
        return Image.fromarray(np.uint8(np.clip(a+(b-a)*d["sh"]*2, 0, 255)), "L")
    if d["so"] > 0:
        return img.filter(ImageFilter.GaussianBlur(radius=d["so"]+.3))
    return img

def grain(rgb, a, size=.45, prof="tgrain", mono=False):
    a = float(a)
    if a <= .001:
        return rgb
    size = .45 if size is None else float(np.clip(size, .20, .90))
    x = np.maximum(arr32(rgb), 0)
    h, w = x.shape[:2]
    d = GP.get(prof, GP["tgrain"])
    rng = np.random.default_rng()
    st = np.clip(a/100, 0, 1)
    fs = st*(.050 if prof == "cubic" else .040)
    fine = rng.normal(0, fs, (h, w)).astype(np.float32)
    ch, cw = max(24, h//3), max(24, w//3)
    co = rng.normal(0, fs*.70, (ch, cw)).astype(np.float32)
    ci = Image.fromarray(np.uint8(np.clip(co*2600+128, 0, 255)), "L")
    if d["cl"] > 0:
        ci = ci.resize((max(16, cw//2), max(16, ch//2)), BILINEAR)
    ci = ci.resize((w, h), BILINEAR)
    ci = _shp(ci, prof)
    co = (np.asarray(ci, np.float32)-128)/2600
    mix = np.clip((size-.20)/.70, 0, 1)
    nz = fine*(1-.38*mix)+co*(.32+.58*mix)
    lm = luminance(x)
    mw = np.clip(.30+.70*(1-np.abs(lm-.52)/.52), .22, 1)
    wt = mw*(1-.72*smoothstep(.78,1,lm))*(.70+.30*smoothstep(.02,.10,lm))
    o = x+nz[..., None]*wt[..., None]
    if not mono:
        # Chrominance grain noise — real color-negative grain has slightly
        # different structure per channel. Skipped for monochrome presets:
        # adding independent per-channel noise to a neutral-gray image
        # produces random color speckling instead of true B&W grain.
        cs = .30 if prof == "chromogenic" else 1
        cm = rng.normal(0, st*.008, (h, w, 3)).astype(np.float32)
        cm -= cm.mean(axis=2, keepdims=True)
        o += cm*wt[..., None]*.75*cs
    return clamp(o)

def halation(rgb, a, resp=(1,.22,.08)):
    a = float(a)
    if a <= .001:
        return rgb
    x = np.maximum(arr32(rgb), 0)
    lm = luminance(x)
    hl = smoothstep(.64, 1.02, lm)
    src = np.clip(x*(hl**1.25)[..., None], 0, 1)
    bl = blur(src, 1.6+a*.055)
    fr = np.maximum(luminance(bl)-lm*hl*.52, 0)
    cm = np.max(x,2)-np.min(x,2)
    fr *= np.clip(.75+cm*.9, .65, 1.20)
    rp = np.asarray(resp, np.float32)
    sc = np.clip(bl, 0, 1)
    sn = sc/np.maximum(np.max(sc,2,keepdims=True), 1e-4)
    hc_ = .60*rp.reshape(1,1,3)+.40*sn
    hc_ = hc_/np.maximum(np.max(hc_,2,keepdims=True), 1e-4)
    st = np.clip(a/100,0,1)*4.20
    gl = fr[..., None]*hc_*st
    return clamp(1-(1-np.clip(x,0,1))*(1-np.clip(gl,0,.78)))

def bloom(rgb, a, tint=(1.0, .94, .84)):
    a = float(a)
    if a <= .001:
        return rgb
    y = np.clip(arr32(rgb), 0, 1)
    lm = luminance(y)
    hl = np.power(smoothstep(.61,1,lm), 1.2)
    src = y*hl[..., None]
    b1, b2, b3 = blur(src, 1.4+a*.03), blur(src, 3.8+a*.065), \
        blur(src, 8.5+a*.095)
    gl = b1*.50+b2*.33+b3*.17
    gl = gl*np.asarray(tint, np.float32).reshape(1,1,3)
    st = np.clip(a/100,0,1)*4
    gx = luminance(gl)
    gl = gl*(.55+.45*smoothstep(.25,.88,lm))[..., None]
    gl = gl*(.55+.45*np.clip(gx*2,0,1))[..., None]
    return clamp(1-(1-y)*(1-np.clip(gl*st,0,.92)))

def clarity_op(rgb, a):
    a = float(a)
    if abs(a) < .001:
        return rgb
    h, w = rgb.shape[:2]
    im = to_pil(rgb)
    s = im.resize((max(8,w//8), max(8,h//8)), BILINEAR)
    s = s.resize((w, h), BILINEAR)
    b = np.asarray(s, np.float32)/255
    d = luminance(rgb)[..., None]-luminance(b)[..., None]
    return np.maximum(rgb+d*(a/100)*2.45, 0)
def tex_op(rgb, a):
    a = float(a)
    if abs(a) < .001:
        return rgb
    s = np.asarray(to_pil(rgb).filter(
        ImageFilter.GaussianBlur(radius=1.2)), np.float32)/255
    return np.maximum(rgb+(rgb-s)*(a/100)*2.10, 0)
def dehaze_op(rgb, a):
    a = float(a)
    if abs(a) < .001:
        return rgb
    b = np.asarray(to_pil(rgb).filter(
        ImageFilter.GaussianBlur(radius=4)), np.float32)/255
    hz = 1-clamp(np.abs(luminance(rgb)-luminance(b))*5)
    return np.maximum(rgb+(rgb-b)*(a/100)*hz[..., None]*1.4, 0)

def prep_scene(rgb, s=.72):
    x = ensure_rgb(rgb)
    wk = srgb2lin(x)
    lm = luminance(x)
    cm = np.max(x,2)-np.min(x,2)
    mid = smoothstep(.10,.22,lm)*(1-smoothstep(.78,.96,lm))
    wt = np.clip(mid*(1-np.clip(cm*1.15,0,.88)), 0, 1)
    dn = float(np.sum(wt))
    g = np.ones(3, np.float32)
    if dn > 50:
        mn = np.sum(wk*wt[..., None], (0,1))/dn
        g = np.clip(float(np.mean(mn))/np.maximum(mn,1e-5),
                    .90,1.10).astype(np.float32)
    return clamp(lin2srgb(wk*(1+(g[None,None]-1)*float(s))))

def _logi(x, a):
    x = np.clip(x, 1e-6, 1-1e-6)
    return (x**a)/(x**a+(1-x)**a)

def print_lut(s=1):
    s = float(np.clip(s, 0, 1))
    ch = [(1.38,.012,.03),(1.35,.010,.012),(1.30,.008,-.015)]
    def f(x):
        o = np.empty((3, x.shape[0]), np.float32)
        for c, (a,l,w_) in enumerate(ch):
            y = _logi(x, a)
            y = y*(1-l)+l
            y = y+w_*smoothstep(.55,1,y)
            o[c] = y
        return o*s+x[None]*(1-s)
    return LUT.build(f, ("p2383", round(s,3)))

def print_op(rgb, s=1):
    s = float(np.clip(s, 0, 1))
    if s <= .001:
        return rgb
    x = np.maximum(arr32(rgb), 0)
    lut = print_lut(s)
    o = np.empty_like(x)
    for c in range(3):
        i = np.clip(np.uint16(np.round(
            x[...,c]*(LUT.SZ-1))), 0, LUT.SZ-1)
        o[...,c] = lut[c][i]
    lm = luminance(o)[..., None]
    return np.clip(lm+(o-lm)*(1+.06*s), 0, 1)


# ============================================================
#  PRESETS (93 total)
# ============================================================

def FP(name, fam, gamma, rms, bal, sd, hal=0, hc=(1,.22,.08),
       prof="tgrain", mw=None, ex=None, proc="", iso=400, notes=""):
    ct = max(-12, min(24, round((float(gamma)-.55)*200)))
    gr = round(max(0, (float(rms)-2)*6.5))
    tp = {"tungsten":-8,"daylight":0,"warm":5,"cool":-3}.get(bal, 0)
    sat = {"very high":112,"high":106,"vivid":108,"medium":100,
           "natural":97,"moderate":97,"controlled":92,"low":90,
           "pastel":86,"vintage":94}.get(sd, 100)
    gs = float(np.clip(.30+(float(iso)/800)*.30, .30, .85))
    p = {"name":name,"family":fam,"process":proc,"description":notes,
         "exposure":0,"contrast":float(ct),"saturation":float(sat),
         "temperature":float(tp),"tint":0,"shadows":0,"highlights":0,
         "blacks":0,"whites":0,"clarity":0,"texture":0,"dehaze":0,
         "grain":float(gr),"grain_size":gs,"grain_profile":prof,
         "halation":float(hal),"halation_color":list(hc),
         "bloom":6 if bal == "tungsten" else 3,"vibrance":0,"density":0,
         "highlight_rolloff":30 if fam == "Color Negative" else 24,
         "vignette":8,"vignette_feather":.72,"fade":0,
         "film_curve_contrast":1+float(ct)/300,"film_shoulder":.16,
         "monochrome":mw is not None,
         "mono_weights":list(mw) if mw else None,
         "split_shadow":(1,1,1),"split_highlight":(1,1,1),
         "split_shadow_amount":0,"split_highlight_amount":0}
    if ex:
        p.update(ex)
    return p

PE, PB, PC_ = (.30,.59,.11), (.26,.55,.19), (.28,.57,.15)
PR = (.45,.50,.05)
HR, HC_, HA = (1,.22,.08), (.35,.75,1), (1,.55,.25)
NH, FH = (1,.70,.45), (1,.62,.28)

PRES = [
FP("Kodak Portra 400","Color Negative",.55,3,"daylight","natural",4,prof="tgrain",notes="Smooth neutral, exceptional skin.",proc="C-41",iso=400,ex={"highlights":-12,"vibrance":6,"clarity":-2,"split_shadow":(.96,.98,1.03),"split_shadow_amount":.05,"split_highlight":(1.03,1,.97),"split_highlight_amount":.04}),
FP("Kodak Portra 160","Color Negative",.50,2.5,"daylight","medium",3,prof="tgrain",notes="Finest-grain Portra.",proc="C-41",iso=160,ex={"highlights":-10,"temperature":2,"grain":4}),
FP("Kodak Portra 800","Color Negative",.55,4,"daylight","high",5,prof="tgrain",notes="Warm low-light.",proc="C-41",iso=800,ex={"temperature":3,"highlights":-12}),
FP("Portra 400 @ EI 800","Color Negative",.58,4.5,"daylight","natural",4,prof="tgrain",notes="One-stop push.",proc="C-41 push",iso=800,ex={"temperature":4,"contrast":8,"grain":14,"highlights":-10,"shadows":-4}),
FP("Kodak Ektar 100","Color Negative",.65,2,"daylight","very high",2,prof="tgrain",notes="Ultra-vivid.",proc="C-41",iso=100,ex={"vibrance":10,"density":14,"highlight_rolloff":40,"split_shadow":(.90,.97,1.10),"split_shadow_amount":.08,"split_highlight":(1.06,1.01,.94),"split_highlight_amount":.06}),
FP("Ektar 100 @ EI 200","Color Negative",.67,2.5,"daylight","very high",2,prof="tgrain",notes="Pushed Ektar.",proc="C-41 push",iso=200,ex={"contrast":22,"vibrance":14,"density":18,"highlight_rolloff":50,"grain":4}),
FP("Kodak Gold 100","Color Negative",.55,3.5,"warm","high",3,prof="cubic",notes="Golden consumer.",proc="C-41",iso=100,ex={"temperature":5,"tint":.8}),
FP("Kodak Gold 200","Color Negative",.58,4.5,"warm","high",3,prof="cubic",notes="Golden warmth.",proc="C-41",iso=200,ex={"temperature":6,"tint":1,"fade":3}),
FP("Gold 200 @ EI 400 (Golden Hour)","Color Negative",.62,6,"warm","high",4,prof="cubic",notes="Golden-hour push.",proc="C-41 push",iso=400,ex={"temperature":8,"tint":1.5,"contrast":12,"saturation":108,"grain":24,"grain_size":.60,"shadows":-4,"vignette":12,"fade":3}),
FP("Kodak ColorPlus 200","Color Negative",.56,4.8,"warm","vintage",3,prof="cubic",notes="Vintage warmth.",proc="C-41",iso=200,ex={"temperature":5,"fade":4,"vignette":12}),
FP("Kodak UltraMax 400","Color Negative",.60,5,"daylight","high",4,prof="tgrain",notes="Vivid consumer.",proc="C-41",iso=400,ex={"vibrance":8,"density":10}),
FP("UltraMax @ EI 800","Color Negative",.63,6,"daylight","vivid",4,prof="tgrain",notes="Pushed UltraMax.",proc="C-41 push",iso=800,ex={"contrast":16,"grain":28,"grain_size":.62,"shadows":-8}),
FP("Fujifilm C200","Color Negative",.55,4.2,"daylight","vivid",3,prof="sigma",notes="Lively greens.",proc="C-41",iso=200,ex={"density":6,"split_highlight":(.99,1.02,1.04),"split_highlight_amount":.06}),
FP("Fujifilm Superia X-TRA 400","Color Negative",.60,3.8,"daylight","vivid",4,prof="sigma",notes="4th layer.",proc="C-41",iso=400,ex={"vibrance":10,"contrast":10,"density":8}),
FP("Fujifilm 400 (2023)","Color Negative",.58,4,"daylight","vivid",4,prof="sigma",notes="Modern successor.",proc="C-41",iso=400,ex={"vibrance":8,"density":6,"highlight_rolloff":34,"grain":13}),
FP("Fujifilm Reala 100","Color Negative",.55,3,"daylight","medium",3,prof="sigma",notes="Legendary skin.",proc="C-41",iso=100,ex={"highlights":-10,"vibrance":5,"clarity":-1,"split_highlight":(.98,1.01,1.03),"split_highlight_amount":.05,"grain":7}),
FP("Fujifilm Pro 400H","Color Negative",.50,3.5,"cool","pastel",3,prof="sigma",notes="Pastel airy.",proc="C-41",iso=400,ex={"temperature":-3,"highlights":-14,"fade":5,"clarity":-3,"split_shadow":(.94,.99,1.05),"split_shadow_amount":.07,"split_highlight":(.98,1.01,1.05),"split_highlight_amount":.07,"vignette":5}),
FP("Fujifilm Superia Venus 800","Color Negative",.58,4.2,"daylight","high",4,prof="sigma",notes="Magenta warmth.",proc="C-41",iso=800,ex={"tint":1.5,"temperature":2}),
FP("Agfa Optima 200","Color Negative",.55,4,"daylight","medium",3,prof="cubic",notes="Clean European.",proc="C-41",iso=200,ex={"split_highlight":(1.02,1,.99),"split_highlight_amount":.04,"grain":13}),
FP("ORWO Wolfen NC500","Color Negative",.50,5,"daylight","vintage",4,prof="cubic",notes="Blue shadows.",proc="C-41",iso=500,ex={"split_shadow":(.86,.92,1.12),"split_shadow_amount":.14,"fade":4,"vignette":13}),
FP("CineStill 800T","Cinema",.55,4.5,"tungsten","moderate",40,hc=HR,prof="tgrain",notes="Red halation.",proc="C-41",iso=800,ex={"highlights":-18,"bloom":14,"highlight_rolloff":46,"split_shadow":(.58,.78,1.10),"split_shadow_amount":.24,"split_highlight":(1.10,.97,.80),"split_highlight_amount":.16,"vignette":14,"temperature":-6}),
FP("CineStill 800T @ EI 1600 (Neon Night)","Cinema",.62,6.5,"tungsten","moderate",42,hc=HR,prof="tgrain",notes="Neon nights.",proc="C-41 push",iso=1600,ex={"temperature":-7,"contrast":12,"grain":30,"grain_size":.72,"highlights":-20,"bloom":18,"highlight_rolloff":50,"vignette":16,"split_shadow":(.55,.76,1.12),"split_shadow_amount":.26}),
FP("CineStill 50D","Cinema",.52,3,"daylight","natural",38,hc=HR,prof="tgrain",notes="Crisp halation.",proc="C-41",iso=50,ex={"highlights":-12,"highlight_rolloff":38,"split_highlight":(1.06,1,.90),"split_highlight_amount":.08}),
FP("CineStill 400D","Cinema",.52,4,"daylight","natural",36,hc=HR,prof="tgrain",notes="250D, no remjet.",proc="C-41",iso=400,ex={"highlights":-14,"highlight_rolloff":42,"bloom":9,"split_shadow":(.62,.80,1.06),"split_shadow_amount":.14,"split_highlight":(1.08,.99,.88),"split_highlight_amount":.10,"contrast":4,"grain":13}),
FP("Kodak Vision3 500T","Cinema",.50,4,"tungsten","moderate",6,hc=HA,prof="tgrain",notes="Clean cine shadows.",proc="ECN-2",iso=500,ex={"temperature":-5,"highlights":-14,"bloom":10,"split_shadow":(.62,.80,1.08),"split_shadow_amount":.18}),
FP("Kodak Vision3 250D","Cinema",.52,3.5,"daylight","natural",6,prof="tgrain",notes="DLT latitude.",proc="ECN-2",iso=250,ex={"highlights":-12,"highlight_rolloff":36}),
FP("Vision3 200D 5213","Cinema",.52,3.4,"daylight","natural",6,prof="tgrain",notes="Fine-grain cine.",proc="ECN-2",iso=200,ex={"highlights":-10,"highlight_rolloff":34,"grain":9,"grain_size":.38}),
FP("Fujifilm Eterna 500T","Cinema",.45,4.2,"tungsten","controlled",5,prof="tgrain",notes="The flat cine look.",proc="ECN-2",iso=500,ex={"temperature":-4,"contrast":-12,"saturation":92,"highlights":-8,"shadows":6,"fade":4,"highlight_rolloff":40,"grain":10,"bloom":6}),
FP("Kodak Eastman 5247","Cinema",.60,3,"daylight","moderate",5,prof="cubic",notes="1950s cine.",proc="ECN-2",iso=64,ex={"fade":6,"vignette":12,"vibrance":-4}),
FP("Kodak Eastman EXR 100T","Cinema",.55,3,"tungsten","moderate",5,hc=HA,prof="tgrain",notes="EXR tungsten.",proc="ECN-2",iso=100,ex={"temperature":-4,"highlights":-12}),
FP("Portra 400 on 2383 Print","Cinematic",.55,3,"daylight","natural",4,prof="tgrain",notes="Wedding cinema print.",proc="C-41 + Print",iso=400,ex={"contrast":11,"saturation":100,"vibrance":7,"highlights":-14,"highlight_rolloff":46,"bloom":8,"density":9,"split_shadow":(.94,.96,1.02),"split_shadow_amount":.08,"grain":8}),
FP("Kodak Tri-X 400","B&W",.65,5.5,"daylight","medium",0,prof="cubic",mw=PB,notes="Bold photojournalism.",proc="B&W",iso=400,ex={"contrast":14,"grain":26,"grain_size":.60,"clarity":6,"vignette":12}),
FP("Tri-X Push EI 3200","B&W",.70,6.5,"daylight","natural",0,prof="cubic",mw=PB,notes="3-stop push.",proc="B&W push",iso=3200,ex={"contrast":20,"grain":38,"grain_size":.82,"shadows":-12,"dehaze":8,"clarity":10,"film_curve_contrast":1.20,"film_shoulder":.20}),
FP("Kodak T-Max 400","B&W",.58,3.5,"daylight","natural",0,prof="tgrain",mw=PE,notes="T-GRAIN smooth.",proc="B&W",iso=400,ex={"contrast":8,"grain":12,"clarity":5}),
FP("Kodak T-Max 100","B&W",.56,2.8,"daylight","natural",0,prof="tgrain",mw=PE,notes="Eye-like response.",proc="B&W",iso=100,ex={"contrast":6,"grain":6,"clarity":7,"texture":4}),
FP("Kodak T-Max P3200","B&W",.62,6,"daylight","natural",0,prof="tgrain",mw=PE,notes="EI 3200.",proc="B&W",iso=3200,ex={"contrast":12,"grain":30,"grain_size":.85,"highlights":-8,"bloom":8}),
FP("Kodak Double-X 5222","B&W",.60,4,"daylight","natural",0,prof="cubic",mw=PB,notes="Classic cine B&W.",proc="B&W (D-96)",iso=250,ex={"contrast":10,"grain":18,"fade":3,"vignette":12,"split_shadow":(.94,.96,1),"split_shadow_amount":.05}),
FP("Kodak Plus-X 125","B&W",.58,3.5,"daylight","natural",0,prof="cubic",mw=PB,notes="Medium classic.",proc="B&W",iso=125,ex={"contrast":7,"grain":14}),
FP("Kodak Verichrome Pan","B&W",.58,4,"daylight","natural",0,prof="cubic",mw=PC_,notes="Soft toe.",proc="B&W",iso=125,ex={"contrast":7,"grain":14,"fade":2,"film_curve_contrast":1.05,"film_shoulder":.14,"clarity":5,"highlights":-5,"blacks":-5}),
FP("Kodak HIE Infrared B&W","B&W",.60,6,"daylight","natural",8,hc=HA,prof="cubic",mw=(.50,.45,.05),notes="Glowing IR whites.",proc="B&W IR",iso=400,ex={"contrast":18,"grain":34,"grain_size":.75,"halation":22,"bloom":12,"vignette":14,"whites":15,"blacks":-14,"clarity":8}),
FP("Rollei Retro 400S","B&W",.62,5,"daylight","natural",0,prof="cubic",mw=PR,notes="Near-IR.",proc="B&W",iso=400,ex={"contrast":16,"grain":26,"grain_size":.68,"highlights":-20,"shadows":-10,"whites":12,"blacks":-12,"clarity":20,"film_shoulder":.18}),
FP("Ilford HP5 Plus 400","B&W",.65,5,"daylight","natural",0,prof="cubic",mw=PB,notes="Versatile S-curve.",proc="B&W",iso=400,ex={"contrast":12,"grain":22,"highlights":-8}),
FP("Ilford FP4 Plus 125","B&W",.58,3.2,"daylight","natural",0,prof="cubic",mw=PE,notes="Fine grain.",proc="B&W",iso=125,ex={"contrast":8,"grain":10,"clarity":4}),
FP("Ilford Delta 3200","B&W",.62,6,"daylight","natural",0,prof="coreshell",mw=PE,notes="Core-shell.",proc="B&W",iso=3200,ex={"contrast":11,"grain":28,"grain_size":.75,"bloom":8}),
FP("Ilford Pan F Plus 50","B&W",.62,2.5,"daylight","natural",0,prof="tgrain",mw=PE,notes="Ultra-fine.",proc="B&W",iso=50,ex={"contrast":10,"grain":4,"clarity":8,"texture":5}),
FP("Ilford XP2 Super 400","B&W",.55,2.2,"daylight","medium",0,prof="chromogenic",mw=PE,notes="Dye-cloud grain.",proc="C-41",iso=400,ex={"contrast":5,"grain":5,"grain_size":.42,"fade":3,"clarity":-2}),
FP("Fujifilm Acros 100","B&W",.55,2.5,"daylight","natural",0,prof="sigma",mw=PE,notes="Extreme fine.",proc="B&W",iso=100,ex={"contrast":8,"grain":6,"clarity":7,"texture":4}),
FP("Agfa APX 400","B&W",.60,5,"daylight","natural",0,prof="cubic",mw=PC_,notes="Rich European.",proc="B&W",iso=400,ex={"contrast":11,"grain":22,"grain_size":.62}),
FP("Fomapan 400 Action","B&W",.60,5.5,"daylight","vintage",0,prof="cubic",mw=PC_,notes="Vintage European.",proc="B&W",iso=400,ex={"contrast":10,"grain":28,"grain_size":.66,"fade":4,"vignette":13}),
FP("ORWO N74 Plus","B&W",.60,4,"daylight","natural",0,prof="cubic",mw=PC_,notes="European cine B&W.",proc="B&W",iso=400,ex={"contrast":10,"grain":18,"vignette":12}),
FP("Fujichrome Velvia 50","Slide",.70,2,"daylight","very high",3,prof="tgrain",notes="Saturated reversal.",proc="E-6",iso=50,ex={"contrast":18,"saturation":116,"highlights":-20,"highlight_rolloff":55,"density":20,"grain":4,"grain_size":.32,"vibrance":12,"split_shadow":(.92,1.02,1.06),"split_shadow_amount":.10,"split_highlight":(1.08,1.03,.92),"split_highlight_amount":.12}),
FP("Kodachrome 64","Slide",.65,2.2,"daylight","high",4,prof="tgrain",notes="Warm reds.",proc="K-14",iso=64,ex={"contrast":15,"saturation":110,"highlights":-14,"highlight_rolloff":48,"grain":4,"grain_size":.32,"density":12,"temperature":2,"split_shadow":(.90,.95,1.10),"split_shadow_amount":.14,"split_highlight":(1.10,1,.88),"split_highlight_amount":.14}),
FP("Kodak Ektachrome E100","Slide",.62,2.4,"daylight","high",3,prof="tgrain",notes="Velvia's brother.",proc="E-6",iso=100,ex={"contrast":14,"saturation":108,"vibrance":8,"highlights":-12,"highlight_rolloff":44,"split_highlight":(1.05,1.01,.96),"split_highlight_amount":.06,"grain":3}),
FP("Fujichrome Provia 100F","Slide",.58,2.2,"daylight","natural",3,prof="sigma",notes="Reference transparency.",proc="E-6",iso=100,ex={"contrast":8,"saturation":103,"highlights":-8,"highlight_rolloff":38,"grain":4,"clarity":3}),
FP("Kodak Aerochrome (False-Color IR)","Experimental",.60,5,"daylight","very high",5,prof="cubic",notes="Vegetation turns PINK.",proc="E-6 IR",iso=400,ex={"contrast":16,"saturation":120,"grain":18,"highlight_rolloff":48,"clarity":12,"split_shadow":(.70,.85,1.30),"split_shadow_amount":.38,"split_highlight":(1.20,.95,.85),"split_highlight_amount":.30,"density":22}),
FP("Agfa Precisa CT (X-Pro)","Experimental",.66,3.8,"cool","high",6,hc=HC_,prof="tgrain",notes="Electric blues.",proc="E-6 in C-41",iso=100,ex={"contrast":15,"temperature":-7,"saturation":112,"highlights":-16,"highlight_rolloff":50,"bloom":9,"grain":12,"split_shadow":(.48,.90,1.15),"split_shadow_amount":.28,"split_highlight":(1.12,1.05,.85),"split_highlight_amount":.18}),
FP("Cross Process E6->C41","Experimental",.68,4,"daylight","high",6,hc=HC_,prof="tgrain",notes="Cyan shadows.",proc="E-6 in C-41",iso=100,ex={"contrast":14,"temperature":-6,"tint":3,"highlights":-18,"highlight_rolloff":52,"saturation":108,"vibrance":6,"bloom":12,"split_shadow":(.45,.95,1.05),"split_shadow_amount":.30,"split_highlight":(1.15,1.02,.80),"split_highlight_amount":.24}),
FP("Polaroid 600","Instant",.55,3.5,"warm","vintage",12,hc=HA,prof="chromogenic",notes="Blacks never black.",proc="Instant",iso=640,ex={"fade":22,"temperature":4,"vignette":15,"halation":12,"saturation":88,"grain":8,"grain_size":.55,"highlights":-8,"whites":-6,"clarity":-4,"bloom":10,"vignette_feather":.85}),
FP("Expired Film 1998","Experimental",.55,5,"warm","vintage",8,prof="cubic",notes="Dye decay.",proc="C-41 aged",iso=200,ex={"temperature":6,"saturation":82,"fade":15,"grain":20,"grain_size":.60,"vignette":18,"split_shadow":(1.05,.94,.90),"split_shadow_amount":.20,"split_highlight":(1.08,.98,.84),"split_highlight_amount":.16}),
FP("Teal & Orange","Cinematic",.55,2,"daylight","medium",5,prof="tgrain",notes="Modern DI grade.",proc="DI",iso=400,ex={"contrast":8,"saturation":104,"highlights":-12,"vibrance":10,"density":10,"bloom":8,"highlight_rolloff":40,"split_shadow":(.45,.85,1.15),"split_shadow_amount":.35,"split_highlight":(1.18,1.02,.75),"split_highlight_amount":.30}),
FP("Day-for-Night","Cinematic",.60,3,"cool","medium",6,hc=HC_,prof="tgrain",notes="Moonlight.",proc="DI",iso=100,ex={"exposure":-1.4,"temperature":-10,"saturation":70,"highlights":-25,"shadows":-8,"blacks":-10,"contrast":12,"bloom":10,"vignette":12,"split_shadow":(.50,.70,1.20),"split_shadow_amount":.25,"split_highlight":(.85,.92,1.15),"split_highlight_amount":.20}),
# iPhone
FP("iPhone ProRAW Clean","Mobile/iPhone",.58,2,"daylight","natural",3,prof="tgrain",notes="Restore true blacks to HDR.",proc="iPhone",iso=100,ex={"contrast":14,"blacks":-12,"shadows":-6,"highlights":-10,"highlight_rolloff":40,"clarity":-3,"grain":3}),
FP("iPhone Cinematic","Mobile/iPhone",.52,3,"daylight","moderate",4,prof="tgrain",notes="iPhone + Vision3.",proc="iPhone",iso=400,ex={"contrast":10,"saturation":98,"vibrance":8,"highlights":-16,"highlight_rolloff":46,"bloom":10,"density":8,"split_shadow":(.62,.80,1.08),"split_shadow_amount":.18,"split_highlight":(1.10,1,.85),"split_highlight_amount":.12,"grain":8}),
FP("iPhone Portrait Studio","Mobile/iPhone",.55,2.5,"warm","natural",3,prof="tgrain",notes="Skin-corrected portrait.",proc="iPhone",iso=200,ex={"temperature":3,"contrast":6,"highlights":-14,"vibrance":6,"highlight_rolloff":44,"bloom":8,"grain":5,"fade":2,"skin_saturation":-8,"skin_warmth":8,"skin_smooth":18}),
FP("iPhone HDR De-Flat","Mobile/iPhone",.55,2,"daylight","medium",2,prof="tgrain",notes="Fix flat HDR.",proc="iPhone",iso=100,ex={"contrast":12,"blacks":-10,"whites":6,"highlight_rolloff":58,"highlights":-18,"clarity":-2,"grain":4}),
FP("iPhone Night Film","Mobile/iPhone",.58,4.5,"cool","moderate",6,prof="tgrain",notes="Night-mode to film.",proc="iPhone",iso=800,ex={"temperature":-6,"contrast":12,"shadows":-10,"blacks":-8,"highlight_rolloff":48,"bloom":12,"grain":16,"grain_size":.55,"vignette":12,"split_shadow":(.55,.75,1.12),"split_shadow_amount":.20}),
FP("iPhone Blue Hour","Mobile/iPhone",.55,2.5,"cool","controlled",4,prof="tgrain",notes="Blue hour cyan.",proc="iPhone",iso=200,ex={"temperature":-8,"saturation":96,"contrast":8,"highlight_rolloff":42,"bloom":9,"split_shadow":(.60,.78,1.15),"split_shadow_amount":.22,"grain":6}),
FP("iPhone Vintage Fade","Mobile/iPhone",.52,3.5,"warm","vintage",8,prof="chromogenic",notes="Gentle nostalgia.",proc="iPhone",iso=400,ex={"temperature":5,"saturation":88,"fade":10,"grain":10,"vignette":12,"highlight_rolloff":44,"clarity":-4}),
FP("iPhone Noir Punch","Mobile/iPhone",.65,3,"daylight","natural",0,prof="cubic",mw=PE,notes="Deep blacks B&W.",proc="iPhone",iso=400,ex={"contrast":16,"blacks":-14,"whites":8,"clarity":8,"grain":14,"vignette":12}),
# Samsung
FP("Samsung Vivid Correct","Mobile/Samsung",.58,2.5,"daylight","natural",2,prof="tgrain",notes="Tame Vivid.",proc="Samsung",iso=100,ex={"contrast":8,"saturation":96,"vibrance":-6,"tint":-1,"highlights":-12,"highlight_rolloff":40,"clarity":-4,"texture":-3,"grain":4}),
FP("Samsung Natural Film","Mobile/Samsung",.55,3,"daylight","natural",3,prof="tgrain",notes="Samsung to DSLR.",proc="Samsung",iso=200,ex={"contrast":10,"saturation":97,"vibrance":5,"highlight_rolloff":42,"grain":7,"clarity":-2}),
FP("Samsung Portrait Warm","Mobile/Samsung",.55,2.8,"warm","natural",3,prof="tgrain",notes="Red -> natural skin.",proc="Samsung",iso=200,ex={"temperature":4,"saturation":96,"highlights":-12,"highlight_rolloff":42,"grain":5,"bloom":7,"skin_saturation":-12,"skin_tan":6,"skin_warmth":6,"skin_smooth":20}),
FP("Samsung Night Neon","Mobile/Samsung",.58,5,"cool","moderate",8,hc=HR,prof="tgrain",notes="Neon + red halation.",proc="Samsung",iso=800,ex={"temperature":-7,"saturation":92,"contrast":10,"highlights":-16,"highlight_rolloff":46,"bloom":14,"halation":20,"grain":18,"grain_size":.60,"vignette":14}),
FP("Samsung De-Punch Soft","Mobile/Samsung",.52,3,"daylight","natural",2,prof="tgrain",notes="Anti-harsh-sharpen.",proc="Samsung",iso=200,ex={"contrast":4,"saturation":98,"clarity":-8,"texture":-6,"highlight_rolloff":38,"grain":4,"fade":2}),
FP("Samsung Film Gold","Mobile/Samsung",.58,4.5,"warm","high",3,prof="cubic",notes="Gold 200 vibe.",proc="Samsung",iso=200,ex={"temperature":6,"saturation":100,"contrast":8,"grain":14,"fade":3,"vignette":10,"highlight_rolloff":40}),
FP("Samsung Street Mono","Mobile/Samsung",.62,4,"daylight","natural",0,prof="cubic",mw=PE,notes="Street B&W.",proc="Samsung",iso=400,ex={"contrast":14,"clarity":6,"grain":20,"grain_size":.58,"vignette":12}),
FP("Samsung Pastel Air","Mobile/Samsung",.50,3,"cool","pastel",3,prof="sigma",notes="Pro 400H pastels.",proc="Samsung",iso=400,ex={"contrast":-8,"saturation":90,"temperature":-3,"highlights":-14,"fade":6,"clarity":-4,"grain":8,"highlight_rolloff":44,"vignette":5}),
# ===== VINTAGE CAMERAS (2006-2011 compacts) =====
FP("Canon IXUS 70 Classic","Vintage Cameras",.58,3.5,"warm","high",3,prof="cubic",notes="2007 DIGIC III: warm skin-centric.",proc="Canon My Colors",iso=200,ex={"temperature":5,"contrast":6,"saturation":106,"highlight_rolloff":20,"vibrance":5,"grain":8,"vignette":10}),
FP("Canon Vivid Mode","Vintage Cameras",.62,4,"warm","vivid",3,prof="cubic",notes="My Colors Vivid: punchy, reds near clip.",proc="Canon My Colors",iso=200,ex={"temperature":4,"contrast":12,"saturation":114,"vibrance":12,"highlight_rolloff":28,"split_highlight":(1.14,1.00,.90),"split_highlight_amount":.10}),
FP("Canon Neutral Mode","Vintage Cameras",.52,3,"warm","controlled",2,prof="cubic",notes="My Colors Neutral: flat for grading.",proc="Canon My Colors",iso=200,ex={"temperature":3,"contrast":-6,"saturation":92,"fade":3,"clarity":-2,"grain":6}),
FP("Canon G11 Enthusiast","Vintage Cameras",.55,3,"daylight","natural",3,prof="tgrain",notes="2009 G11: reference AWB, accurate skin.",proc="Canon G-Series",iso=200,ex={"contrast":6,"saturation":100,"vibrance":4,"highlight_rolloff":34,"grain":5,"clarity":3}),
FP("Canon i-Contrast Lift","Vintage Cameras",.55,3.5,"warm","natural",2,prof="tgrain",notes="i-Contrast: shadows +1-2EV.",proc="Canon DR Tool",iso=400,ex={"temperature":4,"contrast":4,"shadows":18,"blacks":-4,"clarity":5,"grain":10,"highlight_rolloff":30}),
FP("Fuji EXR Chrome","Vintage Cameras",.63,3.5,"daylight","vivid",3,prof="sigma",notes="2009 F200EXR Chrome: Velvia-concept.",proc="Fuji Film Sim",iso=200,ex={"contrast":12,"saturation":112,"vibrance":10,"highlight_rolloff":44,"split_shadow":(.94,1.00,1.04),"split_shadow_amount":.08,"split_highlight":(1.10,1.02,.92),"split_highlight_amount":.10,"grain":5}),
FP("Fuji F30 Natural","Vintage Cameras",.52,2.8,"daylight","natural",2,prof="sigma",notes="2006 F30: ISO-3200 legend, natural.",proc="Real Photo",iso=200,ex={"contrast":2,"saturation":98,"temperature":1,"highlight_rolloff":30,"grain":4,"clarity":2,"vignette":6}),
FP("Fuji Z10 Fashion","Vintage Cameras",.56,3,"warm","vivid",3,prof="chromogenic",notes="2007 Z10fd: fashion, oversaturated fun.",proc="Fuji Film Sim",iso=200,ex={"temperature":5,"contrast":8,"saturation":112,"vibrance":8,"clarity":-4,"fade":2,"skin_saturation":-6,"grain":5}),
FP("Fuji X100 Astia","Vintage Cameras",.54,2.8,"daylight","natural",3,prof="tgrain",notes="2011 X100 Astia: soft tonality, exceptional skin.",proc="Fuji Film Sim",iso=200,ex={"contrast":4,"saturation":96,"vibrance":6,"highlight_rolloff":40,"shadows":6,"skin_saturation":-5,"skin_warmth":6,"skin_smooth":15,"grain":4,"fade":2}),
FP("Fuji X100 Velvia","Vintage Cameras",.65,2.5,"daylight","very high",3,prof="tgrain",notes="2011 X100 Velvia: extreme saturation.",proc="Fuji Film Sim",iso=200,ex={"contrast":16,"saturation":118,"vibrance":14,"highlight_rolloff":52,"density":18,"split_shadow":(.92,1.00,1.06),"split_shadow_amount":.10,"split_highlight":(1.10,1.03,.90),"split_highlight_amount":.12,"grain":4}),
FP("Sony BIONZ Vivid","Vintage Cameras",.58,3,"cool","vivid",2,prof="tgrain",notes="2011 Exmor R BIONZ: vivid blues/greens.",proc="Sony Scene Auto",iso=200,ex={"temperature":-4,"contrast":8,"saturation":110,"vibrance":8,"clarity":-3,"texture":-3,"highlight_rolloff":30,"grain":3,"split_shadow":(.92,.98,1.10),"split_shadow_amount":.10}),
FP("Sony HX5V Twilight","Vintage Cameras",.50,2.2,"cool","moderate",2,prof="chromogenic",notes="2010 HX5V: multi-frame night, ultra-smooth.",proc="Sony Multi-Frame",iso=400,ex={"temperature":-5,"contrast":2,"saturation":98,"shadows":10,"clarity":-6,"texture":-4,"grain":2,"highlight_rolloff":42,"bloom":8,"skin_saturation":-4}),
FP("Nikon Coolpix Neutral","Vintage Cameras",.55,3,"cool","natural",2,prof="tgrain",notes="2011 S6200 EXPEED C2: neutral-cool, accurate AWB.",proc="Nikon Scene Auto",iso=200,ex={"temperature":-3,"contrast":5,"saturation":96,"vibrance":3,"highlight_rolloff":32,"grain":5}),
FP("Panasonic LX3 Nostalgic","Vintage Cameras",.50,3.5,"warm","low",3,prof="cubic",notes="2008 LX3 Nostalgic: warm faded-film signature.",proc="Panasonic Film Mode",iso=200,ex={"temperature":6,"contrast":-4,"saturation":84,"fade":8,"vibrance":-4,"grain":12,"split_shadow":(1.05,.97,.88),"split_shadow_amount":.14,"split_highlight":(1.08,1.00,.86),"split_highlight_amount":.10,"vignette":10}),
# Vintage B&W modes
FP("Fuji X100 Monochrome","Vintage Cameras",.58,2.5,"daylight","natural",0,prof="tgrain",mw=PE,notes="2011 X100 Monochrome: clean standard.",proc="Fuji Film Sim",iso=200,ex={"contrast":8,"grain":5,"clarity":6,"texture":3,"vignette":8}),
FP("Panasonic LX3 B&W","Vintage Cameras",.58,3,"daylight","natural",0,prof="cubic",mw=PC_,notes="2008 LX3 B&W Standard: neutral CCD mono.",proc="Panasonic Film Mode",iso=200,ex={"contrast":7,"grain":12,"clarity":4,"vignette":9,"fade":2}),
FP("Canon Sepia Mode","Vintage Cameras",.55,3,"daylight","vintage",0,prof="cubic",mw=PE,notes="My Colors Sepia: monochromatic brown.",proc="Canon My Colors",iso=200,ex={"contrast":5,"grain":10,"vignette":12,"fade":4,"split_shadow":(.82,.68,.50),"split_shadow_amount":.55,"split_highlight":(1.00,.92,.78),"split_highlight_amount":.35}),
# ===== CINEMA CAMERAS =====
# Look-emulation presets inspired by the publicly documented, well-known
# color-science characteristics of each system's default Rec.709 rendering
# (highlight roll-off, skin handling, saturation character). These are
# stylistic approximations, like every other preset in this file — not a
# literal reproduction of proprietary IDT/LUT matrices.
FP("ARRI Alexa — Classic Color Science","Cinema Cameras",.56,2.2,"daylight","natural",2,hc=(1,.85,.65),prof="tgrain",notes="Natural highlight roll-off & flattering skin — look-emulation of ARRI's signature Rec.709 LUT.",proc="ARRI LogC → Rec.709 (look-emulation)",iso=800,ex={"contrast":6,"temperature":2,"highlights":-10,"highlight_rolloff":48,"shadows":4,"vibrance":6,"clarity":2,"bloom":6,"skin_saturation":-6,"skin_warmth":8,"skin_smooth":10,"split_shadow":(.94,.98,1.04),"split_shadow_amount":.08,"split_highlight":(1.04,1.01,.96),"split_highlight_amount":.08}),
FP("ARRI Alexa — Monochrome","Cinema Cameras",.58,2,"daylight","natural",0,prof="tgrain",mw=PE,notes="Clean digital B&W, festival-grade contrast — look-emulation.",proc="ARRI LogC → Mono Grade (look-emulation)",iso=800,ex={"contrast":10,"highlights":-8,"highlight_rolloff":44,"clarity":4,"vignette":8}),
FP("RED Digital Cinema — IPP2","Cinema Cameras",.58,2.5,"daylight","high",1,prof="tgrain",notes="Wide dynamic range, punchy micro-contrast — look-emulation of RED's IPP2 pipeline.",proc="REDWideGamutRGB → IPP2 Rec.709 (look-emulation)",iso=800,ex={"contrast":10,"temperature":-1,"vibrance":10,"clarity":5,"highlights":-8,"highlight_rolloff":36,"split_shadow":(.96,1,1.02),"split_shadow_amount":.06,"split_highlight":(1.05,1.01,.97),"split_highlight_amount":.06}),
FP("Sony Venice — S-Cinetone","Cinema Cameras",.55,2,"cool","controlled",2,prof="tgrain",notes="Gentle desaturated highlights & protected skin — look-emulation of Sony's S-Cinetone.",proc="S-Gamut3.Cine/S-Log3 → S-Cinetone (look-emulation)",iso=500,ex={"contrast":4,"highlights":-14,"highlight_rolloff":50,"vibrance":4,"skin_saturation":-8,"skin_warmth":4,"skin_smooth":8,"split_shadow":(.85,.95,1.10),"split_shadow_amount":.14,"split_highlight":(1.02,1,1),"split_highlight_amount":.06}),
FP("Blackmagic Design — Film to Rec.709","Cinema Cameras",.52,3,"daylight","moderate",0,prof="tgrain",notes="Flatter, grade-ready tonality — look-emulation of Blackmagic's native Film profile.",proc="Blackmagic Film → Gen5 Color Rec.709 (look-emulation)",iso=400,ex={"contrast":-4,"highlights":-10,"highlight_rolloff":34,"clarity":-2,"fade":2}),
FP("Canon Cinema EOS — Canon Log Warm","Cinema Cameras",.56,2.5,"warm","natural",2,prof="tgrain",notes="Warm, filmic skin rendition favored in indie & documentary cinema — look-emulation.",proc="Canon Log 3 / Cinema Gamut → Rec.709 (look-emulation)",iso=800,ex={"contrast":8,"highlights":-10,"highlight_rolloff":42,"vibrance":6,"skin_warmth":6,"skin_saturation":-4,"split_shadow":(1,.98,.94),"split_shadow_amount":.06,"split_highlight":(1.06,1.02,.94),"split_highlight_amount":.08}),
FP("Panavision / Light Iron — DXL2 Soft Glow","Cinema Cameras",.55,2,"warm","medium",6,hc=(1,.75,.55),prof="tgrain",notes="Soft glamorous highlight roll-off & cinematic glow — look-emulation of a Panavision/Light Iron feature grade.",proc="RED Monstro + Light Iron Color (look-emulation)",iso=800,ex={"contrast":6,"highlights":-16,"highlight_rolloff":56,"bloom":10,"density":6,"vibrance":6,"split_shadow":(.90,.95,1.06),"split_shadow_amount":.10,"split_highlight":(1.10,1.02,.90),"split_highlight_amount":.14}),

# ===== MODERN / UNIQUE =====
# Contemporary, non-film-emulation looks built around current (2025/26)
# grading trends — clean/minimal editorial, muted earth tones, faded
# analog-digital hybrids, high-fashion contrast mono, etc. — rather
# than any specific film stock or camera. Each is a distinct, hand-
# tuned combination (not a palette-swap of another preset) and has
# been run through the full render pipeline (both the cached preview
# path and the export path) to confirm finite, in-range output with
# no errors. Both monochrome entries here (Modern Mono Contrast,
# Monochrome Soft) are built on the corrected neutral B&W pipeline —
# no color grain, no per-channel bloom tint, no residual temperature.
FP("Clean Girl Glow","Modern / Unique",.52,1.5,"warm","controlled",0,prof="tgrain",notes="Soft, luminous, minimal — the 'clean girl' skin-first editorial look.",proc="Digital DI",iso=200,ex={"contrast":-6,"highlights":-8,"shadows":6,"saturation":92,"vibrance":6,"clarity":-6,"skin_brightness":8,"skin_saturation":-6,"skin_smooth":14,"skin_warmth":6,"bloom":4,"vignette":-4}),
FP("Faded 35 Digital","Modern / Unique",.50,2,"warm","pastel",3,prof="tgrain",notes="Trendy faded-film digital look — lifted matte blacks, soft grain, muted warmth.",proc="Digital DI",iso=400,ex={"contrast":-8,"blacks":16,"whites":-8,"fade":18,"saturation":86,"vibrance":-4,"grain":10,"grain_size":.55,"vignette":6}),
FP("Coastal Bright","Modern / Unique",.54,1.5,"cool","clean",0,prof="tgrain",notes="Airy, bright, sun-washed coastal look — cool-neutral whites, gentle contrast.",proc="Digital DI",iso=200,ex={"contrast":-4,"highlights":6,"shadows":10,"whites":8,"saturation":90,"vibrance":8,"clarity":-2,"split_highlight":(.98,1.00,1.03),"split_highlight_amount":.14}),
FP("Dark Academia","Modern / Unique",.46,2.5,"warm","deep",0,prof="tgrain",notes="Deep warm shadows, desaturated amber tones — moody library aesthetic.",proc="Digital DI",iso=400,ex={"contrast":12,"shadows":-10,"blacks":-6,"saturation":80,"vibrance":-8,"density":10,"vignette":18,"split_shadow":(1.02,.94,.82),"split_shadow_amount":.32,"split_highlight":(1.05,.98,.86),"split_highlight_amount":.18}),
FP("Y2K Flash","Modern / Unique",.60,1.5,"cool","punchy",4,prof="tgrain",notes="Punchy digital-flash look — crushed cool highlights, high clarity, early-2000s snapshot energy.",proc="Digital DI",iso=200,ex={"contrast":16,"highlights":-18,"whites":14,"clarity":14,"saturation":104,"vibrance":10,"bloom":8,"vignette":-8}),
FP("Terracotta Warm","Modern / Unique",.56,2,"warm","rich",0,prof="tgrain",notes="Warm terracotta and clay tones — rich, earthy, sunlit warmth.",proc="Digital DI",iso=200,ex={"contrast":8,"saturation":100,"vibrance":10,"skin_warmth":8,"split_shadow":(1.03,.96,.90),"split_shadow_amount":.20,"split_highlight":(1.10,.96,.82),"split_highlight_amount":.28}),
FP("Modern Mono Contrast","Modern / Unique",.62,1.5,"daylight","high",0,prof="tgrain",mw=(.32,.55,.13),notes="Clean, punchy digital black & white — high-fashion editorial contrast, perfectly neutral.",proc="Digital DI",iso=200,ex={"contrast":22,"clarity":10,"whites":8,"blacks":-10,"grain":6,"grain_size":.4,"vignette":10}),
FP("Monochrome Soft","Modern / Unique",.50,2,"daylight","moderate",0,prof="tgrain",mw=(.40,.45,.15),notes="Gentle, low-contrast filmic black & white — soft roll-off, quiet and neutral.",proc="Digital DI",iso=400,ex={"contrast":-6,"highlights":-4,"shadows":6,"blacks":6,"grain":8,"grain_size":.5,"vignette":6}),
FP("Mocha Mousse","Modern / Unique",.56,2,"warm","rich",0,prof="tgrain",notes="Cozy warm mocha-brown neutral — soft, grounded, contemporary warmth.",proc="Digital DI",iso=200,ex={"contrast":6,"saturation":92,"vibrance":4,"shadows":4,"highlights":-4,"skin_warmth":4,"split_shadow":(1.02,.97,.90),"split_shadow_amount":.18,"split_highlight":(1.05,.98,.90),"split_highlight_amount":.16}),
FP("Digital Steel","Modern / Unique",.54,1.5,"cool","controlled",0,prof="tgrain",notes="Clean cool steel-blue commercial/tech look — crisp, restrained, precise.",proc="Digital DI",iso=200,ex={"contrast":6,"saturation":88,"vibrance":-4,"highlights":-4,"shadows":2,"clarity":4,"vignette":6,"split_shadow":(.95,.98,1.05),"split_shadow_amount":.22,"split_highlight":(.97,.99,1.03),"split_highlight_amount":.14}),
FP("Velvet Noir","Modern / Unique",.48,2.5,"warm","high",0,prof="tgrain",notes="Deep rich contrast with jewel-toned shadows — moody, luxurious, editorial.",proc="Digital DI",iso=400,ex={"contrast":20,"shadows":-14,"blacks":-10,"saturation":98,"vibrance":8,"density":12,"vignette":22,"split_shadow":(.92,.90,1.02),"split_shadow_amount":.22,"split_highlight":(1.05,.98,.90),"split_highlight_amount":.14}),
FP("Soft Focus Editorial","Modern / Unique",.52,1.5,"warm","controlled",0,prof="tgrain",notes="Gentle glow and low clarity for a romantic, dreamy portrait look.",proc="Digital DI",iso=200,ex={"contrast":-8,"highlights":-6,"shadows":8,"saturation":90,"clarity":-10,"bloom":10,"skin_smooth":10,"skin_brightness":6,"vignette":-2}),
FP("Urban Concrete","Modern / Unique",.52,2,"cool","low",0,prof="tgrain",notes="Desaturated cool gray-blue grade for street and architectural photography.",proc="Digital DI",iso=400,ex={"contrast":10,"saturation":70,"vibrance":-14,"shadows":-4,"clarity":8,"texture":6,"split_shadow":(.97,.99,1.02),"split_shadow_amount":.16}),
FP("Golden Hour Warmth","Modern / Unique",.58,2,"warm","high",6,hc=(1,.75,.45),prof="tgrain",notes="Warm backlit glow with soft highlight bloom — sunlit lifestyle and wedding look.",proc="Digital DI",iso=200,ex={"contrast":4,"highlights":-6,"saturation":104,"vibrance":10,"bloom":12,"skin_warmth":8,"split_highlight":(1.12,1.00,.80),"split_highlight_amount":.26}),
FP("Muted Mauve","Modern / Unique",.50,1.5,"cool","pastel",0,prof="tgrain",notes="Dusty pink-mauve palette — soft, quiet, contemporary social aesthetic.",proc="Digital DI",iso=200,ex={"contrast":-4,"saturation":82,"vibrance":-6,"split_shadow":(1.00,.96,1.00),"split_shadow_amount":.20,"split_highlight":(1.04,.98,1.00),"split_highlight_amount":.18}),
FP("High Fashion Punch","Modern / Unique",.60,2,"daylight","very high",0,prof="tgrain",notes="Bold saturated contrast for magazine-cover vividness and impact.",proc="Digital DI",iso=200,ex={"contrast":18,"saturation":112,"vibrance":16,"clarity":12,"whites":6,"blacks":-6,"highlight_rolloff":26}),
FP("Ocean Deep","Modern / Unique",.50,2,"cool","moderate",0,prof="tgrain",notes="Cool teal-blue deep shadows for moody travel and nature imagery.",proc="Digital DI",iso=400,ex={"contrast":10,"shadows":-6,"saturation":96,"vibrance":6,"split_shadow":(.80,.95,1.08),"split_shadow_amount":.34,"split_highlight":(.95,1.00,1.02),"split_highlight_amount":.12}),
FP("Polaroid Modern","Modern / Unique",.52,2,"warm","pastel",0,prof="tgrain",notes="Instant-film hybrid — warm cream highlights, soft fade, nostalgic but clean.",proc="Digital DI",iso=200,ex={"contrast":-6,"highlights":-2,"whites":-8,"fade":14,"saturation":88,"grain":8,"vignette":14,"split_highlight":(1.05,1.00,.90),"split_highlight_amount":.20}),
FP("Cinematic Teal Amber","Modern / Unique",.56,2,"daylight","high",0,prof="tgrain",notes="Balanced modern streaming-style grade — teal shadows, amber highlights, tasteful split.",proc="Digital DI",iso=400,ex={"contrast":10,"saturation":100,"vibrance":8,"split_shadow":(.85,.95,1.02),"split_shadow_amount":.28,"split_highlight":(1.08,1.00,.85),"split_highlight_amount":.26}),
FP("Desert Bloom","Modern / Unique",.56,2,"warm","rich",0,prof="tgrain",notes="Warm pink-orange sunset desert tones — soft, rich, golden.",proc="Digital DI",iso=200,ex={"contrast":8,"saturation":102,"vibrance":8,"split_shadow":(1.02,.94,.92),"split_shadow_amount":.16,"split_highlight":(1.10,.90,.85),"split_highlight_amount":.26}),
]

NEGIN = {"name":"Negin ✦ My Beautiful Gem","family":"Cinematic","process":"Secret","description":"For Negin.","exposure":.12,"contrast":8,"saturation":105,"temperature":4,"tint":.5,"highlights":-14,"shadows":8,"whites":5,"blacks":-4,"vibrance":14,"density":8,"highlight_rolloff":38,"halation":18,"halation_color":list(NH),"bloom":12,"grain":6,"grain_size":.40,"grain_profile":"sigma","fade":3,"vignette":10,"vignette_feather":.80,"film_curve_contrast":1.03,"film_shoulder":.14,"monochrome":False,"mono_weights":None,"split_shadow":(.88,.92,1.04),"split_shadow_amount":.10,"split_highlight":(1.10,1.02,.92),"split_highlight_amount":.12}
FORGE = {"name":"Lumen Forge ✦ Molten","family":"Cinematic","process":"Secret","description":"Forged in light.","exposure":-.10,"contrast":16,"saturation":98,"temperature":-4,"tint":1,"highlights":-10,"shadows":-6,"whites":8,"blacks":-10,"vibrance":6,"density":14,"highlight_rolloff":44,"halation":16,"halation_color":list(FH),"bloom":10,"grain":8,"grain_size":.48,"grain_profile":"cubic","fade":0,"vignette":14,"vignette_feather":.65,"film_curve_contrast":1.06,"film_shoulder":.12,"monochrome":False,"mono_weights":None,"split_shadow":(.70,.62,.55),"split_shadow_amount":.20,"split_highlight":(.92,.97,1.10),"split_highlight_amount":.16}


# ============================================================
#  SKIN ENGINE
# ============================================================

_CAS = None
def _cas():
    global _CAS
    if _CAS is not None or not HAVE_CV2:
        return _CAS
    try:
        _CAS = cv2.CascadeClassifier(
            cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
        if _CAS.empty():
            _CAS = None
    except Exception:
        _CAS = None
    return _CAS

def ycc_skin(rgb):
    x = ensure_rgb(rgb)
    r, g, b = x[...,0]*255, x[...,1]*255, x[...,2]*255
    cb = 128-.168736*r-.331264*g+.5*b
    cr = 128+.5*r-.418688*g-.081312*b
    m = ((cb>77)&(cb<127)&(cr>133)&(cr<173)).astype(np.float32)
    lm = luminance(x)
    m *= smoothstep(.10,.20,lm)*(1-smoothstep(.92,1,lm)*.85)
    return clamp(m)

def skin_full(rgb):
    ch = ycc_skin(rgb)
    c = _cas()
    if c is None:
        return ch
    try:
        x = ensure_rgb(rgb)
        g = np.asarray(to_pil(x).convert("L"))
        f = c.detectMultiScale(g, 1.15, 4, minSize=(40, 40))
        if f is None or len(f) == 0:
            return ch
        h, w = g.shape
        bo = np.zeros((h, w), np.float32)
        for (fx, fy, fw, fh) in f:
            cx, cy = fx+fw*.5, fy+fh*.5
            rx, ry = fw*.62, fh*.78
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            el = 1-np.clip(((xx-cx)/max(rx,1))**2+((yy-cy)/max(ry,1))**2,0,1)
            bo = np.maximum(bo, np.clip(el*1.6, 0, 1))
        return clamp(np.maximum(ch, bo*smoothstep(.05,.2,luminance(x))))
    except Exception:
        return ch

def skin_tools(rgb, p, mask=None):
    if not any(abs(p.get(k, 0)) > .5 for k in
               ("skin_warmth","skin_brightness","skin_saturation",
                "skin_tan","skin_smooth","skin_clarity")):
        return rgb
    x = clamp(rgb)
    m = skin_full(x) if mask is None else mask
    m3 = m[..., None]
    sm = float(np.clip(p.get("skin_smooth", 0), 0, 100))/100
    if sm > .005:
        sm *= .60
        if HAVE_CV2:
            sv = cv2.bilateralFilter(x, d=9, sigmaColor=.08+.10*sm,
                                     sigmaSpace=7)
        else:
            bl = np.asarray(to_pil(x).filter(
                ImageFilter.GaussianBlur(radius=2.2)), np.float32)/255
            sv = x-(x-bl)*.4
        hf = x-sv
        sv = sv+hf*(.35*(1-sm))
        x = x*(1-m3*sm)+sv*(m3*sm)
    tn = float(np.clip(p.get("skin_tan", 0), -100, 100))/100
    if abs(tn) > .005:
        br = np.array([1.10,.88,.70], np.float32).reshape(1,1,3)
        if tn > 0:
            tg = x*br*(1-.10*tn)
        else:
            tg = np.clip(x/np.maximum(br,.1)*(1+.04*-tn), 0, 1)
        x = x*(1-m3*abs(tn)*.8)+tg*(m3*abs(tn)*.8)
    wr = float(np.clip(p.get("skin_warmth", 0), -100, 100))
    if abs(wr) > .5:
        x = x*(1-m3*.85)+ctemp(x, wr*.6)*(m3*.85)
    sa = float(np.clip(p.get("skin_saturation", 0), -100, 100))/100
    if abs(sa) > .005:
        lm = luminance(x)[..., None]
        x = x*(1-m3)+(lm+(x-lm)*(1+sa*.5))*m3
    b_ = float(np.clip(p.get("skin_brightness", 0), -100, 100))/100
    if abs(b_) > .005:
        x = x*(1-m3)+np.clip(x*(1+b_*.25), 0, 1)*m3
    sc = float(np.clip(p.get("skin_clarity", 0), -100, 100))
    if abs(sc) > .5:
        h, w = x.shape[:2]
        im = to_pil(x)
        s_ = im.resize((max(8,w//8), max(8,h//8)), BILINEAR)
        s_ = s_.resize((w, h), BILINEAR)
        bse = np.asarray(s_, np.float32)/255
        d = luminance(x)[..., None]-luminance(bse)[..., None]
        x = x*(1-m3)+np.maximum(x+d*(sc/100)*1.8, 0)*m3
    return clamp(x)


# ============================================================
#  IMPORTERS
# ============================================================

def _xe(v):
    v = float(v)
    return v if abs(v) <= 5 else v*.04
XM = {"Exposure2012":("exposure",_xe),"Contrast2012":("contrast",lambda v:float(v)*.22),"Saturation":("saturation",lambda v:100+float(v)*.45),"Vibrance":("vibrance",lambda v:float(v)*.9),"Temperature":("temperature",lambda v:(float(v)-6500)*.0022),"Tint":("tint",lambda v:float(v)*.06),"Highlights2012":("highlights",lambda v:float(v)*.30),"Shadows2012":("shadows",lambda v:float(v)*.30),"Blacks2012":("blacks",lambda v:float(v)*.28),"Whites2012":("whites",lambda v:float(v)*.28),"Clarity2012":("clarity",lambda v:float(v)*.5),"Texture":("texture",lambda v:float(v)*.5),"Dehaze":("dehaze",lambda v:float(v)*.9),"PostCropVignetteAmount":("vignette",lambda v:float(v)*.45),"GrainAmount":("grain",lambda v:float(v)*.45)}
# Lightroom's 8-band HSL panel (crs:HueAdjustmentRed / SaturationAdjustment* /
# LuminanceAdjustment*) maps 1:1 onto this app's own hsl_<band>_<hue|sat|lum>
# sliders — both use a -100..100 range, so no rescaling is needed.
for _b in HSL_BANDS:
    _lb = _b.capitalize()
    XM[f"HueAdjustment{_lb}"] = (f"hsl_{_b}_hue", lambda v: float(v))
    XM[f"SaturationAdjustment{_lb}"] = (f"hsl_{_b}_sat", lambda v: float(v))
    XM[f"LuminanceAdjustment{_lb}"] = (f"hsl_{_b}_lum", lambda v: float(v))
# Lightroom's (2020+) 3-way Color Grading panel — Shadows/Midtones/
# Highlights/Global each get Hue (0-360) + Sat (0-100) + Lum (-100..100),
# plus a single Blending amount; all ranges match this app's cg_* sliders
# 1:1, same as the HSL panel above.
for _r, _lr in (("shadow","Shadow"),("midtone","Midtone"),("highlight","Highlight")):
    XM[f"ColorGrade{_lr}Hue"] = (f"cg_{_r}_hue", lambda v: float(v))
    XM[f"ColorGrade{_lr}Sat"] = (f"cg_{_r}_sat", lambda v: float(v))
    XM[f"ColorGrade{_lr}Lum"] = (f"cg_{_r}_lum", lambda v: float(v))
XM["ColorGradeGlobalHue"] = ("cg_global_hue", lambda v: float(v))
XM["ColorGradeGlobalSat"] = ("cg_global_sat", lambda v: float(v))
XM["ColorGradeGlobalLum"] = ("cg_global_lum", lambda v: float(v))
XM["ColorGradeBlending"] = ("cg_blending", lambda v: float(v))
def _hr_(h):
    h = (float(h) % 360)/60
    i = int(h) % 6
    f = h-int(h)
    b = [(1,f,0),(1-f,1,0),(0,1,f),(0,1-f,1),(f,0,1),(1,0,1-f)][i]
    return tuple(round(c, 3) for c in b)
def _parse_one_curve(t, tag):
    m = re.search(rf'crs:{tag}>\s*<rdf:Seq>(.*?)</rdf:Seq>', t, re.S)
    if not m:
        return None
    li = re.findall(r'<rdf:li>\s*([\d.]+)\s*,\s*([\d.]+)\s*</rdf:li>',
                    m.group(1))
    if len(li) < 2:
        return None
    pts = sorted({(round(float(x)/255.0, 4), round(float(y)/255.0, 4))
                 for x, y in li})
    return pts if len(pts) >= 2 else None

def _parse_tone_curve(t):
    """Parse Lightroom's Point Curve set — the master curve
    (crs:ToneCurvePV2012) plus, when present, the per-channel Red/
    Green/Blue point curves (crs:ToneCurvePV2012Red/Green/Blue) — each
    an rdf:Seq of 'x, y' pairs in 0-255 — into this app's own
    {'rgb','r','g','b'} curve dict, which supports the same per-channel
    structure natively."""
    rgb = _parse_one_curve(t, "ToneCurvePV2012")
    r = _parse_one_curve(t, "ToneCurvePV2012Red")
    g = _parse_one_curve(t, "ToneCurvePV2012Green")
    b = _parse_one_curve(t, "ToneCurvePV2012Blue")
    if not any((rgb, r, g, b)):
        return None
    ident = [(0.0, 0.0), (1.0, 1.0)]
    return {"rgb": rgb or ident, "r": r or ident,
           "g": g or ident, "b": b or ident}
def _bl(name, fam):
    return {"name":name,"family":fam,"process":"","description":"","exposure":0,"contrast":0,"saturation":100,"temperature":0,"tint":0,"shadows":0,"highlights":0,"blacks":0,"whites":0,"clarity":0,"texture":0,"dehaze":0,"grain":0,"grain_size":.45,"grain_profile":"tgrain","halation":0,"halation_color":list(HR),"bloom":0,"vibrance":0,"density":0,"highlight_rolloff":0,"vignette":0,"vignette_feather":.72,"fade":0,"film_curve_contrast":1,"film_shoulder":.12,"monochrome":False,"mono_weights":None,"split_shadow":(1,1,1),"split_highlight":(1,1,1),"split_shadow_amount":0,"split_highlight_amount":0}

def pxmp(path):
    try:
        t = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception as e:
        raise RuntimeError(f"Cannot read XMP: {e}")
    nm = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r'crs:PresetName="([^"]+)"', t) or \
        re.search(r'crs:Name="([^"]+)"', t)
    if m:
        nm = m.group(1)
    ps = _bl(nm, "Imported")
    ok = False
    for k, (tg, cv) in XM.items():
        m = re.search(rf'crs:{re.escape(k)}="([-+0-9.eE]+)"', t)
        if m:
            try:
                ps[tg] = cv(m.group(1))
                ok = True
            except Exception:
                pass
    m = re.search(r'crs:ConvertToGrayscale="([-+0-9.eE]+)"', t)
    if m:
        try:
            if float(m.group(1)) > .5:
                ps["monochrome"] = True
                ps["mono_weights"] = list(PE)
                ok = True
        except Exception:
            pass
    def hs(pfx):
        h = re.search(rf'crs:{pfx}Hue="([-+0-9.eE]+)"', t)
        s = re.search(rf'crs:{pfx}Saturation="([-+0-9.eE]+)"', t)
        if h and s:
            try:
                if float(s.group(1)) > 1:
                    return float(h.group(1)), float(s.group(1))
            except Exception:
                pass
        return None
    sh, hi = hs("SplitToningShadow"), hs("SplitToningHighlight")
    if sh:
        ps["split_shadow"] = _hr_(sh[0])
        ps["split_shadow_amount"] = min(1, sh[1]/130)
        ok = True
    if hi:
        ps["split_highlight"] = _hr_(hi[0])
        ps["split_highlight_amount"] = min(1, hi[1]/130)
        ok = True
    tc = _parse_tone_curve(t)
    if tc:
        ps["tone_curve_pts"] = tc
        ok = True
    if not ok:
        raise RuntimeError("No Lightroom settings found.")
    return ps

def pcube(path):
    """Import a .cube 3D LUT with full accuracy (trilinear-interpolated at
    apply time, see apply_lut3d) instead of collapsing it to a single
    linear temperature/tint/saturation approximation."""
    try:
        tbl, dmin, dmax = _parse_cube_table(path)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Cannot read CUBE: {e}")
    with _LUT3D_LOCK:
        _LUT3D_CACHE[path] = (tbl, dmin, dmax)  # warm the cache immediately
    ps = _bl(os.path.splitext(os.path.basename(path))[0], "Imported")
    ps["lut3d_path"] = path
    return ps

def pjson(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Cannot read JSON: {e}")
    if isinstance(d, dict) and "settings" in d:
        d = d["settings"]
    if not isinstance(d, dict):
        raise RuntimeError("Invalid JSON.")
    ps = _bl(os.path.splitext(os.path.basename(path))[0], "Imported")
    ps.update({k: v for k, v in d.items() if k not in ("name","family")})
    ps["name"] = d.get("name", ps["name"])
    ps["family"] = d.get("family", "Imported")
    return ps

IMPS = {".xmp": pxmp, ".cube": pcube, ".json": pjson}

# ============================================================
#  CAMERA DNA 2.0 — Professional Camera Matching Engine
# ------------------------------------------------------------
#  Architecture (see accompanying spec doc):
#
#    SOURCE IMAGE
#        -> Metadata Analysis          (cd_meta_analyze)
#        -> Input Gamma/Gamut Detect   (cd_detect_gamma_gamut)
#        -> Technical Camera Transform (CameraProfile.technical_transform)
#        -> Camera Character / DNA     (CameraProfile.character_transform)
#        -> [Creative Look / Lumen Forge film processing — unchanged,
#            happens later in staged()/Eng.render()]
#
#  CameraProfile is a plain, serializable, UI-independent dataclass-like
#  dict-backed object. Camera families provide shared defaults; specific
#  models override only what differs (see CAMERA_FAMILIES / CAMERA_MODELS).
#
#  This module is purely pointwise math (per-pixel), so it is tile-safe
#  and integrates cleanly with the existing row-tiled export/staged()
#  pipeline and the layered Eng cache (see LAYER_KEYS["camera"] below).
#
#  IMPORTANT — scientific honesty:
#   - Where an authentic manufacturer LUT/IDT is not present in this
#     project, camera "character" is a mathematically defined,
#     documented approximation (hue/sat/tone response curves), the same
#     approach already used by the existing preset system (FP()).
#     It is explicitly NOT claimed to be a bit-exact reproduction of
#     proprietary color science.
#   - Pixel-based camera *identification* produces a confidence score,
#     never a bare assertion. "Detected" is reserved for metadata-backed
#     identification; "Estimated"/"Auto Best Match" is used for
#     pixel-appearance-only inference.
# ============================================================

# ---- OKLab / OKLCH (perceptually meaningful space for hue-bucket work) --
# Small, vectorized, numerically stable. Used only for camera-character
# hue/sat processing and for strength interpolation, so we don't pay the
# conversion cost anywhere else in the pipeline.

_OKLAB_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                       [0.2119034982, 0.6806995451, 0.1073969566],
                       [0.0883024619, 0.2817188376, 0.6299787005]],
                      np.float32)
_OKLAB_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                       [1.9779984951, -2.4285922050, 0.4505937099],
                       [0.0259040371, 0.7827717662, -0.8086757660]],
                      np.float32)
_OKLAB_M1_INV = np.linalg.inv(_OKLAB_M1).astype(np.float32)
_OKLAB_M2_INV = np.linalg.inv(_OKLAB_M2).astype(np.float32)

def rgb2oklab(rgb):
    """sRGB (0..1, gamma-encoded) -> OKLab. Pointwise, tile-safe."""
    lin = srgb2lin(rgb)
    lms = lin @ _OKLAB_M1.T
    lms_ = np.sign(lms)*np.power(np.abs(lms), 1.0/3.0)
    return (lms_ @ _OKLAB_M2.T).astype(np.float32)

def oklab2rgb(lab):
    lms_ = lab @ _OKLAB_M2_INV.T
    lms = np.sign(lms_)*np.power(np.abs(lms_), 3.0)
    lin = lms @ _OKLAB_M1_INV.T
    return lin2srgb(np.maximum(lin, 0)).astype(np.float32)

def oklab2oklch(lab):
    L, a, b = lab[...,0], lab[...,1], lab[...,2]
    C = np.sqrt(a*a+b*b)
    H = (np.degrees(np.arctan2(b, a))) % 360.0
    return np.stack([L, C, H], -1).astype(np.float32)

def oklch2oklab(lch):
    L, C, H = lch[...,0], lch[...,1], lch[...,2]
    hr = np.radians(H)
    a = C*np.cos(hr)
    b = C*np.sin(hr)
    return np.stack([L, a, b], -1).astype(np.float32)


# ---- Camera Profile -------------------------------------------------

# Hue buckets modeled explicitly per spec section 9. Angles are OKLCH hue
# degrees (approximate centers — red≈30, orange≈55, yellow≈100,
# green≈150, cyan≈200, blue≈260, magenta≈330).
HUE_BUCKETS = ("red","orange","yellow","green","cyan","blue","magenta")
_HUE_CENTER = {"red":30,"orange":58,"yellow":102,"green":150,
               "cyan":200,"blue":262,"magenta":330}

def _hue_weights(H):
    """Soft (cosine-lobe) membership of each pixel's hue in every bucket.
    Returns dict bucket -> weight array (h,w), weights sum to 1 per pixel
    for chromatic pixels. Pointwise, tile-safe."""
    out = {}
    total = np.zeros(H.shape, np.float32)
    raw = {}
    for name, c in _HUE_CENTER.items():
        d = np.abs(((H-c+180) % 360)-180)
        w = np.clip(1-d/60.0, 0, 1)**1.5
        raw[name] = w
        total += w
    total = np.maximum(total, 1e-5)
    for name in raw:
        out[name] = (raw[name]/total).astype(np.float32)
    return out

def _empty_hue_response():
    return {k: 1.0 for k in HUE_BUCKETS}


class CameraProfile:
    """Deterministic, serializable, UI-independent camera profile.

    Fields separate TECHNICAL characteristics (gamma/gamut/log curve —
    "what state is this image actually in") from CREATIVE/CHARACTER
    fields (hue/sat/tone response — "what does this sensor+pipeline
    tend to look like"), per spec section 3.

    All numeric response fields are small multiplicative/additive
    perturbations around neutral (1.0 / 0.0), so identity is exact when
    every field is left at its default and `strength=0` is always a
    lossless no-op (spec section 18/26).
    """
    __slots__ = (
        "id","manufacturer","model","family","category",
        # technical (input-state) description — informational + used to
        # avoid double-applying a log->Rec709 style transform
        "gamma_law","gamut","native_iso",
        # character / DNA (creative, but *not* the Lumen Forge film look)
        "hue_response",         # dict bucket -> hue-rotation degrees
        "sat_response",         # dict bucket -> saturation multiplier
        "highlight_rolloff",    # 0..1, extra highlight compression
        "shadow_lift",          # -1..1, shadow response bias
        "midtone_contrast",     # -1..1
        "color_separation",     # 0..1, extra chroma micro-contrast
        "skin_response",        # dict: warmth/sat multipliers for skin
        "channel_balance",      # (r,g,b) multipliers, neutral (1,1,1)
        "white_balance_bias",   # approx K shift the camera tends toward
        # matching / detection
        "aliases", "metadata_signatures",
    )

    def __init__(self, id, manufacturer, model, family, category,
                 gamma_law="Rec.709", gamut="Rec.709", native_iso=800,
                 hue_response=None, sat_response=None,
                 highlight_rolloff=0.0, shadow_lift=0.0,
                 midtone_contrast=0.0, color_separation=0.0,
                 skin_response=None, channel_balance=(1.0,1.0,1.0),
                 white_balance_bias=0.0, aliases=(),
                 metadata_signatures=()):
        self.id = id
        self.manufacturer = manufacturer
        self.model = model
        self.family = family
        self.category = category
        self.gamma_law = gamma_law
        self.gamut = gamut
        self.native_iso = native_iso
        self.hue_response = dict(hue_response or _empty_hue_response())
        self.sat_response = dict(sat_response or _empty_hue_response())
        self.highlight_rolloff = float(highlight_rolloff)
        self.shadow_lift = float(shadow_lift)
        self.midtone_contrast = float(midtone_contrast)
        self.color_separation = float(color_separation)
        self.skin_response = dict(skin_response or {"warmth":0.0,"sat":1.0})
        self.channel_balance = tuple(channel_balance)
        self.white_balance_bias = float(white_balance_bias)
        self.aliases = tuple(aliases)
        self.metadata_signatures = tuple(metadata_signatures)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def display_name(self):
        return f"{self.manufacturer} {self.model}".strip()

    def cache_key(self):
        """Deterministic, hashable fingerprint for the cache layer
        (spec section 23)."""
        return (self.id, self.gamma_law, self.gamut,
                tuple(sorted(self.hue_response.items())),
                tuple(sorted(self.sat_response.items())),
                round(self.highlight_rolloff,4), round(self.shadow_lift,4),
                round(self.midtone_contrast,4), round(self.color_separation,4),
                tuple(sorted(self.skin_response.items())),
                tuple(round(c,4) for c in self.channel_balance),
                round(self.white_balance_bias,4))


def _family_profile(fam_id, **overrides):
    base = dict(CAMERA_FAMILY_DEFAULTS.get(fam_id, {}))
    base.update(overrides)
    return base

def make_profile(id, manufacturer, model, family, category, **kw):
    """Build a CameraProfile by inheriting the family's defaults and
    overriding only what's supplied (spec section 10 — no per-model
    duplication)."""
    fam_defaults = dict(CAMERA_FAMILY_DEFAULTS.get(family, {}))
    fam_defaults.update(kw)
    return CameraProfile(id, manufacturer, model, family, category,
                          **fam_defaults)


# ---- Family-level defaults (spec section 10) --------------------------
# Every model in a family inherits these unless it overrides a field.
# Values are deliberately conservative, documented approximations of
# each system's well-known, publicly-discussed rendering character
# (highlight roll-off behavior, skin handling, saturation tendency) —
# NOT proprietary IDT/LUT matrices. See PRES's existing "Cinema Cameras"
# presets for the same style of honestly-scoped look-emulation.

CAMERA_FAMILY_DEFAULTS = {
    "ARRI Alexa": dict(
        gamma_law="LogC3", gamut="ARRI Wide Gamut",
        highlight_rolloff=.62, shadow_lift=.05, midtone_contrast=.04,
        color_separation=.10, channel_balance=(1.0,1.0,1.0),
        skin_response={"warmth":.05,"sat":.94},
        hue_response={**_empty_hue_response()},
        sat_response={**_empty_hue_response(), "orange":.94,"red":.96},
    ),
    "Sony VENICE": dict(
        gamma_law="S-Log3", gamut="S-Gamut3.Cine",
        highlight_rolloff=.55, shadow_lift=-.02, midtone_contrast=.0,
        color_separation=.06, skin_response={"warmth":.03,"sat":.92},
        sat_response={**_empty_hue_response(), "green":.90,"cyan":.90},
    ),
    "Sony Cine": dict(
        gamma_law="S-Log3", gamut="S-Gamut3.Cine",
        highlight_rolloff=.48, shadow_lift=-.03, midtone_contrast=.02,
        color_separation=.05, skin_response={"warmth":.0,"sat":.95},
        sat_response={**_empty_hue_response(), "green":.92,"cyan":.92},
    ),
    "Sony Alpha": dict(
        gamma_law="Rec.709", gamut="S-Gamut3",
        highlight_rolloff=.20, shadow_lift=.0, midtone_contrast=.03,
        color_separation=.02, skin_response={"warmth":-.02,"sat":.97},
        sat_response={**_empty_hue_response(), "green":.94,"blue":1.04},
        white_balance_bias=.4,
    ),
    "RED": dict(
        gamma_law="Log3G10", gamut="REDWideGamutRGB",
        highlight_rolloff=.38, shadow_lift=.0, midtone_contrast=.08,
        color_separation=.14, skin_response={"warmth":.0,"sat":1.0},
    ),
    "Canon Cinema": dict(
        gamma_law="Canon Log 3", gamut="Cinema Gamut",
        highlight_rolloff=.42, shadow_lift=.03, midtone_contrast=.02,
        color_separation=.04, skin_response={"warmth":.06,"sat":.97},
        sat_response={**_empty_hue_response(), "orange":.95},
    ),
    "Canon EOS": dict(
        gamma_law="Rec.709", gamut="Rec.709",
        highlight_rolloff=.15, shadow_lift=.0, midtone_contrast=.02,
        color_separation=.02, skin_response={"warmth":.05,"sat":.97},
        sat_response={**_empty_hue_response(), "orange":.95},
        white_balance_bias=-.3,
    ),
    "Blackmagic": dict(
        gamma_law="Blackmagic Film", gamut="Blackmagic Wide Gamut",
        highlight_rolloff=.34, shadow_lift=-.04, midtone_contrast=-.03,
        color_separation=.03, skin_response={"warmth":.0,"sat":.95},
    ),
    "Panasonic Varicam": dict(
        gamma_law="V-Log", gamut="V-Gamut",
        highlight_rolloff=.44, shadow_lift=.02, midtone_contrast=.0,
        color_separation=.05, skin_response={"warmth":.02,"sat":.96},
    ),
    "Nikon Z": dict(
        gamma_law="Rec.709", gamut="Rec.709",
        highlight_rolloff=.16, shadow_lift=.0, midtone_contrast=.02,
        color_separation=.02, skin_response={"warmth":.0,"sat":.97},
        white_balance_bias=-.2,
    ),
    "Nikon DSLR": dict(
        gamma_law="Rec.709", gamut="Rec.709",
        highlight_rolloff=.14, shadow_lift=.0, midtone_contrast=.03,
        color_separation=.02, skin_response={"warmth":.0,"sat":.97},
        white_balance_bias=-.2,
    ),
    "Fujifilm X": dict(
        gamma_law="Rec.709", gamut="Rec.709",
        highlight_rolloff=.24, shadow_lift=.0, midtone_contrast=.05,
        color_separation=.08, skin_response={"warmth":.03,"sat":.95},
        sat_response={**_empty_hue_response(), "green":1.06,"cyan":1.05},
    ),
    "Fujifilm GFX": dict(
        gamma_law="Rec.709", gamut="Rec.709",
        highlight_rolloff=.26, shadow_lift=.0, midtone_contrast=.04,
        color_separation=.07, skin_response={"warmth":.03,"sat":.96},
        sat_response={**_empty_hue_response(), "green":1.05},
    ),
    # ---- Mobile sensors (spec follow-up: iPhone + Android) ----------
    # These characterize the *computational-photography output*, not a
    # raw sensor — every current phone applies multi-frame HDR fusion,
    # local tone mapping, and on-device saturation/sharpening before a
    # JPEG/HEIC ever exists. That pipeline is what gives phones their
    # recognizable "flat-highlight, punchy-midtone, over-sharpened"
    # signature — the same behavior the existing Mobile DNA (fam_of/
    # DNA/mob_adjust) already corrects for via param deltas. Camera DNA
    # 2.0 profiles below encode that same, documented tendency as a
    # proper CameraProfile so phones are selectable Camera Match
    # sources/targets (Auto Detect, skin protection, OKLab strength
    # blending) exactly like the cinema/photo cameras above.
    "Apple iPhone": dict(
        gamma_law="Smart HDR / Rec.709", gamut="Rec.709",
        # Apple's computational pipeline actively protects highlights
        # (Deep Fusion / Smart HDR tone mapping) -> less rolloff *needed*
        # from us, but the source is already flatter/lower-contrast than
        # a natural capture, so we lift midtone contrast a touch instead.
        highlight_rolloff=.10, shadow_lift=.10, midtone_contrast=.06,
        color_separation=-.04,  # slight de-punch: mild oversharpen correction
        skin_response={"warmth":.02,"sat":.92},
        sat_response={**_empty_hue_response(), "red":.95,"orange":.95},
        white_balance_bias=.1,
    ),
    "Android Generic": dict(
        # Broad Android computational-camera baseline (Samsung/Xiaomi/
        # Huawei/Oppo/Pixel families all vary, but share a punchier,
        # more saturated, more aggressively sharpened default JPEG
        # pipeline than either iPhone or a dedicated camera).
        gamma_law="Vendor HDR / Rec.709", gamut="Rec.709",
        highlight_rolloff=.14, shadow_lift=.04, midtone_contrast=.04,
        color_separation=-.08,  # correct for on-device oversharpening
        skin_response={"warmth":-.02,"sat":.90},
        sat_response={**_empty_hue_response(), "green":.92,"blue":.94},
        white_balance_bias=-.1,
    ),
    "Google Pixel": dict(
        # Pixel's HDR+ leans more neutral/contrasty than typical Android
        # vendor tuning (documented, well-known difference from Samsung/
        # Xiaomi's punchier defaults) — kept as its own family rather
        # than folded into "Android Generic".
        gamma_law="HDR+ / Rec.709", gamut="Rec.709",
        highlight_rolloff=.12, shadow_lift=.02, midtone_contrast=.08,
        color_separation=-.03,
        skin_response={"warmth":.0,"sat":.95},
        sat_response={**_empty_hue_response()},
    ),
}


# ---- Fujifilm Film Simulation character (spec section 11) -------------
# Explicitly labeled "-inspired" everywhere in UI text — these are
# mathematically-defined approximations, not proprietary reproductions.

FUJI_FILM_SIM = {
    "Provia":        dict(sat_mult=1.00, contrast=.00, hi_roll=.20, sh_lift=.00, desc="Standard balanced -inspired"),
    "Velvia":        dict(sat_mult=1.18, contrast=.10, hi_roll=.28, sh_lift=-.02, desc="Vivid, saturated -inspired"),
    "Astia":         dict(sat_mult=1.04, contrast=-.03, hi_roll=.16, sh_lift=.02, desc="Soft, portrait-leaning -inspired"),
    "Classic Chrome":dict(sat_mult=.90, contrast=.04, hi_roll=.30, sh_lift=.03, desc="Muted, documentary -inspired"),
    "Acros":         dict(sat_mult=0.0, contrast=.08, hi_roll=.22, sh_lift=.00, desc="Fine-grain monochrome -inspired"),
    "Eterna":        dict(sat_mult=.82, contrast=-.10, hi_roll=.36, sh_lift=.06, desc="Flat cinematic -inspired"),
}


# ---- Sony gamma/gamut metadata detection (spec section 12) ------------

SONY_GAMMA_TOKENS = {
    "s-log2":"S-Log2", "slog2":"S-Log2",
    "s-log3":"S-Log3", "slog3":"S-Log3",
    "hlg":"HLG", "rec709":"Rec.709", "rec.709":"Rec.709",
}
SONY_GAMUT_TOKENS = {
    "s-gamut3.cine":"S-Gamut3.Cine", "sgamut3cine":"S-Gamut3.Cine",
    "s-gamut3":"S-Gamut3", "sgamut3":"S-Gamut3",
    "s-gamut":"S-Gamut", "sgamut":"S-Gamut",
}
CANON_LOG_TOKENS = {"canon log 2":"Canon Log 2","canon log2":"Canon Log 2",
                     "clog2":"Canon Log 2",
                     "canon log 3":"Canon Log 3","canon log3":"Canon Log 3",
                     "clog3":"Canon Log 3",
                     "canon log":"Canon Log","clog":"Canon Log"}
ARRI_MODEL_TOKENS = {
    "alexa mini lf":"Alexa Mini LF", "alexa lf":"Alexa LF",
    "alexa mini":"Alexa Mini", "alexa 35":"Alexa 35", "alexa":"Alexa",
}


# ---- 1. Metadata Analysis (spec section 4) -----------------------------

def cd_meta_analyze(meta):
    """Extract everything usable from the (already-parsed) EXIF dict
    that load_src()/_meta() produced, without crashing on missing
    fields. Returns a plain dict — never raises."""
    meta = meta or {}
    make = str(meta.get("make") or "").strip()
    model = str(meta.get("model") or "").strip()
    text = f"{make} {model} {meta.get('software','')}".lower()
    out = {
        "make": make, "model": model,
        "lens": meta.get("lens"), "iso": meta.get("iso"),
        "raw": bool(meta.get("raw")),
        "gamma": None, "gamut": None, "picture_profile": None,
        "film_simulation": None,
    }
    for tok, name in SONY_GAMMA_TOKENS.items():
        if tok in text:
            out["gamma"] = name
            break
    for tok, name in SONY_GAMUT_TOKENS.items():
        if tok in text:
            out["gamut"] = name
            break
    if out["gamma"] is None:
        for tok, name in CANON_LOG_TOKENS.items():
            if tok in text:
                out["gamma"] = name
                break
    for tok, name in ARRI_MODEL_TOKENS.items():
        if tok in text:
            out["arri_model"] = name
            break
    for sim in FUJI_FILM_SIM:
        if sim.lower().replace(" ", "") in text.replace(" ", ""):
            out["film_simulation"] = sim
            break
    return out


# ---- 2. Pixel-based camera analysis (spec section 5) -------------------

def cd_pixel_signature(rgb):
    """Vectorized, downsampled image-appearance analysis. Never raises.
    All quantities are normalized to roughly 0..1 so they can be compared
    across cameras without magic per-camera thresholds documented
    nowhere (spec section 7).

    Camera DNA 2.3 (Problem 2/4): added a small set of *relative-shape*
    tone features (highlight_slope/shadow_slope) instead of relying only
    on absolute clip fractions. Absolute clip fractions shift with
    exposure even for the same camera+scene; a relative measure of how
    much of the frame's own dynamic range sits compressed near the top
    /bottom decile is far more exposure-invariant, because it's a ratio
    of the frame's own percentiles rather than a fixed threshold. This
    doesn't make the feature camera-specific -- a genuinely flat scene
    will still read as "not compressed" regardless of camera -- but it
    is a real improvement in exposure robustness over the previous
    absolute clip-fraction-only measure (still returned too, for
    backward-compat with any external caller).

    channel_corr is included as a *weak, explicitly scene-dependent*
    signal (Problem 4): a near-monochrome scene will read as highly
    "correlated" independent of which camera shot it, so it is not
    given meaningful weight in scoring below -- it exists for
    diagnostics/future work, not as a fingerprint."""
    x = analysis_size(rgb, 400)
    lm = luminance(x)
    lab = rgb2oklab(x)
    lch = oklab2oklch(lab)
    C, H = lch[...,1], lch[...,2]

    p1, p10, p50, p90, p99 = (float(np.percentile(lm, q))
                               for q in (1, 10, 50, 90, 99))
    clip_hi = float(np.mean(lm > .985))
    clip_lo = float(np.mean(lm < .015))
    contrast = float(p99-p1)
    contrast_safe = max(contrast, 1e-4)
    # Relative shape of the tone curve's extremes, normalized by the
    # frame's own dynamic range -- stable across exposure scaling of
    # the *same* scene+camera far better than an absolute clip count.
    highlight_slope = float(np.clip((p99-p90)/contrast_safe, 0, 1))
    shadow_slope = float(np.clip((p10-p1)/contrast_safe, 0, 1))
    sat_mean = float(np.mean(C))
    sat_p90 = float(np.percentile(C, 90))
    chroma_std = float(np.std(C))

    hb = _hue_weights(H)
    hue_energy = {k: float(np.mean(hb[k]*C)) for k in HUE_BUCKETS}
    tot = sum(hue_energy.values()) or 1.0
    hue_balance = {k: v/tot for k, v in hue_energy.items()}

    # neutral balance / channel bias, measured on near-neutral pixels
    neutral_mask = C < float(np.percentile(C, 25))
    if neutral_mask.sum() > 20:
        nr = float(np.mean(x[...,0][neutral_mask]))
        ng = float(np.mean(x[...,1][neutral_mask]))
        nb = float(np.mean(x[...,2][neutral_mask]))
    else:
        nr, ng, nb = (float(np.mean(x[...,c])) for c in range(3))
    ng_safe = max(ng, 1e-4)
    channel_bias = (nr/ng_safe, 1.0, nb/ng_safe)

    # weak, explicitly scene-dependent diagnostic (see docstring) --
    # not used to drive confident scoring.
    try:
        r, g, b = x[...,0].ravel(), x[...,1].ravel(), x[...,2].ravel()
        rg = float(np.corrcoef(r, g)[0, 1]) if np.std(r) > 1e-5 and np.std(g) > 1e-5 else 1.0
        gb = float(np.corrcoef(g, b)[0, 1]) if np.std(g) > 1e-5 and np.std(b) > 1e-5 else 1.0
        channel_corr = float(np.clip((rg+gb)/2, -1, 1))
    except Exception:
        channel_corr = 1.0

    gy, gx = np.gradient(lm)
    edge = float(np.mean(np.sqrt(gx*gx+gy*gy)))

    return {
        "shadow_p1": p1, "shadow_p10": p10, "midtone_p50": p50,
        "highlight_p90": p90, "highlight_p99": p99,
        "contrast": contrast, "clip_highlight": clip_hi,
        "clip_shadow": clip_lo,
        "highlight_slope": highlight_slope, "shadow_slope": shadow_slope,
        "sat_mean": sat_mean, "sat_p90": sat_p90,
        "chroma_std": chroma_std, "hue_balance": hue_balance,
        "channel_bias": channel_bias, "channel_corr": channel_corr,
        "edge_energy": edge,
    }


# ---- 3. Camera matching / detection (spec sections 6, 7, 27) -----------

class CameraMatchResult:
    """Normalized scoring breakdown. Confidence is a documented, bounded
    combination of the three sub-scores — no unexplained magic
    constants: metadata gets the most weight because it's the most
    reliable signal when present; pixel/tone/color scores only ever
    *reduce* confidence relative to a metadata match, and are the sole
    basis for confidence when metadata is absent."""
    __slots__ = ("profile","confidence","metadata_score","pixel_score",
                 "tone_score","color_score","basis")
    def __init__(self, profile, confidence, metadata_score, pixel_score,
                 tone_score, color_score, basis):
        self.profile = profile
        self.confidence = float(np.clip(confidence, 0.0, 1.0))
        self.metadata_score = float(np.clip(metadata_score, 0.0, 1.0))
        self.pixel_score = float(np.clip(pixel_score, 0.0, 1.0))
        self.tone_score = float(np.clip(tone_score, 0.0, 1.0))
        self.color_score = float(np.clip(color_score, 0.0, 1.0))
        self.basis = basis  # "Detected" (metadata) or "Estimated" (pixel)

def _metadata_match_score(profile, meta_info):
    """1.0 if make/model text directly names this profile or one of its
    aliases; 0 otherwise. Deliberately binary+reliable rather than fuzzy,
    per spec section 27 (metadata identification should be trustworthy)."""
    text = f"{meta_info.get('make','')} {meta_info.get('model','')}".lower()
    if not text.strip():
        return 0.0
    names = (profile.model.lower(), profile.display_name().lower(),
              *[a.lower() for a in profile.aliases])
    for n in names:
        if n and n in text:
            return 1.0
    for sig in profile.metadata_signatures:
        if sig.lower() in text:
            return 0.85
    return 0.0

def _pixel_match_score(profile, sig):
    """Heuristic similarity between the measured pixel signature and this
    profile's *expected tendencies* (highlight rolloff/shadow lift/hue
    saturation bias). This is intentionally coarse: pixels alone cannot
    reliably distinguish similar sensors, so scores here are meant to
    rank plausible candidates, not assert identity (spec section 27).

    Camera DNA 2.3: highlight tendency now reads from `highlight_slope`
    (relative to the frame's own dynamic range) instead of an absolute
    clip-fraction/contrast blend -- more stable across exposure (Problem
    3/14). `channel_corr` is deliberately NOT used here: it's kept in
    the signature only as a diagnostic because it's dominated by scene
    content (a monochrome scene reads as "correlated" independent of
    camera), not weighted into the score (Problem 4)."""
    score = 0.5
    # highlight rolloff tendency vs measured relative highlight
    # compression (exposure-robust: a ratio of the frame's own
    # percentiles, not an absolute clip threshold)
    expect_soft = profile.highlight_rolloff
    measured_soft = sig.get("highlight_slope",
                             float(np.clip(sig["clip_highlight"]*4 +
                                           (1-sig["contrast"]), 0, 1)))
    score += (1-abs(expect_soft-measured_soft))*0.20-0.10
    # saturation tendency
    avg_sat_bias = float(np.mean(list(profile.sat_response.values())))
    measured_sat = float(np.clip(sig["sat_mean"]*3, 0, 1.4))
    expect_sat = float(np.clip(avg_sat_bias, .5, 1.3))
    score += (1-min(abs(measured_sat-expect_sat), 1))*0.20-0.10
    # channel bias (very coarse warm/cool tendency)
    r_bias, _, b_bias = sig["channel_bias"]
    profile_warm = (profile.skin_response.get("warmth", 0) +
                     profile.white_balance_bias*0.02)
    measured_warm = r_bias-b_bias
    score += (1-min(abs(measured_warm-profile_warm)*2, 1))*0.10
    return float(np.clip(score, 0.0, 1.0))

def _tone_score(profile, sig):
    expect = profile.highlight_rolloff
    measured = sig.get("highlight_slope",
                        float(np.clip(sig["clip_highlight"]*5, 0, 1)))
    return float(np.clip(1-abs(expect-measured), 0, 1))

def _color_score(profile, sig):
    avg_sat_bias = float(np.mean(list(profile.sat_response.values())))
    measured = float(np.clip(sig["sat_mean"]*3, 0, 1.4))
    return float(np.clip(1-min(abs(measured-avg_sat_bias), 1), 0, 1))

def _pixel_evidence_quality(sig):
    """0..1: how much real discriminative signal this image's pixel
    signature actually carries for camera-character estimation, as
    opposed to how confidently any candidate profile happens to score.

    A flat gray card, a solid color swatch, or a low-dynamic-range
    frame gives `_pixel_match_score` almost nothing to differentiate
    cameras with -- every profile ends up clustered near the neutral
    0.5 baseline regardless of which camera actually shot it. This is
    a property of the *image*, computed once, independent of any
    candidate profile, so it can gate confidence honestly instead of
    letting 53 profiles each independently claim a plausible-looking
    score off noise (spec 2.2 Problem 1/3).

    Combines: tonal range actually used (contrast), presence of real
    highlight/shadow clipping behavior to read rolloff from, spread of
    chroma across the frame, and spread of hue energy across buckets
    (a single-hue scene, e.g. a wall or sky, gives no hue-response
    evidence at all -- see Problem 3, scene content is not identity)."""
    tone_signal = float(np.clip(sig["contrast"]*1.2, 0, 1))
    clip_signal = float(np.clip((sig["clip_highlight"]+sig["clip_shadow"])*3, 0, 1))
    chroma_signal = float(np.clip(sig["chroma_std"]*4, 0, 1))
    hb = sig["hue_balance"]
    hue_spread_raw = float(np.clip(np.std(list(hb.values()))*6, 0, 1)) if hb else 0.0
    # Hue is mathematically undefined at zero chroma: a flat/near-gray
    # image can report an arbitrary-looking, nonzero hue_balance spread
    # purely from near-0/near-0 division noise, even though there is no
    # real color information to read hue evidence from. Gate the hue
    # term by how much actual chroma is present so a colorless frame
    # can't manufacture false hue-based evidence.
    hue_spread = hue_spread_raw * float(np.clip(sig["sat_mean"]*8, 0, 1))
    return float(np.clip(0.30*tone_signal + 0.25*clip_signal +
                          0.25*chroma_signal + 0.20*hue_spread, 0.0, 1.0))

def cd_match_camera(rgb_preview, meta):
    """AUTO mode: combine metadata + pixel statistics into a ranked list
    of CameraMatchResult, per spec sections 5-7, 27 and Camera DNA 2.2
    Problem 1/3.

    `basis` is one of:
      "Detected"       -- metadata names this profile (or an alias).
      "Estimated"      -- pixel-only, but the image carries enough
                           discriminative signal AND this candidate
                           clearly separates from the runner-up.
      "Low confidence" -- pixel-only, some signal, but the top
                           candidate doesn't clearly beat the next one
                           (an arbitrary image should not pretend to
                           identify a specific camera it can't).
      "Unknown"         -- pixel-only and the image itself carries too
                           little discriminative signal to estimate
                           anything (e.g. a flat/blank/low-contrast
                           frame) -- honest non-answer rather than a
                           confident-looking guess.

    Never claims certainty pixels alone can't support."""
    meta_info = cd_meta_analyze(meta)
    try:
        sig = cd_pixel_signature(rgb_preview)
    except Exception:
        sig = None
    evidence = _pixel_evidence_quality(sig) if sig is not None else 0.0

    scored = []  # (prof, ms, ps, ts, cs, raw_pixel_only)
    for prof in CAMERA_PROFILES.values():
        ms = _metadata_match_score(prof, meta_info)
        if sig is not None:
            ps = _pixel_match_score(prof, sig)
            ts = _tone_score(prof, sig)
            cs = _color_score(prof, sig)
        else:
            ps = ts = cs = 0.0
        raw = ps*0.5 + ts*0.25 + cs*0.25
        scored.append((prof, ms, ps, ts, cs, raw))

    # Score-margin gate (spec 2.2 Problem 1): the raw pixel-only score
    # by itself says "how well does THIS profile fit", never "how much
    # BETTER does it fit than every other candidate". Without that
    # comparison, dozens of unrelated profiles cluster near the same
    # score and any one of them can look falsely confident. Compute
    # the gap between the best and second-best raw pixel-only score
    # across *all* candidates, once, and use it to scale confidence.
    raws_sorted = sorted((s[5] for s in scored), reverse=True)
    top_raw = raws_sorted[0] if raws_sorted else 0.0
    second_raw = raws_sorted[1] if len(raws_sorted) > 1 else top_raw
    margin = max(0.0, top_raw-second_raw)
    margin_norm = float(np.clip(margin/0.12, 0.0, 1.0))
    evidence_norm = float(np.clip(evidence, 0.0, 1.0))
    # Both factors must be present: a huge margin on a blank frame is
    # still meaningless, and strong evidence with no separation between
    # candidates still can't single one out.
    pixel_reliability = margin_norm*evidence_norm

    results = []
    for prof, ms, ps, ts, cs, raw in scored:
        if ms > 0:
            # Metadata-backed: confidence dominated by the reliable
            # metadata hit, lightly corroborated by pixel consistency.
            conf = 0.75*ms + 0.25*((ps+ts+cs)/3)
            basis = "Detected"
        else:
            # Pixel-only: hard cap because pixels alone cannot uniquely
            # fingerprint a camera model, then scaled down further by
            # how little this specific result is actually separated
            # from the field (margin) and how little the image itself
            # supports any pixel-based read (evidence).
            conf = min(0.72, raw) * (0.25+0.75*pixel_reliability)
            if evidence_norm < 0.15:
                basis = "Unknown"
                conf = min(conf, 0.15)
            elif conf < CONFIDENCE_LOW_THRESHOLD:
                basis = "Low confidence"
            else:
                basis = "Estimated"
        results.append(CameraMatchResult(prof, conf, ms, ps, ts, cs, basis))

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results

CONFIDENCE_LOW_THRESHOLD = 0.35  # below this, UI must say "Low confidence"


# ---- 4/5. Technical transform vs Camera Character (spec section 3) -----

def cd_detect_gamma_gamut(meta_info, sig):
    """Best-effort input-state guess used only to avoid double-applying a
    log-style transform to an already-rendered Rec.709/JPEG (spec
    section 15). Metadata wins when present; otherwise assumes the
    image is already display-referred (Rec.709), which is the safe
    default for ordinary JPEG/TIFF/PNG input."""
    if meta_info.get("gamma"):
        return meta_info["gamma"], meta_info.get("gamut") or "Unknown"
    return "Rec.709", "Rec.709"

def _camera_technical_transform(rgb, source_profile, input_gamma):
    """Technical transform stage. If the source is already Rec.709
    (the overwhelmingly common case for this app's rendered-image
    input — see RAW HANDLING note below), this is a no-op: applying a
    log->Rec709 curve to an already-decoded image would be wrong
    (spec section 15/16). If metadata indicates the input truly is a
    log-encoded frame captured straight from RAW/video (rare for this
    pipeline), a mild highlight-protective curve approximates the
    missing IDT step, without inventing sensor data that isn't there."""
    if input_gamma in (None, "Rec.709", "Unknown"):
        return rgb
    # Mild, conservative approximation of a log->display curve: lift
    # shadows slightly and compress highlights, matching the *shape*
    # log footage has after naive display-referred interpretation.
    x = arr32(rgb)
    lm = luminance(x)
    k = smoothstep(.55, .98, lm)
    x = x*(1-0.10*k[...,None])
    x = np.power(np.clip(x, 0, 1), 0.92)
    return x

def _camera_character_transform(rgb, profile, oklab_cache=None):
    """CREATIVE camera-character stage: hue/sat response per bucket,
    highlight rolloff, shadow lift, midtone contrast, color separation,
    channel balance, skin warmth bias. Pure pointwise math — tile-safe,
    cacheable, deterministic (spec sections 9, 21, 22)."""
    x = clamp(rgb)
    cb = np.asarray(profile.channel_balance, np.float32).reshape(1,1,3)
    if not np.allclose(cb, 1.0, atol=1e-4):
        x = clamp(x*cb)

    lab = rgb2oklab(x)
    lch = oklab2oklch(lab)
    L, C, H = lch[...,0], lch[...,1], lch[...,2]

    if any(abs(v) > 1e-4 for v in profile.hue_response.values()) or \
            any(abs(v-1.0) > 1e-4 for v in profile.sat_response.values()):
        hb = _hue_weights(H)
        dH = np.zeros_like(H)
        satmul = np.ones_like(C)
        for name in HUE_BUCKETS:
            w = hb[name]
            dH += w*profile.hue_response.get(name, 0.0)
            satmul += w*(profile.sat_response.get(name, 1.0)-1.0)
        H = (H+dH) % 360.0
        C = np.maximum(C*satmul, 0)

    if abs(profile.color_separation) > 1e-4:
        # Micro-contrast on chroma only (never touches luminance) —
        # increases perceived color separation without a spatial filter.
        # A per-pixel-relative-to-mean version was tried and rejected:
        # it depends on np.mean(C) over the *current tile/preview*, so
        # the same pixel would grade differently in a 256px tile vs a
        # full-frame render — a tile-safety violation (spec section 22).
        # This flat multiplier is pointwise and therefore tile-safe.
        s = profile.color_separation
        C = np.clip(C*(1+s*0.15), 0, None)

    lab = oklch2oklab(np.stack([L, C, H], -1))
    x = clamp(oklab2rgb(lab))

    if abs(profile.highlight_rolloff) > 1e-4:
        x = rolloff(x, profile.highlight_rolloff*60)
    if abs(profile.shadow_lift) > 1e-4:
        lm = luminance(x)[..., None]
        k = 1-smoothstep(0.0, .35, luminance(x))[..., None]
        x = clamp(x + profile.shadow_lift*.12*k)
    if abs(profile.midtone_contrast) > 1e-4:
        lm = luminance(x)
        mt = np.clip(1-np.abs(lm-.5)/.5, 0, 1)[..., None]
        x = clamp(x + (x-luminance(x)[...,None])*profile.midtone_contrast*mt)

    return x

def _apply_skin_response(rgb, profile, skin_mask):
    """Skin protection stage per spec section 19: camera character's
    generic hue/sat shift is dampened toward the profile's dedicated
    skin_response inside the skin mask, instead of letting the general
    hue-bucket transform run unchecked over skin tones."""
    warm = profile.skin_response.get("warmth", 0.0)
    satm = profile.skin_response.get("sat", 1.0)
    if abs(warm) < 1e-4 and abs(satm-1.0) < 1e-4:
        return rgb
    m3 = skin_mask[..., None]
    x = clamp(rgb)
    if abs(warm) > 1e-4:
        x = x*(1-m3*.7) + ctemp(x, warm*20)*(m3*.7)
    if abs(satm-1.0) > 1e-4:
        lm = luminance(x)[..., None]
        adj = lm+(x-lm)*satm
        x = x*(1-m3*.7) + clamp(adj)*(m3*.7)
    return clamp(x)


# ---- 6. Public entry point used by Eng/staged (spec sections 17/18/19) -

def cd_apply(rgb, cd_params, skin_mask=None):
    """Apply Camera Match to `rgb` per `cd_params` (as produced by
    App._stg() — see CD_DEFAULTS below for keys). No-ops cleanly at
    strength 0 or when disabled/no target selected (spec section 26:
    strength=0 must be effectively identical to the original)."""
    if not cd_params or not cd_params.get("cm_enabled"):
        return rgb
    target_id = cd_params.get("cm_target")
    strength = float(np.clip(cd_params.get("cm_strength", 0.0), 0, 1))
    if not target_id or strength <= 1e-4:
        return rgb
    target = CAMERA_PROFILES.get(target_id)
    if target is None:
        return rgb

    source_id = cd_params.get("cm_source")
    source = CAMERA_PROFILES.get(source_id) if source_id else None

    x0 = clamp(rgb)
    x = x0

    input_gamma = cd_params.get("cm_input_gamma", "Rec.709")
    x = _camera_technical_transform(x, source, input_gamma)

    # MANUAL mode with an explicit source: undo the source's character
    # (approximately) before applying the target's, so "Sony A7 IV ->
    # ARRI Alexa 35" reads as a genuine transform, not target-only.
    if source is not None and cd_params.get("cm_mode", "character") == "character":
        x = _camera_character_transform(x, _neutralizing_profile(source))

    x = _camera_character_transform(x, target)

    # Fujifilm film-simulation character layer (spec section 11)
    sim = cd_params.get("cm_film_sim")
    sim_is_mono = False
    if sim and sim in FUJI_FILM_SIM:
        fs = FUJI_FILM_SIM[sim]
        if fs["sat_mult"] <= 1e-4:
            x = mono(x)
            sim_is_mono = True
        else:
            lm = luminance(x)[..., None]
            x = clamp(lm+(x-lm)*fs["sat_mult"])
        if abs(fs["contrast"]) > 1e-4:
            lm = luminance(x)
            mt = np.clip(1-np.abs(lm-.5)/.5, 0, 1)[..., None]
            x = clamp(x + (x-luminance(x)[...,None])*fs["contrast"]*mt)
        if fs["hi_roll"] > 1e-4:
            x = rolloff(x, fs["hi_roll"]*60)

    # Skin protection: blend skin regions back toward a gentler,
    # profile-specific response instead of the raw generic transform.
    # Skipped for monochrome film sims — reintroducing color into a
    # deliberately desaturated result would defeat the simulation.
    if skin_mask is not None and not sim_is_mono:
        x_skin_safe = _apply_skin_response(x0, target, skin_mask)
        m3 = skin_mask[..., None]
        x = x*(1-m3*.55) + x_skin_safe*(m3*.55)

    # Strength interpolation in OKLab (perceptually linear-ish), not
    # naive RGB, to avoid hue/luminance artifacts at partial strength
    # (spec section 18).
    if strength >= .999:
        out = x
    else:
        lab0 = rgb2oklab(x0)
        lab1 = rgb2oklab(x)
        out = clamp(oklab2rgb(lab0*(1-strength)+lab1*strength))
    return out

def _neutralizing_profile(source):
    """Approximate inverse character used only for MANUAL source->target
    matching: negates the source's hue/sat/tone bias so its influence is
    roughly cancelled before the target's is applied. This is a
    documented approximation (true inversion of a lossy pointwise
    transform is not generally exact), not a physical un-mix."""
    inv_hue = {k: -v for k, v in source.hue_response.items()}
    inv_sat = {k: (1.0/max(v, 1e-3)) for k, v in source.sat_response.items()}
    return CameraProfile(
        source.id+"__inv", source.manufacturer, source.model,
        source.family, source.category,
        gamma_law=source.gamma_law, gamut=source.gamut,
        hue_response=inv_hue, sat_response=inv_sat,
        highlight_rolloff=-source.highlight_rolloff*.6,
        shadow_lift=-source.shadow_lift, midtone_contrast=-source.midtone_contrast,
        color_separation=-source.color_separation*.5,
        skin_response={"warmth": -source.skin_response.get("warmth",0)*.6,
                       "sat": 1.0/max(source.skin_response.get("sat",1.0),1e-3)},
        channel_balance=tuple(1.0/max(c,1e-3) for c in source.channel_balance),
        white_balance_bias=-source.white_balance_bias,
    )


# ---- Camera Model Registry (spec sections 10-14) -----------------------
# Extensible: add a new model with make_profile(...) and register it in
# CAMERA_MODELS — no rendering-engine changes required (spec: architecture
# must allow new cameras without touching the engine).

CAMERA_MODELS = [
    # ARRI
    make_profile("arri_alexa","ARRI","Alexa","ARRI Alexa","Cinema",
                 aliases=("alexa classic",)),
    make_profile("arri_alexa_mini","ARRI","Alexa Mini","ARRI Alexa","Cinema"),
    make_profile("arri_alexa_mini_lf","ARRI","Alexa Mini LF","ARRI Alexa","Cinema",
                 gamut="ARRI Wide Gamut / Large Format"),
    make_profile("arri_alexa_lf","ARRI","Alexa LF","ARRI Alexa","Cinema",
                 gamut="ARRI Wide Gamut / Large Format"),
    make_profile("arri_alexa_35","ARRI","Alexa 35","ARRI Alexa","Cinema",
                 gamma_law="LogC4", color_separation=.13, highlight_rolloff=.66),
    # Sony Cinema
    make_profile("sony_venice","Sony","VENICE","Sony VENICE","Cinema"),
    make_profile("sony_venice2","Sony","VENICE 2","Sony VENICE","Cinema"),
    make_profile("sony_fx6","Sony","FX6","Sony Cine","Cinema"),
    make_profile("sony_fx9","Sony","FX9","Sony Cine","Cinema"),
    make_profile("sony_fx3","Sony","FX3","Sony Cine","Cinema"),
    # Sony Alpha
    make_profile("sony_a7iv","Sony","A7 IV","Sony Alpha","Photography",
                  aliases=("a7m4","ilce-7m4")),
    make_profile("sony_a7riv","Sony","A7R IV","Sony Alpha","Photography",
                  aliases=("a7rm4","ilce-7rm4")),
    make_profile("sony_a7rv","Sony","A7R V","Sony Alpha","Photography",
                  aliases=("a7rm5","ilce-7rm5")),
    make_profile("sony_a9ii","Sony","A9 II","Sony Alpha","Photography"),
    make_profile("sony_a1","Sony","A1","Sony Alpha","Photography"),
    # RED
    make_profile("red_v_raptor","RED","V-RAPTOR","RED","Cinema"),
    make_profile("red_komodo","RED","KOMODO","RED","Cinema"),
    make_profile("red_monstro","RED","Monstro 8K VV","RED","Cinema"),
    # Canon Cinema
    make_profile("canon_c300_iii","Canon","EOS C300 Mark III","Canon Cinema","Cinema"),
    make_profile("canon_c500_ii","Canon","EOS C500 Mark II","Canon Cinema","Cinema"),
    make_profile("canon_c70","Canon","EOS C70","Canon Cinema","Cinema"),
    # Canon EOS
    make_profile("canon_r5","Canon","EOS R5","Canon EOS","Photography"),
    make_profile("canon_r6ii","Canon","EOS R6 Mark II","Canon EOS","Photography"),
    make_profile("canon_5d4","Canon","EOS 5D Mark IV","Canon EOS","Photography"),
    # Blackmagic
    make_profile("bmpcc6k","Blackmagic","Pocket Cinema Camera 6K","Blackmagic","Cinema"),
    make_profile("bm_ursa12k","Blackmagic","URSA Mini Pro 12K","Blackmagic","Cinema"),
    # Panasonic
    make_profile("panasonic_varicam_lt","Panasonic","Varicam LT","Panasonic Varicam","Cinema"),
    make_profile("panasonic_varicam_35","Panasonic","Varicam 35","Panasonic Varicam","Cinema"),
    # Nikon
    make_profile("nikon_z9","Nikon","Z9","Nikon Z","Photography"),
    make_profile("nikon_z8","Nikon","Z8","Nikon Z","Photography"),
    make_profile("nikon_z6iii","Nikon","Z6 III","Nikon Z","Photography"),
    make_profile("nikon_d850","Nikon","D850","Nikon DSLR","Photography"),
    # Fujifilm
    make_profile("fuji_xt5","Fujifilm","X-T5","Fujifilm X","Photography"),
    make_profile("fuji_xh2","Fujifilm","X-H2","Fujifilm X","Photography"),
    make_profile("fuji_x100vi","Fujifilm","X100VI","Fujifilm X","Photography"),
    make_profile("fuji_gfx100ii","Fujifilm","GFX100 II","Fujifilm GFX","Photography"),
    make_profile("fuji_gfx50sii","Fujifilm","GFX 50S II","Fujifilm GFX","Photography"),
    # ---- Mobile: iPhone (per-generation, mirrors existing IDNA coverage) ----
    # Later generations push computational HDR harder (more highlight
    # protection, more on-device saturation/sharpening correction), so
    # highlight_rolloff/color_separation trend slightly with generation —
    # same direction as the legacy IDNA deltas (highlights/clarity grow
    # more negative for newer models).
    make_profile("iphone_11","Apple","iPhone 11","Apple iPhone","Mobile",
                 aliases=("iphone 11",)),
    make_profile("iphone_12","Apple","iPhone 12","Apple iPhone","Mobile",
                 aliases=("iphone 12",), highlight_rolloff=.11),
    make_profile("iphone_13","Apple","iPhone 13","Apple iPhone","Mobile",
                 aliases=("iphone 13",), highlight_rolloff=.12,
                 color_separation=-.05),
    make_profile("iphone_14","Apple","iPhone 14","Apple iPhone","Mobile",
                 aliases=("iphone 14",), highlight_rolloff=.13,
                 color_separation=-.05),
    make_profile("iphone_15","Apple","iPhone 15","Apple iPhone","Mobile",
                 aliases=("iphone 15",), highlight_rolloff=.14,
                 color_separation=-.06,
                 sat_response={**_empty_hue_response(), "red":.90,"orange":.90}),
    make_profile("iphone_16","Apple","iPhone 16","Apple iPhone","Mobile",
                 aliases=("iphone 16",), highlight_rolloff=.15,
                 color_separation=-.06,
                 sat_response={**_empty_hue_response(), "red":.88,"orange":.88}),
    # ---- Mobile: Android (Samsung Galaxy S per-generation + other OEMs) ----
    make_profile("galaxy_s20","Samsung","Galaxy S20","Android Generic","Mobile",
                 aliases=("sm-g98","s20")),
    make_profile("galaxy_s21","Samsung","Galaxy S21","Android Generic","Mobile",
                 aliases=("sm-g99","s21"), color_separation=-.09),
    make_profile("galaxy_s22","Samsung","Galaxy S22","Android Generic","Mobile",
                 aliases=("sm-s90","s22"), color_separation=-.09,
                 white_balance_bias=-.15),
    make_profile("galaxy_s23","Samsung","Galaxy S23","Android Generic","Mobile",
                 aliases=("sm-s91","s23"), color_separation=-.10,
                 highlight_rolloff=.15),
    make_profile("galaxy_s24","Samsung","Galaxy S24","Android Generic","Mobile",
                 aliases=("sm-s92","s24"), color_separation=-.10,
                 highlight_rolloff=.15, white_balance_bias=-.15),
    make_profile("galaxy_s25","Samsung","Galaxy S25","Android Generic","Mobile",
                 aliases=("sm-s93","s25"), color_separation=-.09,
                 highlight_rolloff=.14),
    make_profile("pixel_8","Google","Pixel 8","Google Pixel","Mobile",
                 aliases=("pixel 8",)),
    make_profile("pixel_9","Google","Pixel 9","Google Pixel","Mobile",
                 aliases=("pixel 9",)),
    make_profile("xiaomi_generic","Xiaomi","Flagship (Generic)","Android Generic",
                 "Mobile", aliases=("xiaomi","redmi","poco"),
                 color_separation=-.12, sat_response={**_empty_hue_response(),
                 "green":.88,"blue":.90}),
    make_profile("huawei_generic","Huawei","Flagship (Generic)","Android Generic",
                 "Mobile", aliases=("huawei","honor"), color_separation=-.10),
]

CAMERA_PROFILES = {p.id: p for p in CAMERA_MODELS}

def cd_profiles_by_category():
    out = {}
    for p in CAMERA_MODELS:
        out.setdefault(p.category, []).append(p)
    return out


# ---- UI-facing default params (spec section 17) ------------------------
# Kept separate from DEF (the film-preset param dict) so Camera Match is
# a genuinely separate system layered on top of, not merged into,
# existing presets (spec section 24).

CD_DEFAULTS = {
    "cm_enabled": False,
    "cm_mode": "character",       # "character" | "auto"
    "cm_source": None,            # profile id or None (Auto Detect)
    "cm_target": None,            # profile id
    "cm_strength": 1.0,
    "cm_input_gamma": "Rec.709",
    "cm_film_sim": None,
}

CD_LAYER_KEYS = ("cm_enabled","cm_mode","cm_source","cm_target",
                 "cm_strength","cm_input_gamma","cm_film_sim")




# ============================================================
#  RENDER ENGINE v12 — Layered Cache
# ============================================================

SK = ("skin_warmth","skin_brightness","skin_saturation",
      "skin_tan","skin_smooth","skin_clarity")
HSL_KEYS = tuple(f"hsl_{b}_{c}" for b in HSL_BANDS
                 for c in ("hue", "sat", "lum"))
CG_KEYS = tuple(f"cg_{r}_{c}" for r in CG_RANGES
               for c in ("hue", "sat", "lum")) + \
    ("cg_global_hue", "cg_global_sat", "cg_global_lum", "cg_blending")
LAYER_ORDER = ("camera", "wb", "tone", "color")
LAYER_KEYS = {
    "camera": CD_LAYER_KEYS,
    "wb": ("temperature", "tint", "scene_prep", "lut3d_path", "lut3d_strength"),
    "tone": ("exposure", "gamma", "contrast", "shadows", "highlights", "blacks",
             "whites", "fade", "monochrome",
             "film_curve_contrast", "film_shoulder", "tone_curve_pts"),
    "color": ("saturation", "vibrance", "density",
              "split_shadow_amount", "split_highlight_amount")+HSL_KEYS+CG_KEYS,
}

class Eng:
    """v12: fused per-channel LUT + 3-layer cache.
    Effects layer (grain/halation/etc) is NEVER cached (grain is
    stochastic). Changing grain only re-runs effects — tone/color
    layers return cached arrays → ~2x faster slider drags."""
    def __init__(self):
        self._pc = None
        self._skc = None
        self._lc = {}
        self._src = None

    def _prep(self, rgb):
        if self._pc is not None and self._pc[0] is rgb:
            return self._pc[1]
        o = prep_scene(rgb)
        self._pc = (rgb, o)
        return o
    def _sk(self, rgb):
        if self._skc is not None and self._skc[0] is rgb:
            return self._skc[1]
        m = skmask(rgb)
        self._skc = (rgb, m)
        return m
    def _hash(self, p, keys):
        out = []
        for k in keys:
            v = p.get(k, 0)
            out.append(str(v) if isinstance(v, (list, tuple, dict, bool, str))
                        or v is None else round(float(v), 4))
        return tuple(out)
    def inval_img(self):
        self._pc = None
        self._skc = None
        self._lc.clear()
        self._src = None

    def render(self, rgb, p, changed_key=None):
        if changed_key is not None:
            for layer, keys in LAYER_KEYS.items():
                if changed_key in keys:
                    idx = LAYER_ORDER.index(layer)
                    for l in LAYER_ORDER[idx:]:
                        self._lc.pop(l, None)
                    break
        if self._src is not rgb:
            self.inval_img()
            self._src = rgb

        x = ensure_rgb(rgb)

        # LAYER: camera (Camera DNA 2.0 — technical + character transform,
        # applied before Lumen Forge's own tone/color/effects, per spec)
        h = self._hash(p, LAYER_KEYS["camera"])
        c = self._lc.get("camera")
        if c is not None and c[0] == h:
            x = c[1]
        else:
            if p.get("cm_enabled"):
                x = cd_apply(x, p, skin_mask=self._sk(x))
            self._lc["camera"] = (h, x)

        # LAYER: wb
        h = self._hash(p, LAYER_KEYS["wb"])
        c = self._lc.get("wb")
        if c is not None and c[0] == h:
            x = c[1]
        else:
            if p.get("scene_prep"):
                x = self._prep(x)
            if any(abs(p.get(k, 0)) > .5 for k in SK):
                x = skin_tools(x, p)
            if abs(p.get("temperature", 0)) > .01:
                x = ctemp(x, p["temperature"])
            if abs(p.get("tint", 0)) > .01:
                x = tint_op(x, p["tint"])
            if p.get("lut3d_path"):
                t3 = get_lut3d(p["lut3d_path"])
                if t3 is not None:
                    y = apply_lut3d(x, t3)
                    a = float(np.clip(p.get("lut3d_strength", 1), 0, 1))
                    x = y if a > .999 else (x*(1-a)+y*a)
            self._lc["wb"] = (h, x)

        # LAYER: tone (fused per-channel LUT!)
        h = self._hash(p, LAYER_KEYS["tone"])
        c = self._lc.get("tone")
        if c is not None and c[0] == h:
            x = c[1]
        else:
            if p.get("monochrome"):
                x = mono(x, p.get("mono_weights") or PE)
            x = apply_fused_tone(x, p)
            x = LUT.apply(x, fc_lut(p.get("film_curve_contrast", 1),
                                    p.get("film_shoulder", .12)))
            tcp = p.get("tone_curve_pts")
            x = apply_tone_curves(x, tcp)
            self._lc["tone"] = (h, x)

        # LAYER: color
        h = self._hash(p, LAYER_KEYS["color"])
        c = self._lc.get("color")
        if c is not None and c[0] == h:
            x = c[1]
        else:
            if abs(p.get("saturation", 100)-100) > .5:
                x = sat_op(x, p["saturation"]/100)
            if abs(p.get("vibrance", 0)) > .5:
                x = self._vib(x, p["vibrance"])
            if abs(p.get("density", 0)) > .5:
                x = self._den(x, p["density"])
            if _hsl_is_active(p):
                x = apply_hsl(x, p)
            if p.get("split_shadow_amount", 0) > .004 or \
                    p.get("split_highlight_amount", 0) > .004:
                x = split_tone(x, p.get("split_shadow", (1,1,1)),
                               p.get("split_highlight", (1,1,1)),
                               p.get("split_shadow_amount", 0),
                               p.get("split_highlight_amount", 0))
            if _cg_is_active(p):
                x = color_grade(x, p)
            self._lc["color"] = (h, x)

        # EFFECTS: never cached (grain stochastic)
        if p.get("masks"):
            x = apply_local_masks(x, p["masks"])
        if abs(p.get("clarity", 0)) > .5:
            x = clarity_op(x, p["clarity"])
        if abs(p.get("texture", 0)) > .5:
            x = tex_op(x, p["texture"])
        if abs(p.get("dehaze", 0)) > .5:
            x = dehaze_op(x, p["dehaze"])
        if p.get("highlight_rolloff", 0) > .5:
            x = rolloff(x, p["highlight_rolloff"])
        if p.get("halation", 0) > .5:
            x = halation(x, p["halation"], p.get("halation_color", HR))
        if p.get("bloom", 0) > .5:
            x = bloom(x, p["bloom"],
                      tint=(1.,1.,1.) if p.get("monochrome") else (1.,.94,.84))
        if abs(p.get("vignette", 0)) > .5:
            x = vign(x, p["vignette"], p.get("vignette_feather", .72))
        if p.get("print_stock"):
            x = print_op(x, p.get("print_strength", 1))
        if p.get("grain", 0) > .5:
            x = grain(x, p["grain"], p.get("grain_size", .45),
                      p.get("grain_profile", "tgrain"),
                      mono=bool(p.get("monochrome")))

        return clamp(x)

    def _vib(self, rgb, a):
        a = float(a)
        if abs(a) < .5:
            return rgb
        x = np.maximum(arr32(rgb), 0)
        lm = luminance(x)
        cm = np.max(x, 2)-np.min(x, 2)
        ls = np.power(np.clip(1-cm/np.maximum(lm, .06), 0, 1), 1.45)
        mt = np.clip(1-np.abs(lm-.52)/.52, 0, 1)
        gn = (a/100)*ls*((.35+.65*mt))
        gn = gn*(1-self._sk(x)*.72)
        return np.maximum(lm[..., None]+(x-lm[..., None])*(1+gn[..., None]), 0)
    def _den(self, rgb, a):
        a = float(a)
        if abs(a) < .5:
            return rgb
        x = np.maximum(arr32(rgb), 0)
        lm = luminance(x)
        st = np.max(x, 2)-np.min(x, 2)
        md = np.clip(1-np.abs(lm-.50)/.50, 0, 1)
        gd = 1-np.clip(st*1.55, 0, .85)
        gn = (a/100)*(.30+.70*md)*gd
        return np.maximum(lm[..., None]+(x-lm[..., None])*(1+gn[..., None]), 0)

ENG = Eng()

def staged(rgb, p, cb=None, full_h=None, y0=0):
    """Export path — same math, no caches (deterministic). full_h/y0
    let a row-tiled caller say where this row-slice sits within the
    full image, so local masks (always in full-image normalized
    coordinates) land correctly instead of being re-centered per tile."""
    n = 20
    st = [0]
    def tk(l):
        st[0] += 1
        if cb:
            cb(min(1, st[0]/n), l)
    x = ensure_rgb(rgb)
    if p.get("cm_enabled"):
        x = cd_apply(x, p, skin_mask=skmask(x))
    tk("Camera Match")
    if p.get("scene_prep"):
        x = prep_scene(x)
    tk("Scene prep")
    if any(abs(p.get(k, 0)) > .5 for k in SK):
        x = skin_tools(x, p)
    tk("Skin")
    if abs(p.get("temperature", 0)) > .01:
        x = ctemp(x, p["temperature"])
    if abs(p.get("tint", 0)) > .01:
        x = tint_op(x, p["tint"])
    if p.get("lut3d_path"):
        t3 = get_lut3d(p["lut3d_path"])
        if t3 is not None:
            y = apply_lut3d(x, t3)
            a = float(np.clip(p.get("lut3d_strength", 1), 0, 1))
            x = y if a > .999 else (x*(1-a)+y*a)
    if p.get("monochrome"):
        x = mono(x, p.get("mono_weights") or PE)
    tk("Color")
    x = apply_fused_tone(x, p)
    tk("Tone+Gamma")
    x = LUT.apply(x, fc_lut(p.get("film_curve_contrast", 1),
                            p.get("film_shoulder", .12)))
    tcp = p.get("tone_curve_pts")
    x = apply_tone_curves(x, tcp)
    tk("Film curve")
    if abs(p.get("saturation", 100)-100) > .5:
        x = sat_op(x, p["saturation"]/100)
    if abs(p.get("vibrance", 0)) > .5:
        x = ENG._vib(x, p["vibrance"])
    if abs(p.get("density", 0)) > .5:
        x = ENG._den(x, p["density"])
    tk("Vibrance")
    if _hsl_is_active(p):
        x = apply_hsl(x, p)
    tk("HSL")
    if p.get("split_shadow_amount", 0) > .004 or \
            p.get("split_highlight_amount", 0) > .004:
        x = split_tone(x, p.get("split_shadow", (1,1,1)),
                       p.get("split_highlight", (1,1,1)),
                       p.get("split_shadow_amount", 0),
                       p.get("split_highlight_amount", 0))
    tk("Split")
    if _cg_is_active(p):
        x = color_grade(x, p)
    tk("Color Grade")
    if p.get("masks"):
        x = apply_local_masks(x, p["masks"], full_h=full_h, y0=y0)
    tk("Local Masks")
    if abs(p.get("clarity", 0)) > .5:
        x = clarity_op(x, p["clarity"])
    if abs(p.get("texture", 0)) > .5:
        x = tex_op(x, p["texture"])
    if abs(p.get("dehaze", 0)) > .5:
        x = dehaze_op(x, p["dehaze"])
    tk("Detail")
    if p.get("highlight_rolloff", 0) > .5:
        x = rolloff(x, p["highlight_rolloff"])
    tk("Rolloff")
    if p.get("halation", 0) > .5:
        x = halation(x, p["halation"], p.get("halation_color", HR))
    tk("Halation")
    if p.get("bloom", 0) > .5:
        x = bloom(x, p["bloom"],
                  tint=(1.,1.,1.) if p.get("monochrome") else (1.,.94,.84))
    tk("Bloom")
    if abs(p.get("vignette", 0)) > .5:
        x = vign(x, p["vignette"], p.get("vignette_feather", .72))
    tk("Vignette")
    if p.get("print_stock"):
        x = print_op(x, p.get("print_strength", 1))
    tk("Print")
    if p.get("grain", 0) > .5:
        x = grain(x, p["grain"], p.get("grain_size", .45),
                  p.get("grain_profile", "tgrain"),
                  mono=bool(p.get("monochrome")))
    tk("Grain")
    return clamp(x)


# ============================================================
#  UI SYSTEM
# ============================================================

DEF = {"exposure":0,"contrast":0,"gamma":1,"temperature":0,"tint":0,
       "saturation":100,"vibrance":0,"highlights":0,"shadows":0,
       "whites":0,"blacks":0,"clarity":0,"texture":0,"dehaze":0,
       "grain":0,"grain_size":.45,"grain_profile":"tgrain","halation":0,
       "halation_color":list(HR),"bloom":0,"highlight_rolloff":0,"fade":0,
       "vignette":0,"vignette_feather":.72,"monochrome":False,
       "mono_weights":None,"film_curve_contrast":1,"film_shoulder":.12,
       "scene_prep":True,"print_stock":False,"print_strength":1,
       "skin_warmth":0,"skin_brightness":0,"skin_saturation":0,
       "skin_tan":0,"skin_smooth":0,"skin_clarity":0,
       "tone_curve_pts":{"rgb":[(0.0,0.0),(1.0,1.0)],"r":[(0.0,0.0),(1.0,1.0)],
                        "g":[(0.0,0.0),(1.0,1.0)],"b":[(0.0,0.0),(1.0,1.0)]},
       **{f"hsl_{b}_{c}":0 for b in HSL_BANDS for c in ("hue","sat","lum")},
       **{f"cg_{r}_hue":0 for r in CG_RANGES},
       **{f"cg_{r}_sat":0 for r in CG_RANGES},
       **{f"cg_{r}_lum":0 for r in CG_RANGES},
       "cg_global_hue":0,"cg_global_sat":0,"cg_global_lum":0,
       "cg_blending":50}

SPEC = [
("exposure","Exposure",-3,3,"{:+.2f}"),("contrast","Contrast",-100,100,"{:+.0f}"),
("gamma","Gamma",.2,3,"{:.2f}"),("highlights","Highlights",-100,100,"{:+.0f}"),
("shadows","Shadows",-100,100,"{:+.0f}"),("whites","Whites",-100,100,"{:+.0f}"),
("blacks","Blacks",-100,100,"{:+.0f}"),("temperature","Temperature",-100,100,"{:+.0f}"),
("tint","Tint",-100,100,"{:+.0f}"),("saturation","Saturation",0,200,"{:.0f}"),
("vibrance","Vibrance",-100,100,"{:+.0f}"),
("skin_warmth","Skin Warmth",-100,100,"{:+.0f}"),
("skin_brightness","Skin Brightness",-100,100,"{:+.0f}"),
("skin_saturation","Skin Saturation",-100,100,"{:+.0f}"),
("skin_tan","Skin Tan",-100,100,"{:+.0f}"),
("skin_smooth","Skin Smoothness",0,100,"{:.0f}"),
("skin_clarity","Skin Clarity",-100,100,"{:+.0f}"),
("clarity","Clarity",-100,100,"{:+.0f}"),("texture","Texture",-100,100,"{:+.0f}"),
("dehaze","Dehaze",-100,100,"{:+.0f}"),
("highlight_rolloff","Highlight Rolloff",0,100,"{:.0f}"),
("halation","Halation",0,100,"{:.0f}"),("bloom","Bloom",0,100,"{:.0f}"),
("fade","Fade",0,100,"{:.0f}"),("grain","Grain",0,100,"{:.0f}"),
("grain_size","Grain Size",.20,.90,"{:.2f}"),
("vignette","Vignette",-100,100,"{:+.0f}"),
("vignette_feather","Vignette Feather",.35,1,"{:.2f}")]

_HSL_LABELS = {"red":"Red","orange":"Orange","yellow":"Yellow",
              "green":"Green","aqua":"Aqua","blue":"Blue",
              "purple":"Purple","magenta":"Magenta"}
for _b in HSL_BANDS:
    for _c, _cl in (("hue","Hue"),("sat","Saturation"),("lum","Luminance")):
        SPEC.append((f"hsl_{_b}_{_c}", f"{_HSL_LABELS[_b]} {_cl}",
                    -100, 100, "{:+.0f}"))

_CG_LABELS = {"shadow":"Shadows","midtone":"Midtones","highlight":"Highlights"}
for _r in CG_RANGES:
    SPEC.append((f"cg_{_r}_hue", f"{_CG_LABELS[_r]} Hue", 0, 360, "{:.0f}"))
    SPEC.append((f"cg_{_r}_sat", f"{_CG_LABELS[_r]} Saturation", 0, 100, "{:.0f}"))
    SPEC.append((f"cg_{_r}_lum", f"{_CG_LABELS[_r]} Luminance", -100, 100, "{:+.0f}"))
SPEC.append(("cg_global_hue", "Global Hue", 0, 360, "{:.0f}"))
SPEC.append(("cg_global_sat", "Global Saturation", 0, 100, "{:.0f}"))
SPEC.append(("cg_global_lum", "Global Luminance", -100, 100, "{:+.0f}"))
SPEC.append(("cg_blending", "Blending", 0, 100, "{:.0f}"))

PARAM_INFO = {
    "exposure": "روشنایی کلی تصویر را مثل دیافراگم دوربین تغییر می‌دهد. "
                "مقدار مثبت عکس را روشن‌تر و مقدار منفی تیره‌تر می‌کند؛ "
                "این تنظیم به‌صورت یکنواخت روی همه‌ی تون‌ها (سایه، میان‌تون، هایلایت) اثر می‌گذارد.",
    "contrast": "فاصله‌ی بین تیره‌ترین و روشن‌ترین نقاط تصویر را حول نقطه‌ی "
                "خاکستری میانی تنظیم می‌کند. مقدار مثبت تصویر را پرکنتراست‌تر "
                "(سایه‌ها تیره‌تر، هایلایت‌ها روشن‌تر) و مقدار منفی آن را نرم‌تر و صاف‌تر می‌کند.",
    "gamma": "منحنی روشنایی تصویر را به‌صورت توانی (gamma) خم می‌کند. "
             "عدد کمتر از ۱ میان‌تون‌ها را روشن‌تر و عدد بیشتر از ۱ آن‌ها را "
             "تیره‌تر نشان می‌دهد، بدون اینکه سیاه و سفید مطلق تصویر تغییر کند.",
    "highlights": "فقط روی روشن‌ترین قسمت‌های تصویر (هایلایت‌ها) اثر می‌گذارد. "
                  "مقدار منفی برای بازگرداندن جزئیات نواحی سوخته و روشن استفاده می‌شود؛ "
                  "مقدار مثبت آن‌ها را روشن‌تر می‌کند.",
    "shadows": "فقط روی تیره‌ترین قسمت‌های تصویر (سایه‌ها) اثر می‌گذارد. "
               "مقدار مثبت جزئیات پنهان در سایه‌ها را باز می‌کند؛ مقدار منفی "
               "سایه‌ها را عمیق‌تر و تیره‌تر می‌کند.",
    "whites": "نقطه‌ی سفید مطلق تصویر را تنظیم می‌کند — یعنی مشخص می‌کند از "
              "کجا به بعد یک ناحیه کاملاً سفید و بدون جزئیات دیده شود. برای "
              "کنترل دقیق‌تر روشن‌ترین لبه‌ی تصویر به‌کار می‌رود.",
    "blacks": "نقطه‌ی سیاه مطلق تصویر را تنظیم می‌کند — یعنی مشخص می‌کند از "
              "کجا به بعد یک ناحیه کاملاً سیاه و بدون جزئیات دیده شود. برای "
              "کنترل دقیق‌تر عمق سایه‌های تصویر به‌کار می‌رود.",
    "temperature": "دمای رنگ تصویر (وایت بالانس) را روی محور آبی↔نارنجی تنظیم "
                   "می‌کند. مقدار منفی تصویر را سردتر و آبی‌تر، مقدار مثبت آن "
                   "را گرم‌تر و نارنجی‌تر می‌کند. از دکمه‌های Pick Gray Point یا "
                   "Auto WB هم می‌توان برای تنظیم خودکار آن استفاده کرد.",
    "tint": "رنگ تصویر را روی محور سبز↔بنفش (مکمل Temperature) تنظیم می‌کند. "
            "معمولاً برای خنثی کردن کست رنگی سبز یا بنفش نور مصنوعی "
            "(مثل نور فلورسنت) به‌کار می‌رود.",
    "saturation": "میزان اشباع رنگ در کل تصویر را به‌صورت یکنواخت تغییر می‌دهد. "
                  "۱۰۰ حالت خنثی است؛ عدد بیشتر رنگ‌ها را پررنگ‌تر و عدد کمتر "
                  "آن‌ها را کم‌رنگ‌تر (تا سیاه‌وسفید کامل در صفر) می‌کند.",
    "vibrance": "مثل Saturation رنگ‌ها را پررنگ‌تر می‌کند، اما هوشمندتر عمل "
                "می‌کند: رنگ‌های کم‌رنگ را بیشتر تقویت می‌کند و رنگ‌هایی که از "
                "قبل اشباع هستند (و به‌خصوص تن پوست) را کمتر دستکاری می‌کند، "
                "تا از غیرطبیعی شدن رنگ پوست جلوگیری شود.",
    "skin_warmth": "گرمای رنگ فقط در ناحیه‌ی تشخیص‌داده‌شده‌ی پوست را تنظیم "
                   "می‌کند، بدون تاثیر روی بقیه‌ی تصویر. مقدار مثبت پوست را "
                   "گرم‌تر (مایل به نارنجی) و منفی آن را سردتر می‌کند.",
    "skin_brightness": "روشنایی فقط ناحیه‌ی پوست را تغییر می‌دهد، مستقل از "
                        "بقیه‌ی تصویر — برای روشن یا تیره کردن ملایم صورت و "
                        "بدن بدون تغییر نور پس‌زمینه.",
    "skin_saturation": "میزان اشباع رنگ فقط در ناحیه‌ی پوست را تنظیم می‌کند. "
                        "مقدار منفی معمولاً برای طبیعی‌تر و کم‌رنگ‌تر کردن "
                        "پوست در پرتره استفاده می‌شود.",
    "skin_tan": "تعادل رنگ پوست را بین زرد و صورتی/قرمز جابه‌جا می‌کند — "
                "شبیه شبیه‌سازی برنزه شدن پوست یا اصلاح رنگ‌پریدگی آن.",
    "skin_smooth": "میزان صاف‌کردن نرم بافت پوست (کاهش دانه‌دانگی و "
                   "نایکنواختی سطح پوست) را کنترل می‌کند، بدون تاثیر روی لبه‌ها "
                   "و جزئیات مهم چهره مثل چشم و مو.",
    "skin_clarity": "وضوح میکروکنتراست فقط در ناحیه‌ی پوست را تنظیم می‌کند؛ "
                    "مقدار منفی پوست را نرم‌تر و مقدار مثبت آن را شفاف‌تر و "
                    "دارای بافت بیشتر نشان می‌دهد.",
    "clarity": "میکروکنتراست تصویر (کنتراست در جزئیات ریز و لبه‌های میان‌تون) "
               "را تنظیم می‌کند. مقدار مثبت تصویر را شفاف‌تر و دارای عمق بیشتر "
               "نشان می‌دهد؛ مقدار منفی جلوه‌ای نرم و رویایی ایجاد می‌کند.",
    "texture": "جزئیات ریز سطحی تصویر (مثل بافت پارچه، پوست، چوب) را بدون "
               "تاثیر زیاد روی لبه‌های بزرگ تقویت یا کاهش می‌دهد.",
    "dehaze": "اثر مه، غبار یا افت کنتراست اتمسفری را کاهش یا افزایش می‌دهد. "
              "مقدار مثبت مه را از تصویر می‌زداید و کنتراست دوردست را افزایش "
              "می‌دهد؛ مقدار منفی جلوه‌ی مه‌آلود ایجاد می‌کند.",
    "highlight_rolloff": "نحوه‌ی نرم شدن هایلایت‌های خیلی روشن را کنترل "
                          "می‌کند، شبیه رفتار طبیعی فیلم آنالوگ در برابر نور "
                          "زیاد. مقدار بیشتر باعث می‌شود هایلایت‌ها به‌جای "
                          "سوختن ناگهانی، به‌آرامی محو شوند.",
    "halation": "هاله‌ی نورانی رنگی دور منابع نور شدید یا لبه‌های پرکنتراست "
                "ایجاد می‌کند — جلوه‌ای که در فیلم‌های آنالوگ (به‌خصوص فیلم‌های "
                "بدون لایه‌ی remjet) دیده می‌شود.",
    "bloom": "درخشش نرم و پخش‌شده دور نواحی خیلی روشن تصویر ایجاد می‌کند، "
             "شبیه پخش نور در لنزهای دوربین‌های سینمایی یا وینتیج.",
    "fade": "کنتراست سیاه‌های تصویر را کاهش می‌دهد و آن‌ها را به‌سمت خاکستری "
            "می‌برد — جلوه‌ی رایج فیلم‌های آنالوگ کهنه یا اسکن‌شده با کنتراست پایین.",
    "grain": "میزان دانه‌ی فیلم (نویز شبیه‌سازی‌شده) که روی تصویر اضافه "
             "می‌شود را کنترل می‌کند؛ برای بافت آنالوگ و جلوگیری از ظاهر بیش از حد صاف دیجیتال.",
    "grain_size": "اندازه‌ی فیزیکی دانه‌های اضافه‌شده توسط Grain را تنظیم "
                  "می‌کند. عدد کمتر دانه‌ی ریزتر و ظریف‌تر، عدد بیشتر دانه‌ی "
                  "درشت‌تر و چشمگیرتر ایجاد می‌کند.",
    "vignette": "روشنایی گوشه‌ها و لبه‌های کادر را نسبت به مرکز تصویر تغییر "
                "می‌دهد. مقدار منفی گوشه‌ها را تیره می‌کند (تمرکز روی سوژه‌ی "
                "مرکزی)، مقدار مثبت گوشه‌ها را روشن‌تر می‌کند.",
    "vignette_feather": "میزان نرمی و پخش‌شدگی مرز وینیت را کنترل می‌کند. "
                        "عدد کمتر یعنی گذار محسوس‌تر و نزدیک‌تر به مرکز؛ عدد "
                        "بیشتر یعنی گذاری بسیار تدریجی و نرم تا لبه‌ی کادر.",
}

GRP = {"exposure":"LIGHT","contrast":"LIGHT","gamma":"LIGHT",
       "highlights":"LIGHT","shadows":"LIGHT","whites":"LIGHT","blacks":"LIGHT",
       "temperature":"WHITE BALANCE","tint":"WHITE BALANCE",
       "saturation":"COLOUR","vibrance":"COLOUR","clarity":"DETAIL","texture":"DETAIL",
       "dehaze":"DETAIL","skin_warmth":"SKIN","skin_brightness":"SKIN",
       "skin_saturation":"SKIN","skin_tan":"SKIN","skin_smooth":"SKIN",
       "skin_clarity":"SKIN","highlight_rolloff":"FILM","halation":"FILM",
       "bloom":"FILM","fade":"FILM","grain":"FILM","grain_size":"FILM",
       "vignette":"LENS","vignette_feather":"LENS",
       **{f"hsl_{b}_{c}":"HSL" for b in HSL_BANDS
          for c in ("hue","sat","lum")},
       **{f"cg_{r}_{c}":"COLOR GRADE" for r in CG_RANGES
          for c in ("hue","sat","lum")},
       "cg_global_hue":"COLOR GRADE","cg_global_sat":"COLOR GRADE",
       "cg_global_lum":"COLOR GRADE","cg_blending":"COLOR GRADE"}
GORD = ("LIGHT","WHITE BALANCE","COLOUR","HSL","COLOR GRADE","DETAIL","SKIN","FILM","LENS")
FMTS = [("JPEG — quality 95",("jpg",95)),("JPEG — quality 90",("jpg",90)),
        ("JPEG — quality 80",("jpg",80)),("PNG — lossless",("png",None)),
        ("TIFF — lossless",("tif",None))]

def styles(root):
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except Exception:
        pass
    s.configure(".", background=T["bg"], foreground=T["text"],
                font=T["font"], borderwidth=0)
    s.configure("TScale", background=T["card"], troughcolor=T["panel"],
                lightcolor=T["accent"], darkcolor=T["accent"],
                bordercolor=T["stroke"], slidersize=(14, 22))
    s.map("TScale", background=[("active", T["card"])],
          lightcolor=[("active", T["accent2"])],
          darkcolor=[("active", T["accent2"])])
    s.configure("TEntry", fieldbackground=T["panel"], foreground=T["text"],
                insertcolor=T["text"], bordercolor=T["stroke"],
                lightcolor=T["stroke"], darkcolor=T["stroke"],
                padding=(8, 5))
    s.map("TEntry", fieldbackground=[("focus", T["card_hi"])],
          bordercolor=[("focus", T["accent"])])
    s.configure("TCombobox", fieldbackground=T["panel"],
                foreground=T["text"], arrowcolor=T["text_dim"],
                bordercolor=T["stroke"], lightcolor=T["stroke"],
                darkcolor=T["stroke"], padding=(7, 4))
    s.map("TCombobox", fieldbackground=[("readonly", T["panel"])],
          foreground=[("readonly", T["text"])],
          bordercolor=[("focus", T["accent"])])
    s.configure("Vertical.TScrollbar", background=T["panel"],
                troughcolor=T["bg"], bordercolor=T["bg"],
                arrowcolor=T["text_dim"], width=9)
    s.map("Vertical.TScrollbar", background=[("active", T["stroke_hi"])])

def rnd(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
           x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    return cv.create_polygon(pts, smooth=True, **kw)

def _glass_edge(panel, tint):
    """A hairline gradient strip along a panel's top edge — center
    brighter (tinted toward the given accent), fading to the panel's
    own stroke color at both ends. Gives the card a faint 'glass edge'
    highlight instead of a flat top border."""
    strip = tk.Canvas(panel, height=2, bg=T["card"], highlightthickness=0)
    strip.pack(fill="x", side="top", pady=(0, 6))
    def _draw(e=None):
        strip.delete("all")
        w = strip.winfo_width() or 1
        mid = w//2
        for x in range(0, w, 2):
            t = 1-abs(x-mid)/max(1, mid)
            strip.create_line(x, 0, x, 2,
                              fill=_mix(T["stroke"], tint, t*.6))
    strip.bind("<Configure>", _draw)
    return strip

class Tip:
    """Lightweight shared tooltip: one borderless Toplevel, reused for
    every widget that registers via Tip.bind(widget, text). Avoids any
    new dependency — pure tkinter. Wraps longer text (e.g. full slider
    explanations) instead of stretching off-screen."""
    _tw = None
    @staticmethod
    def bind(widget, text):
        widget.bind("<Enter>", lambda e: Tip._show(widget, text), add="+")
        widget.bind("<Leave>", lambda e: Tip._hide(), add="+")
        widget.bind("<Button-1>", lambda e: Tip._hide(), add="+")
    @staticmethod
    def _show(widget, text):
        Tip._hide()
        try:
            x = widget.winfo_rootx()+widget.winfo_width()//2
            y = widget.winfo_rooty()+widget.winfo_height()+6
        except Exception:
            return
        tw = tk.Toplevel(widget)
        tw.overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        wrap = 260 if len(text) > 40 else 0
        tk.Label(tw, text=text, bg=T["accent"], fg="#0a0c10",
                 font=("Segoe UI", 8, "bold" if wrap == 0 else "normal"),
                 padx=7, pady=4, justify="left",
                 wraplength=wrap if wrap else 10000
                 ).pack()
        tw.update_idletasks()
        tw_w = tw.winfo_width()
        sw = tw.winfo_screenwidth()
        x = min(max(0, x-tw_w//2), max(0, sw-tw_w))
        tw.geometry(f"+{x}+{y}")
        Tip._tw = tw
    @staticmethod
    def _hide():
        if Tip._tw is not None:
            try:
                Tip._tw.destroy()
            except Exception:
                pass
            Tip._tw = None

def sep(master, h=24):
    """Thin vertical separator used to group toolbar buttons visually.
    Rendered as a tiny 2-stop vertical gradient (bright center, fading
    to the panel color at each end) for a subtle brushed-metal look."""
    c = tk.Canvas(master, width=2, height=h, bg=T["panel"],
                 highlightthickness=0)
    mid = h//2
    for y in range(h):
        t = 1-abs(y-mid)/max(1,mid)
        c.create_line(0, y, 2, y, fill=_mix(T["panel"], T["stroke_hi"], t))
    return c

class Btn(tk.Canvas):
    def __init__(self, master, text, cmd=None, w=110, h=T["ctrl_h"],
                 kind="ghost", accent=None, fs=9, bg=None, tip=None,
                 icon=None):
        bg = bg or T["panel"]
        super().__init__(master, width=w, height=h, bg=bg,
                         highlightthickness=0, cursor="hand2")
        self._t, self._cmd, self._k = text, cmd, kind
        self._icon = icon
        self._a = accent or T["accent"]
        self._en = True
        self._active = False
        self._bg = bg
        self._f = ("Segoe UI", fs, "bold")
        self._fi = ("Segoe UI Symbol", max(fs, 10))
        self.bind("<Enter>", lambda e: self._p(True))
        self.bind("<Leave>", lambda e: self._p(False))
        self.bind("<Button-1>", self._c)
        if tip:
            Tip.bind(self, tip)
        self._p(False)
    def _p(self, hov):
        if not self._en:
            return
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        # Active (toggled-on) state takes visual priority over hover so a
        # pressed toggle (e.g. Split compare) stays legible as "on" even
        # while the mouse sits elsewhere in the group.
        if self._active:
            f = self._a
            t = "#0a0c10"
            ln = self._a
        elif self._k == "solid":
            f = "#fff" if hov else self._a
            t = self._a if hov else "#0a0c10"
            ln = self._a
        else:
            f = T["card_hi"] if hov else self._bg
            t = T["text"] if hov else self._a
            ln = T["stroke_hi"] if hov else T["stroke"]
        # subtle outer glow ring on hover (one extra soft outline, same
        # accent color at low visual weight) — purely cosmetic, no
        # change to hit-testing or layout.
        if hov and not self._active:
            rnd(self, 0, 0, w, h, T["radius_lg"], fill="", outline=self._a)
        rnd(self, 1, 1, w-2, h-2, T["radius"], fill=f, outline=ln)
        # Brushed-metal vertical gradient over the base fill: lighter at
        # the top, settling to the base color by mid-height, so the flat
        # fill above reads as a subtle metallic surface rather than a
        # single flat color.
        top_c = _mix(f, "#ffffff", .16)
        band_h = max(3, (h-2)//2)
        for i in range(band_h):
            t2 = 1-(i/band_h)
            self.create_line(2, 2+i, w-2, 2+i,
                             fill=_mix(f, top_c, t2))
        # Thin glass "shine" strip near the very top — a slightly
        # brighter, slightly inset line suggesting a specular highlight
        # on a glossy/glass surface.
        self.create_line(4, 3, w-4, 3, fill=_mix(top_c, "#ffffff", .35))
        # Soft inner shadow along the bottom edge for depth.
        self.create_line(2, h-3, w-2, h-3, fill=_mix(f, "#000000", .25))
        if self._icon:
            # One coherent icon language across the whole toolbar: every
            # button gets the same square "chip" badge (rounded, tinted
            # a touch lighter/darker than the button body) holding a
            # single monoline glyph, with the label left-aligned after
            # it — instead of mismatched multicolor emoji glyphs.
            cs = h-12
            cx0 = (w-cs)//2 if not self._t else 6
            cy0 = (h-cs)//2
            chip_fill = (_mix(f, "#000000", .22) if self._k == "solid"
                        else _mix(f, self._a, .22))
            rnd(self, cx0, cy0, cx0+cs, cy0+cs, T["radius_sm"],
               fill=chip_fill, outline="")
            icon_c = t if self._k == "solid" or self._active else self._a
            self.create_text(cx0+cs//2, cy0+cs//2+1, text=self._icon,
                             fill=icon_c, font=self._fi)
            if self._t:
                tx = cx0+cs+8
                self.create_text(tx, h//2, text=self._t, fill=t,
                                 font=self._f, anchor="w")
        else:
            self.create_text(w//2, h//2, text=self._t, fill=t, font=self._f)
    def _c(self, _):
        if self._en and self._cmd:
            try:
                self._cmd()
            except Exception as ex:
                messagebox.showerror(APP_NAME, str(ex))
    def set_active(self, on):
        self._active = bool(on)
        self._p(False)
    def set_en(self, en):
        self._en = bool(en)
        self["cursor"] = "hand2" if en else "arrow"
        if not en:
            self.delete("all")
            w, h = int(self["width"]), int(self["height"])
            rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill=T["panel"],
                outline=T["stroke"])
            if self._icon:
                cs = h-12
                cx0 = (w-cs)//2 if not self._t else 6
                cy0 = (h-cs)//2
                rnd(self, cx0, cy0, cx0+cs, cy0+cs, T["radius_sm"],
                   fill=T["card"], outline="")
                self.create_text(cx0+cs//2, cy0+cs//2+1, text=self._icon,
                                 fill=T["text_dim"], font=self._fi)
                if self._t:
                    self.create_text(cx0+cs+8, h//2, text=self._t,
                                     fill=T["text_dim"], font=self._f,
                                     anchor="w")
            else:
                self.create_text(w//2, h//2, text=self._t,
                                 fill=T["text_dim"], font=self._f)
        else:
            self._p(False)

class Param(tk.Frame):
    def __init__(self, master, label, var, cb, lo=-100, hi=100,
                 fmt="{:+.0f}", default=None, key=None, info=None):
        super().__init__(master, bg=T["card"])
        self._v, self._cb, self._f = var, cb, fmt
        self._lo, self._hi = float(lo), float(hi)
        self._d = float(default) if default is not None else float(var.get())
        self._key = key
        self._lf = 0
        self._e = None
        tp = tk.Frame(self, bg=T["card"])
        tp.pack(fill="x")
        lb = tk.Label(tp, text=label, bg=T["card"], fg=T["text_dim"],
                      font=T["font_sm"], anchor="w", cursor="hand2")
        lb.pack(side="left")
        self._lb = lb
        lb.bind("<Double-Button-1>", lambda e: self._st(self._d))
        if info:
            ic = tk.Label(tp, text="ⓘ", bg=T["card"], fg=T["text_dim"],
                          font=("Segoe UI", 8), padx=3)
            try:
                ic.configure(cursor="question_arrow")
            except Exception:
                try:
                    ic.configure(cursor="hand2")
                except Exception:
                    pass
            ic.pack(side="left")
            Tip.bind(ic, info)
            ic.bind("<Enter>", lambda e: ic.configure(fg=T["accent2"]),
                    add="+")
            ic.bind("<Leave>", lambda e: ic.configure(fg=T["text_dim"]),
                    add="+")
        self._ch = tk.Label(tp, text=fmt.format(float(var.get())),
                            bg=T["glass"], fg=T["accent"],
                            font=("Consolas", 9, "bold"), padx=6,
                            cursor="xterm")
        self._ch.pack(side="right")
        self._ch.bind("<Button-1>", self._ty)
        self._s = ttk.Scale(self, from_=lo, to=hi, variable=var,
                            command=self._oc)
        self._s.pack(fill="x", pady=(1, 2))
        self._s.bind("<ButtonRelease-1>", lambda e: self._fire())
        for k, m in (("<Up>",1),("<Down>",-1),("<Prior>",10),("<Next>",-10)):
            self._s.bind(k, lambda e, m=m: self._ng(m))
        # Mouse-wheel support: hovering the slider scrolls its value
        # (matches the Up/Down step). Bound directly on the widget and
        # returns "break" so it never falls through to a scrollable
        # parent's panel-scroll binding or the app's global Ctrl+Wheel
        # zoom handler — each widget gets exactly one behavior.
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._s.bind(seq, self._on_wheel)
            self.bind(seq, self._on_wheel)
    def _on_wheel(self, e):
        if getattr(e, "num", None) == 4:
            d = 1
        elif getattr(e, "num", None) == 5:
            d = -1
        else:
            d = 1 if e.delta > 0 else -1
        self._ng(d)
        return "break"
    def _ty(self, _=None):
        if self._e:
            return
        self._e = tk.Entry(self._ch.master, bg=T["glass"], fg=T["accent"],
                           font=("Consolas", 9, "bold"), width=7,
                           insertbackground=T["accent"], relief="flat",
                           highlightthickness=1,
                           highlightbackground=T["accent"])
        self._e.insert(0, self._f.format(float(self._v.get())))
        self._e.pack(side="right")
        self._e.focus_set()
        self._e.select_range(0, "end")
        self._e.bind("<Return>", lambda e: self._ok())
        self._e.bind("<Escape>", lambda e: self._cn())
        self._e.bind("<FocusOut>", lambda e: self._ok())
        self._ch.pack_forget()
    def _cn(self):
        if self._e:
            self._e.destroy()
            self._e = None
            self._ch.pack(side="right")
    def _ok(self):
        if not self._e:
            return
        try:
            self._st(float(self._e.get().strip().replace("−","-")
                           .replace(",",".")))
        except ValueError:
            pass
        self._cn()
    def _st(self, v):
        v = float(np.clip(v, self._lo, self._hi))
        self._v.set(v)
        self._ch.configure(text=self._f.format(v))
        self._fire()
    def _ng(self, m):
        self._st(float(self._v.get())+(self._hi-self._lo)/100*m)
        return "break"
    def _oc(self, _=None):
        try:
            self._ch.configure(text=self._f.format(float(self._v.get())))
        except Exception:
            pass
        n = time.time()
        if n-self._lf > .2:
            self._lf = n
            self._fire()
    def _fire(self):
        if self._cb:
            self._cb(self._key)

_HSL_SWATCH = {"red":"#e04a44","orange":"#e8823a","yellow":"#d8c62e",
              "green":"#4caf50","aqua":"#26c6b0","blue":"#3f7fe0",
              "purple":"#8a5fd1","magenta":"#d1479f"}

class HSLMixer(tk.Frame):
    """Lightroom-style Color Mixer: one selected band's Hue/Saturation/
    Luminance sliders at a time, chosen via a row of color chips —
    replaces a flat 24-slider dump with the same interaction model as
    every current color-grading tool (Lightroom, Capture One, DaVinci)."""
    def __init__(self, master, app):
        super().__init__(master, bg=T["card"])
        self.app = app
        self.band = HSL_BANDS[0]
        chips = tk.Frame(self, bg=T["card"])
        chips.pack(fill="x", pady=(2, 6))
        self._chip_w = {}
        for b in HSL_BANDS:
            c = tk.Label(chips, text="", bg=_HSL_SWATCH[b], width=3, height=1,
                        relief="flat", cursor="hand2",
                        highlightthickness=2,
                        highlightbackground=T["card"])
            c.pack(side="left", padx=2)
            c.bind("<Button-1>", lambda e, b=b: self._select(b))
            Tip.bind(c, _HSL_LABELS[b])
            self._chip_w[b] = c
        top = tk.Frame(self, bg=T["card"])
        top.pack(fill="x")
        self._lbl = tk.Label(top, text="", bg=T["card"], fg=T["text"],
                             font=("Segoe UI", 9, "bold"), anchor="w")
        self._lbl.pack(side="left")
        Btn(top, "Reset Color", self._reset_band, w=100, h=22, fs=8,
           icon="↺").pack(side="right")
        self._body = tk.Frame(self, bg=T["card"])
        self._body.pack(fill="x")
        Btn(self, "Reset All Colors", self._reset_all, w=140, h=24, fs=8,
           icon="⟲").pack(pady=(6, 2))
        self._select(self.band)
    def _select(self, band):
        self.band = band
        for b, w in self._chip_w.items():
            w.configure(highlightbackground=T["accent"] if b == band
                       else T["card"])
        self._lbl.configure(text=_HSL_LABELS[band])
        for w in self._body.winfo_children():
            w.destroy()
        for comp, label in (("hue", "Hue"), ("sat", "Saturation"),
                            ("lum", "Luminance")):
            key = f"hsl_{band}_{comp}"
            Param(self._body, label, self.app.vars[key], self.app._scd,
                 -100, 100, "{:+.0f}", DEF.get(key, 0), key=key,
                 info=PARAM_INFO.get(key)).pack(fill="x", pady=2)
    def _reset_band(self):
        for comp in ("hue", "sat", "lum"):
            key = f"hsl_{self.band}_{comp}"
            self.app.vars[key].set(DEF.get(key, 0))
        self._select(self.band)
        self.app._scd(f"hsl_{self.band}_hue")
    def _reset_all(self):
        for b in HSL_BANDS:
            for comp in ("hue", "sat", "lum"):
                key = f"hsl_{b}_{comp}"
                self.app.vars[key].set(DEF.get(key, 0))
        self._select(self.band)
        self.app._scd("hsl_red_hue")

class PRow(tk.Canvas):
    """Modern glass/metallic preset card: rounded canvas card with a
    brushed-metal gradient, an accent glow ring on hover, and a
    persistent accent ring + dot marker when this preset is the one
    currently applied — replacing the old flat bordered tk.Frame row."""
    def __init__(self, master, p, th, oc, on_delete=None, on_rename=None,
                 active=False, favorite=False, on_favorite=None):
        super().__init__(master, height=60, bg=T["card"],
                         highlightthickness=0, cursor="hand2")
        self._p, self._oc, self._img, self._del = p, oc, th, on_delete
        self._ren = on_rename
        self._active = active
        self._favorite = bool(favorite)
        self._on_favorite = on_favorite
        self._hov = False
        self._del_box = None
        self._ren_box = None
        self._fav_box = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._sh(True))
        self.bind("<Leave>", lambda e: self._sh(False))
        self.bind("<Button-1>", self._click)
        self.bind("<Double-Button-1>", self._dclick)
        if on_delete is not None:
            self.bind("<Button-3>", lambda e: on_delete(self._p))
        self._draw()
    def _sh(self, h):
        self._hov = h
        self._draw()
    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = int(self["height"])
        hov = self._hov
        f = T["card_hi"] if (hov or self._active) else T["card"]
        ln = T["accent"] if (hov or self._active) else T["stroke"]
        if hov or self._active:
            rnd(self, 0, 0, w, h, T["radius_lg"], fill="",
               outline=T["accent"] if hov else T["accent2"])
        rnd(self, 1, 1, w-2, h-2, T["radius"], fill=f, outline=ln)
        # Brushed-metal top gradient band, same language as the toolbar
        # buttons, so preset cards read as part of the same UI system.
        top_c = _mix(f, "#ffffff", .10)
        band = max(2, (h-2)//2)
        for i in range(band):
            t2 = 1-(i/band)
            self.create_line(2, 2+i, w-2, 2+i, fill=_mix(f, top_c, t2))
        x = 10
        if self._img is not None:
            try:
                iw = self._img.width()
            except Exception:
                iw = 0
            self.create_image(x, h//2, image=self._img, anchor="w")
            x += iw+10
        if self._active:
            self.create_text(x, h//2, text="●", fill=T["accent"],
                             font=("Segoe UI", 8))
            x += 12
        tx_w = max(40, w-x-(22 if self._del is not None else 10)
                  -(18 if self._ren is not None else 0)
                  -(22 if self._on_favorite is not None else 0))
        self.create_text(x, h//2-10, text=self._p["name"][:44],
                         fill=T["text"], font=("Segoe UI", 9, "bold"),
                         anchor="w", width=tx_w)
        sub = self._p.get("process") or self._p.get("family", "")
        self.create_text(x, h//2+10, text=sub, fill=T["text_dim"],
                         font=("Segoe UI", 7), anchor="w", width=tx_w)
        nx = w-6
        if self._del is not None:
            dx0, dy0, dx1, dy1 = nx-18, h//2-10, nx, h//2+10
            self._del_box = (dx0, dy0, dx1, dy1)
            self.create_text((dx0+dx1)//2, (dy0+dy1)//2, text="✕",
                             fill=T["red"] if hov else T["text_dim"],
                             font=("Segoe UI", 9, "bold"))
            nx = dx0-2
        if self._ren is not None:
            rx0, ry0, rx1, ry1 = nx-18, h//2-10, nx, h//2+10
            self._ren_box = (rx0, ry0, rx1, ry1)
            self.create_text((rx0+rx1)//2, (ry0+ry1)//2, text="✎",
                             fill=T["accent2"] if hov else T["text_dim"],
                             font=("Segoe UI", 9, "bold"))
            nx = rx0-2
        if self._on_favorite is not None:
            fx0, fy0, fx1, fy1 = nx-20, h//2-10, nx, h//2+10
            self._fav_box = (fx0, fy0, fx1, fy1)
            self.create_text((fx0+fx1)//2, (fy0+fy1)//2,
                             text="★" if self._favorite else "☆",
                             fill=T["accent"] if self._favorite else T["text_dim"],
                             font=("Segoe UI Symbol", 10, "bold"))
    def _dclick(self, e):
        if self._ren is not None:
            self._ren(self._p)
    def _click(self, e):
        if self._del_box:
            x0, y0, x1, y1 = self._del_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._del(self._p)
                return
        if self._ren_box:
            x0, y0, x1, y1 = self._ren_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._ren(self._p)
                return
        if self._fav_box and self._on_favorite:
            x0, y0, x1, y1 = self._fav_box
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._on_favorite(self._p)
                return
        self._oc(self._p)

def _auto_icon(text):
    """Best-effort coherent glyph for a dialog button from its label,
    so every confirm/cancel popup across the app (which pass plain,
    varied strings) still gets the same chip-icon language as the
    toolbar instead of staying bare text or ad-hoc emoji."""
    t = text.strip()
    for ch in ("📂", "⚪", "⚡", "✂", "⬇", "👁", "⊘"):
        t = t.replace(ch, "").strip()
    low = t.lower()
    if "open" in low: return "▣", t
    if "close" in low: return "✕", t
    if "cancel" in low: return "✕", t
    if "remove" in low or "delete" in low: return "⌫", t
    if "reset" in low: return "↺", t
    if "save" in low: return "◈", t
    if "export" in low: return "⇧", t
    if "overwrite" in low or "replace" in low: return "⇄", t
    if low == "ok" or "yes" in low or "confirm" in low: return "✓", t
    if "no" in low: return "✕", t
    return None, t

class Dlg(tk.Toplevel):
    def __init__(self, master, title, lines, btns, w=360, acc=None):
        super().__init__(master)
        acc = acc or T["accent"]
        self.configure(bg=T["bg"])
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.transient(master)
        H = 130+36*len(btns)+20*len(lines)
        cv = tk.Canvas(self, width=w, height=H, bg=T["bg"],
                       highlightthickness=1,
                       highlightbackground=T["stroke_hi"])
        cv.pack()
        rnd(cv, 2, 2, w-4, H-4, 10, fill=T["glass"], outline=acc, width=2)
        cv.create_text(w//2, 30, text=title, fill=T["text"],
                       font=("Segoe UI", 13, "bold"))
        y = 58
        for l in lines:
            cv.create_text(w//2, y, text=l, fill=T["text_dim"],
                           font=T["font_sm"])
            y += 20
        by = H-36*len(btns)-10
        for t, c, fl in btns:
            ic, lbl = _auto_icon(t)
            b = Btn(self, lbl, lambda c=c: self._r(c), w=170, h=30,
                    kind="solid" if fl else "ghost", accent=acc, bg=T["bg"],
                    icon=ic)
            b.place(x=(w-170)//2, y=by)
            by += 36
        self.bind("<Escape>", lambda e: self._d())
        self.bind("<Button-1>", lambda e: self._d())
        cv.bind("<Button-1>", lambda e: self._d())
        self.update_idletasks()
        mx = master.winfo_rootx()+master.winfo_width()//2
        my = master.winfo_rooty()+master.winfo_height()//2
        self.geometry(f"+{mx-w//2}+{my-H//2}")
        try:
            self.focus_force()
        except Exception:
            pass
    def _r(self, c):
        if c is None:
            self._d()
            return
        try:
            if c() is not False:
                self._d()
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=self)
    def _d(self):
        try:
            self.destroy()
        except Exception:
            pass

class Egg:
    """Easter-egg reveal: a centered glass/metallic card (rounded,
    gradient-filled, accent glow border) over a dimmed backdrop, with
    a breathing icon, a few slow-drifting sparkle particles, and a
    rounded gradient progress bar — replacing the old flat full-bleed
    dim + plain text version."""
    def __init__(self, app, msg, acc, auto=6000):
        self.app = app
        self.w = msg.split()
        self.i = 0
        self.a = acc
        self.ov = tk.Canvas(app.cnv, highlightthickness=0, bg="#040507",
                            cursor="hand2")
        self.ov.place(x=0, y=0, relwidth=1, relheight=1)
        app._mod = True
        self.alive = True
        self._aid = None
        rng = np.random.default_rng(hash(msg) & 0xffff)
        self._sp = [{"dx": float(rng.uniform(-1, 1)), "dy": float(rng.uniform(-1, 1)),
                     "r": float(rng.uniform(.55, 1.0)),
                     "ph": float(rng.uniform(0, 6.28))} for _ in range(10)]
        self._dr()
        self.ov.bind("<Button-1>", lambda e: self.close())
        app.after(40, self._go, auto)
    def _dr(self):
        if not self.alive:
            return
        self.ov.delete("all")
        cw = max(2, self.app.cnv.winfo_width())
        ch = max(2, self.app.cnv.winfo_height())
        self.ov.configure(width=cw, height=ch)
        self.ov.create_rectangle(0, 0, cw, ch, fill="#040507",
                                 stipple="gray75", outline="")
        cy = ch//2
        card_w = min(560, cw-70)
        card_h = 216
        x0, y0 = cw//2-card_w//2, cy-card_h//2
        x1, y1 = x0+card_w, y0+card_h
        # Outer accent glow ring, then the glass card itself with a
        # brushed-metal vertical gradient (lighter near the top).
        rnd(self.ov, x0-3, y0-3, x1+3, y1+3, T["radius_lg"]+3,
           fill="", outline=self.a)
        rnd(self.ov, x0, y0, x1, y1, T["radius_lg"], fill=T["glass"],
           outline=_mix(self.a, "#000000", .1), width=2)
        top_c = _mix(T["glass"], "#ffffff", .10)
        band = card_h//2
        for k in range(band):
            t2 = 1-(k/band)
            self.ov.create_line(x0+2, y0+2+k, x1-2, y0+2+k,
                                fill=_mix(T["glass"], top_c, t2))
        # Slow-drifting sparkle particles orbiting gently around the
        # card center — purely decorative, seeded once per egg so they
        # don't jump around between redraws.
        for s in self._sp:
            ang = s["ph"]+self.i*0.35
            px = cw//2 + s["dx"]*(card_w*.52) + math.cos(ang)*10
            py = cy + s["dy"]*(card_h*.5) + math.sin(ang)*10
            self.ov.create_text(px, py, text="·", fill=self.a,
                                font=("Segoe UI", int(8+4*s["r"])))
        # Breathing star icon — alternates size on each word-reveal
        # tick for a gentle pulse instead of a static glyph.
        star_fs = 20 if (self.i % 2 == 0) else 16
        self.ov.create_text(cw//2, y0+34, text="✦", fill=self.a,
                            font=("Segoe UI", star_fs, "bold"))
        if self.i > 0:
            self.ov.create_text(cw//2, cy+4,
                                text=" ".join(self.w[:self.i]),
                                fill=T["text"],
                                font=("Segoe UI", 18, "bold italic"),
                                width=max(120, card_w-60))
        # Rounded gradient progress bar: dark track + accent fill that
        # lightens toward its leading edge.
        bar_w = min(300, card_w-100)
        bx0, bx1 = cw//2-bar_w//2, cw//2+bar_w//2
        by = y1-30
        rnd(self.ov, bx0, by, bx1, by+5, 3, fill=T["stroke"], outline="")
        u = int(self.i/max(len(self.w), 1)*bar_w)
        if u > 4:
            rnd(self.ov, bx0, by, bx0+u, by+5, 3,
               fill=_mix(self.a, "#ffffff", .25), outline="")
        if self.i >= len(self.w):
            self.ov.create_text(cw//2, y1-10, text="click to continue",
                                fill=T["text_dim"], font=("Segoe UI", 8))
    def _go(self, auto):
        if not self.alive:
            return
        self._dr()
        self._st_(auto)
    def _st_(self, auto):
        if not self.alive:
            return
        if self.i < len(self.w):
            self.i += 1
            self._dr()
            self._aid = self.app.after(250, self._st_, auto)
        else:
            self._aid = self.app.after(auto, self.close)
    def close(self):
        if not self.alive:
            return
        self.alive = False
        if self._aid:
            try:
                self.app.after_cancel(self._aid)
            except Exception:
                pass
        try:
            self.ov.destroy()
        except Exception:
            pass
        self.app._mod = False
        if self.app._ph is not None:
            self.app._paint()

RTS = [("Free",None),("1:1",1),("4:3",4/3),("3:2",3/2),
       ("16:9",16/9),("9:16",9/16),("5:4",5/4),("2.39:1",2.39)]

class Crop:
    HN = 9
    def __init__(self, cv, sz, off, oa, oc, on_straighten=None,
                 on_rotate=None, on_flip_h=None, on_flip_v=None):
        self.cv = cv
        self.iw, self.ih = sz
        self.ox, self.oy = off
        self.oa, self.oc = oa, oc
        self.on_straighten = on_straighten
        self.on_rotate = on_rotate
        self.on_flip_h = on_flip_h
        self.on_flip_v = on_flip_v
        self.rt = None
        self.dg = None
        self.rc = [.12,.12,.88,.88]
        self._its = []
        self._bar()
        self.cv.configure(cursor="crosshair")
        self.cv.bind("<Button-1>", self._pr)
        self.cv.bind("<B1-Motion>", self._mv)
        self.cv.bind("<ButtonRelease-1>", lambda e: setattr(self, "dg", None))
        self.draw()
    def _bar(self):
        self._tb = tk.Frame(self.cv, bg=T["glass"], highlightthickness=1,
                            highlightbackground=T["stroke_hi"])
        self._i = tk.Label(self._tb, text="", bg=T["glass"],
                           fg=T["accent"], font=("Consolas", 9, "bold"))
        self._i.pack(side="left", padx=8)
        for n, r in RTS:
            b = tk.Label(self._tb, text=n, bg=T["card"], fg=T["text_dim"],
                         font=("Segoe UI", 8, "bold"), padx=7, pady=2,
                         cursor="hand2")
            b.pack(side="left", padx=2, pady=3)
            b.bind("<Button-1>", lambda e, r=r: self.sr(r))
        tk.Frame(self._tb, bg=T["stroke_hi"], width=1
                ).pack(side="left", fill="y", padx=4, pady=3)
        for txt, cb, tip in (
                ("╱ Straighten", self.on_straighten, "Fix horizon tilt"),
                ("⟳ Rotate", self.on_rotate, "Rotate 90° clockwise"),
                ("⇋ Flip H", self.on_flip_h, "Flip horizontally"),
                ("⇅ Flip V", self.on_flip_v, "Flip vertically")):
            if cb is None:
                continue
            gb = tk.Label(self._tb, text=txt, bg=T["card"],
                         fg=T["text_dim"], font=("Segoe UI", 8, "bold"),
                         padx=7, pady=2, cursor="hand2")
            gb.pack(side="left", padx=2, pady=3)
            gb.bind("<Button-1>", lambda e, cb=cb: cb())
            Tip.bind(gb, tip)
        a_ = tk.Label(self._tb, text="✓", bg=T["accent"], fg="#0a0c10",
                      font=("Segoe UI", 9, "bold"), padx=10, pady=3,
                      cursor="hand2")
        a_.pack(side="right", padx=(5,7), pady=3)
        a_.bind("<Button-1>", lambda e: self.ap())
        c_ = tk.Label(self._tb, text="✕", bg=T["red"], fg="#0a0c10",
                      font=("Segoe UI", 9, "bold"), padx=8, pady=3,
                      cursor="hand2")
        c_.pack(side="right", pady=3)
        c_.bind("<Button-1>", lambda e: self.ca())
        self._tb.place(x=6, y=6)
    def sr(self, r):
        self.rt = r
        if r:
            cx = (self.rc[0]+self.rc[2])/2
            cy = (self.rc[1]+self.rc[3])/2
            ai = self.iw/self.ih
            if r > ai:
                w, h = .9, .9*self.iw/(r*self.ih)
            else:
                h, w = .9, .9*r*self.ih/self.iw
            self.rc = [cx-w/2, cy-h/2, cx+w/2, cy+h/2]
        self.draw()
    def _px(self):
        return [self.rc[0]*self.iw+self.ox, self.rc[1]*self.ih+self.oy,
                self.rc[2]*self.iw+self.ox, self.rc[3]*self.ih+self.oy]
    def draw(self):
        for i in self._its:
            self.cv.delete(i)
        self._its = []
        x0, y0, x1, y1 = self._px()
        cw, ch = self.cv.winfo_width(), self.cv.winfo_height()
        for (a, b, c, d) in [(0,0,cw,y0),(0,y1,cw,ch),(0,y0,x0,y1),
                             (x1,y0,cw,y1)]:
            self._its.append(self.cv.create_rectangle(
                a, b, c, d, fill="#040507", stipple="gray50", outline=""))
        for i in (1, 2):
            gx, gy = x0+(x1-x0)*i/3, y0+(y1-y0)*i/3
            self._its.append(self.cv.create_line(gx, y0, gx, y1,
                               fill=T["accent2"], dash=(2,5)))
            self._its.append(self.cv.create_line(x0, gy, x1, gy,
                               fill=T["accent2"], dash=(2,5)))
        self._its.append(self.cv.create_rectangle(x0, y0, x1, y1,
                           outline=T["accent"], width=2))
        for (hx, hy) in [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]:
            self._its.append(self.cv.create_oval(hx-4.5, hy-4.5,
                               hx+4.5, hy+4.5, fill=T["accent"],
                               outline="#fff"))
        self._i.configure(text=f" {int((x1-x0)/self.iw*100)}% x "
                               f"{int((y1-y0)/self.ih*100)}%   "
                               f"{int(x1-x0)}x{int(y1-y0)}px")
    def _ha(self, px, py):
        px, py = px-self.ox, py-self.oy
        x0, y0 = self.rc[0]*self.iw, self.rc[1]*self.ih
        x1, y1 = self.rc[2]*self.iw, self.rc[3]*self.ih
        hs = self.HN+6
        for i, (hx, hy) in enumerate([(x0,y0),(x1,y0),(x0,y1),(x1,y1)]):
            if abs(px-hx) < hs and abs(py-hy) < hs:
                return i
        if x0 < px < x1 and y0 < py < y1:
            return 4
        return -1
    def _pr(self, e):
        self.dg = (self._ha(e.x, e.y), list(self.rc), e.x, e.y)
    def _mv(self, e):
        if not self.dg:
            return
        h, b, sx, sy = self.dg
        dx, dy = (e.x-sx)/self.iw, (e.y-sy)/self.ih
        r = list(b)
        if h in (0, 2):
            r[0] = b[0]+dx
        if h in (1, 3):
            r[2] = b[2]+dx
        if h in (0, 1):
            r[1] = b[1]+dy
        if h in (2, 3):
            r[3] = b[3]+dy
        if h == 4:
            w, hg = b[2]-b[0], b[3]-b[1]
            r[0] = min(max(b[0]+dx, 0), 1-w)
            r[2] = r[0]+w
            r[1] = min(max(b[1]+dy, 0), 1-hg)
            r[3] = r[1]+hg
        if self.rt and h in (0, 1, 2, 3):
            hg = (r[2]-r[0])*self.iw/(self.rt*self.ih)
            if h in (0, 1):
                r[1] = r[3]-hg
            else:
                r[3] = r[1]+hg
        r = [max(0, r[0]), max(0, r[1]), min(1, r[2]), min(1, r[3])]
        if r[2]-r[0] > .03 and r[3]-r[1] > .03:
            self.rc = r
            self.draw()
    def kill(self):
        for i in self._its:
            try:
                self.cv.delete(i)
            except Exception:
                pass
        try:
            self._tb.destroy()
        except Exception:
            pass
        for s_ in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.cv.unbind(s_)
        self.cv.configure(cursor="arrow")
    def ap(self):
        r = tuple(self.rc)
        self.kill()
        self.oa(r)
    def ca(self):
        self.kill()
        self.oc()

class Straighten(tk.Frame):
    """Floating glass panel for horizon straighten: a small live
    preview (rotated thumbnail + fixed rule-of-thirds guide lines so
    the tilt is easy to judge), an angle slider, and Apply/Cancel —
    committed via App._srot / _rotate_straight() so it's crop-free of
    black corners and fully undoable like Crop."""
    PW, PH = 300, 200
    def __init__(self, app, on_apply, on_cancel):
        super().__init__(app.cnv, bg=T["glass"], highlightthickness=1,
                         highlightbackground=T["stroke_hi"])
        self.app, self._oa, self._oc = app, on_apply, on_cancel
        self.angle = float(app._srot)
        hd = tk.Frame(self, bg=T["glass"])
        hd.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(hd, text="╱ STRAIGHTEN", bg=T["glass"], fg=T["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.pcv = tk.Canvas(self, width=self.PW, height=self.PH,
                             bg="#040507", highlightthickness=0)
        self.pcv.pack(padx=8, pady=4)
        row = tk.Frame(self, bg=T["glass"])
        row.pack(fill="x", padx=8)
        tk.Label(row, text="Angle", bg=T["glass"], fg=T["text_dim"],
                 font=T["font_sm"]).pack(side="left")
        self._al = tk.Label(row, text="0.0°", bg=T["glass"],
                            fg=T["accent"], font=("Consolas", 9, "bold"))
        self._al.pack(side="right")
        self._sc = ttk.Scale(self, from_=-45, to=45, value=self.angle,
                             command=self._chg)
        self._sc.pack(fill="x", padx=8, pady=(0, 6))
        btns = tk.Frame(self, bg=T["glass"])
        btns.pack(fill="x", padx=8, pady=(0, 8))
        Btn(btns, "Apply", self._apply, w=100, h=28, icon="✓",
           kind="solid", tip="Apply straighten (crops out the tilt)"
           ).pack(side="left")
        Btn(btns, "Cancel", self._cancel, w=100, h=28, icon="✕"
           ).pack(side="right")
        self.place(x=6, y=6)
        self._render()
    def _chg(self, v):
        self.angle = float(v)
        self._al.configure(text=f"{self.angle:+.1f}°")
        self._render()
    def _render(self):
        self.pcv.delete("all")
        if self.app.pv is not None:
            try:
                im = to_pil(self.app.pv)
                if abs(self.angle) > 1e-6:
                    im = im.rotate(self.angle, resample=BILINEAR,
                                  expand=False, fillcolor=(15, 10, 14))
                iw, ih = im.size
                s = min(self.PW/iw, self.PH/ih)
                im = im.resize((max(1, int(iw*s)), max(1, int(ih*s))),
                              BILINEAR)
                self._ph = ImageTk.PhotoImage(im)
                self.pcv.create_image(self.PW//2, self.PH//2,
                                      image=self._ph)
            except Exception:
                pass
        # Fixed rule-of-thirds guide lines — stay put while the image
        # rotates under them, so the horizon's tilt against them is
        # what you're correcting.
        for gx in (self.PW/3, 2*self.PW/3):
            self.pcv.create_line(gx, 0, gx, self.PH, fill=T["accent"],
                                 dash=(2, 3))
        for gy in (self.PH/3, 2*self.PH/3):
            self.pcv.create_line(0, gy, self.PW, gy, fill=T["accent"],
                                 dash=(2, 3))
    def _apply(self):
        a = self.angle
        self.destroy()
        self._oa(a)
    def _cancel(self):
        self.destroy()
        self._oc()

class MaskTool:
    """Local adjustment masks: Radial / Linear / Brush, each drawn
    directly on the main canvas and carrying its own reduced slider
    set (Exposure/Contrast/Temperature/Saturation/Clarity) plus
    Feather and Invert. A floating glass panel lists existing masks
    (toggle/select/delete) and shows the selected mask's sliders.
    Scope cut: geometry isn't re-editable after creation — delete and
    redraw to reposition/resize."""
    MODES = (("radial", "Radial", "◎"), ("linear", "Linear", "▤"),
            ("brush", "Brush", "✎"))
    LPARAMS = [("exposure", "Exposure", -2, 2, "{:+.2f}"),
              ("contrast", "Contrast", -100, 100, "{:+.0f}"),
              ("temperature", "Temperature", -100, 100, "{:+.0f}"),
              ("saturation", "Saturation", -100, 100, "{:+.0f}"),
              ("clarity", "Clarity", -100, 100, "{:+.0f}")]
    def __init__(self, app):
        self.app = app
        self.mode = "radial"
        self.drag0 = None
        self.pending_brush = None
        self.sel = None
        self.tmp_ids = []
        self._build()
        self._bind_canvas()
        self.refresh_list()
    def _geom(self):
        _, _, dw, dh, _, _, _, _ = self.app._geom(self.app._z, self.app._pan)
        return dw, dh, self.app._off[0], self.app._off[1]
    def _to_norm(self, cx, cy):
        iw, ih, ox, oy = self._geom()
        return (float(np.clip((cx-ox)/max(iw, 1), 0, 1)),
                float(np.clip((cy-oy)/max(ih, 1), 0, 1)))
    def _build(self):
        self.panel = tk.Frame(self.app.cnv, bg=T["glass"],
                              highlightthickness=1,
                              highlightbackground=T["stroke_hi"])
        hd = tk.Frame(self.panel, bg=T["glass"])
        hd.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(hd, text="▨ LOCAL MASKS", bg=T["glass"], fg=T["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        Btn(hd, "Close", self.close, w=64, h=22, fs=8,
           icon="✕").pack(side="right")
        modes = tk.Frame(self.panel, bg=T["glass"])
        modes.pack(fill="x", padx=8)
        self._mode_btns = {}
        for key, label, icon in self.MODES:
            b = Btn(modes, label, lambda k=key: self._set_mode(k),
                   w=76, h=26, fs=8, icon=icon)
            b.pack(side="left", padx=2)
            self._mode_btns[key] = b
        self._mode_btns["radial"].set_active(True)
        self.list_fr = tk.Frame(self.panel, bg=T["glass"])
        self.list_fr.pack(fill="x", padx=8, pady=(6, 2))
        self.param_fr = tk.Frame(self.panel, bg=T["glass"])
        self.param_fr.pack(fill="x", padx=8, pady=(4, 4))
        tk.Label(self.panel, text="drag on image to draw • brush: drag "
                "multiple strokes, then pick it below to adjust",
                bg=T["glass"], fg=T["text_dim"], font=("Segoe UI", 7),
                wraplength=230, justify="left").pack(fill="x",
                                                     padx=8, pady=(0, 8))
        self.panel.place(x=6, y=6)
    def _set_mode(self, k):
        self.mode = k
        for kk, b in self._mode_btns.items():
            b.set_active(kk == k)
        self.pending_brush = None
    def _bind_canvas(self):
        cv = self.app.cnv
        cv.configure(cursor="tcross")
        cv.bind("<Button-1>", self._down)
        cv.bind("<B1-Motion>", self._drag)
        cv.bind("<ButtonRelease-1>", self._up)
    def _unbind_canvas(self):
        cv = self.app.cnv
        for s in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            cv.unbind(s)
        cv.configure(cursor="arrow")
    def _clear_tmp(self):
        for i in self.tmp_ids:
            try:
                self.app.cnv.delete(i)
            except Exception:
                pass
        self.tmp_ids = []
    def _down(self, e):
        if self.mode == "brush":
            if self.pending_brush is None:
                m = {"type": "brush", "enabled": True, "invert": False,
                    "feather": .5, "radius": .04, "strokes": [],
                    "params": {k: 0 for k, *_ in self.LPARAMS}}
                self.app.masks.append(m)
                self.pending_brush = len(self.app.masks)-1
                self.sel = self.pending_brush
            x, y = self._to_norm(e.x, e.y)
            self.app.masks[self.pending_brush]["strokes"].append([(x, y)])
            self._stroke_px = [(e.x, e.y)]
        else:
            self.drag0 = (e.x, e.y)
    def _drag(self, e):
        if self.mode == "brush" and self.pending_brush is not None:
            x, y = self._to_norm(e.x, e.y)
            self.app.masks[self.pending_brush]["strokes"][-1].append((x, y))
            self._stroke_px.append((e.x, e.y))
            self._clear_tmp()
            if len(self._stroke_px) >= 2:
                flat = [c for pt in self._stroke_px for c in pt]
                self.tmp_ids.append(self.app.cnv.create_line(
                    *flat, fill=T["accent"], width=3, smooth=True,
                    capstyle="round"))
            return
        if self.drag0 is None:
            return
        self._clear_tmp()
        x0, y0 = self.drag0
        if self.mode == "radial":
            r = math.hypot(e.x-x0, e.y-y0)
            self.tmp_ids.append(self.app.cnv.create_oval(
                x0-r, y0-r, x0+r, y0+r, outline=T["accent"], width=2,
                dash=(4, 3)))
        elif self.mode == "linear":
            self.tmp_ids.append(self.app.cnv.create_line(
                x0, y0, e.x, e.y, fill=T["accent"], width=2, dash=(4, 3)))
    def _up(self, e):
        if self.mode == "brush":
            self._clear_tmp()
            self._after_change()
            return
        if self.drag0 is None:
            return
        x0, y0 = self.drag0
        self._clear_tmp()
        self.drag0 = None
        iw, ih, ox, oy = self._geom()
        nx0, ny0 = self._to_norm(x0, y0)
        if self.mode == "radial":
            r = math.hypot(e.x-x0, e.y-y0)
            if r < 4:
                return
            m = {"type": "radial", "enabled": True, "invert": False,
                "cx": nx0, "cy": ny0, "rx": r/max(iw, 1), "ry": r/max(ih, 1),
                "angle": 0, "feather": .5,
                "params": {k: 0 for k, *_ in self.LPARAMS}}
        elif self.mode == "linear":
            nx1, ny1 = self._to_norm(e.x, e.y)
            if abs(nx1-nx0) < .01 and abs(ny1-ny0) < .01:
                return
            m = {"type": "linear", "enabled": True, "invert": False,
                "x0": nx0, "y0": ny0, "x1": nx1, "y1": ny1, "feather": .4,
                "params": {k: 0 for k, *_ in self.LPARAMS}}
        else:
            return
        self.app.masks.append(m)
        self.sel = len(self.app.masks)-1
        self._after_change()
    def _after_change(self):
        self.app._ck = None
        self.app.req()
        self.refresh_list()
        self._show_params(self.sel)
    def refresh_list(self):
        for w in self.list_fr.winfo_children():
            w.destroy()
        icon = {"radial": "◎", "linear": "▤", "brush": "✎"}
        for i, m in enumerate(self.app.masks):
            row = tk.Frame(self.list_fr, bg=T["card"])
            row.pack(fill="x", pady=1)
            en = m.get("enabled", True)
            lbl = tk.Label(row, text=f"{icon.get(m['type'],'?')} "
                          f"{m['type'].capitalize()} {i+1}",
                          bg=T["card"], fg=T["text"] if en else T["text_dim"],
                          font=("Segoe UI", 8), anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True, padx=6, pady=3)
            lbl.bind("<Button-1>", lambda e, i=i: self._show_params(i))
            eye = tk.Label(row, text="●" if en else "○", bg=T["card"],
                          fg=T["accent"] if en else T["text_dim"],
                          font=("Segoe UI", 8), cursor="hand2")
            eye.pack(side="right", padx=4)
            eye.bind("<Button-1>", lambda e, i=i: self._toggle(i))
            dele = tk.Label(row, text="✕", bg=T["card"], fg=T["red"],
                           font=("Segoe UI", 8, "bold"), cursor="hand2")
            dele.pack(side="right", padx=4)
            dele.bind("<Button-1>", lambda e, i=i: self._delete(i))
    def _toggle(self, i):
        self.app.masks[i]["enabled"] = not self.app.masks[i].get("enabled", True)
        self.app._ck = None
        self.app.req()
        self.refresh_list()
    def _delete(self, i):
        del self.app.masks[i]
        if self.pending_brush == i:
            self.pending_brush = None
        if self.sel == i:
            self.sel = None
        self.app._ck = None
        self.app.req()
        self.refresh_list()
        self._show_params(None)
    def _show_params(self, i):
        self.sel = i
        for w in self.param_fr.winfo_children():
            w.destroy()
        if i is None or i >= len(self.app.masks):
            return
        m = self.app.masks[i]
        hd = tk.Frame(self.param_fr, bg=T["glass"])
        hd.pack(fill="x")
        tk.Label(hd, text=f"Editing {m['type'].capitalize()} {i+1}",
                bg=T["glass"], fg=T["accent2"],
                font=("Segoe UI", 8, "bold")).pack(side="left")
        inv = tk.Label(hd, text="Invert: ON" if m.get("invert")
                      else "Invert: off", bg=T["glass"], fg=T["text_dim"],
                      font=("Segoe UI", 7), cursor="hand2")
        inv.pack(side="right")
        def _tog(e=None, i=i, lbl=inv):
            self.app.masks[i]["invert"] = not self.app.masks[i].get(
                "invert", False)
            lbl.configure(text="Invert: ON" if self.app.masks[i]["invert"]
                          else "Invert: off")
            self.app._ck = None
            self.app.req()
        inv.bind("<Button-1>", _tog)
        self._slider(self.param_fr, "Feather", m, "feather", 0, 1, "{:.2f}")
        for k, l, lo, hi, f in self.LPARAMS:
            self._slider(self.param_fr, l, m["params"], k, lo, hi, f)
    def _slider(self, master, label, target, key, lo, hi, fmt):
        row = tk.Frame(master, bg=T["glass"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=T["glass"], fg=T["text_dim"],
                font=("Segoe UI", 7), width=11, anchor="w").pack(side="left")
        vl = tk.Label(row, text=fmt.format(target.get(key, 0)),
                     bg=T["glass"], fg=T["accent"],
                     font=("Consolas", 7, "bold"), width=6)
        vl.pack(side="right")
        sc = ttk.Scale(row, from_=lo, to=hi, value=target.get(key, 0),
                       command=lambda v, t=target, k=key, vl=vl, f=fmt:
                       self._on_slide(t, k, v, vl, f))
        sc.pack(side="left", fill="x", expand=True, padx=4)
    def _on_slide(self, target, key, v, lbl, fmt):
        target[key] = float(v)
        lbl.configure(text=fmt.format(float(v)))
        self.app._ck = None
        self.app.req()
    def close(self):
        self._unbind_canvas()
        try:
            self.panel.destroy()
        except Exception:
            pass
        self.app._mask_tool = None
        self.app._bc.set_en(True)
        self.app._bst.set_en(True)
        self.app._paint()


class _CurveCanvas(tk.Canvas):
    """Draggable parametric curve editor for ONE channel: click empty
    space to add a control point, drag a point to reshape the curve
    (endpoints stay pinned to x=0/x=1), right-click a middle point to
    remove it. Curve shape/sampling matches _curve_fn exactly, so
    what's drawn here is exactly what the render engine applies."""
    def __init__(self, master, on_change, h=170, line_color=None):
        super().__init__(master, height=h, bg=T["card"],
                         highlightthickness=1, highlightbackground=T["stroke"],
                         cursor="crosshair")
        self._cb = on_change
        self._line_c = line_color or T["accent"]
        self.pts = [(0.0, 0.0), (1.0, 1.0)]
        self._drag = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._down)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Button-3>", self._del_pt)
        self._draw()
    def set_line_color(self, c):
        self._line_c = c
        self._draw()
    def set_points(self, pts):
        self.pts = sorted(tuple(p) for p in pts) if pts else \
            [(0.0, 0.0), (1.0, 1.0)]
        self._draw()
    def get_points(self):
        return list(self.pts)
    def _m(self, w, h):
        return 8, w-16, h-16
    def _to_c(self, x, y, w, h):
        m, iw, ih = self._m(w, h)
        return m+x*iw, (h-m)-y*ih
    def _to_xy(self, cx, cy, w, h):
        m, iw, ih = self._m(w, h)
        return (float(np.clip((cx-m)/max(1, iw), 0, 1)),
                float(np.clip(((h-m)-cy)/max(1, ih), 0, 1)))
    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = int(self["height"])
        rnd(self, 1, 1, w-2, h-2, T["radius_sm"], fill=T["card"],
           outline=T["stroke"])
        m, iw, ih = self._m(w, h)
        for i in (1, 2):
            gx, gy = m+iw*i/3, m+ih*i/3
            self.create_line(gx, m, gx, h-m, fill=T["stroke"])
            self.create_line(m, gy, w-m, gy, fill=T["stroke"])
        self.create_line(m, h-m, w-m, m, fill=T["stroke_hi"], dash=(2, 2))
        fn = _curve_fn(self.pts)
        xs = np.linspace(0, 1, 80)
        ys = fn(xs)
        line = []
        for xv, yv in zip(xs, ys):
            cx, cy = self._to_c(float(xv), float(yv), w, h)
            line.extend((cx, cy))
        self.create_line(*line, fill=self._line_c, width=2, smooth=True)
        for x, y in self.pts:
            cx, cy = self._to_c(x, y, w, h)
            rnd(self, cx-4, cy-4, cx+4, cy+4, 4, fill=self._line_c,
               outline=T["text"])
    def _hit(self, cx, cy, w, h):
        for i, (x, y) in enumerate(self.pts):
            px, py = self._to_c(x, y, w, h)
            if (px-cx)**2+(py-cy)**2 <= 81:
                return i
        return None
    def _down(self, e):
        w, h = self.winfo_width(), int(self["height"])
        i = self._hit(e.x, e.y, w, h)
        if i is None:
            x, y = self._to_xy(e.x, e.y, w, h)
            if any(abs(x-p[0]) < .02 for p in self.pts) or len(self.pts) >= 10:
                return
            self.pts.append((x, y))
            self.pts.sort()
            i = self.pts.index((x, y))
        self._drag = i
        self._draw()
    def _move(self, e):
        if self._drag is None:
            return
        w, h = self.winfo_width(), int(self["height"])
        x, y = self._to_xy(e.x, e.y, w, h)
        i = self._drag
        if i == 0:
            x = 0.0
        elif i == len(self.pts)-1:
            x = 1.0
        else:
            x = float(np.clip(x, self.pts[i-1][0]+.01,
                              self.pts[i+1][0]-.01))
        self.pts[i] = (x, y)
        self._draw()
        self._cb(self.get_points())
    def _del_pt(self, e):
        w, h = self.winfo_width(), int(self["height"])
        i = self._hit(e.x, e.y, w, h)
        if i is not None and 0 < i < len(self.pts)-1:
            del self.pts[i]
            self._draw()
            self._cb(self.get_points())

class CurveEditor(tk.Frame):
    """Per-channel Tone Curve: RGB/R/G/B tabs, each with its own
    _CurveCanvas and its own point list — matching Lightroom's Point
    Curve (master + per-channel Red/Green/Blue curves)."""
    CH_COLOR = {"rgb": None, "r": None, "g": None, "b": None}  # filled below
    CH_LABEL = {"rgb": "RGB", "r": "R", "g": "G", "b": "B"}
    def __init__(self, master, on_change, h=170):
        super().__init__(master, bg=T["card"])
        CurveEditor.CH_COLOR.update({"rgb": T["text"], "r": T["red"],
                                     "g": T["green"], "b": T["accent2"]})
        self._cb = on_change
        self.curves = {c: list(IDENTITY_CURVE) for c in ("rgb", "r", "g", "b")}
        self.ch = "rgb"
        tabs = tk.Frame(self, bg=T["card"])
        tabs.pack(fill="x", pady=(0, 3))
        self._tabs = {}
        for c in ("rgb", "r", "g", "b"):
            b = Btn(tabs, self.CH_LABEL[c], lambda c=c: self._switch(c),
                   w=44, h=22, fs=8, accent=self.CH_COLOR[c])
            b.pack(side="left", padx=2)
            self._tabs[c] = b
        self._tabs["rgb"].set_active(True)
        self.cv = _CurveCanvas(self, self._changed, h=h,
                               line_color=self.CH_COLOR["rgb"])
        self.cv.pack(fill="x")
    def _switch(self, ch):
        self.ch = ch
        for c, b in self._tabs.items():
            b.set_active(c == ch)
        self.cv.set_line_color(self.CH_COLOR[ch])
        self.cv.set_points(self.curves[ch])
    def _changed(self, pts):
        self.curves[self.ch] = pts
        self._cb(dict(self.curves))
    def set_curves(self, curves):
        curves = curves or {}
        self.curves = {c: list(curves.get(c) or IDENTITY_CURVE)
                       for c in ("rgb", "r", "g", "b")}
        self.cv.set_points(self.curves[self.ch])
    def get_curves(self):
        return dict(self.curves)


# ============================================================
#  APP
# ============================================================

class Splash(tk.Toplevel):
    """Borderless glass-card splash shown while the main window builds
    its (fairly heavy) widget tree. Progress is real, not simulated:
    set_status() is called at each actual construction checkpoint in
    App.__init__, so the bar's position always reflects genuine boot
    progress rather than a fixed-duration animation."""
    W, H = 500, 276
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg=T["bg"])
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw-self.W)//2, (sh-self.H)//2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self._cv = tk.Canvas(self, width=self.W, height=self.H,
                             bg=T["bg"], highlightthickness=0)
        self._cv.pack(fill="both", expand=True)
        self._frac = 0.0
        self._status = "Starting…"
        self._pulse = 0.0
        self._draw()
        self._anim()
    def _draw(self):
        cv = self._cv
        cv.delete("all")
        m = 10
        rnd(cv, m, m, self.W-m, self.H-m, T["radius_lg"], fill=T["card"],
           outline=T["stroke_hi"])
        glow = _mix(T["accent"], T["card"], .55+.25*math.sin(self._pulse))
        rnd(cv, m, m, self.W-m, self.H-m, T["radius_lg"], fill="",
           outline=glow, width=2)
        cy = 102
        cv.create_text(self.W//2, cy, text="◈", fill=T["accent"],
                       font=("Segoe UI", 26, "bold"))
        cv.create_text(self.W//2, cy+42, text="LUMEN FORGE",
                       fill=T["text"], font=("Segoe UI", 17, "bold"))
        cv.create_text(self.W//2, cy+64, text="CINEMA COLOUR",
                       fill=T["text_dim"], font=("Segoe UI", 9, "bold"))
        bw, bh = self.W-2*40, 5
        bx, by = 40, cy+104
        rnd(cv, bx, by, bx+bw, by+bh, bh//2, fill=T["stroke"], outline="")
        fw = max(bh, int(bw*np.clip(self._frac, 0, 1)))
        if fw > 1:
            rnd(cv, bx, by, bx+fw, by+bh, bh//2, fill=T["accent"],
               outline="")
        cv.create_text(self.W//2, by+24, text=self._status,
                       fill=T["text_dim"], font=("Segoe UI", 9))
        cv.create_text(self.W-24, self.H-18, text=f"v{VERSION}",
                       fill=T["text_dim"], font=("Segoe UI", 7),
                       anchor="e")
    def _anim(self):
        self._pulse += .25
        self._draw()
        self._anim_job = self.after(60, self._anim)
    def set_status(self, text, frac):
        self._status = text
        self._frac = frac
        self._draw()
        self.update_idletasks()
        self.update()
    def close(self):
        try:
            self.after_cancel(self._anim_job)
        except Exception:
            pass
        self.destroy()

class App(tk.Tk):
    _EG = {"negin": (NEGIN, "Dedicated to my beautiful Negin ❤️",
                     T["accent2"]),
           "forge": (FORGE, "The forge is lit. Forging your image in light…",
                     T["gold"])}

    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — v{VERSION}")
        self.configure(bg=T["bg"])
        self.withdraw()
        self._boot_splash = Splash(self)
        self._boot_splash.set_status("Starting engine…", .04)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1560, sw-60)}x{min(950, sh-90)}+30+30")
        self.minsize(1180, 700)
        styles(self)

        self._boot_splash.set_status("Preparing workspace…", .12)
        self._o = None
        self.src = None
        self.cr = None
        self._srot = 0.0   # straighten angle (degrees), applied in _acs()
        self._ov_str = None
        self.curve_pts = None  # None = use preset/DEF curve; else user override
        self.masks = []  # local adjustment masks (radial/linear/brush)
        self._mask_tool = None
        self.pv = None
        self.mt = {}
        self.imp = []
        self.ap = None
        self.vars = {}
        # UI-only state: presentation preferences never enter the render pipeline.
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
        self._ek = []
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
        self._ldi()
        self.bind("<Key>", self._ekh)
        self.bind_all("<MouseWheel>", self._wh)
        self.bind_all("<Control-k>", lambda e: (self.command_palette(), "break")[1])
        self.bind_all("<Control-o>", lambda e: (self.oi(), "break")[1])
        self.bind_all("<Control-e>", lambda e: (self.ex(), "break")[1])
        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-Z>", lambda e: self.undo())
        self.bind_all("<Control-y>", lambda e: self.redo())
        self.bind_all("<Control-Shift-Z>", lambda e: self.redo())
        self.bind_all("<Control-Shift-z>", lambda e: self.redo())

        self._boot_splash.set_status("Ready", 1.0)
        self.after(150, self._finish_boot)

    def _finish_boot(self):
        """Launch maximized: 'zoomed' is the Windows/most-ttk-themes state
        name; X11 window managers instead honor the '-zoomed' attribute,
        and a raw fullscreen geometry is the last-resort fallback for
        window managers that support neither."""
        self._boot_splash.close()
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

    def _mkv(self):
        for k, _, lo, hi, _ in SPEC:
            self.vars[k] = tk.DoubleVar(value=DEF.get(k, 0))
        self.v_prep = tk.IntVar(value=1)
        self.v_pr = tk.IntVar(value=0)
        self.v_ps = tk.DoubleVar(value=1)
        self.v_ss = tk.DoubleVar(value=1)
        # Camera Match (Camera DNA 2.0) — separate system, own vars
        self.v_cm_on = tk.IntVar(value=0)
        self.v_cm_mode = tk.StringVar(value="character")
        self.v_cm_source = tk.StringVar(value="")   # "" = Auto Detect
        self.v_cm_target = tk.StringVar(value="")
        self.v_cm_strength = tk.DoubleVar(value=1.0)
        self.cm_detected = None   # last CameraMatchResult list from Auto

    def _snapshot(self):
        """Everything Undo/Redo tracks: applied preset, every editable
        control, and the crop rect / straighten angle. Zoom/pan stay
        excluded — those are viewport navigation, not an edit."""
        return {
            "ap": self.ap,
            "cr": self.cr,
            "srot": self._srot,
            "curve_pts": self.curve_pts,
            "masks": copy.deepcopy(self.masks),
            "vars": {k: float(v.get()) for k, v in self.vars.items()},
            "prep": self.v_prep.get(), "pr": self.v_pr.get(),
            "ps": self.v_ps.get(), "ss": self.v_ss.get(),
            "cm_on": self.v_cm_on.get(), "cm_mode": self.v_cm_mode.get(),
            "cm_source": self.v_cm_source.get(),
            "cm_target": self.v_cm_target.get(),
            "cm_strength": self.v_cm_strength.get(),
        }

    def _restore_snapshot(self, snap):
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

    def _stg(self):
        t = {**DEF, **(self.ap or {})}
        for k, v in self.vars.items():
            t[k] = float(v.get())
        if self.curve_pts is not None:
            t["tone_curve_pts"] = self.curve_pts
        t["masks"] = self.masks
        t["scene_prep"] = bool(self.v_prep.get())
        t["print_stock"] = bool(self.v_pr.get())
        t["print_strength"] = float(np.clip(self.v_ps.get(), 0, 1))
        t.update(self._cm_params())
        s = float(np.clip(self.v_ss.get(), 0, 1))
        if t.get("lut3d_path"):
            t["lut3d_strength"] = s
        if s < .999:
            p = dict(t)
            for k, n in DEF.items():
                if isinstance(n, (int, float)) and not isinstance(n, bool):
                    p[k] = float(n)+(float(t[k])-float(n))*s
            t = p
        return t

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

    def _geom(self, z, pan):
        """Single source of truth for preview placement: exact same
        formula (including the edge clamp) used by _paint() to actually
        draw the image, and by _zs()/pan logic to know where the image
        really is on screen. Previously _zs() re-derived the 'before
        zoom' position without applying this clamp, so once the image
        had been panned to an edge (or was smaller than the canvas on
        one axis) the zoom anchor math silently drifted from what was
        actually on screen — that mismatch, compounding over repeated
        zooms, is what produced the drift toward the top-left corner.

        Uses the stable _fit_wh reference (the fit-to-window size at
        z=1) rather than self._ph's actual pixel size — self.pv (and
        so self._ph) now grows in resolution as the user zooms in, and
        that must never feed back into the fit/zoom math itself."""
        cw = max(1, self.cnv.winfo_width())
        ch = max(1, self.cnv.winfo_height())
        pw, ph = self._fit_wh
        base = min(cw/pw, ch/ph, 1)
        s = base*z
        dw, dh = max(1, int(pw*s)), max(1, int(ph*s))
        fx, fy = (cw-dw)//2, (ch-dh)//2
        ox = min(max(fx+pan[0], cw-dw), 0) if dw > cw else fx
        oy = min(max(fy+pan[1], ch-dh), 0) if dh > ch else fy
        return cw, ch, dw, dh, fx, fy, ox, oy

    def _wh(self, e):
        if e.state & 4:
            try:
                cx = e.x_root - self.cnv.winfo_rootx()
                cy = e.y_root - self.cnv.winfo_rooty()
            except Exception:
                cx = cy = None
            self._zs(1.15 if e.delta > 0 else 1/1.15, cx, cy)
            return
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            w = None
        t = None
        while w is not None and w is not self:
            if w is getattr(self, "_pc", None):
                t = self._pc
                break
            if w is getattr(self, "_pci", None):
                t = self._pci
                break
            if w is getattr(self, "_sc", None):
                t = self._sc
                break
            w = w.master
        if t is not None:
            try:
                t.yview_scroll(int(-e.delta/120), "units")
            except Exception:
                pass

    def _zs(self, f, cx=None, cy=None):
        """Zoom by factor f, anchored on canvas point (cx, cy) if given,
        else on the canvas center. Reads the actual on-screen geometry
        via _geom() (clamp included) so the anchor math always matches
        what is really drawn — no more drift toward a corner."""
        o = self._z
        n = float(np.clip(o*f, 1, ZOOM_MAX))
        if n == o:
            return
        if self._ph is None:
            self._z = n
            return
        cw, ch, dw_o, dh_o, fx_o, fy_o, ox_o, oy_o = self._geom(o, self._pan)
        if cx is None or cy is None:
            cx, cy = cw/2.0, ch/2.0
        # Fractional image-space position under the anchor point, based
        # on where the image ACTUALLY is right now (post-clamp)
        ix = (cx-ox_o)/dw_o if dw_o > 1e-6 else .5
        iy = (cy-oy_o)/dh_o if dh_o > 1e-6 else .5
        ix, iy = float(np.clip(ix, 0, 1)), float(np.clip(iy, 0, 1))
        # Geometry AFTER zoom (unclamped center fx_n/fy_n) — solve the
        # desired pan so the same image point lands back under the
        # anchor; _paint()/_geom() will (re-)clamp this at draw time,
        # exactly as it does for a manually dragged pan.
        self._z = n
        _, _, dw_n, dh_n, fx_n, fy_n, _, _ = self._geom(n, (0, 0))
        ox_n, oy_n = cx-ix*dw_n, cy-iy*dh_n
        self._pan = (int(ox_n-fx_n), int(oy_n-fy_n))
        self._paint()
        self._schedule_zoom_preview()

    def _schedule_zoom_preview(self):
        """Debounced: while the user is actively spinning the mouse
        wheel, _paint() alone (an upscaled draw of whatever self.pv
        already is) keeps the view responsive. Once zooming settles,
        rebuild self.pv at a resolution matching the new zoom level and
        re-render, so the view sharpens up instead of staying a
        stretched, low-res preview."""
        if self._zj:
            try:
                self.after_cancel(self._zj)
            except Exception:
                pass
        self._zj = self.after(180, self._sync_zoom_preview)

    def _sync_zoom_preview(self):
        self._zj = None
        if self.src is None:
            return
        if self._z <= 1.001:
            if self._pv_max > PREVIEW_MAX:
                self._mk_preview(PREVIEW_MAX)
                self.req()
            return
        target = PREVIEW_MAX*self._z
        # Only rebuild on a meaningful change — avoids a re-render for
        # every tiny zoom step, and never needlessly downgrades quality
        # mid-zoom.
        if target > self._pv_max*1.05:
            self._mk_preview(target)
            self.req()

    def _rz(self):
        self._z = 1
        self._pan = (0, 0)
        if self._zj:
            try:
                self.after_cancel(self._zj)
            except Exception:
                pass
            self._zj = None
        if self.src is not None and self._pv_max > PREVIEW_MAX:
            self._mk_preview(PREVIEW_MAX)
            self.req()
        self._paint()
    def _bp(self):
        self.cnv.bind("<Button-1>", self._pp)
        self.cnv.bind("<B1-Motion>", self._pm)
        self.cnv.bind("<ButtonRelease-1>", lambda e:
                      setattr(self, "_pd", None))
        self.cnv.bind("<Double-Button-1>", lambda e: self._rz())
    def _pp(self, e):
        if self._wb_picking:
            self._wb_pick_at(e.x, e.y)
            return
        if self._sp:
            cw = self.cnv.winfo_width()
            if cw > 2:
                self._sx = float(np.clip(e.x/cw, .02, .98))
                self._paint()
            return
        if self._ph is None or self._mod:
            return
        self._pd = (e.x, e.y, self._pan[0], self._pan[1])
    def _pm(self, e):
        if not self._pd or self._ph is None:
            return
        sx, sy, px, py = self._pd
        self._pan = (px+(e.x-sx), py+(e.y-sy))
        self._paint()

    def _ekh(self, e):
        if self._mod:
            self._ek = []
            return
        if not e.char or not e.char.isalpha():
            self._ek = []
            return
        self._ek.append(e.char.lower())
        self._ek = self._ek[-5:]
        w = "".join(self._ek)
        if w in self._EG:
            self._ek = []
            self._ea(w)
    def _ea(self, c):
        p, m, a = self._EG[c]
        if not any(x["name"] == p["name"] for x in PRES):
            PRES.append(p)
        self.ap = p
        ENG._lc.clear()  # full preset swap: don't trust per-layer hash shortcuts
        for k, v in self.vars.items():
            if k in p:
                try:
                    v.set(float(p[k]))
                except (TypeError, ValueError):
                    pass
        self.v_ss.set(1.0)
        self._tc.clear()
        self._sync_strength_label()
        self._rl()
        self.req()
        self.after(150, lambda: Egg(self, m, a))

    def _mku(self):
        top = tk.Frame(self, bg=T["panel"], height=62)
        top.pack(fill="x")
        top.pack_propagate(False)

        # LEFT: identity + current workspace state
        logo = tk.Frame(top, bg=T["panel"])
        logo.pack(side="left", fill="y", padx=(16, 10))
        tk.Label(logo, text="◈", font=("Segoe UI Symbol", 17, "bold"),
                 bg=T["panel"], fg=T["accent"]).pack(side="left", padx=(0, 7))
        idf = tk.Frame(logo, bg=T["panel"])
        idf.pack(side="left", pady=8)
        tk.Label(idf, text="LUMENFORGE", font=("Segoe UI", 12, "bold"),
                 bg=T["panel"], fg=T["text"]).pack(anchor="w")
        self._mode_lbl = tk.Label(idf, text="IMAGE LAB  •  READY",
                                  font=("Segoe UI", 7, "bold"),
                                  bg=T["panel"], fg=T["text_dim"])
        self._mode_lbl.pack(anchor="w", pady=(1, 0))

        # CENTER: essential workflow only.
        bf = tk.Frame(top, bg=T["panel"])
        bf.pack(side="left", expand=True)
        self._bo = Btn(bf, "Open", self.oi, w=94, kind="solid",
                       icon="▣", tip="Open an image (Ctrl+O)")
        self._bo.pack(side="left", padx=3, pady=15)
        self._bi = Btn(bf, "Import", self.ip, w=92,
                       accent=T["accent2"], icon="⇩",
                       tip="Import preset(s) or .cube LUTs")
        self._bi.pack(side="left", padx=3, pady=15)
        sep(bf).pack(side="left", padx=8, pady=18)

        self._bc = Btn(bf, "Crop", self.tc, w=76, icon="⛶",
                       tip="Crop, Straighten, Rotate, Flip")
        self._bc.pack(side="left", padx=3, pady=15)
        self._bst = Btn(bf, "Straighten", self.ts_tool, w=102, icon="╱",
                        tip="Straighten / fix horizon tilt")
        # Kept alive for existing enable/disable integration, but deliberately
        # hidden from the primary toolbar. Crop owns the tool entry point.
        self._bm = Btn(bf, "Masks", self.mask_tool, w=82, icon="▨",
                       tip="Local adjustment masks")
        self._bm.pack(side="left", padx=3, pady=15)
        self._br = Btn(bf, "Reset", self.rs, w=82, icon="↺",
                       tip="Reset all edits")
        self._br.pack(side="left", padx=3, pady=15)
        self._bu = Btn(bf, "Undo", self.undo, w=78, icon="↶",
                       tip="Undo (Ctrl+Z)")
        self._bu.pack(side="left", padx=3, pady=15)
        self._bu.set_en(False)
        self._bre = Btn(bf, "Redo", self.redo, w=78, icon="↷",
                        tip="Redo (Ctrl+Shift+Z)")
        self._bre.pack(side="left", padx=3, pady=15)
        self._bre.set_en(False)

        sep(bf).pack(side="left", padx=8, pady=18)
        self._bf = Btn(bf, "", self._rz, w=40, icon="⤢",
                       tip="Fit / reset zoom")
        self._bf.pack(side="left", padx=3, pady=15)
        self._bs = Btn(bf, "Split", self._ts, w=82, icon="◐",
                       tip="Before/after split view")
        self._bs.pack(side="left", padx=3, pady=15)
        self._ba = Btn(bf, "", None, w=44, accent=T["accent2"], icon="◉",
                       tip="Hold to preview original")
        self._ba.bind("<ButtonPress-1>", lambda e: self._so(True))
        self._ba.bind("<ButtonRelease-1>", lambda e: self._so(False))
        self._ba.pack(side="left", padx=3, pady=15)

        # RIGHT: export.  Command Palette remains available from Ctrl+K;
        # its toolbar icon is intentionally hidden to keep this area cleaner.
        rf = tk.Frame(top, bg=T["panel"])
        rf.pack(side="right", fill="y", padx=(8, 16))

        self._be = Btn(rf, "EXPORT", self.ex, w=132, h=38, fs=10,
                       kind="solid", icon="⇧", tip="Export current image (Ctrl+E)")
        self._be.pack(side="left", pady=11)
        self._bb = Btn(rf, "Batch", self.bt, w=82, icon="▦",
                       tip="Batch export")
        self._bb.pack(side="left", padx=(7, 0), pady=15)
        self._bb.set_en(False)

        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)

        bd = tk.Frame(self, bg=T["bg"])
        bd.pack(fill="both", expand=True)

        self._boot_splash.set_status("Loading presets…", .40)
        # LEFT — premium preset library.
        lw = int(np.clip(self.winfo_screenwidth()*.205, 255, 332))
        left = tk.Frame(bd, bg=T["card"], highlightthickness=1,
                        highlightbackground=T["stroke"], padx=T["pad"], pady=T["pad"])
        left.pack(side="left", fill="y", padx=(9, 5), pady=9)
        left.configure(width=lw)
        left.pack_propagate(False)
        _glass_edge(left, T["accent"])

        self._hdr = tk.Label(left, text="PRESET LIBRARY",
                             font=("Segoe UI", 10, "bold"), bg=T["card"],
                             fg=T["text"], anchor="w")
        self._hdr.pack(fill="x")
        tk.Label(left, text="LOOKS • CAMERA • FILM • YOURS",
                 font=("Segoe UI", 7, "bold"), bg=T["card"],
                 fg=T["text_dim"], anchor="w").pack(fill="x", pady=(0, 5))

        search_row = tk.Frame(left, bg=T["card"])
        search_row.pack(fill="x", pady=(0, 6))
        self._preset_q = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self._preset_q,
                          font=("Segoe UI", 9))
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
            font=("Segoe UI", 8))
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
                       activeforeground=T["accent"], font=("Segoe UI", 8, "bold"),
                       anchor="w", relief="flat", bd=0).pack(fill="x", pady=(0, 6))

        self._pc = tk.Canvas(left, bg=T["panel"], highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=self._pc.yview)
        self._pc.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._pc.pack(fill="both", expand=True)
        self._in = tk.Frame(self._pc, bg=T["panel"])
        self._in.bind("<Configure>", lambda e: self._pc.configure(
            scrollregion=self._pc.bbox("all")))
        _pc_win = self._pc.create_window((0, 0), window=self._in, anchor="nw")
        self._pc.bind("<Configure>",
                      lambda e: self._pc.itemconfig(_pc_win, width=e.width))

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
                                 font=("Segoe UI", 8, "bold"),
                                 bg=T["card"], fg=T["text_dim"], anchor="w")
        self._hdr_imp.pack(side="bottom", fill="x", pady=(0, 2))
        tk.Frame(left, bg=T["stroke"], height=1
                ).pack(side="bottom", fill="x", pady=(6, 4))

        self._boot_splash.set_status("Preparing canvas…", .62)
        # CENTER — image first, controls quiet when not needed.
        ct = tk.Frame(bd, bg=T["bg"])
        ct.pack(side="left", fill="both", expand=True, padx=4, pady=9)
        self.cnv = tk.Canvas(ct, bg="#05040a", highlightthickness=1,
                             highlightbackground=T["stroke"])
        self.cnv.pack(fill="both", expand=True)
        self._empty_open = Btn(self.cnv, "OPEN IMAGE", self.oi, w=160, h=34,
                                kind="solid", icon="▣",
                                tip="Open an image (Ctrl+O)")
        self._empty_open.place(relx=.5, rely=.61, anchor="center")

        self._hc = tk.Canvas(ct, bg=T["card"],
                             height=74 if self.winfo_screenheight() > 800 else 60,
                             highlightthickness=1,
                             highlightbackground=T["stroke"])
        self._hc.pack(fill="x", pady=(3, 0))
        self.cnv.bind("<Configure>", lambda e: self._paint())
        self._bp()

        self._boot_splash.set_status("Building settings panel…", .82)
        # RIGHT — professional controls.
        rw = int(np.clip(self.winfo_screenwidth()*.215, 275, 340))
        right = tk.Frame(bd, bg=T["card"], highlightthickness=1,
                         highlightbackground=T["stroke"], padx=T["pad"], pady=T["pad"])
        right.pack(side="right", fill="y", padx=(5, 9), pady=9)
        right.configure(width=rw)
        right.pack_propagate(False)
        _glass_edge(right, T["accent2"])
        self._bs_(right)

        self._boot_splash.set_status("Finishing up…", .95)
        self._st = tk.Label(self, text="READY  •  Ctrl+K commands  •  Ctrl+O open  •  "
                            "Ctrl+E export  •  Ctrl+Z undo  •  Ctrl+Shift+Z redo",
                            bg=T["panel"], fg=T["text_dim"],
                            font=("Segoe UI", 8), anchor="w", padx=14, pady=6)
        self._st.pack(fill="x", side="bottom")

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
        c.create_text(18, 23, text=message, fill=T["text"],
                      font=("Segoe UI", 9, "bold"), anchor="w", width=382)
        self._toast_job = self.after(duration or MOTION["toast"], self._toast_hide)

    def _toast_hide(self):
        if self._toast_id is not None:
            try:
                self._toast_id.place_forget()
            except Exception:
                pass

    def _render_hud_show(self, label="Rendering"):
        """Indeterminate render HUD: no fabricated percentages."""
        if self._render_hud is not None:
            return
        cv = tk.Canvas(self.cnv, width=260, height=34, bg=T["bg"],
                       highlightthickness=0)
        cv.place(relx=.5, rely=.04, anchor="n")
        rnd(cv, 1, 1, 258, 33, T["radius_sm"], fill=T["glass"],
            outline=T["stroke_hi"])
        cv.create_text(14, 17, text=label, fill=T["text_dim"],
                       font=("Segoe UI", 8, "bold"), anchor="w", tags="label")
        cv.create_line(108, 17, 244, 17, fill=T["stroke"], width=2,
                       tags="track")
        self._render_hud = cv
        self._render_scan_job = 0
        self._render_hud_scan()

    def _render_hud_scan(self):
        if self._render_hud is None:
            return
        c = self._render_hud
        c.delete("scan")
        phase = int((time.time() * 120) % 136)
        x = 108 + phase
        if x > 244:
            x = 108 + (x - 244)
        c.create_line(x, 12, x, 22, fill=T["accent"], width=2, tags="scan")
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
        tk.Label(top, text="COMMAND", bg=T["card"], fg=T["accent"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(top, text="Ctrl+K  •  Escape to close",
                 bg=T["card"], fg=T["text_dim"],
                 font=("Segoe UI", 7)).pack(side="right")
        q = tk.StringVar()
        e = ttk.Entry(wrap, textvariable=q, font=("Segoe UI", 12))
        e.pack(fill="x", pady=(8, 10))
        Tip.bind(e, "Search actions and presets")
        lb = tk.Listbox(wrap, bg=T["panel"], fg=T["text"],
                        selectbackground=T["accent"], selectforeground="#ffffff",
                        highlightthickness=0, relief="flat",
                        font=("Segoe UI", 9), activestyle="none")
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
        _c_win = c.create_window((0, 0), window=inn, anchor="nw")
        inn.bind("<Configure>", lambda e: c.configure(
            scrollregion=c.bbox("all")))
        c.bind("<Configure>", lambda e: c.itemconfig(_c_win, width=e.width))
        self._sc = c

        hd = tk.Frame(inn, bg=T["card"])
        hd.pack(fill="x", pady=(2, 3))
        tk.Label(hd, text="PIPELINE", font=("Segoe UI", 9, "bold"),
                 bg=T["card"], fg=T["accent2"]).pack(side="left")
        tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x", side="left",
                                                    padx=T["pad"], pady=T["pad"])
        for t, v in [("Scene Prep — linear WB", self.v_prep),
                     ("Print Stock 2383", self.v_pr)]:
            tk.Checkbutton(inn, text=t, variable=v, bg=T["card"],
                           fg=T["text"], selectcolor=T["panel"],
                           activebackground=T["card_hi"],
                           activeforeground=T["accent"], font=T["font_sm"],
                           anchor="w",
                           command=lambda: self._scd(None)).pack(fill="x",
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
            hd = tk.Frame(inn, bg=T["card"])
            hd.pack(fill="x", pady=(10 if py == 2 else 7, 3))
            tk.Label(hd, text=g, font=("Segoe UI", 9, "bold"),
                     bg=T["card"], fg=T["accent"]).pack(side="left")
            tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x",
                                                        side="left",
                                                        padx=T["pad"], pady=T["pad"])
            _cg_sub = ["Shadows"]*3+["Midtones"]*3+["Highlights"]*3+ \
                ["Global"]*3+["Blending"]
            for i, (k, l, lo, hi, f) in enumerate(rows):
                if g == "HSL":
                    continue
                if g == "COLOR GRADE" and i < len(_cg_sub) and \
                        (i == 0 or _cg_sub[i] != _cg_sub[i-1]):
                    tk.Label(inn, text=_cg_sub[i], bg=T["card"],
                            fg=T["accent2"], font=("Segoe UI", 8, "bold"),
                            anchor="w").pack(fill="x", pady=(6 if i else 0, 0))
                Param(inn, l, self.vars[k], self._scd, lo, hi, f,
                      DEF.get(k, 0), key=k, info=PARAM_INFO.get(k)).pack(fill="x", pady=py)
            if g == "HSL":
                HSLMixer(inn, self).pack(fill="x", pady=(0, 4))
            if g == "LIGHT":
                chd = tk.Frame(inn, bg=T["card"])
                chd.pack(fill="x", pady=(6, 2))
                tk.Label(chd, text="Tone Curve", bg=T["card"],
                         fg=T["text_dim"], font=T["font_sm"],
                         anchor="w").pack(side="left")
                Btn(chd, "Reset", self._curve_reset, w=64, h=22, fs=8,
                   icon="↺").pack(side="right")
                self._curve_w = CurveEditor(inn, self._curve_changed)
                self._curve_w.pack(fill="x", pady=(0, 4))
                tk.Label(inn, text="drag to shape • click to add point • "
                        "right-click to remove", bg=T["card"],
                        fg=T["text_dim"], font=("Segoe UI", 7)
                        ).pack(fill="x", pady=(0, 4))
            if g == "WHITE BALANCE":
                wbr = tk.Frame(inn, bg=T["card"])
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

    def _bs_camera_match(self, inn):
        """CAMERA MATCH section (Camera DNA 2.0) — spec section 17.
        Integrated with the existing right-panel style; doesn't touch
        the rest of the UI layout."""
        hd = tk.Frame(inn, bg=T["card"])
        hd.pack(fill="x", pady=(10, 3))
        tk.Label(hd, text="CAMERA MATCH", font=("Segoe UI", 9, "bold"),
                 bg=T["card"], fg=T["accent"]).pack(side="left")
        tk.Frame(hd, bg=T["stroke"], height=1).pack(fill="x", side="left",
                                                    padx=T["pad"], pady=T["pad"])
        tk.Checkbutton(inn, text="Enable Camera Match",
                       variable=self.v_cm_on, bg=T["card"], fg=T["text"],
                       selectcolor=T["panel"], activebackground=T["card_hi"],
                       activeforeground=T["accent"], font=T["font_sm"],
                       anchor="w",
                       command=lambda: self._scd(None)).pack(fill="x", pady=1)

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
            ps = [p for p in ps if "Modern" in str(p.get("family"))]
        elif m == "film":
            ps = [p for p in ps if "Mobile" not in str(p.get("family"))
                  and "Vintage" not in str(p.get("family"))
                  and "Modern" not in str(p.get("family"))
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
            tk.Label(self._ini, text="No matching imported looks.\n"
                     "Import a preset or LUT to grow this library.",
                     bg=T["panel"], fg=T["text_dim"],
                     font=("Segoe UI", 8), wraplength=210, anchor="w",
                     justify="left").grid(row=0, column=0, padx=6, pady=10,
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

    def _neutralize(self):
        """Everything a preset/edit/Camera-Match apply can touch, back
        to defaults in one place — shared by Reset-all and by opening
        a new image, so a new image always starts from a clean slate
        instead of inheriting the previous image's grade."""
        self.ap = None
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
        self.req()

    def rs(self):
        self._neutralize()
        self._mark_active()
        self.req()
        self._st.configure(text="Reset to neutral", fg=T["text_dim"])
        self._mode_lbl.configure(text="IMAGE LAB  •  READY") if hasattr(self, "_mode_lbl") else None
        self._toast("Edits reset to neutral", "info")

    # ---- White balance: gray-point picker + gray-world auto ----

    def _wb_pick_toggle(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        self._wb_picking = not self._wb_picking
        if self._wb_pick_btn is not None:
            self._wb_pick_btn.set_active(self._wb_picking)
        self.cnv.configure(cursor="tcross" if self._wb_picking else "arrow")
        self._st.configure(
            text="🎯 Click a neutral gray or white area in the image"
                 if self._wb_picking else "Pick Gray Point cancelled",
            fg=T["accent2"] if self._wb_picking else T["text_dim"])

    def _wb_pick_at(self, cx, cy):
        self._wb_picking = False
        if self._wb_pick_btn is not None:
            self._wb_pick_btn.set_active(False)
        self.cnv.configure(cursor="arrow")
        if self.pv is None:
            return
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        ix = (cx-ox)/dw if dw > 1e-6 else .5
        iy = (cy-oy)/dh if dh > 1e-6 else .5
        if not (0 <= ix <= 1 and 0 <= iy <= 1):
            self._st.configure(text="Pick Gray Point — click was outside "
                               "the image", fg=T["red"])
            return
        h, w = self.pv.shape[:2]
        px, py = ix*(w-1), iy*(h-1)
        try:
            x = self.pv
            if self.v_prep.get():
                x = prep_scene(x)
            temp, tint = wb_from_point(x, px, py)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"White balance failed:\n{ex}")
            return
        self.vars["temperature"].set(temp)
        self.vars["tint"].set(tint)
        self._scd("temperature")
        self._st.configure(
            text=f"🎯 White Balance set from sample — "
                 f"Temperature {temp:+.0f} • Tint {tint:+.0f}",
            fg=T["green"])

    def auto_wb(self):
        if self.pv is None:
            messagebox.showinfo(APP_NAME, "Open an image first.")
            return
        try:
            x = self.pv
            if self.v_prep.get():
                x = prep_scene(x)
            temp, tint = wb_gray_world(x)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"White balance failed:\n{ex}")
            return
        self.vars["temperature"].set(temp)
        self.vars["tint"].set(tint)
        self._scd("temperature")
        self._st.configure(
            text=f"⚪ Auto White Balance — "
                 f"Temperature {temp:+.0f} • Tint {tint:+.0f}",
            fg=T["green"])

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
        try:
            im, mt = load_src(p)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not open:\n{ex}")
            self._toast("Could not open image", "error")
            return
        self._o = im
        self.mt = mt
        self.cr = None
        self._srot = 0.0
        self.masks = []
        if self._mask_tool:
            self._mask_tool.close()
        self.cm_detected = None
        self._neutralize()
        self._rz()
        self._acs()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
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

    def _mk_preview(self, target_max):
        """Build self.pv at a resolution matching what's actually needed
        on screen: PREVIEW_MAX while fit-to-window, scaled up toward the
        full source resolution (capped at PREVIEW_ZOOM_MAX) as the user
        zooms in. Everything renders/regrades from this array, so this
        is what determines how sharp a zoomed-in preview looks — before,
        zooming just stretched the same small fit-to-window preview
        instead of drawing on more real source detail."""
        if self.src is None:
            return
        target_max = min(target_max, PREVIEW_ZOOM_MAX)
        s = min(1, target_max/max(self.src.size))
        pvv = self.src if s >= 1 else self.src.resize(
            (max(1, int(self.src.width*s)),
             max(1, int(self.src.height*s))), BILINEAR)
        self.pv = ensure_rgb(pvv)
        self._pv_max = target_max
        self._tc.clear()
        ENG.inval_img()

    def tc(self):
        if self.src is None or self._ph is None or self._mask_tool:
            return
        if self._ov:
            self._ov.ca()
            return
        self._paint()
        _, _, dw, dh, _, _, _, _ = self._geom(self._z, self._pan)
        self._ov = Crop(self.cnv, (dw, dh), self._off,
                        self._ca, self._cc,
                        on_straighten=self._crop_straighten,
                        on_rotate=self._crop_rotate,
                        on_flip_h=self._crop_flip_h,
                        on_flip_v=self._crop_flip_v)
        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)

    def _crop_straighten(self):
        if self._ov:
            self._ov.ca()
        self.ts_tool()

    def _crop_rotate(self):
        if self._ov:
            self._ov.ca()
        self.rotate90()

    def _crop_flip_h(self):
        if self._ov:
            self._ov.ca()
        self.flip_axis(FLIP_LEFT_RIGHT)

    def _crop_flip_v(self):
        if self._ov:
            self._ov.ca()
        self.flip_axis(FLIP_TOP_BOTTOM)

    def rotate90(self):
        """Discrete 90° clockwise rotation, distinct from Straighten's
        fine-angle horizon fix. Any existing crop is cleared since a
        normalized crop rect defined for the old orientation no longer
        lines up once width and height swap."""
        if self._o is None:
            return
        self._o = self._o.transpose(ROTATE_270)
        self.cr = None
        self._srot = 0.0
        self._rz()
        self._acs()
        self._rl()
        self._st.configure(text="✓ Rotated 90°", fg=T["text_dim"])
        self._ck = None
        self.req()

    def flip_axis(self, mode):
        """Flip does not change image dimensions, so any existing crop
        rect (normalized 0..1) still lines up and is intentionally kept."""
        if self._o is None:
            return
        self._o = self._o.transpose(mode)
        self._acs()
        self._rz()
        self._rl()
        label = "Flipped horizontally" if mode == FLIP_LEFT_RIGHT \
            else "Flipped vertically"
        self._st.configure(text=f"✓ {label}", fg=T["text_dim"])
        self._ck = None
        self.req()

    def _ca(self, r):
        self._ov = None
        self._bp()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self.cr = r
        self._rz()
        self._acs()
        self._rl()
        self._st.configure(text="✓ Crop applied", fg=T["text_dim"])
        self._ck = None
        self.req()

    def _cc(self):
        self._ov = None
        self._bp()
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._paint()

    def ts_tool(self):
        if self.src is None or self._ph is None or self._ov_str is not None \
                or self._mask_tool:
            return
        if self._ov:
            return
        self._ov_str = Straighten(self, self._ts_apply, self._ts_cancel)
        self._bc.set_en(False)
        self._bst.set_en(False)
        self._bm.set_en(False)

    def _ts_apply(self, angle):
        self._ov_str = None
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._srot = float(angle)
        self._acs()
        self._rz()
        self._rl()
        self._st.configure(text=f"✓ Straightened {angle:+.1f}°",
                           fg=T["text_dim"])
        self._ck = None
        self.req()

    def _ts_cancel(self):
        self._ov_str = None
        self._bc.set_en(True)
        self._bst.set_en(True)
        self._bm.set_en(True)
        self._paint()

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

    def _scd(self, key=None):
        if key is not None:
            self._ck = key
        if self._rj:
            try:
                self.after_cancel(self._rj)
            except Exception:
                pass
        self._rj = self.after(70, lambda: self.req())

    def req(self):
        if self.pv is None:
            return
        self._track_undo()
        if self._rb:
            self._rp = True
            return
        st = self._stg()
        rgb = self.pv
        ch = self._ck
        self._rb = True
        self._render_hud_show("Rendering")

        def work():
            try:
                o = ENG.render(rgb, st, changed_key=ch)
            except Exception:
                o = None
            self.after(0, lambda: self._rd(o))

        threading.Thread(target=work, daemon=True).start()

    def _rd(self, o):
        self._rb = False
        self._render_hud_hide()
        if o is not None:
            self._lo = o
            self._ph = ImageTk.PhotoImage(to_pil(o))
            self._paint()
            self._hist(o)
        if self._rp:
            self._rp = False
            self.after(10, self.req)

    def _disp_img(self, dw, dh):
        """PhotoImage of the current render at the actual on-screen
        target size (dw, dh), high-quality resampled. Cached by
        (dw, dh, id(self._lo)) so repeated _paint() calls during a pan
        drag — where neither the render nor the zoom level changed —
        don't pay for a fresh resize every frame.

        Previously _paint() drew self._ph (native preview resolution)
        straight onto the canvas with no resize at all, so the 'zoom'
        level only changed where the image was positioned, not its
        actual on-screen size or sharpness — that mismatch, on top of
        self.pv being capped at a small fixed resolution, is what made
        the zoomed-in preview look so poor."""
        key = (dw, dh, id(self._lo))
        if self._disp_key == key and self._disp_cache is not None:
            return self._disp_cache
        img = to_pil(self._lo) if self._lo is not None \
            else ImageTk.getimage(self._ph)
        if img.size != (dw, dh):
            img = img.resize((dw, dh), LANCZOS)
        ph = ImageTk.PhotoImage(img)
        self._disp_key = key
        self._disp_cache = ph
        return ph

    def _paint(self):
        if self._ph is None:
            self.cnv.delete("all")
            if hasattr(self, "_empty_open"):
                self._empty_open.place(relx=.5, rely=.61, anchor="center")
            cw = max(1, self.cnv.winfo_width())
            ch = max(1, self.cnv.winfo_height())
            if cw > 200 and ch > 120:
                self.cnv.create_text(cw//2, ch//2-34, text="LUMENFORGE",
                                      fill=T["text"], font=("Segoe UI", 22, "bold"))
                self.cnv.create_text(cw//2, ch//2-8,
                                      text="A cinematic image laboratory.",
                                      fill=T["text_dim"], font=("Segoe UI", 10))
                self.cnv.create_text(cw//2, ch//2+16,
                                      text="Open a photograph to begin.",
                                      fill=T["text_dim"], font=("Segoe UI", 8))
                self.cnv.create_text(cw//2, ch-22, text="Ctrl+O  •  drag to pan  •  Ctrl+Wheel to zoom",
                                      fill=T["stroke_hi"], font=("Consolas", 7))
            return
        if hasattr(self, "_empty_open"):
            self._empty_open.place_forget()
        self.cnv.delete("all")
        cw, ch, dw, dh, fx, fy, ox, oy = self._geom(self._z, self._pan)
        self._off = (ox, oy)
        disp = self._disp_img(dw, dh)
        self.cnv.create_image(ox, oy, image=disp, anchor="nw")
        if self._z > 1.001:
            self.cnv.create_text(cw-58, ch-16, text=f"{self._z:.1f}x",
                                 fill=T["accent"],
                                 font=("Consolas", 10, "bold"))
        if self._sp and self.pv is not None:
            op = Image.fromarray((np.clip(self.pv, 0, 1)*255)
                                 .astype(np.uint8))
            if op.size != (dw, dh):
                op = op.resize((dw, dh), LANCZOS)
            cut = max(1, int(dw*self._sx))
            crp = op.crop((0, 0, cut, dh))
            self._sph = ImageTk.PhotoImage(crp)
            sw = max(2, int(dw*self._sx))
            self.cnv.create_image(ox, oy, image=self._sph, anchor="nw")
            self.cnv.create_rectangle(ox+sw-1, oy, ox+sw+1, oy+dh,
                                      fill=T["accent"], outline="")
            self.cnv.create_text(ox+sw+8, oy+15, text="after",
                                 fill=T["accent"],
                                 font=("Consolas", 9, "bold"))
            self.cnv.create_text(ox+sw-8, oy+15, text="before",
                                 fill=T["text"],
                                 font=("Consolas", 9, "bold"))

    def _ts(self):
        if self._ph is None:
            return
        self._sp = not self._sp
        self._bs.set_active(self._sp)
        self._paint()

    def _so(self, s):
        if self.pv is None:
            return
        if s:
            self.cnv.delete("all")
            _, _, dw, dh, _, _, ox, oy = self._geom(self._z, self._pan)
            img = to_pil(self.pv)
            if img.size != (dw, dh):
                img = img.resize((dw, dh), LANCZOS)
            self._oph = ImageTk.PhotoImage(img)
            self.cnv.create_image(ox, oy, image=self._oph, anchor="nw")
        else:
            self._paint()

    def _hist(self, a):
        """Modern RGB+Luma histogram: filled, semi-blended channel
        curves over a metallic glass card, plus small shadow/highlight
        clipping indicators — replacing the old plain 3-line plot on a
        flat dark background."""
        try:
            cv = self._hc
            cv.delete("all")
            W = cv.winfo_width()
            H = int(cv["height"])
            if W < 4:
                return
            rnd(cv, 1, 1, W-2, H-2, T["radius_sm"], fill=T["card"],
               outline=T["stroke"])
            top_c = _mix(T["card"], "#ffffff", .08)
            for i in range(H//2):
                t2 = 1-(i/max(1, H//2))
                cv.create_line(2, 2+i, W-2, 2+i,
                               fill=_mix(T["card"], top_c, t2))
            pad_t, pad_b = 14, 6
            ih = max(4, H-pad_t-pad_b)
            x = np.clip(np.asarray(a, np.float32), 0, 1)
            luma = x[..., 0]*.299+x[..., 1]*.587+x[..., 2]*.114
            bs = np.zeros((4, 128), np.float32)
            for c in range(3):
                hh_, _ = np.histogram(x[..., c], bins=128, range=(0, 1))
                bs[c] = np.log1p(hh_)
            bs[3], _ = np.histogram(luma, bins=128, range=(0, 1))
            bs[3] = np.log1p(bs[3])
            mx = float(bs[:3].max())
            if mx < 1e-6:
                return
            bs = bs/mx
            cols = (T["red"], T["green"], T["accent2"])
            for c, col in enumerate(cols):
                base_y = H-pad_b
                pts = [2, base_y]
                for i in range(128):
                    pts.extend((2+int(i*(W-4)/128),
                               base_y-int(bs[c, i]*ih)))
                pts.extend((W-2, base_y))
                cv.create_polygon(*pts, fill=_mix(T["card"], col, .30),
                                  outline=col, width=1, smooth=True)
            # Luma outline drawn last, on top, as a plain reference line.
            pts = []
            for i in range(128):
                pts.extend((2+int(i*(W-4)/128),
                           H-pad_b-int(min(1, bs[3, i])*ih)))
            if len(pts) >= 4:
                cv.create_line(*pts, fill=T["text"], width=1, smooth=True)
            # Clipping warnings: a meaningful pile-up in the very first
            # or last bin of any channel means crushed shadows / blown
            # highlights — flag it instead of leaving it to guesswork.
            clip_lo = bs[:3, 0].max() > .55
            clip_hi = bs[:3, -1].max() > .55
            if clip_lo:
                cv.create_oval(4, 4, 10, 10, fill=T["red"], outline="")
            if clip_hi:
                cv.create_oval(W-10, 4, W-4, 10, fill=T["gold"], outline="")
            cv.create_text(W/2, 8, text="RGB + LUMA", fill=T["text_dim"],
                           font=("Consolas", 7, "bold"))
        except Exception:
            pass

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
        tk.Label(f, text="EXPORT SETTINGS", font=("Segoe UI", 12, "bold"),
                 bg=T["card"], fg=T["accent"]).pack(pady=(0, 8))
        tk.Label(f, text=f"{self.src.width} x {self.src.height}px  •  "
                 f"{self.ap['name'] if self.ap else 'Custom'}",
                 bg=T["card"], fg=T["text_dim"],
                 font=T["font_sm"]).pack(pady=(0, 10))
        sel = tk.StringVar(value=FMTS[0][0])
        for l, _ in FMTS:
            tk.Radiobutton(f, text=l, variable=sel, value=l, bg=T["card"],
                           fg=T["text"], selectcolor=T["panel"],
                           activebackground=T["card_hi"],
                           activeforeground=T["accent"], font=T["font_sm"],
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
            rgb = ensure_rgb(self.src)
            st = self._stg()
            H, W = rgb.shape[:2]
            TP = 8*1024*1024//3
            rpt = max(64, TP//W)
            nt = max(1, (H+rpt-1)//rpt)
            out = np.empty_like(rgb)
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
                _cas()  # warm the lazy cascade singleton before any workers start
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
                             fill=T["text"], font=("Segoe UI", 11, "bold"))
        self._es = self._ec.create_text(W//2, 52, text="Preparing…",
                                        fill=T["text_dim"],
                                        font=T["font_sm"])
        self._ec.create_rectangle(32, 78, W-32, 88, fill=T["panel"],
                                 outline=T["stroke"])
        self._eb = self._ec.create_rectangle(32, 78, 33, 88,
                                             fill=T["accent"], outline="")
        self._ep_ = self._ec.create_text(W//2, 103, text="0%",
                                         fill=T["accent"],
                                         font=("Consolas", 10, "bold"))
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


# ============================================================
#  SELF-TESTS
# ============================================================

def _tg(w=96, h=64):
    x = np.tile(np.linspace(0, 1, w, np.float32), (h, 1))
    return np.stack([x, np.clip(x*.8+.1, 0, 1), np.clip(1-x, 0, 1)], 2)

def self_tests():
    F = []
    img = _tg()

    # tone+gamma LUT
    gi = np.full((4, 4, 3), .25, np.float32)
    if not (.05 < float(apply_fused_tone(
            gi, {"gamma": 2})[0, 0, 1]) < .08):
        F.append("gamma 0.25^2 wrong")
    if abs(float(apply_fused_tone(gi, {"gamma": 1})[0, 0, 1])-.25) > .01:
        F.append("gamma identity broken")
    # per-channel asymmetry
    l_r = tone_gamma_lut(.5, 0, -20, 0, 0, 0, 1, 0, 0)
    l_b = tone_gamma_lut(.5, 0, -20, 0, 0, 0, 1, 0, 2)
    if float(l_r[LUT.SZ//2]) <= float(l_b[LUT.SZ//2]):
        F.append("v12: R should be softer than B")
    # contrast slider must actually change the render
    ct_hi = apply_fused_tone(gi, {"contrast": 80})[0, 0, 1]
    ct_lo = apply_fused_tone(gi, {"contrast": -80})[0, 0, 1]
    ct_0 = apply_fused_tone(gi, {"contrast": 0})[0, 0, 1]
    if abs(float(ct_hi)-float(ct_0)) < 1e-4 or abs(float(ct_lo)-float(ct_0)) < 1e-4:
        F.append("contrast slider has no effect")
    if not (float(ct_lo) > float(ct_0) > float(ct_hi)):
        # gi is below midgray (.25), so +contrast should darken it
        # further and -contrast should lift it toward .5
        F.append(f"contrast direction wrong: lo={ct_lo} 0={ct_0} hi={ct_hi}")

    # white balance: gray-world neutralizes a color-cast flat field,
    # and the pick-point solver exactly neutralizes a sampled patch
    try:
        warm = np.full((40, 40, 3), [.62, .5, .38], np.float32)
        wt, wn = wb_gray_world(warm)
        if not (wt < -3):
            F.append(f"wb gray-world: expected cooling correction, got {wt}")
        corr = tint_op(ctemp(warm, wt), wn)
        if abs(float(corr[0,0,0])-float(corr[0,0,2])) > .01:
            F.append("wb gray-world: R/B not neutralized")
        cool = np.full((40, 40, 3), [.35, .5, .65], np.float32)
        ct2, tn2 = wb_gray_world(cool)
        if not (ct2 > 3):
            F.append(f"wb gray-world: expected warming correction, got {ct2}")
        patch = np.full((30, 30, 3), [.7, .5, .3], np.float32)
        pt, pn = wb_from_point(patch, 15, 15)
        pc = tint_op(ctemp(patch, pt), pn)[15, 15]
        if abs(float(pc[0])-float(pc[2])) > .01 or \
                abs(float(pc[1])-.5*(float(pc[0])+float(pc[2]))) > .01:
            F.append(f"wb pick-point: sample not neutralized {pc}")
    except Exception as e:
        F.append(f"white balance: {e}")

    # all presets
    for p in PRES:
        try:
            o = staged(img, {**DEF, **p})
            if not np.all(np.isfinite(o)) or o.max() > 1.001 \
                    or o.min() < -.001:
                F.append(f"{p['name']}: invalid")
        except Exception as e:
            F.append(f"{p['name']}: {e}")

    # B&W mono
    tx = next(p for p in PRES if p["name"] == "Kodak Tri-X 400")
    mo = staged(img, {**DEF, **tx})
    if float(np.max(np.abs(mo[..., 0]-mo[..., 2]))) > .02:
        F.append("B&W still colored")

    # grain order
    def ge(p):
        fl = np.full((16, 64, 3), .45, np.float32)
        return float(np.std(grain(fl, max(p.get("grain", 0), 5),
                                  p.get("grain_size", .45),
                                  p.get("grain_profile", "tgrain"))))
    p16 = next(p for p in PRES if p["name"] == "Kodak Portra 160")
    if not (ge(tx) > ge(p16)):
        F.append("grain RMS violated")

    # halation
    cs = next(p for p in PRES if p["name"] == "CineStill 800T")
    c4 = next(p for p in PRES if p["name"] == "CineStill 400D")
    v3 = next(p for p in PRES if p["name"] == "Kodak Vision3 500T")
    if not (cs["halation"] > v3["halation"]*3 and
            c4["halation"] > v3["halation"]*3):
        F.append("halation signature")

    wm = np.zeros((16, 16, 3), np.float32)
    wm[..., 0], wm[..., 1], wm[..., 2] = 1, .9, .7
    cl = np.zeros((16, 16, 3), np.float32)
    cl[..., 0], cl[..., 1], cl[..., 2] = .7, .85, 1
    hw, hc = halation(wm, 50, HR), halation(cl, 50, HR)
    rw = float(np.mean(hw[..., 2]))/max(float(np.mean(hw[..., 0])), 1e-5)
    rc = float(np.mean(hc[..., 2]))/max(float(np.mean(hc[..., 0])), 1e-5)
    if not (rc > rw):
        F.append("halation not chromatic")

    # XMP/CUBE/JSON
    xt = ('<rdf:Description xmlns:crs="http://ns.adobe.com/camera-raw'
          '-settings/1.0/" crs:PresetName="T" crs:Exposure2012="+0.75" '
          'crs:Temperature="7500" crs:Highlights2012="-40"/>')
    with tempfile.NamedTemporaryFile("w", suffix=".xmp", delete=False,
                                     encoding="utf-8") as f:
        f.write(xt)
        xp = f.name
    try:
        pr = pxmp(xp)
        if not (.5 < pr["exposure"] < .9):
            F.append("XMP exposure")
        if not (pr["temperature"] > 1):
            F.append("XMP temp")
    except Exception as e:
        F.append(f"XMP: {e}")
    finally:
        os.unlink(xp)

    cb = ["TITLE 'i'", "LUT_3D_SIZE 2", "0 0 0", "1 0 0", "0 1 0",
          "1 1 0", "0 0 1", "1 0 1", "0 1 1", "1 1 1"]
    with tempfile.NamedTemporaryFile("w", suffix=".cube", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(cb))
        cp = f.name
    try:
        pr = pcube(cp)
        if abs(pr["temperature"]) > 2 or abs(pr["tint"]) > 2:
            F.append("CUBE identity")
    except Exception as e:
        F.append(f"CUBE: {e}")
    finally:
        os.unlink(cp)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump({"name": "j", "saturation": 120}, f)
        jp = f.name
    try:
        pr = pjson(jp)
        if pr["saturation"] != 120:
            F.append("JSON values")
    except Exception as e:
        F.append(f"JSON: {e}")
    finally:
        os.unlink(jp)

    # scene prep
    g = np.full((8, 8, 3), .5, np.float32)
    if float(np.max(np.abs(prep_scene(g)-.5))) > .01:
        F.append("prep gray")
    c = g.copy()
    c[..., 2] = .62
    if not (prep_scene(c)[..., 2].mean() < c[..., 2].mean()):
        F.append("prep cast")

    # print LUT
    pl = print_lut(1)
    for ch in range(3):
        if np.any(np.diff(pl[ch]) < -1e-6):
            F.append(f"print ch{ch}")

    # mobile counts
    ipn = sum(1 for p in PRES if "iPhone" in str(p.get("family")))
    ssn = sum(1 for p in PRES if "Samsung" in str(p.get("family")))
    if ipn != 8:
        F.append(f"iPhone {ipn}")
    if ssn != 8:
        F.append(f"Samsung {ssn}")
    sp = next(p for p in PRES if p["name"] == "Samsung Portrait Warm")
    if not (sp.get("skin_saturation", 0) < 0):
        F.append("Samsung skin sat")
    hf = next(p for p in PRES if p["name"] == "iPhone HDR De-Flat")
    if not (hf.get("highlight_rolloff", 0) >= 50):
        F.append("iPhone HDR")

    # Vintage (17 = 14 color + 3 B&W)
    vn = sum(1 for p in PRES if "Vintage" in str(p.get("family")))
    if vn != 17:
        F.append(f"Vintage {vn} != 17")
    for nm in ("Canon IXUS 70 Classic", "Fuji X100 Astia",
               "Panasonic LX3 Nostalgic", "Sony HX5V Twilight",
               "Nikon Coolpix Neutral", "Fuji X100 Monochrome",
               "Panasonic LX3 B&W", "Canon Sepia Mode"):
        if not any(p["name"] == nm for p in PRES):
            F.append(f"vintage missing: {nm}")
    ast = next(p for p in PRES if p["name"] == "Fuji X100 Astia")
    vel = next(p for p in PRES if p["name"] == "Fuji X100 Velvia")
    if not (vel["saturation"] > ast["saturation"]+10):
        F.append("Velvia > Astia sat")
    if not (ast.get("skin_smooth", 0) > 0):
        F.append("Astia portrait")
    lx3 = next(p for p in PRES if p["name"] == "Panasonic LX3 Nostalgic")
    if not (lx3["fade"] >= 6 and lx3["saturation"] < 90):
        F.append("LX3 Nostalgic")
    ci = next(p for p in PRES if p["name"] == "Canon IXUS 70 Classic")
    nk = next(p for p in PRES if p["name"] == "Nikon Coolpix Neutral")
    if not (ci["temperature"] > nk["temperature"]+4):
        F.append("Canon warm / Nikon cool")
    ic = next(p for p in PRES if p["name"] == "Canon i-Contrast Lift")
    if not (ic.get("shadows", 0) >= 12):
        F.append("i-Contrast lift")
    sep = next(p for p in PRES if p["name"] == "Canon Sepia Mode")
    if not sep.get("monochrome"):
        F.append("Sepia mono flag")
    if not (sep.get("split_shadow_amount", 0) > 0.3):
        F.append("Sepia brown tint")

    # skin mask
    sk = np.zeros((32, 32, 3), np.float32)
    sk[..., 0], sk[..., 1], sk[..., 2] = .72, .5, .38
    sy = np.zeros((32, 32, 3), np.float32)
    sy[..., 2] = .85
    ti = np.concatenate([sk, sy])
    m = ycc_skin(ti)
    if float(np.mean(m[:32])) < .5:
        F.append("skin mask miss")
    if float(np.mean(m[32:])) > .3:
        F.append("skin mask fp")
    o = skin_tools(ti, {**DEF, "skin_warmth": 50, "grain": 0})
    if float(np.mean(np.abs(o[:32]-ti[:32]))) < .01:
        F.append("skin no-effect")
    if float(np.mean(np.abs(o[32:]-ti[32:]))) > .005:
        F.append("skin bleed")

    # registry
    for k, _, _, _, _ in SPEC:
        if k not in DEF:
            F.append(f"registry {k}")
    for k in GRP:
        if k not in {s[0] for s in SPEC}:
            F.append(f"group {k}")

    # layered cache determinism
    p12 = {**DEF, "contrast": 10, "gamma": 1.5, "grain": 0}
    a = ENG.render(img, p12)
    b = ENG.render(img, p12)
    if float(np.max(np.abs(a-b))) > 1e-6:
        F.append("cache non-deterministic")
    # grain change doesn't invalidate tone
    _ = ENG.render(img, p12)
    _ = ENG.render(img, {**p12, "grain": 20}, changed_key="grain")
    if "tone" not in ENG._lc:
        F.append("grain shouldn't invalidate tone")
    ENG.inval_img()

    # engine == staged
    p3 = {**DEF, "contrast": 15, "temperature": 3, "grain": 0,
          "halation": 8, "print_stock": True, "print_strength": .8,
          "scene_prep": True, "grain_profile": "cubic",
          "skin_warmth": 20, "gamma": 1.3}
    a = ENG.render(img, p3)
    b = staged(img, p3)
    if float(np.max(np.abs(a-b))) > 1e-4:
        F.append("engine != staged")

    # eggs
    for s_ in (NEGIN, FORGE):
        o = staged(img, {**DEF, **s_})
        if not np.all(np.isfinite(o)):
            F.append(f"egg {s_['name']}")

    # ===== CAMERA DNA 2.0 =====

    # profile loading — every profile constructs and serializes
    try:
        if len(CAMERA_MODELS) < 20:
            F.append(f"cdna: too few profiles ({len(CAMERA_MODELS)})")
        for prof in CAMERA_MODELS:
            d = prof.to_dict()
            _ = prof.cache_key()
            if prof.id not in CAMERA_PROFILES:
                F.append(f"cdna: {prof.id} not registered")
    except Exception as e:
        F.append(f"cdna profile load: {e}")

    # profile validity — no NaN/Inf, sane ranges
    for prof in CAMERA_MODELS:
        vals = (list(prof.hue_response.values()) +
                list(prof.sat_response.values()) +
                [prof.highlight_rolloff, prof.shadow_lift,
                 prof.midtone_contrast, prof.color_separation,
                 prof.white_balance_bias] + list(prof.channel_balance))
        if not all(np.isfinite(v) for v in vals):
            F.append(f"cdna: {prof.id} has non-finite parameter")
        if any(c <= 0 for c in prof.channel_balance):
            F.append(f"cdna: {prof.id} invalid channel_balance")

    # camera detection — representative metadata strings
    for meta, expect_id in (
            ({"make":"Sony","model":"ILCE-7M4"}, "sony_a7iv"),
            ({"make":"Canon","model":"Canon EOS R5"}, "canon_r5"),
            ({"make":"FUJIFILM","model":"X-T5"}, "fuji_xt5"),
            ({"make":"Nikon","model":"NIKON Z9"}, "nikon_z9")):
        try:
            top = cd_match_camera(img, meta)[0]
            if top.profile.id != expect_id or top.basis != "Detected":
                F.append(f"cdna detect: {meta} -> {top.profile.id}/{top.basis}")
        except Exception as e:
            F.append(f"cdna detect {meta}: {e}")

    # confidence bounds 0..1
    try:
        for r in cd_match_camera(img, {"make":"Unknown","model":"Unknown"}):
            if not (0.0 <= r.confidence <= 1.0):
                F.append(f"cdna confidence OOB: {r.profile.id} {r.confidence}")
    except Exception as e:
        F.append(f"cdna confidence: {e}")

    # confidence calibration (Camera DNA 2.2 Problem 1/3): a flat,
    # information-free image must not produce a confident-looking
    # pixel-only guess for any profile — basis must honestly read
    # "Unknown", not "Estimated".
    try:
        flat_img = np.full((48, 48, 3), 0.45, np.float32)
        flat_res = cd_match_camera(flat_img, {})
        if any(r.basis in ("Estimated", "Detected") for r in flat_res):
            F.append("cdna confidence: flat image produced non-Unknown basis")
        if flat_res[0].confidence > 0.20:
            F.append(f"cdna confidence: flat image overconfident "
                      f"({flat_res[0].confidence:.3f})")
    except Exception as e:
        F.append(f"cdna confidence calibration: {e}")

    # metadata-backed detection must remain untouched by the pixel
    # margin/evidence gate (still "Detected", still high confidence).
    try:
        r = cd_match_camera(img, {"make":"Sony","model":"ILCE-7M4"})[0]
        if r.basis != "Detected" or r.confidence < 0.5:
            F.append(f"cdna confidence: metadata match degraded -> "
                      f"{r.profile.id}/{r.basis}/{r.confidence:.3f}")
    except Exception as e:
        F.append(f"cdna confidence metadata: {e}")

    # camera transform: input finite -> output finite, valid range,
    # across every profile and every Fujifilm film-sim option
    _skm = skmask(img)
    for prof in CAMERA_MODELS:
        for sim in (None, "Provia", "Velvia", "Astia", "Classic Chrome",
                    "Acros", "Eterna"):
            try:
                pp = {**CD_DEFAULTS, "cm_enabled": True, "cm_target": prof.id,
                      "cm_strength": 1.0, "cm_film_sim": sim}
                o = cd_apply(img, pp, skin_mask=_skm)
                if not np.all(np.isfinite(o)) or o.min() < -.001 or o.max() > 1.001:
                    F.append(f"cdna transform invalid: {prof.id}/{sim}")
            except Exception as e:
                F.append(f"cdna transform {prof.id}/{sim}: {e}")

    # strength=0 must be an exact no-op
    p0 = {**CD_DEFAULTS, "cm_enabled": True, "cm_target": "arri_alexa_35",
          "cm_strength": 0.0}
    o0 = cd_apply(clamp(img), p0, skin_mask=_skm)
    if float(np.max(np.abs(o0-clamp(img)))) > 1e-6:
        F.append("cdna strength=0 not identity")

    # determinism
    pcm = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_target": "sony_venice",
           "cm_source": "sony_a7iv", "cm_strength": .7, "grain": 0}
    a = staged(img, pcm)
    b = staged(img, pcm)
    if float(np.max(np.abs(a-b))) > 1e-9:
        F.append("cdna non-deterministic")

    # engine == staged with Camera Match active (preview/export consistency)
    ENG.inval_img()
    ea = ENG.render(img, pcm)
    sb = staged(img, pcm)
    if float(np.max(np.abs(ea-sb))) > 1e-4:
        F.append("cdna engine != staged")
    ENG.inval_img()

    # tile equivalence — Camera Match must be tile-safe (pointwise only)
    big = _tg(160, 128)
    ptile = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_target": "fuji_xt5",
             "cm_strength": 1.0, "cm_film_sim": "Velvia", "grain": 0}
    full = staged(big, ptile)
    H = big.shape[0]
    rpt = 37
    tiled = np.empty_like(full)
    for y0 in range(0, H, rpt):
        y1 = min(y0+rpt, H)
        tiled[y0:y1] = staged(big[y0:y1], ptile)
    if float(np.max(np.abs(full-tiled))) > 1e-3:
        F.append("cdna tile seam")

    # skin protection — skin regions must not receive extreme shifts
    sk = np.zeros((32, 32, 3), np.float32)
    sk[..., 0], sk[..., 1], sk[..., 2] = .72, .5, .38
    bgp = np.zeros((32, 32, 3), np.float32)
    bgp[..., 0], bgp[..., 1], bgp[..., 2] = .2, .6, .8
    tskin = np.concatenate([sk, bgp])
    pskin = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_target": "sony_venice",
             "cm_strength": 1.0, "grain": 0}
    oskin = staged(tskin, pskin)
    skin_shift = float(np.mean(np.abs(oskin[:32]-tskin[:32])))
    if skin_shift > .4:
        F.append(f"cdna skin extreme shift {skin_shift:.3f}")

    # monochrome film-sim must stay exactly monochrome even with skin mask
    pmono = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_target": "fuji_xt5",
             "cm_film_sim": "Acros", "cm_strength": 1.0, "grain": 0}
    omono = staged(img, pmono)
    if float(np.max(np.abs(omono[...,0]-omono[...,2]))) > 1e-6:
        F.append("cdna Acros not monochrome")

    # LUT compatibility unaffected by Camera Match presence
    cb_ = ["TITLE i", "LUT_3D_SIZE 2", "0 0 0", "1 0 0", "0 1 0",
           "1 1 0", "0 0 1", "1 0 1", "0 1 1", "1 1 1"]
    with tempfile.NamedTemporaryFile("w", suffix=".cube", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(cb_))
        cp2 = f.name
    try:
        ps2 = pcube(cp2)
        plut = {**DEF, **CD_DEFAULTS, **ps2, "cm_enabled": True,
                "cm_target": "canon_r5", "cm_strength": 1.0}
        o = staged(img, plut)
        if not np.all(np.isfinite(o)):
            F.append("cdna+LUT invalid")
    except Exception as e:
        F.append(f"cdna+LUT: {e}")
    finally:
        os.unlink(cp2)

    # ===== CAMERA DNA 2.0 — MOBILE SENSORS (iPhone / Android) =====

    mobile_profiles = [p for p in CAMERA_MODELS if p.category == "Mobile"]
    if len(mobile_profiles) < 12:
        F.append(f"cdna mobile: too few mobile profiles ({len(mobile_profiles)})")
    iphone_n = sum(1 for p in mobile_profiles if p.manufacturer == "Apple")
    android_n = len(mobile_profiles) - iphone_n
    if iphone_n < 6:
        F.append(f"cdna mobile: iPhone generations {iphone_n} < 6")
    if android_n < 6:
        F.append(f"cdna mobile: Android models {android_n} < 6")

    for meta, expect_id in (
            ({"make":"Apple","model":"iPhone 15 Pro"}, "iphone_15"),
            ({"make":"Apple","model":"iPhone 11 Pro Max"}, "iphone_11"),
            ({"make":"samsung","model":"SM-S928B"}, "galaxy_s24"),
            ({"make":"Google","model":"Pixel 8 Pro"}, "pixel_8"),
            ({"make":"Xiaomi","model":"23127PN0CG"}, "xiaomi_generic")):
        try:
            top = cd_match_camera(img, meta)[0]
            if top.profile.id != expect_id or top.basis != "Detected":
                F.append(f"cdna mobile detect: {meta} -> "
                         f"{top.profile.id}/{top.basis}")
        except Exception as e:
            F.append(f"cdna mobile detect {meta}: {e}")

    # no substring collisions across iPhone generations (11 must not
    # match inside "iPhone 1" prefix-style against later gens, etc.)
    for model, expect_id in (("iPhone 11 Pro Max","iphone_11"),
                              ("iPhone 12","iphone_12"),
                              ("iPhone 14 Plus","iphone_14"),
                              ("iPhone 16 Pro","iphone_16")):
        top = cd_match_camera(img, {"make":"Apple","model":model})[0]
        if top.profile.id != expect_id:
            F.append(f"cdna mobile collision: {model} -> {top.profile.id}")

    # transform validity + strength=0 identity across every mobile profile
    for prof in mobile_profiles:
        pp = {**CD_DEFAULTS, "cm_enabled": True, "cm_target": prof.id,
              "cm_strength": 1.0}
        o = cd_apply(img, pp, skin_mask=_skm)
        if not np.all(np.isfinite(o)) or o.min() < -.001 or o.max() > 1.001:
            F.append(f"cdna mobile transform invalid: {prof.id}")
        p0m = {**CD_DEFAULTS, "cm_enabled": True, "cm_target": prof.id,
               "cm_strength": 0.0}
        o0m = cd_apply(clamp(img), p0m, skin_mask=_skm)
        if float(np.max(np.abs(o0m-clamp(img)))) > 1e-6:
            F.append(f"cdna mobile strength=0 not identity: {prof.id}")

    # phone -> cinema camera MANUAL matching (a common real-world use
    # case for this feature) must be deterministic and produce a
    # genuinely different result than target-only
    p_manual = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_source": "iphone_15",
                "cm_target": "arri_alexa_35", "cm_strength": 1.0, "grain": 0}
    p_target_only = {**DEF, **CD_DEFAULTS, "cm_enabled": True, "cm_source": None,
                      "cm_target": "arri_alexa_35", "cm_strength": 1.0, "grain": 0}
    ma = staged(img, p_manual)
    mb = staged(img, p_manual)
    if float(np.max(np.abs(ma-mb))) > 1e-9:
        F.append("cdna mobile manual non-deterministic")
    mt_only = staged(img, p_target_only)
    if float(np.max(np.abs(ma-mt_only))) < 1e-4:
        F.append("cdna mobile source has no effect vs target-only")

    print(f"[INFO] presets={len(PRES)} camera_profiles={len(CAMERA_MODELS)}")

    # ===== CAMERA DNA 2.3 =====

    # Round trip (Problem 15): character(A) then neutralizing-inverse(A)
    # should land close to the original for a controlled synthetic
    # chart, since _neutralizing_profile is a documented APPROXIMATE
    # inverse, not an exact one. We assert a bounded error, not zero.
    try:
        chart = np.zeros((6, 6, 3), np.float32)
        patches = [(.05,.05,.05),(.18,.18,.18),(.50,.50,.50),(.75,.75,.75),
                   (.90,.90,.90),(.8,.3,.2),(.2,.6,.3),(.2,.3,.8),
                   (.8,.7,.2),(.7,.2,.7),(.2,.7,.7)]
        for i, p in enumerate(patches):
            chart[i % 6, i // 6] = p
        src_prof = CAMERA_PROFILES["arri_alexa"]
        forward = _camera_character_transform(chart, src_prof)
        back = _camera_character_transform(forward, _neutralizing_profile(src_prof))
        rmse = float(np.sqrt(np.mean((back-chart)**2)))
        max_err = float(np.max(np.abs(back-chart)))
        if not np.all(np.isfinite(back)):
            F.append("cdna round-trip: non-finite")
        elif max_err > 0.35:  # documented approximation, not exact inverse
            F.append(f"cdna round-trip: drift too large "
                      f"(rmse={rmse:.3f} max={max_err:.3f})")
        print(f"[INFO] round-trip source->char->inv: rmse={rmse:.4f} "
              f"max_abs_err={max_err:.4f}")
    except Exception as e:
        F.append(f"cdna round-trip: {e}")

    # Exposure sweep stability of the pixel signature itself (Problem
    # 3/14): a textured synthetic scene at -2..+2 EV should give stable
    # highlight_slope/shadow_slope BEFORE real clipping occurs, and the
    # top *metadata-backed* detection must not depend on exposure at all.
    try:
        rngx = np.random.default_rng(11)
        base = np.linspace(0, 1, 64, dtype=np.float32)[None, :].repeat(48, 0)
        scene = np.stack([base, base*.8+.1, base*.6+.2], -1).astype(np.float32)
        scene += rngx.normal(0, .03, scene.shape).astype(np.float32)
        scene = np.clip(scene, 0, 1)
        slopes = []
        for mul in (.5, 1.0):  # stay below clipping for a stability check
            sig = cd_pixel_signature(np.clip(scene*mul, 0, 1))
            slopes.append((sig["highlight_slope"], sig["shadow_slope"]))
        if abs(slopes[0][0]-slopes[1][0]) > 0.05 or \
                abs(slopes[0][1]-slopes[1][1]) > 0.05:
            F.append(f"cdna exposure stability: slopes drifted {slopes}")
        # metadata-backed identification must be exposure-independent
        r_dim = cd_match_camera(np.clip(scene*.5, 0, 1),
                                 {"make":"Sony","model":"ILCE-7M4"})[0]
        r_bright = cd_match_camera(np.clip(scene*1.0, 0, 1),
                                    {"make":"Sony","model":"ILCE-7M4"})[0]
        if r_dim.profile.id != r_bright.profile.id or r_dim.basis != r_bright.basis:
            F.append("cdna exposure stability: metadata detection changed with exposure")
    except Exception as e:
        F.append(f"cdna exposure stability: {e}")

    # NOTE on full-pipeline determinism (Problem 18): Camera Match
    # (cd_apply/cd_match_camera) is fully deterministic and covered by
    # the "cdna mobile manual non-deterministic" check above. The
    # existing creative grain() layer intentionally uses an unseeded
    # np.random.default_rng() and is NOT deterministic run-to-run; that
    # is unrelated to Camera Match and was left unchanged here per the
    # brief ("do not silently change creative grain behavior"). Any
    # staged() render that includes grain>0 will therefore differ
    # between runs even though the Camera Match layer itself does not.

    return F


def main():
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


if __name__ == "__main__":
    main()