"""One fixed real-service Follow seek-latency causal proof; no repair claim."""
import json
import re
import subprocess
import sys
from unittest.mock import patch
import current_source_check as request
import handoff_repair_check as regression

PARENT = '842a6a809ee431eb6d0a83eed31061d96a674d11'
MESSAGE = 'test: diagnose held seek causal proof 20261022'
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
               baseline_sha=BASELINE_SHA, server_sha=SERVER_SHA, mode='follow-seek-latency-proof', attempt=16)


EXPECTED_TESTS = 13
PROOF_STAGE = 'entry'


def finite_report(raw, stderr, returncode):
    events=[]; invalid=0
    for line in raw.splitlines():
        try:
            event=json.loads(line)
            if type(event) is dict: events.append(event)
            else: invalid+=1
        except (ValueError,TypeError): invalid+=1
    cap=lambda value:min(value,10000)
    kinds=('start','suite','allSuites','group','testStart','testDone','error','done','print')
    errors=[]
    for event in events:
        if event.get('type')!='error': continue
        body=event.get('error',''); stack=event.get('stackTrace','')
        if type(body) is not str:body=''
        if type(stack) is not str:stack=''
        category=next((name for name in ('TimeoutException','StateError','RangeError','LateInitializationError','NoSuchMethodError','MissingPluginException','TestFailure') if name in body),'other')
        lines=sorted(set(int(x) for x in re.findall(r'emo_follow_sync_controller_test\.dart:(\d+)',body+'\n'+stack)))[:20]
        errors.append({'testID':event.get('testID') if type(event.get('testID')) is int and 0<=event['testID']<10000 else None,'isFailure':event.get('isFailure') is True,'exactMarker':body==ASSERTION_MARKER,
                       'containsMarker':ASSERTION_MARKER in body,'category':category,
                       'fixtureLines':[min(x,100000) for x in lines]})
    locations=sorted(set((min(int(a),100000),min(int(b),10000)) for a,b in re.findall(r'emo_follow_sync_controller_test\.dart:(\d+):(\d+): Error:',raw+'\n'+stderr)))[:20]
    return {'stage':'follow-seek-proof-observation','returncode':max(-1000,min(returncode,1000)),
            'targetStarts':cap(sum(e.get('type')=='testStart' and type(e.get('test')) is dict and e['test'].get('name')==TEST_NAME for e in events)),
            'hiddenCompleted':cap(sum(e.get('type')=='testDone' and e.get('hidden') is True for e in events)),
            'skippedCompleted':cap(sum(e.get('type')=='testDone' and e.get('skipped') is True for e in events)),
            'otherEventCount':cap(sum(e.get('type') not in kinds for e in events)),
            'terminalSuccessValues':[e.get('success') if type(e.get('success')) is bool else None for e in events if e.get('type')=='done'][:10],
            'nonJsonLines':cap(invalid),'events':{k:cap(sum(e.get('type')==k for e in events)) for k in kinds},
            'results':{k:cap(sum(e.get('type')=='testDone' and e.get('result')==k for e in events)) for k in ('success','failure','error')},
            'markerCount':cap(sum(type(e.get('error')) is str and ASSERTION_MARKER in e['error'] for e in events)),
            'errors':errors[:20],'compileLocations':locations,
            'causalSampleReports':cap(sum(e.get('type')=='print' and type(e.get('message')) is str and e['message'].startswith('FOLLOW_SEEK_LATENCY_SAMPLES ') for e in events))}



def exact_red(raw):
    global PROOF_STAGE
    PROOF_STAGE = 'json-events'
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
    PROOF_STAGE = 'target-and-terminal'
    targets = [tid for tid,name in tests.items() if name == TEST_NAME]
    p.require(len(targets)==1 and tests.keys()==results.keys() and len(done)==1
              and events[-1] is done[0] and done[0].get('success') is False, message)
    PROOF_STAGE = 'exact-error'
    target=targets[0]
    p.require(len(errors)==1 and errors[0].get('testID')==target
              and errors[0].get('isFailure') is True
              and errors[0].get('error')==ASSERTION_MARKER, message)
    PROOF_STAGE = 'all-control-results'
    visible=0
    for tid,result in results.items():
        p.require(type(result.get('hidden')) is bool, message)
        if not result['hidden']: visible+=1
        p.require((tid==target and result['hidden'] is False and result.get('result')=='failure')
                  or (tid!=target and result.get('result')=='success'), message)
    PROOF_STAGE = 'test-count'
    p.require(visible==EXPECTED_TESTS, message)
    PROOF_STAGE = 'finite-synthetic-samples'
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
    global PROOF_STAGE
    PROOF_STAGE = 'context'
    p=request.p
    request.context()
    if stage=='fetch-baseline':
        p.fetch(); return
    p.require(stage=='red','Unknown causal proof stage.')
    source,_,sha,_=p.source_context(require_server=False)
    env=regression.native.native_env()
    PROOF_STAGE = 'initial-fingerprint'
    before=p.source_fingerprint(source,sha,env)
    try:
        PROOF_STAGE = 'codegen'
        original_quiet = p.quiet
        def observed_quiet(args, cwd=None, env=None):
            global PROOF_STAGE
            known={('flutter','pub','get'):'dependencies',
                   ('dart','run','scripts/check_navigation_consistency.dart'):'navigation-check',
                   ('dart','run','build_runner','build','--delete-conflicting-outputs'):'codegen'}
            PROOF_STAGE=known.get(tuple(args),'setup-command')
            try: return original_quiet(args,cwd,env)
            except p.GateError as exc:
                match=re.fullmatch(r'Tool failed \(exit (-?[0-9]+); (command-resolution|missing-launcher-path|symlink-support|dependency-resolution|navigation-violation|native-assets|unclassified)\); detailed output suppressed for source privacy\.',str(exc))
                if match: print(json.dumps({'stage':PROOF_STAGE,'exitCode':max(-1000,min(int(match.group(1)),1000)),'reason':match.group(2)}),flush=True)
                raise
        with patch.object(p,'quiet',observed_quiet): p.codegen(source,env)
        PROOF_STAGE = 'flutter-test'
        result=subprocess.run(['flutter','test','--no-pub','--reporter=json',TEST_PATH],
                              cwd=source,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              text=True,timeout=600)
        print(json.dumps(finite_report(result.stdout,result.stderr,result.returncode)),flush=True)
        PROOF_STAGE = 'test-return-code'
        p.require(result.returncode!=0 and len(result.stdout)<16777216,'Expected bounded causal regression failure.')
        summary=exact_red(result.stdout)
    finally:
        if p.source_fingerprint(source,sha,env)!=before:
            PROOF_STAGE='final-fingerprint'
            raise p.GateError('Frozen source bytes changed.')
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
    except Exception as exc:
        print(json.dumps({'stage':'follow-seek-proof-failure','failedStage':PROOF_STAGE,
                          'category':type(exc).__name__ if type(exc).__name__ in ('GateError','TimeoutExpired','ValueError','KeyError','TypeError','JSONDecodeError') else 'other'}),flush=True)
        print('ERROR: Startup validation failed; private details suppressed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
