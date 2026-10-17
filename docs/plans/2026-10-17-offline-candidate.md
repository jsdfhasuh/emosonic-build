# Fixed offline Android test build

Build only private source commit `601d6b4d811da18f8b437febe6f677df5cfa4da2`
from the offline browsing/playback candidate. Do not merge or modify source master,
publish a release, change Secrets/permissions, or alter the stable workflow.

The isolated workflow is armed only for a main push from builder parent
`b19087a0fc8d2a27b35d8151c5a59fa791c8c4db`, changing the dedicated request file,
with the exact documented commit message. Later ordinary pushes cannot build.
Retries of that same GitHub run are allowed; there is no new dispatch endpoint.

The source pubspec remains `1.0.6+23`. The APK uses visible versionName
`1.0.6-offline.601d6b4` and versionCode `23`, original application ID and signing
certificate. A no-Secrets preflight downloads the hash-pinned existing release
APK and verifies its actual package/version/signature before compilation starts.
The test package is manually installed, not offered through the stable updater.
Do not uninstall the existing application automatically. Back up application data
first: this test uses the same data and may migrate its database; reinstalling an
old build is not guaranteed to safely reverse migrations. A device with a newer
versionCode may reject this package; do not force a downgrade.

Build a universal APK, including arm64-v8a, with private compiler output suppressed.
Keep source read token only in the fetch step and signing inputs only in build.
The original key is transient. Upload only the APK, checksum and test manifest;
independently inspect them on a fresh runner without user Secrets. Artifacts last
one day. Public Actions cannot sandbox trusted source/dependency behavior; do not
upload private source, raw logs, symbols, credential files or dependency caches.

Validate with all existing pipeline tests, focused candidate gate/provenance and
APK tests, Python compilation and workflow syntax checks. Real-device offline
browsing/playback, coverage install and data preservation remain user validation.

## Tool setup retry, 2026-10-17

Original run [39024877575](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39024877575)
started a public Ubuntu runner and passed all 50 tests. It failed before any
private-source/signing step because sdkmanager was not on PATH (exit 127).
The original failure is retained. Request attempt 2 explicitly arms one new
transition from b19087a, with commit message
`build: retry offline candidate 601d6b4 with explicit SDK tools`.
It first uses already-installed pinned inspection tools, otherwise invokes
sdkmanager by its official SDK path. Source, signing, version and no-publish
restrictions are unchanged. Later unrelated pushes remain rejected.

## Verified build outcome

Run [39025031880](https://github.com/jsdfhasuh/emosonic-build/actions/runs/39025031880)
completed successfully on 2026-10-17 at 10:38:14 UTC, builder
`98936d5b981b16df231a08964b03af7a1007b667`. Preflight passed 53 tests
and inspected the hash-pinned baseline APK at versionCode 23. The candidate
compiled and passed original certificate/application identity, version, ABI and
provenance checks in both the build job and a separate no-user-Secrets runner.

APK size: 76,589,091 bytes. SHA-256:
`106dfd07980f86c8756689995620bfd9387686c47d8c3a59f95fd1568f076f6a`.
Artifact 12098780478 contains exactly the APK, matching checksum and sanitized
manifest. Its ZIP digest is
`f990036f6b82c3262f251b36a5f0005fab4cabb650f64a98a0deeb08624a4a1e`;
the retrieved copy was independently checked against both digests and manifest.
The CI artifact expires 2026-10-18 10:37:50 UTC.

No source merge, stable Release, Windows build or physical-device installation
was performed. Offline behavior, installation and existing-data compatibility
remain pending user validation. The existing stable workflow was not modified;
its bare sdkmanager invocation still needs the same PATH fix before its first
authorized release build.
