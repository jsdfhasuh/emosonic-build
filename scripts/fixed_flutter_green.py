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
