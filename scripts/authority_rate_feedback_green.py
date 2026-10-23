"""Native rate feedback layered on the unchanged 220-case gate."""
import re
import sys
from unittest.mock import patch
import handoff_convergence_green as previous
import follow_directional_settle_green as directional

PARENT = 'bbb5b5dd0ae7e7ec5847bf0c96699dec19c02624'
MESSAGE = 'test: validate synchronous negative nominal diagnostics 20261023'
WORKFLOW = 'authority-rate-feedback-green.yml'
REQUEST_PATH = 'requests/authority-rate-feedback-green-20261023.json'
SOURCE_REF = 'refs/heads/test/negative-nominal-print-lint-20261023'
SOURCE_SHA = '28fc26149f5e4175fe952219b3cc5f9d18519c50'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='authority-rate-feedback-full-green-validation', attempt=80)
INVENTORY_PATH = 'tool/native_rate_feedback/green_inventory.json'
INVENTORY_SHA256 = '28bedc8f4905fbc2166038c1cac1c89f7015cab71ad2be8ffb25157b65289107'
EXPECTED_COUNTS = (3, 5)
DIRECTIONAL_INVENTORY_SHA256 = '2c764aa0cd43d9f951417524640152b60052fac752ae76d683dcdd9016f94d63'
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS[0] == 3, 'Reviewed rate feedback component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed rate feedback repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 25 and sum(len(s['names']) for s in suites) == 220
            and len({s['path'] for s in suites}) == 25,
            'All prior 220 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both frozen rate feedback suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 27 and sum(len(s['names']) for s in suites) == 220 + sum(EXPECTED_COUNTS)
            and len({s['path'] for s in suites}) == 27,
            'All prior and rate feedback focused cases are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: RateFeedback repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.object(directional, 'INVENTORY_SHA256', DIRECTIONAL_INVENTORY_SHA256), patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
