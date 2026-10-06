# LumenForge — Visual / Loading / Easter Egg Handoff

## Purpose
Establish LumenForge as the VICE13TH LABS product with a distinct **Liquid Glass + Dark Chrome + Cinematic Editorial** identity while keeping the parent brand coherent.

## Shared VICE13TH LABS DNA
The shared DNA is structural, not a shared palette:
- dark/cinematic foundation
- premium typography and strict hierarchy
- disciplined spacing
- material depth with restrained glass/chrome effects
- deliberate motion
- consistent accessibility and interaction feedback

Do **not** homogenize product colors, gradients, glow language, or component personality.

## LumenForge visual identity
Base: graphite / near-black / dark chrome.
Accent: restrained electric cyan.
Material: liquid glass, dark chrome, cinematic editorial.
Avoid generic purple SaaS styling, candy gradients, noisy neon, and arbitrary per-screen recoloring.

## Loading states — REQUIRED
Every loading/processing state is a first-class part of the product design system:
- application launch
- asset/import processing
- preview/render processing
- export/save operations
- long-running compute
- completion/failure transitions

Loading UI must use the same surface, typography, spacing, border, glow, and motion language as the main application. It must communicate state and progress without decorative noise.

### Current known issue
The current LumenForge loading presentation has a visible **logo-inside-another-logo** composition. Treat this as an actual asset/layout defect to trace and fix at the source. Do not hide it by random scaling, clipping, opacity tricks, or extra overlays.

The intended result is one deliberate LumenForge mark, with a clear loading composition and no duplicated/stacked logo artifact.

## Easter Eggs — REQUIRED
Easter Eggs are part of the product polish and may remain/expand when intentional.
They must:
- feel authored rather than accidental
- remain visually consistent with LumenForge
- never look like duplicate logos, debug UI, broken icons, or leftover overlays
- never block core workflows
- remain discoverable without degrading usability

Audit existing Easter Eggs before adding new ones. Preserve intentional ones; repair/remove only broken or misleading ones.

## Anti-patterns
No random green/purple panels, no per-screen color invention, no duplicated branding, no loading screens built from unrelated components, no excessive blur, no unreadable glow-on-glass text, and no motion that harms responsiveness.

## Verification gate
Before calling the visual handoff complete:
1. Inspect source/assets for every loading composition.
2. Capture launch/loading, processing, completion, and error states.
3. Verify the logo is singular and intentional in every loading state.
4. Audit Easter Eggs and classify intentional vs accidental.
5. Verify desktop/window-size behavior and readability.
6. Record visual verification separately from design intent.

This document defines design intent; it is not evidence that the implementation has already been visually verified.

> WORKFLOW: INSPECT → REPORT → IMPLEMENT → VERIFY
> BEFORE IMPLEMENTATION: Read AGENTS.md, CHECKPOINT.md, and the current roadmap/technical-gap document. Reconcile this handoff with those sources before changing code.

## Execution hardening

### OBSERVED implementation anchors
- Primary UI and processing source: lumenforge.py
- Primary logo asset: assets/lumenforge_logo.png
- Existing startup surface: Splash class
- Existing startup progress is tied to real initialization milestones.
- Existing render activity surface: _render_hud_show.
- Existing Easter Egg implementation exists in the source and must be inventoried before changes.
- Existing design tokens are centralized in T; do not scatter new colors through widgets.

### CURRENT baseline versus TARGET
The current source palette is Burgundy Noir / purple-oriented and includes semantic green/red values. This is the baseline that the visual redesign is expected to migrate coherently toward the LumenForge target palette. Do not confuse the current palette with the target, and do not perform a mechanical global replace.

### Loading hard rule
There must remain exactly one deliberate product startup splash path. Preserve real progress calls and the Splash-to-main-window lifecycle. Do not create a second splash or replace real progress with a timer/fake percentage.

### Logo defect hard rule
The logo-inside-logo composition is a defect to trace at source/asset/layout level. The fix must remove the unintended duplicate while preserving the intended single LumenForge mark.

### Change boundary
A visual task must not modify rendering math, RAW decoding, Camera DNA, LUT processing, caching, presets, export semantics, or numerical behavior except for the smallest behavior-preserving fix needed for a transient UI defect.

### Stop and report
Stop instead of guessing if the duplicate logo cannot be traced, a new dependency is required for a visual effect, an existing lifecycle state has no real UI anchor, or the requested redesign would require replacing Tkinter.

### Evidence required before completion
Capture or otherwise verify cold launch, every real splash milestone, splash handoff, render HUD, import/editor state, export, error state, resize/high-DPI behavior, and Easter Egg states. Mark visual verification separately from design intent.
