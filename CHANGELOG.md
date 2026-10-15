# Changelog

All notable Lumen Forge changes are documented here.

The project uses two versioning layers:

- **Historical first release:** `v1.0.0` remains published and unchanged.
- **Current versioned Windows release:** [v2.0.0](https://github.com/Vice13th/Lumenforge/releases/tag/v2.0.0) is the canonical public release page.
- **Legacy engineering handoff:** `handoff-2026-10-15` remains available as an older release entry.
- **Application/render-engine version:** the current source identifies itself as **Render Engine 12.0**.

A published handoff/build is not proof that every commit on `main` is represented by the binary.

---

## LumenForge 2.0 — Windows x64 release (2026-10-15)

Published under tag [`v2.0.0`](https://github.com/Vice13th/Lumenforge/releases/tag/v2.0.0). This is the canonical versioned Windows x64 release; the older `handoff-2026-10-15` entry remains available as a legacy release page, while `v1.0.0` remains the historical first public release.

### Artifact validation reported by the release

- Clean CPython 3.12.10 virtual environment; NumPy 2.5.4 and Pillow 12.3.0.
- PyInstaller 6.22.3 clean build passed.
- Tests: **129 passed, 7 skipped, 32 subtests passed**; Ruff passed.
- Startup smoke test: executable process remained alive for 8 seconds before the harness stopped it.
- ZIP extraction and embedded executable SHA-256 equality passed.

### Limits

This is build-host verification, not clean-machine certification. Full open/edit/export was not exhaustively tested on a separate Windows installation. Optional RAW/HEIF and acceleration integrations are not guaranteed bundled. Exact source ancestry to the `v1.0.0` commit is not established; no claim is made that the binary was built from a particular committed source SHA.

### Published artifacts

- [LumenForge-2.0.0-Windows-x64.zip](https://github.com/Vice13th/Lumenforge/releases/download/v2.0.0/LumenForge-2.0.0-Windows-x64.zip) — SHA-256 `5899C72FB9F5DFFBF8B1BD7E0F2F40C8C234C6B251C0934B2FB58F5B496758AA`
- [LumenForge.exe](https://github.com/Vice13th/Lumenforge/releases/download/v2.0.0/LumenForge.exe) — SHA-256 `23D3191DD86DCFD97D7DF3F1DF2C51484F4EC0A74AC6AC89A475AF4F79F8490E`
- [Engineering handoff ZIP](https://github.com/Vice13th/Lumenforge/releases/download/v2.0.0/LumenForge_2_0.zip) — SHA-256 `5B1F91827F3B46B0FF67F2D0EF6307D2EFDCEA2C74095E90D979054A55DA7F82`

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

`349361449982613edad854fee9f968f687cd6868040ac37651f645e25f9c5df7`

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
