"""Fixed bounded recovery budget proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = 'ffd425af33fe9c84f100c9d1b8e30e5047b7c6bc'
MESSAGE = 'test: prove bounded Follow recovery budget 20261024'
WORKFLOW = 'follow-bounded-budget-proof.yml'
REQUEST_PATH = 'requests/follow-bounded-budget-proof-20261024.json'
SOURCE_REF = 'refs/heads/test/follow-bounded-budget-20261024'
SOURCE_SHA = 'a7597e6d8d3d33cee70d792098249dba5d5c779d'
BASELINE_SHA = '72e524134c81becacf80ba8ff3f3d7562328347f'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_bounded_budget/test_inventory.json'
INVENTORY_SHA256 = 'c420f500801d4d86069c7ea899eb61b37bcfa6c6e1ac65e2836de7d1fcce6f06'
ASSERTION_MARKER = 'BOUNDED_FIVE_SECOND_EXPIRY_PREVENTED_NOMINAL_SETTLEMENT'
EXPECTED_COUNT = 4
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-bounded-budget-expected-red-proof', attempt=111)


def main():
    # Unresolved or inconsistent pins must fail before any context/fetch action.
    if not (type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/test/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
            and type(INVENTORY_PATH) is str and re.fullmatch(r'tool/[a-z0-9_]+/test_inventory\.json', INVENTORY_PATH)
            and type(ASSERTION_MARKER) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{1,127}', ASSERTION_MARKER)
            and type(EXPECTED_COUNT) is int and EXPECTED_COUNT == 4
            and REQUEST.get('source_sha') == SOURCE_SHA and REQUEST.get('source_ref') == SOURCE_REF
            and REQUEST.get('baseline_sha') == BASELINE_SHA):
        print('ERROR: Bounded recovery budget proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
