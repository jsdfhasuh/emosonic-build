import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_ordinary_settle_green as c


# Synthetic fixtures, using the exact reviewed boundary count.
SYNTHETIC_BOUNDARY_COUNT = 16


def suites(counts, prefix):
    return [dict(path='test/services/%s_%d_test.dart' % (prefix, i),
                 names=['synthetic_%s_%d_%d' % (prefix, i, j) for j in range(n)])
            for i, n in enumerate(counts)]


class OrdinarySettlementGreenTests(unittest.TestCase):
    def pins(self):
        return patch.multiple(c, SOURCE_SHA='a'*40, SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_SHA256='b'*64,
            REQUEST=dict(c.REQUEST, source_sha='a'*40, source_ref='refs/heads/fix/synthetic'))

    def prior(self):
        return suites((15,3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,4,4,4,3,5,3,5,3,4,3,4,3,8), 'prior')

    def extra(self):
        return suites((4, SYNTHETIC_BOUNDARY_COUNT), 'extra')

    def test_pending_invalid_inconsistent_pins_fail_before_delegation(self):
        for field, value in [('SOURCE_SHA','PENDING'), ('SOURCE_REF','PENDING'),
                            ('INVENTORY_PATH','PENDING'), ('INVENTORY_SHA256','PENDING'),
                            ('EXPECTED_COUNTS',(4,'PENDING')), ('EXPECTED_COUNTS',(4,None)),
                            ('EXPECTED_COUNTS',(4,True)), ('EXPECTED_COUNTS',(3,7)),
                            ('EXPECTED_COUNTS',(4,)), ('EXPECTED_COUNTS',(4,0)),
                            ('EXPECTED_COUNTS',(4,129)), ('EXPECTED_COUNTS',(True,16)),
                            ('EXPECTED_COUNTS',(4,16.0)), ('EXPECTED_COUNTS',[4,16]),
                            ('REVIEWED_BOUNDARY_COUNT',None), ('REVIEWED_BOUNDARY_COUNT',True),
                            ('REVIEWED_BOUNDARY_COUNT',0), ('REVIEWED_BOUNDARY_COUNT',129),
                            ('REVIEWED_BOUNDARY_COUNT',16.0), ('REVIEWED_BOUNDARY_COUNT',8),
                            ('SOURCE_REF','refs/tags/synthetic'), ('SOURCE_SHA','a'*39),
                            ('INVENTORY_SHA256','b'*63),
                            ('INVENTORY_PATH','tool/unreviewed/green_inventory.json'),
                            ('INVENTORY_PATH','../synthetic/green_inventory.json'),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40)),
                            ('REQUEST',dict(c.REQUEST,source_ref='refs/heads/fix/other')),
                            ('REQUEST',{})]:
            with self.subTest(field=field,value=value), self.pins(), patch.object(c,field,value), \
                    patch.object(c.previous,'main') as delegated, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1); delegated.assert_not_called()

    def test_all254_retained_in_exact_order_then_both_new_suites(self):
        prior=self.prior(); extra=self.extra(); before=copy.deepcopy(prior)
        with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                patch.object(c.TIMING,'component_inventory',return_value=extra) as load:
            actual=c.inventory(Path('/synthetic'))
            load.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(4,16))
        self.assertEqual(actual,prior+extra); self.assertEqual(actual[:33],prior)
        self.assertIs(actual[0],prior[0])  # Preserve Broadcast-first order.
        self.assertEqual(len(actual),35); self.assertEqual(sum(len(s['names']) for s in actual),274)
        self.assertEqual(len({name for suite in actual for name in suite['names']}),274)
        self.assertEqual(prior,before)

    def test_missing_changed_duplicate_cases_fail(self):
        for prior, extra in [(self.prior()[:-1],self.extra()),
                            (self.prior(),suites((4,6),'extra')),
                            (self.prior(),suites((11,),'extra')),
                            (self.prior(),suites((4,16),'prior')),
                            (self.prior()[:-1]+[self.prior()[20]],self.extra()),
                            (self.prior(),self.extra()[:1]),
                            (self.prior(),suites((16,4),'extra')),
                            (self.prior(),[dict(s,path='test/services/duplicate_test.dart') for s in self.extra()]),
                            (self.prior(),[dict(s,names=[s['names'][0]]*len(s['names'])) for s in self.extra()])]:
            with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                    patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))
        prior=self.prior(); prior[0]['names'][-1]=prior[0]['names'][0]
        with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                patch.object(c.TIMING,'component_inventory') as load:
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))
            load.assert_not_called()

    def test_manifest_or_fixture_hash_failure_remains_fatal(self):
        with self.pins(), patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()), \
                patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))

    def materialize(self, source, mutation=None):
        extra=self.extra()
        for suite in extra:
            target=source/suite['path']; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('Synthetic fixture only: '+suite['path'])
            suite['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        if mutation: mutation(extra)
        target=source/c.INVENTORY_PATH; target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'suites':extra}))
        return hashlib.sha256(target.read_bytes()).hexdigest()

    def test_real_component_loader_validates_exact_manifest_and_both_fixture_hashes(self):
        for changed in (None,'inventory',0,1):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as d:
                source=Path(d); digest=self.materialize(source)
                if changed=='inventory': (source/c.INVENTORY_PATH).write_text('{}')
                elif type(changed) is int: (source/self.extra()[changed]['path']).write_text('Changed')
                with self.pins(), patch.object(c,'INVENTORY_SHA256',digest), \
                        patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()):
                    if changed is None:
                        actual=c.inventory(source)
                        self.assertEqual([s['names'] for s in actual[-2:]], [s['names'] for s in self.extra()])
                    else:
                        with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(source)

    def test_real_component_loader_rejects_counts_duplicates_ordinal_and_wrong_paths(self):
        mutations=(lambda s:s[0].update(causalOrdinal=1), lambda s:s.pop(),
                   lambda s:s[0]['names'].pop(), lambda s:s[1]['names'].pop(),
                   lambda s:s[0].update(names=[s[0]['names'][0]]*4),
                   lambda s:s[1].update(path=s[0]['path'],sha256=s[0]['sha256']),
                   lambda s:s[0].update(path='../outside_test.dart'),
                   lambda s:s[0].update(path='test/other/synthetic_test.dart'))
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                source=Path(d); digest=self.materialize(source,mutation)
                with self.pins(), patch.object(c,'INVENTORY_SHA256',digest), \
                        patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()):
                    with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(source)

    def test_nested_overrides_full_acceptance_and_restoration(self):
        ingress=c.TIMING.previous; lowest=ingress.recovery
        fractional=c.previous.previous; receipt=fractional.previous
        directional=receipt.directional; restore=directional.restore; clock=directional.CLOCK
        names=('PARENT','MESSAGE','WORKFLOW','REQUEST_PATH','REQUEST','SOURCE_REF','SOURCE_SHA','SERVER_SHA')
        tracked=[(module,name) for module in (lowest,c.previous,fractional,receipt) for name in (*names,'inventory')]
        tracked += [(c.previous,'INVENTORY_PATH'),(c.previous,'INVENTORY_SHA256'),(c.previous,'EXPECTED_COUNTS'),
                    (fractional,'INVENTORY_PATH'),(fractional,'INVENTORY_SHA256'),(fractional,'EXPECTED_COUNTS'),
                    (receipt,'DIRECTIONAL_INVENTORY_SHA256'),(receipt.diagnostic,'FIXTURE_SHA256'),
                    (directional,'INVENTORY_SHA256'),(restore,'COMPONENTS'),
                    (ingress,'RECOVERY_INVENTORY_SHA256'),(lowest,'INVENTORY_SHA256'),
                    (ingress.ingress,'INVENTORY_SHA256'),(lowest,'observe_green'),
                    (lowest,'full_test_observation'),(lowest,'validate_full'),
                    (lowest,'observe_negative_nominal'),(lowest,'observe_samples')]
        original=[getattr(module,name) for module,name in tracked]
        original_observer=lowest.observe_green; original_full=lowest.validate_full
        diagnostics=(lowest.observe_negative_nominal,lowest.observe_samples)
        for stage in ('focused','validate_source'):
            for fails in (False,True):
                def observe():
                    for name in names: self.assertEqual(getattr(lowest,name),getattr(c,name))
                    self.assertIs(lowest.inventory,c.inventory)
                    self.assertEqual(c.previous.INVENTORY_PATH,'tool/follow_initial_apply_receipt/green_inventory.json')
                    self.assertEqual(c.previous.INVENTORY_SHA256,'5628a0ea2f6781ad78ed816f5e17f96157f0da9fb3a663be14f8b634d90b2306')
                    self.assertEqual(c.previous.EXPECTED_COUNTS,(3,8))
                    self.assertEqual(fractional.INVENTORY_PATH,'tool/follow_fractional_precision/green_inventory.json')
                    self.assertEqual(fractional.INVENTORY_SHA256,'9b1fcd4288a1993f2334228184fdecd54ba97911af726d2d682d4424f4681c3e')
                    self.assertEqual(fractional.EXPECTED_COUNTS,(3,4))
                    self.assertEqual(receipt.DIRECTIONAL_INVENTORY_SHA256,fractional.DIRECTIONAL_INVENTORY_SHA256)
                    self.assertEqual(receipt.diagnostic.FIXTURE_SHA256,fractional.DIAGNOSTIC_FIXTURE_SHA256)
                    self.assertEqual(directional.INVENTORY_SHA256,receipt.previous.DIRECTIONAL_INVENTORY_SHA256)
                    self.assertEqual(restore.COMPONENTS,((directional.POST_RESTORE_PATH,directional.POST_RESTORE_DIGEST,(4,6)),))
                    self.assertEqual(ingress.RECOVERY_INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(lowest.INVENTORY_SHA256,clock.RECOVERY_DIGEST)
                    self.assertEqual(ingress.ingress.INVENTORY_SHA256,ingress.INGRESS_INVENTORY_SHA256)
                    self.assertIs(lowest.full_test_observation,ingress.dispatch_full_observation)
                    self.assertIs(lowest.observe_green,ingress.focused_observation if stage=='focused' else original_observer)
                    self.assertIs(lowest.validate_full,original_full)
                    self.assertEqual((lowest.observe_negative_nominal,lowest.observe_samples),diagnostics)
                    self.assertEqual(lowest.ANALYZE_COMMAND,('flutter','analyze','--no-pub','--fatal-infos','--fatal-warnings'))
                    self.assertEqual(lowest.FULL_TEST_COMMAND,('flutter','test','--no-pub','--reporter=json'))
                    if fails: raise RuntimeError('synthetic')
                    return 7
                with self.subTest(stage=stage,fails=fails), self.pins(), \
                        patch.object(sys,'argv',['gate','source',stage]), patch.object(lowest,'main',side_effect=observe):
                    if fails:
                        with self.assertRaises(RuntimeError): c.main()
                    else: self.assertEqual(c.main(),7)
                self.assertEqual([getattr(module,name) for module,name in tracked],original)

    def test_full_historical_composition_keeps_broadcast_first_and_every_component(self):
        fractional=c.previous.previous; receipt=fractional.previous
        directional=receipt.directional; clock=receipt.CLOCK
        base=suites((3,45,13,6,3,34,18,17,7,2,3,1,4,6),'base')
        before=copy.deepcopy(base); original_components=c.TIMING.COMPONENTS
        rows=(
            (clock.INTERVAL_PATH,clock.INTERVAL_DIGEST,(6,7),'clock'),
            (directional.previous.INVENTORY_PATH,directional.previous.INVENTORY_SHA256,(3,4),'admission'),
            (directional.INVENTORY_PATH,fractional.DIRECTIONAL_INVENTORY_SHA256,(4,4),'directional'),
            (receipt.ordinary.INVENTORY_PATH,receipt.ordinary.INVENTORY_SHA256,(4,4),'ordinary'),
            (receipt.broadcast.INVENTORY_PATH,receipt.broadcast.INVENTORY_SHA256,(15,),'broadcast'),
            (receipt.convergence.INVENTORY_PATH,receipt.convergence.INVENTORY_SHA256,(3,5),'convergence'),
            (receipt.previous.INVENTORY_PATH,receipt.previous.INVENTORY_SHA256,(3,5),'rate'),
            (receipt.INVENTORY_PATH,receipt.INVENTORY_SHA256,(3,4),'receipt'),
            (fractional.INVENTORY_PATH,fractional.INVENTORY_SHA256,(3,4),'fractional'),
            (c.previous.INVENTORY_PATH,c.previous.INVENTORY_SHA256,(3,8),'initial'),
            (c.INVENTORY_PATH,'b'*64,(4,16),'settlement'),
        )
        loaded={path:suites(counts,prefix) for path,_,counts,prefix in rows}
        def original(source):
            self.assertEqual(source,Path('/synthetic'))
            self.assertEqual(c.TIMING.COMPONENTS,tuple(
                (p,clock.CLOCK_DIGEST if p==clock.CLOCK_PATH else h,n)
                for p,h,n in original_components))
            self.assertEqual(directional.restore.COMPONENTS,
                ((directional.POST_RESTORE_PATH,directional.POST_RESTORE_DIGEST,(4,6)),))
            return base
        def load(source,path,digest,counts):
            self.assertEqual(source,Path('/synthetic'))
            expected=next(row for row in rows if row[0]==path)
            self.assertEqual((digest,counts),expected[1:3])
            return loaded[path]
        def delegate():
            actual=c.TIMING.previous.recovery.inventory(Path('/synthetic'))
            expected=[*loaded[receipt.broadcast.INVENTORY_PATH],*base]
            for path,_,_,_ in rows:
                if path!=receipt.broadcast.INVENTORY_PATH: expected+=loaded[path]
            self.assertEqual(actual,expected)
            self.assertEqual(len(actual),35)
            self.assertEqual(sum(len(s['names']) for s in actual),274)
            self.assertEqual(len({name for suite in actual for name in suite['names']}),274)
            return 0
        with self.pins(), patch.object(sys,'argv',['gate','source','focused']), \
                patch.object(receipt,'BASE_INVENTORY',side_effect=original), \
                patch.object(c.TIMING,'component_inventory',side_effect=load) as loader, \
                patch.object(c.TIMING.previous.recovery,'main',side_effect=delegate):
            self.assertEqual(c.main(),0)
            self.assertEqual([call.args[1] for call in loader.call_args_list],[row[0] for row in rows])
        self.assertEqual(base,before)
        self.assertEqual(c.TIMING.COMPONENTS,original_components)

    def test_exact_reviewed_count_rejects_any_other_count(self):
        for first in (1,2,3,5,True):
            with self.pins(), patch.object(c,'EXPECTED_COUNTS',(first,16)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()
        for second in range(1,129):
            if second==SYNTHETIC_BOUNDARY_COUNT: continue
            with self.pins(), patch.object(c,'EXPECTED_COUNTS',(4,second)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()
            with self.pins(), patch.multiple(c, REVIEWED_BOUNDARY_COUNT=second, EXPECTED_COUNTS=(4,second)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()

    def test_fixed_baseline_and_reviewed_contract(self):
        self.assertEqual(c.PARENT,'82243ad915ce3e028f074f667295dc8b9113ec83')
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.REQUEST['attempt'],104)
        self.assertEqual(c.REQUEST['mode'],'follow-ordinary-settlement-full-green-validation')
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_smooth_settlement/green_inventory.json')
        self.assertIs(c.ORIGINAL_INVENTORY,c.previous.inventory)
        self.assertEqual(c.REVIEWED_BOUNDARY_COUNT,16)
        self.assertEqual(c.EXPECTED_COUNTS,(4,16))
        self.assertEqual(c.SOURCE_REF,'refs/heads/fix/follow-ordinary-settlement-20261024')
        self.assertEqual(c.SOURCE_SHA,'7a6467b6f66f17f1a58127d9c6ad4debad4983bc')
        self.assertEqual(c.INVENTORY_SHA256,'7b05327f397df0dd74fb8dd751a9f6a85b6716278679fc6ca814ed0590997ff7')
        with patch.object(c,'SOURCE_SHA','PENDING'), patch.object(c.previous,'main') as delegated, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(c.main(),1); delegated.assert_not_called()

    def test_native_package_publish_build_and_red_stages_forbidden(self):
        lowest=c.TIMING.previous.recovery
        for args in (['gate','native','run'],['gate','source','native'],
                     ['gate','source','package'],['gate','source','publish'],['gate','source','red'],
                     ['gate','source','build'],['gate','source','build_windows'],['gate','source','verify']):
            with self.subTest(args=args), self.pins(), patch.object(sys,'argv',args), \
                    patch.object(lowest.request,'context') as context, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1); context.assert_not_called()

    def test_workflow_preserves_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1]; text=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH): self.assertIn(value,text)
        for value in ('contents: read','source focused','source validate_source','if: always()',
                      'source cleanup','persist-credentials: false'): self.assertIn(value,text)
        for value in ('upload-artifact','source native','source package','source publish','source build',
                      'contents: write','workflow_dispatch','continue-on-error','RELEASE_WRITE_TOKEN','macos-'): self.assertNotIn(value,text)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertLess(text.index('source focused'),text.index('source validate_source'))
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',text)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',text)
        self.assertIn("flutter-version: '3.41.2'",text)
        for stage in ('prepare','fetch','focused','validate_source','cleanup'):
            self.assertIn('follow_ordinary_settle_green.py source '+stage,text)


if __name__=='__main__': unittest.main()
