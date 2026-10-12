# SPDX-License-Identifier: MIT
"""Headless image pipeline: colour science, camera profiles, renderer. No tkinter."""

import json
from functools import lru_cache
import math
import numpy as np
import os
import re
import threading
from PIL import ExifTags, Image, ImageDraw, ImageFilter, ImageOps
from .config import RAW_EXT
from .deps import HAVE_CV2, HAVE_OCIO, OCIO, cv2, rawpy


class RenderCancelled(Exception):
    """Raised when a stale render generation becomes obsolete."""


class RenderGeneration:
    """Monotonic render generation shared by UI and tile execution."""
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def current(self):
        with self._lock:
            return self._value

    def next(self):
        with self._lock:
            self._value += 1
            return self._value

    def is_current(self, generation):
        with self._lock:
            return int(generation) == self._value

    def checkpoint(self, generation):
        if not self.is_current(generation):
            raise RenderCancelled(f"stale render generation: {generation}")


RENDER_GENERATIONS = RenderGeneration()


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
        im = _raw_postprocess(path, preview=True)
        return im, {"path":path,"raw":True,"raw_proxy":True}
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB"), _meta(img, path)


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
    # A short/NaN DOMAIN used to import fine and then raise inside every
    # render (swallowed by the render thread -> silently frozen preview).
    if dmin.shape != (3,) or dmax.shape != (3,) or \
            not (np.isfinite(dmin).all() and np.isfinite(dmax).all()):
        raise RuntimeError("Invalid DOMAIN_MIN/DOMAIN_MAX in CUBE.")
    # .cube spec: R varies fastest, then G, then B -> flat reshape is [b,g,r,3]
    table_raw = np.asarray(rows[:sz*sz*sz], np.float32).reshape(sz, sz, sz, 3)
    if not np.isfinite(table_raw).all():
        raise RuntimeError("CUBE contains non-finite values.")
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


def auto_tone_params(rgb):
    """Closed-loop starting point for exposure, contrast, highlights, shadows,
    whites and blacks. Renders a small copy through the real pipeline so the
    result matches what the sliders will do; values stay within slider ranges."""
    small = analysis_size(ensure_rgb(rgb), 300)
    med = lambda im: float(np.median(luminance(im)))
    ev = 0.0
    for _ in range(4):
        m = med(staged(small, {"exposure": ev}))
        ev = float(np.clip(ev+np.clip(math.log2(.46/max(m, .02))*.9, -1.5, 1.5), -3.0, 3.0))
        if abs(m-.46) < .015:
            break
    y = luminance(staged(small, {"exposure": ev})).ravel()
    p1, p5, p95, p99 = (float(v) for v in np.percentile(y, [1, 5, 95, 99]))
    highlights = -float(np.clip((p99-.95)*600, 0, 45))
    whites = float(np.clip((.93-p99)*250, 0, 35))
    shadows = float(np.clip((.10-p5)*420, 0, 50))
    blacks = -float(np.clip((p1-.03)*320, 0, 40))
    contrast = float(np.clip((.60-(p95-p5))*60, 0, 25))
    return {"exposure": round(ev, 2), "contrast": round(contrast), "highlights": round(highlights),
            "shadows": round(shadows), "whites": round(whites), "blacks": round(blacks)}


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
    elif t == "range":
        wgt = np.ones((h, w), np.float32)
    elif t == "auto":
        wgt = _auto_mask_weight((h, w), m, full_h=H, tile_y0=tile_y0)
    else:
        wgt = np.zeros((h, w), np.float32)
    if m.get("invert"):
        wgt = 1-wgt
    return wgt[..., None].astype(np.float32)


