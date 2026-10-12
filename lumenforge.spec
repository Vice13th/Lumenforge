# SPDX-License-Identifier: MIT
# Package the canonical LumenForge monogram as both the Windows executable
# icon and a runtime data asset for Tk titlebar/splash windows.
from pathlib import Path
from PIL import Image

ROOT = Path(SPECPATH)
icon_png = ROOT / "assets" / "lumenforge_logo.png"
icon_ico = ROOT / "assets" / "lumenforge.ico"
if not icon_ico.exists():
    icon_ico.parent.mkdir(parents=True, exist_ok=True)
    if icon_png.is_file():
        with Image.open(icon_png) as image:
            image.convert("RGBA").save(
                icon_ico, format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
    else:
        # Preserve the canonical vector-like monogram when no external PNG
        # is shipped in the source archive.
        import sys
        sys.path.insert(0, str(ROOT))
        from lumenforge.theme import _lumenforge_icon_image
        _lumenforge_icon_image(256).save(
            icon_ico, format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                   (64, 64), (128, 128), (256, 256)])

runtime_assets = [path for path in (icon_ico, icon_png) if path.is_file()]

a = Analysis(
    ["run_lumenforge.py"],
    pathex=["."],
    hiddenimports=[],
    datas=[(str(path), "assets") for path in runtime_assets],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="LumenForge", console=False,
    icon=str(icon_ico) if icon_ico.is_file() else None,
)
