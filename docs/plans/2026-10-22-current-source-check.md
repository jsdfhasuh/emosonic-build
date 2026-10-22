# Current-source build and server verification

The user explicitly requested compilation through this builder and server-backed testing.

Build the exact cache-banner fix candidate (1.0.10+27) on refs/heads/codex/fix-discovery-cache-banners-20261022 without changing source version or publishing. Keep the existing stable workflow, pipeline, policy, environments and Secrets unchanged. A separate build-only wrapper binds a single main transition and exact request, and never exposes a publish entrypoint or release credential. Reuse full source validation, both platform builds and independent verifiers. Distribution artifacts expire after one day.

Server-backed native verification is separate from package validation. Pin isolated server 8e9a319002c0ffa6054cd98e06dd271070ed729b. Never access production or claim physical-device audibility. Test-build permissions require applicable approval before use.

Tests cover exact trigger restrictions, forbidden publish/credential paths, fixed candidate branch resolution and unchanged stable monotonic version checks. Review and validate on a dedicated branch before advancing main with an expected-head lease.

## Approved native sandbox verification

The user approved only network.client and network.server entitlements in these disposable macOS test bundles. Sandbox remains enabled; no host firewall, global network/security settings, production installation or production server change. The current client basic macOS harness uses actual AVQueuePlayer plus a read-only native state getter, not the experimental candidate/recovery algorithm. Update only the copied lab's old server revision guard to the current pinned server. Run measurement guards and actual server/HTTP206/strict-registration preflight before Flutter compilation. Then build three distinct app bundles, run extended two-client Handoff/delay/cancellation and three-client Follow/restoration. Native scripts emit only filtered static classifications and numeric metrics. No raw logs, private source, credentials or native app bundles are uploaded. This verifies same-source instrumented macOS clients, not runtime Android/Windows binaries or physical audibility.

The user additionally requested the cache-banner display fix. Build and native-test that reviewed candidate before merging, with source ref/SHA/version fixed in the request. Candidate artifact manifests label the actual branch, prerelease=true, published=false and build-only; stable publication gates remain untouched. Full source validation includes test/ui/discovery_screen_test.dart.

Native cleanup uses an exact per-run output path and public server checkout, refuses symbolic-link roots or active matching processes and does not signal unrelated PIDs. Source cleanup follows only successful native teardown. Matrix cleanup independently checks actual app preference deletion and fixture shutdown; failure remains a failed/unverified result, not a pass.

Local validation: 140 Python builder/guard tests pass; compileall and YAML parsing pass. Independent review found and resolved overly permissive output classifications and missing native-output teardown. Existing stable workflow, pipeline and policy retain their exact remote blob hashes. No local macOS execution is claimed.