def _auto_mask_weight(shape, m, full_h=None, tile_y0=0):
    """Resize an 'auto' mask's stored weight_map (detected once, e.g.
    by detect_sky_mask()) to the current render — same full-image/
    tile-crop pattern as _brush_weight, so it stays correct under
    row-tiled export."""
    h, w = shape[:2]
    H = full_h or h
    wm = m.get("weight_map")
    if not wm:
        return np.zeros((h, w), np.float32)
    arr = np.clip(np.asarray(wm, np.float32), 0, 1)
    img = Image.fromarray((arr*255).astype(np.uint8))
    img = img.resize((w, H), BILINEAR)
    full = np.asarray(img, np.float32)/255.0
    return full[tile_y0:tile_y0+h] if H != h else full


_ACES_INPUT_MTX = np.array([
    [0.59719, 0.35458, 0.04823],
    [0.07600, 0.90834, 0.01566],
    [0.02840, 0.13383, 0.83777]], np.float32)


_ACES_OUTPUT_MTX = np.array([
    [ 1.60475, -0.53108, -0.07367],
    [-0.10208,  1.10813, -0.00605],
    [-0.00327, -0.07276,  1.07602]], np.float32)


_OCIO_VARIANTS = {
    "1.3": ("ocio://cg-config-v1.0.0_aces-v1.3_ocio-v2.1", "ACES 1.0 - SDR Video"),
    "2.0": ("ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5",
            "ACES 2.0 - SDR 100 nits (Rec.709)"),
}


def aces_fallback_tonemap(x):
    """Narkowicz's fitted approximation of the ACES RRT+ODT filmic
    curve — a pure-numpy stand-in used whenever real OCIO isn't
    installed. Input/output both linear-referred 0..1ish (values above
    1.0 are expected/handled — that's the point of a filmic tonemap)."""
    x = np.maximum(arr32(x), 0)
    v = np.einsum('...i,ji->...j', x, _ACES_INPUT_MTX)
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    v = (v*(a*v+b))/(v*(c*v+d)+e)
    v = np.einsum('...i,ji->...j', v, _ACES_OUTPUT_MTX)
    return np.clip(v, 0, 1).astype(np.float32)


def _ocio_variant():
    v = os.environ.get("LUMENFORGE_ACES", "1.3").strip()
    return v if v in _OCIO_VARIANTS else "1.3"


class ColorManager:
    """Single entry point for working-space -> display transforms.
    Uses a real ACES OCIO config when PyOpenColorIO is importable;
    otherwise falls back to aces_fallback_tonemap so callers never need
    to branch on HAVE_OCIO themselves."""
    _config = None
    _proc_cache = {}
    @classmethod
    def _get_config(cls):
        if not HAVE_OCIO:
            return None
        if cls._config is None:
            try:
                cls._config = OCIO.Config.CreateFromBuiltinConfig(
                    _OCIO_VARIANTS[_ocio_variant()][0])
            except Exception:
                try:
                    cls._config = OCIO.Config.CreateFromEnv()
                except Exception:
                    cls._config = False
        return cls._config or None
    @classmethod
    def to_display(cls, rgb, display="sRGB - Display", view=None):
        """Linear working-space RGB -> display-referred RGB, 0..1."""
        cfg = cls._get_config()
        x = np.ascontiguousarray(arr32(rgb))
        if view is None:
            view = _OCIO_VARIANTS[_ocio_variant()][1]
        if cfg is None:
            return aces_fallback_tonemap(x)
        try:
            key = (display, view)
            proc = cls._proc_cache.get(key)
            if proc is None:
                proc = cfg.getProcessor(
                    OCIO.ROLE_SCENE_LINEAR, display, view,
                    OCIO.TRANSFORM_DIR_FORWARD).getDefaultCPUProcessor()
                cls._proc_cache[key] = proc
            h, w = x.shape[:2]
            flat = x.reshape(-1, 3).copy()
            proc.applyRGB(flat)
            return np.clip(flat.reshape(h, w, 3), 0, 1).astype(np.float32)
        except Exception:
            return aces_fallback_tonemap(x)
    @classmethod
    def available_displays(cls):
        cfg = cls._get_config()
        if cfg is None:
            return ["sRGB - Display (fallback ACES fit)"]
        try:
            return list(cfg.getDisplays())
        except Exception:
            return ["sRGB - Display (fallback ACES fit)"]


