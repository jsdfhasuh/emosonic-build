"""Fixed handoff convergence transition proof using the unchanged bounded red verifier."""
from unittest.mock import patch
import re
import follow_clock_proof as base

PARENT = '7ed103d464d3e21cc6703d1d65e1cdbd88943acd'
MESSAGE = 'test: prove handoff convergence transition ownership 20261023'
WORKFLOW = 'handoff-convergence-proof.yml'
REQUEST_PATH = 'requests/handoff-convergence-proof-20261023.json'
SOURCE_REF = 'refs/heads/test/feedback-reconcile-completion-20261023'
SOURCE_SHA = '4698fafcfb2ccfcc7c2aa10acdfb2c0cd8088247'
BASELINE_SHA = 'c5a62f48839f79ea1000853ac106e96d301645c5'
SERVER_SHA = base.SERVER_SHA
INVENTORY_PATH = 'tool/feedback_reconcile_completion/test_inventory.json'
INVENTORY_SHA256 = 'a2ef01a2564ff316815eeb7c6d1434b96fc0b94799eb42b7baa76bf30625d725'
ASSERTION_MARKER = 'PLAYBACK_CANONICAL_MATCH_LEFT_RECONCILING'
EXPECTED_COUNT = 3
REQUEST = dict(base.request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-handoff-convergence-expected-red-proof', attempt=73)


def main():
    # Unresolved or inconsistent pins must fail before any context/fetch action.
    if not (type(SOURCE_SHA) is str and re.fullmatch(r'[0-9a-f]{40}', SOURCE_SHA)
            and type(SOURCE_REF) is str and re.fullmatch(r'refs/heads/test/[a-zA-Z0-9_./-]+', SOURCE_REF)
            and type(INVENTORY_SHA256) is str and re.fullmatch(r'[0-9a-f]{64}', INVENTORY_SHA256)
            and type(INVENTORY_PATH) is str and re.fullmatch(r'tool/[a-z0-9_]+/test_inventory\.json', INVENTORY_PATH)
            and type(ASSERTION_MARKER) is str and re.fullmatch(r'[A-Z][A-Z0-9_]{1,127}', ASSERTION_MARKER)
            and type(EXPECTED_COUNT) is int and 2 <= EXPECTED_COUNT <= 128
            and REQUEST.get('source_sha') == SOURCE_SHA and REQUEST.get('source_ref') == SOURCE_REF
            and REQUEST.get('baseline_sha') == BASELINE_SHA):
        print('ERROR: Handoff convergence proof pins are incomplete or inconsistent.')
        return 1
    with patch.multiple(base, **{name: globals()[name] for name in (
            'PARENT', 'MESSAGE', 'WORKFLOW', 'REQUEST_PATH', 'SOURCE_REF',
            'SOURCE_SHA', 'BASELINE_SHA', 'SERVER_SHA', 'INVENTORY_PATH',
            'INVENTORY_SHA256', 'ASSERTION_MARKER', 'EXPECTED_COUNT', 'REQUEST')}):
        return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
