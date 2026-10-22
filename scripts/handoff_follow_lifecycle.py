"""Fixed client/server native matrix with finite read-only lifecycle observation."""
import sys
from unittest.mock import patch
import handoff_follow_readiness as base
import native_follow_lifecycle as lifecycle

PARENT = '2db031056576e138cf0ef21df0f09cbf1088a63f'
MESSAGE = 'test: validate bounded native follow preroll 20261022'
WORKFLOW = 'handoff-follow-lifecycle.yml'
REQUEST_PATH = 'requests/handoff-follow-lifecycle-20261022.json'
SOURCE_SHA = base.SOURCE_SHA
SOURCE_REF = base.SOURCE_REF
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
REQUEST = dict(base.REQUEST, server_sha=SERVER_SHA, mode='native-follow-lifecycle-validation', attempt=10)
NATIVE_STAGES = ('prepare', 'dependencies', 'unit', 'preflight', 'attribution', 'build', 'handoff', 'follow', 'cleanup')


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
                            ATTRIBUTION_EXTRA_ARGS=('--lab-debug-observation',)), \
             patch.object(base.request, 'SERVER_SHA', SERVER_SHA):
            if category == 'native' and stage in ('unit', 'attribution', 'build', 'handoff', 'follow'):
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
