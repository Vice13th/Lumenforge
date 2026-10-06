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
