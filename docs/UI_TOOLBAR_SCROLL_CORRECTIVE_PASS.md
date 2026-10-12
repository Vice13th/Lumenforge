# LumenForge v12 — Toolbar Scroll Corrective Pass

## Why the previous pass still failed
The prior implementation relied on collapsing labels based on requested-width measurements. The screenshot demonstrates that the command row still clips after Split. A one-shot fitter cannot guarantee reachability across window sizes, DPI scaling, and late Tk geometry negotiation.

## Actual correction
The toolbar now has three zones: left brand stays pinned, center editing commands live inside a horizontal Canvas viewport, and right Export/Batch stays pinned. The center command frame is embedded in a Canvas window with a dynamic scroll region. Mouse-wheel and Shift+mouse-wheel scroll the command strip; Linux wheel buttons are also handled. Labels remain intact instead of being unpredictably collapsed.

## Verification
The package includes regression tests for the scrollable-center architecture and pinned right-side actions. Native Windows GUI/DPI behavior remains to be verified on Windows; no EXE build is claimed by this pass.
