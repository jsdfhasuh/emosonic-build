import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_receipt_consumption_proof as c


class NativeReceiptConsumptionProofTests(unittest.TestCase):
    def pins(self):
        return dict(SOURCE_SHA='a'*40, SOURCE_REF='refs/heads/test/synthetic-receipt',
                    INVENTORY_SHA256='b'*64,INVENTORY_PATH='tool/synthetic_receipt/test_inventory.json',
                    ASSERTION_MARKER='SYNTHETIC_RECEIPT_MARKER',EXPECTED_COUNT=3,
                    REQUEST=dict(c.REQUEST, source_sha='a'*40,
                                 source_ref='refs/heads/test/synthetic-receipt'))

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
                       {'EXPECTED_COUNT':True}, {'EXPECTED_COUNT':1}, {'EXPECTED_COUNT':129},
                       {'INVENTORY_SHA256':'PENDING'}, {'INVENTORY_SHA256':'0'*63},
                       {'SOURCE_REF':'refs/heads/fix/not-test-only'},
                       {'REQUEST':dict(c.REQUEST,source_sha='c'*40)},
                       {'REQUEST':dict(self.pins()['REQUEST'],baseline_sha='c'*40)}):
            values=dict(self.pins(),**change)
            with self.subTest(change=change),patch.multiple(c,**values),patch.object(c.base,'main') as base,contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(c.main(),1);base.assert_not_called()
                self.assertEqual(out.getvalue(),'ERROR: Native receipt consumption proof pins are incomplete or inconsistent.\n')

    def test_native_package_and_full_stages_remain_forbidden(self):
        for args in (['gate','native','run'],['gate','source','publish'],
                     ['gate','source','build'],['gate','source','validate_source']):
            with self.subTest(args=args),patch.multiple(c,**self.pins()),patch.object(sys,'argv',args),patch.object(c.base.request,'context') as context,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1);context.assert_not_called()

    def events(self):
        names=['synthetic causal']+[f'synthetic control {i}' for i in range(2)]
        events=[dict(type='start')]
        for tid,name in enumerate(names):
            events.append(dict(type='testStart',test=dict(id=tid,name=name)))
            if tid==0:events.append(dict(type='error',testID=tid,isFailure=True,error='SYNTHETIC_RECEIPT_MARKER'))
            events.append(dict(type='testDone',testID=tid,result='failure' if tid==0 else 'success',hidden=False,skipped=False))
        events.append(dict(type='done',success=False))
        return names,events

    def verify(self,events,names,code=1):
        return c.base.red.exact_red('\n'.join(json.dumps(e) for e in events),code,
            names=names,basename='synthetic_receipt_test.dart',causal_ordinal=1,
            expected_count=3,assertion_marker='SYNTHETIC_RECEIPT_MARKER')

    def test_same_verifier_requires_one_exact_causal_failure_and_two_controls(self):
        names,events=self.events();report=self.verify(events,names)
        self.assertEqual(report['visibleTests'],3);self.assertEqual(report['passedControls'],2)
        self.assertEqual(report['causalOrdinal'],1);self.assertEqual(report['expectedFailures'],1)
        self.assertNotIn('synthetic',json.dumps(report))

    def test_wrong_marker_failed_control_skip_missing_case_and_green_refused(self):
        for change in ('marker','control','skip','missing','green'):
            names,events=self.events()
            if change=='marker':events[2]['error']='SYNTHETIC_RECEIPT_MARKER private suffix'
            elif change=='control':events[-2]['result']='failure'
            elif change=='skip':events[-2]['skipped']=True
            elif change=='missing':del events[-3:-1]
            with self.subTest(change=change),self.assertRaises(c.base.GreenVerificationError):
                self.verify(events,names,code=0 if change=='green' else 1)

    def test_exact_fixed_contract(self):
        self.assertEqual(c.BASELINE_SHA,'28fc26149f5e4175fe952219b3cc5f9d18519c50')
        self.assertEqual(c.PARENT,'3abb2333c51f26aeb00849ee8725aaa9ed4fea89')
        self.assertEqual(c.REQUEST['attempt'],82)
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_native_receipt_consumption/test_inventory.json')
        self.assertEqual(c.ASSERTION_MARKER,'FOLLOW_NATIVE_RECEIPT_WAITS_FOR_RECOVERY_POLL')
        self.assertEqual(c.EXPECTED_COUNT,3)
        self.assertEqual((c.SOURCE_SHA,c.SOURCE_REF,c.INVENTORY_SHA256),('af854f4802e616bf22f01df62055d4ce32635d77', 'refs/heads/test/follow-native-receipt-consumption-20261023', 'bb72be1172b73b0a53777951acdb295da4e2a3fa7dbc99480b18ec311d98c35d'))

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
            self.assertIn('native_receipt_consumption_proof.py source '+stage,text)


if __name__=='__main__':unittest.main()
