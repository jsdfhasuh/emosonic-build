"""Fixed native anchor admission proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import follow_clock_proof as base

PARENT = 'c7e1aeb9c4d099dd04208ef7977e5d1d5ae35c21'
MESSAGE = 'test: prove native anchor admission ownership gap 20261023'
WORKFLOW = 'follow-anchor-admission-proof.yml'
REQUEST_PATH = 'requests/follow-anchor-admission-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-anchor-admission-gap-20261023'
SOURCE_SHA = '9d05555e6f65ff1527a7e100dd044ac7a435c4d2'
BASELINE_SHA = '54844e610f5d5c6e935431be087f1fae64fe96d6'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_anchor_admission_gap/test_inventory.json'
INVENTORY_SHA256 = '0bc1d55398fb1dc48fa1edfd56f94e1cc9f1f2ddbb1c3b6577bbdab94a1a95f2'
ASSERTION_MARKER = 'FOLLOW_ANCHOR_ADMISSION_GAP_DUPLICATE_NATIVE_SEEK'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-anchor-admission-expected-red-proof', attempt=58)


def main():
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
