# Build / Private Development

## Public repository policy

The public GitHub repository is intentionally **source-free**. Do not commit the proprietary Python source, private development assets, internal test fixtures, or unpublished processing data.

The private source package is maintained separately by the project owner.

## Private source requirements

Required:

- Python 3.10+
- NumPy
- Pillow

Optional:

- OpenCV (`opencv-python`)
- rawpy

Example setup:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-optional.txt
```

Run the private source build with:

```bash
python src/lumenforge.py
```

For a Windows executable, PyInstaller can be used by the project owner or an authorized distributor:

```bash
pyinstaller --onefile --noconsole --name LumenForge --icon=src/lumenforge.ico src/lumenforge.py
```

The public repository includes the authorized release executable at `dist/LumenForge.exe`. The proprietary source remains outside the public repository.

For ordinary users, no build step is required: run the executable from `dist/`.

The included executable was built with PyInstaller 6.22.0 on Windows 10 / Python 3.11.9.
