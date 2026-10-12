# LumenForge v12 — Runtime Layout Correction Report
Date: 2026-10-12

## Target
`C:\Users\Amirs\Downloads\LumenForge_v12_Toolbar_Scroll_Fix`

## Root causes fixed
1. Toolbar shell height was 56px while toolbar children required about 66px with vertical padding. The shell is now 72px; a fresh full-desktop capture shows controls are no longer clipped vertically.
2. The expanding center toolbar frame was packed before the pinned Export/Batch frame. Tk pack allocated expansion into the right group on narrower windows. The right group is now reserved first, then the center row expands only into the remaining width.
3. Calling `pack_configure(expand=False)` on existing buttons reordered Tk's pack slave list, placing Redo/Fit in the wrong slots. That unnecessary reconfiguration was removed.
4. The workspace rail could be left at its early fixed width because Configure events can fire before every rail widget exists. A final fixed-container fit now runs after all rail controls are constructed; the rail uses a larger 132px minimum to keep navigation labels and buttons readable.
5. The left preset sidebar, center viewer, and right inspector now use matched vertical bounds in measured runtime layout; at 1920×1080 the sidebars share the same y/height. At 1120×760, the toolbar switches to compact icon mode and Export/Batch remain outside the center command row.

## Verification
- Windows 11, Python 3.12.10, PyInstaller 6.22.3.
- `python -m compileall -q lumenforge tests tools`: PASS.
- `python -m unittest discover tests -q`: 40 passed.
- `python tools/verify_package.py`: PASS, exact inventory 54 files before this report is added.
- `python tools/ci_smoke.py`: PASS; deterministic render SHA256 `5d879627c2f4df490d8d677524241cbaad3f288b508462c38edc16ccb6701302`; built-in self-test failures 0.
- Rebuilt the standalone EXE and launched that exact artifact. Windows reports `Lumen Forge - v12.0`, Responding=True. Final screenshot inspected at `runtime_verified_final.png` (remove this diagnostic image before manifest verification).
- No Git or remote repository operations were performed.

## Current executable
Path: `dist\LumenForge.exe`
Size: 85,701,950 bytes
SHA256: `2D6030411631AA1E28E95FCD9F16F95445ED49A0D250C5C4899E139A50EC3336`

Run this EXE in the target folder, not a copy from another location.
