"""Fixed-source focused Follow test with finite read-only lifecycle observation."""
import sys
from unittest.mock import patch
import handoff_follow_readiness as base
import native_follow_lifecycle as lifecycle

PARENT = '44a6325cb80de20fc284a1047ae00403054a7e53'
MESSAGE = 'test: trace fixed-source native follow lifecycle 20261022'
WORKFLOW = 'handoff-follow-lifecycle.yml'
REQUEST_PATH = 'requests/handoff-follow-lifecycle-20261022.json'
SOURCE_SHA = base.SOURCE_SHA
SOURCE_REF = base.SOURCE_REF
REQUEST = dict(base.REQUEST, mode='native-follow-lifecycle-validation', attempt=9)
NATIVE_STAGES = ('prepare', 'dependencies', 'unit', 'preflight', 'attribution', 'build', 'follow', 'cleanup')


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError('Invalid focused validation stage')
        category, stage = sys.argv[1:]
        if category == 'source':
            if stage not in ('prepare', 'fetch', 'cleanup'):
                raise ValueError('Package and publishing stages forbidden')
        elif category != 'native' or stage not in NATIVE_STAGES:
            raise ValueError('Unknown focused native stage')
        with patch.multiple(base, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_SHA=SOURCE_SHA, SOURCE_REF=SOURCE_REF,
                            OBSERVED_HARNESS_SHA256=lifecycle.AFTER_HARNESS_SHA256,
                            ATTRIBUTION_EXTRA_ARGS=('--lab-debug-observation',)):
            if category == 'native' and stage in ('unit', 'attribution', 'build', 'follow'):
                lifecycle.verify_prepared(base.request.p.ROOT / 'source',
                    require_harness=stage in ('unit', 'attribution'))
            result = base.main()
            if result == 0 and category == 'native' and stage == 'prepare':
                lifecycle.apply(base.request.p.ROOT / 'source')
            return result
    except Exception:
        print('ERROR: Focused Follow validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
