"""Fixed ordinary slew transition proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = 'e8640f73beefcb4ddcc15ad3b7fa1499e5849c7d'
MESSAGE = 'test: prove ordinary slew transition ownership 20261023'
WORKFLOW = 'follow-ordinary-slew-proof.yml'
REQUEST_PATH = 'requests/follow-ordinary-slew-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-smooth-magnitude-20261023'
SOURCE_SHA = 'f042aa30cf2e10451f58429264a479650faa0fc6'
BASELINE_SHA = 'dca06e757b9d71663e3ffc7d8841775910fefe41'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_smooth_magnitude/test_inventory.json'
INVENTORY_SHA256 = 'b7daa2756def9540dce0d0572830deb6799ae9d36b3a970d25af1be1a99da246'
ASSERTION_MARKER = 'FOLLOW_SMOOTH_MAGNITUDE_CHATTER_REISSUED_NATIVE_RATE'
EXPECTED_COUNT = 4
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-ordinary-slew-expected-red-proof', attempt=69)


def main():
    # Unresolved or inconsistent pins must fail before any context/fetch action.
    if not (type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/test/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
            and type(INVENTORY_PATH) is str and re.fullmatch(r'tool/[a-z0-9_]+/test_inventory\.json', INVENTORY_PATH)
            and type(ASSERTION_MARKER) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{1,127}', ASSERTION_MARKER)
            and type(EXPECTED_COUNT) is int and 2 <= EXPECTED_COUNT <= 128
            and REQUEST.get('source_sha') == SOURCE_SHA and REQUEST.get('source_ref') == SOURCE_REF
            and REQUEST.get('baseline_sha') == BASELINE_SHA):
        print('ERROR: Ordinary slew proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
