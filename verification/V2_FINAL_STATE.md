# LumenForge V2 — final-state evidence snapshot

> **Evidence timestamp:** 8 October 2026 release-candidate receipts, reviewed 12 October 2026. This file preserves historical release evidence and records the runtime-wiring boundary found by the subsequent source inspection. The 12 October documentation review did not rerun tests or rebuild artifacts.

## Source identity and entry point

- Reviewed V2 source baseline: `integration-v2` at `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1`.
- Application launcher: root `lumenforge.py`, importing `source.lumenforge`.
- Active engine: `source/lumenforge.py`; NumPy-based rendering with selected optional Numba acceleration.
- Historical candidate build environment: Windows 11 / Python 3.12.10 / PyInstaller 6.22.3.
- Historical artifact path: `D:\Lumenlabs\RELEASE_CANDIDATES\LumenForge-2.0.0\dist_final\dist\LumenForge-2.0.0`.
- Historical executable SHA256: `C338A6830E8467CB6874B63A0389BF7A4A99758A5D9CD9042DBB2F94617A9E7B`.
- Historical distribution: 1,128 files / 349,868,017 bytes.
- Historical smoke: process reportedly stayed alive for 8 seconds, window title `Lumen Forge - v2`, and then terminated cleanly.

The artifact/build receipt predates this documentation review. Its exact relationship to any later source state must be checked before reusing it for release.

## Recorded verification (not rerun on 12 October)

- Python tests: **143 passed, 2 skipped, 2 warnings in 9.63s**.
- compileall: PASS in the historical receipt.
- Hygiene: PASS in the historical receipt.
- Secret scan: NO_MATCHES in the historical receipt.
- Optional Numba `tbb12.dll` packaging warning remained.

## Runtime architecture status from 12 October source inspection

- The V2 frame, scene-graph, cache, export, ICC, OCIO, offline-AI, camera-characterization and CUDA modules exist in the repository with focused tests/receipts.
- Those modules are **not established as production runtime integrations**: direct inspection of the active `source/lumenforge.py` found no imports/calls to the `source/v2_*.py` adapters.
- The active in-file 3D LUT path uses trilinear interpolation and clips to `[0,1]`; the standalone CUDA path uses tetrahedral interpolation and does not clip output. No active-app CPU/GPU parity result is established.
- The CUDA receipt is historical and limited to its measured RTX 2070 Max-Q/CUDA environment and probe. It is not an end-to-end performance receipt.
- Full analysis and required next evidence: [V2 architecture review](../docs/V2_ARCHITECTURE_REVIEW_2026-10-12.md).

## Open release boundaries

- Camera Gate 2A: **NOT CLOSED**.
- Camera Gate 2B: **BLOCKED**.
- EXIF/XMP certification: **BLOCKED**.
- Clean-machine portability: **UNVERIFIED**.
- Universal GPU/backend portability: **NOT CLAIMED**.
- Optional Numba `tbb12.dll` packaging warning: **REMAINS RECORDED**.

Root `LICENSE` is present and declares MIT in the historical record.

## Branch/release boundary

GitHub's compare endpoint returned **“No common ancestor between main and integration-v2.”** No merge or release should be inferred from the existence of both branches. The toolbar-only branch based on `main` is a separate change and does not deliver the V2 adapters into the active engine.

## Release decision

**NOT CLEARED FOR A NEW RELEASE from this evidence alone.** Before release, connect and verify intended runtime adapters, resolve edge contracts and dependency declarations, run a fresh test/build/package sequence on the exact release commit, then attach source-to-artifact hashes and platform-specific receipts. Keep the camera-science and portability gates open until their evidence is supplied.
