# LUMEN FORGE — MASTER EXECUTION ROADMAP

Status: BOOTSTRAP / RECONCILIATION REQUIRED

This file is the durable project execution ledger for autonomous engineering agents.

## Operating Contract

Follow:

`INSPECT → RECONCILE → PLAN → IMPLEMENT → TEST → BUILD/PACKAGE → VERIFY → DOCUMENT → NEXT GATE`

Use `reasoning_effort=high` for the entire task/session whenever the host exposes it.

Use relevant installed tools/plugins automatically. Do not wait for the user to repeat tool-selection instructions.

Prefer local execution. Use remote only for evidence that requires the real target environment.

No hallucination:
**NO RECEIPT → NO EPISTEMIC UPGRADE**

## Current State

The current repository state must be reconciled from the actual repository/worktree before any milestone is marked complete.

Required first action:

### B0 — Repository / Worktree Reconciliation

- inspect current branch and worktree;
- detect uncommitted/unpushed changes;
- identify active or conflicting work when observable;
- inspect current source/build/test layout;
- establish current baseline;
- record findings in `docs/AGENT_EXECUTION_LEDGER.md`.

Do not overwrite or discard existing local work.

## Delivery Tracks

### Track A — Stability
Build reproducible baseline, regression coverage, crash/exception isolation, lifecycle/state correctness, and deterministic behavior.

### Track B — UI
Recover/validate UI architecture and interaction performance without coupling heavy image processing to the UI thread.

### Track C — Image / Color Science
Protect numerical correctness, color-space conversions, RAW handling, LUT behavior, Camera DNA behavior, and deterministic image-processing paths.

### Track D — Performance
Measure CPU, memory, GPU acceleration where actually available, image pipeline latency, large-image behavior, and sustained-session stability.

### Track E — Packaging / Release
Validate clean-environment installation, resource inclusion, executable startup, dependency boundaries, licensing, and reproducibility.

### Track F — Security / Supply Chain
Review dependencies, secrets, unsafe file handling, plugin surfaces, untrusted image/RAW/LUT inputs, and distributable assets when relevant.

## Gate Rule

Do not advance on assumptions.

Each gate requires fresh evidence.

When a gate passes, immediately:
1. record evidence;
2. update this roadmap;
3. continue to the next unblocked gate.

When a gate is blocked, preserve the evidence and continue independent tracks.

## Terminal Definition

Lumen Forge is release-ready only when the relevant stability, correctness, performance, packaging, security, and target-environment gates have current evidence.

Do not mark the project COMPLETE merely because source changes compile.

END.