def _lum_range_weight(x, rng, feather=.12):
    """Per-pixel luminance band weight (0-1), soft-edged: Lightroom-style range mask."""
    lo, hi = float(rng[0]), float(rng[1])
    fe = max(float(feather), .01)
    y = luminance(x)
    wl = smoothstep(lo-fe, lo+fe, y)*(1.0-smoothstep(hi-fe, hi+fe, y))
    if lo <= 0.0:
        wl = 1.0-smoothstep(hi-fe, hi+fe, y)
    if hi >= 1.0:
        wl = smoothstep(lo-fe, lo+fe, y)
    return wl[..., None].astype(np.float32)


def _hue_range_weight(x, hr):
    """Colour-range weight: hue within [centre, width] degrees (circular, soft
    edged) and enough saturation to have a meaningful hue."""
    c, wd = float(hr[0]), max(float(hr[1]), 1.0)
    mx, mn = x.max(axis=2), x.min(axis=2)
    d = np.maximum(mx-mn, 1e-6)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    hue = np.where(mx == r, ((g-b)/d) % 6.0, np.where(mx == g, (b-r)/d+2.0, (r-g)/d+4.0))*60.0
    dist = np.abs((hue-c+180.0) % 360.0-180.0)
    wh = 1.0-smoothstep(wd*.5, wd*.5+max(wd*.4, 8.0), dist)
    ws = smoothstep(.05, .18, d/np.maximum(mx, 1e-6))
    return (wh*ws)[..., None].astype(np.float32)


def hue_at(rgb, fx, fy, rad=3):
    """Mean-colour hue in degrees at fractional image position (fx, fy), or None if too grey."""
    x = ensure_rgb(rgb)
    h, w = x.shape[:2]
    cx, cy = int(np.clip(fx, 0, 1)*(w-1)), int(np.clip(fy, 0, 1)*(h-1))
    p = x[max(0, cy-rad):cy+rad+1, max(0, cx-rad):cx+rad+1].reshape(-1, 3).mean(axis=0)
    mx, mn = float(p.max()), float(p.min())
    if mx <= 1e-6 or (mx-mn)/mx < .08:
        return None
    r, g, b = (float(v) for v in p)
    d = mx-mn
    hue = ((g-b)/d) % 6.0 if mx == r else ((b-r)/d+2.0 if mx == g else (r-g)/d+4.0)
    return hue*60.0


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
        if m.get("hue_range"):
            w = w*_hue_range_weight(x, m["hue_range"])
        if m.get("lum_range"):
            w = w*_lum_range_weight(x, m["lum_range"], m.get("lum_feather", .12))
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


def _blur_y(y, r):
    y = np.ascontiguousarray(y, np.float32)
    if HAVE_CV2:
        return cv2.GaussianBlur(y, (0, 0), sigmaX=float(r))
    return blur(np.repeat(y[..., None], 3, 2), r)[..., 0]


def _edge_weight(y, lo=.012, hi=.09):
    """0 in flat areas, 1 on real edges (gradient magnitude of lightly blurred luma)."""
    ys = _blur_y(y, .8)
    gy, gx = np.gradient(ys)
    return smoothstep(lo, hi, np.hypot(gx, gy)*4.0)


def denoise_op(rgb, lum, col):
    """Edge-aware luminance and chroma noise reduction (0-100 each)."""
    rgb = arr32(rgb)
    lum = float(np.clip(lum, 0, 100))/100.0
    col = float(np.clip(col, 0, 100))/100.0
    if lum < .005 and col < .005:
        return rgb
    y = luminance(rgb)
    c = rgb-y[..., None]
    edge = _edge_weight(y)
    if col > .005:
        enc = np.clip(c*.5+.5, 0, 1).astype(np.float32)
        cb = blur(enc, .8+col*5.0)*2.0-1.0
        wc = (col*(1.0-.6*edge))[..., None]
        c = c*(1.0-wc)+cb*wc
    if lum > .005:
        yb = _blur_y(y, .7+lum*2.2)
        wl = lum*.9*(1.0-edge)
        y = y*(1.0-wl)+yb*wl
    return np.maximum(y[..., None]+c, 0)


