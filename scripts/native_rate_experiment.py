"""One frozen sandboxed AVQueuePlayer experiment; no application/release changes."""
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from unittest.mock import patch
import current_source_check as request

PARENT='aeb111d803f6bb15813f3a76f50fc2a1dfe2f440'
MESSAGE='test: measure isolated native rate transitions 20261022'
WORKFLOW='native-rate-experiment.yml'
REQUEST_PATH='requests/native-rate-experiment-20261022.json'
SOURCE_REF='refs/heads/test/native-rate-transition-comparison-20261022'
SOURCE_SHA='7e040ebbfcc08ea16a05ee0a359036c7f3e4d4fe'
SERVER_SHA='5adc23da173c5f20188d79aafe8fcc1e656eb38a'
REQUEST=dict(request.REQUEST,source_ref=SOURCE_REF,source_sha=SOURCE_SHA,server_sha=SERVER_SHA,
             mode='isolated-native-rate-experiment',attempt=55)
DIRECTORY='tool/native_rate_transition'
INPUT_HASHES={'rate_transition.m':'633be7817d21a996015872d3f5ca2107144008a8587bf1784d7bcbb7e92260f7',
 'analyze.py':'371979ea36d6b079e9401edb118d79f313f457d2ed05c073d6c78bd049deeb4f',
 'report_schema.json':'d29441ac2c2eca3f76d1f5fb3dfed3303bceebeb475f2199e09e0ceab89b8785',
 'test_analyze.py':'7beec065cb3a637da154a2d53f8814d53f4962c0d3d85757cee4ebb84ff1972d'}
SCHEMA_SHA='d29441ac2c2eca3f76d1f5fb3dfed3303bceebeb475f2199e09e0ceab89b8785'
WORK='.native-rate-experiment'
MAX_BYTES=8*1024*1024
SUMMARY_BYTES=256*1024
ENTITLEMENTS={'com.apple.security.app-sandbox':True}
STAGES=('entry','inputs','reducer-tests','compile','sign','verify-signature','native','reduce','report','fingerprint','cleanup')
require=request.p.require


def integer(value,low,high):return type(value) is int and low<=value<=high


def bundle_identity():
    values=[os.environ.get(k,'') for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')]
    require(all(re.fullmatch(r'[1-9][0-9]{0,19}',v) for v in values),'Invalid experiment identity.')
    return 'com.emosonic.rateexperiment.run'+values[0]+'.attempt'+values[1]


def environment(work):
    env=request.p.build_env()
    for name in ('GITHUB_ENV','GITHUB_OUTPUT','GITHUB_PATH','GITHUB_STEP_SUMMARY'):
        env.pop(name,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(work),TMP=str(work),TEMP=str(work))
    return env


def schema():
    path=Path(__file__).with_name('native_rate_experiment_schema.json')
    require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==SCHEMA_SHA,
            'Experiment schema changed.')
    return json.loads(path.read_bytes())


def finite(value,shape,key=''):
    if shape=='boolean':require(type(value) is bool,'Invalid report boolean.');return
    if shape in ('finite_number','finite_number_or_null'):
        if value is None and shape=='finite_number_or_null':return
        require(type(value) in (int,float) and math.isfinite(value) and abs(value)<=1000000000,'Invalid report number.');return
    require(type(shape) is dict,'Invalid fixed schema.')
    if set(shape)=={'literal'}:require(type(value) is str and value==shape['literal'],'Invalid report literal.');return
    if set(shape)=={'enum'}:require(type(value) is str and value in shape['enum'],'Invalid report enum.');return
    if set(shape)=={'array'}:
        limit=16 if key=='trials' else 2
        require(type(value) is list and len(value)<=limit,'Invalid report array.')
        for row in value:finite(row,shape['array'])
        return
    require(type(value) is dict and set(value)==set(shape),'Invalid report fields.')
    for name,part in shape.items():finite(value[name],part,name)


