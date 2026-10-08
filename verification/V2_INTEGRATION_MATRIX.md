# LumenForge V2 Integration Matrix

Source of truth: D:\Lumenlabs\SANDBOX_LAB\LumenParallel
Authoritative sandbox package SHA256: b4e63f22045d1926ec4c5937b9819f8becce2792f0128bb9a75a7c0aa9881265
Integration branch: integration-v2
Integration source commit: c863a043658252ace0e1c8d612873e0fd8e175c4

| component | sandbox source | source hash | existing receipt | dependencies | target V2 seam | integration status | focused tests | post-integration tests | new receipt | commit | limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frame/state contract | source/lumenforge_core/frame.py | recorded in V2_FRAME_CONTRACT_RECEIPT | none beyond source tests | numpy | source/v2_frame_contract.py | INTEGRATED | 5 passed | 114 passed, 2 skipped | V2_FRAME_CONTRACT_RECEIPT.json | a1d83c97871863df71edb3ac72caa956746382f3 | Adapter contract; engine execution unchanged |
| scene-linear/graph | frame.py, graph.py, render.py | recorded in V2_SCENE_GRAPH_RECEIPT | sandbox core tests | numpy | source/v2_scene_graph_contract.py | INTEGRATED | 5 passed | 119 passed, 2 skipped | V2_SCENE_GRAPH_RECEIPT.json | d23a410873105d871c1c71fce31cf76f91b7a24f | Contract bridge; no executor replacement |
| cache/determinism | source/lumenforge_core/cache.py | recorded in V2_CACHE_CONTRACT_RECEIPT | sandbox cache/render receipts | numpy | source/v2_cache_contract.py | INTEGRATED | 4 passed | 123 passed, 2 skipped | V2_CACHE_CONTRACT_RECEIPT.json | e174e241fc2ffd17dd56bbe69f8e4d1f4e8c70a2 | Existing V2 cache remains execution owner |
| OCIO | source/lumenforge_core/ocio.py | recorded in V2_OCIO_RECEIPT | OCIO_RECEIPT_20261008.json; OCIO_GPU_EXECUTION_RECEIPT_20261008.json | PyOpenColorIO 2.6.0 | source/v2_ocio_contract.py | INTEGRATED | 4 passed | 127 passed, 2 skipped | V2_OCIO_RECEIPT.json | 4e0defbb0d1723c39e5f2d2069bbc053477ecb63 | GPU evidence limited to measured Intel UHD/OpenGL path; no universal portability claim |
| CUDA LUT | source/lumenforge_core/cuda_lut.py | recorded in V2_CUDA_LUT_RECEIPT | CUDA_PARITY_RECEIPT_20261008.json; RUNTIME_DEPENDENCY_RECEIPT_20261008.json | CuPy 14.2.0 / CUDA 12.090 / RTX 2070 | source/v2_cuda_lut.py | INTEGRATED | 2 passed | 129 passed, 2 skipped | V2_CUDA_LUT_RECEIPT.json | 98feba6503b8bf1ec2266946b6f9f658aeb4991b | Tested runtime only; CPU reference preserved |
| native/raster export | source/lumenforge_core/export.py | recorded in V2_EXPORT_RECEIPT | EXPORT_NATIVE_RECEIPT_20261008.json; EXPORT_RASTER_RECEIPT_20261008.json | Pillow/tifffile/OpenEXR | source/v2_export_contract.py | INTEGRATED | 6 passed | 135 passed, 2 skipped | V2_EXPORT_RECEIPT.json | ee2b45373013aa4b4144f3a5cbb9f1801c500708 | Integer raster requires display-referred; EXR preserves scene headroom; embedding != conversion |
| ICC conversion | export.py | recorded in V2_ICC_RECEIPT | ICC_CONVERSION_RECEIPT_20261008.json | Pillow ImageCms | source/v2_icc_contract.py | INTEGRATED | 3 passed | 138 passed, 2 skipped | V2_ICC_RECEIPT.json | f087c5e1819aabab19192bd5d031984d4b6d7094 | Diagnostic interchange primitive; no color-accuracy certification; Gate 2B remains open |
| offline AI | source/lumenforge_core/offline_ai.py | recorded in V2_OFFLINE_AI_RECEIPT | OFFLINE_AI_INFERENCE_RECEIPT_20261008.json | ONNX Runtime 1.30.0; local MiniLM | source/v2_offline_ai.py | INTEGRATED | 1 passed | 139 passed, 2 skipped | V2_OFFLINE_AI_RECEIPT.json | 23056f2e400996e062ce990158c4e765763b970e | Local deterministic inference only; no semantic-quality certification |
| camera characterization infrastructure | source/lumenforge_core/camera_characterization.py | recorded in V2_CAMERA_CHARACTERIZATION_RECEIPT | CAMERA_CHARACTERIZATION_INFRA_RECEIPT_20261008.json; RESEARCH_CAMERA_DATASET_MANIFEST_20261008.json | numpy | source/v2_camera_characterization.py | INTEGRATED_WITH_RESEARCH_LIMIT | 4 passed | 143 passed, 2 skipped | V2_CAMERA_CHARACTERIZATION_RECEIPT.json | c863a043658252ace0e1c8d612873e0fd8e175c4 | infrastructure_only; Gate 2A NOT CLOSED; Gate 2B BLOCKED; no measured Fuji IDT promoted |
| UI/package runtime | existing V2 + build spec | current source commit | final packaged smoke evidence | PyInstaller 6.22.3 / Windows 11 | release_build_final on integration commit | BLOCKED_FOR_RELEASE | 143 passed, 2 skipped | artifact process stable >=5s; title shows Unhandled exception in script | V2_RELEASE_RECEIPT.json | pending docs commit | GUI launch process remains alive but title indicates an unresolved packaged-runtime exception; clean-machine portability unverified |

## Release-critical verification

- Final Python regression: 143 passed, 2 skipped, 2 warnings in 8.35s.
- Final artifact build tool: PyInstaller 6.22.3, Python 3.12.10, Windows 11.
- Release artifact: onedir distribution `release_build_final\dist\LumenForge-2.0.0`.
- Executable SHA256: 2334C14405021C50FE2FC44A55300DF9907A25AB3A408548346AC426CCE9BD69.
- Distribution contents: 77 files, 20,712,007 bytes.
- Source import from packaged `_internal\source` passed (`VERSION=2`, `APP_NAME=Lumen Forge`).
- Packaged process remained alive for at least 5 seconds, but window title was `Unhandled exception in script`; this remains unresolved and is therefore a release blocker.
- Hygiene scan after removing build scratch directories: PASS.

## Blocked / re-verify research

- Camera Gate 2A: NOT CLOSED.
- Camera Gate 2B: BLOCKED.
- EXIF/XMP certification: BLOCKED.
- Clean-machine portability: UNVERIFIED.
- Packaged UI runtime exception: BLOCKED.
- Universal GPU/backend portability: NOT CLAIMED.
