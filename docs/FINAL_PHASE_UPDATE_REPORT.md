# LumenForge — Source Update and Final-Phase Qualification Report

**Report date:** 2026-10-12
**Qualification status:** `SOURCE PACKAGE QUALIFIED / NATIVE RELEASE GATES OPEN`
**Scope:** Local archive update only; no Git, remote repository, deployment, publication, or remote workflow actions were performed.

## 1. Source identity and baseline decision

The newly uploaded `lumenforge_pkg (6).zip` is the authoritative input for this update. SHA-256:

`aa25cd65b6fc6e6aac29a7c59f460f167807f700590724b3357c94a6953cd354`

The archive contains 47 ZIP entries (43 files) and passes ZIP CRC integrity validation. It represents a different project layout from the earlier `lumenroad.zip` / Phase 2 package: modular `lumenforge/` package, `lumenforge.spec`, `run_lumenforge.py`, version `12.0`, Python `>=3.10`, and PyInstaller as the declared executable builder. The previous package was a single-file `2.1.0` project with a Python `>=3.12,<3.13` declaration and Nuitka packaging. Its implementation and lockfile were therefore not copied over the new source.

Original uploaded archive bytes were left untouched. Changes were made only in the separate working tree and the resulting deliverable archive.

## 2. Changes made

- Added `README.md` for this modular source baseline: installation, launch paths, local verification commands, manifest behavior, and explicit release-evidence limitations.
- Added `tools/verify_package.py`, which checks that `SHA256SUMS.txt` is an exact inventory; it rejects missing, changed, unmanifested, duplicate, self-referential, path-traversal, drive-qualified, non-canonical, and symbolic-link entries. Cache/bytecode and generated `build`/`dist` directories are intentionally excluded.
- Added `tests/test_packaging_contract.py`, covering correct manifests, changed/missing/unmanifested files, duplicate paths, unsafe paths, and manifest self-reference.
- Added `tools/ci_smoke.py`, which runs inventory verification, syntax compilation, the unittest suite, a deterministic headless engine render sanity check, and LumenForge's built-in numerical self-tests. It writes a JSON receipt under `build/smoke-receipt/`.
- Expanded `.github/workflows/ci.yml` to define Ubuntu/Windows source-smoke jobs for Python 3.10, 3.12, and 3.13, plus a Windows PyInstaller artifact-build job. The workflow uses least-privilege `contents: read` and full-length action commit pins. This workflow configuration was **not** dispatched or executed remotely.
- Added `SHA256SUMS.txt` for the resulting source package.

No image-processing behavior, preset definitions, application UI source, or existing executable was intentionally changed.

## 3. Local verification evidence

Environment available in this session: Python `3.13.5`; NumPy `2.3.5`; Pillow `12.3.0`; pytest `9.0.2`; Linux container. OpenCV and Numba are importable here. PyInstaller, rawpy, and PyOpenColorIO are not installed; CUDA hardware/runtime was not qualified.

Observed before adding the verification harness:

- `python -m unittest discover tests -v` — **27 tests passed**, exit code 0, 2.448 seconds.
- `from lumenforge.selftest import self_tests; self_tests()` — **0 reported failures**, exit code 0.
- A syntax parse of all `lumenforge/*.py` files using `ast.parse` — no parse errors reported.

The updated manifest and smoke tool were then created for a full post-change pass. The observed final results were:

```text
python tools/verify_package.py
  PASS — exact inventory verified (48 manifest-listed files)
python -m compileall -q lumenforge tests tools
  PASS — exit 0
python -m unittest discover tests -v
  PASS — 34 tests, 0 failures, exit 0
python tools/ci_smoke.py
  PASS — package integrity, syntax compile, unit tests, deterministic render, built-in self-test; exit 0
```

The smoke render was a float32 array with shape `[32, 48, 3]`, minimum `0.0`, maximum `0.9587550163269043`, and SHA-256 `5d879627c2f4df490d8d677524241cbaad3f288b508462c38edc16ccb6701302`. The built-in numerical suite reported `0` failures. The machine-readable JSON receipt is delivered as a separate artifact at `LumenForge_FinalPhase_Smoke_Receipt.json`.

`ast.parse` also parsed the Python source modules without syntax errors, and PyYAML parsed `.github/workflows/ci.yml` with jobs `source-smoke` and `windows-portable-build`. This is configuration parsing only; it is not evidence that GitHub Actions executed successfully.

## 4. Release gates still open

This package is not declared a fully qualified native release yet. These gates require their actual target environment and remain open:

1. Windows PyInstaller build and executable hash/identity capture.
2. Launching the exact built GUI executable and checking for startup/runtime errors.
3. Relocating and launching the packaged application from a path outside the build workspace.
4. Clean Windows 10/11 machine verification, including missing runtime/DLL detection.
5. Runtime qualification of optional rawpy, PyOpenColorIO, and CUDA/CuPy paths.
6. Visual/window interaction validation on a real display; numerical smoke tests are not a substitute.
7. Confirmation of the configured GitHub Actions jobs on a real runner. They were added to the package but not remotely run.
8. No root `LICENSE` file or SPDX/project license metadata was found. Although 32 Python modules include MIT SPDX identifiers, the package should not be treated as legally complete for public distribution until the owner confirms licensing and supplies/approves the canonical license file.

The official Nuitka documentation recommends verifying standalone behavior before switching to one-file distribution; this new source package uses PyInstaller rather than that earlier Nuitka setup, so the packaging strategy must follow the current `.spec` and not stale Phase 2 instructions.

## 5. Release decision

**Decision: Source-package update accepted for local verification; native executable release remains blocked pending Windows build, launch, relocation, and clean-machine evidence.** No unsupported portability, GPU, color-management, or native UI claims are made.
