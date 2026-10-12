# LumenForge v12 — Corrective UI Pass

Date: 2026-10-12

## Root causes found

1. **Window icon order:** the code applied `iconphoto` and then optionally `iconbitmap`; on Windows the latter can replace the live icon. The icon was not reapplied after the native window was mapped/titlebar refreshed.
2. **Splash/loading visibility:** the splash was closed as soon as initialization reached `_finish_boot`, so on fast machines it could be visible for only a fraction of a second. The generated icon was a diamond, not the visible purple `L` monogram.
3. **Toolbar false overflow:** the responsive fitter measured the expanding center frame's requested width, which could stay larger than its compacted children. It therefore collapsed every button to icon-only even when there was ample visible space. The initial fit could also run while the root was withdrawn.

## Corrective changes

- Replaced the generated diamond artwork with a purple geometric `L` monogram matching the in-app header.
- Set the optional ICO first and the retained Tk `PhotoImage` last; reapplied the icon after native window startup.
- Updated both Splash and the empty-canvas startup state to use the canonical L monogram and matching `IMAGE LAB • LOOK APPLIED` branding.
- Kept the splash visible for at least 750 ms using non-blocking `after()` scheduling.
- Scheduled toolbar fitting after the main window is mapped and again after startup geometry is established.
- Replaced the stale expanding-frame measurement with a sum of actual packed child widths and their horizontal padding.
- Added regression assertions for icon ordering, splash duration/branding, post-map fitting and direct toolbar-child measurement.
- Regenerated `SHA256SUMS.txt` after source changes.

## Verification evidence

- `python -m unittest discover tests -q`: **39 passed**.
- `python -m compileall -q lumenforge tests tools`: **passed**.
- `python tools/verify_package.py`: **passed**, exact inventory verified (49 files).
- `python tools/ci_smoke.py`: **passed**; deterministic render SHA-256 `5d879627c2f4df490d8d677524241cbaad3f288b508462c38edc16ccb6701302`; built-in numerical self-test: 0 failures.
- Tk GUI was launched under Xvfb at 1920×1080 virtual screen. A live screenshot confirmed the header and central empty state use the L monogram; toolbar fit reported `True`, all primary actions remained labeled, and Export/Batch remained visible. The Xvfb window manager used a 1560×950 app window; this is Linux visual evidence, not Windows/DPI qualification.
- Screenshot: `LumenForge_UI_corrected_preview_1920.png`.

## Still open

- Verify on native Windows, including titlebar/taskbar icon rendering and packaged executable icon.
- Verify toolbar and splash at 100%, 125%, 150% and 200% Windows DPI.
- PyInstaller build/launch was not performed in this environment.
- No Git or remote operations were performed; the uploaded source ZIP and previously verified executable were not modified.
