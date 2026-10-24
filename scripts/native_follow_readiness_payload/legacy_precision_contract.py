"""Exact private case identities by digest; finite output, no private names/source."""
import contextlib
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / 'legacy_precision_inventory.json'
DEPENDENCIES = ('fixture_diagnostics.py', 'canonical_observations.py',
    'follow_lifecycle_observation.py', 'follow_server_observation.py', 'native_seek_anchor_observation.py')
HEALTH_LINE = "        value['nativePlayers'][0].update(seekInProgress=False, playingIntent=True)\n"


def digest(data): return hashlib.sha256(data).hexdigest()


def inventory():
    value=json.loads(INVENTORY.read_text())
    assert value['priorCount']==70 and value['finalCompatibleCount']==63 and value['finalPrecisionCount']==46 and value['mappedPrecisionPrefixCount']==35
    assert value['externalConvergenceBudgetMs']==10000
    assert sorted(row['ordinal'] for rows in value['externalBudgetAdaptations'].values() for row in rows)==[13,17,25]
    cases=value['cases']
    assert len(cases)==70 and [x['ordinal'] for x in cases]==list(range(1,71))
    assert len({x['caseSha256'] for x in cases})==70
    assert sum(x['classification'] in ('unchanged_final','metadata_only_final') for x in cases)==63
    assert sum('finalPrecisionOrdinals' in x for x in cases)==7
    return value



def adapt_budget_fixture(data, filename, contract, *, inverse=False):
    """Exact three legacy cases only, inside the removed private unit copy.

    Original discovery names and source hashes remain pinned. Only the listed
    deadline stimuli/assertion constants and renamed finite condition change;
    all other bytes are preserved, and the inverse is byte-exact.
    """
    specs = contract.get('externalBudgetAdaptations', {}).get(filename, [])
    if not specs: return data
    text=data.decode('utf-8'); lines=text.splitlines(keepends=True)
    offsets=[]; at=0
    for line in lines: offsets.append(at); at+=len(line)
    tree=ast.parse(text); found={}; replacements=[]
    for cls in tree.body:
        if not isinstance(cls,ast.ClassDef): continue
        for method in cls.body:
            if not isinstance(method,ast.FunctionDef): continue
            case=digest(f'{Path(filename).stem}.{cls.name}.{method.name}'.encode())
            spec=next((row for row in specs if row['caseSha256']==case),None)
            if spec is None: continue
            assert case not in found
            key='afterAstSha256' if inverse else 'beforeAstSha256'
            assert digest(ast.dump(method,include_attributes=False).encode())==spec[key]
            changed=copy.deepcopy(method)
            for literal in spec['literals']:
                old,new=(literal['after'],literal['before']) if inverse else (literal['before'],literal['after'])
                nodes=[node for node in ast.walk(changed) if isinstance(node,ast.Constant)
                    and type(node.value) is type(old) and node.value==old]
                assert len(nodes)==literal['count']
                for node in nodes:
                    start=offsets[node.lineno-1]+node.col_offset
                    end=offsets[node.end_lineno-1]+node.end_col_offset
                    assert text[start:end]==repr(old)
                    replacements.append((start,end,repr(new)));node.value=new
            target='beforeAstSha256' if inverse else 'afterAstSha256'
            assert digest(ast.dump(changed,include_attributes=False).encode())==spec[target]
            found[case]=True
    assert set(found)=={row['caseSha256'] for row in specs}
    for start,end,replacement in sorted(replacements,reverse=True):text=text[:start]+replacement+text[end:]
    return text.encode('utf-8')


def flattened(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite): yield from flattened(test)
        else: yield test


def select_exact(tests, contract, layer):
    assert layer in ('prior','final_compatible')
    tests=sorted(tests,key=lambda test:test.id())
    expected=contract['cases']
    assert len(tests)==70
    assert [digest(t.id().encode()) for t in tests]==[x['caseSha256'] for x in expected]
    selected=[t for t,row in zip(tests,expected) if layer=='prior' or
        row['classification'] in ('unchanged_final','metadata_only_final')]
    assert len(selected)==(70 if layer=='prior' else 63)
    return selected


