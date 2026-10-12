# SPDX-License-Identifier: MIT
"""Application constants and limits."""

import os
import sys


APP_NAME = "Lumen Forge"


VERSION = "12.0"


if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Bundled read-only assets (PyInstaller unpacks them to _MEIPASS).
ASSET_DIR = getattr(sys, "_MEIPASS", SCRIPT_DIR)
IMPORTED_FILE = os.path.join(SCRIPT_DIR, "imported_presets.json")


PREVIEW_MAX = 900


PREVIEW_ZOOM_MAX = 3600  # ceiling for the zoomed-in preview resolution —


                          # keeps re-renders fast on very large source
                          # images while still giving a sharp 1:1-ish view
ZOOM_MAX = 8.0


RAW_EXT = {".arw",".cr2",".cr3",".nef",".nrw",".raf",".orf",".rw2",
           ".dng",".pef",".srw",".3fr",".raw"}
