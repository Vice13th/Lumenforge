# Changelog

All notable Lumen Forge changes are documented here.

The project uses two versioning layers:

- **Distribution release:** the published desktop release currently remains `v1.0.0`.
- **Application/render-engine version:** the current source identifies itself as **Render Engine 12.0**.

A newer source snapshot on `main` does not automatically mean a new binary release.

---

## [Unreleased] — 2026-10-06

### Repository & Source

- Published the complete `lumenforge.py` application source in the Git repository.
- Added an autonomous-agent bootstrap contract in `AGENTS.md`.
- Added a durable master execution roadmap.
- Added a durable execution/evidence ledger.
- Reconciled the repository documentation with the current open-source state.

### UI

- Added a Windows-native dark title-bar request through DWM for the main Tk window.
- The title-bar change is intentionally limited to native window chrome and does not alter the image-rendering pipeline.

### Documentation

- Reworked the README around the actual current source architecture.
- Added a detailed processing architecture document.
- Added an exact `v1.0.0 → main` repository comparison.
- Expanded build, publishing, security and third-party documentation.
- Clarified the boundary between source state, release artifacts and verification evidence.
- Corrected authoritative LUT terminology to **trilinear interpolation** based on the current source path.
- Reconciled the current source preset inventory at **121 built-in preset definitions**.

### Verification state

- The dark title-bar implementation is **OBSERVED at source level**.
- A real Windows runtime/EXE visual verification has not yet been recorded for that change.
- The published `v1.0.0` executable remains the previously released binary; no new versioned executable has been claimed here.

---

## v1.0.0 — First Public Windows Release

Published: 2026-09-12

The first public Lumen Forge desktop release introduced the application as a Windows distribution built around:

- layered image processing;
- camera-inspired colour rendering;
- perceptual OKLab processing;
- HSL colour control;
- editable curves;
- 3D LUT processing;
- non-destructive editing;
- a dark desktop UI;
- cinematic and photographic colour workflows.

Release artifact:

`LumenForge.exe`

SHA-256:

`349361449982613edad854fee9f968f687cd6868040ac51f645e25f9c5df7`

See the historical release page for the exact v1.0.0 packaging and release text.

---

## Documentation history

The public repository evolved from a release-oriented distribution surface into a source-available project with:

- MIT source licensing;
- source build instructions;
- publishing controls;
- security guidance;
- third-party notices;
- integrity/checksum records;
- agent bootstrap and execution governance.

---

## Licensing

Lumen Forge project-owned source code is released under the MIT License.

Third-party software, assets, trademarks, camera names, and other externally owned materials remain subject to their own licenses and terms.
