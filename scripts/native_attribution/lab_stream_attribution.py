"""Disposable-only attribution proof and lab transport decoration.

No GitHub writes, process launches except requested Flutter unit tests, network
security changes, or changes to production/release checkouts are performed.
Caller owns source checkout admission, complete source validation and cleanup.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import inspect
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
API = 'lib/providers/api_client_providers.dart'
HELPER = 'lib/providers/native_lab_scoped_api_client.dart'
TEST = 'test/remediation/native_lab_scoped_attribution_test.dart'
LAB = 'tool/native_playback_mac/run_lab.py'
STATE = '.native_stream_attribution'
BASELINE_HASHES = {
    API: 'd54fb2a39cf28716654993e668c30ce4554df8f1883f97341e08d3b4eaa5cf03',
    'lib/providers/playback_service_providers.dart': 'f0119d8ea448b93eb37901418f54f0b4624746f47dcbdecb4f8c50214ac7f494',
    'lib/services/audio_source_resolver.dart': 'a94bfc82cc738055c2792e6a7cfd3fca7ee080397d1d9217e54094e87569bf1a',
    'lib/data/services/subsonic/subsonic_api_client.dart': 'ec5d75affa2a7f16c59d3dd94e757d04a480aee3fe34b4e0fadbf0a80b32f44f',
    'tool/native_playback_mac/main.dart': '7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833',
}
LAB_MAIN = 'tool/native_playback_mac/main.dart'
LAB_DEBUG_MAIN_SHA256 = 'f8781ae5077924daebc0908500f79e57ee9a80af8e9d25d474468651563d2af0'
TIMING_OBSERVED_LAB_SHA256 = '44da20c4a134df49d857b800185a287eb8764e4a6563553ff9f89fc0acda59bc'
TIMING_BASELINE_LAB_SHA256 = '55ba43b3d08fe525677c544f2dc583cb5aef05699b23ee63a98f01a18aacbb0f'
IMPORT = "import 'native_lab_scoped_api_client.dart';\n"
ORIGINAL = '''SubsonicApiClient createAccountApiClient(Ref ref, AccountSession session) {
  session.requestContext.ensureCurrent();
  return SubsonicApiClient('''
REPLACEMENT = ORIGINAL.replace('return SubsonicApiClient(', 'return NativeLabScopedApiClient(')
ENV_KEY = 'EMOSONIC_NATIVE_LAB_STREAM_SCOPE_JSON'
TEST_NAMES = (
    'actual scoped factory and resolver attribution expectation is explicit',
    'actual scoped factory and resolver bypass the compatibility override',
    'decoration preserves original URL bytes and every query value',
    'decoration rejects external origin wrong port route and unowned tracks',
    'superclass rejects revoked signed out and unreadable account first',
    'scoped subclass forwards stream options without changing authentication',
)
SOURCE_MODULES = {
    TEST: 'native_lab_scoped_attribution_test.dart',
    HELPER: 'native_lab_scoped_api_client.dart',
    API: 'api_client_providers.dart',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(repo, relative):
    path = repo / relative
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Attribution source must be an owned regular file')
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError('Attribution source escaped its checkout')
    return path


def checked_new_path(repo, relative):
    path = repo / relative
    if (path.exists() or any(item.is_symlink() for item in (path, *path.parents))
            or not path.resolve().is_relative_to(repo.resolve())
            or any(item.exists() and not item.is_dir() for item in path.parents)):
        raise ValueError('Attribution output must be a fresh contained regular path')
    return path


@contextmanager
def lab_debug_observation(repo, enabled=False):
    """Explicit opt-in admits exactly one reviewed disposable lab log setting.

    Default source admission is unchanged. Always prove the debug bytes reverse
    to the original pinned lab main; all other baseline hashes stay identical.
    """
    if type(enabled) is not bool:
        raise ValueError('Lab debug observation mode refused')
    original_hash = BASELINE_HASHES[LAB_MAIN]
    if enabled:
        data = checked_file(repo, LAB_MAIN).read_bytes()
        old = b'  await Logger.setLogLevel(LogLevel.warning);\n'
        new = b'  await Logger.setLogLevel(LogLevel.debug);\n'
        if (digest(data) != LAB_DEBUG_MAIN_SHA256 or data.count(new) != 1
                or digest(data.replace(new, old, 1)) != '7e4b804a9eaeeec929768ddd9ce9a5479639f73f443a8f3e6693916e59565833'):
            raise ValueError('Lab debug observation main roundtrip refused')
        BASELINE_HASHES[LAB_MAIN] = LAB_DEBUG_MAIN_SHA256
    try:
        yield
    finally:
        BASELINE_HASHES[LAB_MAIN] = original_hash


def verify_baseline(repo):
    return {name: digest(checked_file(repo, name).read_bytes())
            for name in BASELINE_HASHES}


def decorate_factory(original):
    text = original.decode('utf-8')
    if digest(original) != BASELINE_HASHES[API] or text.count(ORIGINAL) != 1:
        raise ValueError('Account factory no longer matches reviewed baseline')
    # Exact two edits. Every guard, outcome callback, account and config byte is
    # retained. No production provider caching/disposal logic is modified.
    updated = IMPORT + text.replace(ORIGINAL, REPLACEMENT, 1)
    if updated.removeprefix(IMPORT).replace(REPLACEMENT, ORIGINAL, 1) != text:
        raise ValueError('Account factory round-trip integrity failed')
    return updated.encode('utf-8')


def native_lab_stream_scope(credentials, fixture):
    """Allow only the generated, owned loopback fixture and its exact tracks."""
    base = credentials.get('baseUrl') if isinstance(credentials, dict) else None
    if not isinstance(fixture, dict) or fixture.get('baseUrl') != base or not isinstance(base, str):
        raise ValueError('Native lab fixture scope mismatch')
    uri = urlsplit(base)
    if (uri.scheme != 'http' or uri.hostname != '127.0.0.1' or not uri.port
            or uri.username is not None or uri.password is not None
            or uri.query or uri.fragment or uri.path not in ('', '/')
            or uri.netloc != '127.0.0.1:' + str(uri.port)):
        raise ValueError('Native lab fixture origin refused')
    rows = fixture.get('tracks')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError('Native lab fixture tracks refused')
    ids = [row.get('id') if isinstance(row, dict) else None for row in rows]
    if (any(not isinstance(value, str) or not 1 <= len(value) <= 200 for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Native lab fixture track identities refused')
    # No credentials, tokens or arbitrary hostnames are copied into this value.
    return json.dumps({'streamUrl': 'http://' + uri.netloc + '/rest/stream',
                       'trackIds': ids}, separators=(',', ':'))


def decorate_lab(original):
    text = original.decode('utf-8')
    anchor = "            fixture = json.loads((state / 'fixture.json').read_text())\n"
    definition = '\nclass Client:\n'
    assignment = "            os.environ['EMOSONIC_NATIVE_LAB_STREAM_SCOPE_JSON'] = native_lab_stream_scope(credentials, fixture)\n"
    if text.count(anchor) != 1 or text.count(definition) != 1 or 'def native_lab_stream_scope(' in text:
        raise ValueError('Native fixture handoff no longer matches reviewed anchor')
    if 'from urllib.parse import urlsplit\n' not in text:
        raise ValueError('Native lab URL parser import missing')
    if "env = dict(os.environ, EMOSONIC_NATIVE_LAB='1', EMOSONIC_NATIVE_LAB_ID=self.role," not in text:
        raise ValueError('Native app environment inheritance changed')
    helper = '\n' + inspect.getsource(native_lab_stream_scope) + '\n'
    updated = text.replace(definition, helper + definition, 1).replace(anchor, anchor + assignment, 1)
    if updated.replace(helper + definition, definition, 1).replace(anchor + assignment, anchor, 1) != text:
        raise ValueError('Native lab round-trip integrity failed')
    return updated.encode('utf-8')


def completed_tests(raw):
    """Only a fully successful JSON test stream counts, not compile/setup exit."""
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    tests, finished = {}, {}
    done = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Invalid Flutter test event')
        kind = event.get('type')
        if kind == 'testStart':
            test = event['test']
            if (not isinstance(test, dict) or type(test.get('id')) is not int
                    or test['id'] in tests or not isinstance(test.get('name'), str)):
                raise ValueError('Duplicate Flutter test')
            tests[test['id']] = test.get('name')
        elif kind == 'testDone':
            key = event.get('testID')
            if key not in tests or key in finished or event.get('result') != 'success' or event.get('skipped') is not False:
                raise ValueError('Flutter test not successful')
            finished[key] = event
        elif kind == 'error':
            raise ValueError('Flutter reported a failure')
        elif kind == 'done':
            done.append(event)
        elif kind not in ('start', 'suite', 'allSuites', 'group', 'print'):
            raise ValueError('Unknown Flutter test event')
    visible = [key for key in finished if finished[key].get('hidden') is False]
    if (len(visible) != 6 or {tests[key] for key in visible} != set(TEST_NAMES)
            or set(tests) != set(finished) or len(done) != 1
            or done[0].get('success') is not True or events[-1] != done[0]):
        raise ValueError('Flutter attribution proof incomplete')
    return len(visible)


def proof_failure_diagnostic(phase, *, stdout='', stderr='', exit_code=None,
                             runner_code=None):
    """Finite public diagnostic only. Never copy messages, assertions or URIs.

    Raw reporter/compiler output remains private. Even hostile diagnostic input
    can emit only enumerated fields, bounded ordinals/lines and process status.
    """
    if phase not in ('baseline', 'patched'):
        raise ValueError('Unknown attribution proof phase')
    diagnostic = {'phase': phase, 'category': 'process', 'code': 'process_failed'}
    if type(exit_code) is int and -255 <= exit_code <= 255:
        diagnostic['exitCode'] = exit_code
    if runner_code in ('runner_timeout', 'runner_unavailable'):
        diagnostic.update(category='runner', code=runner_code)
    else:
        stdout = stdout if isinstance(stdout, str) else ''
        stderr = stderr if isinstance(stderr, str) else ''
        # Do not scan arbitrary-sized build logs or let parsing copy their text.
        rows = []
        if len(stdout) <= 1024 * 1024:
            for line in stdout.splitlines()[:10000]:
                if len(line) > 65536:
                    continue
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        names = {}
        for row in rows:
            value = row.get('test')
            if row.get('type') == 'testStart' and isinstance(value, dict):
                name, key = value.get('name'), value.get('id')
                if type(key) is int and name in TEST_NAMES:
                    names[key] = TEST_NAMES.index(name) + 1
        errors = [row for row in rows if row.get('type') == 'error']
        assertion = next((row for row in errors if row.get('isFailure') is True), None)
        location_text = ''
        if assertion is not None:
            diagnostic.update(category='assertion', code='assertion_failed')
            test_id = assertion.get('testID')
            ordinal = names.get(test_id) if type(test_id) is int else None
            if ordinal is not None:
                diagnostic['failedTestOrdinal'] = ordinal
            stack = assertion.get('stackTrace')
            if isinstance(stack, str):
                location_text = stack[:65536]
        else:
            compilation = stderr[:65536]
            for error in errors[:8]:
                value = error.get('error')
                if isinstance(value, str):
                    compilation += '\n' + value[:65536]
            # These are classification tokens only; none are echoed.
            compiler = ('Compilation failed' in compilation
                        or 'Error: ' in compilation
                        or 'COMPILE_TIME_ERROR' in compilation)
            if compiler:
                diagnostic.update(category='compiler', code='compilation_failed')
                location_text = compilation
            elif exit_code == 0:
                diagnostic.update(category='reporter', code='invalid_test_stream')
        for relative, module in SOURCE_MODULES.items():
            # A source frame may be absolute or package-relative. Emit only the
            # known basename and bounded source line, never its path or context.
            package_relative = relative.removeprefix('lib/') if relative.startswith('lib/') else relative
            pattern = r'(?:' + re.escape(relative) + '|' + re.escape(package_relative) + r'):(\d{1,4})(?!\d)(?::\d{1,4}(?!\d))?'
            match = re.search(pattern, location_text)
            if match and 1 <= int(match.group(1)) <= 2000:
                diagnostic.update(sourceModule=module, sourceLine=int(match.group(1)))
                break
    return {'stage': 'scoped-attribution-proof-failure', 'status': 'failed',
            'diagnostic': diagnostic}


def proof_environment():
    # Match the existing hardened native environment. Never let tested source
    # write GitHub command files, inherit build secrets, or use a user server.
    command_files = {'GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY'}
    env = {key: value for key, value in os.environ.items()
           if key not in command_files | {'DEFAULT_SERVER_URL', 'EMOSONIC_MAC_LAB_CREDENTIALS_JSON'}
           and not any(word in key.upper() for word in ('TOKEN', 'PASSWORD', 'SECRET', 'KEYSTORE', 'KEY_ALIAS'))}
    env.update(EMOSONIC_NATIVE_LAB='1', EMOSONIC_NATIVE_LAB_ID='target')
    env[ENV_KEY] = json.dumps({'streamUrl': 'http://127.0.0.1:31337/rest/stream',
                              'trackIds': ['fixture-track-a']})
    return env


def prove_and_patch(repo, *, lab_timing_observation=False):
    _verify_timing_observation(repo, enabled=lab_timing_observation)
    """Run unchanged and decorated production factory/resolver on hosted Flutter.

    Call after Flutter pub get/codegen on the disposable native checkout, not in
    the pristine production source-validation job. Leaves decoration only if
    both unit runs pass. Full JSON stays private inside the disposable checkout.
    """
    if any(path.is_symlink() for path in (repo, *repo.parents)):
        raise ValueError('Attribution checkout cannot use symlink routing')
    repo = repo.resolve()
    if verify_baseline(repo) != BASELINE_HASHES:
        raise ValueError('Attribution source wiring changed')
    # Check all destinations before any write, including dangling symlinks and
    # symlinked ancestors which .exists() alone deliberately does not detect.
    targets = {path: checked_new_path(repo, path) for path in (HELPER, TEST, STATE)}
    private = targets[STATE]
    private.mkdir()
    for path in (HELPER, TEST):
        target = targets[path]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / 'payload' / target.name).read_bytes())
    api = checked_file(repo, API)
    original = api.read_bytes()
    patched = decorate_factory(original)
    env = proof_environment()
    summary = {}
    success = False
    try:
        for phase in ('baseline', 'patched'):
            if phase == 'patched':
                api.write_bytes(patched)
            env['EMOSONIC_NATIVE_LAB_EXPECT_ATTRIBUTION'] = phase
            try:
                result = subprocess.run(['flutter', 'test', '--no-pub', '--reporter=json',
                                         '--dart-define=EMOSONIC_NATIVE_MAC_LAB=true', TEST],
                                        cwd=repo, env=env, capture_output=True, text=True,
                                        timeout=300)
            except subprocess.TimeoutExpired:
                print(json.dumps(proof_failure_diagnostic(phase,
                    runner_code='runner_timeout')), flush=True)
                raise ValueError('Attribution unit runner timed out') from None
            except OSError:
                print(json.dumps(proof_failure_diagnostic(phase,
                    runner_code='runner_unavailable')), flush=True)
                raise ValueError('Attribution unit runner unavailable') from None
            checked_new_path(repo, STATE + '/' + phase + '.jsonl').write_text(result.stdout, encoding='utf-8')
            checked_new_path(repo, STATE + '/' + phase + '.stderr').write_text(result.stderr, encoding='utf-8')
            if result.returncode != 0:
                print(json.dumps(proof_failure_diagnostic(phase, stdout=result.stdout,
                    stderr=result.stderr, exit_code=result.returncode)), flush=True)
                raise ValueError('Attribution ' + phase + ' unit run failed; inspect private diagnostics')
            try:
                summary[phase] = completed_tests(result.stdout)
            except (ValueError, TypeError, KeyError):
                print(json.dumps(proof_failure_diagnostic(phase, stdout=result.stdout,
                    stderr=result.stderr, exit_code=result.returncode)), flush=True)
                raise ValueError('Attribution unit reporter proof incomplete') from None
            print(json.dumps({'stage': 'scoped-attribution-' + phase, 'status': 'passed',
                              'count': summary[phase]}), flush=True)
        for name, sha in BASELINE_HASHES.items():
            expected = digest(patched) if name == API else sha
            if digest(checked_file(repo, name).read_bytes()) != expected:
                raise ValueError('Attribution proof altered unrelated source wiring')
        manifest = {
            'status': 'baseline-omission-and-patched-role-proven',
            'checks': summary,
            'files': {name: {'before': sha, 'after': digest(patched) if name == API else sha}
                      for name, sha in BASELINE_HASHES.items()},
            'added': {name: digest(checked_file(repo, name).read_bytes()) for name in (HELPER, TEST)},
            'productionRepositoryMutation': False,
            'disposableFactoryConstructorOnly': True,
            'authGuardRouteAndAccountBindingPreserved': True,
        }
        checked_new_path(repo, STATE + '/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        success = True
        return manifest
    finally:
        if not success:
            checked_file(repo, API).write_bytes(original)


def verified_manifest(repo, *, native_applied=False):
    """Revalidate all independently pinned factory and packaged-payload bytes."""
    manifest_path = checked_file(repo, STATE + '/manifest.json')
    manifest = json.loads(manifest_path.read_text())
    expected_fields = {'status', 'checks', 'files', 'added', 'productionRepositoryMutation',
                       'disposableFactoryConstructorOnly', 'authGuardRouteAndAccountBindingPreserved'}
    if native_applied:
        expected_fields.add('nativeFixtureEnvironment')
    if (not isinstance(manifest, dict) or set(manifest) != expected_fields
            or manifest.get('status') != 'baseline-omission-and-patched-role-proven'
            or manifest.get('checks') != {'baseline': 6, 'patched': 6}
            or manifest.get('productionRepositoryMutation') is not False
            or manifest.get('disposableFactoryConstructorOnly') is not True
            or manifest.get('authGuardRouteAndAccountBindingPreserved') is not True
            or not isinstance(manifest.get('files'), dict)
            or set(manifest['files']) != set(BASELINE_HASHES)
            or not isinstance(manifest.get('added'), dict)
            or set(manifest['added']) != {HELPER, TEST}):
        raise ValueError('Actual factory/resolver proof must precede native instrumentation')
    # Derive expected API bytes independently of the manifest. A forged after
    # hash cannot approve a different constructor patch or modified guard.
    api_after = checked_file(repo, API).read_bytes()
    text = api_after.decode('utf-8')
    if not text.startswith(IMPORT) or text.count(REPLACEMENT) != 1:
        raise ValueError('Proven account factory decoration changed')
    original = text.removeprefix(IMPORT).replace(REPLACEMENT, ORIGINAL, 1).encode('utf-8')
    if decorate_factory(original) != api_after:
        raise ValueError('Proven account factory byte preservation failed')
    for name, before in BASELINE_HASHES.items():
        after = digest(api_after) if name == API else before
        hashes = manifest['files'][name]
        if (not isinstance(hashes, dict) or set(hashes) != {'before', 'after'}
                or hashes != {'before': before, 'after': after}
                or digest(checked_file(repo, name).read_bytes()) != after):
            raise ValueError('Proven attribution inputs changed')
    for name in (HELPER, TEST):
        sha = digest((ROOT / 'payload' / Path(name).name).read_bytes())
        if manifest['added'][name] != sha or digest(checked_file(repo, name).read_bytes()) != sha:
            raise ValueError('Proven attribution helper changed')
    return manifest


def _verify_timing_observation(repo, *, enabled=False, observed=None):
    if type(enabled) is not bool:
        raise ValueError('Attribution timing observation mode refused')
    if not enabled:
        return
    modules = {}
    for name in ('native_seek_anchor_observation', 'native_follow_lifecycle'):
        path = ROOT.parent / (name + '.py')
        if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError('Attribution timing verifier path refused')
        spec = importlib.util.spec_from_file_location('owned_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    timing = modules['native_seek_anchor_observation']
    lifecycle = modules['native_follow_lifecycle']
    if (timing.HARNESS_SHA != TIMING_BASELINE_LAB_SHA256
            or timing.AFTER[LAB] != TIMING_OBSERVED_LAB_SHA256
            or lifecycle.AFTER_HARNESS_SHA256 != TIMING_BASELINE_LAB_SHA256):
        raise ValueError('Attribution timing fixed hash chain changed')
    timing.verify_prepared(repo, require_harness=observed is None)
    content = checked_file(repo, LAB).read_bytes() if observed is None else observed
    if digest(content) != TIMING_OBSERVED_LAB_SHA256 or digest(timing.restore_harness(content)) != TIMING_BASELINE_LAB_SHA256:
        raise ValueError('Attribution timing inverse changed')
    lifecycle.verify_prepared(repo, require_harness=False)


def apply_native_handoff(repo, *, expected_lab_before_sha256, lab_timing_observation=False):
    _verify_timing_observation(repo, enabled=lab_timing_observation)
    manifest = verified_manifest(repo)
    lab = checked_file(repo, LAB)
    original = lab.read_bytes()
    if digest(original) != expected_lab_before_sha256:
        raise ValueError('Native attribution observed harness pin changed')
    updated = decorate_lab(original)
    lab.write_bytes(updated)
    manifest['nativeFixtureEnvironment'] = {'before': digest(original), 'after': digest(updated)}
    manifest_path = checked_file(repo, STATE + '/manifest.json')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def verify_applied(repo, *, expected_lab_before_sha256, lab_timing_observation=False):
    """Read-only gate for every later native build, Handoff and Follow phase.

    The mandatory expected hash independently pins the already-observed harness
    supplied as a static constant by the wrapper, never derived at runtime.
    """
    manifest = verified_manifest(repo, native_applied=True)
    native = manifest['nativeFixtureEnvironment']
    if (not isinstance(native, dict) or set(native) != {'before', 'after'}
            or any(not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None
                   for value in native.values())):
        raise ValueError('Native attribution manifest hashes invalid')
    updated = checked_file(repo, LAB).read_bytes()
    if digest(updated) != native['after']:
        raise ValueError('Proven native attribution harness changed')
    text = updated.decode('utf-8')
    definition = '\nclass Client:\n'
    helper = '\n' + inspect.getsource(native_lab_stream_scope) + '\n'
    anchor = "            fixture = json.loads((state / 'fixture.json').read_text())\n"
    assignment = "            os.environ['EMOSONIC_NATIVE_LAB_STREAM_SCOPE_JSON'] = native_lab_stream_scope(credentials, fixture)\n"
    if text.count(helper + definition) != 1 or text.count(anchor + assignment) != 1:
        raise ValueError('Native attribution additions changed')
    original = text.replace(helper + definition, definition, 1).replace(anchor + assignment, anchor, 1).encode('utf-8')
    if digest(original) != native['before'] or decorate_lab(original) != updated:
        raise ValueError('Native attribution before/after roundtrip failed')
    if expected_lab_before_sha256 != native['before']:
        raise ValueError('Native attribution observed harness pin changed')
    _verify_timing_observation(repo, enabled=lab_timing_observation, observed=original)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('proof', 'native', 'verify'))
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--expected-lab-before-sha256')
    parser.add_argument('--lab-debug-observation', action='store_true')
    parser.add_argument('--lab-timing-observation', action='store_true')
    args = parser.parse_args()
    if args.stage != 'proof' and (args.expected_lab_before_sha256 is None or
            re.fullmatch(r'[0-9a-f]{64}', args.expected_lab_before_sha256) is None):
        parser.error('native and verify require an independent expected lab before hash')
    with lab_debug_observation(args.repo, enabled=args.lab_debug_observation):
        if args.stage == 'proof':
            prove_and_patch(args.repo, lab_timing_observation=args.lab_timing_observation)
        elif args.stage == 'native':
            apply_native_handoff(args.repo, expected_lab_before_sha256=args.expected_lab_before_sha256,
                                 lab_timing_observation=args.lab_timing_observation)
        else:
            verify_applied(args.repo, expected_lab_before_sha256=args.expected_lab_before_sha256,
                           lab_timing_observation=args.lab_timing_observation)


if __name__ == '__main__':
    main()
