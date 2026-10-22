"""Fixed public-server real SQLite red/green proof. No credentials or raw logs."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

PARENT = '90d9d6074ed70268c8f110f1a383d8cff5b464e3'
MESSAGE = 'test: prove authoritative follow rate contract 20261022'
BASELINE_SHA = 'b69a002c9fcad26ec91155bcd5b14ca9776ab970'
FIXED_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
TARGET = 'tests.base.test_emo_follow_store.EmoFollowStoreTestCase.test_accepted_nonunit_authority_rate_keeps_follow_source_active'
MARKER = 'FOLLOW_ACCEPTED_AUTHORITY_RATE_MUST_NOT_START_RECOVERY'
ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = 'requests/follow-server-contract-20261022.json'
REQUEST = {'server_repository': 'jsdfhasuh/Emosonic-Server', 'baseline_sha': BASELINE_SHA,
           'fixed_sha': FIXED_SHA, 'mode': 'server-contract-red-green', 'attempt': 1}

CHILD = r'''
import contextlib, io, json, pathlib, re, sys, tempfile, unittest
stage, target, marker = sys.argv[1:]
with tempfile.TemporaryFile(mode='w+') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
    import supysonic
    assert pathlib.Path(supysonic.__file__).resolve().parent == pathlib.Path.cwd() / 'supysonic'
    loader = unittest.TestLoader()
    suite = loader.discover('.') if stage == 'full' else loader.loadTestsFromName('tests.net.suite' if stage == 'network' else 'tests.base.test_emo_follow_store' if stage == 'follow' else target)
    result = unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)
    failures = result.failures
    expected = stage == 'red' and result.testsRun == 1 and not result.errors and not result.skipped and len(failures) == 1 and failures[0][0].id() == target and marker in failures[0][1]
    passed = expected if stage == 'red' else result.wasSuccessful() and result.testsRun > 0 and (stage in ('full', 'network') or (not result.skipped and not result.expectedFailures))
    ids = [case.id() for case, _ in [*result.failures, *result.errors]]
    safe_ids = [value for value in ids if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{0,240}', value)][:30]
print(json.dumps({'stage': 'server-contract-' + stage, 'status': 'passed' if passed else 'failed', 'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped), 'expectedFailures': len(result.expectedFailures), 'unexpectedSuccesses': len(result.unexpectedSuccesses), 'expectedRegressionFailure': bool(expected), 'failedTestIds': safe_ids}))
sys.exit(0 if passed else 1)
'''


def context():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    sha = os.environ.get('GITHUB_SHA')
    assert os.environ.get('GITHUB_REPOSITORY') == 'jsdfhasuh/emosonic-build'
    assert os.environ.get('GITHUB_REF') == 'refs/heads/main' and os.environ.get('GITHUB_EVENT_NAME') == 'push'
    assert os.environ.get('GITHUB_WORKFLOW_REF') == 'jsdfhasuh/emosonic-build/.github/workflows/follow-server-contract.yml@refs/heads/main'
    assert event.get('before') == PARENT and event.get('after') == sha
    assert event.get('forced') is False and event.get('deleted') is False and event.get('created') is False
    assert event.get('head_commit', {}).get('id') == sha and event['head_commit'].get('message') == MESSAGE
    assert json.loads((ROOT / REQUEST_PATH).read_text()) == REQUEST
    assert len(FIXED_SHA) == 40 and all(c in '0123456789abcdef' for c in FIXED_SHA)



def original_regression_unchanged():
    values = []
    for directory, expected in (('.server-red', BASELINE_SHA), ('.server-green', FIXED_SHA)):
        repo = ROOT / directory
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == expected
        subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=repo, check=True, capture_output=True)
        source = (repo / 'tests/base/test_emo_follow_store.py').read_text()
        classes = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == 'EmoFollowStoreTestCase']
        assert len(classes) == 1
        methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == TARGET.rsplit('.', 1)[1]]
        assert len(methods) == 1
        values.append((ast.dump(methods[0]), ast.get_source_segment(source, methods[0])))
    assert values[0] == values[1]


def main():
    try:
        context()
        original_regression_unchanged()
        assert len(sys.argv) == 2 and sys.argv[1] in ('red', 'green', 'follow', 'full', 'network')
        stage = sys.argv[1]
        repo = ROOT / ('.server-red' if stage == 'red' else '.server-green')
        expected = BASELINE_SHA if stage == 'red' else FIXED_SHA
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == expected
        result = subprocess.run([sys.executable, '-c', CHILD, stage, TARGET, MARKER], cwd=repo, capture_output=True, text=True, timeout=600)
        if len(result.stdout) > 12000:
            raise ValueError('Invalid finite result')
        value = json.loads(result.stdout)
        assert value.get('stage') == 'server-contract-' + stage
        print(json.dumps(value, allow_nan=False))
        return result.returncode
    except Exception:
        print('Server contract proof failed; raw logs suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
