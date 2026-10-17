# Historical master compatibility review

The initial source-commit allowlist approach was superseded by the owner's approval of [continuous master/source-version automation](2026-10-17-master-version-automation.md). There is no ongoing per-commit review requirement. See the current README for operation.

A read-only comparison of e36793bd0d7df943c36326667df4a5a16b606878 against f5d1dec2c8d5b90def0fd23c1b4a1173a7e9e1d1 covered complete Git trees (580 changed blobs across 69 commits) and focused on build configuration, dependencies, signing, Windows installation identity and updater contracts. This was not a full audit of runtime changes.

At that point Android/Windows native configuration, the Windows batch entrypoint and Inno template were unchanged. Pubspec moved from 1.0.6+22 to 1.0.6+23 and Dio from ^5.3.0 to ^5.11.0; updater timeout handling was adapted, while latest lookup, version parsing and platform asset selection remained unchanged. The product release workflow became manual-only. No tracked pubspec lockfile was present.

The earlier change passed 33 local pipeline tests, Python compilation, actionlint (without shellcheck/pyflakes) and whitespace checks. No actual product build or release was performed. Source-provided integration test results were not represented as tests run by the builder task.

Strict realtime protocol 2.9/r19 server integration and deployment remained unverified. This remains separate from ordinary library playback and device upgrade acceptance; no server was deployed as part of this task.
