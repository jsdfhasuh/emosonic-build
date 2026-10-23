"""Ordinary slew repair layered on the unchanged 189-case natural/directional gate."""
import re
import sys
from unittest.mock import patch
import follow_directional_settle_green as previous

PARENT = '880025805daf70312c613115fe4ce0a5ec183475'
MESSAGE = 'test: verify ordinary slew magnitude ownership 20261023'
WORKFLOW = 'follow-ordinary-slew-green.yml'
REQUEST_PATH = 'requests/follow-ordinary-slew-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/follow-smooth-magnitude-20261023'
SOURCE_SHA = 'c78d08acc413a891b19f16cd18dfe1ea23d4c3df'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-ordinary-slew-full-green-validation', attempt=70)
INVENTORY_PATH = 'tool/follow_smooth_magnitude/green_inventory.json'
INVENTORY_SHA256 = 'b2ddb84bf2eddc917ebb975b7ec5f93fa20d29671c50934d79309074d800c48f'
EXPECTED_COUNTS = (4, 4)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS[0] == 4, 'Reviewed ordinary slew component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed ordinary slew repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 20 and sum(len(s['names']) for s in suites) == 189
            and len({s['path'] for s in suites}) == 20,
            'All prior 189 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both frozen ordinary slew suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 22 and sum(len(s['names']) for s in suites) == 189 + sum(EXPECTED_COUNTS)
            and len({s['path'] for s in suites}) == 22,
            'All prior and ordinary slew focused cases are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Ordinary slew repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
