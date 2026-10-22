"""One bounded native-only diagnostic retry; no package or publishing stages."""
import sys
from unittest.mock import patch
import current_source_check as request
import current_native_check as native

PARENT = '3ad13bfa8fd64392704a85fe453c272609b27b54'
MESSAGE = 'test: diagnose fixed-source native handoff 20261022'
WORKFLOW = 'current-native-diagnostic.yml'
REQUEST_PATH = 'requests/current-native-diagnostic-20261022.json'
REQUEST = dict(request.REQUEST, attempt=2, mode='native-diagnostic-only')


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'native'):
        print('ERROR: Invalid bounded diagnostic stage.')
        return 1
    category, stage = sys.argv[1:]
    if category == 'source' and stage not in ('prepare', 'fetch', 'cleanup'):
        print('ERROR: Package and release stages are forbidden.')
        return 1
    with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE,
                        WORKFLOW=WORKFLOW, REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST):
        with patch.object(sys, 'argv', [sys.argv[0], stage]):
            return request.main() if category == 'source' else native.main()


if __name__ == '__main__':
    sys.exit(main())
