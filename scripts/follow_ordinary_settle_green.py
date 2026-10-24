"""Ordinary settlement repair layered on the unchanged 254-case source gate."""
import re
import sys
from unittest.mock import patch
import initial_apply_receipt_green as previous

PARENT = 'ec0703df69806fb6704be502569c91b782d0ed66'
MESSAGE = 'test: validate ordinary Follow settlement fixture correction 20261024'
WORKFLOW = 'follow-ordinary-settle-green.yml'
REQUEST_PATH = 'requests/follow-ordinary-settle-green-20261024.json'
SOURCE_REF = 'refs/heads/fix/follow-ordinary-settlement-20261024'
SOURCE_SHA = '2fb9f8bf711da6b1aaf8b9d7442ee3111befe0d4'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-ordinary-settlement-full-green-validation', attempt=105)
INVENTORY_PATH = 'tool/follow_smooth_settlement/green_inventory.json'
INVENTORY_SHA256 = 'e086df2bfc30773f04d355c860075bff478ad6bbb7b9610188c6dfe2e4977f47'
# Final independently reviewed fixture correction; preserve the frozen four cases.
REVIEWED_BOUNDARY_COUNT = 17
EXPECTED_COUNTS = (4, REVIEWED_BOUNDARY_COUNT)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(REVIEWED_BOUNDARY_COUNT) is int and REVIEWED_BOUNDARY_COUNT == 17
        and type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (4, 17),
        'Frozen ordinary settlement baseline and exact reviewed boundary count are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and INVENTORY_PATH == 'tool/follow_smooth_settlement/green_inventory.json'
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed ordinary settlement repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 33 and sum(len(s['names']) for s in suites) == 254
            and len({s['path'] for s in suites}) == 33
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All prior 254 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both complete frozen ordinary settlement suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 35 and sum(len(s['names']) for s in suites) == 275
            and len({s['path'] for s in suites}) == 35
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All prior and ordinary settlement cases across 35 unique suites are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Ordinary settlement repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
