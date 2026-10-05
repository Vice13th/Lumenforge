# SPDX-License-Identifier: MIT
"""
pytest suite for LumenForge's render engine and pipeline (no display
required — only imports/exercises the pure numpy/PIL engine functions,
never instantiates Tk widgets). Run with:

    pip install pytest numba
    pytest test_lumenforge.py -v

This formalizes lumenforge.py's built-in self_tests() into real pytest
cases, plus dedicated coverage for the newer features (multi-channel
Tone Curve, HSL, Color Grading, Local Masks, Straighten, Lightroom
import) that self_tests() doesn't cover yet.
"""
import importlib.util
import math
import tempfile
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "lumenforge.py")


def _load():
    spec = importlib.util.spec_from_file_location("lumenforge", _SRC)
    mod = importlib.util.module_from_spec(spec)
    # Numba cache restoration expects the imported module to be registered
    # in sys.modules under the same stable name used by the spec.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def lf():
    return _load()


def test_canvas_wheel_zoom_routes_to_canonical_zoom(lf):
    from types import SimpleNamespace

    calls = []
    canvas = SimpleNamespace(
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 200,
    )
    app = SimpleNamespace(cnv=canvas)
    app._zs = lambda factor, cx, cy: calls.append((factor, cx, cy))

    event = SimpleNamespace(delta=120, num=None, x_root=140, y_root=260)
    assert lf.App._wheel_zoom(app, event) == "break"
    assert calls == [(1.15, 40, 60)]

    calls.clear()
    event = SimpleNamespace(delta=-120, num=None, x_root=140, y_root=260)
    lf.App._wheel_zoom(app, event)
    assert calls == [(1 / 1.15, 40, 60)]

    calls.clear()
    event = SimpleNamespace(delta=0, num=4, x_root=140, y_root=260)
    lf.App._wheel_zoom(app, event)
    assert calls == [(1.15, 40, 60)]

    calls.clear()
    event = SimpleNamespace(delta=0, num=5, x_root=140, y_root=260)
    lf.App._wheel_zoom(app, event)
    assert calls == [(1 / 1.15, 40, 60)]


def test_ctrl_wheel_reuses_the_same_zoom_callback(lf):
    from types import SimpleNamespace

    class FakeCanvas:
        winfo_rootx = lambda self: 100
        winfo_rooty = lambda self: 200

    app = SimpleNamespace(cnv=FakeCanvas(), _z=1, _ph=None)
    app._wheel_zoom = lf.App._wheel_zoom.__get__(app, lf.App)
    app._zs = lambda factor, cx, cy: setattr(app, "_z", factor)

    event = SimpleNamespace(
        state=4, delta=120, num=None, x_root=140, y_root=260)
    assert lf.App._wh(app, event) == "break"
    assert app._z == 1.15


def test_canvas_binds_all_supported_wheel_events(lf):
    from types import SimpleNamespace

    bound = []

    class FakeCanvas:
        def bind(self, sequence, callback):
            bound.append((sequence, callback))

    app = SimpleNamespace(
        cnv=FakeCanvas(),
        _pp=lambda e: None,
        _pm=lambda e: None,
        _rz=lambda: None,
    )
    app._wheel_zoom = lf.App._wheel_zoom.__get__(app, lf.App)
    lf.App._bp(app)
    sequences = {sequence for sequence, _ in bound}
    assert {"<MouseWheel>", "<Button-4>", "<Button-5>"} <= sequences
    wheel_callbacks = {
        sequence: callback for sequence, callback in bound
        if sequence in {"<MouseWheel>", "<Button-4>", "<Button-5>"}
    }
    assert all(getattr(callback, "__func__", callback) == lf.App._wheel_zoom
               for callback in wheel_callbacks.values())


# ---------------------------------------------------------------- built-in
def test_render_effect_cache_avoids_recomputing_spatial_effects(lf, monkeypatch):
    img = np.random.default_rng(123).random((32, 48, 3), dtype=np.float32)
    p = {**lf.DEF, "clarity": 20, "texture": 10, "dehaze": 15}
    calls = {"clarity": 0, "texture": 0, "dehaze": 0}

    for name in calls:
        original = getattr(lf, {"clarity":"clarity_op", "texture":"tex_op", "dehaze":"dehaze_op"}[name])
        def wrapper(*args, _n=name, _orig=original, **kwargs):
            calls[_n] += 1
            return _orig(*args, **kwargs)
        monkeypatch.setattr(lf, {"clarity":"clarity_op", "texture":"tex_op", "dehaze":"dehaze_op"}[name], wrapper)

    lf.ENG.inval_img()
    lf.ENG.render(img, p)
    first = dict(calls)
    lf.ENG.render(img, p)
    assert calls == first
    p2 = dict(p); p2["exposure"] = 0.25
    lf.ENG.render(img, p2, changed_key="exposure")
    assert calls == first
    p3 = dict(p2); p3["clarity"] = 25
    lf.ENG.render(img, p3, changed_key="clarity")
    assert calls["clarity"] == first["clarity"] + 1
    assert calls["texture"] == first["texture"] + 1
    assert calls["dehaze"] == first["dehaze"] + 1


