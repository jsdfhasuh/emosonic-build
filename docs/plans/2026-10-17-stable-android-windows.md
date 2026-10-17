# Historical dual-platform stable plan

Source/version selection is superseded by [master/source-version automation](2026-10-17-master-version-automation.md). See the current README for operation and permissions.

The owner approved adding Windows so existing Android and Windows clients can both use the original latest-release updater. The implementation added a Windows build environment and an independent verifier, preserved the original installation identity, and required matching source SHA/version across both platforms before publishing all six assets as a stable latest release.

The initial implementation used manual version selection, a temporary Windows pubspec override and source script/template blob pins. Those mechanisms have been removed: current runs resolve only master, read its exact source version and leave pubspec unchanged. Original package/signing/installer identity checks and separate publisher permissions remain.

Local regression tests covered missing platforms, provenance mismatches, duplicate tags, corrupted uploads and failed promotion. No actual product compilation, Actions run or release was performed during this infrastructure work.
