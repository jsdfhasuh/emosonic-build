# Validate ingress ordering repair

This bounded build-only workflow runs the unchanged strict green verifier against the original 64 recovery/provenance cases plus three real-ingress cases, followed by fatal Flutter analysis and the entire test suite. Private fixture hashes and exact names remain in pinned private manifests. All raw output remains private; only existing finite diagnostics are emitted. Cleanup always runs. No native execution, packages, release, deployment, new credential, or security setting is involved.

Historical expected-red run 39781042797 proves ordered stale replay at source5506dac. Any revised completion oracle must also have baseline red evidence before the repaired candidate is accepted. Final source and inventory pins remain pending independent review.

Verified baseline: run39786957072 at client37a675b48a8f1c7b0397c410cef4f1069def7962 produced exactly one causal failure and two passing controls with the same completion fixture. Candidate88b145873c5ea09b0d50e186bf2c223992681615 preserves all67 focused fixtures. Full-suite evidence additionally verifies the four hash-pinned dispatch cases by exact private names and emits only pass ordinals. Independent439 builder tests pass. No native acceptance is implied.