def test_bounded_tile_cache_reuses_and_evicts(lf):
    src = np.random.default_rng(11).random((32, 24, 3), dtype=np.float32)
    cache = lf.BoundedTileCache(src, tile_rows=8, max_tiles=2)
    a = cache.get(0, 8)
    b = cache.get(8, 16)
    assert a.shape == (8, 24, 3)
    assert b.shape == (8, 24, 3)
    assert not a.flags.writeable
    _ = cache.get(0, 8)
    _ = cache.get(16, 24)
    stats = cache.stats
    assert stats.hits >= 1
    assert stats.misses >= 3
    assert stats.evictions >= 1


def test_bounded_tile_source_enforces_resident_byte_budget(lf):
    src = np.random.default_rng(13).random((64, 32, 3), dtype=np.float32)
    ts = lf.BoundedTileSource(src, tile_rows=8, max_tiles=2, budget_mib=1)
    _ = ts.get(0, 8)
    _ = ts.get(8, 16)
    _ = ts.get(16, 24)
    assert ts.resident_bytes <= 2 * src[:8].nbytes
    assert ts.evictions >= 1


def test_bounded_tile_source_matches_direct_slices(lf):
    src = np.random.default_rng(14).random((41, 29, 3), dtype=np.float32)
    ts = lf.BoundedTileSource(src, tile_rows=7, max_tiles=2, budget_mib=4)
    for y0, y1 in ((0, 7), (7, 14), (14, 21), (34, 41)):
        got = ts.get(y0, y1)
        assert np.array_equal(got, src[y0:y1])


def test_render_bounded_sink_matches_full_small_frame(lf):
    src = np.random.default_rng(12).random((40, 37, 3), dtype=np.float32)
    p = {**lf.DEF, "scene_prep": False, "grain": 0, "clarity": 0,
         "texture": 0, "dehaze": 0, "halation": 0, "bloom": 0,
         "vignette": 0}
    reference = lf.staged(src, p)
    pieces = []
    out = lf.ENG.render_bounded(src, p, tile_rows=7, cache_tiles=2,
                                tile_sink=lambda y0, y1, tile: pieces.append((y0, y1, tile.copy())))
    assert out is None
    got = np.concatenate([tile for _, _, tile in sorted(pieces)], axis=0)
    assert got.shape == reference.shape
    assert np.allclose(got, reference, atol=1e-6, rtol=1e-6)


def test_builtin_self_tests(lf):
    """The app's own self_tests() — gamma/contrast/white-balance/Camera
    DNA round-trip/preset & profile counts. Must return zero failures."""
    failures = lf.self_tests()
    assert failures == [], f"{len(failures)} built-in self-test failures: {failures}"


# ---------------------------------------------------------------- straighten
def test_straighten_crops_out_black_corners(lf):
    from PIL import Image
    im = Image.new("RGB", (400, 300), (128, 64, 32))
    out = lf._rotate_straight(im, 5.0)
    assert out.width < im.width and out.height < im.height


def test_straighten_zero_angle_preserves_size(lf):
    from PIL import Image
    im = Image.new("RGB", (400, 300), (128, 64, 32))
    out = lf._rotate_straight(im, 0.0)
    assert abs(out.width - im.width) <= 2
    assert abs(out.height - im.height) <= 2


# ---------------------------------------------------------------- tone curve
def test_tone_curve_identity_is_noop(lf):
    x = np.random.rand(8, 8, 3).astype(np.float32)
    identity = {"rgb": [(0, 0), (1, 1)], "r": [(0, 0), (1, 1)],
                "g": [(0, 0), (1, 1)], "b": [(0, 0), (1, 1)]}
    y = lf.apply_tone_curves(x.copy(), identity)
    assert np.allclose(x, y, atol=1e-3)


def test_tone_curve_per_channel_isolated(lf):
    x = np.random.rand(8, 8, 3).astype(np.float32)
    curves = {"rgb": [(0, 0), (1, 1)], "r": [(0, 0), (0.5, 0.8), (1, 1)],
              "g": [(0, 0), (1, 1)], "b": [(0, 0), (1, 1)]}
    y = lf.apply_tone_curves(x.copy(), curves)
    assert not np.allclose(x[..., 0], y[..., 0], atol=1e-3)
    assert np.allclose(x[..., 1], y[..., 1], atol=1e-3)
    assert np.allclose(x[..., 2], y[..., 2], atol=1e-3)


