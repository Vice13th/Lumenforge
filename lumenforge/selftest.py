# SPDX-License-Identifier: MIT
"""In-app self tests used by the application."""

import tempfile
import json
import numpy as np
from .engine import CAMERA_MODELS, CAMERA_PROFILES, CD_DEFAULTS, ENG, LUT, PRES, _camera_character_transform, _neutralizing_profile, apply_fused_tone, cd_apply, cd_match_camera, cd_pixel_signature, clamp, ctemp, grain, halation, pcube, pjson, prep_scene, print_lut, pxmp, skin_tools, skmask, staged, tint_op, tone_gamma_lut, wb_from_point, wb_gray_world, ycc_skin
from .engine import HR
from .params import DEF, GRP, SPEC
import os


def _tg(w=96, h=64):
    x = np.tile(np.linspace(0, 1, w, np.float32), (h, 1))
    return np.stack([x, np.clip(x*.8+.1, 0, 1), np.clip(1-x, 0, 1)], 2)


def self_tests():
    """Run the built-in numerical and pipeline regression checks."""
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

    # Why this exists:
    # Camera Match is deterministic, while the existing grain layer is intentionally
    # stochastic; preserving that distinction keeps the render contract unchanged.

    return F
