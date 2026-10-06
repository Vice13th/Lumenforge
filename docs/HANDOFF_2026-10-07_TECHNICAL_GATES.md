# LumenForge — Technical Gates Handoff — 2026-10-07

## Canonical State

- Repository: `Vice13th/Lumenforge`
- Source branch: `main`
- Base commit inspected: `78967c97546ae7e0231a37f239b4215c78ff81c7`
- Public distribution release: `v1.0.0`
- Current source/render-engine version: `12.0`
- Current `main` is a newer development snapshot than the published v1.0.0 executable.

## Evidence Contract

Use: `VERIFIED`, `OBSERVED`, `MEASURED`, `USER-ASSERTED`, `UNVERIFIED`, `BLOCKED`, `FAILED`.

**NO RECEIPT → NO EPISTEMIC UPGRADE.**

Chat history and owner reports must not be promoted to repository truth without a durable receipt.

---

# Technical Gates

## A — Correctness & Stability

### Goal
Protect numerical/image-processing correctness and detect regressions in the current main snapshot.

### Acceptance
- Current built-in self-test passes.
- Representative raster and RAW workflows open/render correctly.
- Main colour pipeline produces finite, valid-range output.
- Undo/redo and preset/import paths remain correct.
- Live render and staged/export paths remain aligned.
- No reproducible crash, invalid-array, or runaway-memory defect.

### Current state
- Self-test path exists in source: **OBSERVED**.
- Current-main self-test receipt in repository: **UNVERIFIED**.
- Owner-reported clean-environment result of 65 passed / 2 skipped / 4767 warnings: **USER-ASSERTED** until exact command/environment/output is persisted.

### Next receipt
Run the exact current-main self-test and preserve interpreter, dependency versions, command, exit code, counts, and warnings.

---

## B — UI / Windows Runtime

### Goal
Prove the desktop UI and native Windows chrome work in the real runtime, not only in source.

### Acceptance
- Source launch works.
- Packaged EXE launches.
- Windows dark title bar is actually visible.
- Native minimize/maximize/close remain functional.
- Viewport, zoom, crop, rotate, masks, command palette and undo/redo remain responsive.
- Visual system matches the approved dark photographer-first direction.

### Current state
- Dark title-bar implementation exists: **OBSERVED**.
- Packaged-EXE visual verification of the title bar: **UNVERIFIED**.
- Visual/design handoff contracts are already present.

### Next receipt
Build current main, launch the actual EXE on Windows, inspect title bar and key interactions, and record runtime evidence.

---

## C — Colour Science / Render Integrity

### Goal
Keep the render math stable and prevent silent look changes during optimization or UI work.

### Protected processing order

```text
Input
→ Camera Match
→ Scene Preparation
→ Skin / WB / 3D LUT
→ Tone + Gamma
→ Film Curve + Curves
→ Saturation / Vibrance / Density
→ HSL
→ Split Tone
→ Color Grade
→ Local Masks
→ Detail
→ Highlight Rolloff
→ Halation
→ Bloom
→ Vignette
→ Print
→ Grain
→ Clamped Output
```

### Acceptance
- Processing order remains deliberate and regression-tested.
- Live and staged/export paths stay mathematically aligned.
- Numeric output remains finite and bounded.
- Camera DNA exposes confidence/evidence honestly.
- Approximate camera character is never presented as proprietary manufacturer science.
- LUT terminology remains consistent with implementation; current documentation says CUBE processing uses trilinear interpolation.

### Current state
- Architecture contract: **OBSERVED**.
- Independent image-quality accuracy benchmark: **UNVERIFIED**.
- Live-vs-staged parity remains a release gate.

### Next receipt
Use representative image fixtures and deterministic tolerances for parity tests, excluding or normalizing stochastic grain where required.

---

## D — Performance / Acceleration

### Goal
Replace optimization assumptions with measured evidence and preserve safe CPU fallback.

