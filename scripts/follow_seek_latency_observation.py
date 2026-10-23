"""Read-only five-sample projection for one byte-pinned original fixture/case."""
import json
from pathlib import Path

from follow_seek_latency_proof import TEST_PATH, TEST_NAME, project_synthetic_samples

FIXTURE_SHA256 = '49fa9ab784dfbf39ad199855813466e4fe084a4b66df84b0adfc79584ef98e5a'
PREFIX = 'FOLLOW_SEEK_LATENCY_SAMPLES '
MAX_BYTES = 128 * 1024 * 1024
MAX_EVENTS = 1000000


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def floating(value):
        number = float(value)
        if not (-1.7976931348623157e308 <= number <= 1.7976931348623157e308):
            raise ValueError('Nonfinite JSON number')
        return number
    def constant(_):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=floating, parse_constant=constant)


def observe_samples(raw, source, suites, phase):
    """Only inventory-verified callers use this; observation never decides pass/fail."""
    report = {'stage': 'follow-seek-samples-observation',
              'phase': phase if phase in ('focused', 'full') else 'unknown',
              'status': 'fixture-mismatch'}
    selected = [s for s in suites if type(s) is dict and s.get('path') == TEST_PATH]
    if not selected:
        return None
    if (len(selected) != 1 or selected[0].get('sha256') != FIXTURE_SHA256
            or type(selected[0].get('names')) is not list
            or len(selected[0]['names']) != 13
            or selected[0]['names'].count(TEST_NAME) != 1):
        return report
    if type(raw) is not str:
        return dict(report, status='malformed-events')
    if len(raw.encode('utf-8')) > MAX_BYTES:
        return dict(report, status='output-limit')
    events = []
    try:
        for line in raw.splitlines():
            if not line.strip():
                continue
            if len(events) >= MAX_EVENTS:
                return dict(report, status='event-limit')
            event = strict_json(line)
            if type(event) is not dict:
                raise ValueError('Invalid event')
            events.append(event)
    except (ValueError, TypeError, RecursionError):
        return dict(report, status='malformed-events')
    suite_events = [e.get('suite') for e in events if e.get('type') == 'suite']
    paths = (TEST_PATH, str(Path(source) / TEST_PATH))
    matched = [s for s in suite_events if type(s) is dict and s.get('path') in paths]
    if len(matched) != 1 or type(matched[0].get('id')) is not int:
        return dict(report, status='ambiguous-suite' if matched else 'missing-suite')
    sid = matched[0]['id']
    if sum(type(s) is dict and s.get('id') == sid for s in suite_events) != 1:
        return dict(report, status='ambiguous-suite')
    starts = [(i, e.get('test')) for i, e in enumerate(events) if e.get('type') == 'testStart']
    targets = [(i, t) for i, t in starts if type(t) is dict
               and type(t.get('suiteID')) is int and t['suiteID'] == sid and t.get('name') == TEST_NAME]
    if len(targets) != 1 or type(targets[0][1].get('id')) is not int:
        return dict(report, status='ambiguous-target' if targets else 'missing-target')
    start, target = targets[0]
    tid = target['id']
    if sum(type(t) is dict and t.get('id') == tid for _, t in starts) != 1:
        return dict(report, status='ambiguous-target')
    all_reports = [(i, e) for i, e in enumerate(events) if e.get('type') == 'print'
                   and type(e.get('message')) is str and e['message'].startswith(PREFIX)]
    reports = [(i, e) for i, e in all_reports if type(e.get('testID')) is int and e['testID'] == tid]
    if not reports:
        return dict(report, status='wrong-test-id' if all_reports else 'missing-report')
    if len(reports) != 1 or reports[0][0] <= start:
        return dict(report, status='malformed-samples')
    text = reports[0][1]['message']
    try:
        if len(text) >= 8192:
            return dict(report, status='malformed-samples')
        strict_json(text[len(PREFIX):])
        samples = project_synthetic_samples([text])
    except Exception:
        # Only finite failure labels survive; never assertion text or raw decisions.
        return dict(report, status='malformed-samples')
    return dict(report, status='observed', samples=samples)
