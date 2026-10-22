# Same-source Follow stop diagnostics

## Evidence and scope

Native run 39798198112 failed the unchanged initial Follow alignment gate: about 80 ms follower lag after 5.275 s. The completed same-item seek tape did not show the previous backward replay, and final native/Dart anchor residuals were about 1 ms. This does not establish complete Follow acceptance. Both cleanup steps completed; private runtime logs were intentionally removed.

Repeat the isolated matrix at client `e6f7ea84d8ce9a1a29e56f5a083173a9810e4316` and server `5adc23da173c5f20188d79aafe8fcc1e656eb38a`, retaining only bounded existing log events and existing endpoint timing fields. The full source validation gate remains run 39795770390. No production source, native observer, deadline, precision threshold, rate cap, account policy, credential destination, sandbox permission, or release path changes.

## Questions

- Which existing cancellation, exhaustion, ordinary speed-correction, or nominal-restoration event occurs before the failed measurement?
- What rates were requested, separately from measured native rates?
- Do the source and follower's existing estimated server-clock offsets differ, and does the endpoint's projected target differ from the simultaneous native reference?

## Interpretation limits

Log order and relative log-wall times are not a monotonic clock pairing. There is no existing recovery-arm timestamp, so exact ownership-budget age remains unavailable. A speed-setting invocation is not a successful native rate change. Missing cancellation markers do not prove no recovery admission. Endpoint fields describe their observation time, not a past controller stop-time fact. A clock-offset hypothesis is not a demonstrated cause until actual observations and source semantics agree.

Both Follow and extended Handoff remain required. A failed earlier stage is not a pass for skipped stages. No final packages, stable release, or server deployment are authorized by this diagnostic transition.
