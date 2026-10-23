"""Fixed initial apply receipt proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '31f5bb104246aca265c836682593e943cd027cf2'
MESSAGE = 'test: prove initial apply native receipt consumption 20261023'
WORKFLOW = 'initial-apply-receipt-proof.yml'
REQUEST_PATH = 'requests/initial-apply-receipt-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-initial-apply-receipt-20261023'
SOURCE_SHA = 'b4b01cdf8edc38d5b5ed7ac189030c73a0b09509'
BASELINE_SHA = 'c7301a107fd1474ec0d22bb609426a435bc52584'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_initial_apply_receipt/test_inventory.json'
INVENTORY_SHA256 = 'eaa73e02369200e8d21a4e39e46973d7ebb882c34c5a8442ae5b9b77fd26e35d'
ASSERTION_MARKER = 'FOLLOW_INITIAL_APPLY_RECEIPT_WAITS_FOR_AUTHORITY_HEARTBEAT'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-initial-apply-receipt-expected-red-proof', attempt=91)


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
        print('ERROR: Initial apply receipt proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
