# LumenForge v2 Architecture

> **Evidence baseline:** branch `integration-v2`, commit `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1` (8 October 2026). This page records source-observed architecture, not a claim that every adapter is connected to the running application. Reviewed 12 October 2026 by direct GitHub source inspection; tests were not rerun for this documentation pass.

## 1. Application entry point and active engine

The repository has a thin root launcher and a large active application module:

- `lumenforge.py` adds the repository root to `sys.path`, imports from `source.lumenforge`, and launches `source.lumenforge.App().mainloop()`.
- `source/lumenforge.py` contains the Tkinter application, rendering helpers, the interactive `Eng` engine, and the non-cached `staged(rgb, params, ...)` render path. At the evidence baseline it is approximately 9,282 lines.
- The active engine is NumPy-based. Selected operations have optional Numba acceleration with a NumPy-compatible path. This is not equivalent to a CUDA-resident image-processing pipeline.
- Interactive rendering reaches `ENG.render(...)` through the application render path. The `Eng.render` implementation has its own layer cache and uses the in-file CPU 3D-LUT implementation when `lut3d_path` is configured.

Do not treat `lumenforge.py` at repository root as the full engine; it is now a compatibility/launch wrapper.

## 2. Current render path and LUT semantics

The active source contains two relevant LUT paths:

1. `LUT.apply(rgb, lut)` applies a cached **1D** lookup table.
2. `get_lut3d(path)` parses and caches a `.cube` 3D lattice. The in-file `apply_lut3d(rgb, lut3d)` performs vectorized **trilinear interpolation**, uses an effective minimum domain span of `1e-6`, and clips the resulting RGB values into `[0, 1]`.

The active `Eng.render` path applies this in-file CPU 3D LUT during its white-balance/scene-preparation layer. The `staged(...)` function includes a non-cached equivalent LUT stage for export-style rendering. This is the observed production-source behavior at the evidence baseline.

The standalone CUDA adapter instead implements **tetrahedral interpolation**. These interpolation methods are not interchangeable by definition. Before replacing the active path, the project must explicitly decide whether the intended behavior is to preserve current trilinear results or intentionally change the rendering contract.

## 3. V2 contract and adapter modules

The V2 branch contains the modules below. Their presence and focused tests are real; that fact alone does not mean the active application calls them.

| Module | Source-observed role | Runtime status at the evidence baseline |
|---|---|---|
| `source/v2_frame_contract.py` | `V2Frame`, color-state/pixel-format enums, metadata, revision and fingerprint helpers, input validation | Standalone contract; no import/call found in `source/lumenforge.py` |
| `source/v2_scene_graph_contract.py` | Scene-linear validation, node identity and deterministic graph-key descriptors | Contract/key bridge only; no graph executor replacement |
| `source/v2_cache_contract.py` | Canonical parameter digest and cache-key helper using source, revision, tile, quality, color-state and backend values | Helper only; the existing `Eng` cache remains in the active engine |
| `source/v2_cuda_lut.py` | Optional CuPy RawKernel for tetrahedral 3D-LUT application; availability/device reporting | Standalone callable; not selected or called by the active render pipeline |
| `source/v2_export_contract.py` | TIFF, EXR, PNG and JPEG write/inspection helpers with explicit color-state guards | Standalone helpers; app-export wiring is not established by source references |
| `source/v2_icc_contract.py` | Explicit Pillow/ImageCms display-referred profile conversion | Standalone conversion primitive; current implementation quantizes input to 8-bit RGB |
| `source/v2_ocio_contract.py` | OCIO config/processor discovery, CPU RGB application, CPU/GPU capability reporting | Standalone bridge; capability detection is not GPU execution |
| `source/v2_offline_ai.py` | Local ONNX sentence-embedding wrapper with model/tokenizer hashes in a receipt | Standalone local inference adapter; no application workflow integration found |
| `source/v2_camera_characterization.py` | RGB-to-XYZ fit helpers, CIEDE2000 metrics, train/holdout receipts | Research infrastructure; not a measured camera profile or production IDT |

### Runtime-wiring finding

At the evidence baseline, direct inspection of `source/lumenforge.py` found the CPU `ComputeBackend` / `CPUBackend` boundary and `render_stage_reference`, but no references to `v2_cuda_lut`, `tetrahedral_cuda`, CuPy, or CUDA/GPU selection. The V2 adapter modules therefore must be described as **present and separately testable, but not yet wired into the active app render path**. See [the 12 October review](V2_ARCHITECTURE_REVIEW_2026-10-12.md) and [the integration matrix](../verification/V2_INTEGRATION_MATRIX.md).

## 4. CUDA LUT adapter contract and unresolved edge conditions

The current function signature is `tetrahedral_cuda(rgb, lut3d)`, where `lut3d` is a tuple of table, domain-min RGB triple and domain-max RGB triple. The table is expected to be a cubic `N × N × N × 3` lattice.

