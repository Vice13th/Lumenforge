# Lumen Forge — v1.0.0 → main

## Comparison basis

This document compares the published **Git tag `v1.0.0`** with the current **`main`** snapshot.

- v1.0.0 commit: `da7daecf976890942f45429bcd8b7e1e47098fc1`
- current main head: `59a4458f237e2509d0f1a761180a73e411bd66484`
- Git status: current main is **10 commits ahead**, 0 behind.
- Changed paths reported by GitHub: **13**.

This is a repository comparison, not a claim that the current source is the same binary as v1.0.0.

---

## The big change

### v1.0.0

The public repository was primarily a **release/distribution surface**.

The tag did not contain the application source file `lumenforge.py`.

The public release included the Windows executable:

`LumenForge.exe`

### Current main

The repository is now a **source-available development surface**.

The application source is present as:

`lumenforge.py`

Static source inspection of the current file reports:

- 7,295 lines;
- 18 classes;
- 107 top-level functions;
- 121 preset registry entries;
- 53 Camera DNA profile registry entries.

---

## Repository delta

| Area | v1.0.0 | Current main |
|---|---|---|
| Application source | Not present in tag | `lumenforge.py` published |
| Licensing | Release/distribution oriented | MIT source model documented |
| Build docs | Private-source guidance | Public source build workflow |
| Publishing | Binary-centric | Source + release-artifact separation |
| Security docs | Minimal proprietary-project notice | Local-input/dependency/package security scope |
| Third-party notices | Dependency notice | Expanded licensing/trademark/asset boundary |
| Agent governance | None | `AGENTS.md` + roadmap + execution ledger |
| Architecture docs | None | Added detailed processing architecture |
| Version audit | None | Added exact v1.0.0 → main comparison |
| Windows title bar | Historical v1.0.0 behavior | New dark native title-bar request in source |
| Release binary | v1.0.0 | Still historical v1.0.0 unless a new release is created |

---

## Source change after publication

The source became present on the repository before the latest documentation/bootstrap commits.

Comparing the source snapshot at commit `edd2a383034393c330d1e506843357a543720f5c` with the current source shows:

- **+30 lines**
- **+1,098 characters**

Those source additions implement the Windows native dark title-bar helper and invoke it for the main Tk window.

No other image-processing behavior was intentionally changed by that patch.

---

## Important documentation corrections

### 1. LUT terminology

The historical v1.0.0 release text used the term **tetrahedral interpolation**.

The current authoritative source contains an explicit **trilinear interpolation** implementation in the 3D LUT path.

The current documentation therefore uses **trilinear** as the source-backed term.

### 2. Preset inventory

Older text said **109 presets**, while the current source registry contains **121 `FP(...)` definitions**.

The current documentation uses 121 for the present source snapshot and avoids pretending this is a runtime benchmark.

### 3. Versioning

The public release is **v1.0.0**.

The application source identifies the render engine as **12.0**.

These are now documented as separate version layers.

### 4. Release artifact boundary

The published v1.0.0 EXE remains the historical release artifact.

A commit on `main` does not silently update that executable.

---

## Current release artifact

The v1.0.0 Windows executable has SHA-256:

`349361449982613edad854fee9f968f687cd6868040ac51f645e25f9c5df7`

The current source snapshot is not represented by that digest.

---

## Bottom line

The repository has evolved from:

```text
binary-first public distribution
          ↓
source-available application repository
          ↓
documented engineering surface
          ↓
governed autonomous-development repository
```

The largest substantive repository change since v1.0.0 is therefore **source publication and the surrounding engineering/documentation infrastructure**, while the latest functional source change is the native Windows dark title bar.

