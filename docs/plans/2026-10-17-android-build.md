# Historical Android-only plan

Superseded by the dual-platform stable pipeline and [master/source-version automation](2026-10-17-master-version-automation.md). See the current README for operation and permissions.

The initial public builder added isolated preparation, Android compilation, independent signature inspection and publication jobs. It preserved the existing Android application ID and signing certificate, enforced increasing release versions and prohibited overwriting assets. An Android-only prerelease strategy was initially used because the existing Windows updater also reads latest.

The owner subsequently approved real Windows builds and complete stable releases. Android-only prereleases and manual ref/version selection are no longer supported. Source commit allowlists are no longer part of the current design. No product build or release was executed during this infrastructure work.
