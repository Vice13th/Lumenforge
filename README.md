# Lumen Forge

> **A color-first desktop image laboratory for photographers, filmmakers, and anyone obsessed with light.**

Lumen Forge is a Python desktop photo editor built around a layered image-processing pipeline rather than a pile of disconnected sliders. The current source snapshot combines RAW-aware image loading, perceptual colour operations, film/look emulation, Camera DNA matching, local masks, 3D LUT processing, and a performance-oriented preview path in a single application.

<div align="center">

**Windows desktop** · **Python / Tkinter** · **MIT-licensed source** · **Render Engine 12.0**

</div>

---

## ✦ What Lumen Forge is

Lumen Forge treats colour as a first-class processing problem:

`source → camera interpretation → scene preparation → tone → colour → local adjustments → optical/film effects → output`

The current `main` source snapshot contains **121 built-in preset definitions** and **53 Camera DNA profiles**, counted directly from the source registries. These are source-level inventory counts, not benchmark claims.

### Core capabilities

| Area | Current implementation |
|---|---|
| Image input | Common raster formats + RAW workflow when `rawpy` is installed |
| White balance | Scene preparation, temperature/tint, gray-point and Auto WB tools |
| Tone | Exposure, contrast, gamma, highlights, shadows, whites, blacks, film curve and editable RGB curves |
| Colour | Saturation, vibrance, density, HSL mixer, split toning and colour grading |
| Camera DNA | Metadata/pixel analysis, confidence gating, camera-character transforms and mobile profiles |
| LUTs | `.cube` import with 3D LUT interpolation and adjustable strength |
| Local work | Radial, linear and brush masks with exposure/contrast/temperature/saturation/clarity controls |
| Detail / finish | Clarity, texture, dehaze, highlight roll-off, halation, bloom, vignette, print simulation and grain |
| Workflow | Non-destructive edit state, undo/redo, preset search, favorites, command palette |
| Preview | Zoom, pan, adaptive preview resolution and layered render/display caching |
| Output path | Shared processing math between live rendering and the staged/export path |

---

## 🎞️ Processing architecture

The application keeps the render pipeline explicit.

```text
IMAGE / RAW
    │
    ▼
┌───────────────────────┐
│ Camera Match          │
│ Camera DNA / profile  │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Scene Preparation     │
│ WB / skin-aware prep  │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Tone + Film Curve     │
│ Exposure / contrast /  │
│ gamma / curves        │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Colour                │
│ HSL / split / grade   │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Local + Detail        │
│ masks / clarity /     │
│ texture / dehaze      │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ Optical / Film Finish │
│ roll-off / halation / │
│ bloom / vignette /    │
│ print / grain         │
└──────────┬────────────┘
           ▼
        OUTPUT
```

The live engine uses cacheable layers for repeated interactive edits; the effects stage is intentionally not cached because grain is stochastic. The staged/export path uses the same processing sequence without the interactive cache layer.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detailed pipeline.

---

## 🧬 Camera DNA

Camera DNA is designed as a documented approximation system, not a claim of proprietary manufacturer colour science.

It can use:

- metadata-backed camera identification;
- pixel-appearance analysis;
- confidence and evidence gating;
- source-camera and target-camera matching;
- mobile-camera profiles;
- film-simulation style transforms where implemented.

When manufacturer colour science is not publicly available, Lumen Forge labels the result as an **inspired / approximate** character rather than presenting it as an official IDT or proprietary transform.

---

## 🎨 LUTs, presets, and grading

Built-in and imported looks can coexist in the same workflow.

Supported preset/LUT imports currently include:

- `.xmp`
- `.cube`
- `.json`

CUBE LUT processing is implemented through the application's **3D LUT interpolation path**. The current source uses **trilinear interpolation**; older release wording that described this as tetrahedral interpolation has been retired from the authoritative documentation.

---

## 🖥️ Run from source

### Requirements

- Python 3.10+
- Tkinter
- NumPy
- Pillow

Optional:

- `rawpy` — RAW image decoding
- `opencv-python` — optional computer-vision functionality

