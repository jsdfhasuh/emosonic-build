# Independent Follow matrix first

Run39768813656 passed normal1.5x and delayed0.8x Handoff, but the second cold target generation never connected before its100s registration deadline. Cancellation and Follow were not reached; that cold-start failure remains unresolved.

This same-client466f56d9/server5adc iteration changes only the order of the two existing independently initialized server/client matrices: Follow first, then extended Handoff. Both remain required, and any failure leaves the workflow failed. Each matrix retains its original cleanup and every assertion, deadline and threshold. No product code, credentials, native instrumentation or permissions change. Successful exact validation39767536382 and historical causal proof39745934922 remain mandatory. No packages, release or deployment.
