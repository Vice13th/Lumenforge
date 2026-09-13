# Lumen Forge

Lumen Forge is a Python desktop photo editing and color-grading application.

## Open-source license

The Lumen Forge source code in this repository is released under the **MIT License**.
See `LICENSE`.

> Third-party Python packages are not relicensed by this project. Their own
> licenses and terms continue to apply.

## Requirements

- Python 3
- Tkinter (normally included with standard Python installations)
- NumPy
- Pillow
- Optional: `rawpy` for RAW formats
- Optional: `opencv-python` for OpenCV-backed functionality

## Install

```bash
pip install numpy pillow
# Optional RAW support:
pip install rawpy
# Optional OpenCV support:
pip install opencv-python
```

## Run

```bash
python lumenforge.py
```

## Build a Windows executable

```bash
pyinstaller --onefile --noconsole --name "LumenForge" lumenforge.py
```

## Supported source formats

The application includes support for common image formats and RAW extensions
such as ARW, CR2, CR3, NEF, NRW, RAF, ORF, RW2, DNG, PEF, SRW, 3FR and RAW,
with RAW loading dependent on `rawpy`.

## Presets and LUT import

Lumen Forge includes its built-in preset system and supports importing:

- `.xmp`
- `.cube`
- `.json`

CUBE LUTs are applied through the application's 3D LUT/trilinear pipeline.

## Camera DNA

The Camera DNA system provides camera matching using metadata and/or pixel
appearance analysis, with confidence states rather than unconditional claims.
Where proprietary manufacturer color science is unavailable, camera character
is implemented as a documented mathematical approximation rather than a
bit-exact proprietary IDT/LUT.

## Project note

This repository is intended to be a clean open-source distribution of the
Lumen Forge application source. Do not add third-party proprietary LUTs,
IDTs, presets, images, trademarks, or other assets unless their licenses
permit redistribution.
