# Native playback ACK and diagnostic-log sharing: verified stable release

## Published identity

- Release: [EmoSonic 1.0.9+26](https://github.com/jsdfhasuh/emosonic-releases/releases/tag/v1.0.9%2B26), stable/latest, published 2026-10-18 01:20:22 UTC.
- Exact private source: `ecd827ec605577c31f3abcc3390fd53baf22df4c`.
- Exact builder: `f82d257f53fff083d6ebdfaa4b5a9965f51961f9`.
- [Build run 39085337807](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39085337807), attempt 1: prepare, build, verify, build-windows, verify-windows and publish all succeeded.
- The source uses a genuine two-parent diagnostic-log merge, a separate native ACK implementation commit, and a version-only commit. Both repository refs were advanced with exact expected-head leases and no force.

## Automated evidence

The complete local Flutter suite passed **2,442/2,442** across 290 test files, with no source-fingerprint changes. Full-project analysis reported zero issues. Offline dependency resolution, code generation, navigation consistency, formatting, vendor integrity and whitespace checks all passed. Four preserved legacy probes passed 4/4, independent service/protocol probes passed 13/13, and production Java passed 104 checks. Focused counts overlap the aggregate and are not additive unique-test totals.

The frozen local snapshot's 1,372 files were matched by exact Git blob identity to the final remote candidate tree; unchanged files omitted from the local app snapshot were retained from the real upstream tree. The complete aggregate started before the commit object existed and retains its original snapshot identity, with a separate exact binding to the published source.

The official Android build log records:

- 01:10:19 UTC: production NativeStartGate plus the committed standalone main harness compiled with Temurin 17 `javac --release 8`, then **104 checks executed and passed**.
- 01:16:42 UTC: a full debug APK compiled the complete committed vendored just_audio Android plugin, before release signing material was created.
- A separate signed release APK build then succeeded.
- 01:19:54 UTC: the fresh-runner Android verifier passed signature, package, version, ABI and provenance checks.

The Windows build and original Inno installer succeeded. A separate Windows runner verified original installation identity, embedded version, x64 executable, full runtime payload and provenance at 01:15:12 UTC. The publisher required both verifier digests and the exact six uploaded assets before promoting latest at 01:20:22 UTC. No build attempt or gate was bypassed.

## Independently downloaded assets

All six public assets were downloaded again after publication. Each byte count and SHA-256 matched the release API; both checksum sidecars matched their packages; both schema-3 manifests matched the exact source, builder, run, version and expected platform identity. A subsequent latest read still returned release 416167309 / v1.0.9+26, neither draft nor prerelease.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `android-manifest.json` | 774 | `11656f7eee9152860e5a83b615bf32ccb7c69889c45aff344fadab746173affe` |
| `emosonic_android_v1.0.9+26.apk` | 77375607 | `1efbf49c74e97a3c3bc35909037d7c2cfcda666cbec7566c1485ccbd2ecccb37` |
| `emosonic_android_v1.0.9+26.apk.sha256` | 97 | `e93a6fb5549f096df0652e8d9429eae994ce95dc773fb667369ea860a1a1bfe4` |
| `emosonic_windows_v1.0.9+26_setup.exe` | 14058586 | `809abad090d963fa4686bb5111ebf53c5437d2991a327905b7c1805c01cd91a8` |
| `emosonic_windows_v1.0.9+26_setup.exe.sha256` | 103 | `42dcbb7a5360d53b4b0699e701ec7713795333dfb49ba1d48af6ab63d52dd19b` |
| `windows-manifest.json` | 819 | `75c150515339f41a178e80879ee81c4230c81ed1a9c6c9d1df9068202fe4762e` |

Android retains `com.example.emosonic`, versionName 1.0.9, versionCode 26, all three expected ABIs and certificate SHA-256 `6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f`. Windows retains installer GUID `{779F17F8-DA99-4D5B-A404-E7E2D17C1E65}`, the existing per-user installation location and x64 identity. Windows Authenticode remains NotSigned, as before.

## Private-source CI is a separate result

[Client validation run 39085304151](https://github.com/jsdfhasuh/emosonic/actions/runs/39085304151) on the same source is recorded as failure. Its single flutter-checks job has no steps and runner_id 0; no runner or test execution was established. Its cause is unconfirmed because the connector does not expose the annotations endpoint. This result is not called passed and is not substituted for the complete local suite or the six successful public build/release jobs.

## Acceptance limits

The Android bridge now observes actual Media3 Player.isPlaying with exact instance, load, occurrence, owner/session and execution-token binding. This closes the missing implementation path, including fully buffered starts, inherited-playing reload, repeated-play and stale early-event handling. It does not prove sound at a physical speaker. Windows retains its existing native-progress/terminal behavior; no new Windows immediate-start bridge is claimed. Log sharing exports redacted snapshots through the system share flow and preserves original logs; redaction is not complete anonymization.

**Android/Windows installation, upgrade/data retention, actual audio, offline cold starts, OS/media controls and lifecycle, and end-to-end updates remain NOT_RUN / PENDING_USER_VALIDATION.** No server deployment, strict-v2 server acceptance or production-readiness certification is implied.

The phone's existing signing conflict remains unresolved. Historical GitHub certificate equality does not identify the installed APK's certificate. If Android reports a signature mismatch, stop; do not uninstall the old app or clear its data to force installation. Preserve downloaded music and user data.

Any subsequent documentation-only commit is distinct from the build's immutable source/builder SHAs above and does not change the published packages.
