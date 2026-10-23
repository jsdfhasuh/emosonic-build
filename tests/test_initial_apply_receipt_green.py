import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import initial_apply_receipt_green as c


def suites(counts, prefix):
    return [dict(path='test/services/%s_%d_test.dart' % (prefix, i),
                 names=['synthetic_%s_%d_%d' % (prefix, i, j) for j in range(n)])
            for i, n in enumerate(counts)]


class InitialApplyReceiptGreenTests(unittest.TestCase):
    def pins(self):
        # Fixed reviewed baseline and boundary counts.
        return patch.multiple(c, SOURCE_SHA='a'*40, SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_PATH='tool/synthetic_initial_apply/green_inventory.json',
            INVENTORY_SHA256='b'*64, EXPECTED_COUNTS=(3, 8),
            REQUEST=dict(c.REQUEST, source_sha='a'*40, source_ref='refs/heads/fix/synthetic'))

    def prior(self):
        return suites((15,3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,4,4,4,3,5,3,5,3,4,3,4), 'prior')

    def test_pending_invalid_inconsistent_pins_fail_before_delegation(self):
        for field, value in [('SOURCE_SHA','PENDING'), ('SOURCE_REF','PENDING'),
                            ('INVENTORY_PATH','PENDING'), ('INVENTORY_SHA256','PENDING'),
                            ('EXPECTED_COUNTS',(3,'PENDING')), ('EXPECTED_COUNTS',(3,None)),
                            ('EXPECTED_COUNTS',(3,True)), ('EXPECTED_COUNTS',(4,2)),
                            ('EXPECTED_COUNTS',(3,)), ('EXPECTED_COUNTS',(3,0)),
                            ('EXPECTED_COUNTS',(3,129)), ('EXPECTED_COUNTS',(True,2)),
                            ('EXPECTED_COUNTS',(3,2.0)), ('EXPECTED_COUNTS',[3,2]),
                            ('SOURCE_REF','refs/tags/synthetic'), ('SOURCE_SHA','a'*39),
                            ('INVENTORY_SHA256','b'*63),
                            ('INVENTORY_PATH','../synthetic/green_inventory.json'),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.subTest(field=field,value=value), self.pins(), patch.object(c,field,value), \
                    patch.object(c.previous,'main') as delegated, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1); delegated.assert_not_called()

    def test_all243_retained_in_exact_order_then_both_new_suites(self):
        prior=self.prior(); extra=suites((3,8),'extra'); before=json.dumps(prior)
        with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                patch.object(c.TIMING,'component_inventory',return_value=extra) as load:
            actual=c.inventory(Path('/synthetic'))
            load.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(3,8))
        self.assertEqual(actual,prior+extra); self.assertEqual(actual[:31],prior)
        self.assertIs(actual[0],prior[0])  # Broadcast-first prefix is never reordered.
        self.assertEqual(len(actual),33); self.assertEqual(sum(len(s['names']) for s in actual),254)
        self.assertEqual(json.dumps(prior),before)

    def test_missing_changed_duplicate_cases_fail(self):
        for prior, extra in [(self.prior()[:-1],suites((3,8),'extra')),
                            (self.prior(),suites((3,3),'extra')),
                            (self.prior(),suites((5,),'extra')),
                            (self.prior(),suites((3,8),'prior')),
                            (self.prior()[:-1]+[self.prior()[20]],suites((3,8),'extra')),
                            (self.prior(),suites((3,8),'extra')[:1]),
                            (self.prior(),suites((2,3),'extra')),
                            (self.prior(),[dict(s,path='test/services/duplicate_test.dart') for s in suites((3,8),'extra')]),
                            (self.prior(),[dict(s,names=[s['names'][0]]*len(s['names'])) for s in suites((3,8),'extra')])]:
            with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                    patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))

    def test_manifest_or_fixture_hash_failure_remains_fatal(self):
        with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()), \
                patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))

    def test_nested_overrides_full_acceptance_and_restoration(self):
        ingress=c.TIMING.previous; lowest=ingress.recovery
        receipt=c.previous.previous; directional=receipt.directional
        restore=directional.restore; clock=directional.CLOCK
        names=('PARENT','MESSAGE','WORKFLOW','REQUEST_PATH','REQUEST','SOURCE_REF','SOURCE_SHA','SERVER_SHA')
        tracked=[(module,name) for module in (lowest,c.previous,receipt) for name in (*names,'inventory')]
        tracked += [(c.previous,'INVENTORY_PATH'),(c.previous,'INVENTORY_SHA256'),(c.previous,'EXPECTED_COUNTS'),
                    (receipt,'DIRECTIONAL_INVENTORY_SHA256'),(receipt.diagnostic,'FIXTURE_SHA256'),
                    (directional,'INVENTORY_SHA256'),(restore,'COMPONENTS'),
                    (ingress,'RECOVERY_INVENTORY_SHA256'),(lowest,'INVENTORY_SHA256'),
                    (ingress.ingress,'INVENTORY_SHA256'),(lowest,'observe_green'),
                    (lowest,'full_test_observation'),(lowest,'validate_full')]
        original=[getattr(module,name) for module,name in tracked]
        original_observer=lowest.observe_green; original_full=lowest.validate_full
        for stage in ('focused','validate_source'):
            for fails in (False,True):
                def observe():
                    for name in names: self.assertEqual(getattr(lowest,name),getattr(c,name))
                    self.assertIs(lowest.inventory,c.inventory)
                    self.assertEqual(c.previous.INVENTORY_PATH,'tool/follow_fractional_precision/green_inventory.json')
                    self.assertEqual(c.previous.INVENTORY_SHA256,'9b1fcd4288a1993f2334228184fdecd54ba97911af726d2d682d4424f4681c3e')
                    self.assertEqual(c.previous.EXPECTED_COUNTS,(3,4))
                    self.assertEqual(receipt.DIRECTIONAL_INVENTORY_SHA256,c.previous.DIRECTIONAL_INVENTORY_SHA256)
                    self.assertEqual(receipt.diagnostic.FIXTURE_SHA256,c.previous.DIAGNOSTIC_FIXTURE_SHA256)
                    self.assertEqual(directional.INVENTORY_SHA256,receipt.previous.DIRECTIONAL_INVENTORY_SHA256)
                    self.assertEqual(restore.COMPONENTS,((directional.POST_RESTORE_PATH,directional.POST_RESTORE_DIGEST,(4,6)),))
                    self.assertEqual(ingress.RECOVERY_INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(lowest.INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(ingress.ingress.INVENTORY_SHA256,ingress.INGRESS_INVENTORY_SHA256)
                    self.assertIs(lowest.full_test_observation,ingress.dispatch_full_observation)
                    self.assertIs(lowest.observe_green,ingress.focused_observation if stage=='focused' else original_observer)
                    self.assertIs(lowest.validate_full,original_full)
                    if fails: raise RuntimeError('synthetic')
                    return 7
                with self.subTest(stage=stage,fails=fails), self.pins(), \
                        patch.object(sys,'argv',['gate','source',stage]), patch.object(lowest,'main',side_effect=observe):
                    if fails:
                        with self.assertRaises(RuntimeError): c.main()
                    else: self.assertEqual(c.main(),7)
                self.assertEqual([getattr(module,name) for module,name in tracked],original)

    def test_fixed_baseline_and_reviewed_contract(self):
        self.assertEqual(c.PARENT,'22f7bbc97c3766ebb2989fb1b7dda37b5061f748')
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.REQUEST['attempt'],95)
        self.assertEqual((c.SOURCE_SHA,c.SOURCE_REF),('f6251a2a0e6441f174d05b488bc0fb1b41d52e39', 'refs/heads/fix/follow-initial-apply-flow-lint-20261023'))
        self.assertEqual(c.INVENTORY_SHA256,'5628a0ea2f6781ad78ed816f5e17f96157f0da9fb3a663be14f8b634d90b2306')
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_initial_apply_receipt/green_inventory.json')
        self.assertEqual(c.EXPECTED_COUNTS,(3,8))
        with patch.object(c,'SOURCE_SHA','PENDING'), patch.object(c.previous,'main') as delegated, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(c.main(),1); delegated.assert_not_called()
        for first in (1,2,4,True):
            with self.pins(), patch.object(c,'EXPECTED_COUNTS',(first,8)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()
        for second in (1,2,3,4,5,6,7,9,128):
            with self.pins(), patch.object(c,'EXPECTED_COUNTS',(3,second)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()

    def test_native_package_publish_and_red_stages_forbidden(self):
        lowest=c.TIMING.previous.recovery
        for args in (['gate','native','run'],['gate','source','native'],
                     ['gate','source','package'],['gate','source','publish'],['gate','source','red']):
            with self.subTest(args=args), self.pins(), patch.object(sys,'argv',args), \
                    patch.object(lowest.request,'context') as context, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1); context.assert_not_called()

    def test_workflow_preserves_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1]; text=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH): self.assertIn(value,text)
        for value in ('contents: read','source focused','source validate_source','if: always()',
                      'source cleanup','persist-credentials: false'): self.assertIn(value,text)
        for value in ('upload-artifact','source native','source package','source publish',
                      'contents: write','workflow_dispatch','continue-on-error','RELEASE_WRITE_TOKEN','macos-'): self.assertNotIn(value,text)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertLess(text.index('source focused'),text.index('source validate_source'))
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',text)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',text)
        self.assertIn("flutter-version: '3.41.2'",text)
        for stage in ('prepare','fetch','focused','validate_source','cleanup'):
            self.assertIn('initial_apply_receipt_green.py source '+stage,text)


if __name__=='__main__': unittest.main()
