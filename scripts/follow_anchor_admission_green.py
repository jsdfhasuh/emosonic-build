"""Bounded admission ownership repair, layered on all prior full-source gates."""
import re
import sys
from unittest.mock import patch
import follow_clock_interval_green as previous

PARENT = '870533605f1b0fc7aa22b95517e1220e137e2ceb'
MESSAGE = 'test: verify bounded native anchor admission ownership 20261023'
WORKFLOW = 'follow-anchor-admission-green.yml'
REQUEST_PATH = 'requests/follow-anchor-admission-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/follow-anchor-admission-ownership-20261023'
SOURCE_SHA = '6adf81189c02d4c9997fdeff5edc61b7f33308ee'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-anchor-admission-full-green-validation', attempt=60)
INVENTORY_PATH = 'tool/follow_anchor_admission_gap/green_inventory.json'
INVENTORY_SHA256 = '0bb5f47b2cb9b25c8c5b49cafc3efb2b058ef52ee8ec69ce263948647c545a12'
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.previous.previous


def require_pins():
    require = TIMING.previous.recovery.request.p.require
    require(type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
            and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
            'Reviewed admission repair pins are required.')


def inventory(source):
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 16 and sum(len(s['names']) for s in suites) == 174
            and len({s['path'] for s in suites}) == 16,
            'All prior 174 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, (3, 4))
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == (3, 4),
            'Both frozen admission suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 18 and sum(len(s['names']) for s in suites) == 181
            and len({s['path'] for s in suites}) == 18,
            'All 181 unique focused cases are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Admission repair pins are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