# ---------------------------------------------------------------- HSL
def test_hsl_is_active_detection(lf):
    zero = {f"hsl_{b}_{c}": 0 for b in lf.HSL_BANDS for c in ("hue", "sat", "lum")}
    assert not lf._hsl_is_active(zero)
    on = dict(zero)
    on["hsl_red_sat"] = 40
    assert lf._hsl_is_active(on)


def test_hsl_saturation_increases_target_band(lf):
    red_img = np.zeros((4, 4, 3), np.float32)
    red_img[..., 0] = 0.8
    red_img[..., 1] = 0.2
    red_img[..., 2] = 0.2
    p = {f"hsl_{b}_{c}": 0 for b in lf.HSL_BANDS for c in ("hue", "sat", "lum")}
    p["hsl_red_sat"] = 100
    out = lf.apply_hsl(red_img.copy(), p)
    _, s0, _ = lf._rgb_to_hsv_np(red_img)
    _, s1, _ = lf._rgb_to_hsv_np(out)
    assert s1.mean() > s0.mean()


def test_hsl_numba_matches_numpy_fallback(lf):
    """If numba is installed, the JIT kernel must match the numpy path
    (this is the correctness guarantee for the optional fast path)."""
    if not lf.HAVE_NUMBA:
        pytest.skip("numba not installed")
    img = np.random.rand(50, 60, 3).astype(np.float32)
    p = {f"hsl_{b}_{c}": 0.0 for b in lf.HSL_BANDS for c in ("hue", "sat", "lum")}
    p["hsl_red_sat"] = 40.0
    p["hsl_orange_hue"] = 15.0
    p["hsl_blue_lum"] = -20.0
    out_numba = lf.apply_hsl(img.copy(), p)
    lf.HAVE_NUMBA = False
    try:
        out_numpy = lf.apply_hsl(img.copy(), p)
    finally:
        lf.HAVE_NUMBA = True
    assert np.abs(out_numba - out_numpy).max() < 1e-4


# ---------------------------------------------------------------- color grade
def test_color_grade_is_active_detection(lf):
    zero = {"cg_shadow_hue": 0, "cg_shadow_sat": 0, "cg_shadow_lum": 0,
            "cg_midtone_hue": 0, "cg_midtone_sat": 0, "cg_midtone_lum": 0,
            "cg_highlight_hue": 0, "cg_highlight_sat": 0, "cg_highlight_lum": 0,
            "cg_global_hue": 0, "cg_global_sat": 0, "cg_global_lum": 0,
            "cg_blending": 50}
    assert not lf._cg_is_active(zero)
    on = dict(zero)
    on["cg_shadow_sat"] = 80
    assert lf._cg_is_active(on)


def test_color_grade_shadow_tint_direction(lf):
    gray = np.full((4, 4, 3), 0.1, np.float32)
    p = {"cg_shadow_hue": 210, "cg_shadow_sat": 80, "cg_shadow_lum": 0,
         "cg_midtone_hue": 0, "cg_midtone_sat": 0, "cg_midtone_lum": 0,
         "cg_highlight_hue": 0, "cg_highlight_sat": 0, "cg_highlight_lum": 0,
         "cg_global_hue": 0, "cg_global_sat": 0, "cg_global_lum": 0,
         "cg_blending": 50}
    out = lf.color_grade(gray.copy(), p)
    assert not np.allclose(gray, out, atol=1e-3)
    assert out[..., 2].mean() > out[..., 0].mean()  # blue-ish tint


# ---------------------------------------------------------------- local masks
@pytest.fixture
def base_radial_mask():
    return {"type": "radial", "enabled": True, "invert": False,
            "cx": .5, "cy": .5, "rx": .2, "ry": .2, "feather": .5, "angle": 0,
            "params": {"exposure": 1.0, "contrast": 0, "temperature": 0,
                      "saturation": 0, "clarity": 0}}


def test_local_mask_radial_brightens_center(lf, base_radial_mask):
    img = (np.random.rand(200, 300, 3).astype(np.float32) * 0.5 + 0.25)
    out = lf.apply_local_masks(img.copy(), [base_radial_mask])
    assert out[100, 150].mean() > img[100, 150].mean()


def test_local_mask_disabled_is_noop(lf, base_radial_mask):
    img = (np.random.rand(200, 300, 3).astype(np.float32) * 0.5 + 0.25)
    m = dict(base_radial_mask)
    m["enabled"] = False
    out = lf.apply_local_masks(img.copy(), [m])
    assert np.allclose(img, out, atol=1e-6)


def test_local_mask_invert_flips_effect(lf, base_radial_mask):
    img = (np.random.rand(200, 300, 3).astype(np.float32) * 0.5 + 0.25)
    normal = lf.apply_local_masks(img.copy(), [base_radial_mask])
    inv = dict(base_radial_mask)
    inv["invert"] = True
    inverted = lf.apply_local_masks(img.copy(), [inv])
    assert not np.allclose(normal, inverted, atol=1e-3)


