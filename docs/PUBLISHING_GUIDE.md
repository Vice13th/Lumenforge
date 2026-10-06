# Publishing Lumen Forge

This guide is the release-control document for the public repository.

The repository contains source code, documentation and release metadata. Release binaries are published separately through GitHub Releases.

---

## Release model

```text
Git source
   │
   ├── documentation / checksums
   │
   └── validated build
           │
           ▼
     GitHub Release
```

The current public release is **v1.0.0**.

A newer commit on `main` is a development snapshot unless a new release is explicitly created.

---

## Pre-release gate

Before publishing a new release, verify:

- `LICENSE` is present and correct;
- `README.md` describes the actual release;
- `CHANGELOG.md` contains release notes;
- `lumenforge.py` is the intended source;
- `requirements.txt` and `requirements-optional.txt` are current;
- `docs/SECURITY.md` is current;
- `docs/THIRD_PARTY_NOTICES.md` is current;
- the build instructions reproduce the intended package;
- release artifacts have fresh hashes;
- no secrets, credentials, private fixtures or development archives are included;
- third-party assets and licenses are accounted for.

---

## Source vs release artifact

Do not imply that a published EXE represents every commit on `main`.

For example:

`v1.0.0` currently points to the historical Windows release artifact, while `main` contains later source/documentation work.

The current `main` branch also includes a native Windows dark title-bar implementation that is **not** retroactively part of the v1.0.0 binary.

---

## Checksums

`SHA256SUMS.txt` is the repository's integrity manifest for published artifacts and selected tracked files.

When any listed text file changes, its checksum entry must be regenerated.

For a new Windows binary, publish its SHA-256 digest with the release.

---

## What must never be published

Do not publish:

- passwords, API keys or tokens;
- private build credentials;
- private user images or datasets;
- internal test fixtures that are not licensed for redistribution;
- proprietary third-party LUTs or IDTs;
- unlicensed fonts, logos, images or other assets;
- temporary build folders and local archives.

---

## Release evidence

A release is complete only when all relevant evidence is durable:

```text
SOURCE
  ↓
BUILD
  ↓
TEST
  ↓
PACKAGE
  ↓
HASH
  ↓
RELEASE
  ↓
DOCUMENT
```

A Git tag or uploaded file alone is not evidence that the corresponding build passed every validation gate.

