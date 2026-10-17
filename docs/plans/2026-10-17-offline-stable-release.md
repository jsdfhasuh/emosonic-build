# Offline stable 1.0.7+24 release

The owner authorized merging and publishing on 2026-10-17. PR #4 was merged normally, then pubspec was raised to 1.0.7+24 at source ec2f9dedd04a11ccdbcf72b8eedf8e91502a5c9c. No behavior or dependency change is part of this version bump.

Reuse android.yml and pipeline.py, including both platform builders, independent verifiers, and the six-asset draft-to-latest promotion. Retain manual workflow_dispatch for future normal use. Add one bounded push request for this publication only: fixed main predecessor, commit message, request payload, source SHA and version. Reject forced/new/deleted refs, wrong workflow, mismatched source, ordinary pushes and version conflicts. No credential or environment/branch protection changes.

Repair the existing stable Android SDK setup using the proven candidate helper: use installed build-tools 36.0.0 or an absolute sdkmanager path. Keep its pinned identity and all verification gates. Publish honest device-validation limits in release notes. Validate synthetic gate tests, compileall and actionlint before the trigger commit, then monitor both platform jobs and verify latest plus every asset. First failures remain evidence; never blindly rerun or replace a published asset.

This run is not physical-device acceptance. Installation/upgrade, audio, offline cold start, OS lifecycle/media, data compatibility and M01–M15 remain pending user validation; personal-lab policy and server.strictV2Implemented=false remain unchanged. Private-repository CI has not executed its tests. Public builder results do not remove that gate.
