# Frozen ingress pending-apply causal proof

This lean proof runs one new private test-only descendant, not the previous source as a replacement fixture. The reviewed test-only client is 87251d4976fd884efefe765a18f8b12b1eabe63e on refs/heads/test/follow-ingress-pending-apply-20261022. The private inventory SHA256 is 6db76d19ef749275814527166fc5a3a9f9ce7c328840fdaa3c1578db5be2d7c1, with causal ordinal 1. It pins fixture SHA256 e77d38137f49fbb5f9bbf08c7440ab793f3186475a65c19f18936e847a1dbb8f.

The private inventory pins one fixture's path, byte digest, three exact visible names and its 1-based causal ordinal. No private test names, fixture source, raw logs, stack text, URLs or token values are exported. The existing whole-stream observer reports finite counts, categories, ordinals and fixture locations before acceptance. Setup/test capture is bounded in memory and time; partial timeout/output-limit observations never qualify as proof.

Acceptance requires exactly three completed visible tests, two successful controls, exactly one causal isFailure error with the exact marker FOLLOW_INGRESS_STALE_PENDING_APPLY_REPLAYED, target result failure, process exit 1, exactly one final terminal success false, and every hidden lifecycle passing without skips. Only after those causal checks does a narrow normalization reuse the original unchanged strict green verifier for complete inventory and lifecycle accounting. No compile error, setup error, wrong assertion, extra error, missing case or hidden failure is accepted.

Each of the three case-scoped FOLLOW_INGRESS_NATIVE_ORDER records is retained only through its agreed fixed schema: enum changes/phases, bounded integer timings/positions/counts, booleans and fewer than ten dispatches per list. Missing, duplicate, out-of-scope, oversized or schema-invalid evidence fails the gate. No raw print body is exported.

Existing prepare, fetch, code generation, source fingerprint and cleanup helpers remain in use. Tracked private bytes must match before and after, including failure paths. Only the existing source-read secret is used, only in prepare/fetch steps. No private artifacts are uploaded. Workflow permissions are read-only and checkout credentials are not persisted.

Client production baseline: 466f56d9935afb299724a212d680a743a11c723f.
Server: 5adc23da173c5f20188d79aafe8fcc1e656eb38a, unchanged and not executed here.
Public builder predecessor: f88b7d69bc774a7195303b78b6bb6471ab87bf28.

This expected-red result is causal evidence, not a repaired/green candidate. The original full-source analysis, full tests, vendor integrity and all 64 existing focused cases remain mandatory on the later repaired candidate. This workflow does not replace them and performs no native build/run, package build, server deployment or stable release. Existing stable files and workflows remain byte-for-byte unchanged.

## Await-phase diagnostic iteration

Run 39775963962 did not establish causal evidence: all three visible cases ended in TimeoutException, three hidden lifecycle cases passed, and no native-order record was emitted. The diagnostic-only source descendant is 28b05652403eab21100e8960e94bfabed331482e on refs/heads/test/follow-ingress-barrier-diagnostics-20261022. Private inventory SHA256: 65676025dce1f558a8082df54c6a95fef9449c4c1a6dc62a04b0883b17faa67c. Fixture SHA256: 4e94b9b678d46697d46dfd20a900e1aeb827446cbc58350dda4e97c87863367d.

The new FOLLOW_INGRESS_STAGE observation admits only the agreed case ordinal and 44 fixed await-stage enum values, binds them to the pinned reporter test ID, and retains at most 48 stages per case. It always prints summaries for all three ordinals before expected-red rejection, including missing histories. Full bounded histories preserve the unfinished body await even if teardown later emits stages. Invalid/extra fields, arbitrary strings, wrong-case IDs and overflow are counted without being exported.

This is diagnosis only: strict expected-red acceptance, native evidence schema, assertions, timeouts and production bytes are unchanged. Builder predecessor is a3684c1076046c70a7dc9d40278a3badcaa0dcfb and request attempt is 29. No native, package, deployment, release or credential changes.
