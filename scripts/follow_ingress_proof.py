"""One immutable ingress expected-red proof. No repair, native or release claim."""
from functools import partial
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
from unittest.mock import patch

import current_source_check as request
from current_native_check import native_env
from fixed_flutter_green import (MAX_BYTES, MAX_EVENTS, GreenVerificationError,
                                 observe_green, verify_green)
from follow_recovery_check import owned_file

PARENT = '3b1d1382bf6f838aab64560ca88576c6bc5a8afc'
MESSAGE = 'test: classify ordered stale ingress replay 20261022'
WORKFLOW = 'follow-ingress-proof.yml'
REQUEST_PATH = 'requests/follow-ingress-proof-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-ingress-native-order-20261022'
SOURCE_SHA = '5506dac821413f046c2463892c76eb1780746313'
BASELINE_SHA = '466f56d9935afb299724a212d680a743a11c723f'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
INVENTORY_PATH = 'tool/follow_ingress/test_inventory.json'
INVENTORY_SHA256 = '8148ee360c01501679c4825cb417f84ec5b404d4de12dffe804ad153ba42d49f'
ASSERTION_MARKER = 'FOLLOW_INGRESS_STALE_PENDING_APPLY_REPLAYED'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA,
               mode='follow-ingress-expected-red-proof', attempt=31)
STAGE = 'entry'


def strict_json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError('Duplicate JSON key.')
            obj[key] = value
        return obj
    def number(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError('Non-finite JSON.')
        return value
    def constant(_):
        raise ValueError('Non-finite JSON.')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=constant)


