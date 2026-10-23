"""Initial apply receipt repair layered on the unchanged 243-case full gate."""
import re
import sys
from unittest.mock import patch
import fractional_precision_green as previous

PARENT = 'bd51fdc6472d5a6bc42f0b38d442dcbd8659c676'
MESSAGE = 'test: validate initial apply native receipt repair 20261023'
WORKFLOW = 'initial-apply-receipt-green.yml'
REQUEST_PATH = 'requests/initial-apply-receipt-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/follow-initial-apply-receipt-20261023'
SOURCE_SHA = 'fd0deab86014c0f0cee0b1c525893e493f426b9c'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='initial-apply-receipt-full-green-validation', attempt=92)
INVENTORY_PATH = 'tool/follow_initial_apply_receipt/green_inventory.json'
INVENTORY_SHA256 = 'c7d556fc1e024fbf09236ff9ae20260537a5d298adbf13966c96e49f24b5a139'
EXPECTED_COUNTS = (3, 6)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 128 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (3, 6),
        'Frozen initial apply receipt baseline and reviewed boundary count are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_PATH) is str and re.fullmatch(r'tool/[a-z0-9_]+/green_inventory\.json', INVENTORY_PATH)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed initial apply receipt repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 31 and sum(len(s['names']) for s in suites) == 243
            and len({s['path'] for s in suites}) == 31
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All prior 243 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both complete frozen initial apply receipt suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 33 and sum(len(s['names']) for s in suites) == 252
            and len({s['path'] for s in suites}) == 33
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All 252 cases across 33 unique suites are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Initial apply receipt repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
