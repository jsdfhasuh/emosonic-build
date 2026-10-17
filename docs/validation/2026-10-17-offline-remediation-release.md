# Offline remediation 1.0.8+25 release verification

Date: 2026-10-17 UTC

## Result

**Published as stable latest at 2026-10-17 22:19:36 UTC.** [Release v1.0.8+25](https://github.com/jsdfhasuh/emosonic-releases/releases/tag/v1.0.8%2B25), release ID 416103678, is neither draft nor prerelease. All six jobs in [run 39073984985](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39073984985) succeeded on the first attempt. All six release assets were subsequently downloaded in the cloud and independently hashed; their byte lengths and SHA-256 values match the GitHub release API. Both downloaded manifests and checksum text files match the packages.

## Immutable coordinates and source changes

- Validated application source: 8445e8af1467de7e97e5a0e51c57d1ff42efd260.
- Remediation delivery: 9e210d039bb42ded402097809af60ef6d570ea8e, with exactly two documentation changes after the validated source.
- Release source: [fe045684e89a18e1fb51b39c9483be6d1f6ac324](https://github.com/jsdfhasuh/emosonic/commit/fe045684e89a18e1fb51b39c9483be6d1f6ac324), with exactly one version-line change after delivery: pubspec.yaml 1.0.7+24 to 1.0.8+25.
- Builder: [596d77e3fe595f3000f3e2f09bd8c3401aebf1ea](https://github.com/jsdfhasuh/emosonic-build/commit/596d77e3fe595f3000f3e2f09bd8c3401aebf1ea).
- Fixed request: requests/stable-1.0.8-25.json, attempt 1, publish-stable.
- Both branch updates used expected-head leases and were read back. No force push or diagnostic-log-sharing branch merge occurred.
- No backend changes, credentials, Secrets, permissions, signing identity or user-computer changes were made.

## Checks

Local builder tests: **68 passed**. Python compileall passed. Actionlint passed for both workflows, with shellcheck and pyflakes integrations disabled. A separate read-only review found no blocking changes to authorization or package/release gates.

| Job | ID | Result |
| --- | --- | --- |
| prepare | 117517225280 | success |
| build Android | 117517258320 | success |
| build-windows | 117517258305 | success |
| verify Android | 117518921565 | success |
| verify-windows | 117518812683 | success |
| publish | 117518968050 | success |

The independent Android runner verified the actual APK signature, package ID com.example.emosonic, versionName 1.0.8, versionCode 25, non-debug state, exact ABI set arm64-v8a/armeabi-v7a/x86_64, and provenance. Certificate SHA-256 remains 6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f.

The independent Windows runner extracted and inspected the installer without installing or running the application. It verified the existing AppId {779F17F8-DA99-4D5B-A404-E7E2D17C1E65}, per-user installation directory, lowest privileges, x64 application, embedded numeric version 1.0.8.25 and textual version 1.0.8+25, expected complete payload and unchanged NotSigned Authenticode policy. The manifest retains the escaped Inno form of AppId.

The publishing job consumed both independent verifier digests, checked all six uploaded file sizes and hashes, and promoted the release to stable latest. The post-publication cloud download check reconfirmed all six hashes, both checksum texts and matching manifests. Binary signature/embedded-version inspection was performed in independent CI runners; the subsequent local cloud check was download/digest/provenance verification, not a second installation or device test.

## Assets

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| android-manifest.json | 774 | 3846cf4e4160dd75469545bbb8ed212d3f0c69a29a6c5d529c137f56b74c198e |
| emosonic_android_v1.0.8+25.apk | 76982291 | cdf0f806fcb763de00f754f12bc61bf9d778396c72c6a9961e15665e4163419b |
| emosonic_android_v1.0.8+25.apk.sha256 | 97 | 0f4b4497dbdaf02bab7bb6bd1a90ae6bc869ba5424a6967bd8ab883aebde8d93 |
| emosonic_windows_v1.0.8+25_setup.exe | 14025390 | 29f1687e1a49b92c973e0991ada4a15cd72c0432c6696a68937cfa75c60700c0 |
| emosonic_windows_v1.0.8+25_setup.exe.sha256 | 103 | c18b6998121a38b6a1bd042ee1a9240c49491fac3066695f47844413dc629058 |
| windows-manifest.json | 819 | 84b1b816695bc22e8a4e7ce416a10aa7655c71aae4dba78a0d8b3c396ccb3aee |

[Android APK](https://github.com/jsdfhasuh/emosonic-releases/releases/download/v1.0.8%2B25/emosonic_android_v1.0.8%2B25.apk) · [Windows installer](https://github.com/jsdfhasuh/emosonic-releases/releases/download/v1.0.8%2B25/emosonic_windows_v1.0.8%2B25_setup.exe)

## Application validation and remaining limits

Application tests were previously run on immutable source 8445e8af: original suite 2213/2213, new remediation suite 108/108 and independent full aggregate 2321/2321 passed. The release changed only two documentation files and the version line after that tested application source. This package workflow does not claim a new full Flutter test run. Original independent audit probes remain 9 PASS / 4 FAIL as explained in the [source remediation report](https://github.com/jsdfhasuh/emosonic/blob/fe045684e89a18e1fb51b39c9483be6d1f6ac324/docs/validation/2026-10-18-offline-review-remediation.md).

F01 and F03-F14 are implemented. F02 completion outbox and account-scoped retry are repaired, but immediate Android real-start ACK remains **PARTIAL / OPEN**. No server bridge or deployment was attempted.

The separate private source [Client validation run 39073812859](https://github.com/jsdfhasuh/emosonic/actions/runs/39073812859) for fe045684 is **failure**. Its returned job has runner_name empty and steps empty. There is no verified test-execution evidence; its cause is unconfirmed. Public package build success does not mark private source CI passed.

Real-device installation, upgrades, actual audio, offline cold start, data compatibility, OS/media lifecycle and the device matrices remain **NOT_RUN / PENDING_USER_VALIDATION**. The user performs these tests; the source report contains detailed steps, expected results, log markers and return format. Acceptance remains personal-lab only.

**If Android reports a signature mismatch, stop. Do not uninstall the existing app or clear its data to force installation. Preserve downloaded music and application data.** Matching the historical GitHub release certificate does not establish compatibility with the APK already installed on the phone.

## Follow-up

Publication and verification are complete. Await user device-test observations and Android controller/Windows authority logs. Do not infer that successful package validation resolves F02 or the installed-phone signature conflict.
