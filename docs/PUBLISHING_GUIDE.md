# Publishing Guide

This guide describes the recommended workflow for publishing Lumen Forge as
an open-source project and distributing release builds.

## Repository

The public GitHub repository contains the Lumen Forge source code, supporting
documentation, assets, dependency declarations, and release metadata.

The repository is an open-source development and distribution surface.

## Before Publishing

Verify the following:

- `LICENSE` is present and contains the MIT License.
- `README.md` accurately describes the current release.
- `CHANGELOG.md` contains the release notes.
- `lumenforge.py` is the current release source.
- `requirements.txt` is current.
- `requirements-optional.txt` is current.
- `docs/THIRD_PARTY_NOTICES.md` is current.
- `docs/SECURITY.md` is current.
- `SHA256SUMS.txt` matches published release artifacts.
- No credentials, API keys, private user data, or local development files are
  included.

## Source Release

The main application source is:

```text
lumenforge.py