# Repaired native position-anchor acceptance

This iteration pins client 1efc826b85c305bd60210aa705444114c1a0d5e2 and unchanged isolated server 5adc23da173c5f20188d79aafe8fcc1e656eb38a. The lean proof run 39736562648 reproduced the exact baseline missing-anchor failure and passed all 12 fixed native tests; complete Flutter validation must also pass before this workflow is pushed.

Only source identity, the bounded main transition, and exact native getter instrumentation hashes change. The new native AudioPlayer.m baseline is ecec29e1f913f0dca944ca3fb2e45a7ad96a138391af59f99ca3f46dfd5b65b3. Adding the same two read-only getters produces dfc408d533c30fe95b8d0a9ad2284f2266fdbaba3377da2bde372fcaad4441c7; exact removal reconstructs the source bytes. Header and harness behavior are unchanged. The existing prepare transformation produces dfdd215375ac1afd5a90e278733f5ca1a1ef5683317f95526933b5b6fe758532.

Normal Handoff, actual delayed media, cancellation, three-client Follow, authority transfer, 35-second continuity, non-unit rate change and paused-task restoration all run again. The original 50 ms settling threshold, five-second deadline and continuous measurement windows remain unchanged. No samples are excluded and no assertion is weakened. Diagnostics retain the existing finite position and lifecycle fields to detect residual bias or correction storms. Physical audibility remains outside hosted acceptance.

The same approved temporary sandbox network permissions and existing source credential are used. No stable release, package artifact, deployment, new credential or production setting. Both native teardown and private-source cleanup remain mandatory. Final package rebuilding is blocked until the complete strict matrix passes.
