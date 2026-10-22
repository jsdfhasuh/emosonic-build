# Ordinary-startup regression verification

The earlier Handoff repair added a final lease fence in a shared trigger. This request verifies the narrow correction that scopes the new fence to Handoff initiation, preserving every pre-existing ordinary-path fence.

- Test-only baseline: `440d9345be2976fb21c3515b12078a7baccf4daa`, production bytes inherited from `19639161be7945884d998ecd268d9bc30afcf02d`.
- Fixed source: `01967c853a4e6020097e9a2da61f9785b470ff7d`.
- Require the exact marked ordinary startup failure on baseline, then complete analyzer/test/provenance/byte-integrity validation on fixed source. Original Handoff regression and cancellation boundaries remain in the full suite.
- No native clients, packages, release, deployment, new credentials or security changes in this request. Native matrix resumes separately after this gate passes.
- Source remains private and temporary outputs are removed. Only finite validation summaries are retained.
