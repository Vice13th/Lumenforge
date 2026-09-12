# LumenForge

**A color engine for real creators.**

LumenForge started as a personal tool for shaping the color and character of my own photos, then grew into a serious image-processing project that I decided to make freely available to creators.

The application is built around a layered color pipeline covering camera character, white balance, fused tone + gamma, HSL, curves, 3D LUT processing, skin protection, film/analog character, and cached render stages.

> **Important:** LumenForge is free to use, but it is **not open source**. The application source code, processing implementation, preset definitions, and related intellectual property remain proprietary and are not licensed for public modification, redistribution, or reuse.

## Current release

A ready-to-run Windows build is included at `dist/LumenForge.exe`.

The repository is the public distribution/documentation surface; proprietary source is intentionally kept outside the public repository.

## Processing note

The current verified v12 source uses **trilinear interpolation** for `.cube` 3D LUT evaluation. Earlier project copy and promotional wording referenced tetrahedral interpolation, but the implementation was audited before this release and that claim is deliberately not repeated here until the engine actually implements it.

## Requirements

### Windows users

No Python installation is required for the included executable. Run:

`dist/LumenForge.exe`

### Private development

For authorized source development, Python 3.10+ with NumPy and Pillow is required. OpenCV and rawpy are optional dependencies.

See `docs/BUILD.md` for the development/private-source setup and `docs/THIRD_PARTY_NOTICES.md` for dependency licensing.

## License

LumenForge itself is distributed under the **LumenForge Free Use License**, a proprietary, non-open-source license.

You may use the released application for personal and commercial creative work at no charge, subject to the license. You may not publish, sell, sublicense, modify, reverse engineer, extract, or redistribute the proprietary source or internal implementation.

See `LICENSE` for the full terms.

## Easter egg

There is a small personal Easter egg in the application. Try typing `negin` in the command/preset search area.
