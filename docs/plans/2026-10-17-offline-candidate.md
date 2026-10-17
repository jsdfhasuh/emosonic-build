# Fixed offline Android test build

Build only private source commit `601d6b4d811da18f8b437febe6f677df5cfa4da2`
from the offline browsing/playback candidate. Do not merge or modify source master,
publish a release, change Secrets/permissions, or alter the stable workflow.

The isolated workflow is armed only for a main push from builder parent
`f12dc154d0d8131fda516e7c4a1b5bde836ef3b0`, changing the dedicated request file,
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
