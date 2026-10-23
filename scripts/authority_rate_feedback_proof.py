"""Fixed authority rate feedback proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '5b261eb360f7e04dce0352086bd99e1deafac954'
MESSAGE = 'test: prove authority rate feedback ownership 20261023'
WORKFLOW = 'authority-rate-feedback-proof.yml'
REQUEST_PATH = 'requests/authority-rate-feedback-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/native-rate-feedback-20261023'
SOURCE_SHA = 'b1fd7295c7af882a772bb66e32ea0f61b1dc626c'
BASELINE_SHA = 'aaa07a9860d167cafcf440ac16011e745a5c74a4'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/native_rate_feedback/test_inventory.json'
INVENTORY_SHA256 = '975bb3b92d19745ed06b6896fa70c9159243bc92706c90b217daa599f8a0ec11'
ASSERTION_MARKER = 'NATIVE_RATE_FEEDBACK_WAITS_FOR_PROGRESS_HEARTBEAT'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-authority-rate-feedback-expected-red-proof', attempt=76)


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
        print('ERROR: Authority rate feedback proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
