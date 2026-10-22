"""Validate one bounded Flutter JSON stream against a caller-pinned inventory.

No execution, printing, source discovery, or artifact writing. Callers must supply
trusted literal test names and fixture basename, never derive them from the stream.
Subprocess capture limits/timeouts and source integrity are the caller's job.
"""
import json
import math
import re

MAX_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 100000
MAX_TESTS = 10000


class GreenVerificationError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__('Fixed Flutter green verification failed; private details suppressed.')


def verify_green(raw, returncode, *, expected_names, fixture_basename, stderr=''):
    """Return finite counts or raise GreenVerificationError with a finite report.

    Every visible test must exactly match the supplied unique inventory. Hidden
    lifecycle tests may have runner-generated names, but must also start/finish
    exactly once, pass, and not skip. No error event is tolerated, even if the
    reporter later labels its test successful. Unknown event types fail closed.
    """
    counts = {'visibleTests': 0, 'hiddenTests': 0, 'completedTests': 0}

    compile_locations = []

    def fail(reason, ordinal=None, line=None, category=None):
        report = dict(stage='fixed-flutter-green', status='failed', reason=reason, **counts)
        if type(returncode) is int:
            report['exitCode'] = max(-1000, min(returncode, 1000))
        if compile_locations:
            report.update(fixture=fixture_basename, compileLocations=compile_locations)
        if category is not None:
            report['errorCategory'] = category
        if ordinal is not None:
            report['testOrdinal'] = ordinal
        if line is not None:
            report.update(fixture=fixture_basename, line=line)
        raise GreenVerificationError(report)

    if (type(expected_names) not in (tuple, list) or not 1 <= len(expected_names) <= MAX_TESTS
            or any(type(n) is not str or not n or len(n) > 8192 for n in expected_names)
            or len(set(expected_names)) != len(expected_names)
            or type(fixture_basename) is not str
            or len(fixture_basename) > 128
            or re.fullmatch(r'[A-Za-z0-9_]+_test\.dart', fixture_basename) is None):
        fail('invalid-inventory')
    inventory = {name: ordinal for ordinal, name in enumerate(expected_names, 1)}
    if type(returncode) is not int:
        fail('invalid-return-code')
    if type(raw) is not str or type(stderr) is not str:
        fail('invalid-output')
    try:
        size = len(raw.encode('utf-8')) + len(stderr.encode('utf-8'))
    except UnicodeError:
        fail('invalid-output')
    if size > MAX_BYTES:
        fail('output-limit')

    location_pattern = (r'(?<![A-Za-z0-9_])' + re.escape(fixture_basename)
                        + r':([0-9]{1,6}):([0-9]{1,6}): Error:')
    compile_locations = [dict(line=line, column=column) for line, column in sorted({
        (int(m.group(1)), int(m.group(2)))
        for text in (raw, stderr) for m in re.finditer(location_pattern, text)
    })[:10]]

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('non-finite JSON')

    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('non-finite JSON')
        return number

    tests, results, visible_names = {}, set(), set()
    done = False
    event_count = 0
    for text in raw.splitlines():
        if not text.strip():
            continue
        event_count += 1
        if event_count > MAX_EVENTS:
            fail('event-limit')
        if done:
            fail('event-after-terminal')
        try:
            event = json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
        except (ValueError, RecursionError):
            fail('compiler-diagnostic' if compile_locations else 'malformed-json')
        if type(event) is not dict:
            fail('malformed-event')
        kind = event.get('type')
        if kind == 'testStart':
            test = event.get('test')
            if (type(test) is not dict or type(test.get('id')) is not int
                    or not 0 <= test['id'] < MAX_EVENTS or test['id'] in tests
                    or type(test.get('name')) is not str or not test['name']
                    or len(test['name']) > 8192 or len(tests) >= MAX_TESTS):
                fail('invalid-test-start')
            tests[test['id']] = test['name']
        elif kind == 'testDone':
            tid = event.get('testID')
            if type(tid) is not int or tid not in tests or tid in results:
                fail('invalid-test-completion')
            ordinal = inventory.get(tests[tid])
            if type(event.get('hidden')) is not bool or type(event.get('skipped')) is not bool:
                fail('invalid-test-flags', ordinal)
            if event['skipped']:
                fail('skipped-test', ordinal)
            if event.get('result') != 'success':
                fail('test-not-successful', ordinal)
            if event['hidden']:
                if ordinal is not None:
                    fail('expected-test-hidden', ordinal)
                counts['hiddenTests'] += 1
            else:
                if ordinal is None:
                    fail('unexpected-visible-test')
                if tests[tid] in visible_names:
                    fail('duplicate-visible-test', ordinal)
                visible_names.add(tests[tid])
                counts['visibleTests'] += 1
            results.add(tid)
            counts['completedTests'] += 1
        elif kind == 'error':
            tid = event.get('testID')
            ordinal = inventory.get(tests.get(tid)) if type(tid) is int else None
            stack = event.get('stackTrace')
            line = None
            if type(stack) is str:
                match = re.search(r'(?<![A-Za-z0-9_])' + re.escape(fixture_basename)
                                  + r':([0-9]{1,6})(?=[:\s]|$)', stack)
                if match:
                    line = int(match.group(1))
            body = event.get('error')
            categories = ('TimeoutException', 'StateError', 'RangeError',
                          'LateInitializationError', 'NoSuchMethodError',
                          'MissingPluginException', 'TestFailure', 'AssertionError')
            category = next((name for name in categories
                             if type(body) is str and re.search(
                                 r'(?<![A-Za-z0-9_])' + name + r'(?![A-Za-z0-9_])', body)), 'other')
            fail('reporter-error', ordinal, line, category)
        elif kind == 'done':
            if event.get('success') is not True:
                fail('terminal-not-successful')
            done = True
        elif kind not in ('start', 'suite', 'allSuites', 'group', 'print'):
            fail('unknown-event')
    if not done:
        fail('compiler-diagnostic' if compile_locations else 'missing-terminal')
    if set(tests) != results:
        fail('incomplete-tests')
    if visible_names != set(inventory):
        fail('inventory-mismatch')
    if returncode != 0:
        fail('process-failed')
    return dict(stage='fixed-flutter-green', status='passed', **counts)


