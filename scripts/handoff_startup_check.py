"""Frozen real-service ordinary-startup red/green verification; no native or packages."""
import sys
from unittest.mock import patch
import current_source_check as request
import handoff_repair_check as regression

PARENT = 'fab6e5994438d005b9815bcc57353362d288f65f'
MESSAGE = 'test: verify ordinary startup lease regression 20261022'
WORKFLOW = 'handoff-startup-check.yml'
REQUEST_PATH = 'requests/handoff-startup-20261022.json'
SOURCE_REF = 'refs/heads/fix/handoff-play-initiation-20261022'
SOURCE_SHA = '01967c853a4e6020097e9a2da61f9785b470ff7d'
BASELINE_SHA = '440d9345be2976fb21c3515b12078a7baccf4daa'
TEST_PATH = 'test/remediation/handoff_play_initiation_boundaries_test.dart'
TEST_NAME = 'local play survives first authority lease during held source policy'
ASSERTION_MARKER = 'LOCAL_PLAY_MUST_SURVIVE_FIRST_AUTHORITY_LEASE'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, mode='handoff-startup-validation', attempt=5)


def main():
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'regression'):
            raise request.p.GateError('Only fixed-source startup validation is allowed.')
        category, stage = sys.argv[1:]
        if category == 'source' and stage not in ('prepare', 'fetch', 'validate_source', 'cleanup'):
            raise request.p.GateError('Native, package and publishing stages are forbidden.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA):
            if category == 'regression':
                with patch.multiple(regression, BASELINE_SHA=BASELINE_SHA, TEST_PATH=TEST_PATH,
                                    TEST_NAME=TEST_NAME, ASSERTION_MARKER=ASSERTION_MARKER):
                    regression.regression(stage)
                    return 0
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                return request.main()
    except Exception:
        print('ERROR: Startup validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
