# Preserve the Follow unit fixtures' real readiness prerequisite

## Evidence

Run 39722503590 passed 195 public tests and the 11 hosted readiness contract checks, then failed the existing macOS measurement unit suite before preflight or compilation. Native and private-source cleanup succeeded. Reproduction identified a synthetic alignment fixture with an empty `last` snapshot and no identity metadata. The real native harness records a fully ready sample before this stage.

## Bounded change

Keep client `01967c853a4e6020097e9a2da61f9785b470ff7d`, server `8e9a319002c0ffa6054cd98e06dd271070ed729b`, version and all runtime harness/native getter bytes unchanged. Extend only the disposable unit fixture with synthetic identity metadata and an initial ready baseline. Do not advance its clock, consume an observed sample, invoke its mutation callback, change original test methods or modify assertions and timing thresholds.

Pin the fixture's before/after hashes and preserve original test method ASTs. Require prepared-file integrity before executing the unchanged private unit suite, and again before expensive build stages. The 11 baseline/patched readiness contract checks remain mandatory.

## Validation and trigger

Local reproduction must pass all 70 private tests against both original observed and final instrumented harnesses. Public pipeline tests cover the additional integrity gate and refuse modified fixtures. Repeat the existing full native sequence: preflight, actual scoped transport proof, three sandboxed builds, normal/delayed/cancel Handoff, then Follow transfer/restoration.

The existing request is updated to attempt 8. Execution is limited to the exact non-forced main transition from `0a765ad777010d2097248e7bf97f39b692c9a550` with commit message `test: verify complete follow fixtures and native matrix 20261022`. No arbitrary inputs, releases, package rebuilds, deployments, new credentials, changed credential destinations, new sandbox privileges, raw logs or private source uploads are introduced.

Final repair packages remain gated on a successful complete native matrix, not on this fixture change or a partial result.
