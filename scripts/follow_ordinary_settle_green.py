"""Ordinary settlement repair layered on the unchanged 254-case source gate."""
import re
import sys
from unittest.mock import patch
import initial_apply_receipt_green as previous

PARENT = '82243ad915ce3e028f074f667295dc8b9113ec83'
MESSAGE = 'test: validate ordinary Follow settlement repair 20261024'
WORKFLOW = 'follow-ordinary-settle-green.yml'
REQUEST_PATH = 'requests/follow-ordinary-settle-green-20261024.json'
SOURCE_REF = 'refs/heads/fix/follow-ordinary-settlement-20261024'
SOURCE_SHA = '7a6467b6f66f17f1a58127d9c6ad4debad4983bc'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-ordinary-settlement-full-green-validation', attempt=104)
INVENTORY_PATH = 'tool/follow_smooth_settlement/green_inventory.json'
INVENTORY_SHA256 = '7b05327f397df0dd74fb8dd751a9f6a85b6716278679fc6ca814ed0590997ff7'
# Final independently reviewed boundary count; preserve the frozen four cases.
REVIEWED_BOUNDARY_COUNT = 16
EXPECTED_COUNTS = (4, REVIEWED_BOUNDARY_COUNT)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(REVIEWED_BOUNDARY_COUNT) is int and REVIEWED_BOUNDARY_COUNT == 16
        and type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (4, 16),
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
    require(len(suites) == 35 and sum(len(s['names']) for s in suites) == 274
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
