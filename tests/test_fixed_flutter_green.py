import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fixed_flutter_green as v

NAMES = ('private test alpha', 'private test beta')
BASE = 'owned_fixture_test.dart'


def fixture():
    events = [{'type': 'start'}, {'type': 'suite'}, {'type': 'group'}]
    for tid, name in enumerate((*NAMES, 'private lifecycle')):
        events.extend([
            {'type': 'testStart', 'test': {'id': tid, 'name': name}},
            {'type': 'print', 'message': 'secret URI/token/private code', 'testID': tid},
            {'type': 'testDone', 'testID': tid, 'result': 'success',
             'hidden': tid == 2, 'skipped': False}])
    return events + [{'type': 'done', 'success': True}]


class GreenTests(unittest.TestCase):
    def verify(self, events=None, **kw):
        raw = '\n'.join(json.dumps(e) for e in (fixture() if events is None else events))
        return v.verify_green(raw, kw.pop('returncode', 0), expected_names=kw.pop('expected_names', NAMES),
                              fixture_basename=BASE, **kw)

    def refused(self, events, reason=None, **kw):
        with self.assertRaises(v.GreenVerificationError) as caught:
            self.verify(events, **kw)
        report = caught.exception.report
        if reason:
            self.assertEqual(report['reason'], reason)
        output = str(caught.exception) + json.dumps(report)
        for secret in (*NAMES, 'secret URI', 'private lifecycle'):
            self.assertNotIn(secret, output)
        return report

    def test_exact_green_hidden_lifecycle_and_private_print(self):
        self.assertEqual(self.verify(), {'stage': 'fixed-flutter-green', 'status': 'passed',
                         'visibleTests': 2, 'hiddenTests': 1, 'completedTests': 3})

    def test_missing_extra_and_duplicate_visible(self):
        for inventory in (NAMES + ('absent',), NAMES[:1]):
            self.refused(fixture(), expected_names=inventory)
        events = fixture()
        events[6]['test']['name'] = NAMES[0]
        self.refused(events, 'duplicate-visible-test')

    def test_duplicate_start_and_completion(self):
        for index in (3, 5):
            events = fixture()
            events.insert(index + 1, copy.deepcopy(events[index]))
            self.refused(events)

    def test_unknown_boolean_and_missing_ids(self):
        for value in (True, 99, None, '0'):
            events = fixture()
            events[5]['testID'] = value
            self.refused(events, 'invalid-test-completion')

    def test_hidden_failure_skip_and_missing_completion(self):
        for key, value in (('result', 'failure'), ('result', 'error'), ('skipped', True),
                           ('skipped', 0), ('hidden', 1)):
            events = fixture()
            events[11][key] = value
            self.refused(events)
        events = fixture()
        del events[11]
        self.refused(events, 'incomplete-tests')

    def test_expected_test_must_be_visible(self):
        events = fixture()
        events[5]['hidden'] = True
        self.refused(events, 'expected-test-hidden')

    def test_error_event_even_when_all_results_pass(self):
        events = fixture()
        events.insert(-1, {'type': 'error', 'testID': 0, 'error': 'secret URI/token',
                          'stackTrace': '/private/path/' + BASE + ':25:3 secret URI'})
        report = self.refused(events, 'reporter-error')
        self.assertEqual(report['testOrdinal'], 1)
        self.assertEqual(report['fixture'], BASE)
        self.assertEqual(report['line'], 25)
        events[-2]['stackTrace'] = 'unknown_test.dart:99:3 secret URI'
        self.assertNotIn('line', self.refused(events))
        events[-2]['stackTrace'] = BASE + ':1234567:3'
        self.assertNotIn('line', self.refused(events))

    def test_terminal_missing_false_duplicate_and_trailing(self):
        self.refused(fixture()[:-1], 'missing-terminal')
        for value in (False, 1, None):
            events = fixture()
            events[-1]['success'] = value
            self.refused(events, 'terminal-not-successful')
        for extra in ({'type': 'done', 'success': True}, {'type': 'print'}):
            self.refused(fixture() + [extra], 'event-after-terminal')

    def test_process_code_nonzero_and_bool(self):
        self.refused(fixture(), 'process-failed', returncode=1)
        self.refused(fixture(), 'invalid-return-code', returncode=False)

    def test_inventory_not_stream_derived(self):
        for names in ((), ('same', 'same'), ('',), (True,), 'not-list'):
            self.refused(fixture(), 'invalid-inventory', expected_names=names)

    def test_malformed_nonfinite_duplicate_keys_and_unknown_events(self):
        for raw in ('not JSON', '[]', '{"type":"done","type":"start"}',
                    '{"type":"print","x":NaN}', '{"type":"print","x":1e999}',
                    '{"type": "untrusted"}', '{"type": []}'):
            with self.subTest(raw=raw), self.assertRaises(v.GreenVerificationError):
                v.verify_green(raw, 0, expected_names=NAMES, fixture_basename=BASE)

    def test_output_and_event_bounds(self):
        with patch.object(v, 'MAX_BYTES', 4):
            self.refused(fixture(), 'output-limit')
        with patch.object(v, 'MAX_EVENTS', 2):
            self.refused(fixture(), 'event-limit')
        self.refused(fixture(), 'output-limit', stderr='x' * (v.MAX_BYTES + 1))

    def test_known_exception_categories_and_private_unknown(self):
        for category in ('TimeoutException', 'StateError', 'RangeError',
                         'LateInitializationError', 'NoSuchMethodError',
                         'MissingPluginException', 'TestFailure', 'AssertionError'):
            events = fixture()
            events.insert(-1, {'type': 'error', 'testID': 0,
                              'error': category + ': secret URI/token'})
            report = self.refused(events, 'reporter-error')
            self.assertEqual(report['errorCategory'], category)
            self.assertEqual(report['exitCode'], 0)
        events[-2]['error'] = 'PrivateTokenStateErrorSuffix secret URI/token'
        self.assertEqual(self.refused(events)['errorCategory'], 'other')

    def test_bounded_compile_locations_are_not_assertion_results(self):
        stderr = '\n'.join('/secret/path/' + BASE + f':{n}:0: Error: private token'
                           for n in range(20))
        report = self.refused([], 'compiler-diagnostic', returncode=999999, stderr=stderr)
        self.assertEqual(report['exitCode'], 1000)
        self.assertEqual(report['fixture'], BASE)
        self.assertEqual(report['compileLocations'],
                         [{'line': n, 'column': 0} for n in range(10)])
        self.assertNotIn('errorCategory', report)
        self.assertNotIn('secret', json.dumps(report))
        with self.assertRaises(v.GreenVerificationError) as caught:
            v.verify_green(stderr, -999999, expected_names=NAMES, fixture_basename=BASE)
        self.assertEqual(caught.exception.report['reason'], 'compiler-diagnostic')
        self.assertEqual(caught.exception.report['exitCode'], -1000)
        for stderr in ('unknown_test.dart:1:2: Error: secret',
                       BASE + ':1234567:2: Error: secret',
                       BASE + ':1:1234567: Error: secret'):
            report = self.refused([], 'missing-terminal', stderr=stderr)
            self.assertNotIn('compileLocations', report)

    def test_untrusted_basename_rejected_without_echo(self):
        with self.assertRaises(v.GreenVerificationError) as caught:
            v.verify_green('', 0, expected_names=NAMES, fixture_basename='/secret/token.dart')
        self.assertNotIn('secret', str(caught.exception.report))


