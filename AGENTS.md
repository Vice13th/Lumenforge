# LUMEN FORGE — AGENT BOOTSTRAP CONTRACT

This repository uses a thin agent bootstrap plus durable project execution records.

## Authority

Read, in order, before every material engineering task:

1. `AGENTS.md`
2. `docs/LUMENFORGE_MASTER_ROADMAP.md`
3. `README.md`
4. `docs/AGENT_EXECUTION_LEDGER.md`
5. Relevant source, tests, build configuration, and security documentation

The repository and current worktree are the source of truth for code state.
Do not use chat history as code truth.

## Reasoning

When the host exposes configurable reasoning effort:

- initialize with `reasoning_effort=high`;
- keep high reasoning for the entire task/session;
- never voluntarily downgrade;
- never ask the user to repeat this setting;
- if the host does not expose it, use the strongest available mode and continue.

## Tool / Plugin Autoload

At the beginning of every material engineering task, inspect available tool/plugin capabilities once and automatically select relevant capabilities.

The user must NOT need to repeatedly say which plugin to use.

Use as applicable:

### Engineering
- Superpowers: planning, systematic debugging, TDD, execution, verification-before-completion, code review, branch finishing.
- Codex Dev Workflows: feature development, bug investigation, verification, QA, orchestration, release review, interrupted-task recovery, handoff.
- Codex Engineering Guardrails: scoped implementation and independent verification.

### Repository / documentation
- GitHub: repository/history/reference inspection.
- Context7: current Python/library/API documentation.

### Research
- Exa: broad/current technical research.
- SciSpace: academic/scientific research when relevant.

### Security
- Focused security-review capabilities when the changed surface materially requires them.

### Remote
- Remote Desktop Commander only when actual machine/device evidence is required.
- Do software work locally first.

Do not invoke irrelevant plugins merely to satisfy a checklist.

## Execution

Default:

`INSPECT → RECONCILE → PLAN → IMPLEMENT → TEST → BUILD/PACKAGE → VERIFY → DOCUMENT → NEXT GATE`

After a gate passes:

record evidence
→ update roadmap/ledger
→ select the next unblocked gate
→ continue automatically.

Do not stop merely because a report was produced.
Do not ask the user what to do next when normal continuation is already authorized.

## Speed

MAXIMUM VERIFIED PROGRESS PER TOOL CALL.

Prefer local execution over remote.

Batch independent reads/searches/checks.
Parallelize safe independent checks.
Reuse long-lived test/build processes.
Use remote only for evidence unavailable locally.
Do not use remote to inspect source already available locally.

## Lumen Forge Engineering Priorities

Preserve the project's image-processing and color-science correctness while improving performance, UI, packaging, and maintainability.

Before changing behavior:

1. inspect the actual source and current worktree;
2. identify the owning module and data flow;
3. establish a reproducible baseline;
4. make the smallest safe change;
5. test the changed behavior and adjacent regression surface;
6. build/package when relevant;
7. independently verify the result;
8. document durable evidence.

Never replace a large UI or processing subsystem merely because the existing code is inconvenient. Diagnose first.

## Evidence Contract

Use:

VERIFIED
OBSERVED
MEASURED
UNVERIFIED
BLOCKED
FAILED
INFERRED

Rule:

**NO RECEIPT → NO EPISTEMIC UPGRADE**

Never invent:

- benchmark results;
- dependency versions;
- GPU/CUDA capabilities;
- image-processing accuracy;
- build results;
- executable behavior;
- test counts;
- performance improvements;
- compatibility claims.

## Change Safety

- Preserve verified behavior unless the task explicitly changes it.
- Never overwrite user/local work.
- Never force-push or rewrite unrelated history.
- Avoid dependency/version changes unless justified and tested.
- Keep image-processing math and color transforms testable and isolated from UI concerns.
- Treat third-party assets, LUTs, IDTs, presets, fonts, images, and licenses as supply-chain/legal boundaries.
- Never add proprietary assets without redistribution permission.
- Update the master roadmap whenever material project state changes.

## Retry / Anti-Loop

Attempt 1: diagnose and use the primary valid method.

Attempt 2: use a materially different valid method based on new evidence.

Attempt 3: mark FAILED/BLOCKED with evidence, preserve the state, and continue independent work.

Never repeat an identical failing action without new evidence.

## Remote Policy

Remote access is for final or otherwise necessary real-environment evidence, not for routine source inspection.

If remote access is unavailable:

mark the blocked evidence explicitly,
continue all independent local work,
prepare the exact verification batch,
and do not claim remote verification.

## Completion

A task is complete only after relevant tests/build/package checks and verification evidence are captured.

A written report is not a substitute for verification.

END.
