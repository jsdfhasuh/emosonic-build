"""Fractional precision repair layered on the unchanged 236-case gate."""
import re
import sys
from unittest.mock import patch
import native_receipt_consumption_green as previous

PARENT = 'd3404b85931ea1ef737469ac73079ceb970c7105'
MESSAGE = 'test: validate fractional native precision repair 20261023'
WORKFLOW = 'fractional-precision-green.yml'
REQUEST_PATH = 'requests/fractional-precision-green-20261023.json'
SOURCE_REF = 'refs/heads/fix/follow-fractional-precision-20261023'
SOURCE_SHA = 'c7301a107fd1474ec0d22bb609426a435bc52584'
SERVER_SHA = previous.SERVER_SHA
REQUEST = dict(previous.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='fractional-precision-full-green-validation', attempt=86)
INVENTORY_PATH = 'tool/follow_fractional_precision/green_inventory.json'
INVENTORY_SHA256 = '9b1fcd4288a1993f2334228184fdecd54ba97911af726d2d682d4424f4681c3e'
DIRECTIONAL_INVENTORY_SHA256 = 'c3e17aa8d1cb6ee071149674bdf8b1aafd9fa982e930feaa9ca040201f3b972c'
DIAGNOSTIC_FIXTURE_SHA256 = 'd76e021d275cb2dcec44132c82aecf76b6b2c84ff4824c1a965b8de9ecb69c74'
EXPECTED_COUNTS = (3, 4)
ORIGINAL_INVENTORY = previous.inventory
TIMING = previous.TIMING


def require_counts():
    TIMING.previous.recovery.request.p.require(
        type(EXPECTED_COUNTS) is tuple and len(EXPECTED_COUNTS) == 2
        and all(type(n) is int and 1 <= n <= 128 for n in EXPECTED_COUNTS)
        and EXPECTED_COUNTS == (3, 4), 'Exact reviewed fractional precision component counts are required.')


def require_pins():
    require_counts()
    TIMING.previous.recovery.request.p.require(
        type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
        and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/[a-zA-Z0-9_./-]+', SOURCE_REF)
        and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
        and type(DIRECTIONAL_INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', DIRECTIONAL_INVENTORY_SHA256)
        and type(DIAGNOSTIC_FIXTURE_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', DIAGNOSTIC_FIXTURE_SHA256)
        and REQUEST['source_sha'] == SOURCE_SHA and REQUEST['source_ref'] == SOURCE_REF,
        'Reviewed fractional precision repair pins are required.')


def inventory(source):
    require_counts()
    suites = ORIGINAL_INVENTORY(source)
    require = TIMING.previous.recovery.request.p.require
    require(len(suites) == 29 and sum(len(s['names']) for s in suites) == 236
            and len({s['path'] for s in suites}) == 29
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All prior 236 unique focused cases are required.')
    additional = TIMING.component_inventory(source, INVENTORY_PATH, INVENTORY_SHA256, EXPECTED_COUNTS)
    require(len(additional) == 2 and tuple(len(s['names']) for s in additional) == EXPECTED_COUNTS,
            'Both complete frozen fractional precision suites are required.')
    suites = [*suites, *additional]
    require(len(suites) == 31 and sum(len(s['names']) for s in suites) == 243
            and len({s['path'] for s in suites}) == 31
            and all(len(set(s['names'])) == len(s['names']) for s in suites),
            'All 243 cases across 31 unique suites are required.')
    return suites


def main():
    try:
        require_pins()
    except Exception:
        print('ERROR: Fractional precision repair pins or counts are incomplete or inconsistent.', file=sys.stderr)
        return 1
    with patch.object(previous.diagnostic, 'FIXTURE_SHA256', DIAGNOSTIC_FIXTURE_SHA256), \
            patch.multiple(previous, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                        REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                        SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA, inventory=inventory,
                        DIRECTIONAL_INVENTORY_SHA256=DIRECTIONAL_INVENTORY_SHA256):
        return previous.main()


if __name__ == '__main__':
    sys.exit(main())
