# Third-Party Notices

Lumen Forge combines project-owned source code with third-party software and references to external technologies.

The **MIT License applies to project-owned Lumen Forge source and materials explicitly released under it.** It does not relicense third-party software, trademarks, proprietary camera technology or external assets.

---

## Runtime dependencies

| Dependency | Role in Lumen Forge | License boundary |
|---|---|---|
| NumPy | Numerical arrays and image-processing math | Use under NumPy's own license |
| Pillow | Image loading, manipulation and display preparation | Use under Pillow's own license and notices |
| rawpy | Optional RAW-camera decoding | Use under rawpy's own license |
| OpenCV | Optional computer-vision functionality | Use under OpenCV's own license |

The exact versions used for a particular build determine the exact third-party notices that must accompany that build.

For redistributed binaries, preserve the notices required by the dependency versions actually shipped.

---

## Trademarks and camera names

Lumen Forge may reference camera manufacturers, camera families, formats, software, or product names when describing compatibility, profiles or creative looks.

Those names remain the property of their respective owners.

Reference to a third-party camera or product does not imply endorsement, certification or ownership.

---

## Camera DNA and look emulation

Lumen Forge uses documented mathematical approximations where proprietary manufacturer colour science is not publicly available.

The following should **not** be inferred from the presence of a camera name:

- an official manufacturer IDT;
- a proprietary LUT matrix;
- a licensed manufacturer colour transform;
- bit-exact reproduction of proprietary camera science.

Where applicable, the project uses **inspired / approximate** language to keep that boundary explicit.

---

## Assets

Project-owned branding assets are part of the Lumen Forge distribution boundary.

Third-party assets must retain their applicable license and attribution requirements.

Do not add proprietary LUTs, IDTs, fonts, logos, photographs or other third-party material to the public repository unless redistribution rights are established.

---

## Distribution rule

Before shipping a build:

1. inventory the actual bundled dependencies;
2. preserve the notices required by those exact versions;
3. check project-owned vs third-party assets;
4. verify trademarks and naming are descriptive rather than misleading.

The MIT License does not override any of these third-party obligations.

