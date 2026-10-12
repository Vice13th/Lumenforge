"""Preset quality audit: python tests/preset_qa.py  (also imported by test_presets)."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from lumenforge import engine
from lumenforge.params import DEF, SPEC

META = {"name", "family", "process", "description", "monochrome", "mono_weights"}
_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lumenforge", "engine.py"), encoding="utf8").read()
RANGES = {k: (lo, hi) for k, _, lo, hi, _ in SPEC}


def scenes():
    h, w = 72, 96
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    skin = np.dstack([.78-.2*yy/h, .55-.2*yy/h, .45-.15*yy/h]) * (.85+.15*xx/w)[..., None]
    sky = np.clip(np.dstack([.35+.4*(1-yy/h), .55+.3*(1-yy/h), .85+.1*(1-yy/h)]), 0, 1)
    land = sky.copy(); land[h//2:] = np.dstack([.18+.1*xx[h//2:]/w, .38+.2*yy[h//2:]/h, .12+0*xx[h//2:]])
    night = np.clip(np.dstack([.03+.5*np.exp(-((xx-60)**2+(yy-30)**2)/60), .04+.35*np.exp(-((xx-60)**2+(yy-30)**2)/60), .08+.2*np.exp(-((xx-30)**2+(yy-50)**2)/90)]), 0, 1)
    return {"skin": skin.astype(np.float32), "land": np.clip(land, 0, 1).astype(np.float32), "night": night.astype(np.float32)}


def audit(presets):
    problems, seen = [], set()
    S = scenes()
    for p in presets:
        n = p.get("name", "?")
        for k in ("name", "family", "description"):
            if not p.get(k):
                problems.append((n, f"missing {k}"))
        if n in seen:
            problems.append((n, "duplicate name"))
        seen.add(n)
        for k, v in p.items():
            if k in META:
                continue
            if k not in DEF and f'"{k}"' not in _SRC:
                problems.append((n, f"unknown key {k}"))
            elif k in RANGES and isinstance(v, (int, float)) and not (RANGES[k][0] <= v <= RANGES[k][1]):
                problems.append((n, f"{k}={v} out of range {RANGES[k]}"))
        for sn, img in S.items():
            try:
                o = engine.staged(img, {**DEF, **p})
            except Exception as e:
                problems.append((n, f"render error on {sn}: {e}")); continue
            if not np.isfinite(o).all():
                problems.append((n, f"non-finite output on {sn}")); continue
            y0, y1 = float(np.median(engine.luminance(img))), float(np.median(engine.luminance(o)))
            if abs(y1-y0) > .30 and sn != "night":
                problems.append((n, f"median luma shift {y1-y0:+.2f} on {sn}"))
            clip = float((o >= .995).any(axis=2).mean())
            if clip > .12 and sn != "night":
                problems.append((n, f"{clip:.0%} highlight clipping on {sn}"))
            crush = float((o <= .004).all(axis=2).mean())
            if crush > .35 and sn != "night":
                problems.append((n, f"{crush:.0%} crushed shadows on {sn}"))
    return problems


if __name__ == "__main__":
    pr = audit(engine.PRES)
    print(len(engine.PRES), "presets,", len(pr), "problems")
    import collections
    print(collections.Counter(m.split(" ")[0] if "=" not in m else "range" for _, m in pr))
    for n, m in pr[:40]:
        print(" -", n, "|", m)
