# Modern macOS position-anchor validation

## Scope
Validate the exact reviewed client candidate 1efc826b85c305bd60210aa705444114c1a0d5e2 against test-only baseline 7e1c24ecffcce1a9a4f928ad6806207d86507547. The source branch is fix/darwin-position-anchor-20261022; version remains 1.0.10+27. Server candidate 5adc23da173c5f20188d79aafe8fcc1e656eb38a is recorded for subsequent integration, not launched by this gate.

The prior real-player run 39731106287 completed functional Handoff, delayed transfer, cancellation, Follow rate change and restoration, but failed the unchanged 50 ms / five-second sustained-drift requirement. A 69 ms Dart-versus-native follower position bias was observed. Immediate rate-change broadcasting has adverse historical evidence; the old periodic discontinuity path is not active on modern macOS.

The candidate introduces an explicit modern-macOS-only observer with a monotonic maximum five position reads/events per second, quality and lifecycle guards. This is new bounded sampling, not a claim of reusing an existing active callback. iOS and legacy registration remain unchanged. Vendor provenance explicitly records the native patch while preserving upstream hashes and license.

## Ordered proof
1. A bounded exact-parent main transition runs public pipeline tests and verifies the immutable source ref, SHA and version using the existing source-read credential.
2. A lean macOS job checks out the test-only baseline and requires exactly the causal missing-anchor assertion, not any failure containing a marker in a traceback. Compilation errors do not count as red.
3. The same frozen regression directory runs all 12 exact-method native tests against the fixed source. Inputs and complete source bytes are checked before and after both phases. No Flutter installation or native application build occurs in this job.
4. Only after native red/green passes, run full Flutter analysis, tests, vendor provenance and source-byte checks. The five new actual Dart consumer tests are included.
5. A later separately pinned real-server/native matrix is still required to establish convergence and performance. Synthetic proof is not native playback acceptance.

## Privacy and non-goals
No stable publication, package build, deployment, security changes or artifact upload. Private source, compiler output and test output remain in owned temporary storage and are removed. Only finite validated counts, categories and line/column diagnostics can leave the native proof process. Existing publisher and stable monotonic version checks are unchanged. Existing credential destination is unchanged.
