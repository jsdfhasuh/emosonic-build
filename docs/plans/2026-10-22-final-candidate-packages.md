# Filename-compatible strict verification for bounded-budget TEST packages

Request 115 reached the full Flutter test command and failed with exit 1 and
unclassified suppressed output. Dependencies, navigation, code generation,
vendor provenance and full analysis passed; cleanup succeeded, package jobs
were skipped and no artifacts were produced. Its product cause remains unknown.
Run 40089331968, builder 185816dfbb86aa4966f51efc713cf7ba749918ea and native
validation history remain preserved; this is not a product fix or a claimed pass.

Request 116 added one fixed diagnostic gate, not an automatic or blind retry.
Both complete strict same-source native witnesses remain unchanged. Every
productive stage still rejects pending or invalid pins before token access,
network traffic or source fetch, and prepare rechecks immutable evidence.

Request 116, run 40090787548 at builder
45a8dc2d9f6153ef39bbe4a97036713b695232bd, passed source validation, both builds
and independent Android verification. Windows independent verification failed
its unchanged installer identity predicate; this workflow is not accepted for
delivery. Its Windows artifact 12559211785 has ZIP SHA256
ff7b55bf4bfc3c31f3e2551ee8af4a75452b882b6866fb0f30996e5eb5ba9bab and EXE SHA256
b45b5ea35db54bcb32d2da3a51c035a5f2a857ba67ddf0b9faa282a077b9d2ce.

Bounded static parsing of the actual EXE verified the header and compressed-chunk
CRCs and found the stored BaseFilename empty, while the inspected public app
identity and version fields matched. The pinned innounp release ui_2_2_13 source
at b94b34935ff4b1019359462c154509de9fd951b9, RebuildScript.pas GetBaseFileName,
uses the input EXE basename when that field is empty. Thus renaming the delivery
copy to TEST changes reconstructed OutputBaseFilename. This is synthesized tool
metadata, not authenticated evidence of the original embedded output filename.

Request 117 changes only the package wrapper's Windows inspection input context.
After the original strict three-file bundle validation, it makes a private,
ordinary non-symlink copy in an exclusively owned direct ROOT temporary directory
under the original installer_name. Delivery and temporary-copy digests must both
equal the already-validated digest before and after the unchanged inspect_windows
call. No setup_identity field or expected value is patched or removed. A stored
nonempty wrong BaseFilename, incorrect identity/version, payload or signature
still fails. Cleanup must finish, the delivered EXE digest must still match, and
the complete original bundle must revalidate before any success digest is emitted.
The TEST delivery filename and bytes remain unchanged; no app or installer runs.

The original manifest binds builder SHA, run ID and attempt to the current
workflow. Request 117 therefore retains the full source-validation/build/verify
workflow and recompiles the same pinned source. It does not consume request 116
artifacts, change producer identity checks or introduce a verify-only workflow.

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
change before any authorized package publication. The package request is 117.
A running, failed, cancelled, partial or skipped witness cannot unlock it.
Neither old c730 nor old 72e witnesses are admissible. Pending-state negative
tests explicitly use false fixtures; they do not assert real witness failure.

Each witness independently requires the exact repository, main push, first run
attempt, workflow, run, builder, native job, product, observer, server and version.
Both native matrices, attribution, measurement validation, preflight, native
compilation and both teardown steps must uniquely succeed. Immutable source
declarations retain historical causal proof 39745934922 and recovery validation
39767536382; those historical prerequisites do not count as native witnesses.

Only the five package-specific files change relative to request 116. pipeline.py,
current_source_check.py, policy.json, stable workflows and all native harness
files remain unchanged. In particular native_recovery_check_observation.py is
not modified or retried. The package wrapper does not import that module.

The validate_source stage alone reuses follow_recovery_check.validate_full's
existing scoped quiet/fingerprint observation context. Its inventory is locally
patched to an empty list ONLY to omit private name/testOrdinal annotations and
fixture-specific sample markers. It does not select or omit any test. No
historical 282-green entrypoint, inventory pin chain or native task is invoked.
The original pipeline still owns exact full analysis and test commands,
dependency/codegen/vendor checks, complete stream parsing, zero exit requirement,
all-suite inventory and pre/post source fingerprint checks. Nonzero exits remain
failures even after diagnostic output. Successful exits still require the same
strict original parser. The observation context and its STAGE state are restored
on all paths; the only other stage adaptation is the Windows input-copy context
described above.

Only existing finite diagnostics may be printed: whole-stream counts, terminal
flags, capped error categories and safe scalar comparisons, tracked fileOrdinal
and bounded line/column locations. No private path, test name, assertion text,
stack trace, raw JSON/stdout/stderr or Secret is published. An unknown or limited
diagnostic status never supplies or overrides a pass verdict: the unchanged
original parser and process result decide acceptance. The full original report
is never truncated or substituted. An empty annotation inventory means no focused
testOrdinal is promised, not that focused or full tests have been removed.

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
the original Windows build output and all original Inno identity predicates
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
