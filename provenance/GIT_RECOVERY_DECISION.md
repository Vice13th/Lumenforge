# Git Recovery Decision — LumenForge UI

## Local workspace evidence
- Inspected workspace: `[local path omitted]`.
- No `.git` directory exists at the workspace root.
- Therefore there is no recoverable local branch name, HEAD, upstream, commit graph, staged diff, unstaged diff, or objective way to label current source edits as Git-uncommitted.
- The source workspace and its adjacent archive are byte-identical for the non-cache payload. This supports packaging from the current workspace content, but does not prove Git provenance.

## Remote GitHub evidence (read-only inspection)
- Repository default branch: `main`, current ref commit `b3bb65c054a74727a2eeaf275d533967be192b6f`.
- Remote UI branch: `fix/phase1-toolbar-layout-20261012` at `e4fc71628901c1003e6221a93e2ddf45848116be`. This commit is present remotely and is not the default-branch HEAD. Its diff targets the older monolithic `lumenforge.py`, `tests/test_toolbar_layout.py`, and documentation. It is not the current modular workspace implementation.
- The current modular paths `lumenforge/app.py`, `lumenforge/layout.py`, `lumenforge/theme.py`, `lumenforge/winchrome.py`, and `lumenforge.spec` were not found on remote `main` when checked through the GitHub contents API.
- PR #3 (`docs/repo-hygiene-20261012`, head `da18b3a9b2106829005649ea83d334b0a252eb6e`) is open and unmerged.
- PR #4 (`fix/cuda-lut-input-contract-20261012`, head `67c552c28e57c0eba16e8269f24fe654375693a9`) is open and unmerged.

## Classification
- **Committed remotely:** the older monolithic Phase 1 toolbar correction exists as remote commit `e4fc716...` on its separate branch.
- **Current modular UI workspace:** local-only relative to the checked remote main and known UI branch; because the folder is Git-less, whether it was ever committed on another branch or has local uncommitted changes cannot be established.
- **CUDA:** separate PR only; no CUDA source changes were imported into the recovered UI source.
- **Docs:** imported into a separate `reference-docs/` area with original branch, commit, blob SHA and URL recorded.

## Proposed next branch/diff plan (not executed)
1. Create a new review branch from the intended current integration target only after the source owner confirms the correct base.
2. Compare the recovered modular source against the target branch by file content; do not transplant the monolithic Phase 1 branch wholesale.
3. Review the minimal UI-only diff for toolbar responsiveness, canonical logo/icon, splash behavior, window chrome and packaging spec.
4. Run source tests and target-Windows UI verification; capture fresh screenshots at standard and narrow sizes.
5. Open a UI-only PR. Keep PR #4 and all CUDA implementation changes isolated.
6. Do not merge, push, or publish a release as part of this recovery task.
