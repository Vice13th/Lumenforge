# LumenForge 2.0 — Windows x64 Build & Engineering Handoff

**Release tag:** `handoff-2026-10-15`  
**Release type:** Windows x64 build and engineering handoff  
**Historical baseline:** `v1.0.0` remains available and unchanged  
**Application engine label:** Render Engine 12.0

LumenForge is a color-first desktop image editor organized around an explicit image-processing pipeline. This release makes a Windows x64 build and an engineering handoff package available alongside a more inspectable source repository and expanded engineering documentation.

> **Artifact boundary:** this release does not claim that the binary was built from a particular committed source SHA. The recovered source snapshot's ancestry to the public `v1.0.0` commit has not been established.

## Downloads

- [Recommended Windows x64 ZIP](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge-2.0.0-Windows-x64.zip)  
  SHA-256: `5899C72FB9F5DFFBF8B1BD7E0F2F40C8C234C6B251C0934B2FB58F5B496758AA`
- [Standalone Windows executable](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge.exe)  
  SHA-256: `23D3191DD86DCFD97D7DF3F1DF2C51484F4EC0A74AC6AC89A475AF4F79F8490E`
- [Engineering handoff ZIP](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge_2_0_ENGINEERING_HANDOFF.zip)  
  SHA-256: `5B1F91827F3B46B0FF67F2D0EF6307D2EFDCEA2C74095E90D979054A55DA7F82`
- [Historical v1.0.0 release](https://github.com/Vice13th/Lumenforge/releases/tag/v1.0.0) — preserved as a separate release.

## What is available in the current source snapshot

These capabilities are documented in the current source; this list is not a claim that every item is new in 2.0 or that every optional dependency is bundled in the EXE.

- Layered processing flow for camera matching, scene preparation/white balance, tone and curves, color, local masks, detail and optical/film finishing.
- Camera DNA matching based on metadata and pixel evidence, with confidence gating. Where proprietary manufacturer transforms are unavailable, results are approximate or inspired rather than official camera IDTs.
- 3D `.cube` LUT processing using **trilinear interpolation** in the current source.
- HSL mixing, split toning, color grading, editable RGB curves, exposure and tone controls.
- Radial, linear and brush local masks.
- Presets and imported looks; current source inventory is **121 built-in preset definitions** and **53 Camera DNA profiles**. These are static registry counts, not quality or performance measurements.
- Preview viewport controls, adaptive preview resolution, layered render/display caching, undo/redo, preset search/favorites and a command palette.
- A staged/export path that follows the same processing sequence as the live renderer without using the interactive cache.

The architecture documentation describes caching as an optimization design; it does not substitute for a measured performance benchmark. The effects layer is intentionally outside the cache strategy because grain is stochastic.

## What changed around the project since v1.0.0

The repository comparison identifies the largest verified change as the move from a release-oriented distribution surface to a source-available project with the application source, MIT licensing, source build instructions, publishing controls, security guidance, third-party notices, architecture documentation, version comparison, roadmap and execution ledger.

The latest functional source patch identified in the repository comparison is a Windows-native dark title-bar request for the main Tk window. It is **source-observed, not runtime-verified**; this release does not claim that the packaged EXE visibly applies the title-bar change.

Other capabilities listed above are part of the current source inventory and must not automatically be presented as newly introduced in this release.

## Validation evidence

The release record reports:

- Clean CPython 3.12.10 virtual environment.
- Core dependencies pinned to NumPy 2.5.4 and Pillow 12.3.0.
- PyInstaller 6.22.3 clean build (`--clean`) passed.
- Test suite: **129 passed, 7 skipped, 32 subtests passed**.
- Ruff: all checks passed.
- Executable startup smoke test: the process remained alive for 8 seconds, then the test harness stopped it.
- ZIP extraction and embedded executable SHA-256 equality passed.

### Limits and unverified areas

- This is build-host verification, **not clean-machine certification**.
- A full open/edit/export workflow was not exhaustively tested on a separate Windows installation.
- Optional RAW/HEIF and acceleration integrations are not guaranteed to be bundled.
- Exact source ancestry between the recovered build snapshot and the public `v1.0.0` commit is not established.
- No performance benchmark or image-quality superiority claim is made here.
- The native dark title-bar change still needs a fresh Windows runtime/packaged-EXE visual check.

## Color perception and interface design: evidence, not marketing

Human visual attention is sensitive to color, but its effects depend on the task, the particular colors, and the surrounding display. Research on attentional guidance by individual colors in complex displays supports treating color choices as context-dependent rather than assuming every hue has a universal attention effect. Research on attention affordances in complex visual interfaces similarly examines how interface design can guide visual search.

For LumenForge, the defensible product implication is modest: a consistent visual hierarchy and carefully differentiated controls can help users locate and interpret editing tools. These studies do **not** establish that LumenForge improves cognition, brain performance, mental health, or photographic outcomes. No neuroscience or clinical validation of LumenForge is claimed.

Selected peer-reviewed references:
- Wolfe, J. M. et al. (2019), “The attentional guidance of individual colours in increasingly complex displays,” *Applied Ergonomics*. https://doi.org/10.1016/j.apergo.2019.102885
- “Attention affordances: Applying attention theory to the design of complex visual interfaces” (2021), *Journal of Experimental Psychology: Applied*. https://doi.org/10.1037/xap0000349

## Recommended next verification gates

1. Run a clean-machine installation and launch test on a separate supported Windows environment.
2. Exercise the complete open → edit → export path with representative raster inputs; test RAW/HEIF only where the optional decoders are actually installed.
3. Verify the packaged EXE's title-bar appearance and capture reproducible runtime evidence.
4. Publish a reproducible source-to-binary provenance record tied to an exact commit.
5. Measure preview latency and export throughput using a documented image set and repeatable method before making performance claims.

**Color should feel intentional, and the engineering behind it should be inspectable.**
