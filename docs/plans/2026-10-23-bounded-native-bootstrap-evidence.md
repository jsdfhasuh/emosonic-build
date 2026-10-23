# Bounded native bootstrap evidence

Request 100 retains product `f6251a2a0e6441f174d05b488bc0fb1b41d52e39`, server `5adc23da173c5f20188d79aafe8fcc1e656eb38a`, auxiliary `e19bf7da3bdee9bb202728a30ad7db38c883d29e`, and full-source prerequisite `39966140487`. It does not repair startup or change playback acceptance.

Request 99 passed attribution, analysis and compilation, but failed the initial 100-second registration wait before loading media or joining Follow. The follower's HTTP endpoint remained available with empty observation buffers, disconnected state and connection generation zero. An identity-match false value compares in-memory client fields, not persisted preferences. Native error output covers AVPlayer errors, not all asynchronous bootstrap errors. These observations do not identify the cause.

The existing failure path already reads each process-owned debug log, rejecting files above 8 MiB and reading at most the final 256 KiB. One disposable lifecycle hook passes those already-read bytes and lines to a finite classifier. It does not open another file, poll state, read a clock, retry startup or alter a deadline. Existing bundle, process, sentinel and non-symlink ownership checks remain unchanged.

Only framed `Main` startup connect/requested/failed markers and `EmoRealtimeClient` bootstrap markers are classified. The six fixed stages are client ID, device session ID, device alias, playback-context outbox, Follow recovery and Broadcast recovery. Their four statuses are started, completed, timed out and failed. Joining an active request, stale-attempt failure and connection abort also have bounded counters. Scope, identity, error type, error text, stack and timestamp suffixes are never exported. Unknown markers have only a count.

Byte coverage is whole-current-file, tail-only, partial or unavailable. Launch coverage is always unknown: log rotation, earlier truncated content and suppression are not ruled out. Zero counts never prove that startup was not called. Invalid encoding, long or partial lines are explicitly counted, and counters saturate. The existing file/read limits are unchanged.

All 40 strict acceptance tests and runtime methods remain unchanged. Exact removal of the one observer call and import name restores the complete request-99 attributed harness byte-for-byte. Updated lifecycle, timing and independent attribution hashes are checked by the actual composed verifier and CLI preflight. Native instrumentation, private auxiliary source transforms and source bytes are unchanged.

Local validation: 766 public tests, 40 final precision contracts, 35 prior readiness contracts, and the distinct 70 prior-provenance / 63 final-compatible / 40 final-precision unit layers pass. Actual extracted owned-log readers were exercised for all three roles and rejected a wrong process ID. The preflight makes zero Flutter or native invocations.

The populated three-client success report remains 511,542 bytes. The populated initial-readiness failure report, now including maximal bootstrap counters, is 523,765 bytes, below the unchanged 512 KiB regression bound. These figures apply to the tested report shapes, not arbitrary later nested failure reports. A new native run is pending; preparation success is not a synchronization result.
