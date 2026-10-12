# V2 dependency matrix

> This is a source-inspected matrix for `integration-v2` at `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1`, reviewed 12 October 2026. It is not proof that every package is installed or that every adapter is wired into the app.

## Declared project environment

| Source | Declared dependencies | Interpretation |
|---|---|---|
| `pyproject.toml` project | Python `>=3.12,<3.13`; `numpy==2.5.3`; `pillow==11.3.0`; `numba==0.67.0`; `rawpy==0.27.1`; `opencv-python==4.10.0.84` | Declared direct project dependencies for the reviewed V2 tree |
| `pyproject.toml` dev group | `pytest==9.1.1`; `pyinstaller==6.22.3`; `nuitka>=4.2.2` | Development/test/packaging tools |
| `uv.lock` | Present | Lock file is the resolution artifact; its presence alone is not evidence that a clean install succeeded |
| `docs/requirements.txt` | Loose NumPy/Pillow/Numba/rawpy/OpenCV/OpenColorIO notes | Legacy compatibility list, not a full V2 lock/install recipe |

## Adapter-specific imports not declared by the project dependency list

| Adapter/feature | Observed imports | Documentation boundary |
|---|---|---|
| CUDA 3D LUT | `cupy` | Requires a compatible CuPy/CUDA/device combination. The historical receipt is limited to the recorded RTX 2070 Max-Q environment. |
| Native/raster export | `tifffile`, `OpenEXR`, plus Pillow | Export helpers may fail at call time if the optional writer library is absent. No universal availability claim. |
| Local text embeddings | `onnxruntime`, `tokenizers`, a local ONNX model and tokenizer files | Local-only adapter; model files are runtime assets, not implied by installing the Python package. |
| OCIO processing | `PyOpenColorIO` | Optional runtime import; `v2_ocio_contract.py` exposes CPU application and capability reporting, not GPU execution. |
| ICC conversion | Pillow `ImageCms` | Uses Pillow, but the current adapter converts through 8-bit RGB. |

## Known metadata mismatch

- `pyproject.toml` names `opencv-python`; `docs/requirements.txt` names `opencv-python-headless`. Do not install both blindly or assume they are interchangeable packaging choices.
- The V2 tree does not contain the root `requirements.txt` referenced by older docs.
- The reviewed V2 tree does not contain `.github/workflows/tests.yml`, despite older documentation describing that workflow.
- Adapter files are imported dynamically or directly by focused tests; their source presence does not guarantee dependencies or runtime integration.

## Installation and verification policy

1. Treat `pyproject.toml` and `uv.lock` as the declared V2 project metadata; do not treat `docs/requirements.txt` as a complete locked environment.
2. Define adapter-specific optional extras or a documented environment recipe before promising that a feature works on a fresh machine.
3. Verify a clean install and the exact optional backend on the target platform.
4. Record Python, OS, GPU, driver, CUDA/CuPy version, package versions, test command, exit code and artifact hashes with each relevant receipt.
5. Do not promote the recorded 8 October test/packaging result into fresh evidence for a different commit.
