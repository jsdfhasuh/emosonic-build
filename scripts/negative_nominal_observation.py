"""Finite observation for one byte-pinned case; never changes a verdict."""
from pathlib import Path
from follow_seek_latency_observation import strict_json, MAX_BYTES, MAX_EVENTS

TEST_PATH = 'test/services/emo_follow_directional_boundary_test.dart'
FIXTURE_SHA256 = '16db235aa9a61faaf04b41368888ed979cddb92f2605e511a8307d9089b99a97'
PREFIX = 'FOLLOW_NEGATIVE_NOMINAL_DIAGNOSTIC '
PHASES = ('after_ack', 'after_first', 'after_second')

def integer(v, lo, hi):
    return type(v) is int and lo <= v <= hi

def number(v, lo, hi):
    return type(v) in (int, float) and lo <= v <= hi

def project(v):
    if type(v) is not dict or set(v) != {'schemaVersion','exactAckFloorObserved','ackBeforeUs','ackAfterUs','snapshots','rateWriteCount','rateWrites'}:
        raise ValueError('shape')
    if type(v['schemaVersion']) is not int or v['schemaVersion'] != 1 or v['exactAckFloorObserved'] is not False:
        raise ValueError('version')
    if not integer(v['ackBeforeUs'],0,60000000) or not integer(v['ackAfterUs'],v['ackBeforeUs'],60000000):
        raise ValueError('ack')
    if not integer(v['rateWriteCount'],0,1000) or type(v['rateWrites']) is not list or len(v['rateWrites']) != min(8,v['rateWriteCount']):
        raise ValueError('writes')
    for w in v['rateWrites']:
        if type(w) is not dict or set(w) != {'atMs','rate'} or not integer(w['atMs'],0,10000) or not number(w['rate'],0.5,2):
            raise ValueError('write')
    if type(v['snapshots']) is not list or len(v['snapshots']) != 3:
        raise ValueError('snapshots')
    for phase,s in zip(PHASES,v['snapshots']):
        if type(s) is not dict or set(s) != {'phase','nowMs','nativeResidualMs','runtimeDriftMs','currentRate','nativeRate','requestedRate','settledCount','activeTimerCount','rateWriteCount','anchorSequence','anchorPositionUs','anchorSampleOffsetUs','ageBeforeUs','ageAfterUs'} or s['phase'] != phase:
            raise ValueError('snapshot')
        if not integer(s['nowMs'],0,10000) or not number(s['nativeResidualMs'],-100000,100000) or not (s['runtimeDriftMs'] is None or integer(s['runtimeDriftMs'],-100000,100000)):
            raise ValueError('clock')
        if not all(number(s[k],0.5,2) for k in ('currentRate','nativeRate','requestedRate')) or not all(integer(s[k],0,1000) for k in ('settledCount','activeTimerCount','rateWriteCount')):
            raise ValueError('state')
        bounds={'anchorSequence':(0,1000000),'anchorPositionUs':(0,3600000000),'anchorSampleOffsetUs':(-60000000,60000000),'ageBeforeUs':(-60000000,60000000),'ageAfterUs':(-60000000,60000000)}
        if not (all(s[k] is None for k in bounds) or all(integer(s[k],*b) for k,b in bounds.items())):
            raise ValueError('anchor')
        if s['ageBeforeUs'] is not None and s['ageAfterUs'] < s['ageBeforeUs']:
            raise ValueError('age')
    if v['snapshots'][-1]['rateWriteCount'] != v['rateWriteCount']:
        raise ValueError('write count')
    return v


def observe_negative_nominal(raw, source, suites, phase):
    """Only inventory-verified callers use this; observation never decides pass/fail."""
    report = {'stage': 'negative-nominal-observation',
              'phase': phase if phase in ('focused', 'full') else 'unknown',
              'status': 'fixture-mismatch'}
    selected = [s for s in suites if type(s) is dict and s.get('path') == TEST_PATH]
    if not selected:
        return None
    if (len(selected) != 1 or selected[0].get('sha256') != FIXTURE_SHA256
            or type(selected[0].get('names')) is not list
            or len(selected[0]['names']) != 3
            or len(set(selected[0]['names'])) != 3):
        return report
    test_name = selected[0]['names'][2]
    if type(test_name) is not str:
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
               and type(t.get('suiteID')) is int and t['suiteID'] == sid and t.get('name') == test_name]
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
        samples = project(strict_json(text[len(PREFIX):]))
    except Exception:
        # Only finite failure labels survive; never assertion text or raw decisions.
        return dict(report, status='malformed-samples')
    return dict(report, status='observed', diagnostic=samples)