def inventory(source):
    p = request.p
    path = owned_file(source, INVENTORY_PATH)
    p.require(path.stat().st_size <= 65536, 'Private inventory size invalid.')
    raw = path.read_bytes()
    p.require(hashlib.sha256(raw).hexdigest() == INVENTORY_SHA256,
              'Private inventory changed.')
    value = strict_json(raw)
    p.require(type(value) is dict and set(value) == {'suites'}
              and type(value['suites']) is list and len(value['suites']) == 1,
              'Private suite inventory invalid.')
    suite = value['suites'][0]
    p.require(type(suite) is dict and set(suite) == {'path', 'sha256', 'names', 'causalOrdinal'},
              'Private suite schema invalid.')
    p.require(type(suite['path']) is str and re.fullmatch(
        r'test/services/[a-z0-9_]+_test\.dart', suite['path']), 'Private fixture path invalid.')
    p.require(type(suite['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', suite['sha256']),
              'Private fixture digest invalid.')
    fixture = owned_file(source, suite['path'])
    p.require(fixture.stat().st_size <= 2 * 1024 * 1024
              and hashlib.sha256(fixture.read_bytes()).hexdigest() == suite['sha256'],
              'Frozen fixture changed.')
    names = suite['names']
    p.require(type(names) is list and len(names) == 3
              and all(type(name) is str and 0 < len(name) <= 8192 for name in names)
              and len(set(names)) == 3 and type(suite['causalOrdinal']) is int
              and 1 <= suite['causalOrdinal'] <= 3, 'Private visible inventory invalid.')
    return suite


def exact_red(raw, returncode, *, names, basename, causal_ordinal, stderr=''):
    """Normalize only one already-proved causal failure, then reuse strict green."""
    def fail(reason):
        raise GreenVerificationError(dict(stage='follow-ingress-red', status='failed', reason=reason))
    if (type(names) not in (list, tuple) or len(names) != 3
            or any(type(name) is not str or not name or len(name) > 8192 for name in names)
            or len(set(names)) != 3 or type(causal_ordinal) is not int or not 1 <= causal_ordinal <= 3):
        fail('invalid-inventory')
    if type(returncode) is not int or returncode != 1:
        fail('expected-exit-one')
    if type(raw) is not str or type(stderr) is not str:
        fail('invalid-output')
    if len(raw.encode('utf-8')) + len(stderr.encode('utf-8')) > MAX_BYTES:
        fail('output-limit')
    if re.search(r'(?:^|\n)[^\n]*\.dart:[0-9]{1,6}:[0-9]{1,6}: Error:', raw + '\n' + stderr):
        fail('compiler-diagnostic')
    events = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if len(events) >= MAX_EVENTS:
            fail('event-limit')
        try:
            event = strict_json(line)
        except (ValueError, RecursionError):
            fail('malformed-json')
        if type(event) is not dict:
            fail('malformed-event')
        events.append(event)
    errors = [(index, event) for index, event in enumerate(events) if event.get('type') == 'error']
    if len(errors) != 1:
        fail('expected-single-error')
    starts = [(index, event['test']) for index, event in enumerate(events)
              if event.get('type') == 'testStart' and type(event.get('test')) is dict
              and event['test'].get('name') == names[causal_ordinal - 1]]
    if len(starts) != 1 or type(starts[0][1].get('id')) is not int:
        fail('causal-start-mismatch')
    start_index, target = starts[0]
    tid = target['id']
    error_index, error = errors[0]
    if (type(error.get('testID')) is not int or error['testID'] != tid
            or error.get('isFailure') is not True or error.get('error') != ASSERTION_MARKER):
        fail('causal-error-mismatch')
    completions = [(index, event) for index, event in enumerate(events)
                   if event.get('type') == 'testDone' and type(event.get('testID')) is int
                   and event['testID'] == tid]
    if len(completions) != 1:
        fail('causal-completion-mismatch')
    completion_index, completion = completions[0]
    if (not start_index < error_index < completion_index
            or completion.get('hidden') is not False or completion.get('skipped') is not False
            or completion.get('result') != 'failure'):
        fail('causal-completion-mismatch')
    terminals = [event for event in events if event.get('type') == 'done']
    if len(terminals) != 1 or terminals[0].get('success') is not False or events[-1] is not terminals[0]:
        fail('terminal-mismatch')
    # Nothing else is removed or changed. The unchanged verifier owns inventory,
    # controls, all lifecycle results, skips, duplicate IDs and complete accounting.
    normalized = []
    for event in events:
        if event is error:
            continue
        if event is completion:
            event = dict(event, result='success')
        elif event is terminals[0]:
            event = dict(event, success=True)
        normalized.append(json.dumps(event, allow_nan=False))
    report = verify_green('\n'.join(normalized), 0, expected_names=names,
                          fixture_basename=basename, stderr=stderr)
    return dict(stage='follow-ingress-red', status='expected-failure-confirmed',
                visibleTests=report['visibleTests'], hiddenTests=report['hiddenTests'],
                completedTests=report['completedTests'], causalOrdinal=causal_ordinal,
                expectedFailures=1, passedControls=2, unexpectedFailures=0)


EVIDENCE_PREFIX = 'FOLLOW_INGRESS_NATIVE_ORDER '
EVIDENCE_CHANGES = ('same_generation', 'authority_owner', 'control_cursor')


def dispatch_observation(raw, names):
    """Retain only the agreed three case-scoped finite native dispatch records."""
    report = dict(stage='follow-ingress-native-order', reportCount=0, invalidReports=0, records=[])
    if type(raw) is not str or len(raw.encode('utf-8')) > MAX_BYTES:
        return dict(report, reason='output-limit')
    starts, completed, seen = {}, set(), set()
    metrics = {'bSampleElapsedMs': (0, 60000), 'cSampleElapsedMs': (0, 60000),
               'bPositionMs': (0, 300000), 'cPositionMs': (0, 300000),
               'pendingTargetMs': (0, 300000), 'bSequence': (2, 2), 'cSequence': (3, 3),
               'metadataRequests': (2, 9), 'backwardCount': (0, 9)}
    keys = set(metrics) | {'change', 'whileHeld', 'nativeSeeks'}
    events = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        events += 1
        if events > MAX_EVENTS:
            return dict(report, reason='event-limit')
        try:
            event = strict_json(line)
        except (ValueError, RecursionError):
            continue  # The unchanged whole-stream observer and verifier reject it.
        if type(event) is not dict:
            continue
        kind = event.get('type')
        tid = event.get('testID')
        if kind == 'testStart' and type(event.get('test')) is dict:
            test = event['test']
            if type(test.get('id')) is int:
                starts[test['id']] = (names.index(test.get('name')) + 1
                                      if test.get('name') in names and test['id'] not in starts else None)
        elif kind == 'testDone' and type(tid) is int:
            completed.add(tid)
        elif kind == 'print' and type(event.get('message')) is str and event['message'].startswith(EVIDENCE_PREFIX):
            report['reportCount'] += 1
            ordinal = starts.get(tid) if type(tid) is int else None
            try:
                if ordinal is None or ordinal in seen or tid in completed or len(event['message']) > 4096:
                    raise ValueError('Invalid case-scoped evidence.')
                value = strict_json(event['message'][len(EVIDENCE_PREFIX):])
                if (type(value) is not dict or set(value) != keys
                        or value['change'] != EVIDENCE_CHANGES[ordinal - 1]
                        or any(type(value[key]) is not int or not low <= value[key] <= high
                               for key, (low, high) in metrics.items())
                        or value['cSampleElapsedMs'] <= value['bSampleElapsedMs']):
                    raise ValueError('Invalid finite evidence.')
                for key in ('whileHeld', 'nativeSeeks'):
                    if type(value[key]) is not list or len(value[key]) >= 10:
                        raise ValueError('Invalid dispatch count.')
                    for item in value[key]:
                        if (type(item) is not dict or set(item) != {'phase', 'targetMs', 'nativeBeforeMs', 'completed'}
                                or item['phase'] not in ('A_loading', 'C_accepted_B_held', 'B_released')
                                or type(item['completed']) is not bool
                                or any(type(item[name]) is not int or not 0 <= item[name] <= 300000
                                       for name in ('targetMs', 'nativeBeforeMs'))):
                            raise ValueError('Invalid dispatch evidence.')
                seen.add(ordinal)
                report['records'].append(dict(testOrdinal=ordinal, **value))
            except (ValueError, TypeError, RecursionError):
                report['invalidReports'] += 1
    report['records'].sort(key=lambda record: record['testOrdinal'])
    return report


PHASE_PREFIX = 'FOLLOW_INGRESS_STAGE '
PHASE_STEPS = ('create', 'harnessInitialize', 'audioPlayQueue', 'audioUntilPlaying',
               'audioPause', 'audioSeek', 'startFollow', 'firstMetadata', 'firstHold',
               'bDrain', 'secondMetadata', 'mirrorReady', 'secondHold', 'cDrain',
               'secondReturned', 'replayCompletion', 'stalePreflightExit',
               'currentCCompletion', 'finalDrain', 'disposeDrain', 'playbackDispose')
PHASE_STAGES = frozenset(step + suffix for step in PHASE_STEPS for suffix in ('.before', '.after')) | {
    'bIngress.accepted', 'cIngress.accepted'}


def phase_observation(raw, names):
    """Diagnostic only: three bounded, case-scoped fixed-enum await histories."""
    report = dict(stage='follow-ingress-phases', reportCount=0, invalidReports=0,
                  cases=[dict(testOrdinal=i, stages=[], lastStage=None) for i in range(1, 4)])
    if type(raw) is not str or len(raw.encode('utf-8')) > MAX_BYTES:
        return dict(report, reason='output-limit')
    starts, completed = {}, set()
    events = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        events += 1
        if events > MAX_EVENTS:
            return dict(report, reason='event-limit')
        try:
            event = strict_json(line)
        except (ValueError, RecursionError):
            continue  # The original whole-stream accounting still owns acceptance.
        if type(event) is not dict:
            continue
        kind, tid = event.get('type'), event.get('testID')
        if kind == 'testStart' and type(event.get('test')) is dict:
            test = event['test']
            if type(test.get('id')) is int:
                starts[test['id']] = (names.index(test.get('name')) + 1
                                      if test.get('name') in names and test['id'] not in starts else None)
        elif kind == 'testDone' and type(tid) is int:
            completed.add(tid)
        elif kind == 'print' and type(event.get('message')) is str and event['message'].startswith(PHASE_PREFIX):
            report['reportCount'] += 1
            ordinal = starts.get(tid) if type(tid) is int else None
            try:
                if ordinal is None or tid in completed or len(event['message']) > 256:
                    raise ValueError('Invalid case-scoped phase.')
                value = strict_json(event['message'][len(PHASE_PREFIX):])
                if (type(value) is not dict or set(value) != {'caseOrdinal', 'stage'}
                        or type(value['caseOrdinal']) is not int or value['caseOrdinal'] != ordinal
                        or type(value['stage']) is not str or value['stage'] not in PHASE_STAGES
                        or len(report['cases'][ordinal - 1]['stages']) >= 48):
                    raise ValueError('Invalid finite phase.')
                case = report['cases'][ordinal - 1]
                case['stages'].append(value['stage'])
                case['lastStage'] = value['stage']
            except (ValueError, TypeError, RecursionError):
                report['invalidReports'] += 1
    return report


def bounded_run(args, cwd=None, env=None, *, timeout=600, max_bytes=MAX_BYTES):
    """Linux-only in-memory capture, process-group stop, no raw log artifacts."""
    chunks = {'stdout': bytearray(), 'stderr': bytearray()}
    total = 0
    reason = None
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    deadline = time.monotonic() + timeout
    def stop():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        with selectors.DefaultSelector() as selector:
            for label in chunks:
                selector.register(getattr(process, label), selectors.EVENT_READ, label)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = 'timeout'
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    keep = min(len(data), max_bytes - total)
                    chunks[key.data].extend(data[:keep])
                    total += keep
                    if keep != len(data):
                        reason = 'output-limit'
                        break
                if reason:
                    break
        if reason:
            stop()
        try:
            code = process.wait(timeout=max(0.1, deadline - time.monotonic()) if not reason else 5)
        except subprocess.TimeoutExpired:
            reason = 'timeout'
            stop()
            code = process.wait(timeout=5)
    finally:
        if process.poll() is None:
            stop()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    return (subprocess.CompletedProcess(args, code, chunks['stdout'].decode('utf-8', errors='replace'),
                                       chunks['stderr'].decode('utf-8', errors='replace')), reason)


def bounded_quiet(args, cwd=None, env=None, *, suite=None):
    global STAGE
    setup = {('flutter', 'pub', 'get'): 'dependencies',
             ('dart', 'run', 'scripts/check_navigation_consistency.dart'): 'navigation-check',
             ('dart', 'run', 'build_runner', 'build', '--delete-conflicting-outputs'): 'codegen'}
    if tuple(args) in setup:
        STAGE = setup[tuple(args)]
    result, reason = bounded_run(args, cwd, env)
    if reason or result.returncode != 0:
        report = observe_green(result.stdout, result.returncode, expected_names=suite['names'],
                               fixture_basename=Path(suite['path']).name, stderr=result.stderr) if suite else {}
        report.update(stage=STAGE, status='failed', reason=reason or 'command-failed',
                      exitCode=max(-1000, min(result.returncode, 1000)))
        print(json.dumps(report), flush=True)
        raise request.p.GateError('Bounded command failed; private details suppressed.')
    return result.stdout


def prove():
    global STAGE
    p = request.p
    STAGE = 'source-context'
    source, _, sha, _ = p.source_context(require_server=False)
    env = native_env()
    STAGE = 'initial-fingerprint'
    before = p.source_fingerprint(source, sha, env)
    try:
        STAGE = 'inventory'
        suite = inventory(source)
        STAGE = 'codegen'
        with patch.object(p, 'quiet', partial(bounded_quiet, suite=suite)):
            p.codegen(source, env)
        STAGE = 'flutter-test'
        result, reason = bounded_run(['flutter', 'test', '--no-pub', '--reporter=json', suite['path']],
                                     cwd=source, env=env)
        basename = Path(suite['path']).name
        observation = observe_green(result.stdout, result.returncode, expected_names=suite['names'],
                                    fixture_basename=basename, stderr=result.stderr)
        if reason:
            observation['captureFailure'] = reason
        print(json.dumps(observation), flush=True)
        print(json.dumps(phase_observation(result.stdout, suite['names'])), flush=True)
        evidence = dispatch_observation(result.stdout, suite['names'])
        print(json.dumps(evidence), flush=True)
        p.require(reason is None, 'Bounded Flutter capture did not complete.')
        STAGE = 'expected-red-verification'
        report = exact_red(result.stdout, result.returncode, names=suite['names'], basename=basename,
                           causal_ordinal=suite['causalOrdinal'], stderr=result.stderr)
        STAGE = 'native-order-evidence'
        p.require(not evidence.get('reason') and evidence['reportCount'] == 3
                  and evidence['invalidReports'] == 0 and len(evidence['records']) == 3,
                  'Three finite case-scoped dispatch records are required.')
    finally:
        old_stage = STAGE
        STAGE = 'final-fingerprint'
        p.require(p.source_fingerprint(source, sha, env) == before, 'Frozen source bytes changed.')
        STAGE = old_stage
    print(json.dumps(report), flush=True)


def main():
    global STAGE
    STAGE = 'entry'
    try:
        p = request.p
        p.require(len(sys.argv) == 3 and sys.argv[1] == 'source'
                  and sys.argv[2] in ('prepare', 'fetch', 'red', 'cleanup'),
                  'Only fixed ingress proof stages are allowed.')
        stage = sys.argv[2]
        STAGE = stage
        p.checked_sha(SOURCE_SHA)
        p.require(SOURCE_SHA != BASELINE_SHA and SOURCE_REF.startswith('refs/heads/test/'),
                  'Reviewed test-only descendant required.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST, SOURCE_REF=SOURCE_REF,
                            SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA), patch.object(p, 'quiet', bounded_quiet):
            request.context()
            if stage == 'red':
                prove()
            else:
                request.run(stage)
        return 0
    except GreenVerificationError as exc:
        print(json.dumps(exc.report), flush=True)
    except Exception as exc:
        category = type(exc).__name__
        known = ('GateError', 'TimeoutExpired', 'ValueError', 'TypeError', 'KeyError',
                 'JSONDecodeError', 'OSError', 'FileNotFoundError', 'PermissionError')
        print(json.dumps(dict(stage='follow-ingress-proof-failure', failedStage=STAGE,
                              category=category if category in known else 'other')), flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
