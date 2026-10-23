"""Fixed native receipt consumption proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '3abb2333c51f26aeb00849ee8725aaa9ed4fea89'
MESSAGE = 'test: prove native receipt consumption ownership 20261023'
WORKFLOW = 'native-receipt-consumption-proof.yml'
REQUEST_PATH = 'requests/native-receipt-consumption-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-native-receipt-consumption-20261023'
SOURCE_SHA = 'af854f4802e616bf22f01df62055d4ce32635d77'
BASELINE_SHA = '28fc26149f5e4175fe952219b3cc5f9d18519c50'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_native_receipt_consumption/test_inventory.json'
INVENTORY_SHA256 = 'bb72be1172b73b0a53777951acdb295da4e2a3fa7dbc99480b18ec311d98c35d'
ASSERTION_MARKER = 'FOLLOW_NATIVE_RECEIPT_WAITS_FOR_RECOVERY_POLL'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-native-receipt-consumption-expected-red-proof', attempt=82)


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
        print('ERROR: Native receipt consumption proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