Install:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-optional.txt
```

Run:

```bash
python lumenforge.py
```

For packaging instructions, see [`docs/BUILD.md`](docs/BUILD.md).

---

## 📦 Windows releases

The latest published Windows x64 build is **LumenForge 2.0 — Engineering Handoff + Windows x64 Build** (tag: `handoff-2026-10-15`). This is a published handoff/build release, not a claim that every commit on `main` is represented by the executable.

- [Recommended Windows x64 ZIP](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge-2.0.0-Windows-x64.zip) — SHA-256: `5899C72FB9F5DFFBF8B1BD7E0F2F40C8C234C6B251C0934B2FB58F5B496758AA`
- [Standalone LumenForge.exe](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge.exe) — SHA-256: `23D3191DD86DCFD97D7DF3F1DF2C51484F4EC0A74AC6AC89A475AF4F79F8490E`
- [Engineering handoff ZIP](https://github.com/Vice13th/Lumenforge/releases/download/handoff-2026-10-15/LumenForge_2_0_ENGINEERING_HANDOFF.zip)

**Historical first release:** [LumenForge v1.0.0](https://github.com/Vice13th/Lumenforge/releases/tag/v1.0.0) remains available and unchanged.

Historical `LumenForge.exe` SHA-256:

```
349361449982613edad854fee9f968f687cd6868040ac37651f645e25f9c5df7
```

The 2.0 build was validated on its build host, but it is not a clean-machine certification. The release notes document the exact test results and limitations. The current `main` source and the published binary must be treated as separate artifacts unless build provenance explicitly links them.

---

## 🌓 Current development snapshot

The repository has moved significantly beyond the original binary-only public distribution surface:

```text
v1.0.0 release
    ↓
source published in main
    ↓
open-source licensing + build/security/publishing docs
    ↓
agent bootstrap + execution roadmap
    ↓
native Windows dark title-bar patch
```

The current native title-bar change is source-level implemented but is not yet a new versioned Windows release.

For an exact before/after audit, see:

**[`docs/VERSION_COMPARISON.md`](docs/VERSION_COMPARISON.md)**

---

## 📚 Documentation map

| Document | Purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Processing pipeline, live engine, preview path and design boundaries |
| [Version comparison](docs/VERSION_COMPARISON.md) | Exact `v1.0.0 → main` repository delta |
| [Build guide](docs/BUILD.md) | Source setup, development run and Windows packaging |
| [Publishing guide](docs/PUBLISHING_GUIDE.md) | Release hygiene, artifact handling and public publishing |
| [Security policy](docs/SECURITY.md) | Security scope and responsible reporting |
| [Third-party notices](docs/THIRD_PARTY_NOTICES.md) | Dependency, trademark and licensing boundaries |
| [Master roadmap](docs/LUMENFORGE_MASTER_ROADMAP.md) | Autonomous execution state and delivery gates |
| [Execution ledger](docs/AGENT_EXECUTION_LEDGER.md) | Durable evidence log for material engineering work |
| [Changelog](CHANGELOG.md) | Human-readable product history |
| [LumenForge 2.0 release notes](docs/RELEASE_NOTES_2.0.md) | Windows x64 artifact links, validation evidence, limitations and research context |

---

## 🧪 Evidence policy

Lumen Forge documentation distinguishes implementation facts from validation results.

**VERIFIED** means current evidence exists.

**OBSERVED** means the implementation or repository state was inspected.

**MEASURED** means a value came from an actual measurement or test receipt.

**UNVERIFIED** means the claim still requires runtime/device/build evidence.

No benchmark, compatibility claim, image-quality claim, performance improvement, or release status should be inferred merely from source code.

---

## 🔐 Licensing boundary

Project-owned Lumen Forge source code is released under the **MIT License**.

Third-party libraries, trademarks, camera names, assets, and externally owned technology remain subject to their own terms. See [`docs/THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md).

---

## ❤️ From obsession to open source

Lumen Forge started as a personal project built around a simple idea:

> **Colour should feel intentional, not accidental.**

It is now available as an open-source codebase so the architecture, experiments, and tools can be inspected rather than hidden behind the executable.

### Contact

GitHub: https://github.com/Vice13th

For sensitive security issues, follow [`docs/SECURITY.md`](docs/SECURITY.md).

---

> **Beyond the interface, something waits.**
>
> No button.  
> No shortcut.  
> Just type her name. Anywhere.
