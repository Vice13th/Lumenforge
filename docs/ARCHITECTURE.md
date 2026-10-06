# Lumen Forge — Architecture

## Overview

Lumen Forge is currently organized as a single Python application file, `lumenforge.py`, with the processing engine and Tkinter desktop UI living in the same source distribution.

The code is internally segmented into explicit areas:

1. numerical utilities;
2. LUT and 3D LUT handling;
3. colour operations;
4. white balance / scene preparation;
5. preset registry;
6. skin processing;
7. importers;
8. Render Engine 12 / layered cache;
9. UI system;
10. application state and interactions;
11. self-tests.

This document describes the architecture visible in the current source. It is not a runtime architecture diagram generated from telemetry.

---

## Processing path

The staged/export path in `staged()` makes the processing order explicit:

```text
Input RGB
   │
   ▼
Camera Match
   │
   ▼
Scene Preparation
   │
   ▼
Skin tools / temperature / tint / 3D LUT
   │
   ▼
Tone + Gamma
   │
   ▼
Film Curve + User Tone Curves
   │
   ▼
Saturation / Vibrance / Density
   │
   ▼
HSL
   │
   ▼
Split Tone
   │
   ▼
Color Grade
   │
   ▼
Local Masks
   │
   ▼
Detail
   │
   ▼
Highlight Rolloff
   │
   ▼
Halation
   │
   ▼
Bloom
   │
   ▼
Vignette
   │
   ▼
Print
   │
   ▼
Grain
   │
   ▼
Clamped Output
```

This ordering matters: changing it can change the resulting image even when the individual operations remain identical.

---

## Live render engine

The `Eng.render()` path is designed for interactive editing.

It divides repeated work into cacheable layers:

```text
Camera
  ↓
WB / scene preparation / 3D LUT
  ↓
Tone
  ↓
Colour
  ↓
Effects
```

The implementation invalidates downstream layers when a relevant parameter changes instead of blindly recomputing every earlier stage.

The effects layer is intentionally kept outside the cache strategy because grain is stochastic.

### Important boundary

The comments in the source describe a performance objective for layered caching. Those comments are not a substitute for a measured benchmark.

---

## Staged/export path

`staged()` uses the same transformation sequence without interactive render caching.

That gives the project two useful properties:

- live interaction can avoid unnecessary repeated work;
- export can use the same processing math rather than a separate look-development implementation.

The project contains explicit self-tests that compare the engine and staged paths for multiple scenarios.

---

## Camera DNA

Camera DNA is a separate system layered before the application's own tone/colour/effects path.

Current source structure includes:

```text
metadata + pixel evidence
          │
          ▼
     camera ranking
          │
          ▼
confidence / basis
          │
          ▼
source → target camera character
```

The source explicitly distinguishes confidence states and avoids presenting proprietary manufacturer colour science as bit-exact technology when it is not available.

---

## Presets

Presets are represented through the `FP(...)` registry and ultimately feed the same parameter system consumed by the render engine.

Current source-level inventory:

- 121 `FP(...)` preset definitions;
- multiple families including film, cinema, mobile, vintage and modern looks;
- importable external preset/LUT formats through the importer path.

The header comment in `lumenforge.py` and older documentation contain stale inventory language in places; the registry count above is the authoritative source-level count for this snapshot.

---

## UI architecture

The desktop layer is Tkinter-based.

Major UI responsibilities include:

- preset library/search/favorites;
- command palette;
- image canvas and viewport;
- histogram;
- pipeline controls;
- Camera Match controls;
- HSL mixer;
- Tone Curves;
- crop / rotate / straighten / flip;
- local masks;
- undo/redo;
- transient render HUD/toasts.

The UI should remain a presentation and interaction layer. Image-processing correctness belongs to the processing functions and engine paths.

---

## Window chrome

The current source includes a small Windows-only DWM helper that requests dark native title-bar rendering for the main Tk window.

This affects OS-provided window chrome only.

Runtime status for this feature is currently:

**OBSERVED — source implementation present**

A fresh Windows runtime/packaged-EXE check is still required before documenting it as runtime-verified.

---

## Verification philosophy

Architecture documentation is descriptive; it is not a test certificate.

Use:

- `OBSERVED` for source inspection;
- `MEASURED` for actual benchmarks;
- `VERIFIED` for fresh test/build receipts;
- `UNVERIFIED` where runtime evidence is still missing.

