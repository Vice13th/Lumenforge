# Artifact Hygiene Verification — 2026-10-05

## Status

PASS for repository/index hygiene at the current un-staged state. No forbidden or oversized artifact is tracked. The only untracked forbidden-extension files remaining are five explicitly allowlisted representative PNG evidence artifacts.

## Scan

- Tracked forbidden extensions: 0
- Tracked files > 5 MB: 0
- Tracked build/generated paths: 0
- Unallowlisted untracked forbidden extensions: 0
- Non-build worktree files > 5 MB: 0
- Verification files > 2 MB: 0
- Verification tree size: 0 MB

## Historical Large Artifact

- dist/LumenForge.exe exists in Git history at 72.2 MB (legacy release artifact). History was not rewritten.

## External RAW Protection

- E:\Remote\DSCF0833.RAF remains external to the repository.
- DSCF0839.RAF was relocated from the repository root to E:\LumenForge_VERIFICATION_ARCHIVE_20261005\raw_fixtures\DSCF0839.RAF.

## Important Artifacts

| Artifact | Type | Size | SHA-256 | Repository-tracked? | Release-included? | Reason |
|---|---|---:|---|---|---|---|
| source\lumenforge.py | source | 439968 bytes | 8FF1C4BE2F03C89A6E1694797D071FAE97E8A06E0BF5F6DC55A4129780F903A3 | YES | NO | Production source |
| .gitignore | repository policy | 1279 bytes | 757D1D703C815A8FB34B8325251E26BA4B5B3C0EFC078489651EBF942B231894 | YES | NO | Artifact-hygiene protection rules |
| verification\TEN_RUN_BENCHMARK_20261005.json | benchmark JSON | 14869 bytes | 3E97C92021A5C36193B030B34156D6805A36AD0FC78A5784B67008EE1CEF4B7A | NO | NO | Existing verified baseline; not rerun |
| verification\ui_a11y\runtime_normal_20261005_g.png | canonical screenshot | 108598 bytes | 295B38300756022F3904BCBD205A9240CED795AC68B560E5B84A252CBFAE54E0 | NO | NO | Packaged candidate-g normal UI evidence; allowlisted |
| verification\ui_a11y\runtime_focus_20261005_g2.png | canonical screenshot | 51846 bytes | 9317581870DCA500C2F3818F3846180E10F5C8F988423E358C0F3231FAE05440 | NO | NO | Packaged candidate-g Focus evidence; allowlisted |
| verification\ui_a11y\runtime_after_focus_exit_20261005_g.png | canonical screenshot | 140066 bytes | 5922D0D2F7CD0947C18EE2ADFFC1B1166DBA8C2C74F78018E2121EC42BB78504 | NO | NO | Packaged candidate-g Focus-exit evidence; allowlisted |
| verification\ui_a11y\focus_old_crop2.png | canonical crop | 20650 bytes | 269CD434A380868920D944446EF4641C2F8A16C431B16B1AB5B84005DE296C0F | NO | NO | FOCUS icon-removal comparison; allowlisted |
| verification\ui_a11y\focus_new_crop2.png | canonical crop | 18558 bytes | 357374B034E15FFDCD8429EC691B31C85358BB5366BBDBF505A55DA8A968E20A | NO | NO | FOCUS icon-removal comparison; allowlisted |
| build\nuitka_candidate_20261005g\lumenforge.dist\lumenforge.exe | Nuitka runtime executable | 110829568 bytes | D0E6B7DCA57F114039033B2B012282AC568617C49DA43F3939BCBD8051E573F7 | NO (ignored build workspace) | CANDIDATE ONLY | Self-contained packaged candidate; not repository content |
| E:\Remote\DSCF0833.RAF | external RAW fixture | 28365392 bytes | 2746DAE753858897FDD5DC75A4E6C87254FB73C3E853A626075A4F996117AAED | NO | NO | Real test input; permanently external |
| E:\LumenForge_VERIFICATION_ARCHIVE_20261005\raw_fixtures\DSCF0839.RAF | external RAW fixture archive | 28095648 bytes | 32DC5260D247E9B57763985E3359444A1677D800687A0017B917BA886990D592 | NO | NO | Relocated from repository root; permanently external |

## Release Package

No final release ZIP was created or declared by this hygiene pass. Release packaging must perform a separate recursive self-contamination audit before declaration.

## Commit State

git diff --check was normalized and no commit or push was performed.
