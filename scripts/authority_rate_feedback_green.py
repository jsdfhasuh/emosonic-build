"""Native rate feedback layered on the unchanged 220-case gate."""
import re
import sys
from unittest.mock import patch
import handoff_convergence_green as previous

PARENT = 'c18fd5552b4e43adbfea11ea1a450aa98ab96f89'
MESSAGE = 'test: validate native rate feedback fixture lint cleanup 20261023'
WORKFLOW = 'authority-rate-feedback-green.yml'
REQUEST_PATH = 'requests/authority-rate-feedback-green-20261023.json'
SOURCE_REF = 'refs/heads/test/native-rate-feedback-lint-20261023'
SOURCE_SHA = '401f01e7e4ebe239b8aa5fb2201f45496facc686'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='authority-rate-feedback-full-green-validation', attempt=78)
INVENTORY_PATH = 'tool/native_rate_feedback/green_inventory.json'
INVENTORY_SHA256 = '28bedc8f4905fbc2166038c1cac1c89f7015cab71ad2be8ffb25157b65289107'
EXPECTED_COUNTS = (3, 5)
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
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
