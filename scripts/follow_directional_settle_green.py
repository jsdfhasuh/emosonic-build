"""Directional settling repair layered on all prior 181 full-source focused cases."""
import re
import sys
from unittest.mock import patch
import follow_anchor_admission_green as previous

PARENT = '7e5d1a09779a10ff6dfcc3169fad2fe38a0b2b5f'
MESSAGE = 'test: verify direction-aware nominal settling 20261023'
WORKFLOW = 'follow-directional-settle-green.yml'
REQUEST_PATH = 'requests/follow-directional-settle-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/follow-directional-settle-20261023'
SOURCE_SHA = 'd77264578146e8c8f078bbdca2db04a66fbcf374'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-directional-settle-full-green-validation', attempt=65)
INVENTORY_PATH = 'tool/follow_directional_settle/green_inventory.json'
INVENTORY_SHA256 = '2baf894a92a57c229d590ab6839b00f0b63079d29ed5f8c93386ac59072cf391'
EXPECTED_COUNTS = (4, 3)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS[0] == 4, 'Reviewed directional component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed directional repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 18 and sum(len(s['names']) for s in suites) == 181
            and len({s['path'] for s in suites}) == 18,
            'All prior 181 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both frozen directional suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 20 and sum(len(s['names']) for s in suites) == 181 + sum(EXPECTED_COUNTS)
            and len({s['path'] for s in suites}) == 20,
            'All prior and directional focused cases are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Directional repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
