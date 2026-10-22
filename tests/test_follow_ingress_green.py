import contextlib
import hashlib
import tempfile
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_ingress_green as gate

class GreenAdapterTest(unittest.TestCase):
    def suites(self):
        return [dict(path=f'test/services/suite_{i}_test.dart', names=[f't{i}_{j}' for j in range(n)]) for i,n in enumerate((45,13,6))]

    def test_combines_exact_original_and_ingress_inventories(self):
        old=self.suites(); new=dict(path='test/services/ingress_test.dart',names=['a','b','c'])
        lifecycle=dict(path=gate.LIFECYCLE_PATH,names=['life'])
        with patch.object(gate,'RECOVERY_INVENTORY',return_value=old),patch.object(gate.ingress,'inventory',return_value=new),patch.object(gate,'lifecycle_inventory',return_value=lifecycle):
            self.assertEqual(gate.inventory(Path('/owned')),old+[new,lifecycle])

    def test_rejects_missing_original_case(self):
        old=self.suites();old[0]['names'].pop()
        with patch.object(gate,'RECOVERY_INVENTORY',return_value=old):
            with self.assertRaises(gate.recovery.request.p.GateError):gate.inventory(Path('/owned'))

    def test_rejects_duplicate_ingress_suite(self):
        old=self.suites()
        with patch.object(gate,'RECOVERY_INVENTORY',return_value=old),patch.object(gate.ingress,'inventory',return_value=old[0]):
            with self.assertRaises(gate.recovery.request.p.GateError):gate.inventory(Path('/owned'))

    def test_focused_observer_keeps_original_result(self):
        original={'exitCode':1,'errorCount':1}
        out=io.StringIO()
        with patch.object(gate,'ORIGINAL_OBSERVER',return_value=original),patch.object(gate.ingress,'phase_observation',return_value={'stage':'phase'}),patch.object(gate.ingress,'dispatch_observation',return_value={'stage':'native'}),contextlib.redirect_stdout(out):
            self.assertIs(gate.focused_observation('private',1,expected_names=['a','b','c']),original)
        self.assertEqual([json.loads(x)['stage'] for x in out.getvalue().splitlines()],['phase','native'])
        self.assertNotIn('private',out.getvalue())

    def test_original_suites_get_no_ingress_projection(self):
        with patch.object(gate,'ORIGINAL_OBSERVER',return_value={}),patch.object(gate.ingress,'phase_observation') as obs:
            gate.focused_observation('',0,expected_names=['a']*45)
            obs.assert_not_called()

    def test_main_delegates_focused_acceptance_unchanged(self):
        with patch.object(sys,'argv',['gate','source','focused']),patch.object(gate.recovery,'main',return_value=7) as original:
            self.assertEqual(gate.main(),7);original.assert_called_once()

    def test_workflow_orders_focused_before_full_and_always_cleans(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/follow-ingress-green.yml').read_text()
        self.assertLess(text.index(' source focused'),text.index(' source validate_source'))
        self.assertIn('if: always()',text)
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('RELEASE_WRITE_TOKEN',text)
        self.assertNotIn('macos-',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('github.event.before ==',text)

class DispatchEvidenceTest(unittest.TestCase):
    def exercise(self, mutate=None, code=0, bad_hash=False):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory);file=source/gate.DISPATCH_PATH;file.parent.mkdir(parents=True)
            data=b"test(\n 'Synthetic case '\n 'android=$android cancel=$cancel', () {});"
            file.write_bytes(data)
            events=[{'type':'suite','suite':{'id':7,'path':str(file)}}]
            names=[f'Synthetic case android={a} cancel={c}' for a in ('false','true') for c in ('false','true')]
            for i,name in enumerate(names):
                events += [{'type':'testStart','test':{'id':i,'suiteID':7,'name':name}},
                           {'type':'testDone','testID':i,'result':'success','skipped':False,'hidden':False}]
            if mutate:mutate(events)
            output=io.StringIO();original={'malformedEvents':0,'exitCode':code}
            with patch.object(gate,'DISPATCH_SHA256','0'*64 if bad_hash else hashlib.sha256(data).hexdigest()),patch.object(gate,'ORIGINAL_FULL_OBSERVER',return_value=original),contextlib.redirect_stdout(output):
                result=gate.dispatch_full_observation('\n'.join(json.dumps(e) for e in events),'',[],source,[],code)
            self.assertIs(result,original)
            text=output.getvalue();self.assertNotIn('Synthetic',text);self.assertNotIn(directory,text)
            return json.loads(text)

    def test_all_four_actual_completions_export_only_ordinals(self):
        self.assertEqual(self.exercise()['passedOrdinals'],[1,2,3,4])

    def test_missing_completion_rejected(self):
        with self.assertRaises(gate.recovery.request.p.GateError):self.exercise(lambda e:e.pop())

    def test_skipped_hidden_failed_duplicate_or_error_rejected(self):
        mutations=[lambda e:e[-1].update(skipped=True),lambda e:e[-1].update(hidden=True),
                   lambda e:e[-1].update(result='failure'),lambda e:e.append(dict(e[-1])),
                   lambda e:e.append({'type':'error','testID':3})]
        for mutate in mutations:
            with self.subTest(mutate=mutate),self.assertRaises(gate.recovery.request.p.GateError):self.exercise(mutate)

    def test_wrong_suite_or_name_rejected(self):
        for mutate in [lambda e:e[0]['suite'].update(path='other.dart'),lambda e:e[1]['test'].update(name='unlisted')]:
            with self.subTest(mutate=mutate),self.assertRaises(gate.recovery.request.p.GateError):self.exercise(mutate)

    def test_wrong_fixture_hash_rejected(self):
        with self.assertRaises(gate.recovery.request.p.GateError):self.exercise(bad_hash=True)

    def test_failed_full_suite_keeps_original_failure_observation(self):
        self.assertFalse(self.exercise(lambda e:e.pop(),code=1)['verified'])

class LifecycleInventoryTest(unittest.TestCase):
    def exercise(self, change=None, wrong_hash=False):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory);file=source/gate.LIFECYCLE_PATH;file.parent.mkdir(parents=True);file.write_bytes(b'fixture')
            value={'suites':[{'path':gate.LIFECYCLE_PATH,'sha256':hashlib.sha256(b'fixture').hexdigest(),'names':['one','two']}]}
            if change:change(value['suites'][0])
            data=json.dumps(value).encode();path=source/gate.LIFECYCLE_INVENTORY_PATH;path.parent.mkdir(parents=True);path.write_bytes(data)
            with patch.object(gate,'LIFECYCLE_INVENTORY_SHA256','0'*64 if wrong_hash else hashlib.sha256(data).hexdigest()):return gate.lifecycle_inventory(source)

    def test_exact_private_fixture_and_names(self):self.assertEqual(self.exercise()['names'],['one','two'])

    def test_wrong_inventory_or_fixture_hash_rejected(self):
        with self.assertRaises(gate.recovery.request.p.GateError):self.exercise(wrong_hash=True)
        with self.assertRaises(gate.recovery.request.p.GateError):self.exercise(lambda s:s.update(sha256='0'*64))

    def test_wrong_path_empty_or_duplicate_names_rejected(self):
        for change in [lambda s:s.update(path='other.dart'),lambda s:s.update(names=[]),lambda s:s.update(names=['same','same'])]:
            with self.subTest(change=change),self.assertRaises(gate.recovery.request.p.GateError):self.exercise(change)

if __name__=='__main__':unittest.main()