def sharpen_op(rgb, amount, radius=1.0, masking=0.0):
    """Luminance unsharp mask with soft-limited halos and edge masking."""
    rgb = arr32(rgb)
    k = float(np.clip(amount, 0, 150))/100.0
    if k < .005:
        return rgb
    y = luminance(rgb)
    d = y-_blur_y(y, float(np.clip(radius, .3, 4.0)))
    d = np.tanh(d*4.0)/4.0
    m = float(np.clip(masking, 0, 100))/100.0
    if m > .005:
        d = d*(1.0-m*(1.0-_edge_weight(y)))
    return np.maximum(rgb+(d*k*1.6)[..., None], 0)


def defringe_op(rgb, amount):
    """Desaturate purple/green fringes that sit next to high-contrast edges."""
    rgb = arr32(rgb)
    k = float(np.clip(amount, 0, 100))/100.0
    if k < .005:
        return rgb
    y = luminance(rgb)
    c = rgb-y[..., None]
    mag = smoothstep(.02, .10, np.maximum(np.minimum(c[..., 0], c[..., 2])-c[..., 1],
                                          c[..., 1]-np.maximum(c[..., 0], c[..., 2])))
    near = np.clip(_blur_y(_edge_weight(y), 2.5)*3.0, 0, 1)
    w = (mag*near*k)[..., None]
    return np.maximum(y[..., None]+c*(1.0-w), 0)