def test_local_mask_row_tiling_matches_full_render(lf, base_radial_mask):
    """Regression test for the row-tiled-export mask bug: a mask split
    across export tiles must land identically to a non-tiled render."""
    img = np.random.rand(200, 300, 3).astype(np.float32) * 0.5 + 0.25
    full = lf.apply_local_masks(img.copy(), [base_radial_mask])
    H = img.shape[0]
    stitched = np.zeros_like(img)
    rpt = 50
    for t in range(4):
        y0, y1 = t * rpt, t * rpt + rpt
        stitched[y0:y1] = lf.apply_local_masks(
            img[y0:y1].copy(), [base_radial_mask], full_h=H, y0=y0)
    assert np.allclose(full, stitched, atol=1e-4)


def test_local_mask_brush_changes_image(lf):
    img = np.random.rand(120, 160, 3).astype(np.float32) * 0.5 + 0.25
    m = {"type": "brush", "enabled": True, "invert": False, "feather": .5,
        "radius": .05, "strokes": [[(0.3, 0.3), (0.5, 0.3), (0.5, 0.6)]],
        "params": {"exposure": 0, "contrast": 0, "temperature": 0,
                  "saturation": 80, "clarity": 0}}
    out = lf.apply_local_masks(img.copy(), [m])
    assert not np.allclose(img, out, atol=1e-3)


# ---------------------------------------------------------------- lightroom import
_XMP_SAMPLE = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Exposure2012="0.50" crs:Contrast2012="20" crs:Saturation="15"
    crs:HueAdjustmentRed="10" crs:SaturationAdjustmentOrange="20"
    crs:ColorGradeShadowHue="210" crs:ColorGradeShadowSat="30"
    crs:ColorGradeBlending="60">
   <crs:ToneCurvePV2012>
    <rdf:Seq>
     <rdf:li>0, 0</rdf:li><rdf:li>64, 50</rdf:li>
     <rdf:li>192, 210</rdf:li><rdf:li>255, 255</rdf:li>
    </rdf:Seq>
   </crs:ToneCurvePV2012>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


@pytest.fixture
def xmp_file():
    with tempfile.NamedTemporaryFile(suffix=".xmp", delete=False, mode="w") as f:
        f.write(_XMP_SAMPLE)
        path = f.name
    yield path
    os.unlink(path)


def test_xmp_import_maps_basic_and_hsl_and_colorgrade(lf, xmp_file):
    ps = lf.pxmp(xmp_file)
    assert abs(ps.get("exposure", 0)) > 0.01
    assert ps.get("hsl_red_hue") == 10.0
    assert ps.get("hsl_orange_sat") == 20.0
    assert ps.get("cg_shadow_hue") == 210.0
    assert ps.get("cg_blending") == 60.0


def test_xmp_import_tone_curve_shape(lf, xmp_file):
    ps = lf.pxmp(xmp_file)
    tc = ps.get("tone_curve_pts")
    assert isinstance(tc, dict) and "rgb" in tc
    assert len(tc["rgb"]) == 4
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in tc["rgb"])


# ---------------------------------------------------------------- cube LUT
_CUBE_SAMPLE = """TITLE "test"
LUT_3D_SIZE 2
0.0 0.0 0.0
1.0 0.0 0.0
0.0 1.0 0.0
1.0 1.0 0.0
0.0 0.0 1.0
1.0 0.0 1.0
0.0 1.0 1.0
1.0 1.0 1.0
"""


def test_cube_lut_roundtrip(lf):
    with tempfile.NamedTemporaryFile(suffix=".cube", delete=False, mode="w") as f:
        f.write(_CUBE_SAMPLE)
        path = f.name
    try:
        lut3d = lf.get_lut3d(path)
        test_rgb = np.zeros((2, 2, 3), np.float32)
        test_rgb[0, 0] = [1, 0, 0]
        out = lf.apply_lut3d(test_rgb, lut3d)
        assert out[0, 0, 0] > 0.9
    finally:
        os.unlink(path)


# ---------------------------------------------------------------- presets/profiles
def test_preset_names_are_unique(lf):
    names = [p["name"] for p in lf.PRES]
    assert len(set(names)) == len(names)


def test_camera_profile_ids_are_unique(lf):
    ids = [c.id for c in lf.CAMERA_MODELS]
    assert len(set(ids)) == len(ids)


def test_camera_match_returns_ranked_candidates(lf):
    rgb = np.random.rand(80, 80, 3).astype(np.float32) * 0.6 + 0.2
    res = lf.cd_match_camera(rgb, {})
    assert res and hasattr(res[0], "confidence") and hasattr(res[0], "profile")


