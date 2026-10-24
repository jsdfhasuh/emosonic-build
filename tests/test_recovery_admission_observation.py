"""Synthetic admission summaries only; no private controller source."""
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/native_follow_lifecycle_payload')]
import follow_lifecycle_observation as observer
import native_follow_lifecycle_schema as schema
import native_follow_lifecycle as lifecycle
import native_seek_anchor_observation as timing
import current_native_check as public
import test_native_compact_export as compact
from test_follow_correction_observation import restore_legacy_apply_parser


def summary(ordinal=1, reason='admitted', path='prepared', prepared='owner_accepted'):
    return {'invocationOrdinal': ordinal, 'reason': reason, 'path': path, 'preparedReason': prepared}


def envelope(rows=None, attempts=None, dropped=0):
    rows = [summary()] if rows is None else rows
    attempts = max((row['invocationOrdinal'] for row in rows), default=0) if attempts is None else attempts
    return {'schemaVersion': 1, 'attemptCount': attempts, 'overflow': attempts == 5,
        'droppedCount': dropped, 'droppedCountSaturated': dropped == 1000000, 'summaries': rows}


class RecoveryAdmissionObservationTests(unittest.TestCase):
    def test_exact_schema_and_payload_pins(self):
        raw = (ROOT / 'tests/fixtures/recovery_admission_schema.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '056abf764544781334ab3a906ad53177495bf422176f8c9d0c0b9cb619cc595a')
        contract = json.loads(raw); item = contract['properties']['summaries']['items']
        self.assertEqual(set(contract['required']), set(envelope()))
        self.assertEqual(set(item['required']), set(summary()))
        self.assertEqual(tuple(item['properties']['reason']['enum']), observer.ADMISSION_REASONS)
        self.assertEqual(tuple(item['properties']['path']['enum']), observer.ADMISSION_PATHS)
        self.assertEqual(tuple(item['properties']['preparedReason']['enum'][1:]), observer.ADMISSION_PREPARED_REASONS)
        self.assertEqual(schema.ADMISSION_REASONS, observer.ADMISSION_REASONS)
        self.assertEqual(schema.ADMISSION_PATHS, observer.ADMISSION_PATHS)
        self.assertEqual(schema.ADMISSION_PREPARED_REASONS, observer.ADMISSION_PREPARED_REASONS)
        self.assertEqual(hashlib.sha256(Path(observer.__file__).read_bytes()).hexdigest(), lifecycle.PAYLOAD_HASHES['follow_lifecycle_observation.py'])

    def test_absent_empty_declined_then_admitted_are_not_conflated(self):
        self.assertEqual(observer._admission_snapshot(None), {'status': 'unavailable'})
        self.assertNotIn('recoveryAdmission', observer._endpoint_timing([{}])['clients'][0])
        empty = observer._admission_snapshot(envelope([]))
        self.assertEqual(empty['summaries'], []); self.assertEqual(empty['coverage'], 'complete')
        raw = envelope([summary(1, 'prepared_owner_missing', prepared='native_anchor_missing'), summary(2)])
        got = observer._admission_snapshot(raw)
        self.assertEqual(got['summaries'], raw['summaries']); self.assertEqual(got['coverage'], 'complete')
        self.assertEqual(got['ordinalBasis'], 'begin_invocation_not_recovery_or_native_owner')
        self.assertEqual(got['scope'], 'begin_attempts_not_all_policy_routes')
        self.assertEqual(got['callerAttribution'], 'unverified')
        self.assertEqual(got['measurementMeaning'], 'admission_not_seek_completion_or_readiness')

    def test_all_fixed_enums_and_null_omission(self):
        for reason in observer.ADMISSION_REASONS:
            for path in observer.ADMISSION_PATHS:
                for prepared in (None, *observer.ADMISSION_PREPARED_REASONS):
                    raw = envelope([summary(reason=reason, path=path, prepared=prepared)])
                    got = observer._admission_snapshot(raw)
                    self.assertEqual(got['status'], 'observed')
                    self.assertEqual(got['summaries'][0], {k:v for k,v in raw['summaries'][0].items() if v is not None})

    def test_record_unknown_missing_type_and_range_are_invalid(self):
        cases = [('invocationOrdinal', True), ('invocationOrdinal', 0), ('invocationOrdinal', 5),
            ('invocationOrdinal', 1.0), ('reason', 'PRIVATE'), ('reason', {}),
            ('path', 'PRIVATE'), ('path', None), ('preparedReason', 'PRIVATE'),
            ('preparedReason', False), ('preparedReason', float('nan'))]
        for key, value in cases:
            row = summary(); row[key] = value
            self.assertEqual(observer._admission_snapshot(envelope([row], attempts=4)), {'status':'invalid'})
        for mutate in (lambda r:r.pop('preparedReason'), lambda r:r.update(raw='SECRET')):
            row = summary(); mutate(row)
            self.assertEqual(observer._admission_snapshot(envelope([row])), {'status':'invalid'})

    def test_envelope_type_extra_fields_and_bound_rejection(self):
        for key, value in [('schemaVersion', True), ('schemaVersion', 2), ('attemptCount', True),
                ('attemptCount', 6), ('attemptCount', -1), ('attemptCount', float('inf')),
                ('overflow', 1), ('overflow', True), ('droppedCount', True), ('droppedCount', -1),
                ('droppedCount', 1000001), ('droppedCountSaturated', 1), ('droppedCountSaturated', True),
                ('summaries', {}), ('summaries', [summary()] * 5)]:
            raw=envelope();raw[key]=value
            self.assertEqual(observer._admission_snapshot(raw), {'status':'invalid'})
        for mutate in (lambda r:r.pop('overflow'), lambda r:r.update(raw='SECRET')):
            raw=envelope();mutate(raw)
            self.assertEqual(observer._admission_snapshot(raw), {'status':'invalid'})

    def test_order_gaps_throws_overflow_and_drops_remain_truthful(self):
        for rows in ([summary(2),summary(1)], [summary(1),summary(1)], [summary(2)]):
            raw=envelope(rows, attempts=1 if len(rows)==1 else 2)
            self.assertEqual(observer._admission_snapshot(raw), {'status':'invalid'})
        cases=[envelope([summary(2)], attempts=2), envelope([], attempts=1),
            envelope([summary(1)], dropped=1), envelope([summary(i) for i in range(1,5)], attempts=5, dropped=1),
            envelope([summary(i) for i in range(1,5)], attempts=5, dropped=1000000)]
        for raw in cases:
            got=observer._admission_snapshot(raw)
            self.assertEqual(got['coverage'],'incomplete')
            self.assertEqual(got['summaries'],raw['summaries'])
        got=observer._admission_snapshot(envelope([summary(reason='prepared_owner_threw', prepared=None)]))
        self.assertEqual(got['summaries'][0]['reason'],'prepared_owner_threw')

    def test_no_reads_clocks_controls_input_mutation_or_cross_clock_math(self):
        raw=envelope();before=copy.deepcopy(raw)
        with patch('builtins.open',side_effect=AssertionError('No I/O')), patch.object(observer.time,'monotonic',side_effect=AssertionError('No clock')):
            got=observer._endpoint_timing([{'recoveryAdmissionDiagnostics':raw}])
        self.assertEqual(raw,before);self.assertEqual(got['clients'][0]['recoveryAdmission']['status'],'observed')
        text=inspect.getsource(observer._admission_snapshot)
        for token in ('.state(', '.command(', '.seek(', '.play(', '.finish(', 'time.', 'datetime.', 'open('):
            self.assertNotIn(token,text)
        self.assertFalse(any(isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Sub,ast.Div,ast.Mult)) for n in ast.walk(ast.parse(text))))

    def test_success_and_failure_reuse_same_existing_endpoint_without_reads(self):
        states=[{'recoveryAdmissionDiagnostics':envelope()}]*3
        matrix=SimpleNamespace(last=states, follow_lifecycle_observation=None,
            rate_measurement={'nativeTiming':{'authority':{},'follower':{}}},states=Mock(side_effect=AssertionError('No poll')))
        success=timing.successful_follow_observation(matrix)['followLifecycle']['endpointTiming']
        failure=observer.finish_follow_lifecycle(matrix)['endpointTiming']
        self.assertEqual(success,failure);matrix.states.assert_not_called()
        matrix.last=[{'recoveryAdmissionDiagnostics':{'raw':'SECRET'}}]
        self.assertEqual(timing.successful_follow_observation(matrix)['followLifecycle']['endpointTiming']['clients'][0]['recoveryAdmission'],{'status':'invalid'})

    def test_three_clients_preserve_all_four_summaries_and_filter_private_additions(self):
        raw=envelope([summary(i) for i in range(1,5)],attempts=5,dropped=1000000)
        endpoint=observer._endpoint_timing([{'recoveryAdmissionDiagnostics':raw}]*3)
        value={'stage':'follower-avplayer-rate-1.5','status':'passed','followLifecycle':{'endpointTiming':endpoint}}
        self.assertEqual(public.report_line(json.dumps(value)),value)
        dirty=copy.deepcopy(value);dirty['followLifecycle']['endpointTiming']['clients'][0]['recoveryAdmission']['raw']='SECRET'*10000
        self.assertEqual(public.report_line(json.dumps(dirty)),value)
        self.assertTrue(all(len(row['recoveryAdmission']['summaries'])==4 for row in endpoint['clients']))

    def test_exact_public_inverse_preserves_all_existing_observer_bytes(self):
        text=restore_legacy_apply_parser(Path(observer.__file__).read_text());begin=text.index('ADMISSION_REASONS =')
        end=text.index('def _endpoint_timing(states):',begin)
        restored=text[:begin]+text[end:]
        hook=("        if 'recoveryAdmissionDiagnostics' in state:\n"
            "            row['recoveryAdmission'] = _admission_snapshot(state['recoveryAdmissionDiagnostics'])\n")
        self.assertEqual(restored.count(hook),1);restored=restored.replace(hook,'',1)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'83a4fef529eff8fdb472d65ce25e0299c55113c2efb7ea6ecfa53b9e0d3f25ab')

    def test_maximum_existing_success_failure_shapes_roundtrip_through_actual_export(self):
        def filled(spec):
            if spec is bool:return True
            if type(spec) is frozenset:return max(spec,key=len)
            if type(spec) is dict:return {key:filled(value) for key,value in spec.items()}
            if spec[0]=='list':return [filled(spec[1]) for _ in range(spec[2])]
            return spec[2] if spec[0]=='integer' else float(spec[2])
        rate=dict(public.RATE_SCHEMA,nativeTiming={'authority':timing.SCHEMA,'follower':timing.SCHEMA})
        success={'stage':'follower-avplayer-rate-1.5','status':'passed',
            'observationBasis':'retained_alignment_and_post_measurement_log',
            'rateMeasurement':filled(rate),'followLifecycle':filled(schema.FOLLOW_LIFECYCLE_SCHEMA)}
        failure={'stage':'follower-avplayer-rate-1.5:native-follow-alignment','status':'failed','errorType':'TimeoutError',
            'rateMeasurement':success['rateMeasurement'],'followLifecycle':success['followLifecycle']}
        for key in ('nativeLogClassifications','waitObservation','startupStreams','failureFrames','failureLocation','nativeErrors','nativePlayback'):
            failure[key]=filled(public.DIAGNOSTIC_SCHEMA[key])
        with patch.dict(public.RATE_SCHEMA,{'nativeTiming':rate['nativeTiming']}):
            for value in (success,failure):
                lines=compact.CompactNativeExportTests().execute_record(value)
                self.assertEqual(json.loads(lines[0]),value)
                self.assertEqual(list(json.loads(lines[0])),list(public.report_line(json.dumps(value))))
                self.assertLess(len(lines[0].encode('utf-8')),512*1024)
                clients=json.loads(lines[0])['followLifecycle']['endpointTiming']['clients']
                self.assertEqual(len(clients),3)
                self.assertTrue(all(len(row['recoveryAdmission']['summaries'])==4 for row in clients))


if __name__=='__main__':unittest.main()
