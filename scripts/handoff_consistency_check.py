"""One same-source native run with finer assertion observations only."""
import sys
from unittest.mock import patch
import current_source_check as request
import current_native_check as native
from native_consistency_observation import apply_observations

PARENT = '6dd7b7e9cc556b49175fa32966d9ada89ea64eab'
MESSAGE = 'test: observe native handoff consistency 20261022'
WORKFLOW = 'handoff-consistency-check.yml'
REQUEST_PATH = 'requests/handoff-consistency-20261022.json'
SOURCE_REF = 'refs/heads/fix/handoff-play-initiation-20261022'
SOURCE_SHA = '19639161be7945884d998ecd268d9bc30afcf02d'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='native-consistency-observation', attempt=4)


def main():
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'native'):
            raise request.p.GateError('Invalid bounded consistency stage.')
        category, stage = sys.argv[1:]
        if category == 'source' and stage not in ('prepare', 'fetch', 'cleanup'):
            raise request.p.GateError('Only exact-source preparation, fetch and cleanup are allowed.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA):
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                result = request.main() if category == 'source' else native.main()
                if result == 0 and category == 'native' and stage == 'prepare':
                    apply_observations(request.p.ROOT / 'source/tool/native_playback_mac/run_lab.py')
                return result
    except Exception:
        print('ERROR: Native consistency observation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
