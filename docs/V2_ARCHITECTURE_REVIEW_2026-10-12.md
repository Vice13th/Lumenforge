# V2 architecture and documentation review — 12 October 2026

## Executive finding

**Assessment: PARTIAL — substantive V2 adapter code exists, but production runtime wiring and several contracts remain unverified.**

This review is based on direct inspection of files served by GitHub at `integration-v2` HEAD `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1`. It is not a fresh execution of the tests, a GPU benchmark, a release audit, or an inspection of unpushed local files. The review changes documentation only.

## Evidence baseline

| Item | Observed |
|---|---|
| V2 branch head | `033e8e48b82fa50efaeda304071b0f6b5c8a0ac1` |
| V2 source engine blob | `source/lumenforge.py`, blob `db753fdcbcfede29ef67f94bce96310e8f4c34b6`, 9,282 lines |
| Root launcher | `lumenforge.py` imports `source.lumenforge` |
| CUDA adapter | `source/v2_cuda_lut.py` contains `tetrahedral_cuda` and a CuPy RawKernel |
| Focused CUDA test | `tests/test_v2_cuda_lut.py` tests availability and CPU-reference parity when CUDA is available |
| Historical CUDA receipt | dated 8 October 2026; names an RTX 2070 Max-Q / CUDA runtime 12090 test environment |
| Latest recorded aggregate suite | 143 passed, 2 skipped, 2 warnings, 9.63s in the receipt/matrix |
| Fresh tests in this review | Not run |

## Findings

### P1 — CUDA adapter is not wired to the production render path

**Evidence:** Direct source inspection of `source/lumenforge.py` finds the `ComputeBackend`, `CPUBackend` and `render_stage_reference` definitions. It contains no import/call references to `v2_cuda_lut`, `tetrahedral_cuda`, CuPy or CUDA/GPU selection. The active `Eng.render` and `staged(...)` 3D-LUT stages call the in-file `apply_lut3d`.

**Impact:** Presence of a CUDA kernel and passing focused adapter test do not establish that opening/editing/exporting an image in the application uses the GPU. No user-facing GPU acceleration claim is supported by this branch snapshot.

**Required next evidence:** a single explicit active-engine backend seam, a call trace proving the selected backend is reached by a real render, CPU fallback tests, and end-to-end CPU/GPU output comparison on deterministic inputs.

### P1 — Production CPU LUT and CUDA LUT use different interpolation contracts

**Evidence:** Active `apply_lut3d` is vectorized trilinear interpolation and clips output to `[0,1]`. `tetrahedral_cuda` uses tetrahedral interpolation and does not clip output. The focused test's `cpu_tetrahedral` helper independently mirrors the tetrahedral algorithm; it does not compare CUDA output against the active trilinear implementation.

**Impact:** Existing test evidence can establish the kernel's agreement with its tetrahedral reference within the tested tolerance, but not pixel equivalence to the current app path. Changing algorithms may legitimately change pixels; that needs an explicit rendering decision, not an implicit backend swap.

**Required next evidence:** define interpolation, domain normalization, output range and scene-headroom semantics; include known reference LUTs and independent boundary vectors; compare through the actual engine interface.

### P1 — CUDA input/domain validation is incomplete at the public function boundary

**Evidence:** The kernel divides by `domain_max - domain_min` without a per-channel positive-span check. The public function validates the shapes of the domain arrays but does not explicitly validate their finiteness/order, image/LUT finiteness, or empty-image behavior. It casts the image to float32 but does not explicitly normalize and validate the table dtype before passing it to a `float*` kernel.

**Impact:** Degenerate domains, non-finite values, empty arrays or unexpected caller-provided table dtypes may produce invalid results or launch/runtime errors instead of a deterministic contract error.

**Required next evidence:** reject or define each boundary case and add tests for zero/negative domain spans, NaN/Inf, empty images, non-float32 LUT input, LUT sizes of two and larger, and out-of-domain pixel values.

### P2 — CUDA parity receipt is not a performance receipt

**Evidence:** The adapter transfers flattened image and LUT arrays to CuPy, launches the kernel, synchronizes the null stream and copies output back to host. The existing receipt reports numerical parity on a single recorded RTX 2070 Max-Q environment, with the 17³ LUT and 96×113 probe. It does not record complete active-app CPU-vs-GPU end-to-end latency.

**Impact:** The numerical result is useful but does not prove acceleration at practical image sizes. Transfer and synchronization cost can dominate small workloads.

**Required next evidence:** benchmark active-path calls at several image sizes and LUT dimensions; report cold/warm setup separately, transfer-inclusive latency, throughput, memory use and numerical error, with CPU and GPU running the same declared algorithm.

### P2 — V2 frame/cache identity can become stale after in-place mutation

