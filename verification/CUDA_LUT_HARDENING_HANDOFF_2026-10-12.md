# CUDA LUT hardening — final-phase handoff

**Status:** deferred intentionally; this document is a task handoff, not an implementation receipt.  
**Scope:** `source/v2_cuda_lut.py` and focused tests. No CUDA source changes are part of the documentation cleanup branch.

## Why this is last

Complete repository/documentation hygiene and agree the production LUT behavior contract first. Do not wire the standalone CUDA adapter into the active engine until the owning engineer resolves interpolation semantics and output-range behavior.

## Required implementation work

1. Validate the public input contract: image shape/channel layout, LUT shape and cubic dimensions, domain vector shape, array dtype and contiguity.
2. Reject or deliberately handle non-finite image/LUT/domain values.
3. Require each domain span to be strictly positive; define the error type/message for zero or reversed spans.
4. Normalize the LUT to contiguous `float32` before passing it to a kernel that reads `float*`; verify actual CuPy/kernel dtype agreement.
5. Define empty-image behavior explicitly and ensure it does not launch a zero-block CUDA grid.
6. Decide whether the intended output is clipped to `[0,1]` or preserves headroom. Document why, and compare that choice with the active CPU path.
7. Add focused negative tests for malformed shapes, non-finite data, invalid domains, dtype conversion and empty input. Keep a CPU-only test path where possible.
8. On CUDA hardware, record CuPy/CUDA/device/driver versions and compare the kernel to a trusted reference over deterministic LUTs, image sizes, domain ranges and edge values.
9. Measure complete-call latency including host/device transfers and synchronization. Do not promote kernel-only timing to an end-to-end speed claim.
10. Do not claim active-app integration until a production call site and application-level parity/fallback tests are proven.

## Required evidence before closeout

- Exact branch and source commit SHA.
- Focused test command and raw pass/fail output.
- CPU/reference parity metrics and tolerances.
- CUDA device, driver, CUDA and CuPy versions.
- Empty/invalid-input behavior and error cases.
- Transfer-inclusive timings at multiple practical image sizes.
- A clear statement of what was not tested.

## Acceptance gate

Close this handoff only when the above results are attached to the exact tested commit. The current historical CUDA receipt is limited to its recorded environment/probe and does not establish end-to-end performance or active-engine parity.
