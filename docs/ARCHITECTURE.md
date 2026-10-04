# Architecture (verified by inspection of lumenforge.py, 7,788 lines; not a full line-by-line read)
- **Single-file app**, GUI = Tkinter/ttk only. Entry: `python lumenforge.py` (`class App(tk.Tk)`); widgets: Btn, Param, HSLMixer, CurveEditor, MaskTool, Crop, Straighten, Splash, Dlg.
- **Engine (no display needed):** `staged(rgb, p, ...)` = the render pipeline; `Eng` = engine/preview class; helpers: tone curve, HSL (numba kernel + numpy fallback), color grading, local masks, skin tools, grain, blur, Local Laplacian (Clarity/Texture/Dehaze), `LUT`, `CameraProfile`/`CameraMatchResult`, presets (121) and camera profiles (53).
- **Color:** `ColorManager.to_display()` uses OCIO builtin ACES config when PyOpenColorIO is importable (default ACES 1.3 / "ACES 1.0 - SDR Video"; ACES 2.0 opt-in via `LUMENFORGE_ACES=2.0`), else numpy `aces_fallback_tonemap`.
- **Optional deps (auto-detected, graceful fallback):** numba (JIT speed), rawpy (RAW open), OpenCV (blur/bilateral/face cascade), PyOpenColorIO.
- **I/O:** Pillow for images; rawpy for RAW; .cube LUT round-trip; Lightroom XMP import.
- **Security/session:** none (local single-user app) — see TOKEN_MANAGEMENT.md.
- **Rendering engine treated as high-risk:** only change so far is bit-exact LLF refactor.
