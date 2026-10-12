import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lumenforge.theme import _lumenforge_icon_image


class BrandingAndLayoutTests(unittest.TestCase):
    def test_canonical_icon_has_expected_square_rgba_sizes(self):
        for size in (16, 32, 64, 128, 256):
            image = _lumenforge_icon_image(size)
            self.assertEqual(image.size, (size, size))
            self.assertEqual(image.mode, "RGBA")
            self.assertIsNotNone(image.getbbox())

    def test_splash_uses_canonical_brand_helper(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lumenforge" / "dialogs.py").read_text(encoding="utf-8")
        self.assertIn("_lumenforge_icon_image(64)", source)
        self.assertIn("LUMENFORGE", source)
        self.assertIn("IMAGE LAB", source)
        self.assertIn("self._brand_icon = self._window_icon", source)
        draw_source = source.split("    def _draw(self):", 1)[1].split("    def _anim(self):", 1)[0]
        self.assertNotIn("ImageTk.PhotoImage", draw_source)
        theme_source = (Path(__file__).resolve().parents[1] / "lumenforge" / "theme.py").read_text(encoding="utf-8")
        self.assertIn('fill="#C4B5FD"', theme_source)
        self.assertIn('fill="#A78BFA"', theme_source)

    def test_toolbar_fit_accounts_for_secondary_controls(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lumenforge" / "layout.py").read_text(encoding="utf-8")
        app_source = (Path(__file__).resolve().parents[1] /
                      "lumenforge" / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.minsize(min(1120, max(800, sw-40))', app_source)
        self.assertIn('self.after_idle(self._schedule_toolbar_fit)', app_source)
        self.assertIn('self.after(220, self._toolbar_fit)', app_source)
        self.assertNotIn('center_view = tk.Canvas(', app_source)
        self.assertIn('bf.pack(side="left", fill="x", expand=True)', app_source)
        self.assertIn('self.iconphoto(False, self._app_icon)', app_source)
        self.assertIn('1.40 - elapsed', app_source)
        self.assertIn('self._tb_top.winfo_ismapped()', source)
        self.assertIn('window_width = max(1, min(', source)
        self.assertIn('top = tk.Frame(self._top_shell, bg=T["panel"], height=72)', app_source)
        self.assertIn('want = grid_clamp(max(132, need), 132, 144)', source)
        self.assertIn('self._fit_fixed_containers()', app_source)

    def test_primary_toolbar_container_expands_without_overlapping_export(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lumenforge" / "app.py").read_text(encoding="utf-8")
        self.assertIn('bf.pack(side="left", fill="x", expand=True)', source)
        self.assertIn('rf.pack(side="right", fill="y", padx=(8, 16))', source)
        self.assertLess(source.index('rf.pack(side="right", fill="y", padx=(8, 16))'), source.index('bf.pack(side="left", fill="x", expand=True)'))
        self.assertIn('self._tb_groups = (', source)
        self.assertIn('self._be.pack(side="left", pady=11)', source)
        self.assertIn('self._bb.pack(side="left", padx=(7, 0), pady=15)', source)

    def test_pyinstaller_spec_embeds_runtime_and_executable_icons(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lumenforge.spec").read_text(encoding="utf-8")
        self.assertIn('name="LumenForge"', source)
        self.assertIn('icon=str(icon_ico)', source)
        self.assertIn('runtime_assets = [path for path in (icon_ico, icon_png) if path.is_file()]', source)
        self.assertIn('datas=[(str(path), "assets") for path in runtime_assets]', source)


if __name__ == "__main__":
    unittest.main()


class ToolbarScrollRegressionTests(unittest.TestCase):
    def test_toolbar_uses_scrollable_center_with_pinned_export_group(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "lumenforge" / "app.py").read_text(encoding="utf-8")
        layout_source = (root / "lumenforge" / "layout.py").read_text(encoding="utf-8")
        self.assertNotIn('center_view = tk.Canvas(', app_source)
        self.assertIn('bf.pack(side="left", fill="x", expand=True)', app_source)
        self.assertIn('rf.pack(side="right", fill="y", padx=(8, 16))', app_source)
        self.assertNotIn('def _toolbar_mousewheel(self, event):', app_source)
        self.assertIn('center_need = self._tb_center.winfo_reqwidth()', layout_source)
        self.assertNotIn('collapse_order =', layout_source)