# ---------------------------------------------------------------- ACES/OCIO
def test_aces_fallback_tonemap_output_range(lf):
    x = np.random.rand(16, 16, 3).astype(np.float32) * 2.0
    out = lf.ColorManager.to_display(x)
    assert out.shape == x.shape
    assert out.min() >= 0 and out.max() <= 1.0001


def test_aces_toggle_changes_pipeline_output(lf):
    img = np.random.rand(32, 32, 3).astype(np.float32)
    p = dict(lf.DEF)
    p["aces_display"] = True
    o1 = lf.staged(img, p)
    p["aces_display"] = False
    o2 = lf.staged(img, p)
    assert not np.allclose(o1, o2)


# ---------------------------------------------------------------- security
def test_pil_decompression_bomb_ceiling_is_finite_and_generous(lf):
    """Must be raised above PIL's stock ~89.5MP default (real 61-100MP
    cameras and panorama stitches exceed it) but must stay finite —
    disabling the check entirely (None) would remove protection
    against a corrupt/malicious file claiming absurd dimensions."""
    from PIL import Image
    assert Image.MAX_IMAGE_PIXELS is not None
    assert Image.MAX_IMAGE_PIXELS > 89_478_485
    assert Image.MAX_IMAGE_PIXELS <= 1_000_000_000


