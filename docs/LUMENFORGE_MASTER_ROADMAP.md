# Lumen Forge — Master Execution Roadmap

> **Purpose:** one durable source of truth for autonomous engineering state, delivery gates and evidence.

**Current branch:** `main`  
**Current repository state:** active development snapshot  
**Public release:** `v1.0.0`  
**Application/render-engine version in source:** `12.0`

---

## 0. Operating contract

`INSPECT → RECONCILE → PLAN → IMPLEMENT → TEST → BUILD/PACKAGE → VERIFY → DOCUMENT → NEXT GATE`

- Keep `reasoning_effort=high` for the task/session when the host exposes it.
- Discover and use relevant installed tools/plugins automatically.
- Prefer local execution; use remote only for evidence that requires the real target environment.
- Never overwrite uncommitted or unpushed user work.
- **NO RECEIPT → NO EPISTEMIC UPGRADE.**

Evidence vocabulary:

`VERIFIED` · `OBSERVED` · `MEASURED` · `UNVERIFIED` · `BLOCKED` · `FAILED` · `INFERRED`

---

## 1. Current repository baseline

### Repository structure

The current source distribution contains:

- `lumenforge.py` — the application and processing engine;
- `assets/` — project branding assets;
- `requirements.txt` — core dependencies;
- `requirements-optional.txt` — optional RAW/computer-vision dependencies;
- `docs/` — build, publishing, security, licensing, architecture and execution records;
- `SHA256SUMS.txt` — integrity manifest.

### Source inventory

Static source inspection of the current `main` snapshot found:

- 7,295 lines in `lumenforge.py`;
- 18 classes;
- 107 top-level function definitions;
- 121 built-in preset definitions (`FP(...)` registry entries);
- 53 Camera DNA profile definitions (`make_profile(...)` registry entries).

These are source-level observations, not runtime test results.

---

## 2. Release comparison

Reference release:

`v1.0.0` → commit `da7daecf976890942f45429bcd8b7e1e47098fc1`

Audit snapshot used for the repository-wide comparison:

`59a4458f237e2509d0f1a761180a73e411bd66484`

At that audit snapshot, Git comparison reported `main` **10 commits ahead** of `v1.0.0`. The documentation commits produced by this pass occur after that snapshot and are documentation/control-plane changes; they do not alter the substantive release comparison.

The major repository-level changes are:

- full application source published in `main`;
- open-source documentation and licensing model established;
- build/publishing/security/third-party documentation expanded;
- autonomous agent governance added;
- master roadmap and evidence ledger added;
- native Windows dark title-bar implementation added.

The historical `v1.0.0` executable has not been silently replaced by these source changes.

See [`docs/VERSION_COMPARISON.md`](VERSION_COMPARISON.md).

---

## 3. Delivery tracks

### Track A — Correctness & Stability

- maintain the built-in self-test path;
- add regression coverage for real defects;
- preserve numerical finiteness and valid colour ranges;
- investigate crashes and memory pressure with reproducible evidence.

### Track B — UI

- verify native window chrome;
- preserve the dark visual system;
- keep heavy processing out of interaction-critical paths;
- maintain predictable viewport, zoom, crop, mask and command interactions.

### Track C — Colour Science

- preserve the documented processing order;
- protect OKLab/HSL/curve/LUT behavior;
- distinguish camera-inspired approximations from proprietary manufacturer transforms;
- keep live and staged/export processing aligned.

### Track D — Performance

- measure preview latency;
- measure memory behavior on large images;
- validate layered cache invalidation;
- measure optional acceleration only when the build actually provides it.

### Track E — Packaging

- reproduce clean source environments;
- package Windows builds;
- verify startup and key workflows;
- publish hashes;
- keep source/build/release states distinct.

### Track F — Security & Supply Chain

- review file parsing/import paths;
- review dependency versions;
- review bundled assets and licenses;
- ensure release packages contain no secrets or private material.

---

## 4. Immediate gates

| Gate | State | Evidence needed |
|---|---|---|
| Source publication | VERIFIED | `lumenforge.py` present on `main` |
| Documentation bootstrap | VERIFIED | `AGENTS.md`, roadmap, ledger present |
| Dark Windows title bar | OBSERVED | Real Windows runtime/EXE visual confirmation |
| Current self-test | UNVERIFIED | Fresh test receipt from current source |
| Current packaged EXE | UNVERIFIED | New build + launch verification |
| Performance baseline | UNVERIFIED | Fresh measured benchmark |
| New public release | NOT STARTED | Release-specific validation |

---

## 5. Gate discipline

A gate passes only with fresh evidence.

When a gate passes:

1. record the evidence in `docs/AGENT_EXECUTION_LEDGER.md`;
2. update this roadmap;
3. continue automatically to the next unblocked gate.

When a gate is blocked:

- preserve the evidence;
- mark it `BLOCKED`;
- continue independent workstreams.

Do not turn documentation into a substitute for validation.

---

## 6. Terminal definition of release readiness

A release candidate is ready only when the relevant:

`SOURCE → TEST → BUILD → PACKAGE → VERIFY → SECURITY → LICENSE → HASH → RELEASE`

chain has current evidence.

A successful commit is not itself a release.

