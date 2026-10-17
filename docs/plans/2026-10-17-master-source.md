# Reviewed master source selection

## Scope and decision

Use source `master` by default, resolving it once in `prepare` to a reviewed exact SHA for both Android and Windows jobs. Replace the previous allowlist entry with `e36793bd0d7df943c36326667df4a5a16b606878`. A future branch movement must fail before build outputs are emitted until the new commit is reviewed. Do not silently fall back to an older source commit.

This changes public build infrastructure only. Do not run product builds, Actions or releases; do not change product code, server deployment or Secrets.

## Read-only compatibility review

Compared complete Git trees against `f5d1dec2c8d5b90def0fd23c1b4a1173a7e9e1d1` (580 changed blobs across 69 commits). Reviewed build configuration, dependency changes, installer identity, signing and updater contracts; this is not a full audit of all runtime changes.

- Android and Windows native build configuration is unchanged. Original Windows batch script and Inno template match the existing pinned Git blobs. Keep package name, signing certificate, installer identity and update destination unchanged.
- Source version is now `1.0.6+23`, matching the existing public latest `v1.0.6+23`. Keep strict version/build monotonicity: the next run requires a separately confirmed higher build number.
- The declared Dio constraint changes from `^5.3.0` to `^5.11.0`; updater error handling adds its timeout enum case. No tracked pubspec lockfile exists, so dependency resolution remains variable. Keep Flutter 3.41.2 and its pinned SDK commit.
- Latest-release lookup, version-tag parsing and platform asset selection are unchanged. Continue requiring newly built Android and Windows assets from the same source SHA and version before promoting a stable latest release.
- The product release workflow is now manual-only. Still avoid concurrent manual publishers across repositories.
- Source integration notes report dependency resolution, code generation, analysis and tests with the same Flutter/Dart toolchain. Those are source-provided results, not checks performed by this builder task; no successful product build is asserted here.

## Validation and handoff

Add regression cases for master resolving exactly once, unreviewed branch movement stopping without outputs or fallback, and reuse of the resolved SHA by both build jobs. Run the full local pipeline unit suite, Python compilation, actionlint and whitespace checks. Recheck remote master before pushing the infrastructure commit.

Completed local validation: 33 pipeline tests passed, Python compilation passed, actionlint passed (shellcheck and pyflakes unavailable/disabled), and `git diff --check` passed. Read-only GitHub recheck confirmed the reviewed master SHA, latest `v1.0.6+23`, and zero builder Actions runs. These checks do not compile the product or validate its runtime behavior.

Real Android/Windows builds and device acceptance remain pending user-configured Secrets and version confirmation. On both platforms, validate upgrade installation with retained settings, ordinary library playback, and update detection independently of realtime connectivity. Strict realtime requires the paired server's protocol 2.9 / r19 authentication acknowledgement; server integration/deployment remains unverified. A missing or incompatible acknowledgement is not evidence of an ordinary library playback failure. Do not enable compatibility workarounds or deploy a server as part of this task.
