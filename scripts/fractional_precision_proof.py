"""Fixed fractional precision proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '208edd8a07916465c33d4c2d2828def1f58eeb5d'
MESSAGE = 'test: prove fractional native precision boundary 20261023'
WORKFLOW = 'fractional-precision-proof.yml'
REQUEST_PATH = 'requests/fractional-precision-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-fractional-precision-20261023'
SOURCE_SHA = '183716155d5424471b59a990154acf4772477be8'
BASELINE_SHA = '17a35e301ca7182d4fed1114c7e42a940f2d208e'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_fractional_precision/test_inventory.json'
INVENTORY_SHA256 = '65459d5e218e74e0fd3fa426f17f3be3b328655834b7553ec349d7fadab6a980'
ASSERTION_MARKER = 'FOLLOW_FRACTIONAL_DRIFT_SETTLED_OUTSIDE_TOLERANCE'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-fractional-precision-expected-red-proof', attempt=85)


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
        print('ERROR: Fractional precision proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