def observe_green(raw, returncode, *, expected_names, fixture_basename, stderr='',
                  diagnostic_max_bytes=MAX_BYTES, diagnostic_max_events=MAX_EVENTS):
    """Finite whole-stream diagnostics only. Never substitutes for verify_green."""
    report = {'stage': 'fixed-flutter-observation', 'events': 0, 'malformedEvents': 0,
              'completedTests': 0, 'visibleTests': 0, 'hiddenTests': 0,
              'skippedTests': 0, 'results': {'success': 0, 'failure': 0, 'error': 0},
              'terminalCount': 0, 'terminalSuccess': None, 'errorCount': 0, 'errors': []}
    if (type(diagnostic_max_bytes) is not int or not 1 <= diagnostic_max_bytes <= 128 * 1024 * 1024
            or type(diagnostic_max_events) is not int or not 1 <= diagnostic_max_events <= 1000000):
        report['reason'] = 'invalid-diagnostic-budget'
        return report
    if type(returncode) is int:
        report['exitCode'] = max(-1000, min(returncode, 1000))
    if (type(expected_names) not in (tuple, list) or not 1 <= len(expected_names) <= MAX_TESTS
            or any(type(n) is not str or not n or len(n) > 8192 for n in expected_names)
            or len(set(expected_names)) != len(expected_names)
            or type(fixture_basename) is not str or len(fixture_basename) > 128
            or re.fullmatch(r'[A-Za-z0-9_]+_test\.dart', fixture_basename) is None):
        report['reason'] = 'invalid-inventory'
        return report
    if type(raw) is not str or type(stderr) is not str:
        report['reason'] = 'invalid-output'
        return report
    try:
        if len(raw.encode('utf-8')) + len(stderr.encode('utf-8')) > diagnostic_max_bytes:
            report['reason'] = 'output-limit'
            return report
    except UnicodeError:
        report['reason'] = 'invalid-output'
        return report

    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError('duplicate key')
            obj[key] = value
        return obj

    def constant(_):
        raise ValueError('non-finite JSON')

    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('non-finite JSON')
        return number

    inventory = {name: i for i, name in enumerate(expected_names, 1)}
    starts, ambiguous, errors = {}, set(), []
    completions = {}
    terminal = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if report['events'] >= diagnostic_max_events:
            report['reason'] = 'event-limit'
            break
        report['events'] += 1
        try:
            event = json.loads(line, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
            if type(event) is not dict:
                raise ValueError('not an object')
        except (ValueError, RecursionError):
            report['malformedEvents'] += 1
            continue
        kind = event.get('type')
        if kind == 'testStart':
            test = event.get('test')
            if type(test) is dict and type(test.get('id')) is int and 0 <= test['id'] < MAX_EVENTS:
                tid = test['id']
                if tid in starts:
                    ambiguous.add(tid)
                name = test.get('name')
                starts[tid] = inventory.get(name) if type(name) is str else None
        elif kind == 'testDone':
            if type(event.get('testID')) is int:
                completions.setdefault(event['testID'], []).append(event)
            report['completedTests'] += 1
            if event.get('hidden') is True:
                report['hiddenTests'] += 1
            elif event.get('hidden') is False:
                report['visibleTests'] += 1
            if event.get('skipped') is True:
                report['skippedTests'] += 1
            result = event.get('result')
            if type(result) is str and result in report['results']:
                report['results'][result] += 1
        elif kind == 'done':
            report['terminalCount'] += 1
            terminal.append(event.get('success') if type(event.get('success')) is bool else None)
        elif kind == 'error':
            report['errorCount'] += 1
            if len(errors) < 20:
                errors.append(event)
    if len(terminal) == 1:
        report['terminalSuccess'] = terminal[0]
    categories = ('TimeoutException', 'StateError', 'RangeError', 'LateInitializationError',
                  'NoSuchMethodError', 'MissingPluginException', 'TestFailure', 'AssertionError',
                  'FlutterError', 'ProcessException', 'SocketException', 'FileSystemException',
                  'DatabaseException', 'SqliteException', 'PlatformException', 'FormatException')
    location = (r'(?<![A-Za-z0-9_])' + re.escape(fixture_basename)
                + r'(?::|[ \t]+)([0-9]{1,6}):([0-9]{1,6})(?![0-9])')
    scalar = r'(true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)'
    for event in errors:
        error = {}
        tid = event.get('testID')
        if type(tid) is int and tid not in ambiguous and starts.get(tid) is not None:
            error['testOrdinal'] = starts[tid]
        if type(event.get('isFailure')) is bool:
            error['isFailure'] = event['isFailure']
        completed = completions.get(tid, []) if type(tid) is int else []
        if len(completed) == 1:
            if type(completed[0].get('hidden')) is bool:
                error['hidden'] = completed[0]['hidden']
            if completed[0].get('result') in ('success', 'failure', 'error'):
                error['result'] = completed[0]['result']
        body = event.get('error') if type(event.get('error')) is str else ''
        stack = event.get('stackTrace') if type(event.get('stackTrace')) is str else ''
        error['category'] = next((name for name in categories if re.search(
            r'(?<![A-Za-z0-9_])' + name + r'(?![A-Za-z0-9_])', body)),
            'assertion' if event.get('isFailure') is True else 'other')
        if error['category'] == 'other':
            for literal, reason in (('A Timer is still pending', 'pending-timer'),
                                    ('Shell subprocess crashed', 'shell-crash'),
                                    ('Test timed out after', 'test-timeout'),
                                    ('Failed to load ', 'test-load-failed')):
                if literal in body:
                    error['category'] = reason
                    break
        locations = sorted({(int(m.group(1)), int(m.group(2)))
                            for m in re.finditer(location, body + '\n' + stack)})[:5]
        if locations:
            error.update(fixture=fixture_basename,
                         locations=[dict(line=a, column=b) for a, b in locations])
        for label in ('Expected', 'Actual'):
            values = []
            for text in body.splitlines():
                match = re.fullmatch(r'\s*' + label + r':\s*(?:' + scalar + r'|<' + scalar + r'>)\s*', text)
                if match:
                    token = match.group(1) or match.group(2)
                    try:
                        value = json.loads(token)
                    except ValueError:
                        continue
                    if value is None or type(value) is bool or (type(value) in (int, float)
                            and abs(value) <= 1000000 and math.isfinite(value)):
                        values.append(value)
            if len(values) == 1:
                error[label.lower()] = values[0]
        report['errors'].append(error)
    compile_pattern = (r'(?<![A-Za-z0-9_])' + re.escape(fixture_basename)
                       + r':([0-9]{1,6}):([0-9]{1,6}): Error:')
    locations = sorted({(int(m.group(1)), int(m.group(2)))
                        for text in (raw, stderr) for m in re.finditer(compile_pattern, text)})[:10]
    if locations:
        report.update(fixture=fixture_basename,
                      compileLocations=[dict(line=a, column=b) for a, b in locations])
    return report
