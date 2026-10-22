# Seek-aware native Follow readiness

## Frozen evidence

Client candidate: 01967c853a4e6020097e9a2da61f9785b470ff7d.
Server: 8e9a319002c0ffa6054cd98e06dd271070ed729b.
Source analysis and all 2,464 tests passed in run39718010580.

Run39719724687 passed normal Handoff, strict stream provenance, native rate/continuity, four-second delayed Handoff and cancellation with late media delivery. Its separate three-client Follow run failed at a premeasurement readiness assertion: the follower was paused/buffering on the sample after initial readiness. This was not a completed Follow/restoration test.

## Purpose and boundary

Native seek deliberately pauses the engine, enters buffering and restores the requested rate on completion. The existing alignment phase documents permitted premeasurement correction and already has one fixed five-second deadline, but asserts uninterrupted readiness before it can observe such a transition.

Do not classify arbitrary buffering as a correction. Only the disposable plugin copy gains read-only access to existing pending-seek and playing-intent fields. No production playback method, client commit, server algorithm, authorization guard or transport route changes.

A permitted seek-readiness sample must retain the exact source/follower task, connection, recovery and native-player identity; authority playback and requested rates remain valid. Only a decoded, ready native follower with explicit pending seek and retained play intent may temporarily be paused/buffering. Other states fail. A genuine pending seek may consume only the original fixed readiness deadline; it does not reset it. All subsequent native advancement, continuous rate/drift windows, Handoff source-release, cancellation, provenance and restoration assertions remain unchanged.

## Verification before triggering

- Deterministic unchanged-harness reproduction, then green readiness tests.
- Negative tests for sustained buffering, expired deadline, arbitrary pause, identity loss, wrong requested rate, and any bad continuous-measurement sample.
- Exact source fingerprints, narrow patch counts and hashes; copied native getter integrity verified after build and before measurements.
- Independent review of source-preserving getter instrumentation and readiness semantics.
- New bounded main push/request with exact parent, message, client/server commits and workflow identity. No broad dispatch, publishing or deployment.
- Re-run the complete real-server native Handoff and Follow/restoration matrix. A successful source suite or Handoff-only result is not full acceptance.

No new credential destinations, persistent access, host networking changes or sandbox entitlements are introduced. Only the previously approved network client/server permissions remain in temporary sandboxed test bundles. No Android/Windows package rebuild occurs in this diagnostic run. Physical audibility is outside this hosted evidence.
