"""Fixed matched-pong interval proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import follow_clock_proof as base

PARENT = 'b283f2c6044825ca98953e63d2efab7b043f72fe'
MESSAGE = 'test: prove matched-pong feasible offset interval 20261022'
WORKFLOW = 'follow-clock-interval-proof.yml'
REQUEST_PATH = 'requests/follow-clock-interval-proof-20261022.json'
SOURCE_REF = 'refs/heads/test/server-clock-feasible-interval-20261022'
SOURCE_SHA = 'dcf57562a1f35247f81a28888137c27855adf06d'
BASELINE_SHA = '3093662be2bcc31fefde455baf5d6f68e51784dc'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/server_clock_interval/test_inventory.json'
INVENTORY_SHA256 = '97bb0b7184de7ad7f10ec8b324ca3fdc481fadc350b9977a1d1c0ec5185d578e'
ASSERTION_MARKER = 'SERVER_CLOCK_ESTIMATE_OUTSIDE_MATCHED_PONG_INTERVAL'
EXPECTED_COUNT = 6
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-clock-interval-expected-red-proof', attempt=53)


def main():
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
