# LumenForge

LumenForge is a local desktop image editor for photographic rendering and cinema-style colour work. The application uses a Python/Tkinter interface and a NumPy-based rendering path with selected optional acceleration.

> **Current engineering status:** the V2 contract and adapter modules are present in the `integration-v2` source line, but the 12 October 2026 source review did not establish that those adapters are wired into the active application render path. This repository state is **not cleared for a new release on the basis of historical receipts alone**. See the architecture review before making release claims.

## Start from source

Use Python 3.12 and the environment declared by `pyproject.toml` and `uv.lock`.

```powershell
python lumenforge.py
python -m pytest tests -q
```

These are the project launch and test commands, not a claim that they were freshly executed for this documentation branch. Some adapter-specific dependencies are optional and are not all included in the core project dependency list; see the dependency matrix.

## Engineering references

- [Project guide](docs/README.md)
- [Architecture and runtime boundaries](docs/ARCHITECTURE.md)
- [V2 architecture review — 12 October 2026](docs/V2_ARCHITECTURE_REVIEW_2026-10-12.md)
- [Dependency matrix](docs/DEPENDENCY_MATRIX.md)
- [Release manifest and package hygiene rules](docs/RELEASE_MANIFEST.md)
- [V2 integration and runtime-wiring matrix](verification/V2_INTEGRATION_MATRIX.md)
- [Historical release receipt](verification/V2_RELEASE_RECEIPT.json)
- [Final-state evidence snapshot](verification/V2_FINAL_STATE.md)
- [CUDA LUT hardening handoff](verification/CUDA_LUT_HARDENING_HANDOFF_2026-10-12.md)

## Release and evidence policy

Historical test/build receipts apply only to their recorded commit, environment and artifact. They do not prove that a later commit is tested, that all adapters are active, or that the package runs on a clean machine. Camera-science, EXIF/XMP and portability gates remain open until supported by fresh evidence.

The V2 source line and `main` have a documented history boundary; do not infer that they are interchangeable or safe to merge without an explicit reconciliation plan.

## License

MIT — see [LICENSE](LICENSE).
