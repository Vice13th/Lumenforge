# LumenForge V2 Integration and Runtime-Wiring Matrix

**Reviewed against:** `integration-v2` baseline `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1`, 12 October 2026.

**Historical provenance:** the source/receipt rows below were assembled during V2 recovery from the LumenParallel workspace. Original receipt test counts and source commit IDs are retained as historical evidence. They are not fresh test runs performed for this documentation update.

## Status vocabulary

- **Adapter present/tested** means a module and focused contract test are in the repository and a historical receipt records a result.
- **Runtime wired** means the active application actually imports/calls the adapter from its production render/export/control path.
- These are separate criteria. At the reviewed baseline, inspection of `source/lumenforge.py` found no import/call reference to the `source/v2_*.py` adapters. Therefore the non-launcher adapters below are **not established as runtime-wired**, even where older rows said `INTEGRATED`.

## Component matrix

| Component | V2 target file | Historical focused / aggregate receipt | Active application wiring at reviewed baseline | Remaining boundary |
|---|---|---|---|---|
| Frame / color-state contract | `source/v2_frame_contract.py` | 5 focused / 114 aggregate passed, 2 skipped at recorded stage; `V2_FRAME_CONTRACT_RECEIPT.json` | **Not wired**; current engine uses its existing array parameters | Frozen dataclass does not make its NumPy buffer immutable; supplied metadata fingerprint may become stale after in-place mutation |
| Scene-linear / graph identity | `source/v2_scene_graph_contract.py` | 5 focused / 119 aggregate passed, 2 skipped at recorded stage; `V2_SCENE_GRAPH_RECEIPT.json` | **Contract only; no executor replacement** | Deterministic identities and state guards exist; no active graph evaluation path shown |
| Cache / determinism key | `source/v2_cache_contract.py` | 4 focused / 123 aggregate passed, 2 skipped at recorded stage; `V2_CACHE_CONTRACT_RECEIPT.json` | **Not wired**; active `Eng` cache remains in `source/lumenforge.py` | New key helper does not prove production cache invalidation uses source/revision/tile/backend identity |
| OCIO bridge | `source/v2_ocio_contract.py` | 4 focused / 127 aggregate passed, 2 skipped at recorded stage; `V2_OCIO_RECEIPT.json` | **Not wired**; bridge has a CPU apply function and GPU capability reporting | Capability probe is not GPU execution; no universal backend portability claim |
| CUDA 3D LUT | `source/v2_cuda_lut.py` | 2 focused / 129 aggregate passed, 2 skipped at recorded stage; `V2_CUDA_LUT_RECEIPT.json` | **Standalone kernel; not wired**; no call from active engine | Tetrahedral GPU path vs trilinear active CPU path; edge validation and transfer-inclusive benchmark remain open |
| Native/raster export | `source/v2_export_contract.py` | 6 focused / 135 aggregate passed, 2 skipped at recorded stage; `V2_EXPORT_RECEIPT.json` | **Helpers present; app-export wiring not shown** | Optional `tifffile` / `OpenEXR`; output round-trip evidence is test-fixture scoped |
| ICC conversion | `source/v2_icc_contract.py` | 3 focused / 138 aggregate passed, 2 skipped at recorded stage; `V2_ICC_RECEIPT.json` | **Standalone utility; not wired** | Display-referred `[0,1]` input is quantized to 8-bit before conversion; no color-accuracy certification; Gate 2B remains blocked |
| Local offline AI | `source/v2_offline_ai.py` | 1 focused / 139 aggregate passed, 2 skipped at recorded stage; `V2_OFFLINE_AI_RECEIPT.json` | **Standalone adapter; no app workflow shown** | Needs ONNX Runtime, tokenizers and local model assets; deterministic/local does not establish semantic quality |
| Camera characterization | `source/v2_camera_characterization.py` | 4 focused / 143 aggregate passed, 2 skipped at recorded stage; `V2_CAMERA_CHARACTERIZATION_RECEIPT.json` | **Research utilities only** | Receipt says `infrastructure_only`; Camera Gate 2A not closed, Gate 2B blocked; no measured Fuji IDT promoted |
| Packaged launcher | root `lumenforge.py` + `source/lumenforge.py` | Historical 143 passed, 2 skipped, 2 warnings; packaged smoke receipt | **Wired** to the current `source.lumenforge.App` entry point | Release artifact is historical; clean-machine portability remains unverified |

Historical sandbox source references and staged commit IDs remain in the individual receipt JSON files and prior integration commits; this matrix deliberately does not reinterpret those values as current runtime proof.

## Latest recorded candidate evidence (historical)

- Aggregate regression: **143 passed, 2 skipped, 2 warnings in 9.63s**.
- Build environment: Windows 11 / Python 3.12.10 / PyInstaller 6.22.3.
- Recorded EXE SHA256: `C338A6830E8467CB6874B63A0389BF7A4A99758A5D9CD9042DBB2F94617A9E7B`.
- Distribution: 1,128 files / 349,868,017 bytes.
- Packaged GUI smoke: reported alive for 8 seconds with title `Lumen Forge - v2`, then clean termination.
- Optional Numba `tbb12.dll` packaging warning remained.

These outcomes describe the recorded candidate/environment. The 12 October documentation change did not rerun the tests or rebuild the artifact.

## Required to change an adapter to “runtime wired”

1. Name the production caller and the seam where the adapter is selected.
2. Prove active UI/engine calls reach the adapter on a representative image.
3. Define dependency missing/device unavailable/error fallback behavior.
4. Add application-level tests and current CPU/reference comparisons for the chosen behavior.
5. Record a fresh hardware/runtime receipt and transfer-inclusive benchmark where performance is claimed.
6. Update the status only after those checks are attached to the exact commit.
