# LumenForge v2 — project guide

LumenForge is a desktop image editor for photographic rendering and cinema-style colour work. This page describes the **`integration-v2` source tree**, reviewed against commit `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1` on 12 October 2026. It does not represent a newly published release.

## Current architecture

- **Launcher:** root `lumenforge.py` is a thin wrapper that imports `source.lumenforge` and starts the Tkinter app.
- **Active render engine:** `source/lumenforge.py` — NumPy pipeline, interactive `Eng` layer cache, non-cached `staged(...)` path, LUT parsing/application and UI.
- **V2 contracts/adapters:** `source/v2_*.py` — frame/color-state, graph/cache keys, CUDA LUT, image export, ICC, OCIO, local ONNX embeddings and camera-characterization helpers.
- **Tests:** `tests/test_lumenforge.py`, `tests/test_ui_accessibility.py`, and focused `tests/test_v2_*.py` modules.
- **Evidence:** `verification/V2_*_RECEIPT.json`, `verification/V2_INTEGRATION_MATRIX.md` and `verification/V2_FINAL_STATE.md`.

Important distinction: the V2 adapter files are present and have focused tests, but source inspection at the reviewed baseline did **not** find those adapters imported or called by the active `source/lumenforge.py` engine. In particular, `source/v2_cuda_lut.py` is not yet the production render backend. See [Architecture](ARCHITECTURE.md) and [the 12 October evidence review](V2_ARCHITECTURE_REVIEW_2026-10-12.md).

## Run and test

The reviewed tree contains `pyproject.toml` and `uv.lock`; it does not contain a root `requirements.txt` or the `.github/workflows/tests.yml` referenced by older README text. `docs/requirements.txt` is a legacy optional-dependency compatibility list and is **not** a complete V2 lock/install recipe.

In an environment with the declared project and test dependencies available, run:

```powershell
python lumenforge.py
python -m pytest tests -q
```

These commands describe how to launch the source and run tests; they are not a claim that either command was executed during the 12 October documentation pass. The most recent aggregate test result recorded in the V2 receipts is 143 passed, 2 skipped and 2 warnings on 8 October 2026.

## Dependency authority

- `pyproject.toml` declares the project Python range and direct project/development dependencies.
- `uv.lock` records a resolved environment.
- Optional adapter imports such as CuPy, tifffile, OpenEXR, ONNX Runtime, tokenizers and PyOpenColorIO are not all declared in the project dependency list. Availability of an adapter's Python file therefore does not guarantee that its runtime dependencies are installed.
- `docs/requirements.txt` does not exactly match `pyproject.toml` (including the OpenCV distribution name). See [Dependency Matrix](DEPENDENCY_MATRIX.md).

## Feature areas

The active application includes exposure/tone/colour controls, white balance, HSL and colour grading, tone curves, local adjustments, crop/straighten, undo/redo, 3D `.cube` LUT support, Lightroom XMP import, camera-profile workflows, batch export and optional RAW input via rawpy when available.

V2 adds independently testable boundaries for frame/color-state metadata, deterministic graph/cache identities, a CuPy tetrahedral LUT kernel, explicit export and ICC helpers, OCIO processing, local ONNX embeddings and camera-characterization research. These are not all wired into the active UI/render pipeline.

## Current release gates

The recorded V2 candidate was built in Windows 11 / Python 3.12.10 with PyInstaller 6.22.3. Its receipt reports a packaged startup smoke pass. The same record leaves Camera Gate 2A open, Camera Gate 2B blocked, EXIF/XMP certification blocked, clean-machine portability unverified and universal GPU portability unclaimed. The optional Numba `tbb12.dll` packaging warning also remains recorded.

Receipt results describe their original environment and commit; they must not be reused as proof for a different source state or machine. A new release needs fresh source-to-artifact traceability and fresh verification.

## Repository history boundary

GitHub's compare endpoint reports no common ancestor between `main` and `integration-v2`. The branches must not be merged or treated as one release line by assumption. The V2 docs are being reconciled on a documentation-only branch based on `integration-v2`; no source behavior or release artifact is changed by this documentation work.

## License

MIT; see the root `LICENSE`.
