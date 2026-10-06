# Security Policy

Lumen Forge is a local desktop application that processes user-provided image and preset data.

Security reports are welcome for issues that can materially affect a user's machine, files, secrets, privacy, or the integrity of the application.

---

## Reporting

For a security-sensitive issue, contact the project owner privately before public disclosure.

Provide enough information to reproduce the issue while avoiding unnecessary credentials, private images, personal data or other secrets.

For ordinary, non-sensitive defects, use GitHub Issues.

---

## Do not include

Never place the following into a public issue:

- passwords;
- API keys;
- access tokens;
- private certificates;
- private user images;
- personal information;
- private build credentials;
- unpublished proprietary material;
- complete exploit payloads when a safe reproduction is sufficient.

---

## Relevant security surfaces

The following surfaces are particularly relevant because of the application's behavior:

### File handling

Lumen Forge opens image files and can read optional RAW inputs.

### Preset / LUT import

The application accepts imported `.xmp`, `.cube` and `.json` content. Treat imported files as untrusted input.

### Image-processing paths

Malformed or adversarial image data may exercise large memory allocations, decoder behavior or numerical edge cases.

### Third-party dependencies

NumPy, Pillow, and optional RAW/computer-vision packages form part of the executable's attack surface when installed or bundled.

### Packaging

PyInstaller builds and bundled runtime files must be checked for accidental inclusion of secrets or development-only material.

---

## Security claims

This document defines reporting scope; it does **not** certify the application as vulnerability-free.

No statement such as "secure", "safe", or "fully audited" should be inferred without a dedicated security assessment and current evidence.

---

## Responsible disclosure

Please allow reasonable time for investigation and remediation before public disclosure of a confirmed vulnerability.

For dependency-originated issues, coordinate with the upstream project when appropriate.

