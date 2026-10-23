"""Targeted legacy capability compatibility, then unchanged 197-case validation."""
import re
import sys
from unittest.mock import patch
import follow_ordinary_slew_green as previous

PARENT = '0bc081e98409afb51edae5b971faccb9ad6a3971'
MESSAGE = 'test: verify broadcast capability compatibility 20261023'
WORKFLOW = 'follow-broadcast-compat-green.yml'
REQUEST_PATH = 'requests/follow-broadcast-compat-green-20261023.json'
SOURCE_REF = 'refs/heads/test/broadcast-native-cache-compat-20261023'
SOURCE_SHA = 'c5a62f48839f79ea1000853ac106e96d301645c5'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-broadcast-compat-full-green-validation', attempt=71)
INVENTORY_PATH = 'tool/broadcast_native_cache_compat/test_inventory.json'
INVENTORY_SHA256 = 'c860ca628d5633c8aa004c7dba36d09aed06c653880ecc759990b50c74967854'
EXPECTED_COUNTS = (15,)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_pins():
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_PATH) is str and re.fullmatch(r'tool/[a-z_]+/[a-z_]+\.json', INVENTORY_PATH)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 1
        and type(EXPECTED_COUNTS[0]) is int and 1 <= EXPECTED_COUNTS[0] <= 1000
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed compatibility pins and exact target count are required.')


def inventory(source):
    require_pins()
    require = TIMING.previous.recovery.request.p.require
    targeted = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(targeted) == 1 and tuple(len(s['names']) for s in targeted) == EXPECTED_COUNTS,
            'Exact targeted compatibility file is required.')
    prior = ORIGINAL_INVENTORY(source)
    require(len(prior) == 22 and sum(len(s['names']) for s in prior) == 197
            and len({s['path'] for s in prior}) == 22,
            'All prior 197 unique cases are required.')
    suites = [*targeted, *prior]
    require(len({s['path'] for s in suites}) == 23,
            'Targeted compatibility and prior suites must not overlap.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Compatibility pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