**Evidence:** `V2Frame` is frozen as a dataclass, but `data` is a mutable NumPy array. Initial finiteness checks occur in `__post_init__`; they cannot prevent or revalidate subsequent in-place mutation. `source_fingerprint()` trusts a supplied `metadata.source_fingerprint` instead of hashing the current array.

**Impact:** Mutating pixels without updating revision/fingerprint can leave cache/graph identity inconsistent with image content.

**Required next evidence:** choose an explicit ownership/immutability contract (for example, owned read-only arrays or validated replacement-only updates); bind revision/fingerprint invalidation to content changes; test mutated arrays and stale metadata.

### P2 — Adapter contract modules are not a replacement for active runtime subsystems

**Evidence:** `v2_scene_graph_contract` calculates state/graph identity but does not execute a graph. `v2_cache_contract` builds digests/keys while `Eng` retains its own cache. `v2_export_contract`, `v2_icc_contract`, `v2_ocio_contract` and `v2_offline_ai` provide callable utilities, but no call sites into the active application were found in the engine source. OCIO's GPU capability check is not itself a GPU-apply function.

**Impact:** “Adapter present” or “contract tests pass” must not be reported as the corresponding production feature being integrated end to end.

**Required next evidence:** one documented production seam per adapter, caller/callee trace, dependency availability handling, user-visible behavior tests and failure/fallback behavior.

### P2 — ICC conversion boundary is explicitly 8-bit

**Evidence:** `convert_display_referred_rgb` requires display-referred RGB in `[0,1]`, rounds/scales to uint8 for Pillow ImageCms conversion, and returns float32 values reconstructed from that uint8 output.

**Impact:** It does not preserve high-bit-depth precision or scene-linear headroom. Treat it as a display-referred 8-bit conversion primitive, not a general precision-preserving scene transform.

**Required next evidence:** preserve this documented scope or add separately tested high-bit-depth/scene-linear workflows; do not silently widen the claim.

### P2 — Dependency documentation and metadata disagree

**Evidence:** `pyproject.toml` declares NumPy, Pillow, Numba, rawpy and `opencv-python`, plus development tools. `docs/requirements.txt` describes some dependencies as optional, uses `opencv-python-headless`, and does not cover all V2 adapter imports. The V2 tree has `pyproject.toml` and `uv.lock`, but no root `requirements.txt`; older `docs/README.md` text referred to both a root requirements file and `.github/workflows/tests.yml`, neither of which appears in the reviewed tree.

**Impact:** A developer may install a partial or conflicting environment and misinterpret an adapter import failure as an implementation defect or as a supported fallback.

**Required next evidence:** designate one install/lock source, list extras per adapter, align OpenCV package naming, and verify an install from a clean machine before calling portability verified.

### P2 — Main and integration-v2 branch relationship is unresolved

**Evidence:** GitHub's commit-compare endpoint returns “No common ancestor between main and integration-v2”; `integration-v2` does have a common ancestor with `develop` and is 18 commits ahead of it at the review baseline. The toolbar patch branch was created from the `main` base and changes only the legacy monolithic entry point.

**Impact:** Do not infer that a successful toolbar push contains V2 changes or that the V2 line can be merged into `main` as a routine fast-forward.

**Required next evidence:** inspect authoritative local refs and intended release lineage, establish a reconciliation/cherry-pick or migration plan, then rerun integration tests on the actual merge candidate. No merge was performed during this documentation task.

## Historical receipt boundary

The records in `verification/` state 143 passed, 2 skipped, 2 warnings and report a PyInstaller startup smoke pass from the 8 October candidate environment. These facts are preserved as historical receipts. This review did not rerun pytest, compileall, a packaged GUI launch, CUDA on hardware, or a benchmark. The CUDA receipt's parity values are specific to its recorded probe and environment.

The following gates remain open in the recorded release state: Camera Gate 2A, Camera Gate 2B, EXIF/XMP certification, clean-machine portability and universal GPU/backend portability. The Numba `tbb12.dll` warning remains recorded.

## Recommended execution order

1. Approve the LUT behavior contract before implementation.
2. Harden the standalone CUDA adapter and its edge-case tests.
3. Wire a single backend boundary into active `Eng.render` and the export path without breaking CPU behavior.
4. Prove active-engine CPU/GPU equivalence for the chosen interpolation semantics, including failure/fallback conditions.
5. Measure transfer-inclusive end-to-end speed and memory at practical sizes.
6. Resolve frame mutation/fingerprint semantics and connect the active cache to the chosen identity contract.
7. Integrate other adapters one by one only when their dependencies, call sites and application-level tests are defined.
8. Reconcile `main` and `integration-v2` lineage before any merge or release.
9. Generate fresh release receipts from the exact final source and packaged artifact; update gates only from those receipts.
