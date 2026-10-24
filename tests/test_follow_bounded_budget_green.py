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
import follow_bounded_budget_green as c


COUNTS = (15,3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,4,4,4,3,5,3,5,3,4,3,4,3,8,4,17)
# Unrelated fixture paths and every test name stay synthetic in public tests.
PATHS = tuple({
    2: 'test/services/emo_follow_post_seek_recovery_test.dart',
    13: 'test/services/emo_follow_nominal_restore_boundary_test.dart',
    14: 'test/services/emo_follow_nominal_restore_verification_test.dart',
    17: 'test/services/emo_follow_anchor_admission_gap_test.dart',
    18: 'test/services/emo_follow_anchor_admission_boundary_test.dart',
    19: 'test/services/emo_follow_directional_settle_test.dart',
    20: 'test/services/emo_follow_directional_boundary_test.dart',
    27: 'test/services/emo_follow_native_receipt_consumption_test.dart',
    28: 'test/services/emo_follow_native_receipt_wake_boundary_test.dart',
    29: 'test/services/emo_follow_fractional_precision_test.dart',
    34: 'test/services/emo_follow_smooth_settlement_boundary_test.dart',
}.get(i, 'test/services/synthetic_prior_%d_test.dart' % i) for i in range(35))


def synthetic_suites(paths, counts):
    return [dict(path=path, sha256=hashlib.sha256(path.encode()).hexdigest(),
                 names=['synthetic_%d_%d' % (i,j) for j in range(count)])
            for i,(path,count) in enumerate(zip(paths, counts))]


