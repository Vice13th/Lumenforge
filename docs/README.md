# LumenForge v2 — Cinema Colour Grading

LumenForge v2 is a desktop photo editor focused on film-emulation and cinema-style colour work.

The current application is implemented as a single Python/Tkinter application with the render engine and UI in `lumenforge.py`.

## Release

**Release:** LumenForge v2

## Current Status

- Primary application: `lumenforge.py`
- UI toolkit: Python `tkinter` / `ttk`
- Render engine: NumPy-based pipeline with optional Numba acceleration
- Preview canvas: interactive image preview with pan and zoom
- Mouse Wheel Zoom: enabled on the main Preview/Canvas while preserving normal wheel behavior elsewhere
- Tests: 64 passed / 3 skipped in the current fresh verification run

## Run

```bash
pip install -r requirements.txt
python lumenforge.py
```

Optional dependencies are handled conservatively by the application:

- `numba` — accelerates selected processing paths; NumPy remains the fallback
- `rawpy` — enables RAW image input; without it, RAW files are not opened
- `opencv-python-headless` — used for optional image-processing fast paths
- OpenColorIO — optional; when unavailable, the application uses its NumPy fallback for the display transform

## Test

Install the test dependency and run the project test suite:

```bash
pip install pytest
pytest tests/test_lumenforge.py -v
```

The current suite contains 63 passing tests plus 3 optional skips covering the render engine, HSL, Color Grading, Tone Curve, Local Masks, Local Laplacian processing, sky detection, Lightroom XMP import, CUBE LUT import, Camera Match, and the staged pipeline with multiple features enabled together.

CI is defined in `.github/workflows/tests.yml` and runs the Python test matrix on Ubuntu and Windows with and without Numba.

## Large-image processing

The current code includes a conservative bounded-tile execution path for verified row-safe graphs. The sink form avoids a full resident output buffer, but the current stress source is still a resident NumPy array. Therefore this evidence is **not** claimed as true file-backed out-of-core input processing.

A fresh 5920×5920×3 float32 sink stress run processed 47 tiles at 128 rows, with 401.07 MiB logical input and 197.97 MiB observed peak RSS in the current environment. These figures describe this specific stress configuration, not a universal performance guarantee.

## Mouse Wheel Zoom

The Preview/Canvas supports direct mouse-wheel zooming.

- Wheel Up → Zoom In
- Wheel Down → Zoom Out
- Linux button events (`Button-4` / `Button-5`) are supported
- Zoom uses the existing canonical zoom path and its existing limits/scale behavior
- Cursor-relative zoom anchoring is preserved
- Wheel input is scoped to the Preview/Canvas and is not globally converted into zoom
- Existing application wheel handling outside the Preview/Canvas remains available

The existing zoom implementation is centered on `App._zs()`. Mouse-wheel input is routed into that path rather than introducing a second zoom system.

## Feature Set

### Colour and Tone

- Exposure, tone and colour controls
- White Balance
- Clarity, Texture and Dehaze using the Local Laplacian Filter
- 8-band HSL controls
- 3-way Color Grading for Shadows, Midtones, Highlights and Global
- Per-channel Tone Curve for Master, Red, Green and Blue

### Camera and Look Development

- Camera Match / Camera DNA workflow
- Automatic camera-profile detection from EXIF where available
- 3D `.cube` LUT import
- Lightroom `.xmp` preset import
- Optional ACES-inspired display transform with an OpenColorIO path when available and a NumPy fallback otherwise

### Local Adjustments

- Radial masks
- Linear masks
- Brush masks
- Automatically detected Sky mask based on classical colour, position and local-texture heuristics

### Editing and Projects

- Straighten
- Crop
- Undo / Redo
- Non-destructive `.lfproj` project files
- Batch export

## Processing Notes

Clarity, Texture and Dehaze use a Local Laplacian based implementation rather than a single-scale unsharp-mask approach. The current implementation was validated against a step-edge test during the latest engineering pass, where the previous halo/ringing behavior was reduced to the expected bounded result.

Optional Numba acceleration is used where available and falls back to the NumPy implementation automatically.

## Known Technical Gaps

The following items remain intentionally outside the current patch scope:

1. **Full current ACES implementation** — the built-in path is an ACES-inspired NumPy fallback. A real OpenColorIO installation is required when the project needs the external color-management implementation.
3. **Full GPU-resident render pipeline** — the current architecture is primarily CPU/NumPy based, with optional Numba acceleration for selected operations. A complete GPU pipeline would require a larger architectural change.

These limitations are documented here rather than being represented as implemented features.

## Repository Structure

```text
.
├── lumenforge.py
├── requirements.txt
├── tests/
│   └── test_lumenforge.py
├── .github/
│   └── workflows/
│       └── tests.yml
├── CHECKPOINT.md
├── PATCH_REPORT.md
├── ROADMAP.md
└── LICENSE
```

## Engineering Principles

Changes to the project should remain conservative and evidence-driven:

- Preserve existing behavior unless a change is explicitly required.
- Reuse canonical processing paths instead of duplicating logic.
- Verify imports, tests and runtime behavior after implementation.
- Remove code or dependencies only when repository evidence proves they are no longer required.
- Leave uncertain components untouched and document them as unverified.

## License

MIT

## ACES variant (optional)
Set `LUMENFORGE_ACES=2.0` to use the ACES 2.0 OCIO config (needs PyOpenColorIO >= 2.5). Default is the ACES 1.3 config (unchanged behaviour).
