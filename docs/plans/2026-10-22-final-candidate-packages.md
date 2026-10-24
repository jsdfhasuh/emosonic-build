# Dual-native-proven bounded-budget TEST packages

Local package-gate preparation only; no package build or publication has been
performed by this draft. Both complete strict same-source native witnesses have
now reached terminal success. Every productive stage still rejects pending or
invalid pins before token access, network traffic or source fetch, and prepare
rechecks the actual immutable evidence before source preparation.

Product bfc1967a8eae65154bdd5e74491f99136dfc198d on
refs/heads/fix/follow-bounded-budget-20261024, version 1.0.10+27. Isolated native
server 5adc23da173c5f20188d79aafe8fcc1e656eb38a. Read-only observer
3e06d0a7faf99f3608a2d3734847e683f6d71d07 on
refs/heads/test/bounded-budget-observation-20261024.

Source validation 40062350211, builder 99eff9a11146fe47d3cec5611d5207919f749514,
job 120778419750 passed 282 focused cases in 37 suites, analyzer zero findings,
3068 full tests and cleanup. The gate verifies this run, its job and immutable
source declaration independently before checking the two native witnesses.

First native witness: run 40080780672, builder
68a208eb5b6fd712c1459f313e6222b0e885da2d, job 120833766576, request 113,
completed success. Second witness: run 40088297493, builder
ebf18d6e90a9682deab0b14a3a0529a2e02157f2, job 120855662181, request 114,
completed success including every matrix and cleanup step. Its terminal evidence
SHA256 is 30ccedcb575f0ef2700041805004b589449ba3058d60b6dcce902244f0dbcc0b.
SECOND_WITNESS_ACCEPTED is now true, with both exact run/head/job pins fixed.
The owner must still review the fresh builder-main parent and final five-file
change before any authorized package publication. The package request is 115.
A running, failed, cancelled, partial or skipped witness cannot unlock it.
Neither old c730 nor old 72e witnesses are admissible. Pending-state negative
tests explicitly use false fixtures; they do not assert real witness failure.

Each witness independently requires the exact repository, main push, first run
attempt, workflow, run, builder, native job, product, observer, server and version.
Both native matrices, attribution, measurement validation, preflight, native
compilation and both teardown steps must uniquely succeed. Immutable source
declarations retain historical causal proof 39745934922 and recovery validation
39767536382; those historical prerequisites do not count as native witnesses.

Only five package-specific files are added. pipeline.py,
current_source_check.py, policy.json, stable workflows and all native harness
files remain unchanged. In particular native_recovery_check_observation.py is
not modified or retried. The package wrapper does not import that module.

The workflow reruns full source analysis, tests, vendor provenance and frozen
byte integrity before either package build. Android keeps the existing pinned
certificate, com.example.emosonic, version, three ABIs and non-debuggable policy.
The existing deterministic Java contract count stays 104. Windows keeps its
original installer and embedded application identity, version, x64 architecture
and installer Authenticode NotSigned policy. Fresh independent verification
runners receive no user Secrets and verify checksums, exact manifests and
binary contents without executing the delivered app or installer.

Both delivery filenames and artifact containers explicitly include TEST,
version 1.0.10+27 and full source SHA. Package-wrapper-only naming adapters leave
the original Windows build output and embedded Inno OutputBaseFilename checks
unchanged. Each artifact contains exactly the package, matching .sha256 and
platform manifest. Manifests remain build-only, prerelease and unpublished, and
add TEST delivery identity plus test_evidence binding both witnesses, source
validation, isolated test server and observer. The test server SHA is evidence,
not a claim about the package runtime endpoint; existing DEFAULT_SERVER_URL
and GitHub updater configuration are unchanged.

Artifacts retain the existing one-day expiration. Upload occurs before the
fresh-runner verifiers, so artifact existence or a successful build alone is not
delivery acceptance. Deliver only after complete workflow success and both
independent verifiers pass, including verified links, checksums and expiry.
No private source, raw diagnostics, credentials or native test clients are
uploaded. No formal release, deployment, production-server change, source-main
merge or Android/Windows real-device audio acceptance is implied. The same
version and signing identity do not establish compatibility with every existing
installation; never force installation by uninstalling or clearing user data.
