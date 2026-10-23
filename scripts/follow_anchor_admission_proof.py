"""Fixed native anchor admission proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import follow_clock_proof as base

PARENT = '6cd4550468cfbc2f5dc559a1715bc74cf6f3814c'
MESSAGE = 'test: prove scoped native anchor admission ownership gap 20261023'
WORKFLOW = 'follow-anchor-admission-proof.yml'
REQUEST_PATH = 'requests/follow-anchor-admission-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-anchor-admission-gap-20261023'
SOURCE_SHA = '3926502af51ef8a105b15c5601c8bd90db55a80c'
BASELINE_SHA = '54844e610f5d5c6e935431be087f1fae64fe96d6'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/follow_anchor_admission_gap/test_inventory.json'
INVENTORY_SHA256 = '915f01c17afb0731d2effb95eb532be5faf5f15917b627b382898551d964c85e'
ASSERTION_MARKER = 'FOLLOW_ANCHOR_ADMISSION_GAP_DUPLICATE_NATIVE_SEEK'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-anchor-admission-expected-red-proof', attempt=59)


def main():
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