The adapter currently:
- casts the image input to NumPy float32;
- validates a basic image shape, cubic LUT shape and 3-value domain bounds;
- transfers the flattened image and table to CuPy arrays;
- launches a RawKernel, synchronizes the null stream, then copies the result back to NumPy.

The following contracts are not yet strong enough for production integration:

- No guard ensures every `domain_max[c] > domain_min[c]`; the CUDA kernel divides directly by the span.
- The function does not explicitly reject NaN/infinite input, non-finite LUT samples or an empty image before launching the kernel.
- The image is cast to float32, but the table is not explicitly normalized to a validated contiguous float32 array at the public function boundary. The current parser produces float32, but callers can supply the tuple directly.
- The CUDA kernel does not clip output values to `[0, 1]`, whereas the active trilinear path does. This is a behavioral difference that needs an intentional color/headroom decision.
- The current focused CPU reference in `tests/test_v2_cuda_lut.py` is a separate tetrahedral implementation. It does not prove equivalence to the active in-file trilinear production path.
- A call transfers input and LUT to the device and synchronizes before returning. No end-to-end performance claim follows from kernel parity alone.

These are documentation of observed code boundaries, not assertions that an invalid result has already occurred in the release artifact.

## 5. Frame identity, cache and color-state caveats

- `V2Frame` is a frozen dataclass, but its NumPy array remains mutable. The constructor validates finiteness once; it cannot prevent later in-place array mutation.
- `V2Frame.source_fingerprint()` returns `metadata.source_fingerprint` when that value is supplied, instead of hashing the current pixel buffer. If the array is mutated without revising metadata/revision, the reported identity can become stale.
- `v2_scene_graph_contract` hashes the declared color-space state, frame revision/fingerprint and node identities. It is a deterministic identity contract, not an executor.
- `v2_cache_contract.cache_contract_key` includes source identity, node/upstream revisions, tile, quality, color state and backend. Its presence does not mean the active render cache uses that key; the current `Eng` cache is implemented separately in `source/lumenforge.py`.
- `v2_icc_contract.convert_display_referred_rgb` requires display-referred RGB in `[0,1]`, converts via an 8-bit Pillow image, then returns float32 values derived from that 8-bit output. It is not a high-bit-depth/scene-linear-preserving transform.
- `v2_ocio_contract` exposes `cpu_apply_rgb`; GPU processor capability reporting does not implement a GPU apply path.
- Camera characterization receipts are explicitly `infrastructure_only`; measured camera data and scientific acceptance gates remain separate requirements.

## 6. Dependencies and packaging boundary

The project metadata in `pyproject.toml` declares Python `>=3.12,<3.13`, NumPy, Pillow, Numba, rawpy and OpenCV, plus developer tools. The V2 adapters additionally import packages such as CuPy, tifffile, OpenEXR, ONNX Runtime, tokenizers and optionally PyOpenColorIO. Those imports are not all declared in the project dependency list.

`docs/requirements.txt` is a legacy compatibility list, not a lock file or complete V2 installation manifest; it also names `opencv-python-headless`, whereas `pyproject.toml` names `opencv-python`. See [the dependency matrix](DEPENDENCY_MATRIX.md). A successful import/test run in one equipped workspace does not establish clean-machine portability.

## 7. Evidence and release status

The V2 receipt files record a Windows 11 / Python 3.12.10 / PyInstaller 6.22.3 candidate, a packaged startup smoke test, and an aggregate test result of 143 passed, 2 skipped and 2 warnings on 8 October 2026. Those are historical receipts from that environment, not tests rerun by this documentation review.

Still open in the recorded handoff:
- Camera Gate 2A: not closed.
- Camera Gate 2B: blocked.
- EXIF/XMP certification: blocked.
- Clean-machine portability: unverified.
- Universal GPU/backend portability: not claimed.
- Optional Numba `tbb12.dll` packaging warning: still recorded.

The GitHub compare endpoint reports no common ancestor between `main` and `integration-v2`. Do not assume a safe merge or fast-forward path between those lines without an explicit reconciliation plan. The separate toolbar patch based on `main` is not evidence of V2 architecture integration.

## 8. Next engineering sequence

1. Choose and document the canonical 3D-LUT interpolation/output-range contract.
2. Harden CUDA input/domain validation and add negative/empty/non-finite tests.
3. Introduce one explicit backend selection seam in the active render engine, preserving CPU as reference and fallback; do not add a second disconnected pipeline.
4. Test actual production-call parity over deterministic images/LUTs, edge values, domains, and image dimensions on CPU and a CUDA-equipped runner.
5. Benchmark complete calls including transfers/synchronization at multiple image sizes; report both latency and numerical error.
6. Resolve frame immutability/fingerprint behavior and ensure the active cache invalidation uses a content/revision contract.
7. Wire export/ICC/OCIO/AI adapters only through deliberate production seams and add application-level tests.
8. Update the release gates only from new receipts; keep camera science, EXIF/XMP and clean-machine gates open until directly evidenced.
