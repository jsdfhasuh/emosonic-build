"""One pinned bounded Follow recovery validation; no packages or publication."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch
import current_source_check as request
import handoff_repair_check as regression
from fixed_flutter_green import verify_green, observe_green, GreenVerificationError

PARENT = '496885572b30447b5503d446208513a5a573e171'
MESSAGE = 'test: diagnose complete recovery source validation 20261022'
WORKFLOW = 'follow-recovery-check.yml'
REQUEST_PATH = 'requests/follow-recovery-check-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-recovery-sync-fixture-20261022'
SOURCE_SHA = '15bdc56b8a93db62bba2b5549073e1e09a8a88ff'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
INVENTORY_PATH = 'tool/follow_recovery/test_inventory.json'
INVENTORY_SHA256 = '33b9ae0c51b6c60913a88367f3fa5fc5d8e2a7f1c46cc07dced3c0e0f85296c4'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               server_sha=SERVER_SHA, mode='bounded-follow-recovery-validation', attempt=24)
STAGE = 'entry'


def owned_file(source, relative):
    p=request.p
    p.require(type(relative) is str and relative and not Path(relative).is_absolute()
              and all(part not in ('', '.', '..') for part in relative.split('/')),
              'Private source path invalid.')
    path=source
    for part in relative.split('/'):
        path=path/part
        p.require(not path.is_symlink(), 'Private source symlink forbidden.')
    p.require(path.is_file() and source in path.resolve().parents,
              'Private source path invalid.')
    return path


def inventory(source):
    p=request.p
    path=owned_file(source,INVENTORY_PATH)
    raw=path.read_bytes()
    p.require(hashlib.sha256(raw).hexdigest()==INVENTORY_SHA256, 'Private inventory changed.')
    value=json.loads(raw)
    p.require(type(value) is dict and set(value)=={'suites'} and type(value['suites']) is list
              and len(value['suites'])==3, 'Private suite inventory invalid.')
    seen=set()
    for suite in value['suites']:
        p.require(type(suite) is dict and set(suite)=={'path','sha256','names'}, 'Private suite schema invalid.')
        name=suite['path']
        p.require(type(name) is str and re.fullmatch(r'test/services/[a-z0-9_]+_test\.dart',name)
                  and name not in seen, 'Private fixture path invalid.')
        seen.add(name)
        target=owned_file(source,name)
        p.require(hashlib.sha256(target.read_bytes()).hexdigest()==suite['sha256'], 'Frozen fixture changed.')
        p.require(type(suite['names']) is list and 1<=len(suite['names'])<=1000
                  and all(type(n) is str and 0<len(n)<=8192 for n in suite['names'])
                  and len(set(suite['names']))==len(suite['names']), 'Private visible test inventory invalid.')
    return value['suites']


def focused():
    global STAGE
    p=request.p
    request.context()
    source,_,sha,_=p.source_context(require_server=False)
    env=regression.native.native_env()
    STAGE='initial-fingerprint'
    before=p.source_fingerprint(source,sha,env)
    try:
        STAGE='inventory'
        suites=inventory(source)
        original=p.quiet
        def observed(args,cwd=None,env=None):
            global STAGE
            STAGE={('flutter','pub','get'):'dependencies',
                   ('dart','run','scripts/check_navigation_consistency.dart'):'navigation-check',
                   ('dart','run','build_runner','build','--delete-conflicting-outputs'):'codegen'}.get(tuple(args),'setup-command')
            try: return original(args,cwd,env)
            except p.GateError as exc:
                match=re.fullmatch(r'Tool failed \(exit (-?[0-9]+); (command-resolution|missing-launcher-path|symlink-support|dependency-resolution|navigation-violation|native-assets|unclassified)\); detailed output suppressed for source privacy\.',str(exc))
                if match: print(json.dumps({'stage':STAGE,'exitCode':max(-1000,min(int(match.group(1)),1000)),'reason':match.group(2)}),flush=True)
                raise
        with patch.object(p,'quiet',observed): p.codegen(source,env)
        failed=False
        for ordinal,suite in enumerate(suites,1):
            STAGE='focused-test'
            try:
                result=subprocess.run(['flutter','test','--no-pub','--reporter=json',suite['path']],
                                      cwd=source,env=env,capture_output=True,text=True,timeout=600)
            except subprocess.TimeoutExpired:
                failed=True
                print(json.dumps({'stage':'focused-test','suiteOrdinal':ordinal,
                                  'status':'failed','reason':'timeout'}),flush=True)
                continue
            STAGE='focused-observation'
            observation=observe_green(result.stdout,result.returncode,expected_names=suite['names'],
                                      fixture_basename=Path(suite['path']).name,stderr=result.stderr)
            print(json.dumps(dict(observation,suiteOrdinal=ordinal)),flush=True)
            STAGE='focused-verification'
            try:
                report=verify_green(result.stdout,result.returncode,expected_names=suite['names'],
                                    fixture_basename=Path(suite['path']).name,stderr=result.stderr)
            except GreenVerificationError as exc:
                print(json.dumps(dict(exc.report,suiteOrdinal=ordinal)),flush=True)
                failed=True
                continue
            print(json.dumps(dict(report,suiteOrdinal=ordinal)),flush=True)
        STAGE='focused-verification'
        p.require(not failed,'Every frozen focused suite must pass; private details suppressed.')
    finally:
        if p.source_fingerprint(source,sha,env)!=before:
            STAGE='final-fingerprint'
            raise p.GateError('Frozen source bytes changed.')


ANALYZE_COMMAND=('flutter','analyze','--no-pub','--fatal-infos','--fatal-warnings')
FULL_TEST_COMMAND=('flutter','test','--no-pub','--reporter=json')
ANALYZER_CODES=frozenset(('curly_braces_in_flow_control_structures','unused_import','unused_local_variable','unused_field','unused_element',
    'dead_code','unnecessary_import','unnecessary_null_comparison','unnecessary_non_null_assertion',
    'unnecessary_cast','unnecessary_await_in_return','invalid_assignment','argument_type_not_assignable',
    'undefined_identifier','undefined_method','undefined_getter','undefined_named_parameter',
    'missing_required_argument','not_enough_positional_arguments','extra_positional_arguments',
    'return_of_invalid_type','body_might_complete_normally','non_bool_condition','await_only_futures',
    'prefer_const_constructors','prefer_const_declarations','avoid_print','deprecated_member_use',
    'deprecated_member_use_from_same_package','invalid_use_of_visible_for_testing_member',
    'invalid_use_of_protected_member','unused_result','discarded_futures','unawaited_futures',
    'unnecessary_type_check','unused_catch_clause','avoid_void_async','cancel_subscriptions'))


def analyzer_observation(raw, stderr, paths, source, returncode):
    report={'stage':'full-analysis-observation','exitCode':max(-1000,min(returncode,1000)),
            'severityCounts':{'error':0,'warning':0,'info':0},'unrecognizedLines':0,'findings':[]}
    ordinals={name:i for i,name in enumerate(sorted(paths),1)}
    if len(raw.encode('utf-8'))+len(stderr.encode('utf-8'))>16777216:
        return dict(report,reason='output-limit')
    for text in (raw,stderr):
        for line in text.splitlines():
            if not line.strip():continue
            parts=line.strip().split(' • ')
            if len(parts)!=4 or parts[0] not in report['severityCounts']:
                report['unrecognizedLines']=min(100000,report['unrecognizedLines']+1);continue
            severity,_,location,code=parts
            match=re.fullmatch(r'(.+):([0-9]{1,6}):([0-9]{1,6})',location)
            report['severityCounts'][severity]=min(100000,report['severityCounts'][severity]+1)
            finding={'severity':severity,'code':code if code in ANALYZER_CODES else 'other'}
            if match:
                name=match.group(1)
                prefix=str(source)+'/'
                if name.startswith(prefix):name=name[len(prefix):]
                if name in ordinals:
                    finding.update(fileOrdinal=ordinals[name],line=int(match.group(2)),column=int(match.group(3)))
            if len(report['findings'])<100:report['findings'].append(finding)
    return report


def full_test_observation(raw, stderr, paths, source, suites, returncode):
    # Reuse bounded whole-stream accounting; no source-derived names are exported.
    observation=observe_green(raw,returncode,expected_names=['__diagnostic_count_only__'],
                              fixture_basename='diagnostic_count_only_test.dart',stderr=stderr,
                              diagnostic_max_bytes=128 * 1024 * 1024, diagnostic_max_events=1000000)
    observation['stage']='full-tests-observation'
    observation['errors']=[]
    observation.pop('compileLocations',None);observation.pop('fixture',None)
    if observation.get('reason') in ('output-limit','invalid-output','event-limit'):return observation
    ordinals={name:i for i,name in enumerate(sorted(paths),1)}
    inventory={s['path']:s['names'] for s in suites}
    suite_paths={};tests={};ambiguous_suites=set();ambiguous_tests=set();errors=[]
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate')
            result[key]=value
        return result
    def floating(value):
        number=float(value)
        if not (-1.7976931348623157e308<=number<=1.7976931348623157e308):raise ValueError('nonfinite')
        return number
    for line in raw.splitlines():
        try:event=json.loads(line,object_pairs_hook=pairs,parse_float=floating,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        except (ValueError,RecursionError):continue
        if type(event) is not dict:continue
        if event.get('type')=='suite':
            suite=event.get('suite')
            if type(suite) is not dict or type(suite.get('id')) is not int:continue
            sid=suite['id']
            if sid in suite_paths:ambiguous_suites.add(sid)
            name=suite.get('path');prefix=str(source)+'/'
            if type(name) is str and name.startswith(prefix):name=name[len(prefix):]
            suite_paths[sid]=name if type(name) is str and name in ordinals else None
        elif event.get('type')=='testStart':
            test=event.get('test')
            if type(test) is not dict or type(test.get('id')) is not int:continue
            if test['id'] in tests:ambiguous_tests.add(test['id'])
            tests[test['id']]=test
        elif event.get('type')=='error' and len(errors)<20:errors.append(event)
    for error in errors:
        tid=error.get('testID');test=tests.get(tid,{}) if type(tid) is int and tid not in ambiguous_tests else {}
        sid=test.get('suiteID');name=suite_paths.get(sid) if type(sid) is int and sid not in ambiguous_suites else None
        if name is not None:
            names=inventory.get(name,['__diagnostic_count_only__'])
            start={'type':'testStart','test':{'id':0,'name':test.get('name')}}
            sample=dict(error,testID=0)
            details=observe_green(json.dumps(start)+'\n'+json.dumps(sample),returncode,
                                  expected_names=names,fixture_basename=Path(name).name)['errors'][0]
            details.pop('fixture',None)
            details['fileOrdinal']=ordinals[name]
            observation['errors'].append(details)
        else:
            details=observe_green(json.dumps(error),returncode,expected_names=['__diagnostic_count_only__'],
                                  fixture_basename='diagnostic_count_only_test.dart')['errors'][0]
            details.pop('testOrdinal',None);details.pop('fixture',None);details.pop('locations',None)
            observation['errors'].append(details)
    return observation


def validate_full():
    """Only add finite observations; the original pipeline owns all acceptance."""
    global STAGE
    p=request.p
    original_quiet=p.quiet;original_fingerprint=p.source_fingerprint
    tracked=None;suites=None;source_root=None
    def fingerprint(source,sha,env):
        nonlocal tracked,suites,source_root
        result=original_fingerprint(source,sha,env)
        if tracked is None:
            tracked=result[1];source_root=source;suites=inventory(source)
        return result
    def quiet(args,cwd=None,env=None):
        global STAGE
        if tuple(args) not in (ANALYZE_COMMAND,FULL_TEST_COMMAND):return original_quiet(args,cwd,env)
        p.require(tracked is not None and cwd==source_root,'Frozen diagnostic source unavailable.')
        STAGE='full-analysis' if tuple(args)==ANALYZE_COMMAND else 'full-tests'
        try:
            result=subprocess.run(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        except OSError:
            raise p.GateError('Required tool is unavailable.') from None
        raw=result.stdout.decode('utf-8',errors='replace');stderr=result.stderr.decode('utf-8',errors='replace')
        if tuple(args)==ANALYZE_COMMAND:
            report=analyzer_observation(raw,stderr,tracked,source_root,result.returncode)
        else:
            report=full_test_observation(raw,stderr,tracked,source_root,suites,result.returncode)
        print(json.dumps(report),flush=True)
        p.require(result.returncode==0,'Full validation command failed; private details suppressed.')
        return raw
    with patch.object(p,'quiet',quiet),patch.object(p,'source_fingerprint',fingerprint):
        return request.main()


def main():
    global STAGE
    try:
        request.p.require(len(sys.argv)==3,'Invalid recovery validation arguments.')
        category,stage=sys.argv[1:]
        request.p.require(category=='source' and stage in ('prepare','fetch','focused','validate_source','cleanup'),
                          'Packages, native execution and publishing forbidden.')
        with patch.multiple(request,PARENT=PARENT,MESSAGE=MESSAGE,WORKFLOW=WORKFLOW,
                            REQUEST_PATH=REQUEST_PATH,REQUEST=REQUEST,SOURCE_REF=SOURCE_REF,
                            SOURCE_SHA=SOURCE_SHA,SERVER_SHA=SERVER_SHA):
            STAGE=stage
            if stage=='focused': focused();return 0
            with patch.object(sys,'argv',[sys.argv[0],stage]):
                return validate_full() if stage=='validate_source' else request.main()
    except Exception as exc:
        known=('GateError','GreenVerificationError','TimeoutExpired','ValueError','TypeError','KeyError','JSONDecodeError')
        print(json.dumps({'stage':'follow-recovery-validation-failure','failedStage':STAGE,
                          'category':type(exc).__name__ if type(exc).__name__ in known else 'other'}),flush=True)
        return 1

if __name__=='__main__':sys.exit(main())
