# LumenForge 12.0 — Modular Desktop Application

LumenForge is a Tkinter desktop photo editor with a numerical image-processing engine and film-emulation preset library. This source package is the modular `lumenforge/` version, distinct from earlier single-file 2.x packages.

## Run from source

Requirements: Python 3.10 or newer, NumPy, and Pillow.

```bash
python -m pip install numpy Pillow
python -m lumenforge
# or
python run_lumenforge.py
```

Optional integrations are declared in `pyproject.toml`: OpenCV/Numba (`fast`) and rawpy (`raw`). They must be tested on their target runtime before being claimed as release-qualified.

## Local verification

```bash
python tools/verify_package.py
python -m compileall -q lumenforge tests tools
python -m unittest discover tests -v
python tools/ci_smoke.py
```

`tools/verify_package.py` treats `SHA256SUMS.txt` as an exact inventory of package files and rejects missing, modified, unmanifested, duplicate, or unsafe paths. Regenerate after intentional source changes with:

```bash
python tools/verify_package.py --write-manifest
```

The smoke command runs package integrity, syntax compilation, unit tests, a deterministic headless render, and the application's built-in numerical self-tests. It writes a machine-readable receipt under `build/smoke-receipt/`.

## Release evidence boundaries

Passing source tests does not prove that a PyInstaller executable builds, launches, or works on a clean Windows machine. Windows packaging, executable launch/runtime, optional integrations (CUDA, OpenColorIO, rawpy), installer/portable-bundle relocation, and clean-machine tests remain separate release gates until executed and recorded on their intended hosts.

## Package provenance

The input archive for the current package update is `lumenforge_pkg (6).zip`, SHA-256:

`aa25cd65b6fc6e6aac29a7c59f460f167807f700590724b3357c94a6953cd354`

The uploaded source ZIP is retained unchanged. The current package has its own generated `SHA256SUMS.txt`; this is not an upstream or signed publisher manifest.
