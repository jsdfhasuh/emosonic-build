"""Fixed ordinary settlement proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '4cf220d7a7228cbe168860ff1d9af071225fc6eb'
MESSAGE = 'test: prove ordinary Follow settlement debt 20261024'
WORKFLOW = 'follow-ordinary-settle-proof.yml'
REQUEST_PATH = 'requests/follow-ordinary-settle-proof-20261024.json'
SOURCE_REF = 'refs/heads/test/follow-smooth-settlement-20261024'
SOURCE_SHA = '7c99e38ecf68cf157bc08b2cf3bae8ce273d54b3'
BASELINE_SHA = 'f6251a2a0e6441f174d05b488bc0fb1b41d52e39'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_smooth_settlement/test_inventory.json'
INVENTORY_SHA256 = '8333739b5f453587527ee19afcff703232ba8d491ae902d5e4bedd8865c43936'
ASSERTION_MARKER = 'FOLLOW_ORDINARY_POSITIVE_RESTORE_PRECEDES_TARGET_CROSSING'
EXPECTED_COUNT = 4
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-ordinary-settlement-expected-red-proof', attempt=103)


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
        print('ERROR: Ordinary settlement proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
