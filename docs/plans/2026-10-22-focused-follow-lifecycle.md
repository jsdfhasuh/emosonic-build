# Focused Follow lifecycle diagnosis on the frozen repair candidate

Run 39723597885 again passed normal, delayed and cancelled Handoff, but the three-client matrix never reached its initial native Follow-ready predicate within the original 45-second deadline. Its final snapshot showed the original paused local task. That snapshot does not distinguish accepted-then-restored from an unobserved transition.

## Scope

Keep client 01967c853a4e6020097e9a2da61f9785b470ff7d, server 8e9a319002c0ffa6054cd98e06dd271070ed729b and version 1.0.10+27 unchanged. Run the complete three-client Follow transfer, sustained-follow, rate-change and restoration sequence. Do not repeat the separate two-client delayed/cancel suite merely to collect Follow diagnostics.

Add only bounded read-only observation: preserve the existing command-return state; summarize existing polls and lifecycle transitions; read the owned fixture SQLite database with read-only/query-only transactions; classify exact allowlisted events/reasons and stack-function tokens from private lab logs. A missing lease is admission unknown, not rejection. Server and client snapshots are not atomic and their differences are observations, not inferred causal errors or new acceptance gates.

The disposable lab entrypoint changes its existing warning logging level to debug so recovery markers actually exist. It is an exact hash-pinned, reversible one-line test configuration change, not a production logger change. No raw logs, private identifiers, credentials, URLs, exception text or stack lines are uploaded. Existing private cleanup remains mandatory. The attribution helper admits this one frozen lab variant only when explicitly selected by the focused wrapper; all other factory/account/route guards and six-plus-six proof checks remain unchanged.

Normalize the newly created controller-owned temporary root before fixture construction to avoid macOS's standard /var alias, while retaining strict arbitrary fixture/child/database symlink refusal. No server flags, endpoints, deployments, network settings or additional sandbox permissions are changed.

## Validation and execution

Require all existing 70 private measurement tests and 11 readiness proof checks, plus deterministic observer/privacy/integrity tests. Preserve original assertions, playback calls, deadlines and complete measurement windows. Observation manifests and the composed attribution hash are checked before compilation and runtime.

The exact non-forced main transition is 44a6325cb80de20fc284a1047ae00403054a7e53 with message `test: trace fixed-source native follow lifecycle 20261022`, one fixed request and attempt 9. Existing credential destinations and source/server pins remain unchanged. No releases, ordinary package builds or artifact uploads occur in this workflow.

Final ordinary packages require separately verified prior Handoff coverage and a complete successful Follow run on the same frozen source/server. A single successful diagnostic run will not silently erase an unexplained intermittent failure.