class BoundedBudgetGreenTests(unittest.TestCase):
    def test_fixed_reviewed_contract_and_only_scoped_pin_targets(self):
        self.assertEqual(c.PARENT,'a65819318279f53c06fd8d19794959c39d6b00e8')
        self.assertEqual(c.SERVER_SHA,'5adc23da173c5f20188d79aafe8fcc1e656eb38a')
        self.assertEqual(c.REQUEST['attempt'],112)
        self.assertEqual(c.REQUEST['mode'],'follow-bounded-budget-full-green-validation')
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_bounded_budget/green_inventory.json')
        self.assertEqual(c.EXPECTED_COUNTS,(4,3))
        self.assertIs(c.ORIGINAL_INVENTORY,c.previous.inventory)
        self.assertEqual(c.PRIOR_NAMES_SHA256,'d96bc2a64d8f1b8b78e30bed4aef60922686418d1a18712a2b31cbca2fd7d3a9')
        self.assertEqual(c.FROZEN_PRIOR_SHA256,'c0ddcbb15a9bda247129ab55307903b13307c0226b4aba0f2c7e822ff6371586')
        self.assertEqual(c.BUDGET_BASELINE_SHA256,'98dbc33717f6f9b33b4c85d007046f63406b7992d729f02fa2fbbc2ecea03580')
        self.assertEqual(c.RENAMED_CASE,(
            'test/services/emo_follow_nominal_restore_verification_test.dart',
            '31ecc7c0826098dfaf9800056a8ec3d9e7364cd313c2f0ce91146b91e6e5ac07',
            '34f557936588019499483320f414fa277dbbd08e3129f3cd87e96496be81e596'))
        self.assertEqual(len(c.PIN_TARGETS),7)
        self.assertEqual(len({(m.__name__,a) for _,m,a,_ in c.PIN_TARGETS}),7)
        self.assertEqual({p for p,_,_,_ in c.PIN_TARGETS},set(c.REVIEWED_MANIFEST_SHA256))
        self.assertEqual(len(set(c.CHANGED_PRIOR_PATHS)),11)
        self.assertEqual(len(c.CHANGED_PRIOR_PATHS),11)
        self.assertEqual(set(c.CHANGED_PRIOR_PATHS),
            {PATHS[i] for i in (2,13,14,17,18,19,20,27,28,29,34)})

    def test_every_other_budget_count_is_rejected(self):
        for first in (True,1,2,3,5,128):
            with patch.object(c,'EXPECTED_COUNTS',(first,3)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()
        for second in range(1,129):
            if second==3: continue
            with patch.object(c,'EXPECTED_COUNTS',(4,second)):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.require_counts()

    def prior(self):
        value = synthetic_suites(PATHS, COUNTS)
        value[14]['names'][5] = 'synthetic new policy name'
        return value

    def extra(self):
        value = synthetic_suites((c.BUDGET_BASELINE_PATH,
            'test/services/emo_follow_bounded_budget_boundary_test.dart'), (4,3))
        for i,suite in enumerate(value):
            suite['names'] = ['budget_%d_%d' % (i,j) for j in range(len(suite['names']))]
        value[0]['sha256'] = c.BUDGET_BASELINE_SHA256
        return value

    @contextlib.contextmanager
    def synthetic_contract(self):
        prior = self.prior()
        old = copy.deepcopy(prior)
        old[14]['names'][5] = 'synthetic old policy name'
        names = [[s['path'], [c.name_hash(n) for n in s['names']]] for s in old]
        frozen = [[s['path'],s['sha256']] for s in old if s['path'] not in c.CHANGED_PRIOR_PATHS]
        with patch.multiple(c, PRIOR_NAMES_SHA256=c.digest(names), FROZEN_PRIOR_SHA256=c.digest(frozen),
                RENAMED_CASE=(PATHS[14],c.name_hash('synthetic old policy name'),c.name_hash('synthetic new policy name'))):
            yield

    def test_invalid_pins_fail_before_delegation_and_do_not_change_historical_owners(self):
        mutations = [('SOURCE_SHA','PENDING'),('SOURCE_SHA','a'*39),
            ('SOURCE_REF','refs/tags/synthetic'),('SOURCE_REF','PENDING'),
            ('INVENTORY_PATH','tool/unreviewed/green_inventory.json'),
            ('INVENTORY_SHA256','PENDING'),('INVENTORY_SHA256','b'*63),
            ('DIAGNOSTIC_FIXTURE_SHA256','PENDING'),
            ('DIAGNOSTIC_FIXTURE_SHA256',c.ORIGINAL_DIAGNOSTIC_SHA256),
            ('REVIEWED_MANIFEST_SHA256',{}),('REVIEWED_MANIFEST_SHA256',[]),
            ('EXPECTED_COUNTS',(4,2)),('EXPECTED_COUNTS',(4,True)),
            ('EXPECTED_COUNTS',(4,3.0)),('EXPECTED_COUNTS',[4,3]),
            ('RENAMED_CASE',()),('RENAMED_CASE',(PATHS[14],'a'*64,'a'*64)),
            ('REQUEST',dict(c.REQUEST,source_sha='a'*40)),
            ('REQUEST',dict(c.REQUEST,source_ref='refs/heads/fix/other')),('REQUEST',{})]
        first = c.PIN_TARGETS[0]
        for replacement in ('PENDING', first[3]):
            values = dict(c.REVIEWED_MANIFEST_SHA256); values[first[0]] = replacement
            mutations.append(('REVIEWED_MANIFEST_SHA256',values))
        values = dict(c.REVIEWED_MANIFEST_SHA256); values['tool/unreviewed/green_inventory.json']='a'*64
        mutations.append(('REVIEWED_MANIFEST_SHA256',values))
        original = [getattr(m,a) for _,m,a,_ in c.PIN_TARGETS]
        for field,value in mutations:
            with self.subTest(field=field,value=value),patch.object(c,field,value), \
                    patch.object(c.previous,'main') as called,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1); called.assert_not_called()
            self.assertEqual([getattr(m,a) for _,m,a,_ in c.PIN_TARGETS],original)

    def test_every_historical_owner_is_checked_before_any_override(self):
        targets = [(m,a) for _,m,a,_ in c.PIN_TARGETS]+[(c.fractional,'DIAGNOSTIC_FIXTURE_SHA256')]
        for module,field in targets:
            with self.subTest(module=module.__name__,field=field),patch.object(module,field,'a'*64), \
                    patch.object(c.previous,'main') as called,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1); called.assert_not_called()

    def test_all275_then_frozen4_and_new3_keep_order_and_input_unchanged(self):
        prior=self.prior(); extra=self.extra(); before=copy.deepcopy(prior)
        with self.synthetic_contract(),patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                patch.object(c.TIMING,'component_inventory',return_value=extra) as loader:
            actual=c.inventory(Path('/synthetic'))
        self.assertEqual(actual,prior+extra); self.assertEqual(actual[:35],prior)
        self.assertIs(actual[0],prior[0]); self.assertEqual(prior,before)
        self.assertEqual((len(actual),sum(len(s['names']) for s in actual)),(37,282))
        loader.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,c.INVENTORY_SHA256,(4,3))

    def test_every_unauthorized_prior_name_path_order_and_hash_change_is_fatal(self):
        for mode in ('remove-suite','remove-case','duplicate-case','rename-unrelated','restore-old-name',
                     'swap-order','change-path','change-frozen-sha','change-frozen-four','change-slew-helper'):
            prior=self.prior()
            if mode=='remove-suite': prior.pop()
            elif mode=='remove-case': prior[0]['names'].pop()
            elif mode=='duplicate-case': prior[0]['names'][-1]=prior[0]['names'][0]
            elif mode=='rename-unrelated': prior[2]['names'][0]='unreviewed name'
            elif mode=='restore-old-name': prior[14]['names'][5]='synthetic old policy name'
            elif mode=='swap-order': prior[0],prior[1]=prior[1],prior[0]
            elif mode=='change-path': prior[2]['path']='test/services/unreviewed_test.dart'
            elif mode=='change-frozen-sha': prior[1]['sha256']='a'*64
            elif mode=='change-frozen-four': prior[33]['sha256']='a'*64
            else: prior[21]['sha256']='a'*64
            with self.subTest(mode=mode),self.synthetic_contract(), \
                    patch.object(c,'ORIGINAL_INVENTORY',return_value=prior), \
                    patch.object(c.TIMING,'component_inventory') as loader:
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))
                loader.assert_not_called()

    def test_incomplete_reordered_overlapping_or_modified_budget_suites_are_fatal(self):
        for mode in ('remove-suite','wrong-count','reorder','overlap','duplicate-name','change-frozen-baseline'):
            extra=self.extra()
            if mode=='remove-suite': extra.pop()
            elif mode=='wrong-count': extra[1]['names'].pop()
            elif mode=='reorder': extra.reverse()
            elif mode=='overlap': extra[1]['path']=PATHS[0]
            elif mode=='duplicate-name': extra[1]['names'][0]=extra[0]['names'][0]
            else: extra[0]['sha256']='a'*64
            with self.subTest(mode=mode),self.synthetic_contract(), \
                    patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()), \
                    patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))

    def test_real_component_loader_checks_manifest_and_both_fixture_hashes(self):
        for changed in (None,'inventory',0,1):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as d:
                source=Path(d); extra=self.extra()
                for suite in extra:
                    file=source/suite['path']; file.parent.mkdir(parents=True,exist_ok=True)
                    file.write_text('Synthetic fixture only: '+suite['path'])
                    suite['sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
                manifest=source/c.INVENTORY_PATH; manifest.parent.mkdir(parents=True)
                manifest.write_text(json.dumps({'suites':extra}))
                digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
                if changed=='inventory': manifest.write_text('{}')
                elif type(changed) is int: (source/extra[changed]['path']).write_text('Changed')
                with self.synthetic_contract(),patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()), \
                        patch.multiple(c,INVENTORY_SHA256=digest,BUDGET_BASELINE_SHA256=extra[0]['sha256']):
                    if changed is None: self.assertEqual(c.inventory(source)[-2:],extra)
                    else:
                        with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(source)

    def test_scoped_effective_pins_full_acceptance_and_exception_restoration(self):
        ingress=c.TIMING.previous; lowest=ingress.recovery
        names=('PARENT','MESSAGE','WORKFLOW','REQUEST_PATH','REQUEST','SOURCE_REF','SOURCE_SHA','SERVER_SHA')
        tracked=[(m,a) for _,m,a,_ in c.PIN_TARGETS]
        tracked += [(c.fractional,'DIAGNOSTIC_FIXTURE_SHA256'),(c.receipt,'DIRECTIONAL_INVENTORY_SHA256'),
            (c.receipt.diagnostic,'FIXTURE_SHA256'),(c.directional.restore,'COMPONENTS'),
            (ingress,'RECOVERY_INVENTORY_SHA256'),(lowest,'INVENTORY_SHA256')]
        tracked += [(m,a) for m in (lowest,c.previous) for a in (*names,'inventory')]
        tracked += [(lowest,a) for a in ('validate_full','verify_green','observe_green',
            'full_test_observation','observe_negative_nominal','observe_samples')]
        originals=[getattr(m,a) for m,a in tracked]
        original_observer=lowest.observe_green
        untouched=(c.TIMING.component_inventory,lowest.validate_full,lowest.verify_green,
                   lowest.observe_negative_nominal,lowest.observe_samples)
        for stage in ('focused','validate_source'):
            for fails in (False,True):
                def observe():
                    for name in names: self.assertEqual(getattr(lowest,name),getattr(c,name))
                    self.assertIs(lowest.inventory,c.inventory)
                    for path,module,field,_ in c.PIN_TARGETS:
                        self.assertEqual(getattr(module,field),c.REVIEWED_MANIFEST_SHA256[path])
                    self.assertEqual(lowest.INVENTORY_SHA256,c.REVIEWED_MANIFEST_SHA256[c.PIN_TARGETS[0][0]])
                    self.assertEqual(c.receipt.DIRECTIONAL_INVENTORY_SHA256,
                        c.REVIEWED_MANIFEST_SHA256['tool/follow_directional_settle/green_inventory.json'])
                    self.assertEqual(c.receipt.diagnostic.FIXTURE_SHA256,c.DIAGNOSTIC_FIXTURE_SHA256)
                    self.assertEqual(c.directional.restore.COMPONENTS,
                        ((c.directional.POST_RESTORE_PATH,c.directional.POST_RESTORE_DIGEST,(4,6)),))
                    self.assertEqual((c.TIMING.component_inventory,lowest.validate_full,lowest.verify_green,
                        lowest.observe_negative_nominal,lowest.observe_samples),untouched)
                    self.assertIs(lowest.full_test_observation,ingress.dispatch_full_observation)
                    self.assertIs(lowest.observe_green,
                        ingress.focused_observation if stage=='focused' else original_observer)
                    self.assertEqual(lowest.ANALYZE_COMMAND,('flutter','analyze','--no-pub','--fatal-infos','--fatal-warnings'))
                    self.assertEqual(lowest.FULL_TEST_COMMAND,('flutter','test','--no-pub','--reporter=json'))
                    if fails: raise RuntimeError('synthetic')
                    return 7
                with self.subTest(stage=stage,fails=fails),patch.object(sys,'argv',['gate','source',stage]), \
                        patch.object(lowest,'main',side_effect=observe):
                    if fails:
                        with self.assertRaises(RuntimeError): c.main()
                    else: self.assertEqual(c.main(),7)
                self.assertEqual([getattr(m,a) for m,a in tracked],originals)

    def test_entire_historical_composition_uses_every_reviewed_manifest(self):
        prior=self.prior(); extra=self.extra(); lowest=c.TIMING.previous.recovery
        components=(
            (c.clock.INTERVAL_PATH,c.clock.INTERVAL_DIGEST,(6,7),prior[15:17]),
            (c.admission.INVENTORY_PATH,c.REVIEWED_MANIFEST_SHA256[c.admission.INVENTORY_PATH],(3,4),prior[17:19]),
            (c.directional.INVENTORY_PATH,c.REVIEWED_MANIFEST_SHA256[c.directional.INVENTORY_PATH],(4,4),prior[19:21]),
            (c.receipt.ordinary.INVENTORY_PATH,c.receipt.ordinary.INVENTORY_SHA256,(4,4),prior[21:23]),
            (c.receipt.broadcast.INVENTORY_PATH,c.receipt.broadcast.INVENTORY_SHA256,(15,),prior[:1]),
            (c.receipt.convergence.INVENTORY_PATH,c.receipt.convergence.INVENTORY_SHA256,(3,5),prior[23:25]),
            (c.receipt.previous.INVENTORY_PATH,c.receipt.previous.INVENTORY_SHA256,(3,5),prior[25:27]),
            (c.receipt.INVENTORY_PATH,c.REVIEWED_MANIFEST_SHA256[c.receipt.INVENTORY_PATH],(3,4),prior[27:29]),
            (c.fractional.INVENTORY_PATH,c.REVIEWED_MANIFEST_SHA256[c.fractional.INVENTORY_PATH],(3,4),prior[29:31]),
            (c.previous.previous.INVENTORY_PATH,c.previous.previous.INVENTORY_SHA256,(3,8),prior[31:33]),
            (c.previous.INVENTORY_PATH,c.REVIEWED_MANIFEST_SHA256[c.previous.INVENTORY_PATH],(4,17),prior[33:35]),
            (c.INVENTORY_PATH,c.INVENTORY_SHA256,(4,3),extra),
        )
        calls=[]
        def load(source,path,digest,counts):
            self.assertEqual(source,Path('/synthetic')); calls.append(path)
            row=next(row for row in components if row[0]==path)
            self.assertEqual((digest,counts),row[1:3]); return row[3]
        def base(source):
            self.assertEqual(c.directional.restore.COMPONENTS,
                ((c.directional.POST_RESTORE_PATH,c.REVIEWED_MANIFEST_SHA256[c.directional.POST_RESTORE_PATH],(4,6)),))
            return prior[1:15]
        def delegate():
            self.assertEqual(lowest.inventory(Path('/synthetic')),prior+extra); return 0
        with self.synthetic_contract(),patch.object(sys,'argv',['gate','source','focused']), \
                patch.object(c.receipt,'BASE_INVENTORY',side_effect=base), \
                patch.object(c.TIMING,'component_inventory',side_effect=load),patch.object(lowest,'main',side_effect=delegate):
            self.assertEqual(c.main(),0)
        self.assertEqual(calls,[row[0] for row in components])

    def test_inherited_manifest_failures_remain_fatal(self):
        with patch.object(c,'ORIGINAL_INVENTORY',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed')), \
                patch.object(c.TIMING,'component_inventory') as loader:
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))
            loader.assert_not_called()

    def test_all_non_source_stages_are_forbidden(self):
        lowest=c.TIMING.previous.recovery
        for args in (['gate','native','run'],['gate','source','native'],['gate','source','package'],
                     ['gate','source','publish'],['gate','source','red'],['gate','source','build'],
                     ['gate','source','build_windows'],['gate','source','verify']):
            with self.subTest(args=args),patch.object(sys,'argv',args), \
                    patch.object(lowest.request,'context') as context,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(),1); context.assert_not_called()

    def test_workflow_keeps_exact_source_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH): self.assertIn(value,text)
        for value in ('contents: read','source focused','source validate_source','if: always()',
                      'source cleanup','persist-credentials: false'): self.assertIn(value,text)
        for value in ('upload-artifact','source native','source package','source publish','source build',
                      'contents: write','workflow_dispatch','continue-on-error','RELEASE_WRITE_TOKEN','macos-'):
            self.assertNotIn(value,text)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertLess(text.index('source focused'),text.index('source validate_source'))
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',text)
        self.assertIn('subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2',text)
        self.assertIn("flutter-version: '3.41.2'",text)
        for stage in ('prepare','fetch','focused','validate_source','cleanup'):
            self.assertIn('follow_bounded_budget_green.py source '+stage,text)


if __name__=='__main__': unittest.main()
