"""Frozen red/green regression and native-only Handoff repair verification."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import current_source_check as request
import current_native_check as native

PARENT = '4afe4129c8a889f116e1f866928395da7b35a8cb'
MESSAGE = 'test: verify bounded handoff start repair 20261022'
WORKFLOW = 'handoff-repair-check.yml'
REQUEST_PATH = 'requests/handoff-repair-20261022.json'
SOURCE_REF = 'refs/heads/fix/handoff-play-initiation-20261022'
SOURCE_SHA = '19639161be7945884d998ecd268d9bc30afcf02d'
BASELINE_SHA = 'cb84d946ed4212c07e2f91afa1a914a0faed446d'
TEST_PATH = 'test/remediation/handoff_play_initiation_test.dart'
TEST_NAME = 'handoff play waits for held source policy before completing'
ASSERTION_MARKER = 'HANDOFF_START_MUST_WAIT_FOR_SOURCE_POLICY'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, mode='handoff-repair-validation', attempt=3)


def intentional_red(raw):
    """Accept exactly the named assertion failure, never compile/setup failure."""
    p = request.p
    message = 'Baseline did not reproduce the exact reviewed regression; details suppressed.'
    events = []
    try:
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (ValueError, TypeError):
        raise p.GateError(message) from None
    p.require(bool(events) and all(isinstance(e, dict) for e in events), message)
    tests = {}
    results = {}
    errors = []
    done = []
    for e in events:
        kind = e.get('type')
        if kind == 'testStart':
            t = e.get('test', {})
            p.require(isinstance(t, dict) and type(t.get('id')) is int and t['id'] not in tests, message)
            tests[t['id']] = t.get('name')
        elif kind == 'testDone':
            tid = e.get('testID')
            p.require(tid in tests and tid not in results and e.get('skipped') is False, message)
            results[tid] = e
        elif kind == 'error':
            errors.append(e)
        elif kind == 'done':
            done.append(e)
        elif kind not in ('start', 'suite', 'allSuites', 'group', 'print'):
            raise p.GateError(message)
    target = [tid for tid, name in tests.items() if name == TEST_NAME]
    p.require(len(target) == 1 and tests.keys() == results.keys() and len(done) == 1
              and done[0].get('success') is False and events[-1] is done[0], message)
    target = target[0]
    p.require(len(errors) == 1 and errors[0].get('testID') == target
              and errors[0].get('isFailure') is True
              and isinstance(errors[0].get('error'), str)
              and ASSERTION_MARKER in errors[0]['error'], message)
    for tid, result in results.items():
        p.require((tid == target and result.get('hidden') is False and result.get('result') == 'failure')
                  or (tid != target and result.get('hidden') is True and result.get('result') == 'success'), message)
    return {'expectedFailures': 1, 'unexpectedFailures': 0}


def regression(stage):
    p = request.p
    request.context()
    p.checked_sha(BASELINE_SHA)
    if stage not in ('fetch-baseline', 'red'):
        raise p.GateError('Invalid regression stage.')
    with patch.dict(os.environ, {'SOURCE_SHA': BASELINE_SHA}):
        if stage == 'fetch-baseline':
            p.fetch()
            return
        source, _, sha, _ = p.source_context(require_server=False)
        env = native.native_env()
        before = p.source_fingerprint(source, sha, env)
        try:
            p.codegen(source, env)
            result = subprocess.run(['flutter', 'test', '--no-pub', '--reporter=json',
                                     '--plain-name', TEST_NAME, TEST_PATH], cwd=source,
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            p.require(result.returncode != 0, 'Regression unexpectedly passed on the unfixed baseline.')
            summary = intentional_red(result.stdout)
        finally:
            p.require(p.source_fingerprint(source, sha, env) == before, 'Baseline source byte integrity changed.')
        print(json.dumps(dict(stage='deterministic-unfixed-baseline', status='expected-failure-confirmed', **summary)))


def main():
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'native', 'regression'):
            raise request.p.GateError('Invalid bounded repair stage.')
        category, stage = sys.argv[1:]
        if category == 'source' and stage not in ('prepare', 'fetch', 'validate_source', 'cleanup'):
            raise request.p.GateError('Package and publishing stages are forbidden.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA):
            if category == 'regression':
                regression(stage)
                return 0
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                return request.main() if category == 'source' else native.main()
    except request.p.GateError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    except Exception:
        print('ERROR: Repair validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
