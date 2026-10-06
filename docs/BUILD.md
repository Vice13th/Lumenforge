# Building Lumen Forge

This guide covers the **current source tree on `main`**.

The published `v1.0.0` executable is a release artifact. It is not regenerated automatically from every commit on `main`.

---

## 1. Environment

### Required

- Python 3.10 or newer
- Tkinter
- NumPy
- Pillow

### Optional

- `rawpy` — RAW image decoding
- `opencv-python` — optional computer-vision features

The repository declares the core dependencies in `requirements.txt` and optional dependencies in `requirements-optional.txt`.

---

## 2. Recommended setup

Windows:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -r requirements-optional.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install -r requirements-optional.txt
```

---

## 3. Run from source

```bash
python lumenforge.py
```

Lumen Forge uses Tkinter for the desktop UI. On systems where Tkinter is packaged separately from Python, install the platform's Tk package before launching.

---

## 4. Windows executable

The application can be packaged with PyInstaller.

```bash
python -m pip install pyinstaller
pyinstaller --onefile --noconsole --name "LumenForge" lumenforge.py
```

The resulting executable is a **new build** and must not be described as an official release until it has passed the project's relevant validation gates.

The historical `v1.0.0` Windows binary is distributed from GitHub Releases and is intentionally not treated as an automatically updated build.

---

## 5. Validation before publishing

At minimum:

1. start the application from a clean environment;
2. open representative raster and RAW inputs where optional dependencies are installed;
3. exercise the main colour pipeline;
4. test imported `.cube`, `.xmp` and `.json` workflows as applicable;
5. verify undo/redo and viewport interactions;
6. run the built-in self-test path;
7. package the Windows executable;
8. launch the packaged executable;
9. record fresh evidence in the execution ledger.

Do not replace a failed check with a source-level assumption.

---

## 6. Release discipline

Use the following distinction:

```text
source on main
    ≠
tested build
    ≠
published release
```

Each stage needs its own evidence.

For release hygiene, see [`docs/PUBLISHING_GUIDE.md`](PUBLISHING_GUIDE.md).

