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

PARENT = '3b93097b80ad1fd69b19737edbd8028780d46ca2'
MESSAGE = 'test: validate controlled recovery event delivery 20261022'
WORKFLOW = 'follow-recovery-check.yml'
REQUEST_PATH = 'requests/follow-recovery-check-20261022.json'
SOURCE_REF = 'refs/heads/test/follow-recovery-sync-fixture-20261022'
SOURCE_SHA = '15bdc56b8a93db62bba2b5549073e1e09a8a88ff'
SERVER_SHA = '5adc23da173c5f20188d79aafe8fcc1e656eb38a'
INVENTORY_PATH = 'tool/follow_recovery/test_inventory.json'
INVENTORY_SHA256 = '33b9ae0c51b6c60913a88367f3fa5fc5d8e2a7f1c46cc07dced3c0e0f85296c4'
REQUEST = dict(request.REQUEST, source_ref=SOURCE_REF, source_sha=SOURCE_SHA,
               server_sha=SERVER_SHA, mode='bounded-follow-recovery-validation', attempt=22)
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
            with patch.object(sys,'argv',[sys.argv[0],stage]):return request.main()
    except Exception as exc:
        known=('GateError','GreenVerificationError','TimeoutExpired','ValueError','TypeError','KeyError','JSONDecodeError')
        print(json.dumps({'stage':'follow-recovery-validation-failure','failedStage':STAGE,
                          'category':type(exc).__name__ if type(exc).__name__ in known else 'other'}),flush=True)
        return 1

if __name__=='__main__':sys.exit(main())
