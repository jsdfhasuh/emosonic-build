# Refresh the Windows unpacker pin — 2026-11-12

## Failure and verified upstream change

Stable publication run `43135317119`, attempt 2, stopped in Windows tool setup
with `Downloaded Windows tool digest mismatch`, before private source fetch or
application compilation. The previously reviewed `ui_2_2_13/innounp-2.zip` URL
now serves a different upstream asset.

The official `jrathlev/InnoUnpacker-Windows-GUI` release asset `695694723` was
created on 2026-10-31. Its GitHub-reported digest and independently downloaded
archive digest both equal
`f8e45c9676bebc7d7570108ab572673b541fcf7a7d3d24a04319ac6b5315b4e8`.
The contained `innounp.exe` digest is
`ab58400460cfda503ec88702dd3d82f6ee207b28e0548c9f8861ef008f85b644`.
Windows file-version resources, the bundled HTML heading and `innounp-cl.txt`
identify version **2.71.3**. The bundled changelog dates it 2026-10-31 and adds
Inno Setup 7.1.1 support. Official upstream source commit
`75ded58da3a81c029db4f73ab803b9b4154400e9`, dated 2026-10-31 and titled
`Update to 2.71.3`, updates `innounp-2/bin/innounp-2.zip` as well.
The outer release description still says 2.71.2, so
that description alone is insufficient evidence of the actual download version.
No downloaded executable was run during this provenance inspection.

Inno Setup 6.7.3 still matches the existing archive pin; its compiler version,
archive hash and executable hash do not change.

## Minimal repair and validation

Update only the unpacker version, archive digest and executable digest in
`policy.json`, and align the README's version. Keep the existing upstream URL,
all download/executable digest checks, package inspection, source validation,
signature policy, release-history checks and publication gates unchanged.

The historical final-package unit test also pins the complete `policy.json`
bytes. Refresh that one expected fingerprint to
`bc0b2b6ead32a118752fa715238b08cef579ba65b74762de5682c46092750d86`
for this explicitly reviewed three-field tool update. Retain the whole-file
assertion and all other protected pipeline/workflow/helper fingerprints.

Run the existing public pipeline unit tests, including rejection of incorrect
tool and package hashes. The subsequent Windows build and independent Windows
verifier must both use the reviewed 2.71.3 binary; accepting a new download hash
alone is insufficient validation.

Local validation results:

- Core pipeline/Windows contracts: 42 tests passed on Windows.
- Refreshed protected-file fingerprint assertion: passed; all other expected
  protected-file hashes and the native contract count remain unchanged.
- Complete 951-test run on this Windows host: not passing. The unchanged
  baseline has 18 failures and 53 errors; the initial repair has the same
  failures/errors plus the intentionally changed policy fingerprint. Examples
  include POSIX path/mode and mocked tool-launch assumptions. The sole added
  fingerprint failure is resolved by the explicit reviewed baseline refresh.
  This is not reported as a passing complete suite.
- The new run's Linux prepare job must pass all 951 tests before source
  validation or either application build can proceed.

Commit/push this build-repository repair, then dispatch a new `publish-stable`
run on `main`. Re-running the old workflow cannot pick up the repaired policy
because GitHub freezes the builder commit for that run. Keep application source
`45667515c94d36e06b5030f7043875a7a133c857` / `1.0.13+30` unchanged and verify the
new prepare job freezes that source again.

The previous stable release stays available until both builds and independent
checks succeed. On another tool mismatch, stop and inspect the changed asset;
never add an unverified fallback or turn off digest checks. Reverting this policy
change restores the old pin and intentionally rejects the replaced upstream
asset. No application installation or real-device acceptance is performed here.
