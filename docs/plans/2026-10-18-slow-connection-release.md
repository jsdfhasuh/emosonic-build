# Slow-connection timeout release

## Scope

Publish EmoSonic 1.0.10+27 from the authorized master merge of the slow-connection
change. The release retains Android package/signing identity, Windows installer
identity, the existing update formats, and the existing manual build-only and
publish-stable paths. No credentials or server configuration change is required.

## Source

- Slow-connection commit: `40bddf9170c640e2ccb7f100a62a7b6bdfabab2e`.
- Genuine merge: `2f96cbebe2bb6972be6f6028566014aa3ff2eba0`.
- Version-only commit and initial release candidate:
  `3d31c15c14e3bb5613455c2cdb409f389d1a225a`.
- API connection attempts become 8/10/12 seconds within one 45-second overall
  request budget. Android queue hydration becomes 30 seconds, and dependent
  preparation/restore waits allow 31 seconds. Dedicated probes are unchanged.
- Existing cancellation, stale-source cleanup, native start ACK, and strict-v2
  personal-lab restrictions are preserved. The hydration timeout does not forcibly
  abort a native load; its late completion remains guarded and cleaned up.

## Verification and release gates

The private source CI on this candidate did not establish a runner (job has no
steps and runner_id 0). This is not a passing CI result. Add a bounded public
builder validation job using the same pinned Flutter 3.41.2 and exact private
source snapshot, with private output suppressed and no source/test logs uploaded.
It must run dependency resolution, code generation, navigation consistency,
vendor provenance, full analysis and the complete Flutter suite. Report only
sanitized pass/fail metadata and numeric counts. Preserve source identity and
tracked bytes across validation. Both platform builds and publication depend on
this job. Keep strict failure behavior rather than ignoring analyzer/test issues.

Retain the native Java 104-check gate, full Android debug compilation, signed
release build, fresh-runner Android inspection, original Windows build/installer,
fresh-runner Windows inspection, exact six-asset publication checks, and monotonic
stable version checks. Update the existing one-off request binding to this exact
parent, source, version, request path and commit message; force pushes remain
disallowed. Re-read refs before publication and never overwrite an existing tag.

## Acceptance limits

Automated release checks do not establish real-device playback or upgrades.
Android and Windows installation, retained data/downloads, audible playback,
slow/stalled loading, rapid source changes, offline cold start, OS media lifecycle
and in-app updating remain pending user validation. The installed Android APK's
signing mismatch is unresolved; do not uninstall the existing app or clear data
to force an update. No server deployment or production-readiness claim is made.

## Results

Pending. The final verification report will record the actual immutable source,
builder, run, test counts, hashes and device limitations after publication.
