# Composed attribution preflight correction

Request 98 keeps product f6251a2a0e6441f174d05b488bc0fb1b41d52e39, auxiliary
895af76dbd648acc73497bb41fb32f36b70c88d7, server, version, source validation and
all native acceptance predicates unchanged. It follows builder
40b9833dd9e99f62880175362e1b94a3aa178e9e.

Request 97 run 39974898854 failed before native compilation. Its preparation,
40-case final precision proof, 70/63 unit layers and server preflight passed;
both cleanups passed. The attribution helper retained two request96 harness
hashes after the reviewed pending-state transform changed the composed harness.
Its exact timing verifier therefore rejected the mismatch before Flutter could
run either attribution phase. The private CLI exception was suppressed; the
existing finite diagnostic begins only inside the Flutter phase. No attribution
assertion failure or product/native regression is established by that run.

This correction changes only those two derived attribution constants to the
already reviewed lifecycle/timing hashes. No Dart fixture, production source,
observer payload, strict test body or acceptance assertion changes. The existing
script checksum is updated. No diagnostic expansion is needed for this proven
preflight defect.

Three tests in normal public discovery now compare the actual independently
pinned readiness/lifecycle/timing/attribution modules, reject stale attribution
constants, and invoke the actual verifier against altered timing/lifecycle
modules. Unlike the historical mocked compatibility test, the new pin equality
regression cannot make a stale value agree by copying it into a mock. It runs in
ordinary preparation before any private checkout or native build.

Local verification also invoked the actual attribution timing preflight on the
complete composed request97 source and manifests with the existing recovery and
debug options: old pins fail, corrected pins pass, every source byte remains
unchanged and zero Flutter processes are launched. This is not a substitute for
the hosted six-plus-six attribution tests or the full strict native matrix.

The 40 final-method bodies and the 70 historical / 63 final-compatible coverage
remain intact. Request96's genuine initial strict pass and request97's failed
preflight remain distinct evidence. Publication and any native execution require
the normal reviewed successor workflow; this document does not claim them passed.
