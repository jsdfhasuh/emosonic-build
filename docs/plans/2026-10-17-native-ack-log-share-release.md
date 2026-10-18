# Native playback ACK and diagnostic-log sharing release

## Status and authorization boundary

Prepared locally only. The candidate source is ecd827ec605577c31f3abcc3390fd53baf22df4c, version 1.0.9+26. It matches every file in the locally frozen snapshot 3c64228e4730b1f766ac9a4d775cf9d78fa7ca7d08ffdfa82eb39394b12a0658. Complete application validation now passed: 2,442/2,442 Flutter tests, full-project analysis, dependency resolution, code generation, navigation consistency, formatting, vendor integrity, whitespace and all four preserved regression probes, with no frozen-source changes. The coordinating parent approved proceeding after these gates. Native release compilation and both independent binary verifiers must still pass before publication.

Fresh inventory: builder main `8b015c2cf4c86397acbe2491569fcb4b999f103b`; stable latest `v1.0.8+25`; releases and tags contain no higher/reserved version. `1.0.9+26` is selected, subject to the final inventory check.

## Pipeline design

Reuse the six-job stable pipeline and official signing identities. Add an Android-native gate before materializing the release keystore or signing properties. Following dependency resolution/code generation, require just_audio to resolve to the committed vendored Android plugin. Compile the actual production NativeStartGate.java and its committed standalone NativeStartGateTest.java with Temurin Java 17 javac --release 8, then execute the generated test class with java -ea. Require both produced class files and the exact success marker/count (currently 104 checks); any absent source/class, nonzero command, missing marker or count mismatch blocks signing. These are deterministic Java main-harness checks, not JUnit tests. Next compile the real Android app and complete vendored native plugin with a debug APK build. Private compiler output remains suppressed and is not uploaded.

Only after these native gates pass may the Android release build materialize signing files, compile the signed release, and stage the three-file Android bundle. The independent Android verifier still checks certificate, package ID, version and all three ABIs. Windows uses the same final source SHA/version, and its independent verifier retains the original installation identity, embedded version and x64 checks. Publication still requires all five dependencies, both independent verifier digests and exactly six checked uploaded assets before latest promotion.

One fixed request is tied to the true current builder parent, exact commit message, request path/content, source SHA and version. Ordinary pushes cannot sign or publish. Keep manual build-only/publish-stable behavior intact. Every remote repository write uses GitHub create_tree/create_commit with the true parent and update_ref with expected_sha and force=false. No synthetic local Git history is pushed.

## Validation and final evidence

Before publication: all synthetic pipeline tests, Python compileall, workflow actionlint, final source validation and review. After publication: all six jobs terminal success, native test execution and the exact 104-check success count in build logs, independent binary verification, exact stable latest, six assets downloaded and SHA-256/size checked, both manifests cross-checked against fixed source/builder/run/version identities. Never overwrite or reuse an existing release/tag/asset.

## Unchanged acceptance limits

Android and Windows real-device installation, upgrade/data retention, actual audio, offline cold start, OS/media lifecycle and end-to-end update behavior remain NOT_RUN / PENDING_USER_VALIDATION. No server deployment or strict-v2 server acceptance is implied. A native Media3 playing observation does not prove audible output on the user's device. The existing phone's signing conflict is not resolved by preserving historical GitHub signing identity. On signature mismatch, stop; do not uninstall or clear application data to force installation. Preserve downloaded music and user data. Do not mark the previous F02 gap complete before final implementation and automated validation evidence exists.
