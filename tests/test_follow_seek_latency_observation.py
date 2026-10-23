import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_seek_latency_observation as c
import follow_seek_latency_proof as proof
import follow_recovery_check as recovery


class SeekSamplesObservationTests(unittest.TestCase):
    def setUp(self):
        self.source = Path('/owned/source')
        self.names = [c.TEST_NAME] + [f'synthetic control {i}' for i in range(12)]
        self.suite = dict(path=c.TEST_PATH, sha256=c.FIXTURE_SHA256, names=self.names)

    def samples(self):
        return [dict(cycle=i, rate=1.5, holdMs=200,
                     decision='[[EMO_FOLLOW_SYNC]] action=softCorrectDrift private-secret-suffix',
                     requestedPositionMs=10000+i*1500, serverNowMs=100200+i*1000,
                     residualMs=-290, nativeResidualMs=-300, realProjectionUpperMs=10,
                     nativeAnchorAdopted=True) for i in range(5)]

    def events(self, failed=False):
        result = [dict(type='suite', suite=dict(id=7, path=str(self.source/c.TEST_PATH)))]
        for i, name in enumerate(self.names):
            result.append(dict(type='testStart', test=dict(id=i+1, suiteID=7, name=name)))
            if i == 0:
                result.append(dict(type='print', testID=1, message=c.PREFIX+json.dumps(self.samples())))
                if failed:
                    result.append(dict(type='error', testID=1, isFailure=True, error='private-error'))
            result.append(dict(type='testDone', testID=i+1, hidden=False, skipped=False,
                               result='failure' if failed and i == 0 else 'success'))
        result.append(dict(type='done', success=not failed))
        return result

    def raw(self, events=None):
        return '\n'.join(json.dumps(e) for e in (self.events() if events is None else events))

    def observe(self, events=None, phase='focused', suites=None):
        report = c.observe_samples(self.raw(events), self.source,
                                   [self.suite] if suites is None else suites, phase)
        self.assertNotIn('private', json.dumps(report))
        self.assertNotIn('synthetic control', json.dumps(report))
        self.assertNotIn(str(self.source), json.dumps(report))
        self.assertNotIn(c.TEST_NAME, json.dumps(report))
        return report

    def test_known_five_samples_are_same_in_focused_and_full(self):
        focused = self.observe(); full = self.observe(phase='full')
        self.assertEqual(focused['status'], 'observed')
        self.assertEqual(focused['samples'], full['samples'])
        self.assertEqual(len(full['samples']), 5)
        self.assertEqual(full['samples'][0]['decision'], 'softCorrectDrift')
        self.assertEqual(full['samples'], proof.project_synthetic_samples([c.PREFIX+json.dumps(self.samples())]))

    def test_wrong_test_id_boolean_id_name_and_suite_never_export_samples(self):
        for kind in ('other-id', 'bool-id', 'wrong-name', 'other-suite', 'wrong-path'):
            events = self.events()
            if kind == 'other-id': events[2]['testID'] = 2
            elif kind == 'bool-id': events[2]['testID'] = True
            elif kind == 'wrong-name': events[1]['test']['name'] = 'other'
            elif kind == 'other-suite': events[1]['test']['suiteID'] = 8
            else: events[0]['suite']['path'] = '/outside/'+c.TEST_PATH
            with self.subTest(kind=kind): self.assertNotIn('samples', self.observe(events))

    def test_inventory_fixture_hash_and_target_membership_required(self):
        for field, value in (('sha256', '0'*64), ('names', ['other']*13)):
            with self.subTest(field=field):
                report = self.observe(suites=[dict(self.suite, **{field:value})])
                self.assertEqual(report['status'], 'fixture-mismatch')
        self.assertIsNone(self.observe(suites=[]))
        self.assertEqual(self.observe(suites=[self.suite, self.suite])['status'], 'fixture-mismatch')

    def test_duplicate_suite_test_and_report_rejected(self):
        for index in (0, 1, 2):
            events=self.events(); events.append(events[index])
            with self.subTest(index=index): self.assertNotIn('samples', self.observe(events))

    def test_missing_or_early_report_is_finite(self):
        events=self.events(); report=events.pop(2)
        self.assertEqual(self.observe(events)['status'], 'missing-report')
        events.insert(0, report)
        self.assertEqual(self.observe(events)['status'], 'malformed-samples')

    def test_extra_keys_nonfinite_bad_action_scalar_and_cycle_rejected(self):
        changes=[('extra','private'),('rate',float('nan')),('holdMs',float('inf')),
                 ('holdMs',True),('holdMs',1000001),('decision','private'),('cycle',True),
                 ('nativeAnchorAdopted',1)]
        for key,value in changes:
            samples=self.samples();samples[0][key]=value
            events=self.events();events[2]['message']=c.PREFIX+json.dumps(samples)
            with self.subTest(key=key,value=value):self.assertEqual(self.observe(events)['status'],'malformed-samples')

    def test_malformed_oversized_duplicate_inner_keys_and_wrong_count(self):
        texts=['{private', 'x'*8192, json.dumps(self.samples()[:4]),
               json.dumps(self.samples()).replace('"cycle": 0','"cycle": 0, "cycle": 0')]
        for text in texts:
            events=self.events();events[2]['message']=c.PREFIX+text
            with self.subTest(length=len(text)):self.assertEqual(self.observe(events)['status'],'malformed-samples')

    def test_event_output_bounds_and_malformed_json(self):
        for raw in ('private raw text', '{"type":"print","type":"print"}', '{"x":NaN}', '[1]'):
            report=c.observe_samples(raw,self.source,[self.suite],'full')
            self.assertEqual(report['status'],'malformed-events');self.assertNotIn('private',json.dumps(report))
        with patch.object(c,'MAX_BYTES',10):self.assertEqual(self.observe()['status'],'output-limit')
        with patch.object(c,'MAX_EVENTS',2):self.assertEqual(self.observe()['status'],'event-limit')

    def test_full_observer_retains_tape_without_normalizing_exit_or_failure(self):
        for failed in (False,True):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                report=recovery.full_test_observation(self.raw(self.events(failed)),'',
                    {c.TEST_PATH},self.source,[self.suite],int(failed))
            tape=json.loads(output.getvalue())
            self.assertEqual(tape['status'],'observed');self.assertEqual(tape['phase'],'full')
            self.assertEqual(report['exitCode'],int(failed))
            self.assertEqual(report['results']['failure'],int(failed))
            self.assertIs(report['terminalSuccess'],not failed)
            self.assertNotIn('private',output.getvalue())

    def test_focused_observer_preserves_failure_and_fingerprint_checks(self):
        output=io.StringIO()
        with patch.object(recovery.request,'context'), \
             patch.object(recovery.request.p,'source_context',return_value=(self.source,None,'a'*40,None)), \
             patch.object(recovery.regression.native,'native_env',return_value={}), \
             patch.object(recovery.request.p,'source_fingerprint',return_value='same') as fingerprint, \
             patch.object(recovery,'inventory',return_value=[self.suite]), \
             patch.object(recovery.request.p,'codegen'), \
             patch.object(recovery.subprocess,'run',return_value=subprocess.CompletedProcess([],1,self.raw(self.events(True)),'')), \
             contextlib.redirect_stdout(output):
            with self.assertRaises(recovery.request.p.GateError): recovery.focused()
        self.assertEqual(fingerprint.call_count,2)
        reports=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(reports[0]['phase'],'focused');self.assertEqual(reports[0]['status'],'observed')
        self.assertEqual(reports[-1]['status'],'failed')
        self.assertNotIn('private',output.getvalue())

    def test_observation_does_not_modify_inputs_or_red_stage(self):
        events=self.events();before=json.dumps(events);stage=proof.PROOF_STAGE
        self.observe(events)
        self.assertEqual(json.dumps(events),before);self.assertEqual(proof.PROOF_STAGE,stage)


if __name__=='__main__':unittest.main()
