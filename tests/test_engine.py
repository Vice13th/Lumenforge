"""Headless engine tests: run with `python -m unittest discover tests` (no tkinter needed)."""
import sys, os, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from lumenforge import engine


class EngineTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.rgb = rng.random((48, 64, 3), dtype=np.float32)

    def test_identity_render_keeps_shape_and_range(self):
        out = engine.ENG.render(self.rgb, {}, changed_key=None)
        self.assertEqual(out.shape, self.rgb.shape)
        self.assertTrue(0.0 <= float(out.min()) and float(out.max()) <= 1.0)

    def test_aces_display_changes_output(self):
        a = engine.staged(self.rgb, {})
        b = engine.staged(self.rgb, {"aces_display": True})
        self.assertGreater(float(np.abs(a - b).mean()), 1e-4)

    def test_auto_mask_uses_weight_map(self):
        wm = np.ones(self.rgb.shape[:2], np.float32).tolist()
        mask = {"type": "auto", "enabled": True, "weight_map": wm,
                "params": {"exposure": 1.0}, "invert": False}
        base = engine.staged(self.rgb, {})
        out = engine.staged(self.rgb, {"masks": [mask]})
        self.assertGreater(float(np.abs(out - base).mean()), 1e-4)

    def test_tile_safety_gate(self):
        self.assertTrue(engine.staged_tile_safe({}))
        self.assertFalse(engine.staged_tile_safe({"grain": 10}))
        self.assertFalse(engine.staged_tile_safe({"vignette": 10}))

    def test_noise_reduction_lowers_noise(self):
        rng = np.random.default_rng(3)
        base = np.full((64, 64, 3), .5, np.float32)
        noisy = np.clip(base + rng.normal(0, .05, base.shape), 0, 1).astype(np.float32)
        out = engine.staged(noisy, {"nr_luma": 80, "nr_color": 80})
        self.assertLess(float(np.std(out - base)), float(np.std(noisy - base)) * .7)

    def test_sharpen_acts_on_edges_not_flat_areas(self):
        img = np.full((48, 96, 3), .3, np.float32)
        img[:, 48:] = .7
        out = engine.staged(img, {"sharpen": 100, "sharpen_masking": 60})
        self.assertGreater(float(np.abs(out - img)[:, 44:52].mean()), .01)
        self.assertLess(float(np.abs(out - img)[:, 5:30].mean()), 1e-3)

    def test_auto_tone_centres_median_and_stays_in_range(self):
        dark = np.clip(np.full((60, 80, 3), .18, np.float32) * np.linspace(.4, 1.4, 80)[None, :, None], 0, 1)
        v = engine.auto_tone_params(dark)
        for k, lim in (("exposure", 3), ("contrast", 100), ("highlights", 100),
                       ("shadows", 100), ("whites", 100), ("blacks", 100)):
            self.assertLessEqual(abs(v[k]), lim)
        out = engine.staged(dark, v)
        self.assertLess(abs(float(np.median(engine.luminance(out))) - .46), .06)

    def test_defringe_removes_edge_fringe_only(self):
        img = np.full((48, 96, 3), .2, np.float32)
        img[:, 48:] = .8
        img[:, 46:48] = [.45, .2, .5]
        base = engine.staged(img, {})
        out = engine.staged(img, {"defringe": 100})
        self.assertLess(float(np.ptp(out[:, 46:48], axis=2).mean()), .05)
        self.assertEqual(float(np.abs(out - base)[:, :30].max()), 0.0)

    def test_spot_heal_removes_blemish(self):
        img = np.full((80, 80, 3), .5, np.float32)
        img[38:43, 38:43] = .05
        spot = {"x": .5, "y": .5, "r": .1, "sx": .25, "sy": .25}
        out = engine.staged(img, {"spots": [spot]})
        self.assertLess(abs(float(out[40, 40, 0]) - .5), .02)
        base = engine.staged(img, {})
        self.assertEqual(float(np.abs(out - base)[:20, :20].max()), 0.0)
        self.assertFalse(engine.staged_tile_safe({"spots": [spot]}))

    def test_distortion_moves_edges_not_centre(self):
        img = np.zeros((60, 80, 3), np.float32)
        img[:, 70:] = 1.0
        out = engine.staged(img, {"distortion": 100})
        base = engine.staged(img, {})
        self.assertAlmostEqual(float(out[30, 40, 0]), float(base[30, 40, 0]), places=3)
        self.assertGreater(float(np.abs(out - base).max()), .1)
        self.assertEqual(engine.distort_op(img, 0).shape, img.shape)

    def test_clipping_overlay_marks_extremes(self):
        img = np.full((4, 4, 3), .5, np.float32)
        img[0, 0] = 1.0
        img[1, 1] = 0.0
        out = engine.clipping_overlay(img)
        self.assertGreater(out[0, 0, 0], .9)
        self.assertGreater(out[1, 1, 2], .9)
        self.assertEqual(float(out[3, 3, 0]), .5)

    def test_range_mask_only_touches_selected_luminance(self):
        img = np.full((20, 40, 3), .2, np.float32)
        img[:, 20:] = .9
        m = {"type": "range", "enabled": True, "lum_range": [.65, 1.0],
             "params": {"exposure": -1.0}}
        base = engine.staged(img, {})
        out = engine.staged(img, {"masks": [m]})
        self.assertEqual(float(np.abs(out - base)[:, :10].max()), 0.0)
        self.assertGreater(float(np.abs(out - base)[:, 30:].mean()), .1)

    def test_hue_range_mask_selects_only_matching_colour(self):
        img = np.zeros((20, 40, 3), np.float32)
        img[:, :20] = [.2, .7, .2]
        img[:, 20:] = [.8, .2, .2]
        m = {"type": "range", "enabled": True, "hue_range": [120, 70],
             "params": {"exposure": -1.0}}
        base = engine.staged(img, {})
        out = engine.staged(img, {"masks": [m]})
        self.assertGreater(float(np.abs(out - base)[:, :20].mean()), .05)
        self.assertEqual(float(np.abs(out - base)[:, 25:].max()), 0.0)

    def test_hue_at_reads_hue_and_rejects_grey(self):
        img = np.full((20, 20, 3), .5, np.float32)
        img[:, :10] = [.2, .7, .2]
        self.assertAlmostEqual(engine.hue_at(img, .2, .5), 120.0, delta=2)
        self.assertIsNone(engine.hue_at(img, .9, .5))

    def test_sanitize_params_clamps_and_repairs(self):
        from lumenforge.params import sanitize_params
        out = sanitize_params({"exposure": 99, "contrast": "bad", "masks": [], "custom": 1})
        self.assertEqual(out["exposure"], 3)
        self.assertEqual(out["contrast"], 0)
        self.assertEqual(out["custom"], 1)

    def test_face_cascade_loader_is_cached_and_safe(self):
        self.assertIs(engine._cas(), engine._cas())

    def test_sky_mask_shape(self):
        self.assertEqual(engine.detect_sky_mask(self.rgb).shape, self.rgb.shape[:2])

    def test_render_generation_cancels_stale_work(self):
        gen = engine.RenderGeneration()
        first = gen.next()
        gen.next()
        with self.assertRaises(engine.RenderCancelled):
            gen.checkpoint(first)


if __name__ == "__main__":
    unittest.main()