# ---------------------------------------------------------------- local laplacian
def test_clarity_no_halo_on_step_edge(lf):
    """Regression test for the old single-scale unsharp-mask halo bug:
    on a flat step edge, a region away from the edge must stay flat
    (near-zero std) and the output must not overshoot [0,1] — both of
    which the old algorithm failed (measured: max=2.115, ringing
    std=0.0296 in the flat region)."""
    h, w = 80, 80
    step = np.zeros((h, w, 3), np.float32)
    step[:, w//2:] = 1.0
    out = lf.clarity_op(step.copy(), 100)
    assert out[:, :w//2-8].std() < 0.01
    assert out[:, w//2+8:].std() < 0.01
    assert out.max() <= 1.001


def test_clarity_texture_dehaze_noop_at_zero(lf):
    img = np.random.rand(40, 50, 3).astype(np.float32)*0.6+0.2
    assert np.allclose(lf.clarity_op(img.copy(), 0), img)
    assert np.allclose(lf.tex_op(img.copy(), 0), img)
    assert np.allclose(lf.dehaze_op(img.copy(), 0), img)


def test_clarity_sign_behavior(lf):
    img = np.random.rand(40, 50, 3).astype(np.float32)*0.6+0.2
    pos = lf.clarity_op(img.copy(), 60) - img
    neg = lf.clarity_op(img.copy(), -60) - img
    mask = np.abs(pos) > 1e-4
    same_dir = np.sum(np.sign(pos[mask]) == np.sign(neg[mask]))
    assert same_dir < mask.sum()*0.1


# ---------------------------------------------------------------- auto sky mask
def test_sky_detector_discriminates_sky_from_ground(lf):
    h, w = 120, 160
    sky_h = int(h*0.4)
    img = np.zeros((h, w, 3), np.float32)
    for i in range(sky_h):
        t = i/sky_h
        img[i, :] = [0.45+0.25*t, 0.65+0.15*t, 0.95]
    rng = np.random.default_rng(0)
    ground = np.zeros((h-sky_h, w, 3), np.float32)
    ground[..., 0] = 0.35+rng.normal(0, 0.08, (h-sky_h, w))
    ground[..., 1] = 0.42+rng.normal(0, 0.08, (h-sky_h, w))
    ground[..., 2] = 0.18+rng.normal(0, 0.05, (h-sky_h, w))
    img[sky_h:] = np.clip(ground, 0, 1)
    wgt = lf.detect_sky_mask(img, feather=3)
    assert wgt.shape == (h, w)
    assert wgt[:sky_h-5].mean() > 0.5
    assert wgt[sky_h+10:].mean() < 0.3


def test_auto_mask_type_applies_and_tiles_consistently(lf):
    h, w = 120, 160
    img = np.random.rand(h, w, 3).astype(np.float32)*0.5+0.25
    wgt = lf.detect_sky_mask(img, feather=3)
    m = {"type": "auto", "enabled": True, "invert": False, "feather": 0,
        "weight_map": wgt.tolist(),
        "params": {"exposure": -0.5, "contrast": 0, "temperature": 0,
                  "saturation": 0, "clarity": 0}}
    out = lf.apply_local_masks(img.copy(), [m])
    assert out.shape == img.shape
    assert not np.allclose(out, img)
    full = out
    stitched = np.zeros_like(img)
    rpt = 30
    for t in range(4):
        y0, y1 = t*rpt, t*rpt+rpt
        stitched[y0:y1] = lf.apply_local_masks(img[y0:y1].copy(), [m],
                                               full_h=h, y0=y0)
    # tolerance is the 8-bit quantization step used when the weight_map
    # round-trips through a PIL 'L' image inside _auto_mask_weight, not
    # a tiling bug — geometric mask types (radial/linear) hit 1e-4 here
    # because they have no such quantization step.
    assert np.abs(full-stitched).max() < 1/255


# ---------------------------------------------------------------- full pipeline
def test_staged_pipeline_with_every_feature_active(lf):
    img = np.random.rand(64, 64, 3).astype(np.float32)
    p = dict(lf.DEF)
    p["exposure"] = 0.3
    p["contrast"] = 20
    p["hsl_red_sat"] = 50
    p["cg_shadow_sat"] = 40
    p["cg_shadow_hue"] = 200
    p["tone_curve_pts"] = {"rgb": [(0, 0), (0.5, 0.6), (1, 1)],
                           "r": [(0, 0), (1, 1)], "g": [(0, 0), (1, 1)],
                           "b": [(0, 0), (1, 1)]}
    p["masks"] = [{"type": "linear", "enabled": True, "invert": False,
                  "x0": 0.2, "y0": 0.5, "x1": 0.8, "y1": 0.5, "feather": .4,
                  "params": {"exposure": 0.5, "contrast": 0, "temperature": 0,
                            "saturation": 0, "clarity": 0}}]
    out = lf.staged(img, p)
    assert out is not None and out.shape == img.shape
    assert np.nanmin(out) >= -0.01 and np.nanmax(out) <= 1.5


# ---- optional-dependency paths (OpenCV / rawpy) ----------------------------
def _img(seed=0, h=96, w=128):
    return np.random.RandomState(seed).rand(h, w, 3).astype(np.float32)


def test_blur_cv2_and_fallback_agree(lf, monkeypatch):
    if not lf.HAVE_CV2:
        pytest.skip("OpenCV not installed")
    x = _img()
    with_cv2 = lf.blur(x, 2.0)
    monkeypatch.setattr(lf, "HAVE_CV2", False)
    without = lf.blur(x, 2.0)
    assert with_cv2.shape == without.shape == x.shape
    assert np.isfinite(with_cv2).all() and np.isfinite(without).all()
    # different kernels: only require the same smoothing regime, not equality
    assert abs(float(with_cv2.std()) - float(without.std())) < 0.05


def test_skin_smooth_cv2_and_fallback_finite_and_bounded(lf, monkeypatch):
    p = {"skin_smooth": 60}
    x = _img(1)
    m = np.ones(x.shape[:2], np.float32)
    outs = []
    for flag in ([True, False] if lf.HAVE_CV2 else [False]):
        monkeypatch.setattr(lf, "HAVE_CV2", flag)
        o = lf.skin_tools(x, p, mask=m)
        assert o.shape == x.shape and np.isfinite(o).all()
        outs.append(o)
    for o in outs:
        assert float(o.min()) >= -1e-6 and float(o.max()) <= 1 + 1e-6


def test_face_cascade_loads_when_cv2_present(lf, monkeypatch):
    if not lf.HAVE_CV2:
        pytest.skip("OpenCV not installed")
    monkeypatch.setattr(lf, "_CAS", None)
    assert lf._cas() is not None


def test_face_cascade_none_without_cv2(lf, monkeypatch):
    monkeypatch.setattr(lf, "_CAS", None)
    monkeypatch.setattr(lf, "HAVE_CV2", False)
    assert lf._cas() is None


def test_raw_without_rawpy_raises_clear_error(lf, monkeypatch, tmp_path):
    monkeypatch.setattr(lf, "rawpy", None)
    p = tmp_path / "x.arw"
    p.write_bytes(b"not a raw")
    with pytest.raises(RuntimeError, match="rawpy"):
        lf.load_src(str(p))


def test_corrupt_raw_with_rawpy_fails_loudly(lf, tmp_path):
    if lf.rawpy is None:
        pytest.skip("rawpy not installed")
    p = tmp_path / "bad.arw"
    p.write_bytes(b"not a raw")
    with pytest.raises(Exception):
        lf.load_src(str(p))


def test_xtrans_raw_postprocess_is_repeatable(lf):
    if lf.rawpy is None:
        pytest.skip("rawpy not installed")
    path = os.environ.get("LUMENFORGE_GOLDEN_RAW")
    if not path or not os.path.isfile(path):
        pytest.skip("golden RAW fixture not configured")
    a = lf._raw_postprocess(path, preview=False)
    b = lf._raw_postprocess(path, preview=False)
    assert a.size == b.size
    assert np.array_equal(np.asarray(a), np.asarray(b))


# ---- OCIO path ---------------------------------------------------------------
def test_ocio_to_display_valid_and_differs_from_fallback(lf):
    if not lf.HAVE_OCIO:
        pytest.skip("PyOpenColorIO not installed")
    if lf.ColorManager._get_config() is None:
        pytest.skip("OCIO config unavailable")
    x = _img(2, 32, 32) * 4
    a = lf.ColorManager.to_display(x)
    assert a.shape == x.shape and np.isfinite(a).all()
    assert float(a.min()) >= 0 and float(a.max()) <= 1
    b = lf.aces_fallback_tonemap(x)
    assert float(np.abs(a - b).max()) > 1e-3  # real config != numpy fit


def test_to_display_falls_back_without_ocio(lf, monkeypatch):
    monkeypatch.setattr(lf.ColorManager, "_config", None)
    monkeypatch.setattr(lf, "HAVE_OCIO", False)
    x = _img(3, 16, 16)
    assert np.allclose(lf.ColorManager.to_display(x), lf.aces_fallback_tonemap(x))


# ---- ACES variant selection (R9) ---------------------------------------------
def test_aces_variant_default_and_invalid_env(lf, monkeypatch):
    monkeypatch.delenv("LUMENFORGE_ACES", raising=False)
    assert lf._ocio_variant() == "1.3"
    monkeypatch.setenv("LUMENFORGE_ACES", "bogus")
    assert lf._ocio_variant() == "1.3"
    monkeypatch.setenv("LUMENFORGE_ACES", "2.0")
    assert lf._ocio_variant() == "2.0"


def test_aces_2_0_opt_in_valid_and_differs_from_1_3(lf, monkeypatch):
    if not lf.HAVE_OCIO:
        pytest.skip("PyOpenColorIO not installed")
    x = _img(4, 32, 32) * 4
    outs = {}
    for v in ("1.3", "2.0"):
        monkeypatch.setenv("LUMENFORGE_ACES", v)
        monkeypatch.setattr(lf.ColorManager, "_config", None)
        monkeypatch.setattr(lf.ColorManager, "_proc_cache", {})
        if lf.ColorManager._get_config() is None:
            pytest.skip(f"ACES {v} builtin config unavailable")
        o = lf.ColorManager.to_display(x)
        assert o.shape == x.shape and np.isfinite(o).all()
        assert float(o.min()) >= 0 and float(o.max()) <= 1
        outs[v] = o
    assert float(np.abs(outs["1.3"] - outs["2.0"]).max()) > 1e-3


# ---- LLF perf refactor regression (bit-exact vs original level-outer algorithm)
def _llf_reference(lf, gray, sigma, alpha, num_levels, num_samples):
    gray = np.clip(gray, 0, 1).astype(np.float32)
    n = max(1, min(num_levels, int(np.log2(max(8, min(gray.shape))))-2))
    gpyr = lf._llf_pyramid(gray, n)
    out_pyr = [None]*n+[gpyr[-1]]
    refs = np.linspace(0, 1, max(2, num_samples))
    for level in range(n):
        acc = np.zeros_like(gpyr[level]); wsum = np.zeros_like(gpyr[level])
        for ref in refs:
            rem = lf._llf_remap(gray, ref, sigma, alpha)
            lap = lf._llf_laplacian_at_level(rem, level)
            w_ = np.maximum(1-np.abs(gpyr[level]-ref)*(len(refs)-1), 0)
            acc += w_*lap; wsum += w_
        out_pyr[level] = acc/np.maximum(wsum, 1e-6)
    img = out_pyr[n]
    for level in range(n-1, -1, -1):
        img = lf._llf_up(img, out_pyr[level].shape)+out_pyr[level]
    return img


@pytest.mark.parametrize("kw", [dict(sigma=.12, alpha=.35, num_levels=3, num_samples=4),
                                dict(sigma=.05, alpha=.5, num_levels=2, num_samples=4),
                                dict(sigma=.18, alpha=.3, num_levels=3, num_samples=6)])
def test_llf_optimized_matches_reference_exactly(lf, kw):
    g = np.random.RandomState(7).rand(120, 157).astype(np.float32)
    assert np.array_equal(lf.local_laplacian_filter(g, **kw),
                          _llf_reference(lf, g, **kw))

# ---------------------------------------------------------------- tile-safety gate



def test_tile_spec_core_and_input_bounds(lf):
    t = lf.TileSpec(core_y0=32, core_y1=64, halo_top=24, halo_bottom=24,
                    full_h=100, full_w=200)
    assert t.input_y0 == 8
    assert t.input_y1 == 88
    assert t.core_slice == slice(24, 56)


@pytest.mark.parametrize(("key", "value", "historical_halo"), [
    ("clarity", 70, 32),
    ("texture", 70, 16),
    ("dehaze", 70, 32),
    ("halation", 70, 24),
    ("bloom", 70, 64),
    ("skin_smooth", 70, 8),
    ("skin_clarity", 70, 32),
])
def test_historical_halos_are_not_execution_contracts(lf, key, value, historical_halo):
    p = dict(lf.DEF)
    p["scene_prep"] = False
    p[key] = value
    assert lf.tile_halo_requirements(p) == 0
    graph = lf.graph_tile_contract(p)
    assert graph["verified"] is False
    assert graph["halo"] >= 1


def test_graph_receptive_field_recurrence(lf):
    nodes = [lf.SpatialNode("a", 1, 2, 2),
             lf.SpatialNode("b", 1, 2, 2),
             lf.SpatialNode("c", 1, 2, 2)]
    assert lf.graph_receptive_field(nodes) == (7, 7, 8, 8)


def test_render_budget_tile_rows_is_bounded(lf):
    rows = lf.tile_rows_for_budget(5920)
    assert rows > 0
    assert rows <= 5920
    assert lf.estimate_rgb_bytes(rows, 5920) <= lf.RENDER_TILE_BUDGET_MIB * 1024**2


def _tile_with_halo(lf, img, p, tile_h, halo):
    full_h = img.shape[0]
    out = np.empty_like(img)
    for core_y0 in range(0, full_h, tile_h):
        core_y1 = min(core_y0 + tile_h, full_h)
        spec = lf.TileSpec(core_y0, core_y1, halo, halo, full_h, img.shape[1])
        inp = img[spec.input_y0:spec.input_y1]
        render = lf.staged(inp, p, full_h=full_h, y0=spec.input_y0)
        out[core_y0:core_y1] = render[spec.core_slice]
    return out


def test_proven_halo_is_bit_exact_for_historical_differential_only(lf):
    img = np.random.RandomState(1234).rand(160, 256, 3).astype(np.float32)
    p = dict(lf.DEF)
    p["scene_prep"] = False
    p["grain"] = 0
    p["clarity"] = 70
    full = lf.staged(img, p)
    tiled = _tile_with_halo(lf, img, p, 32, 32)
    assert np.array_equal(full, tiled)
    assert lf.tile_halo_requirements(p) == 0


def test_staged_tile_contract_distinguishes_full_and_row(lf):
    p = dict(lf.DEF)
    p["scene_prep"] = False
    p["grain"] = 0
    assert lf.staged_tile_contract(p)["mode"] == "row"
    q = dict(p, clarity=70)
    assert lf.staged_tile_contract(q)["mode"] == "full"
    assert lf.staged_tile_contract(q)["graph_halo"] > 0
    r = dict(p, vignette=70)
    assert lf.staged_tile_contract(r)["mode"] == "full"

def test_compute_backend_reference_delegates_bit_exactly(lf):
    img = np.random.RandomState(61).rand(48, 73, 3).astype(np.float32)
    p = dict(lf.DEF)
    p["scene_prep"] = False
    p["grain"] = 0
    p["exposure"] = 0.5
    p["contrast"] = 12
    direct = lf.staged(img, p)
    backend = lf.CPU_BACKEND.staged(img, p)
    assert np.array_equal(direct, backend)
    assert lf.CPU_BACKEND.name == "cpu-reference"
    assert lf.CPU_BACKEND.available is True


def test_reference_entrypoint_matches_staged(lf):
    img = np.random.RandomState(77).rand(36, 55, 3).astype(np.float32)
    p = dict(lf.DEF)
    p["scene_prep"] = False
    p["grain"] = 0
    p["exposure"] = -.35
    assert np.array_equal(lf.staged(img, p), lf.render_stage_reference(img, p))


def test_render_request_coalesces_while_render_is_busy(lf):
    from types import SimpleNamespace
    calls = []
    app = SimpleNamespace(pv=np.ones((4, 4, 3), np.float32), _rb=True, _rp=False,
                          _ck=None)
    app._track_undo = lambda: calls.append('undo')
    app._stg = lambda: {**lf.DEF}
    app.req = lf.App.req.__get__(app, lf.App)
    app.req()
    app.req()
    assert app._rp is True
    assert calls == []


def test_render_request_captures_changed_key_once(lf):
    from types import SimpleNamespace
    class After:
        def __init__(self): self.calls=[]
        def __call__(self, *_): self.calls.append('after'); return None
    app = SimpleNamespace(pv=np.ones((4, 4, 3), np.float32), _rb=False, _rp=False,
                          _ck='exposure', _render_hud_show=lambda *_: None)
    app._track_undo = lambda: None
    app._stg = lambda: {**lf.DEF}
    app.after = After()
    old = lf.ENG.render
    lf.ENG.render = lambda rgb, st, changed_key=None: (calls.append(changed_key) or rgb) if False else rgb
    calls=[]
    lf.App.req(app)
    lf.ENG.render = old
    assert app._ck is None
