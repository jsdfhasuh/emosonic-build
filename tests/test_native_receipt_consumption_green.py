import contextlib
import copy
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
                 names=['synthetic_%s_%d_%d' % (prefix,i,j) for j in range(n)]) for i,n in enumerate(counts)]


class NativeReceiptConsumptionGreenTests(unittest.TestCase):
    @contextlib.contextmanager
    def pins(self):
        with patch.multiple(c,SOURCE_SHA='a'*40,SOURCE_REF='refs/heads/fix/synthetic',
                INVENTORY_SHA256='b'*64,DIRECTIONAL_INVENTORY_SHA256='c'*64,EXPECTED_COUNTS=(3,4),
                REQUEST=dict(c.REQUEST,source_sha='a'*40,source_ref='refs/heads/fix/synthetic')), \
                patch.object(c.diagnostic,'FIXTURE_SHA256','d'*64):
            yield

    def base(self):
        return suites((3,45,13,6,3,34,18,17,7,2,3,1,4,6),'base')

    def components(self):
        return (
            (c.CLOCK.INTERVAL_PATH,c.CLOCK.INTERVAL_DIGEST,(6,7),'clock'),
            (c.directional.previous.INVENTORY_PATH,c.directional.previous.INVENTORY_SHA256,(3,4),'admission'),
            (c.directional.INVENTORY_PATH,'c'*64,(4,4),'directional'),
            (c.ordinary.INVENTORY_PATH,c.ordinary.INVENTORY_SHA256,(4,4),'ordinary'),
            (c.broadcast.INVENTORY_PATH,c.broadcast.INVENTORY_SHA256,(15,),'broadcast'),
            (c.convergence.INVENTORY_PATH,c.convergence.INVENTORY_SHA256,(3,5),'convergence'),
            (c.previous.INVENTORY_PATH,c.previous.INVENTORY_SHA256,(3,5),'rate'),
            (c.INVENTORY_PATH,'b'*64,(3,4),'receipt'),
        )

    def natural_scope(self):
        return patch.object(c.directional.restore,'COMPONENTS',
            ((c.directional.POST_RESTORE_PATH,c.directional.POST_RESTORE_DIGEST,(4,6)),))

    def test_pending_invalid_inconsistent_pins_fail_before_delegation(self):
        for field,value in [('SOURCE_SHA','PENDING'),('SOURCE_REF','PENDING'),
                            ('INVENTORY_SHA256','PENDING'),('DIRECTIONAL_INVENTORY_SHA256','PENDING'),
                            ('EXPECTED_COUNTS',(3,None)),('EXPECTED_COUNTS',(3,True)),
                            ('EXPECTED_COUNTS',(4,4)),('EXPECTED_COUNTS',(3,)),
                            ('EXPECTED_COUNTS',(3,0)),('EXPECTED_COUNTS',(3,1001)),
                            ('EXPECTED_COUNTS',(True,4)),('EXPECTED_COUNTS',(3,4.0)),
                            ('EXPECTED_COUNTS',[3,4]),('EXPECTED_COUNTS',(3,'PENDING')),
                            ('SOURCE_REF','refs/tags/synthetic'),('SOURCE_SHA','a'*39),
                            ('INVENTORY_SHA256','b'*63),('DIRECTIONAL_INVENTORY_SHA256','c'*63),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.subTest(field=field,value=value),self.pins(),patch.object(c,field,value),patch.object(c.previous,'main') as call,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);call.assert_not_called()
        with self.pins(),patch.object(c.diagnostic,'FIXTURE_SHA256','PENDING'),patch.object(c.previous,'main') as call,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(c.main(),1);call.assert_not_called()

    def test_all236_names_complete_and_exact_order_with_broadcast_first(self):
        prior=self.base();before=copy.deepcopy(prior);original=c.TIMING.COMPONENTS
        components=self.components();loaded={path:suites(counts,prefix) for path,_,counts,prefix in components}
        def base(source):
            self.assertEqual(c.TIMING.COMPONENTS,tuple((p,c.CLOCK.CLOCK_DIGEST if p==c.CLOCK.CLOCK_PATH else h,n) for p,h,n in original))
            return prior
        def load(source,path,digest,counts):
            self.assertEqual(source,Path('/synthetic'))
            expected=next(row for row in components if row[0]==path)
            self.assertEqual((digest,counts),expected[1:3])
            return loaded[path]
        with self.pins(),self.natural_scope(),patch.object(c,'BASE_INVENTORY',side_effect=base),patch.object(c.TIMING,'component_inventory',side_effect=load) as loader:
            actual=c.inventory(Path('/synthetic'))
        expected=[*loaded[c.broadcast.INVENTORY_PATH],*prior]
        for path,_,_,_ in components:
            if path!=c.broadcast.INVENTORY_PATH:expected+=loaded[path]
        self.assertEqual(actual,expected);self.assertEqual(len(actual),29)
        self.assertEqual(sum(len(s['names']) for s in actual),236)
        self.assertEqual(len({name for suite in actual for name in suite['names']}),236)
        self.assertEqual([call.args[1] for call in loader.call_args_list],[row[0] for row in components])
        boundary=loaded[c.directional.INVENTORY_PATH][1]
        self.assertEqual(len(next(s for s in actual if s['path']==boundary['path'])['names']),4)
        self.assertEqual(prior,before);self.assertEqual(c.TIMING.COMPONENTS,original)

    def test_missing_changed_duplicate_cases_and_paths_fail(self):
        for mode in ('missing-base','duplicate-base','changed-base','missing-component',
                     'changed-count','missing-fourth','duplicate-path','overlap-base','duplicate-name'):
            prior=self.base();loaded={p:suites(n,prefix) for p,_,n,prefix in self.components()}
            directional=loaded[c.directional.INVENTORY_PATH]
            if mode=='missing-base':prior.pop()
            elif mode=='duplicate-base':prior[4]=prior[0]
            elif mode=='changed-base':prior[0]['names'].pop()
            elif mode=='missing-component':directional.pop()
            elif mode=='changed-count':directional[0]['names'].pop()
            elif mode=='missing-fourth':directional[1]['names'].pop()
            elif mode=='duplicate-path':directional[1]['path']=directional[0]['path']
            elif mode=='overlap-base':directional[1]['path']=prior[0]['path']
            else:directional[1]['names'][-1]=directional[1]['names'][0]
            with self.subTest(mode=mode),self.pins(),self.natural_scope(),patch.object(c,'BASE_INVENTORY',return_value=prior),patch.object(c.TIMING,'component_inventory',side_effect=lambda source,path,digest,counts:loaded[path]):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_every_manifest_failure_remains_fatal_without_later_components(self):
        for failed in range(8):
            calls=[];components=self.components()
            def load(source,path,digest,counts):
                calls.append(path)
                if len(calls)==failed+1:raise c.TIMING.previous.recovery.request.p.GateError('changed fixture')
                return suites(counts,components[len(calls)-1][3])
            with self.subTest(failed=failed),self.pins(),self.natural_scope(),patch.object(c,'BASE_INVENTORY',return_value=self.base()),patch.object(c.TIMING,'component_inventory',side_effect=load):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
            self.assertEqual(calls,[row[0] for row in components[:failed+1]])

    def test_required_scoped_overrides_and_exception_restoration(self):
        original=c.TIMING.COMPONENTS
        for components in ((),original+tuple(row for row in original if row[0]==c.CLOCK.CLOCK_PATH)):
            with self.pins(),self.natural_scope(),patch.object(c.TIMING,'COMPONENTS',components),patch.object(c,'BASE_INVENTORY') as base:
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
                base.assert_not_called()
        with self.pins(),patch.object(c.directional.restore,'COMPONENTS',()),patch.object(c,'BASE_INVENTORY') as base:
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
            base.assert_not_called()
        with self.pins(),self.natural_scope(),patch.object(c,'BASE_INVENTORY',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):c.inventory(Path('/synthetic'))
        self.assertEqual(c.TIMING.COMPONENTS,original)

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

    def test_exact_fixed_contract_rejects_any_other_boundary_count(self):
        self.assertEqual(c.PARENT,'588cfc638101528925ed41f3af6c0f9ecaef1820')
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.REQUEST['attempt'],84)
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_native_receipt_consumption/green_inventory.json')
        self.assertEqual(c.EXPECTED_COUNTS,(3,4))
        for count in (1,2,3,5,1000):
            with self.pins(),patch.object(c,'EXPECTED_COUNTS',(3,count)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.require_counts()

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
        self.assertEqual(c.REQUEST['attempt'],84)
        self.assertLess(w.index('source focused'),w.index('source validate_source'))
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',w)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',w)
        self.assertIn("flutter-version: '3.41.2'",w)
        for stage in ('prepare','fetch','focused','validate_source','cleanup'):
            self.assertIn('native_receipt_consumption_green.py source '+stage,w)


if __name__=='__main__':unittest.main()