if __name__ == '__main__':
    unittest.main()

class ObservationTests(unittest.TestCase):
    def observe(self, events, **kwargs):
        return v.observe_green('\n'.join(json.dumps(e) for e in events), 1,
                               expected_names=NAMES, fixture_basename=BASE, **kwargs)

    def test_all_errors_and_terminal_after_first_failure(self):
        events=fixture()
        events[5]['result']='failure'
        events[8]['result']='failure'
        events.insert(-1, {'type':'error','testID':0,'isFailure':True,
                          'error':'Expected: true\n  Actual: <false>\nprivate secret',
                          'stackTrace':'package:private/' + BASE + ' 123:45 private secret'})
        events.insert(-1, {'type':'error','testID':1,'isFailure':False,
                          'error':'StateError: private secret',
                          'stackTrace':'/private/' + BASE + ':234:56'})
        events[-1]['success']=False
        report=self.observe(events)
        self.assertEqual(report['completedTests'],3)
        self.assertEqual(report['visibleTests'],2)
        self.assertEqual(report['hiddenTests'],1)
        self.assertEqual(report['results'],dict(success=1,failure=2,error=0))
        self.assertIs(report['terminalSuccess'],False)
        self.assertEqual(report['errorCount'],2)
        self.assertEqual(report['errors'][0],dict(testOrdinal=1,isFailure=True,category='assertion',
            fixture=BASE,locations=[dict(line=123,column=45)],expected=True,actual=False))
        self.assertEqual(report['errors'][1]['category'],'StateError')
        self.assertNotIn('private',json.dumps(report))
        with self.assertRaises(v.GreenVerificationError):
            v.verify_green('\n'.join(json.dumps(e) for e in events),1,expected_names=NAMES,fixture_basename=BASE)

    def test_scalar_allowlist_and_private_unknowns(self):
        for expected,actual,value1,value2 in [('null','<1.5>',None,1.5),('-20','<0>',-20,0)]:
            event={'type':'error','isFailure':True,'error':f'Expected: {expected}\nActual: {actual}'}
            error=self.observe([event])['errors'][0]
            self.assertEqual(error['expected'],value1);self.assertEqual(error['actual'],value2)
        for text in ('Expected: secret','Actual: <NaN>','Actual: <1000001>',
                     'Actual: <1> secret','prefix Expected: false','Actual: <true>\nActual: <false>',
                     'Actual: <1e999>', 'Actual: <'+'9'*4000+'>', 'Expected: "secret"'):
            report=self.observe([{'type':'error','isFailure':1,'error':text,'stackTrace':BASE+' 1234567:1'}])
            error=report['errors'][0]
            self.assertNotIn('expected',error);self.assertNotIn('actual',error)
            self.assertNotIn('isFailure',error);self.assertNotIn('locations',error)
            self.assertEqual(error['category'],'other')
            self.assertNotIn('secret',json.dumps(report))

    def test_caps_unknown_ids_and_duplicate_ids(self):
        events=fixture()
        events.insert(4, {'type':'testStart','test':{'id':0,'name':NAMES[0]}})
        events += [{'type':'error','testID':0,'isFailure':True,'error':'secret'}]*25
        report=self.observe(events)
        self.assertEqual(report['errorCount'],25);self.assertEqual(len(report['errors']),20)
        self.assertTrue(all('testOrdinal' not in e for e in report['errors']))
        with self.assertRaises(v.GreenVerificationError):
            v.verify_green('\n'.join(json.dumps(e) for e in events),0,expected_names=NAMES,fixture_basename=BASE)

    def test_malformed_stream_observed_but_never_accepted(self):
        raw='{"type":"print","type":"done"}\nnot JSON\n'+json.dumps({'type':'done','success':True})
        report=v.observe_green(raw,0,expected_names=NAMES,fixture_basename=BASE,
                               stderr='/private/'+BASE+':0:3: Error: secret')
        self.assertEqual(report['malformedEvents'],2)
        self.assertEqual(report['terminalCount'],1)
        self.assertEqual(report['compileLocations'],[dict(line=0,column=3)])
        self.assertNotIn('private',json.dumps(report))
        with self.assertRaises(v.GreenVerificationError):
            v.verify_green(raw,0,expected_names=NAMES,fixture_basename=BASE)
