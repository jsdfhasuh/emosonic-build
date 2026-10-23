import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_receipt_consumption_green as c


def suites(counts, prefix):
    return [dict(path='test/services/%s_%d_test.dart' % (prefix, i),
                 names=['synthetic_%d_%d' % (i,j) for j in range(n)]) for i,n in enumerate(counts)]


class NativeReceiptConsumptionGreenTests(unittest.TestCase):
    def pins(self):
        return patch.multiple(c,SOURCE_SHA='a'*40,SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_SHA256='b'*64,EXPECTED_COUNTS=(3,4),
            REQUEST=dict(c.REQUEST,source_sha='a'*40,source_ref='refs/heads/fix/synthetic'))

    def prior(self):
        return suites((15,3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,3,4,4,3,5,3,5),'prior')

    def test_pending_invalid_inconsistent_pins_fail_before_delegation(self):
        for field,value in [('SOURCE_SHA','PENDING'),('SOURCE_REF','PENDING'),
                            ('INVENTORY_SHA256','PENDING'),('EXPECTED_COUNTS',(3,None)),
                            ('EXPECTED_COUNTS',(3,True)),('EXPECTED_COUNTS',(4,4)),
                            ('EXPECTED_COUNTS',(3,)),('EXPECTED_COUNTS',(3,0)),('EXPECTED_COUNTS',(3,1001)),
                            ('EXPECTED_COUNTS',(True,4)),('EXPECTED_COUNTS',(3,4.0)),
                            ('EXPECTED_COUNTS',[3,4]),('EXPECTED_COUNTS',(3,'PENDING')),
                            ('SOURCE_REF','refs/tags/synthetic'),('SOURCE_SHA','a'*39),
                            ('INVENTORY_SHA256','b'*63),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.pins(),patch.object(c,field,value),patch.object(c.previous,'main') as call,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);call.assert_not_called()

    def test_all228_retained_then_both_exact_new_suites(self):
        prior=self.prior();extra=suites((3,4),'extra');before=json.dumps(prior)
        with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=prior),patch.object(c.TIMING,'component_inventory',return_value=extra) as load:
            actual=c.inventory(Path('/synthetic'));load.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(3,4))
        self.assertEqual(actual,prior+extra);self.assertEqual(len(actual),29)
        self.assertEqual(sum(len(s['names']) for s in actual),235);self.assertEqual(json.dumps(prior),before)

    def test_missing_changed_duplicate_cases_fail(self):
        for prior,extra in [(self.prior()[:-1],suites((3,4),'extra')),
                            (self.prior(),suites((3,3),'extra')),
                            (self.prior(),suites((7,),'extra')),
                            (self.prior(),suites((3,4),'prior')),
                            (self.prior()[:-1]+[self.prior()[24]],suites((3,4),'extra')),
                            (self.prior(),suites((3,4),'extra')[:1]),
                            (self.prior(),suites((4,3),'extra')),
                            (self.prior(),[dict(s,path='test/services/synthetic_duplicate_test.dart') for s in suites((3,4),'extra')])]:
            with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=prior),patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_manifest_failure_remains_fatal(self):
        with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()),patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_complete_delegation_nested_overrides_diagnostics_and_restoration(self):
        ingress=c.TIMING.previous;lowest=ingress.recovery
        directional=c.previous.directional;restore=directional.restore;clock=directional.CLOCK
        names=('PARENT','MESSAGE','WORKFLOW','REQUEST_PATH','REQUEST','SOURCE_REF','SOURCE_SHA','SERVER_SHA')
        tracked=[(module,name) for module in (lowest,c.previous) for name in (*names,'inventory')]
        tracked += [(directional,'INVENTORY_SHA256'),(restore,'COMPONENTS'),
                    (ingress,'RECOVERY_INVENTORY_SHA256'),(lowest,'INVENTORY_SHA256'),
                    (ingress.ingress,'INVENTORY_SHA256'),(lowest,'observe_green'),
                    (lowest,'full_test_observation'),(lowest,'validate_full')]
        original=[getattr(module,name) for module,name in tracked]
        original_observer=lowest.observe_green;original_full=lowest.validate_full
        for stage in ('focused','validate_source'):
            for fails in (False,True):
                def observe():
                    for name in names:self.assertEqual(getattr(lowest,name),getattr(c,name))
                    self.assertIs(lowest.inventory,c.inventory)
                    self.assertEqual(directional.INVENTORY_SHA256,c.previous.DIRECTIONAL_INVENTORY_SHA256)
                    self.assertEqual(restore.COMPONENTS,((directional.POST_RESTORE_PATH,directional.POST_RESTORE_DIGEST,(4,6)),))
                    self.assertEqual(ingress.RECOVERY_INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(lowest.INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(ingress.ingress.INVENTORY_SHA256,ingress.INGRESS_INVENTORY_SHA256)
                    self.assertIs(lowest.full_test_observation,ingress.dispatch_full_observation)
                    self.assertIs(lowest.observe_green,ingress.focused_observation if stage=='focused' else original_observer)
                    self.assertIs(lowest.validate_full,original_full)
                    if fails:raise RuntimeError('synthetic')
                    return 7
                with self.subTest(stage=stage,fails=fails),self.pins(),patch.object(sys,'argv',['gate','source',stage]),patch.object(lowest,'main',side_effect=observe):
                    if fails:
                        with self.assertRaises(RuntimeError):c.main()
                    else:self.assertEqual(c.main(),7)
                self.assertEqual([getattr(module,name) for module,name in tracked],original)

    def test_exact_fixed_contract_and_bounded_boundary_count(self):
        self.assertEqual(c.PARENT,'412cba5ff569d62b53ff800dfbef7cc80700e325')
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.REQUEST['attempt'],83)
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_native_receipt_consumption/green_inventory.json')
        self.assertEqual(c.EXPECTED_COUNTS[0],3)
        for count in (1,4,1000):
            with self.pins(),patch.object(c,'EXPECTED_COUNTS',(3,count)):c.require_counts()

    def test_native_package_publish_and_red_stages_remain_forbidden(self):
        lowest=c.TIMING.previous.recovery
        for args in (['gate','native','run'],['gate','source','native'],
                     ['gate','source','package'],['gate','source','publish'],['gate','source','red']):
            with self.subTest(args=args),self.pins(),patch.object(sys,'argv',args),patch.object(lowest.request,'context') as context,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1);context.assert_not_called()

    def test_workflow_preserves_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1];w=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,w)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup','persist-credentials: false'):self.assertIn(value,w)
        for value in ('upload-artifact','source native','source package','source publish','contents: write','workflow_dispatch','continue-on-error','RELEASE_WRITE_TOKEN','macos-'):self.assertNotIn(value,w)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertEqual(c.REQUEST['attempt'],83)
        self.assertLess(w.index('source focused'),w.index('source validate_source'))
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',w)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',w)
        self.assertIn("flutter-version: '3.41.2'",w)
        for stage in ('prepare','fetch','focused','validate_source','cleanup'):
            self.assertIn('native_receipt_consumption_green.py source '+stage,w)


if __name__=='__main__':unittest.main()
