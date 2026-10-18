# Slow-connection timeouts: verified stable release 1.0.10+27

## Published identity

- [EmoSonic 1.0.10+27](https://github.com/jsdfhasuh/emosonic-releases/releases/tag/v1.0.10%2B27) is stable/latest, published 2026-10-18T11:38:11Z (release 416414552).
- Source: `3d31c15c14e3bb5613455c2cdb409f389d1a225a`.
- Slow-connection branch: `40bddf9170c640e2ccb7f100a62a7b6bdfabab2e`.
- Genuine two-parent merge: `2f96cbebe2bb6972be6f6028566014aa3ff2eba0`; the following source commit changes only the version to 1.0.10+27.
- Builder: `e9608e68410e0022f7bb610a52edbb8fde944424`.
- [Workflow run 39122884739](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39122884739), attempt 1: all seven jobs succeeded (prepare, validate-source, build, verify, build-windows, verify-windows, publish).
- Source and builder refs were advanced with exact expected-head leases and force=false. Existing later work was not overwritten. No source code or vendor bytes were changed while preparing this release beyond the authorized timeout merge and version bump.

The API now uses 8/10/12-second staged connection limits within one 45-second total request budget. Android hydration permits 30 seconds and dependent preparation/restore waits 31 seconds. Dedicated reachability probes, cancellation, retry limits, stale-load guards, native start acknowledgment and personal-lab strict-v2 behavior remain unchanged. The hydration timer bounds error reporting and preparation waits; it does not forcibly abort the underlying native load.

## Actual automated validation

The frozen release source ran under pinned Flutter 3.41.2 / SDK commit `90673a4eef275d1a6692c26ac80d6d746d41a73a` on a fresh Linux runner:

- Dependencies, navigation consistency and full code generation passed.
- Vendor provenance passed on exact repository bytes, without newline normalization.
- Full Flutter analysis passed with fatal warnings and infos enabled. The earlier local Flutter 3.47.4 diagnostics did not reproduce with this release's pinned SDK; no lint suppression or unrelated source fix was added.
- **2,446 tests in 290 suites passed; zero failures and zero skips.** The parser separately identified 298 hidden loader/lifecycle events and did not count them as tests.
- The complete test stream, suite inventory and root-group counts were validated. Original tracked bytes, file modes and source inventory remained identical to the frozen commit after all commands.
- 119 public builder synthetic tests passed both locally and in Actions. New cases cover incomplete/failed/skipped JSON test reports, source drift, staged files, mutable ignore-file bypasses and workflow dependencies. These are separate from the Flutter count.

Private source output was suppressed and no private test logs/source artifacts were uploaded. Both platform builds and publication required successful current-source validation; no gate was bypassed.

The Android build compiled the production NativeStartGate and its committed Java harness with Temurin 17 javac --release 8, then executed **104 checks** successfully at 11:30:17 UTC. Full Android arm64 debug compilation of the vendored plugin passed at 11:35:09 UTC, before the signed release build. A fresh runner passed APK signature, application ID, version, three ABIs and provenance at 11:37:51 UTC.

Windows release compilation and original Inno installer packaging passed. A separate Windows runner verified installer identity, embedded app version, x64/runtime payload and provenance at 11:36:06 UTC. Publication required both verifier digests and all six exact assets before promoting latest.

## Independently downloaded public assets

All six assets were fetched again after publication. Their byte counts and SHA-256 values match the release API. Both checksum sidecars match their package; both schema-3 manifests match source, builder, run, attempt, version and historical platform identity.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `android-manifest.json` | 775 | `3cabd4ede60d2a281daa75055740c3a9f89618b46b328aed424263355e098ebe` |
| `emosonic_android_v1.0.10+27.apk` | 77375611 | `942815976c063d792c0eb1637dd6547c22fed935615c4103470183d21dc17c9d` |
| `emosonic_android_v1.0.10+27.apk.sha256` | 98 | `c65ffad4ad2d0f91812c0efce976b747369a28573af7f70c144fbbb83c42c215` |
| `emosonic_windows_v1.0.10+27_setup.exe` | 14060551 | `6b70be2ebc257e43b3df9ddf168d3ac0a7b6d7004a8f16a3f934174e123ef7e3` |
| `emosonic_windows_v1.0.10+27_setup.exe.sha256` | 104 | `c8232cd9e335ce0666caf83ab3bf0e9c85c2dd0c6e41dc232271a9f8bea68515` |
| `windows-manifest.json` | 820 | `48127a055083881d8f959dd524e35568f73116e8df8b6e37ab265893ff79fc0f` |

The downloaded APK was independently inspected again using Google's official Android build-tools 36.0.0: apksigner cryptographic verification passed, with certificate SHA-256 `6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`; aapt confirmed `com.example.emosonic`, versionName 1.0.10, versionCode 27, and arm64-v8a/armeabi-v7a/x86_64. The signing identity matches the previous GitHub release.

Windows preserves installer GUID `{779F17F8-DA99-4D5B-A404-E7E2D17C1E65}`, the existing per-user install directory and lowest-privilege/x64 identity. Authenticode remains NotSigned, as before. The original installer hash and manifest match the artifact independently inspected by the fresh Windows runner; this Linux-side recheck does not claim to execute or install Windows software.

## Separate source-repository CI status

[Client validation run 39122379948](https://github.com/jsdfhasuh/emosonic/actions/runs/39122379948) for the same source is failure with no executed steps and runner_id 0. Its cause remains unconfirmed. It is not recorded as passing or as an observed test failure. The successful current-source validation above was actually executed in the public builder instead.

## Device acceptance remains pending

Android and Windows installation/upgrade, retained accounts/downloads, physical audible playback, slow/stalled network behavior, offline cold start, OS media/lifecycle handling and end-to-end updater acceptance are **NOT_RUN / PENDING_USER_VALIDATION**. Automated tests and binary inspection are not production-readiness certification or server deployment/compatibility acceptance.

The phone's pre-existing APK signing conflict remains unresolved. Matching historical release certificates does not identify the currently installed APK's signer. If Android reports a signature mismatch, stop; do not uninstall the existing app or clear its data to force installation. Preserve downloaded music and application data.

Exact slow/stalled-loading, cancellation, source-switching and log-collection steps remain in the [source validation plan](https://github.com/jsdfhasuh/emosonic/blob/3d31c15c14e3bb5613455c2cdb409f389d1a225a/docs/plans/2026-10-18-relax-server-connection-timeouts.md#manual-verification-pending-user-validation). Android hydration expectations apply only to Android; Windows retains its existing single-source playback path.

Any documentation-only commit after the builder SHA above is distinct from the immutable build provenance and does not change the published packages.
