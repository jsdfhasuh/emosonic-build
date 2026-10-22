"""Fixed-source native matrix after actual scoped URL-attribution proof."""
import sys
from pathlib import Path
from unittest.mock import patch
import current_source_check as request
import current_native_check as native
from native_consistency_observation import apply_observations

PARENT = 'cc34fd62244db0eec16617982ef6155e4c919126'
MESSAGE = 'test: validate scoped native handoff matrix 20261022'
WORKFLOW = 'handoff-native-closure.yml'
REQUEST_PATH = 'requests/handoff-native-closure-20261022.json'
OBSERVED_HARNESS_SHA256 = 'd4334d816816b81e8fa9fa807fbfbdc1198300d66884db828c55037513709332'
SOURCE_REF = 'refs/heads/fix/handoff-play-initiation-20261022'
SOURCE_SHA = '01967c853a4e6020097e9a2da61f9785b470ff7d'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               mode='native-scoped-attribution-validation', attempt=6)


def checked_native_context():
    p = request.p
    request.context()
    p.require(sys.platform == 'darwin', 'A genuine macOS runner is required.')
    p.require(native.os.environ.get('EMOSONIC_MAC_LAB_NETWORK_APPROVED') == '1', 'Test-network approval missing.')
    p.require(p.quiet(['git', 'rev-parse', 'HEAD'], p.ROOT / 'source').strip() == SOURCE_SHA, 'Wrong client source.')
    p.require(p.quiet(['git', 'rev-parse', 'HEAD'], p.ROOT / '.native-server').strip() == request.SERVER_SHA, 'Wrong server source.')


def main():
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'native'):
            raise request.p.GateError('Invalid fixed native validation stage.')
        category, stage = sys.argv[1:]
        if category == 'source' and stage not in ('prepare', 'fetch', 'cleanup'):
            raise request.p.GateError('Package and publishing stages are forbidden.')
        if category == 'native' and stage not in (*native.STAGES, 'attribution'):
            raise request.p.GateError('Unknown native validation stage.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA):
            if category == 'native' and stage in ('prepare', 'attribution'):
                checked_native_context()
                source = request.p.ROOT / 'source'
                if stage == 'prepare':
                    request.p.source_fingerprint(source, SOURCE_SHA, native.native_env())
                    print('Pristine frozen source bytes verified before disposable lab instrumentation.')
                else:
                    request.p.source_context(require_server=False)
                    request.p.codegen(source, native.native_env())
                    helper = Path(__file__).resolve().parent / 'native_attribution/lab_stream_attribution.py'
                    native.execute([sys.executable, str(helper), 'proof', '--repo', str(source)], 'scoped-attribution-proof', True)
                    native.execute([sys.executable, str(helper), 'native', '--repo', str(source), '--expected-lab-before-sha256', OBSERVED_HARNESS_SHA256], 'scoped-attribution-native-handoff', True)
                    return 0
            if category == 'native' and stage in ('build', 'handoff', 'follow'):
                checked_native_context()
                helper = Path(__file__).resolve().parent / 'native_attribution/lab_stream_attribution.py'
                native.execute([sys.executable, str(helper), 'verify', '--repo', str(request.p.ROOT / 'source'), '--expected-lab-before-sha256', OBSERVED_HARNESS_SHA256], 'scoped-attribution-integrity', True)
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                result = request.main() if category == 'source' else native.main()
                if result == 0 and category == 'native' and stage == 'prepare':
                    apply_observations(request.p.ROOT / 'source/tool/native_playback_mac/run_lab.py')
                return result
    except Exception:
        print('ERROR: Fixed native matrix failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
