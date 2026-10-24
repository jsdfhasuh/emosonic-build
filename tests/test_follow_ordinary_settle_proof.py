import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_ordinary_settle_proof as c


class OrdinarySettlementProofTests(unittest.TestCase):
    def pins(self):
        return dict(SOURCE_SHA='a'*40, SOURCE_REF='refs/heads/test/synthetic-ordinary-settlement',
                    INVENTORY_SHA256='b'*64,INVENTORY_PATH='tool/synthetic_ordinary_settlement/test_inventory.json',
                    ASSERTION_MARKER='SYNTHETIC_ORDINARY_SETTLEMENT_MARKER',EXPECTED_COUNT=4,
                    REQUEST=dict(c.REQUEST, source_sha='a'*40,
                                 source_ref='refs/heads/test/synthetic-ordinary-settlement'))

    def test_exact_delegation_and_restore_after_success_or_exception(self):
        names=('PARENT','MESSAGE','WORKFLOW','REQUEST_PATH','SOURCE_REF','SOURCE_SHA',
               'BASELINE_SHA','SERVER_SHA','INVENTORY_PATH','INVENTORY_SHA256',
               'ASSERTION_MARKER','EXPECTED_COUNT','REQUEST')
        old={name:getattr(c.base,name) for name in names}
        for raises in (False,True):
            def check():
                for name in names:self.assertEqual(getattr(c.base,name),getattr(c,name))
                if raises:raise RuntimeError('synthetic')
                return 7
            with self.subTest(raises=raises),patch.multiple(c,**self.pins()),patch.object(c.base,'main',side_effect=check):
                if raises:
                    with self.assertRaises(RuntimeError):c.main()
                else:self.assertEqual(c.main(),7)
            self.assertEqual({name:getattr(c.base,name) for name in names},old)

    def test_pending_and_inconsistent_pins_block_before_delegation(self):
        for change in ({'SOURCE_SHA':'PENDING'}, {'SOURCE_REF':'PENDING'},
                       {'INVENTORY_PATH':'PENDING'}, {'ASSERTION_MARKER':None},
                       {'ASSERTION_MARKER':'private words'}, {'EXPECTED_COUNT':None},
                       {'EXPECTED_COUNT':True}, {'EXPECTED_COUNT':1}, {'EXPECTED_COUNT':3}, {'EXPECTED_COUNT':5}, {'EXPECTED_COUNT':129},
                       {'INVENTORY_SHA256':'PENDING'}, {'INVENTORY_SHA256':'0'*63},
                       {'SOURCE_REF':'refs/heads/fix/not-test-only'},
                       {'REQUEST':dict(c.REQUEST,source_sha='c'*40)},
                       {'REQUEST':dict(self.pins()['REQUEST'],baseline_sha='c'*40)}):
            values=dict(self.pins(),**change)
            with self.subTest(change=change),patch.multiple(c,**values),patch.object(c.base,'main') as base,contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(c.main(),1);base.assert_not_called()
                self.assertEqual(out.getvalue(),'ERROR: Ordinary settlement proof pins are incomplete or inconsistent.\n')

    def test_native_package_and_full_stages_remain_forbidden(self):
        for args in (['gate','native','run'],['gate','source','publish'],
                     ['gate','source','build'],['gate','source','validate_source']):
            with self.subTest(args=args),patch.multiple(c,**self.pins()),patch.object(sys,'argv',args),patch.object(c.base.request,'context') as context,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1);context.assert_not_called()

    def events(self):
        names=['synthetic causal']+[f'synthetic control {i}' for i in range(3)]
        events=[dict(type='start')]
        for tid,name in enumerate(names):
            events.append(dict(type='testStart',test=dict(id=tid,name=name)))
            if tid==0:events.append(dict(type='error',testID=tid,isFailure=True,error='SYNTHETIC_ORDINARY_SETTLEMENT_MARKER'))
            events.append(dict(type='testDone',testID=tid,result='failure' if tid==0 else 'success',hidden=False,skipped=False))
        events.append(dict(type='done',success=False))
        return names,events

    def verify(self,events,names,code=1):
        return c.base.red.exact_red('\n'.join(json.dumps(e) for e in events),code,
            names=names,basename='synthetic_ordinary_settlement_test.dart',causal_ordinal=1,
            expected_count=4,assertion_marker='SYNTHETIC_ORDINARY_SETTLEMENT_MARKER')

    def test_same_verifier_requires_one_exact_causal_failure_and_three_controls(self):
        names,events=self.events();report=self.verify(events,names)
        self.assertEqual(report['visibleTests'],4);self.assertEqual(report['passedControls'],3)
        self.assertEqual(report['causalOrdinal'],1);self.assertEqual(report['expectedFailures'],1)
        self.assertNotIn('synthetic',json.dumps(report))

    def test_wrong_marker_failed_control_skip_missing_case_and_green_refused(self):
        for change in ('marker','control','skip','missing','green','extra_error',
                       'duplicate_id','wrong_causal','hidden_causal','missing_done'):
            names,events=self.events()
            if change=='marker':events[2]['error']='SYNTHETIC_ORDINARY_SETTLEMENT_MARKER private suffix'
            elif change=='control':events[-2]['result']='failure'
            elif change=='skip':events[-2]['skipped']=True
            elif change=='missing':del events[-3:-1]
            elif change=='extra_error':events.insert(-1,dict(events[2]))
            elif change=='duplicate_id':events[-3]['test']['id']=0
            elif change=='wrong_causal':events[2]['testID']=1
            elif change=='hidden_causal':events[3]['hidden']=True
            elif change=='missing_done':events.pop()
            with self.subTest(change=change),self.assertRaises(c.base.GreenVerificationError):
                self.verify(events,names,code=0 if change=='green' else 1)

    def fixture_tree(self, root):
        path='test/services/synthetic_ordinary_settlement_test.dart'
        target=root/path
        target.parent.mkdir(parents=True)
        target.write_text('synthetic private fixture, not a product test')
        names,_=self.events()
        suite=dict(path=path,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                   names=names,causalOrdinal=1)
        inventory=root/self.pins()['INVENTORY_PATH']
        inventory.parent.mkdir(parents=True)
        inventory.write_text(json.dumps(dict(suites=[suite])))
        return suite,inventory

    def test_same_verifier_checks_frozen_fixture_and_inventory_bytes(self):
        for change in ('fixture','inventory'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                suite,inventory=self.fixture_tree(root)
                digest=hashlib.sha256(inventory.read_bytes()).hexdigest()
                with patch.multiple(c.base,EXPECTED_COUNT=4,
                                    INVENTORY_PATH=self.pins()['INVENTORY_PATH'],
                                    INVENTORY_SHA256=digest):
                    self.assertEqual(c.base.inventory(root),suite)
                    target=root/suite['path'] if change=='fixture' else inventory
                    target.write_text(target.read_text()+' changed')
                    with self.assertRaises(c.base.request.p.GateError):
                        c.base.inventory(root)

    def test_bad_inventory_never_relaxes_the_four_case_contract(self):
        for change in ('three_cases','five_cases','duplicate_name','missing_ordinal',
                       'bool_ordinal','zero_ordinal','extra_key'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                suite,inventory=self.fixture_tree(root)
                if change=='three_cases':suite['names'].pop()
                elif change=='five_cases':suite['names'].append('unexpected case')
                elif change=='duplicate_name':suite['names'][-1]=suite['names'][0]
                elif change=='missing_ordinal':del suite['causalOrdinal']
                elif change=='bool_ordinal':suite['causalOrdinal']=True
                elif change=='zero_ordinal':suite['causalOrdinal']=0
                elif change=='extra_key':suite['private_detail']='must not export'
                inventory.write_text(json.dumps(dict(suites=[suite])))
                digest=hashlib.sha256(inventory.read_bytes()).hexdigest()
                with patch.multiple(c.base,EXPECTED_COUNT=4,
                                    INVENTORY_PATH=self.pins()['INVENTORY_PATH'],
                                    INVENTORY_SHA256=digest):
                    with self.assertRaises(c.base.request.p.GateError):
                        c.base.inventory(root)

    def test_wrapper_runs_the_unchanged_bounded_inventory_proof(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            suite,inventory=self.fixture_tree(root)
            pins=dict(self.pins(),INVENTORY_SHA256=hashlib.sha256(inventory.read_bytes()).hexdigest())
            _,events=self.events()
            result=SimpleNamespace(stdout='\n'.join(json.dumps(e) for e in events),
                                   stderr='',returncode=1)
            with patch.multiple(c,**pins), \
                 patch.object(sys,'argv',['gate','source','red']), \
                 patch.object(c.base.request,'context'), \
                 patch.object(c.base.request.p,'source_context',return_value=(root,None,'a'*40,None)), \
                 patch.object(c.base.request.p,'source_fingerprint',return_value='unchanged') as fingerprint, \
                 patch.object(c.base,'native_env',return_value={}), \
                 patch.object(c.base.request.p,'codegen') as codegen, \
                 patch.object(c.base,'bounded_run',return_value=(result,None)) as run, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(c.main(),0)
            fingerprint.assert_called()
            self.assertEqual(fingerprint.call_count,2)
            codegen.assert_called_once_with(root,{})
            run.assert_called_once_with(
                ['flutter','test','--no-pub','--reporter=json',suite['path']],cwd=root,env={})
            report=json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(report['status'],'expected-failure-confirmed')
            self.assertEqual(report['visibleTests'],4)
            self.assertEqual(report['passedControls'],3)
            self.assertEqual(report['causalOrdinal'],1)
            self.assertNotIn('synthetic private fixture',output.getvalue())
            self.assertNotIn('synthetic causal',output.getvalue())

    def test_exact_fixed_contract(self):
        self.assertEqual(c.BASELINE_SHA,'f6251a2a0e6441f174d05b488bc0fb1b41d52e39')
        self.assertEqual(c.PARENT,'4cf220d7a7228cbe168860ff1d9af071225fc6eb')
        self.assertEqual(c.REQUEST['attempt'],103)
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_smooth_settlement/test_inventory.json')
        self.assertEqual(c.ASSERTION_MARKER,'FOLLOW_ORDINARY_POSITIVE_RESTORE_PRECEDES_TARGET_CROSSING')
        self.assertEqual(c.EXPECTED_COUNT,4)
        self.assertEqual((c.SOURCE_SHA,c.SOURCE_REF,c.INVENTORY_SHA256),('7c99e38ecf68cf157bc08b2cf3bae8ce273d54b3', 'refs/heads/test/follow-smooth-settlement-20261024', '8333739b5f453587527ee19afcff703232ba8d491ae902d5e4bedd8865c43936'))

    def test_workflow_and_request_preserve_security_and_cleanup(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,text)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertIn('contents: read',text);self.assertIn('persist-credentials: false',text)
        self.assertIn('if: always()',text);self.assertIn("flutter-version: '3.41.2'",text)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',text)
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',text)
        for value in ('upload-artifact','contents: write','continue-on-error','macos-',
                      'validate-source:','publish','RELEASE_WRITE_TOKEN'):
            self.assertNotIn(value,text)
        for stage in ('prepare','fetch','red','cleanup'):
            self.assertIn('follow_ordinary_settle_proof.py source '+stage,text)


if __name__=='__main__':unittest.main()
