"""Guarded convergence completion layered on the unchanged 212-case gate."""
import re
import sys
from unittest.mock import patch
import follow_broadcast_compat_green as previous

PARENT = '33df1e6773ed407f054a6bd96b3b4c3db2b513b0'
MESSAGE = 'test: verify guarded handoff convergence completion 20261023'
WORKFLOW = 'handoff-convergence-green.yml'
REQUEST_PATH = 'requests/handoff-convergence-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/feedback-reconcile-completion-20261023'
SOURCE_SHA = 'aaa07a9860d167cafcf440ac16011e745a5c74a4'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='handoff-convergence-full-green-validation', attempt=74)
INVENTORY_PATH = 'tool/feedback_reconcile_completion/green_inventory.json'
INVENTORY_SHA256 = '243e1165b8ae33a704a8e9e28a2acec8da494ebebab84afedef0204f119f9f34'
EXPECTED_COUNTS = (3, 5)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 1000 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS[0] == 3, 'Reviewed convergence component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed convergence repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 23 and sum(len(s['names']) for s in suites) == 212
            and len({s['path'] for s in suites}) == 23,
            'All prior 212 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both frozen convergence suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 25 and sum(len(s['names']) for s in suites) == 212 + sum(EXPECTED_COUNTS)
            and len({s['path'] for s in suites}) == 25,
            'All prior and convergence focused cases are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Convergence repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
