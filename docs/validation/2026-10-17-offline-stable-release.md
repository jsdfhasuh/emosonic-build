# EmoSonic 1.0.7+24 release verification

Published 2026-10-17 11:24:12 UTC as stable latest, release ID 415763369.

- [Release and downloads](https://github.com/jsdfhasuh/emosonic-releases/releases/tag/v1.0.7%2B24)
- [Successful build and publication](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39027937897)
- Product PR #4 merge: `d9275dc08ed6f9d747ac9df476242cdec9bb9473`
- Shared Android/Windows source: `ec2f9dedd04a11ccdbcf72b8eedf8e91502a5c9c`
- Shared source version: `1.0.7+24`
- Builder: `949660021c8fb9e165dcef96e8675ae3a395660a`

## Completed checks

All six jobs passed: prepare, Android build, Windows build, independent Android verification, independent Windows verification, publish. Public pipeline synthetic tests: 66 passed; compileall and actionlint passed. Source compare from PR head to release source contains only the version bump and release-plan document. The frozen feature source's existing report records 2,213 passing automated tests; this publication did not rerun or upgrade that source suite.

Android: original package `com.example.emosonic`, versionName `1.0.7`, versionCode `24`, original certificate SHA-256 `6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`, non-debug, arm64-v8a/armeabi-v7a/x86_64. Windows: original AppId `{779F17F8-DA99-4D5B-A404-E7E2D17C1E65}`, local-appdata install directory, lowest privileges, `emosonic.exe`, x64 PE, file/product version `1.0.7+24`, numeric [1,0,7,24], complete runtime payload; unsigned Authenticode behavior unchanged. No application or installer was executed in the verifier.

Six exact allowlisted assets were uploaded into a new draft, verified remotely by size and SHA-256, then promoted to non-draft/non-prerelease stable latest. Independent post-publication REST reads confirmed the tag, six uploaded assets and digests. Existing assets were not overwritten. No Android-only release was published.

| Package | Bytes | SHA-256 |
| --- | ---: | --- |
| emosonic_android_v1.0.7+24.apk | 76589071 | cf008d8211d66887a95c6d283a089b853cb686ac84aa6b08c56260d3c4f11c4c |
| emosonic_windows_v1.0.7+24_setup.exe | 13993148 | db2fb0dcd49993e901cd0181d814428697ec8c0312502d8e5363317a17ea5e8a |

Matching .sha256 files and platform manifests are attached to the release. Both manifests bind source SHA/version, builder SHA, run ID/attempt, platform identity and package digest.

## Preserved first failures

1. [39026597285](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39026597285), builder `7c360f6a77822b93251b7d00f376f6b22cc1b30c`: Windows tool preparation, source fetch and dependencies succeeded; navigation process exited nonzero after 85 ms. Its private output was not exposed. The exact startup cause remains unconfirmed. Android built and passed package inspection, then independent verifier failed when emitting `apk_sha256` because the original output-name regex excluded digits.
2. [39027117454](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39027117454), builder `a37b5931d4a96faf89d86ca85839a2d3dc7c230d`: explicit bundled Dart runtime, safe numeric/fixed-category diagnostics. Windows navigation, codegen, application build and packaging succeeded; Android built successfully. PATH already selected the bundled runtime, so this run does not establish PATH as the first failure's cause. Both independent package inspections reached the same output-name error (`apk_sha256` / `installer_sha256`). No release was published.
3. Final run uses an exact six-name output allowlist with CR/LF rejection and injection regression tests. All build, verifier and publication stages succeeded. No signature, version, provenance, package-identity or platform gate was relaxed.

## Outstanding acceptance and access boundaries

Private source CI at exact release source [39026439275](https://github.com/jsdfhasuh/emosonic/actions/runs/39026439275) remains completed/failure before execution: runner_id=0, zero steps. It is not a failed Flutter test suite and is not made green by the public builder. Account billing, budget, credentials, security settings and branch protection were not changed.

Android/Windows installation and upgrade, actual audio, offline cold start, OS media/process lifecycle, data compatibility, application-update end-to-end behavior, M01–M15 and device performance remain NOT_RUN / PENDING_USER_VALIDATION. Back up application data before upgrading. Personal-lab policy and server.strictV2Implemented=false remain unchanged; no server deployment or production-readiness certification is implied. Windows remains unsigned as before. No work was performed on the user's computer.
