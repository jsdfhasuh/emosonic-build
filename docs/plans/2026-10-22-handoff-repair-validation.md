# Handoff play-initiation repair validation

User requested iterative correction and testing after the fixed-source native matrix reported `commit_failed / playback_not_playing`. Preserve the previous failure evidence. No production server, release, credentials, or user computer changes.

This additive workflow pins a test-only baseline and a separately reviewed fixed candidate. The baseline differs from c381e75 only in the held-policy regression and plan. It must fail exactly the named assertion `HANDOFF_START_MUST_WAIT_FOR_SOURCE_POLICY`; compile, setup, missing, skipped or other failures are not accepted as reproduction. The candidate then runs the full existing source analysis/test/provenance/fingerprint gate. Only after that passes may the same-source native matrix run against server8e9a319.

Native validation retains all existing measurement assertions, deadlines, source-release ordering, real HTTP/SocketIO fixture, and approved temporary sandbox network entitlements. It covers ordinary, delayed and cancelled Handoff then Follow transfer/restoration. Keep finite diagnostic observations and private cleanup. No raw logs/private source uploaded. No Android/Windows packaging during repair iterations; final validated candidate packaging is separate.

Trigger is one fixed main transition from4afe4129 with exact marker and request; no general dispatch, arbitrary ref or broad future trigger. Scoped wrapper forbids publishing/package stages and restores context overrides. Public Python regression gate tests and independent review precede push. Both source SHAs, full test name and final request are required before trigger.
