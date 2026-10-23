# Strict sampled Follow acceptance

This is an intentional disposable harness acceptance correction, not a product repair or a claim that earlier passes proved this stronger contract.

## Precision and coverage

- Pin the lab's reported tolerance to 50 ms and lead compensation to numeric zero.
- At every existing paired observation, require absolute native timestamp-aligned drift plus the full reported time uncertainty plus 1 media millisecond for the two rounded positions to be at most 50 ms. Existing uncertainty admission remains bounded at 25 ms.
- Source and follower requested/property rates must both be nominal within 0.0001 once settled. That epsilon compares rate representations; it does not prove physical slope. Both native players must also genuinely advance with matching identities and per-interval slope error below the existing 0.15 bound.
- Readiness requires two consecutive eligible advancing pairs. A within-cap correction may remain pending only within its original deadline and resets that witness. Malformed/outside-cap/unsafe identity evidence fails.
- Every existing tuple in each complete three-second measurement is checked. No unstable tuple is omitted, no failed window restarts, and cumulative average slope cannot replace the per-pair precision bound. Both native elapsed time and measurement wall time must reach three seconds before the unchanged five-second measurement timeout. A carried witness must have been observed within the existing 200 ms cadence when reused.
- The existing 35-second collection checks the same steady predicate on every 0.5-second tuple. Failures latch permanently. It does not rearm settling grace for drift, heartbeats, or repeated rate oscillations.
- This establishes finite sampled coverage (approximately 200 ms and 500 ms cadences plus read cost), not an assertion about unobserved time between samples. No poll, media-position read, sleep, playback command, or native instrumentation is added.

## Deadline origins and ownership

Initial Follow keeps its separate bounded 45-second task-ready acquisition, followed by five-second convergence from observed readiness. Acquisition and command-to-measurement-end durations are reported separately; alignment duration is not command-total duration.

Normal authority transfer and the explicit 0.8 rate command each capture one monotonic origin immediately before the existing command. Their five-second convergence deadlines include command/protocol time and carry across all intervening target/source measurements. The transfer origin is deliberately earlier than the unobserved actual authority takeover. Deliberately delayed standalone Handoff is not subject to this Follow budget.

The tracker consumes only existing tuples. While propagation is pending it freezes participant process/task identities and permits only the old or explicitly commanded authority. The actual matching completed Handoff supplies the new canonical epoch/controlVersion/queueRevision; no increment is guessed. Follower canonical agreement and full correction identity are required before eligibility. Heartbeat/data revisions are not control identities. Once settled, subsequent strict violations cannot buy another budget.

## Layered deterministic evidence

The frozen original discovery scope has six Python test files and 70 cases, independently checked against the exact source revision. Hosted discovery verifies all 70 exact case-name digests before any selection. Extra or missing files/cases fail closed.

- All 70 execute on the exact inverse-restored prior acceptance layer as historical provenance.
- 54 unchanged cases and nine metadata-only adapted alignment cases execute on final bytes, totaling 63. The metadata addition supplies only synthetic seek/play-intent booleans; original assertions and sample stimuli are unchanged.
- Seven superseded fixtures are explicitly mapped by exact identity digest to the required 35 final-method precision/transition cases. Five previously mocked rate windows now have actual source/follower three-second coverage, wrong-rate/task/deadline negatives, including persistent 0.832 at nominal 0.8 rejection. Two old loop fixtures omitted a transition origin; final loop tests establish the real tracker and cover steady success, immutable failure, and unsafe identity stopping dependent checks.
- The earlier 35-method readiness proof remains explicitly prior-layer provenance. The new 35-method proof runs both on the strict readiness layer and final composed observation layer. These overlapping layer executions are not a count of unique tests.

The packaged legacy inventory records the exact 70 identity digests, classification, source-file hashes, and final-case mapping without publishing private test names or source.

## Handoff audit: distinct unchanged semantics

Normal transfer uses an elapsed projection at 1.5 and raw absolute continuity error at most 1000 ms. Delayed transfer uses the same 1000 ms bound at 0.8. Neither has an uncertainty allowance and neither is a conservative 50 ms simultaneous-player guarantee. These predicates are unchanged.

Post-seek Handoff readiness admits requested position minus 1000 through requested position plus elapsed times expected rate plus 1000. Advancement requires positive intervals, nonnegative movement, bounded interval slope, greater than 1 ms movement and elapsed time greater than summed sampling uncertainty. The uncertainty here strengthens movement evidence, not the continuity-error threshold.

Standalone Handoff rate measurements retain the original three-second cumulative slope tolerance and nominal property comparison. Cancelled late-callback observation retains source ownership/playing, target non-playback/stopped, and at least 12 seconds of bounded source progression. Canonical consistency and source-release/provenance checks are unchanged. No new 50 ms Handoff contract is claimed.

A historical -48 ms drift with approximately 3.15 ms uncertainty was an old deadline failure. Its hypothetical rejection under the new conservative bound must not be mislabeled as the historical failure cause.