### Acceptance
- Preview latency measured on representative image sizes.
- Large-image memory behavior measured.
- Layered cache invalidation validated.
- No unnecessary full-pipeline recomputation.
- Acceleration used only when actually available.
- CPU fallback remains correct.
- Long interactive sessions do not retain unbounded stale state.
- Packaging preserves required runtime dependencies.

### Current state
- Layered cache strategy exists: **OBSERVED**.
- Performance baseline in repository: **UNVERIFIED**.
- Owner-reported CPU/GPU validation: **USER-ASSERTED** until a durable receipt is stored.
- Owner-reported hardware context includes RTX 2070 Max-Q 8 GB + i7-10750H; this is environment context, not a universal compatibility claim.

### Recent environment reported by owner
- Python 3.12.10
- NumPy 2.5.3
- Pillow 11.3.0
- OpenCV 4.10.0.84
- rawpy 0.27.1
- Numba 0.67.0
- llvmlite 0.49.0
- PyInstaller 6.22.x

OpenCV 5 was rejected after regression testing; OpenCV 4.10.0.84 is the accepted owner-reported compatibility baseline.

These version/results are **USER-ASSERTED** here unless the exact receipt is added to the repository.

### Next receipt
Record image size, operation set, warm/cold cache state, preview timing, peak memory, CPU/GPU path, fallback path, repetitions, and exact environment.

---

## E — Packaging / Release Integrity

### Goal
Maintain strict provenance between source, tested build, packaged executable, and public release.

```text
source on main
    ≠
tested build
    ≠
packaged EXE
    ≠
published release
```

### Acceptance
- Clean environment reproduces the build.
- PyInstaller package succeeds.
- Packaged EXE launches.
- Key workflows work in the packaged artifact.
- Exact artifact hash recorded.
- Release notes identify the source commit used.
- No generated EXE is accidentally committed.
- Historical v1.0.0 remains the historical release artifact.

### Current state
- PyInstaller is supported.
- v1.0.0 is a historical release artifact.
- Current-main packaged EXE build + launch: **UNVERIFIED** in current repository evidence.

### Next receipt
Produce a clean current-main EXE, record toolchain/build/hash, launch it, exercise key flows, and only then consider a new release candidate.

---

## F — Security / Supply Chain / Licensing

### Goal
Prevent malformed inputs, dependency risk, and redistribution problems from reaching a public build.

### Acceptance
- Review image/LUT/preset import boundaries.
- Review dependency versions/advisories.
- Review bundled assets and licenses.
- Keep LICENSE, SECURITY and THIRD_PARTY_NOTICES accurate.
- No secrets, private datasets, internal fixtures or development archives in releases.
- Fonts, LUTs, IDTs, images and other third-party assets are redistributable.
- Packaged contents are inspected before publication.

### Current state
- Security and third-party notice docs exist: **OBSERVED**.
- Fresh dependency/security audit for the next release: **UNVERIFIED**.
- Fresh packaged-content supply-chain/license inspection: **UNVERIFIED**.

### Next receipt
Run focused security/dependency review for the exact release environment and inspect the final package contents.

---

# Release Readiness

A new public release requires a current evidence chain:

```text
SOURCE
→ SELF-TEST
→ RUNTIME
→ BUILD
→ EXE LAUNCH
→ PERFORMANCE
→ SECURITY / LICENSE
→ HASH
→ RELEASE
→ DOCUMENT
```

Current blockers for a new main-derived release:

1. Current-main self-test receipt.
2. Current packaged EXE build + launch receipt.
3. Measured performance baseline.
4. Runtime verification of the Windows dark title bar.
5. Fresh security/supply-chain review.
6. Exact artifact hash + source-commit provenance.

## Important boundary

The public v1.0.0 executable must not be treated as representing current main. New main commits require their own build, test, package, verification and release evidence.

## Working rule

```text
INSPECT
→ RECONCILE
→ BASELINE
→ IMPLEMENT
→ TEST
→ BUILD/PACKAGE
→ VERIFY
→ DOCUMENT
→ NEXT GATE
```

Do not loop on identical failures. Preserve the receipt and move to a materially different valid method or mark the gate FAILED/BLOCKED.