def child(directory,layer):
    contract=inventory();directory=Path(directory)
    for name,wanted in contract['testFiles'].items():
        actual=directory/name
        assert actual.is_file() and not actual.is_symlink()
        if layer=='prior' and name=='test_follow_alignment.py':wanted=contract['priorAlignmentSha256']
        elif layer=='final_compatible':wanted=contract['finalBudgetTestFiles'].get(name,wanted)
        assert digest(actual.read_bytes())==wanted
    assert {p.name for p in directory.glob('test_*.py')}==set(contract['testFiles'])
    sys.path.insert(0,str(directory))
    with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
        suite=unittest.defaultTestLoader.discover(str(directory),pattern='test_*.py')
        selected=select_exact(list(flattened(suite)),contract,layer)
        result=unittest.TestResult();unittest.TestSuite(selected).run(result)
    failed=[]
    known={row['caseSha256']:row['ordinal'] for row in contract['cases']}
    for test,_ in result.errors+result.failures:
        owner=getattr(test,'test_case',test)
        ordinal=known.get(digest(owner.id().encode()))
        if ordinal is not None:failed.append(ordinal)
    okay=(result.testsRun==len(selected) and not (result.errors or result.failures or result.skipped
        or result.expectedFailures or result.unexpectedSuccesses))
    return {'status':'passed' if okay else 'failed','count':result.testsRun,
        'failedCaseOrdinals':sorted(set(failed)), 'errorCategory':'runner' if result.errors else 'assertion'}


def run_layer(source_directory,harness,layer):
    """No source writes: one private, removed, isolated Python module tree."""
    assert layer in ('prior','final_compatible')
    contract=inventory();source_directory=Path(source_directory)
    assert {p.relative_to(source_directory).as_posix() for p in source_directory.rglob('test_*.py')}==set(contract['testFiles'])
    with tempfile.TemporaryDirectory(prefix='owned-follow-unit-') as temporary:
        directory=Path(temporary).resolve(strict=True)
        for name in (*contract['testFiles'],*DEPENDENCIES):
            path=source_directory/name
            assert path.is_file() and not path.is_symlink() and path.stat().st_size<=1024*1024
            data=path.read_bytes()
            if name in contract['testFiles']:
                assert digest(data)==contract['testFiles'][name]
            if name=='test_follow_alignment.py' and layer=='prior':
                assert data.count(HEALTH_LINE.encode())==1
                data=data.replace(HEALTH_LINE.encode(),b'',1)
                assert digest(data)==contract['priorAlignmentSha256']
            if layer=='final_compatible' and name in contract['testFiles']:
                original=data;data=adapt_budget_fixture(data,name,contract)
                assert adapt_budget_fixture(data,name,contract,inverse=True)==original
            (directory/name).write_bytes(data)
        (directory/'run_lab.py').write_bytes(harness)
        env={k:v for k,v in os.environ.items() if k not in
            ('GITHUB_ENV','GITHUB_OUTPUT','GITHUB_PATH','GITHUB_STEP_SUMMARY','PYTHONPATH','PYTHONHOME')}
        env['PYTHONDONTWRITEBYTECODE']='1';env['TMPDIR']=str(directory)
        process=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),str(directory),layer],
            cwd=directory,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        assert process.returncode==0 and len(process.stdout)<=16384 and len(process.stderr)<=16384
        value=json.loads(process.stdout)
        assert type(value) is dict and set(value)=={'status','count','failedCaseOrdinals','errorCategory'}
        assert value['status'] in ('passed','failed') and value['errorCategory'] in ('runner','assertion')
        assert type(value['count']) is int and value['count']==(70 if layer=='prior' else 63)
        assert type(value['failedCaseOrdinals']) is list and len(value['failedCaseOrdinals'])<=70
        assert all(type(v) is int and 1<=v<=70 for v in value['failedCaseOrdinals'])
        assert value['failedCaseOrdinals']==sorted(set(value['failedCaseOrdinals']))
        assert value['status']!='passed' or not value['failedCaseOrdinals']
        return value


if __name__=='__main__':
    try:
        assert len(sys.argv)==3 and sys.argv[2] in ('prior','final_compatible')
        result=child(sys.argv[1],sys.argv[2]);print(json.dumps(result))
    except Exception:
        # Never serialize import errors, assertion values, IDs or private paths.
        raise SystemExit(1) from None
