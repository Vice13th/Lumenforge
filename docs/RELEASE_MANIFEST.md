# LumenForge v2 — Release Manifest

- **Project:** LumenForge
- **Release:** v2
- **Package purpose:** Public GitHub repository/release package
- **License:** MIT
- **Contents:** source, tests, tools, CI configuration, dependency/build metadata, documentation, release notes, verification evidence, and selected visual review assets.
- **Excluded:** Git metadata, caches, compiled artifacts, temporary files, profiling artifacts, and machine-local state.
- **Public-package rule:** no internal process-plan documents are included.


## Evidence hygiene and scope

- Any receipt selected for a distributable/public package must not expose workstation-local absolute paths. Replace those paths with a neutral omission marker while retaining artifact hashes, sizes, toolchain versions, timestamps and measured outcomes.
- Keep raw fixtures, unsanitized workspace reports and internal process-plan documents outside the distributable package.
- Historical verification records must identify their source commit and environment. A historical `RELEASE READY` or `VERIFIED` label is not current release clearance for another commit.
- The repo's verification folder may contain engineering history, but it must not be treated as a blind copy target for a public release package.