def validate_report(value):
    contract=schema();finite(value,contract['reportShape'])
    require(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['hostLeadSupplied'] is False,
            'Invalid experiment claims.')
    require(type(value['trialCount']) is int and value['trialCount']==16 and len(value['trials'])==16,
            'All sixteen trials are required.')
    for i,row in enumerate(value['trials']):
        require(all(type(row[k]) is int for k in ('trialOrdinal','arm','round','order')) and
                (row['trialOrdinal'],row['arm'],row['round'],row['order'])==
                (i+1,contract['orders'][i//4][i%4],i//4+1,i%4+1),'Counterbalanced trials changed.')
        for name in ('sampleCount','validSampleCount','notReadySampleCount','notPlayingSampleCount',
                     'bufferEmptySampleCount','nativeErrorSampleCount','invalidIdentitySampleCount',
                     'forwardJumpCount','backwardJumpCount'):
            require(integer(row[name],0,181),'Invalid observation count.')
        require(row['validSampleCount']<=row['sampleCount'] and integer(row['transitionCount'],0,2)
                and integer(row['windowCount'],0,2) and row['windowCount']==len(row['windows'])
                and row['transitionCount']==len(row['windowObservations']),'Invalid window inventory.')
        require([w['ordinal'] for w in row['windowObservations']]==list(range(1,row['transitionCount']+1))
                and all(type(w['ordinal']) is int for w in row['windowObservations']),'Invalid observation order.')
        expected=[w['ordinal'] for w in row['windowObservations'] if w['status']=='observed']
        require([w['ordinal'] for w in row['windows']]==expected and all(type(w['ordinal']) is int for w in row['windows']),
                'Invalid retained windows.')
    require(integer(value['completedTrials'],0,16) and value['completedTrials']==sum(t['status']=='completed' for t in value['trials'])
            and integer(value['fullyMeasuredTrials'],0,16) and value['fullyMeasuredTrials']==sum(t['fullyMeasured'] for t in value['trials'])
            and value['allCleanupStopped']==all(t['cleanupStopped'] and t['cleanupItemRemoved'] for t in value['trials']),
            'Invalid experiment totals.')
    return value


def experiment_complete(value):
    # Deficits may be positive, zero or negative. There is no improvement test.
    return (value['sandboxIdentityVerified'] and value['ownedMediaRemoved'] and value['allCleanupStopped']
            and value['completedTrials']==16 and value['fullyMeasuredTrials']==16)


def compile_diagnostic(data):
    errors=[];count=0
    for line in data.decode('utf-8','replace').splitlines():
        match=re.search(r':([0-9]+):([0-9]+): (?:fatal )?error: (.*)$',line)
        if not match:continue
        count+=1
        if len(errors)>=12:continue
        location=[min(1000000,int(match[i])) for i in (1,2)];message=match[3]
        category='other'
        for token,label in (('undeclared identifier','unknown_identifier'),('property','missing_property'),
                            ('selector','missing_selector'),('incompatible','type_conversion'),('expected','syntax')):
            if token in message:category=label;break
        errors.append({'line':location[0],'column':location[1],'category':category})
    return {'errorCount':min(4096,count),'truncated':count>12,'errors':errors}


def command_failure(label,reason,code=None):
    phases=set(STAGES)|{'entitlements'}
    reasons={'command_failed','timeout','output_limit','spawn_failed','process_exit_unverified'}
    require(label in phases and reason in reasons,'Invalid finite command diagnostic.')
    value={'stage':'native-rate-experiment-command','status':'failed','phase':label,'reason':reason}
    if type(code) is int and -255<=code<=255:value['exitCode']=code
    print(json.dumps(value),flush=True)


def bounded(command,work,label,timeout,env):
    """Capture privately, bound bytes/time, and reap only our new process group."""
    out=work/(label+'.stdout');err=work/(label+'.stderr')
    require(not out.exists() and not out.is_symlink() and not err.exists() and not err.is_symlink(),'Existing private output refused.')
    reason=None
    with out.open('xb') as stdout,err.open('xb') as stderr:
        try:process=subprocess.Popen(command,cwd=work,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        except OSError:
            command_failure(label,'spawn_failed')
            raise request.p.GateError('Experiment command could not start.') from None
        (work/'active.json').write_text(json.dumps({'pid':process.pid,'label':label}))
        started=time.monotonic()
        while process.poll() is None:
            if time.monotonic()-started>timeout:reason='timeout';break
            if out.stat().st_size>MAX_BYTES or err.stat().st_size>MAX_BYTES:reason='output_limit';break
            time.sleep(.05)
        if reason:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        process.wait(timeout=10)
        try:os.killpg(process.pid,0)
        except ProcessLookupError:pass
        else:
            command_failure(label,'process_exit_unverified',process.returncode)
            raise request.p.GateError('Owned process group still active.')
        (work/'active.json').unlink()
    if reason is None and (out.stat().st_size>MAX_BYTES or err.stat().st_size>MAX_BYTES):reason='output_limit'
    if reason or process.returncode!=0:command_failure(label,reason or 'command_failed',process.returncode)
    require(reason is None,'Experiment command exceeded a finite bound.')
    return process.returncode,out,err


def inputs(source):
    root=source/DIRECTORY
    require(root.is_dir() and not root.is_symlink() and INPUT_HASHES,'Frozen experiment inputs missing.')
    actual={}
    for path in root.rglob('*'):
        require(not path.is_symlink(),'Experiment input link refused.')
        if path.is_file():actual[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    require(actual==INPUT_HASHES and actual.get('report_schema.json')==SCHEMA_SHA,'Experiment inputs changed.')
    return root


def container_path():
    return Path.home().resolve(strict=True)/'Library'/'Containers'/bundle_identity()


def work_path():return request.p.ROOT/WORK


def cleanup_owned():
    work=work_path()
    if not work.exists() and not work.is_symlink():return
    require(work.is_dir() and not work.is_symlink(),'Invalid experiment cleanup root.')
    state=work/'ownership.json'
    require(state.is_file() and not state.is_symlink(),'Experiment ownership missing.')
    owner=json.loads(state.read_text())
    require(type(owner) is dict and set(owner)=={'bundle','containerInitiallyAbsent','launchAttempted'} and
            owner['bundle']==bundle_identity() and owner['containerInitiallyAbsent'] is True and type(owner['launchAttempted']) is bool,
            'Experiment ownership mismatch.')
    active=work/'active.json'
    if active.exists():
        data=json.loads(active.read_text());require(type(data) is dict and set(data)=={'pid','label'} and integer(data['pid'],1,2147483647),'Invalid owned process record.')
        try:os.killpg(data['pid'],0)
        except ProcessLookupError:pass
        else:raise request.p.GateError('Owned process exit not verified; cleanup refused.')
    container=container_path()
    require(not container.is_symlink(),'Container cleanup link refused.')
    if container.exists() and owner['launchAttempted']:
        require(container.is_dir() and container.parent.resolve()==container.parent,'Container cleanup scope changed.')
        shutil.rmtree(container)
        require(not container.exists(),'Owned container remains.')
    shutil.rmtree(work)


REDUCER_CHILD="""import contextlib,json,sys,unittest
with open(sys.argv[2],'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
 sys.path.insert(0,sys.argv[1]);s=unittest.defaultTestLoader.discover(sys.argv[1],pattern='test_analyze.py');r=unittest.TextTestRunner(stream=sink).run(s)
ok=r.testsRun==15 and r.wasSuccessful() and not r.skipped and not r.expectedFailures
print(json.dumps({'tests':r.testsRun,'failed':len(r.failures)+len(r.errors),'skipped':len(r.skipped),'passed':ok}))
sys.exit(0 if ok else 1)
"""


def experiment():
    p=request.p;require(sys.platform=='darwin','Real macOS is required.')
    source=p.ROOT/'source';work=work_path();container=container_path()
    require(not work.exists() and not work.is_symlink(),'Existing experiment work refused.')
    require(not container.exists() and not container.is_symlink(),'Pre-existing container refused.')
    require(container.parent.is_dir() and container.parent.resolve()==container.parent,'Unexpected container parent.')
    work.mkdir();(work/'ownership.json').write_text(json.dumps({'bundle':bundle_identity(),'containerInitiallyAbsent':True,'launchAttempted':False}))
    env=environment(work);before=None;stage='inputs'
    try:
        require(p.source_version((source/'pubspec.yaml').read_text())==request.VERSION,'Source version mismatch.')
        before=p.source_fingerprint(source,SOURCE_SHA,env);root=inputs(source)
        stage='reducer-tests'
        code,out,_=bounded([sys.executable,'-B','-c',REDUCER_CHILD,str(root),str(work/'reducer-private.log')],work,stage,30,env)
        require(out.stat().st_size<=1024,'Invalid reducer test result.')
        result=json.loads(out.read_bytes())
        require(type(result) is dict and set(result)=={'tests','failed','skipped','passed'} and result=={'tests':15,'failed':0,'skipped':0,'passed':True}
                and all(type(result[k]) is int for k in ('tests','failed','skipped')) and type(result['passed']) is bool and code==0,'Reducer tests failed.')
        app=work/'RateExperiment.app';mac=app/'Contents'/'MacOS';mac.mkdir(parents=True)
        binary=mac/'RateExperiment'
        (app/'Contents'/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'RateExperiment','CFBundleIdentifier':bundle_identity(),
            'CFBundleName':'RateExperiment','CFBundlePackageType':'APPL','CFBundleVersion':'1','CFBundleShortVersionString':'1.0','LSUIElement':True}))
        ent=work/'entitlements.plist';ent.write_bytes(plistlib.dumps(ENTITLEMENTS))
        stage='compile'
        code,_,err=bounded(['xcrun','--sdk','macosx','clang','-fobjc-arc','-O0','-framework','Foundation','-framework','AVFoundation',
            '-framework','CoreMedia',str(root/'rate_transition.m'),'-o',str(binary)],work,stage,90,env)
        if code:print(json.dumps({'stage':'native-rate-experiment-compile','status':'failed','compile':compile_diagnostic(err.read_bytes())}),flush=True)
        require(code==0 and binary.is_file() and not binary.is_symlink() and binary.stat().st_size<=MAX_BYTES,'Native compilation failed.')
        stage='sign';code,_,_=bounded(['codesign','--force','--sign','-','--entitlements',str(ent),str(app)],work,stage,30,env);require(code==0,'Ad-hoc signing failed.')
        stage='verify-signature';code,_,_=bounded(['codesign','--verify','--deep','--strict',str(app)],work,stage,30,env);require(code==0,'Signature verification failed.')
        code,out,_=bounded(['codesign','--display','--entitlements',':-',str(app)],work,'entitlements',30,env)
        require(code==0 and plistlib.loads(out.read_bytes())==ENTITLEMENTS,'Sandbox-only entitlement verification failed.')
        stage='native'
        require(not container.exists() and not container.is_symlink(),'Container appeared before native launch; refusing ownership.')
        (work/'ownership.json').write_text(json.dumps({'bundle':bundle_identity(),'containerInitiallyAbsent':True,'launchAttempted':True}))
        code,out,_=bounded([str(binary)],work,stage,420,env)
        require(code==0,'Native experiment failed.')
        stage='reduce';summary=work/'summary.json'
        code,_,_=bounded([sys.executable,'-B',str(root/'analyze.py'),'--input',str(out),'--output',str(summary)],work,stage,30,env)
        require(code==0 and summary.is_file() and not summary.is_symlink() and summary.stat().st_size<=SUMMARY_BYTES,'Experiment reduction failed.')
        stage='report';value=validate_report(json.loads(summary.read_bytes()))
        passed=experiment_complete(value)
        print(json.dumps({'stage':'native-rate-experiment','status':'passed' if passed else 'failed','report':value},allow_nan=False),flush=True)
        require(passed,'Experiment was incomplete or cleanup was not verified.')
    except Exception:
        print(json.dumps({'stage':'native-rate-experiment-stage','status':'failed','phase':stage if stage in STAGES else 'entry'}),flush=True)
        raise
    finally:
        try:
            if before is not None:require(p.source_fingerprint(source,SOURCE_SHA,env)==before,'Frozen source changed during experiment.')
        finally:cleanup_owned()


def main():
    stage='entry'
    try:
        require(len(sys.argv)==2 and sys.argv[1] in ('prepare','fetch','run','cleanup'),'Unknown experiment stage.')
        stage=sys.argv[1]
        with patch.multiple(request,PARENT=PARENT,MESSAGE=MESSAGE,WORKFLOW=WORKFLOW,REQUEST_PATH=REQUEST_PATH,
                            REQUEST=REQUEST,SOURCE_REF=SOURCE_REF,SOURCE_SHA=SOURCE_SHA,SERVER_SHA=SERVER_SHA):
            request.context()
            if stage=='prepare':request.prepare()
            elif stage=='fetch':request.p.fetch()
            elif stage=='run':experiment()
            else:
                try:cleanup_owned()
                finally:request.p.cleanup()
                print(json.dumps({'stage':'native-rate-experiment-cleanup','status':'passed'}),flush=True)
        return 0
    except Exception:
        print(json.dumps({'stage':'native-rate-experiment-gate','status':'failed','phase':stage}),flush=True)
        return 1


if __name__=='__main__':sys.exit(main())
