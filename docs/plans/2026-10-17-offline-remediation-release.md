# Offline review remediation stable release plan

Date: 2026-10-17 UTC

## Scope and fixed source

Publish the already-delivered master remediation as the next Android and Windows stable release. Current source master is 9e210d039bb42ded402097809af60ef6d570ea8e, which differs from validated source 8445e8af1467de7e97e5a0e51c57d1ff42efd260 only in two documentation files. Change only pubspec.yaml version from 1.0.7+24 to 1.0.8+25, commit with an expected-head lease, then pin its full SHA in one exact push request. Release and tag inventories currently end at v1.0.7+24. Recheck version uniqueness and monotonicity in prepare and publish. Do not merge the independent diagnostic-log sharing branch or change the backend.

## Implementation

Reuse the existing six-job Android and Windows stable pipeline, environment names, signing configuration, package identities, independent binary verifiers, six-asset publication, and stable latest promotion gates. Replace the expired one-off push authorization with a single request for 1.0.8+25, bound to the current builder parent deb59cc8a6de0cc17a9100b38b82d8a3ae2f43a3, exact commit message, exact request path and content, fixed source SHA and version. Ordinary pushes remain unable to sign or publish; manual mode remains unchanged. Do not read, output, or change Secrets, create credentials, change permissions, or add signing identities.

## Validation and acceptance

Run all synthetic pipeline tests, compileall and actionlint before pushing. Confirm the exact source version-only diff and builder diff remotely, then follow all six jobs to terminal success. Verify stable latest, exact assets, SHA-256, both manifests, shared source and builder SHA, Android com.example.emosonic/versionCode 25/certificate 6db83974a60fe21ff18babf57a518fa34d05f63be49bdefc1fac7008a7f6942f, and existing Windows AppId {779F17F8-DA99-4D5B-A404-E7E2D17C1E65}. Never override an existing tag, release or asset.

## Limitations to include in release notes

Source validation: original suite 2213/2213, new remediation 108/108 and independent aggregate 2321/2321 on source 8445e8af. F01 and F03-F14 are implemented. F02 completion outbox/retry is repaired, but immediate Android real-start ACK remains PARTIAL/OPEN. No backend bridge is part of this release. Independent original audits retain 9 PASS / 4 FAIL with explanations in the private source validation report. Private source CI and public package-build CI must be reported separately; the cause of missing private CI execution evidence is unconfirmed.

Real-device installation, upgrades, actual audio, data compatibility and end-to-end checks remain NOT_RUN/PENDING_USER_VALIDATION. Android certificate equality to historical GitHub packages does not establish compatibility with the APK already installed on the user's phone. If Android reports a signature mismatch, stop; do not uninstall or clear application data to force installation. Preserve existing downloaded music and data. The user will perform device validation.
