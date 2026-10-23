"""Native receipt compatibility with explicit, complete 236-case composition."""
import re
import sys
from unittest.mock import patch
import authority_rate_feedback_green as previous
import follow_directional_settle_green as directional
import follow_ordinary_slew_green as ordinary
import follow_broadcast_compat_green as broadcast
import handoff_convergence_green as convergence
import negative_nominal_observation as diagnostic

PARENT = '588cfc638101528925ed41f3af6c0f9ecaef1820'
MESSAGE = 'test: validate native receipt boundary compatibility 20261023'
WORKFLOW = 'native-receipt-consumption-green.yml'
REQUEST_PATH = 'requests/native-receipt-consumption-green-20261023.json'
SOURCE_REF = 'refs/heads/test/native-receipt-fixture-compatibility-20261023'
SOURCE_SHA = '17a35e301ca7182d4fed1114c7e42a940f2d208e'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='native-receipt-consumption-full-green-validation', attempt=84)
INVENTORY_PATH = 'tool/follow_native_receipt_consumption/green_inventory.json'
INVENTORY_SHA256 = '7bf0cca302b29c6d1b7dc96dd6eb8060c29d453805c1a4a69872d15b82fe9230'
DIRECTIONAL_INVENTORY_SHA256 = '4f3d2d858e3aefccf97d7aa8a36247bfe15d491d121430bd1fc92442385c1d55'
EXPECTED_COUNTS = (3, 4)
BASE_INVENTORY = directional.BASE_INVENTORY
CLOCK = directional.CLOCK
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (3, 4), 'Exact reviewed native receipt component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and type(DIRECTIONAL_INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', DIRECTIONAL_INVENTORY_SHA256)
        and type(diagnostic.FIXTURE_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', diagnostic.FIXTURE_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed native receipt consumption repair pins are required.')


def inventory(source):
    require_counts()
    require = TIMING.previous.recovery.request.p.require
    # Keep the same reviewed legacy clock and natural post-restoration composition.
    components = tuple((path, CLOCK.CLOCK_DIGEST if path == CLOCK.CLOCK_PATH else digest, counts)
                       for path, digest, counts in TIMING.COMPONENTS)
    require(sum(path == CLOCK.CLOCK_PATH for path, _, _ in components) == 1,
            'Exactly one reviewed legacy clock inventory is required.')
    require(directional.restore.COMPONENTS == ((directional.POST_RESTORE_PATH,
            directional.POST_RESTORE_DIGEST, (4, 6)),),
            'Scoped natural post-restoration override required.')
    with patch.object(TIMING, 'COMPONENTS', components):
        suites = BASE_INVENTORY(source)
    require(len(suites) == 14 and sum(len(s['names']) for s in suites) == 162
            and len({s['path'] for s in suites}) == 14
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All 162 prior natural post-restoration cases are required.')
    components = (
        (CLOCK.INTERVAL_PATH, CLOCK.INTERVAL_DIGEST, (6, 7), 16, 175, False),
        (directional.previous.INVENTORY_PATH, directional.previous.INVENTORY_SHA256, (3, 4), 18, 182, False),
        (directional.INVENTORY_PATH, DIRECTIONAL_INVENTORY_SHA256, (4, 4), 20, 190, False),
        (ordinary.INVENTORY_PATH, ordinary.INVENTORY_SHA256, (4, 4), 22, 198, False),
        (broadcast.INVENTORY_PATH, broadcast.INVENTORY_SHA256, (15,), 23, 213, True),
        (convergence.INVENTORY_PATH, convergence.INVENTORY_SHA256, (3, 5), 25, 221, False),
        (previous.INVENTORY_PATH, previous.INVENTORY_SHA256, (3, 5), 27, 229, False),
        (INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS, 29, 236, False),
    )
    suites = list(suites)
    for path, digest, counts, suite_count, case_count, prepend in components:
        additional = TIMING.component_inventory(source, path, digest, counts)
        require(len(additional) == len(counts) and tuple(len(s['names']) for s in additional) == counts,
                'Every complete frozen component and case is required.')
        suites = [*additional, *suites] if prepend else [*suites, *additional]
        require(len(suites) == suite_count and sum(len(s['names']) for s in suites) == case_count
                and len({s['path'] for s in suites}) == suite_count
                and all(len(set(s['names'])) == len(s['names']) for s in suites),
                'All intermediate frozen suites and cases are required.')
    require(len(suites) == 29 and sum(len(s['names']) for s in suites) == 236
            and len({s['path'] for s in suites}) == 29,
            'All 236 cases across 29 unique suites are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: NativeReceiptConsumption repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
