"""Directional settling repair with explicit natural-stimulus fixture composition."""
import re
import sys
from unittest.mock import patch
import follow_anchor_admission_green as previous
import follow_restore_green as restore

PARENT = 'ef4a045f5b8387234d8d0078f5f04a57deb0e289'
MESSAGE = 'test: validate natural directional restore fixtures 20261023'
WORKFLOW = 'follow-directional-settle-green.yml'
REQUEST_PATH = 'requests/follow-directional-settle-green-20261023.json'
SOURCE_REF = 'refs/heads/test/follow-directional-post-restore-compat-20261023'
SOURCE_SHA = 'dca06e757b9d71663e3ffc7d8841775910fefe41'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='follow-directional-settle-full-green-validation', attempt=67)
INVENTORY_PATH = 'tool/follow_directional_settle/green_inventory.json'
INVENTORY_SHA256 = '2baf894a92a57c229d590ab6839b00f0b63079d29ed5f8c93386ac59072cf391'
EXPECTED_COUNTS = (4, 3)
TIMING = previous.TIMING
CLOCK = previous.previous
BASE_INVENTORY = restore.inventory
POST_RESTORE_PATH = 'tool/follow_post_restore/fixed_green_inventory.json'
POST_RESTORE_BASE_DIGEST = '535d86b9cd441c952554eb67f0627bcf50dba13175369ab0e122f718fa464854'
POST_RESTORE_DIGEST = '263dbe2a40cfd6f723f689fe71061cfdb44ac3920b31db50d216adb25cdc42e6'


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (4, 3), 'Reviewed directional component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and type(POST_RESTORE_DIGEST) is str and re.fullmatch(r'[0-9a-f]{64}', POST_RESTORE_DIGEST)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed directional repair pins are required.')


def reviewed_restore_components():
    # One explicit compatibility override; no historical helper mutation.
    TIMING.previous.recovery.request.p.require(
        type(restore.COMPONENTS) is tuple and len(restore.COMPONENTS) == 1
        and type(restore.COMPONENTS[0]) is tuple and len(restore.COMPONENTS[0]) == 3
        and type(restore.COMPONENTS[0][2]) is tuple
        and all(type(n) is int for n in restore.COMPONENTS[0][2])
        and restore.COMPONENTS == ((POST_RESTORE_PATH, POST_RESTORE_BASE_DIGEST, (4, 5)),)
        and type(POST_RESTORE_DIGEST) is str and re.fullmatch(r'[0-9a-f]{64}', POST_RESTORE_DIGEST),
        'Exact legacy post-restoration component contract required.')
    return ((POST_RESTORE_PATH, POST_RESTORE_DIGEST, (4, 6)),)


def inventory(source):
    require_counts()
    require = TIMING.previous.recovery.request.p.require
    # Same reviewed legacy clock replacement as the historical clock layer.
    components = tuple((path, CLOCK.CLOCK_DIGEST if path == CLOCK.CLOCK_PATH else digest, counts)
                       for path, digest, counts in TIMING.COMPONENTS)
    require(sum(path == CLOCK.CLOCK_PATH for path, _, _ in components) == 1,
            'Exactly one reviewed legacy clock inventory is required.')
    require(restore.COMPONENTS == ((POST_RESTORE_PATH, POST_RESTORE_DIGEST, (4, 6)),),
            'Scoped natural post-restoration override required.')
    with patch.object(TIMING, 'COMPONENTS', components):
        suites = BASE_INVENTORY(source)
    require(len(suites) == 14 and sum(len(s['names']) for s in suites) == 162
            and len({s['path'] for s in suites}) == 14,
            'All prior and natural post-restoration focused cases are required.')
    components = (
        (CLOCK.INTERVAL_PATH, CLOCK.INTERVAL_DIGEST, (6, 7), 16, 175),
        (previous.INVENTORY_PATH, previous.INVENTORY_SHA256, (3, 4), 18, 182),
        (INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS, 20, 189))
    suites = list(suites)
    for path, digest, counts, suite_count, case_count in components:
        additional = TIMING.component_inventory(source, path, digest, counts)
        require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == counts,
                'Every frozen component and case is required.')
        suites += additional
        require(len(suites) == suite_count and sum(len(s['names']) for s in suites) == case_count
                and len({s['path'] for s in suites}) == suite_count,
                'All intermediate frozen suites and cases are required.')
    require(len(suites) == 20 and sum(len(s['names']) for s in suites) == 189
            and len({s['path'] for s in suites}) == 20,
            'All 189 unique focused cases are required.')
    return suites


def main():
    try:
        require_pins()
        components = reviewed_restore_components()
    except Exception:
        print('ERROR: Directional repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.object(restore, 'COMPONENTS', components), \
            patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
