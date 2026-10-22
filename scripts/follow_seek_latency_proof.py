"""One fixed real-service Follow seek-latency causal proof; no repair claim."""
import json
import re
import subprocess
import sys
from unittest.mock import patch
import current_source_check as request
import handoff_repair_check as regression

PARENT = 'c759ec74bf2b6a64b7b9f74cd23d818584345f2f'
MESSAGE = 'test: prove follow seek latency feedback 20261022'
WORKFLOW = 'follow-seek-latency-proof.yml'
REQUEST_PATH = 'requests/follow-seek-latency-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-seek-latency-20261022'
SOURCE_SHA = '69c80772e4321a42e9f73f8699a60c5ee5ffa1ff'
BASELINE_SHA = SOURCE_SHA
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
TEST_PATH = 'test/services/emo_follow_sync_controller_test.dart'
TEST_NAME = 'Follow native seek hold must not sustain 1.5x soft-seek loop'
ASSERTION_MARKER = 'FOLLOW_SEEK_HOLD_MUST_NOT_REPEAT_UNSETTLED_SOFT_SEEKS'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA, mode='follow-seek-latency-proof', attempt=15)


EXPECTED_TESTS = 13


def exact_red(raw):
    p = request.p
    message = 'Exact causal failure and all twelve controls required; details suppressed.'
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    p.require(events and all(type(e) is dict for e in events), message)
    tests, results, errors, done = {}, {}, [], []
    for event in events:
        kind = event.get('type')
        if kind == 'testStart':
            test = event.get('test', {})
            p.require(type(test) is dict and type(test.get('id')) is int and test['id'] not in tests, message)
            tests[test['id']] = test.get('name')
        elif kind == 'testDone':
            tid = event.get('testID')
            p.require(tid in tests and tid not in results and event.get('skipped') is False, message)
            results[tid] = event
        elif kind == 'error': errors.append(event)
        elif kind == 'done': done.append(event)
        elif kind not in ('start','suite','allSuites','group','print'):
            raise p.GateError(message)
    targets = [tid for tid,name in tests.items() if name == TEST_NAME]
    p.require(len(targets)==1 and tests.keys()==results.keys() and len(done)==1
              and events[-1] is done[0] and done[0].get('success') is False, message)
    target=targets[0]
    p.require(len(errors)==1 and errors[0].get('testID')==target
              and errors[0].get('isFailure') is True
              and errors[0].get('error')==ASSERTION_MARKER, message)
    visible=0
    for tid,result in results.items():
        p.require(type(result.get('hidden')) is bool, message)
        if not result['hidden']: visible+=1
        p.require((tid==target and result['hidden'] is False and result.get('result')=='failure')
                  or (tid!=target and result.get('result')=='success'), message)
    p.require(visible==EXPECTED_TESTS, message)
    prefix = 'FOLLOW_SEEK_LATENCY_SAMPLES '
    reports = [e.get('message') for e in events if e.get('type') == 'print'
               and e.get('testID') == target and type(e.get('message')) is str
               and e['message'].startswith(prefix)]
    p.require(len(reports) == 1 and len(reports[0]) < 8192, message)
    samples = json.loads(reports[0][len(prefix):])
    keys = {'cycle','rate','holdMs','decision','requestedPositionMs','serverNowMs',
            'residualMs','nativeResidualMs','realProjectionUpperMs','nativeAnchorAdopted'}
    p.require(type(samples) is list and len(samples) == 5, message)
    for index, sample in enumerate(samples):
        p.require(type(sample) is dict and type(sample.get('decision')) is str and len(sample['decision']) < 4096, message)
        match = re.match(r'^\[\[EMO_FOLLOW_SYNC\]\] action=(applyTrackOrQueue|applyStateOnly|softCorrectDrift|hardSeek|smoothCorrectDrift|ignoreProgressHeartbeat)(?:\s|$)', sample['decision'])
        p.require(match is not None, message)
        sample = dict(sample, decision=match.group(1))
        samples[index] = sample
        p.require(type(sample) is dict and set(sample) == keys and sample['cycle'] == index
                  and type(sample['cycle']) is int and type(sample['rate']) in (int,float)
                  and sample['rate'] == 1.5 and type(sample['nativeAnchorAdopted']) is bool
                  and sample['decision'] in ('applyTrackOrQueue','applyStateOnly','softCorrectDrift',
                      'hardSeek','smoothCorrectDrift','ignoreProgressHeartbeat')
                  and all(type(sample[key]) is int and -1000000 <= sample[key] <= 1000000
                          for key in ('holdMs','requestedPositionMs','serverNowMs','residualMs',
                                      'nativeResidualMs','realProjectionUpperMs')), message)
    return {'tests':visible,'expectedFailures':1,'passedControls':visible-1,
            'unexpectedFailures':0,'syntheticSamples':samples}


def prove(stage):
    p=request.p
    request.context()
    if stage=='fetch-baseline':
        p.fetch(); return
    p.require(stage=='red','Unknown causal proof stage.')
    source,_,sha,_=p.source_context(require_server=False)
    env=regression.native.native_env()
    before=p.source_fingerprint(source,sha,env)
    try:
        p.codegen(source,env)
        result=subprocess.run(['flutter','test','--no-pub','--reporter=json',TEST_PATH],
                              cwd=source,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              text=True,timeout=600)
        p.require(result.returncode!=0 and len(result.stdout)<16777216,'Expected bounded causal regression failure.')
        summary=exact_red(result.stdout)
    finally:
        p.require(p.source_fingerprint(source,sha,env)==before,'Frozen source bytes changed.')
    print(json.dumps(dict(stage='follow-seek-latency-causal-proof',status='expected-failure-confirmed',**summary)))


def main():
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('source', 'regression'):
            raise request.p.GateError('Only fixed-source startup validation is allowed.')
        category, stage = sys.argv[1:]
        if category == 'source' and stage not in ('prepare', 'fetch', 'cleanup'):
            raise request.p.GateError('Native, package and publishing stages are forbidden.')
        with patch.multiple(request, PARENT=PARENT, MESSAGE=MESSAGE, WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH, REQUEST=REQUEST,
                            SOURCE_REF=SOURCE_REF, SOURCE_SHA=SOURCE_SHA, SERVER_SHA=SERVER_SHA):
            if category == 'regression':
                prove(stage)
                return 0
            with patch.object(sys, 'argv', [sys.argv[0], stage]):
                return request.main()
    except Exception:
        print('ERROR: Startup validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
