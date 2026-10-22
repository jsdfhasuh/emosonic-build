"""Exact modern-macOS native anchoring red/green proof; never publishes packages."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from unittest.mock import patch
import current_source_check as request

PARENT = 'be056c4086460cad87f32e2049d86b2b46d64f5f'
MESSAGE = 'test: prove modern macOS position anchor repair 20261022'
WORKFLOW = 'darwin-anchor-check.yml'
REQUEST_PATH = 'requests/darwin-anchor-check-20261022.json'
SOURCE_REF = 'refs/heads/fix/darwin-position-anchor-20261022'
SOURCE_SHA = '1efc826b85c305bd60210aa705444114c1a0d5e2'
BASELINE_SHA = '7e1c24ecffcce1a9a4f928ad6806207d86507547'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
MODULE = 'tool.native_position_anchor.test_darwin_position_anchor'
TARGET = MODULE + '.DarwinModernAnchor.test_modern_registered_callback_repairs_late_hold'
MARKER = 'DARWIN_MODERN_SAMPLE_MUST_REFRESH_EVENT_ANCHOR'
GREEN_COUNT = 12
TEST_DIRECTORY = 'tool/native_position_anchor'
MANIFEST = '.darwin-anchor-regression.json'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               server_sha=SERVER_SHA, baseline_sha=BASELINE_SHA,
               mode='darwin-anchor-validation', attempt=12)

CHILD = r'''
import contextlib, json, sys, tempfile, unittest
stage, module, target, marker, expected_count = sys.argv[1:]
with tempfile.TemporaryFile(mode='w+') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
    suite = unittest.defaultTestLoader.loadTestsFromName(target if stage == 'red' else module)
    def flatten(value):
        return [case for item in value for case in (flatten(item) if isinstance(item, unittest.TestSuite) else [item])]
    tests = flatten(suite)
    ordinals = {case.id(): index + 1 for index, case in enumerate(tests)}
    prefixes = ('DARWIN_TEST_COMPILE_FAILURE (not causal red): ',
                'DARWIN_TEST_COMPILE_FAILURE (iOS preprocessor isolation, not causal red): ')
    class FiniteResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.finite_failures = []
            self.exact_causal = []
        def remember(self, test, error, is_error):
            owner = getattr(test, 'test_case', test)
            exact = (error[0] is AssertionError and type(error[1]) is AssertionError
                     and len(error[1].args) == 1 and type(error[1].args[0]) is str
                     and error[1].args[0] == marker)
            row = {'ordinal': ordinals.get(owner.id(), 0),
                   'reason': 'causal_anchor_missing' if exact else 'test_error' if is_error else 'test_failure'}
            if exact:
                self.exact_causal.append((test is owner, owner.id()))
            if type(error[1]) is RuntimeError and len(error[1].args) == 1 and type(error[1].args[0]) is str:
                message = error[1].args[0]
                for prefix in prefixes:
                    if message.startswith(prefix):
                        row['reason'] = 'compile_error'
                        try:
                            row['compile'] = json.loads(message[len(prefix):])
                        except (TypeError, ValueError):
                            pass
                        break
            self.finite_failures.append(row)
        def addFailure(self, test, error):
            self.remember(test, error, False)
            super().addFailure(test, error)
        def addError(self, test, error):
            self.remember(test, error, True)
            super().addError(test, error)
        def addSubTest(self, test, subtest, error):
            if error is not None:
                self.remember(subtest, error, not issubclass(error[0], test.failureException))
            super().addSubTest(test, subtest, error)
        def addExpectedFailure(self, test, error):
            self.finite_failures.append({'ordinal': ordinals.get(test.id(), 0), 'reason': 'expected_failure'})
            super().addExpectedFailure(test, error)
        def addUnexpectedSuccess(self, test):
            self.finite_failures.append({'ordinal': ordinals.get(test.id(), 0), 'reason': 'unexpected_success'})
            super().addUnexpectedSuccess(test)
    result = unittest.TextTestRunner(stream=sink, verbosity=0, resultclass=FiniteResult).run(suite)
    causal = (stage == 'red' and result.testsRun == 1 and not result.errors and not result.skipped
              and len(result.failures) == 1 and result.failures[0][0].id() == target
              and not result.expectedFailures and not result.unexpectedSuccesses
              and result.exact_causal == [(True, target)])
    passed = causal if stage == 'red' else (result.wasSuccessful() and result.testsRun == int(expected_count)
              and result.testsRun > 0 and not result.skipped and not result.expectedFailures)
print(json.dumps({'stage': 'darwin-anchor-' + stage, 'status': 'passed' if passed else 'failed',
    'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
    'skipped': len(result.skipped), 'expectedFailures': len(result.expectedFailures),
    'unexpectedSuccesses': len(result.unexpectedSuccesses),
    'expectedRegressionFailure': causal, 'failedTests': result.finite_failures[:64]}))
sys.exit(0 if passed else 1)
'''

COUNTS = ('tests', 'failures', 'errors', 'skipped', 'expectedFailures', 'unexpectedSuccesses')
REASONS = frozenset(('causal_anchor_missing', 'test_error', 'test_failure', 'compile_error',
                     'expected_failure', 'unexpected_success'))
COMPILE_CATEGORIES = frozenset(('unknown_identifier', 'missing_property', 'missing_selector',
                               'type_conversion', 'syntax', 'other'))


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate_summary(value, stage, returncode, expected_count=None):
    """Reject unknown fields/values before anything from the child is public."""
    require = request.p.require
    expected_count = GREEN_COUNT if expected_count is None else expected_count
    require(stage in ('red', 'green') and integer(expected_count, 1, 4096), 'Invalid proof configuration.')
    require(type(value) is dict and set(value) == {
        'stage', 'status', *COUNTS, 'expectedRegressionFailure', 'failedTests',
    }, 'Invalid finite proof schema.')
    require(value['stage'] == 'darwin-anchor-' + stage and value['status'] in ('passed', 'failed')
            and type(value['status']) is str
            and type(value['expectedRegressionFailure']) is bool
            and all(integer(value[key], 0, 4096) for key in COUNTS)
            and type(value['failedTests']) is list and len(value['failedTests']) <= 64,
            'Invalid finite proof values.')
    for row in value['failedTests']:
        require(type(row) is dict and set(row) in ({'ordinal', 'reason'}, {'ordinal', 'reason', 'compile'})
                and integer(row['ordinal'], 0, expected_count)
                and type(row['reason']) is str and row['reason'] in REASONS,
                'Invalid finite failure entry.')
        if 'compile' in row:
            diagnostic = row['compile']
            require(row['reason'] == 'compile_error' and type(diagnostic) is dict
                    and set(diagnostic) == {'stage', 'errors', 'error_count', 'truncated'}
                    and diagnostic['stage'] == 'compile'
                    and integer(diagnostic['error_count'], 0, 4096)
                    and type(diagnostic['truncated']) is bool
                    and diagnostic['truncated'] == (diagnostic['error_count'] > 12)
                    and type(diagnostic['errors']) is list
                    and len(diagnostic['errors']) == min(diagnostic['error_count'], 12),
                    'Invalid finite compiler summary.')
            for item in diagnostic['errors']:
                require(type(item) is dict and set(item) == {'line', 'column', 'category'}
                        and integer(item['line'], 0, 1000000) and integer(item['column'], 0, 1000000)
                        and type(item['category']) is str and item['category'] in COMPILE_CATEGORIES,
                        'Invalid finite compiler location.')
    total = sum(value[key] for key in ('failures', 'errors', 'expectedFailures', 'unexpectedSuccesses'))
    require(len(value['failedTests']) == min(total, 64), 'Incomplete finite failure entries.')
    exact_red = (stage == 'red' and value['tests'] == 1 and value['failures'] == 1
                 and all(value[key] == 0 for key in ('errors', 'skipped', 'expectedFailures', 'unexpectedSuccesses'))
                 and value['failedTests'] == [{'ordinal': 1, 'reason': 'causal_anchor_missing'}])
    require(not value['expectedRegressionFailure'] or exact_red, 'Invalid causal regression claim.')
    passed = (value['expectedRegressionFailure'] if stage == 'red' else
              value['tests'] == expected_count and total == 0 and value['skipped'] == 0
              and not value['expectedRegressionFailure'])
    require(value['status'] == ('passed' if passed else 'failed')
            and type(returncode) is int and returncode == (0 if passed else 1),
            'Inconsistent finite proof result.')
    return value


def regression_env():
    env = request.p.build_env()
    for name in ('GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY'):
        env.pop(name, None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def run_child(source, env, stage, timeout=300):
    """Own temporary outputs even if compilation or the Python runner times out."""
    with tempfile.TemporaryDirectory(prefix='.darwin-anchor-work-', dir=request.p.ROOT) as temporary:
        work = str(Path(temporary).resolve(strict=True))
        child_env = dict(env, TMPDIR=work, TMP=work, TEMP=work)
        process = subprocess.Popen(
            [sys.executable, '-B', '-c', CHILD, stage, MODULE, TARGET, MARKER, str(GREEN_COUNT)],
            cwd=source, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Only this newly-created test process group, never a shared runner process.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise request.p.GateError('Native proof timed out.') from None
        request.p.require(len(stdout) <= 16384, 'Native proof result exceeded finite output bound.')
        return validate_summary(json.loads(stdout), stage, process.returncode)


def final_cleanup():
    """The intermediate baseline cleanup deliberately preserves the manifest."""
    saved = request.p.ROOT / MANIFEST
    try:
        request.p.cleanup()
    finally:
        request.p.require(not saved.exists() or saved.is_file() or saved.is_symlink(),
                          'Invalid private regression manifest path.')
        if saved.exists() or saved.is_symlink():
            saved.unlink()

def test_manifest(source):
    root = source / TEST_DIRECTORY
    request.p.require(root.is_dir() and not root.is_symlink(), 'Missing frozen native regression directory.')
    entries = {}
    for path in sorted(root.rglob('*')):
        request.p.require(not path.is_symlink(), 'Regression symlink forbidden.')
        if path.is_file():
            request.p.require(path.suffix in ('.py', '.m', '.h', '.json', '.md'), 'Unexpected native regression input.')
            entries[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    request.p.require(bool(entries), 'Missing frozen native regression inputs.')
    return entries


def regression(stage):
    p = request.p
    request.context()
    p.checked_sha(BASELINE_SHA); p.checked_sha(SOURCE_SHA)
    if stage == 'cleanup':
        final_cleanup()
        return
    if stage == 'fetch-baseline':
        with patch.dict(os.environ, {'SOURCE_SHA': BASELINE_SHA}):
            p.fetch()
        return
    p.require(stage in ('red', 'green') and sys.platform == 'darwin', 'Real macOS native toolchain required.')
    source = p.ROOT / 'source'
    sha = BASELINE_SHA if stage == 'red' else SOURCE_SHA
    env = regression_env()
    p.require(p.source_version((source / 'pubspec.yaml').read_text()) == request.VERSION, 'Source version mismatch.')
    before = p.source_fingerprint(source, sha, env)
    inputs = test_manifest(source)
    saved = p.ROOT / MANIFEST
    if stage == 'green':
        p.require(saved.is_file() and not saved.is_symlink() and json.loads(saved.read_text()) == inputs,
                  'Baseline and fixed native regression inputs differ.')
    else:
        p.require(not saved.exists() and not saved.is_symlink(), 'Existing native regression manifest refused.')
    try:
        value = run_child(source, env, stage)
        print(json.dumps(value, allow_nan=False), flush=True)
        p.require(value['status'] == 'passed', 'Native position anchor regression failed.')
    finally:
        p.require(p.source_fingerprint(source, sha, env) == before, 'Native regression changed frozen source bytes.')
    if stage == 'red':
        with os.fdopen(os.open(saved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
            json.dump(inputs, handle, sort_keys=True)


def main():
    try:
        request.p.require(len(sys.argv) == 3, 'Invalid anchor validation stage.')
        category, stage = sys.argv[1:]
        request.p.require(category in ('source', 'regression'), 'Unknown validation category.')
        if category == 'source':
            request.p.require(stage in ('prepare', 'fetch', 'validate_source', 'cleanup'), 'Build and publish forbidden.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                            SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA):
            if category == 'regression':
                regression(stage)
                return 0
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                return request.main()
    except Exception:
        print('ERROR: Native anchor validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
