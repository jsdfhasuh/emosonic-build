"""Fixed directional nominal switching proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '64cf207eae63f459fe6c3a4ce0979271c183c952'
MESSAGE = 'test: prove positive-slew nominal switching boundary 20261023'
WORKFLOW = 'follow-directional-settle-proof.yml'
REQUEST_PATH = 'requests/follow-directional-settle-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-directional-settle-20261023'
SOURCE_SHA = '440e9311718932a0c0d2ce70c754eb195c324350'
BASELINE_SHA = '6adf81189c02d4c9997fdeff5edc61b7f33308ee'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_directional_settle/test_inventory.json'
INVENTORY_SHA256 = 'b9bf802e15aca730310b55ac842a933ef5b7805a95bb7a4cb19ddf89fe6131fb'
ASSERTION_MARKER = 'FOLLOW_POSITIVE_SLEW_RESTORED_BEFORE_ZERO_CROSSING'
EXPECTED_COUNT = 4
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-directional-settle-expected-red-proof', attempt=64)


def main():
    # Unresolved or inconsistent pins must fail before any context/fetch action.
    if not (type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/test/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
            and REQUEST.get('source_sha') == SOURCE_SHA and REQUEST.get('source_ref') == SOURCE_REF
            and REQUEST.get('baseline_sha') == BASELINE_SHA):
        print('ERROR: Directional proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