def distort_op(rgb, amount):
    """Radial lens distortion correction (-100..100). Positive pulls the
    edges in (fixes barrel), negative pushes them out (fixes pincushion)."""
    x = arr32(rgb)
    k = float(np.clip(amount, -100, 100))/100.0*.35
    if abs(k) < 1e-4:
        return x
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w-1)/2.0, (h-1)/2.0
    half = math.hypot(cx, cy)
    dx, dy = (xx-cx)/half, (yy-cy)/half
    f = 1.0+k*(dx*dx+dy*dy)
    sx = np.clip(cx+dx*f*half, 0, w-1)
    sy = np.clip(cy+dy*f*half, 0, h-1)
    if HAVE_CV2:
        return cv2.remap(np.ascontiguousarray(x), sx.astype(np.float32), sy.astype(np.float32),
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    x0, y0 = np.floor(sx).astype(np.int32), np.floor(sy).astype(np.int32)
    x1, y1 = np.minimum(x0+1, w-1), np.minimum(y0+1, h-1)
    fx, fy = (sx-x0)[..., None], (sy-y0)[..., None]
    top = x[y0, x0]*(1-fx)+x[y0, x1]*fx
    bot = x[y1, x0]*(1-fx)+x[y1, x1]*fx
    return (top*(1-fy)+bot*fy).astype(np.float32)


def clipping_overlay(rgb, hi=.995, lo=.005):
    """Copy of an image with blown highlights tinted red and crushed shadows blue."""
    x = arr32(rgb).copy()
    hot = (x >= hi).any(axis=2)
    cold = (x <= lo).all(axis=2)
    x[hot] = [1.0, .05, .05]
    x[cold & ~hot] = [.05, .2, 1.0]
    return x


def heal_op(rgb, spots):
    """Spot healing: clone a source disc over each blemish, matching the
    local mean colour and feathering the edge. Spots are dicts with
    x, y (target), sx, sy (source) as 0-1 fractions of width/height and
    r as a fraction of the longest side."""
    x = arr32(rgb).copy()
    h, w = x.shape[:2]
    for s in spots or ():
        try:
            r = max(2, int(float(s["r"])*max(w, h)))
            cx, cy = int(float(s["x"])*w), int(float(s["y"])*h)
            sx, sy = int(float(s["sx"])*w), int(float(s["sy"])*h)
        except (KeyError, TypeError, ValueError):
            continue
        r = min(r, w//2, h//2)
        if r < 2:
            continue
        x0, x1 = max(0, cx-r), min(w, cx+r+1)
        y0, y1 = max(0, cy-r), min(h, cy+r+1)
        sx0, sy0 = x0-cx+sx, y0-cy+sy
        if x1 <= x0 or y1 <= y0 or sx0 < 0 or sy0 < 0 or sx0+(x1-x0) > w or sy0+(y1-y0) > h:
            continue
        dst = x[y0:y1, x0:x1]
        src = x[sy0:sy0+(y1-y0), sx0:sx0+(x1-x0)]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xx-cx, yy-cy)/float(r)
        a = (1.0-smoothstep(.55, 1.0, d))[..., None]
        ring = ((d > .8) & (d <= 1.0))
        if ring.any():
            src_ring = np.zeros_like(src)
            src_ring = src[ring].mean(axis=0)
            dst_ring = dst[ring].mean(axis=0)
            src = src-src_ring+dst_ring
        x[y0:y1, x0:x1] = dst*(1.0-a)+np.maximum(src, 0)*a
    return x


def heal_pick_source(rgb, x, y, r):
    """Choose a clean nearby source disc for a blemish at (x, y): the candidate
    with the smoothest, best colour-matched surroundings. Fractions in, fractions out."""
    img = analysis_size(ensure_rgb(rgb), 600)
    h, w = img.shape[:2]
    lum = luminance(img)
    rr = max(2, int(r*max(w, h)))
    cx, cy = x*w, y*h
    ref = lum[int(max(0, cy-rr)):int(min(h, cy+rr+1)), int(max(0, cx-rr)):int(min(w, cx+rr+1))]
    ref_mean = float(np.median(ref)) if ref.size else .5
    best, bs = (min(.98, x+r*3), y), 1e9
    for k in range(8):
        a = k*math.pi/4
        for dist in (2.6, 4.0):
            sx, sy = cx+math.cos(a)*rr*dist, cy+math.sin(a)*rr*dist
            if sx-rr < 0 or sy-rr < 0 or sx+rr >= w or sy+rr >= h:
                continue
            c = lum[int(sy-rr):int(sy+rr+1), int(sx-rr):int(sx+rr+1)]
            s = float(np.var(c))*40.0+abs(float(np.median(c))-ref_mean)
            if s < bs:
                best, bs = (sx/w, sy/h), s
    return best


DETAIL_STAGES = (
    # (gate on params, operation) — one table drives both render() and staged()
    (lambda p: p.get("defringe", 0) > .5,
     lambda x, p: defringe_op(x, p["defringe"])),
    (lambda p: p.get("nr_luma", 0) > .5 or p.get("nr_color", 0) > .5,
     lambda x, p: denoise_op(x, p.get("nr_luma", 0), p.get("nr_color", 0))),
    (lambda p: p.get("sharpen", 0) > .5,
     lambda x, p: sharpen_op(x, p["sharpen"], p.get("sharpen_radius", 1.0),
                             p.get("sharpen_masking", 0))),
)


def apply_detail(x, p):
    """Apply the spatial detail stages (defringe, noise reduction, sharpening) in order."""
    for gate, op in DETAIL_STAGES:
        if gate(p):
            x = op(x, p)
    return x


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

from .presets_modern import MODERN_PRESETS
PRES.extend(MODERN_PRESETS)






@lru_cache(maxsize=1)
def _cas():
    """Face cascade, loaded once on first use (None when OpenCV or the data is missing)."""
    if not HAVE_CV2:
        return None
    try:
        c = cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
        return None if c.empty() else c
    except Exception:
        return None


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


FUJI_FILM_SIM = {
    "Provia":        dict(sat_mult=1.00, contrast=.00, hi_roll=.20, sh_lift=.00, desc="Standard balanced -inspired"),
    "Velvia":        dict(sat_mult=1.18, contrast=.10, hi_roll=.28, sh_lift=-.02, desc="Vivid, saturated -inspired"),
    "Astia":         dict(sat_mult=1.04, contrast=-.03, hi_roll=.16, sh_lift=.02, desc="Soft, portrait-leaning -inspired"),
    "Classic Chrome":dict(sat_mult=.90, contrast=.04, hi_roll=.30, sh_lift=.03, desc="Muted, documentary -inspired"),
    "Acros":         dict(sat_mult=0.0, contrast=.08, hi_roll=.22, sh_lift=.00, desc="Fine-grain monochrome -inspired"),
    "Eterna":        dict(sat_mult=.82, contrast=-.10, hi_roll=.36, sh_lift=.06, desc="Flat cinematic -inspired"),
}


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


SK = ("skin_warmth","skin_brightness","skin_saturation",
      "skin_tan","skin_smooth","skin_clarity")


HSL_KEYS = tuple(f"hsl_{b}_{c}" for b in HSL_BANDS
                 for c in ("hue", "sat", "lum"))


CG_KEYS = tuple(f"cg_{r}_{c}" for r in CG_RANGES
               for c in ("hue", "sat", "lum")) + \
    ("cg_global_hue", "cg_global_sat", "cg_global_lum", "cg_blending")


LAYER_ORDER = ("camera", "wb", "tone", "color")


LAYER_KEYS = {
    "camera": CD_LAYER_KEYS + ("distortion", "spots"),
    "wb": ("temperature", "tint", "scene_prep", "lut3d_path",
           "lut3d_strength") + SK,
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
            if abs(p.get("distortion", 0)) > .5:
                x = distort_op(x, p["distortion"])
            if p.get("spots"):
                x = heal_op(x, p["spots"])
            if p.get("cm_enabled"):
                x = cd_apply(x, p, skin_mask=self._sk(x))
            self._lc["camera"] = (h, x)

        # LAYER: wb
        # Each layer's cache key chains the upstream layer's key (h), so an
        # upstream edit can never be masked by a stale downstream entry even
        # when changed_key is None or stale (e.g. _scd(None) from the Camera
        # Match / Scene Prep controls). changed_key is only an eager-evict hint.
        h = (h, self._hash(p, LAYER_KEYS["wb"]))
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
        h = (h, self._hash(p, LAYER_KEYS["tone"]))
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
        h = (h, self._hash(p, LAYER_KEYS["color"]))
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
        x = apply_detail(x, p)
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

        if p.get("aces_display"):
            x = ColorManager.to_display(x)

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
    if abs(p.get("distortion", 0)) > .5:
        x = distort_op(x, p["distortion"])
    if p.get("spots"):
        x = heal_op(x, p["spots"])
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
    x = apply_detail(x, p)
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
    if p.get("aces_display"):
        x = ColorManager.to_display(x)
    return clamp(x)


_RAW_XTRANS_OMP_LOCK = threading.Lock()


def _raw_postprocess(path, *, preview=False):
    if rawpy is None:
        raise RuntimeError("RAW needs rawpy: pip install rawpy")

    kwargs = {
        "use_camera_wb": True,
        "output_color": rawpy.ColorSpace.sRGB,
        "output_bps": 8,
    }
    if preview:
        kwargs["half_size"] = True

    with rawpy.imread(path) as r:
        # LibRaw currently has a reproducibility race for Fujifilm X-Trans
        # RAF postprocessing when its OpenMP path is enabled (LibRaw #845).
        # Keep the workaround scoped to the affected RAW family so unrelated
        # RAW decodes and the rest of the application's thread pool retain
        # their normal parallelism.
        pattern = getattr(r, "raw_pattern", None)
        xtrans = pattern is not None and tuple(pattern.shape) == (6, 6)
        if xtrans and bool(getattr(rawpy, "flags", {}).get("OPENMP", False)):
            try:
                import ctypes
                import sys

                omp_candidates = [
                    os.path.join(os.path.dirname(rawpy.__file__), "vcomp140.dll"),
                    os.path.join(os.path.dirname(sys.executable), "vcomp140.dll"),
                ]
                omp_path = next(
                    (candidate for candidate in omp_candidates if os.path.isfile(candidate)),
                    None,
                )
                if omp_path is None:
                    raise OSError("vcomp140.dll not found beside rawpy or the executable")
                omp = ctypes.CDLL(omp_path)
                get_max_threads = omp.omp_get_max_threads
                get_max_threads.restype = ctypes.c_int
                set_num_threads = omp.omp_set_num_threads
                set_num_threads.argtypes = [ctypes.c_int]
                set_num_threads.restype = None
                get_dynamic = omp.omp_get_dynamic
                get_dynamic.restype = ctypes.c_int
                set_dynamic = omp.omp_set_dynamic
                set_dynamic.argtypes = [ctypes.c_int]
                set_dynamic.restype = None
            except (AttributeError, OSError) as exc:
                raise RuntimeError(
                    "Deterministic Fujifilm X-Trans RAW processing requires "
                    "the rawpy OpenMP runtime"
                ) from exc

            with _RAW_XTRANS_OMP_LOCK:
                previous_threads = get_max_threads()
                previous_dynamic = get_dynamic()
                set_dynamic(0)
                set_num_threads(1)
                try:
                    rgb = r.postprocess(**kwargs)
                finally:
                    set_num_threads(previous_threads)
                    set_dynamic(previous_dynamic)
        else:
            rgb = r.postprocess(**kwargs)

    return Image.fromarray(rgb, "RGB")


def detect_sky_mask(rgb, feather=8):
    """Classical (non-ML) sky detector: blue/cyan OR bright-flat
    (overcast) hue, weighted toward the upper frame, downweighted
    where local detail (high-frequency texture) is high — buildings,
    trees and horizons are textured, sky rarely is. Not a substitute
    for a trained segmentation model (the real state-of-the-art per
    LumenForge's own capability audit), but a legitimate, dependency-
    free way to auto-seed a sky mask instead of drawing one by hand.
    Returns a single-channel [0,1] weight map, same size as rgb."""
    x = np.maximum(arr32(rgb), 0)
    h, w = x.shape[:2]
    hue, sat, val = _rgb_to_hsv_np(x)
    hue_deg = hue*360.0
    blue_dist = np.abs(((hue_deg-215.0+180.0) % 360.0)-180.0)
    blue_score = np.clip(1-blue_dist/70.0, 0, 1)*np.clip((sat-0.05)/0.5, 0, 1)
    overcast_score = np.clip((0.22-sat)/0.22, 0, 1)*np.clip((val-0.55)/0.35, 0, 1)
    color_score = np.maximum(blue_score, overcast_score)
    yy = (np.arange(h, dtype=np.float32)[:, None]+.5)/h
    position_score = np.clip(1.25-1.5*yy, 0, 1)*np.ones((1, w), np.float32)
    lum = luminance(x)
    lum_img = Image.fromarray((np.clip(lum, 0, 1)*255).astype(np.uint8))
    small = np.asarray(lum_img.resize((max(1, w//8), max(1, h//8)), BILINEAR)
                       .resize((w, h), BILINEAR), np.float32)/255.0
    detail = np.abs(lum-small)
    smooth_score = np.clip(1-detail*6.0, 0, 1)
    weight = color_score*np.clip(0.35+0.65*position_score, 0, 1)*(0.4+0.6*smooth_score)
    w_img = Image.fromarray((np.clip(weight, 0, 1)*255).astype(np.uint8))
    weight = np.asarray(w_img.filter(
        ImageFilter.GaussianBlur(radius=feather)), np.float32)/255.0
    return np.clip(weight, 0, 1).astype(np.float32)


def staged_tile_safe(p):
    if not p:
        return True
    if p.get("scene_prep") or p.get("grain", 0) > .5:
        return False
    if p.get("spots") or abs(p.get("distortion", 0)) > .5:
        return False
    if abs(p.get("vignette", 0)) > .5:
        return False
    if any(gate(p) for gate, _ in DETAIL_STAGES):
        return False
    return True
