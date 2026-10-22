"""Fixed feasible-clock repair with all prior focused and full-source gates."""
import sys
from unittest.mock import patch
import follow_restore_green as previous

PARENT = 'fb38f21040bc6e35659384c68e9b04a355d86106'
MESSAGE = 'test: verify native expiry oracle and feasible clock repair 20261022'
WORKFLOW = 'follow-clock-interval-green.yml'
REQUEST_PATH = 'requests/follow-clock-interval-green-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-expiry-native-oracle-20261022'
SOURCE_SHA = '54844e610f5d5c6e935431be087f1fae64fe96d6'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-clock-interval-full-green-validation', attempt=56)
CLOCK_PATH = 'tool/server_clock_source_ownership/green_inventory.json'
CLOCK_DIGEST = '62e0ee0f8d466298be20f3dbdd3a3a62338d177d0bcb7d3dd883cbf8a1bb88db'
INTERVAL_PATH = 'tool/server_clock_interval/green_inventory.json'
INTERVAL_DIGEST = 'b5e44785ebf3256bb2a61ed82c51eeeb071a2fc445ea0612fbf32b1f5f361c1f'
RECOVERY_DIGEST = 'fda39ee980a7a8b93261b3147d0a467adf460af614689a8ec5610fe871deb01a'
ORIGINAL_INVENTORY = previous.inventory


def inventory(source):
    timing = previous.previous
    require = timing.previous.recovery.request.p.require
    components = tuple((path, CLOCK_DIGEST if path == CLOCK_PATH else digest, counts)
                       for path, digest, counts in timing.COMPONENTS)
    require(sum(path == CLOCK_PATH for path, _, _ in components) == 1,
            'Exactly one reviewed legacy clock inventory is required.')
    with patch.object(timing, 'COMPONENTS', components):
        suites = ORIGINAL_INVENTORY(source)
    require(len(suites) == 14 and sum(len(s['names']) for s in suites) == 161,
            'All prior focused cases remain required.')
    suites += timing.component_inventory(source, INTERVAL_PATH, INTERVAL_DIGEST, (6, 7))
    require(len(suites) == 16 and sum(len(s['names']) for s in suites) == 174
            and len({s['path'] for s in suites}) == len(suites),
            'All 174 unique focused cases are required.')
    return suites


def main():
    with patch.object(previous.previous.previous, 'RECOVERY_INVENTORY_SHA256', RECOVERY_DIGEST), \
         patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
