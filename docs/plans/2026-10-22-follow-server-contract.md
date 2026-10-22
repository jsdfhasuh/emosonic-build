# Fixed public server Follow rate proof

## Scope
Test only the reviewed public server candidate5adc23da173c5f20188d79aafe8fcc1e656eb38a against the test-only baselineb69a002c9fcad26ec91155bcd5b14ca9776ab970. No private source credentials, environment credentials, deployment, release or artifact uploads. Both commits descend from8e9a319002c0ffa6054cd98e06dd271070ed729b.

## Acceptance
The original real SQLite test must fail exactly once with FOLLOW_ACCEPTED_AUTHORITY_RATE_MUST_NOT_START_RECOVERY on baseline and pass unchanged on candidate. Its full source text and AST must match. Run all Follow store tests without skipped cases, then the existing complete unit and network suites. Preserve and report any optional skips in the latter suites rather than counting them as executed coverage. All code imports must resolve to the exact current checkout, despite editable dependency installation.

## Bounds
Only the one exact main transition from90d9d6074ed70268c8f110f1a383d8cff5b464e3 with the declared request and commit message can run. Public regression/unit test counters and allowlisted test identifiers are retained; raw application/test output is suppressed. The existing release workflow is unchanged. Native testing waits for this server gate and must use the reviewed server SHA explicitly. No production server deployment is authorized or performed.
