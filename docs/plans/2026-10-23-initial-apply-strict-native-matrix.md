# Initial apply repair: strict native successor

Request 96 is a pin-only successor for client f6251a2a0e6441f174d05b488bc0fb1b41d52e39, server 5adc23da173c5f20188d79aafe8fcc1e656eb38a and version 1.0.10+27. No product or acceptance behavior is edited by this builder change.

Admission requires completed-success run 39966140487 at builder d03a90db5341ceed03eb2d200eae0b270804f0fc, workflow initial-apply-receipt-green.yml, including its exact focused, full-validation and cleanup steps. Its frozen manifest covers 254 cases in 33 suites, not the historical 243-case scope. The new component is 3+8 cases with inventory SHA256 5628a0ea2f6781ad78ed816f5e17f96157f0da9fb3a663be14f8b634d90b2306.

The c730-to-f625 Git tree comparison confirms all 16 native/lab paths unchanged, including the six original unit files. Native instrumentation and the public harness inverse chain remain unchanged. The unit gate retains 70 exact prior-provenance executions, 63 final-compatible executions and 35 final precision checks; these overlapping layers are not 168 unique tests.

The strict gate still requires nominal requested/property rates, two genuinely advancing alignment pairs, and conservative absolute drift plus time uncertainty plus one media-ms rounding allowance no greater than 50 ms. Every existing paired sample in the full three-second and 35-second steady windows is checked. Existing command-origin five-second transition deadlines, no-rearm rules, frozen ownership and original source/target release checks remain. Initial task acquisition remains separately bounded at 45 seconds before five-second convergence. These are finite sampled observations, not an inter-sample precision guarantee.

Both Follow and extended Handoff stages and both cleanups remain. Handoff retains its separate 1000 ms transfer-continuity contract. No new poll, native read, logger, timer, control or permission is introduced.

The rebased private auxiliary memory observer retains exactly the existing seek-recovery checkpoint schema and 32 operations; it does not provide a complete trace of the new initial-apply watcher. Its four-file child commit must be pinned and byte-inverted against f625 before execution. This plan is preparation only, not a native result or release approval.
