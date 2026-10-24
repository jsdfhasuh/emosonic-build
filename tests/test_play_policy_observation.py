"""Public bounded endpoint projection; no private service or controller source."""
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/native_follow_lifecycle_payload')]
import follow_lifecycle_observation as observer
import native_follow_lifecycle_schema as schema
import native_follow_lifecycle as lifecycle
import native_seek_anchor_observation as timing
import current_native_check as public
from test_follow_correction_observation import restore_legacy_apply_parser
CONTRACT = ROOT/'tests/fixtures/play_policy_schema.json'
CONTRACT_SHA = '9104b050fcaef7db7111acc4d42fe845d11ff5fb8de9a30d70f992046985adc6'


def record(ordinal=1, phase='policy_begin'):
    row = {'eventOrdinal':ordinal, 'triggerOrdinal':1, 'phase':phase, 'elapsedUs':1000*ordinal,
        'policyOutcome':None, 'currentTrigger':True, 'cacheKind':'unknown', 'vendorSequence':None,
        'serviceOwnerMatches':None, 'sampleAfterPlayRequest':None, 'receiptProgress':None,
        'nativeLoadAttribution':'unverified'}
    if phase == 'truncated':
        row.update({key:None for key in observer.PLAY_POLICY_FIELDS-{'eventOrdinal','phase'}})
    return row


def envelope(rows=None, attempts=None, dropped=0, pending=None):
    rows = [record()] if rows is None else rows
    attempts=max((row['eventOrdinal'] for row in rows),default=0) if attempts is None else attempts
    return {'schemaVersion':1, 'status':'truncated' if attempts==33 else 'recording',
        'recordLimit':32, 'truncationRecordLimit':1, 'attemptCount':attempts,
        'droppedCount':dropped, 'droppedCountSaturated':dropped==1000000,
        'records':rows, 'pendingTriggerOrdinal':pending}


class PlayPolicyObservationTests(unittest.TestCase):
    def test_frozen_schema_fields_phases_and_payload_hash(self):
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),CONTRACT_SHA)
        contract=json.loads(CONTRACT.read_text()); item=contract['$defs']['record']
        self.assertEqual(set(contract['required']),set(envelope()))
        self.assertEqual(set(item['required']),observer.PLAY_POLICY_FIELDS)
        self.assertEqual(tuple(item['properties']['phase']['enum']),observer.PLAY_POLICY_PHASES)
        self.assertEqual(observer.PLAY_POLICY_PHASES,schema.PLAY_POLICY_PHASES)
        self.assertEqual(hashlib.sha256(Path(observer.__file__).read_bytes()).hexdigest(),
            lifecycle.PAYLOAD_HASHES['follow_lifecycle_observation.py'])

    def test_absent_empty_populated_and_pending_snapshots_are_distinct(self):
        self.assertEqual(observer._play_policy_snapshot(None),{'status':'unavailable'})
        self.assertEqual(observer._endpoint_timing([{}])['clients'],[{'clientOrdinal':0}])
        self.assertEqual(observer._endpoint_timing([{'playPolicyDiagnostics':None}])['clients'][0]['playPolicy'],{'status':'unavailable'})
        for raw in (envelope([]),envelope(),envelope(pending=32)):
            result=observer._play_policy_snapshot(raw)
            self.assertEqual(result['status'],'observed');self.assertEqual(result['coverage'],'complete')
            self.assertEqual(len(result['records']),raw['attemptCount'])
            self.assertEqual(result.get('pendingTriggerOrdinal'),raw['pendingTriggerOrdinal'])

    def test_all_fixed_phases_and_null_omission(self):
        rows=[record(i,phase) for i,phase in enumerate(observer.PLAY_POLICY_PHASES[:-1],1)]
        rows.append(record(33,'truncated'))
        result=observer._play_policy_snapshot(envelope(rows,dropped=1))
        self.assertEqual(len(result['records']),14);self.assertEqual(result['coverage'],'incomplete')
        self.assertEqual(result['records'][-1],{'eventOrdinal':33,'phase':'truncated'})
        self.assertEqual(result['nullFields'],'omitted_unavailable')
        self.assertEqual(result['timeBasis'],'process_local_stopwatch_not_native_clock')
        self.assertEqual(result['receiptBasis'],'accepted_service_receipt_not_native_observer_ordinal')
        self.assertEqual(result['measurementMeaning'],'in_process_observation_not_native_start_latency')
        self.assertEqual(result['nativeLoadAttribution'],'unverified')

    def test_record_shape_type_range_and_nonfinite_rejection(self):
        bad=[('eventOrdinal',True),('eventOrdinal',0),('eventOrdinal',34),('triggerOrdinal',None),
            ('triggerOrdinal',True),('triggerOrdinal',33),('phase','PRIVATE'),('phase',{}),
            ('elapsedUs',1.0),('elapsedUs',-1),('elapsedUs',9007199254740992),('elapsedUs',float('nan')),
            ('vendorSequence',True),('vendorSequence',-1),('vendorSequence',float('inf')),
            ('policyOutcome','PRIVATE'),('cacheKind',False),('nativeLoadAttribution','verified'),
            ('nativeLoadAttribution',None)] + [(k,1) for k in observer.PLAY_POLICY_FLAGS]
        for key,value in bad:
            with self.subTest(field=key,value_type=type(value).__name__):
                row=record();row[key]=value
                self.assertEqual(observer._play_policy_snapshot(envelope([row],attempts=1)),{'status':'invalid'})
        for edit in (lambda r:r.pop('elapsedUs'),lambda r:r.update(privateSource='SECRET')):
            row=record();edit(row)
            self.assertEqual(observer._play_policy_snapshot(envelope([row])),{'status':'invalid'})
        row=record();row.update(elapsedUs=9007199254740991,vendorSequence=9007199254740991)
        self.assertEqual(observer._play_policy_snapshot(envelope([row]))['records'][0]['elapsedUs'],9007199254740991)

    def test_truncation_marker_is_the_exact_uniform_null_shape(self):
        bad=[record(32,'truncated'),record(33,'policy_begin')]
        for key in observer.PLAY_POLICY_FIELDS-{'eventOrdinal','phase'}:
            row=record(33,'truncated');row[key]=record()[key] if record()[key] is not None else False;bad.append(row)
        for row in bad:
            self.assertEqual(observer._play_policy_snapshot(envelope([row],attempts=33,dropped=1)),{'status':'invalid'})

    def test_envelope_exact_shape_types_and_bounds(self):
        bad=[('schemaVersion',True),('recordLimit',33),('truncationRecordLimit',False),
            ('attemptCount',True),('attemptCount',34),('droppedCount',-1),('droppedCount',1000001),
            ('status','truncated'),('status',[]),('droppedCountSaturated',1),('droppedCountSaturated',True),
            ('pendingTriggerOrdinal',True),('pendingTriggerOrdinal',0),('pendingTriggerOrdinal',33),
            ('records',{}),('records',[record()]*34)]
        for key,value in bad:
            raw=envelope();raw[key]=value
            self.assertEqual(observer._play_policy_snapshot(raw),{'status':'invalid'})
        for edit in (lambda r:r.pop('pendingTriggerOrdinal'),lambda r:r.update(privateToken='SECRET')):
            raw=envelope();edit(raw)
            self.assertEqual(observer._play_policy_snapshot(raw),{'status':'invalid'})

    def test_gaps_drops_saturation_and_order_are_not_complete(self):
        for raw in (envelope(dropped=1),envelope(dropped=1000000),envelope([record(2)],attempts=2),
                    envelope([],attempts=1,dropped=1)):
            self.assertEqual(observer._play_policy_snapshot(raw)['coverage'],'incomplete')
        for raw in (envelope([record(2),record(1)]),envelope([record(),record()],attempts=2),
                    envelope([record(2)],attempts=1)):
            self.assertEqual(observer._play_policy_snapshot(raw),{'status':'invalid'})
        raw=envelope([record(i) for i in range(1,33)]+[record(33,'truncated')],dropped=1000000)
        result=observer._play_policy_snapshot(raw)
        self.assertEqual(len(result['records']),33);self.assertEqual(result['coverage'],'incomplete')
        self.assertTrue(result['droppedCountSaturated'])

    def test_endpoint_projection_is_repeatable_nonmutating_and_private_safe(self):
        raw={'playPolicyDiagnostics':envelope(),'privateToken':'SECRET'};before=copy.deepcopy(raw)
        first=observer._endpoint_timing([raw]);second=observer._endpoint_timing([raw])
        self.assertEqual(first,second);self.assertEqual(raw,before)
        self.assertNotIn('SECRET',json.dumps(first))
        first['clients'][0]['playPolicy']['records'][0]['elapsedUs']=999
        self.assertEqual(raw,before)

    def test_success_and_failure_reuse_existing_endpoint_without_new_reads(self):
        saved=SimpleNamespace(value={'status':'observing'},client=object(),original={},cursor={},
            finished=False,_server=Mock())
        saved.finish=MethodType(observer.FollowLifecycleObservation.finish,saved)
        matrix=SimpleNamespace(rate_measurement={'nativeTiming':{'authority':{},'follower':{}}},
            follow_lifecycle_observation=saved,last=[{'playPolicyDiagnostics':envelope()}],
            states=Mock(side_effect=AssertionError('No new state read')))
        with patch.object(observer,'read_log_since',return_value={'coverage':'complete'}) as read:
            success=timing.successful_follow_observation(matrix)
            failure=observer.finish_follow_lifecycle(matrix)
        self.assertEqual(success['followLifecycle']['endpointTiming'],failure['endpointTiming'])
        self.assertEqual(success['observationBasis'],'retained_alignment_and_post_measurement_log')
        self.assertEqual(read.call_count,2);matrix.states.assert_not_called()

    def test_invalid_observation_cannot_change_pass_or_original_evidence(self):
        matrix=SimpleNamespace(rate_measurement={'nativeTiming':{'authority':{},'follower':{}}},
            follow_lifecycle_observation=None,last=[{'playPolicyDiagnostics':{'PRIVATE':'SECRET'}}])
        before=copy.deepcopy(matrix.rate_measurement)
        value=timing.successful_follow_observation(matrix)
        self.assertEqual(value['followLifecycle']['endpointTiming']['clients'][0]['playPolicy'],{'status':'invalid'})
        self.assertEqual(matrix.rate_measurement,before);self.assertNotIn('SECRET',json.dumps(value))

    def test_full_three_client_export_is_bounded_and_filters_unknown_fields(self):
        rows=[record(i,'native_progress') for i in range(1,33)]+[record(33,'truncated')]
        for row in rows[:-1]:
            row.update(elapsedUs=9007199254740991,vendorSequence=9007199254740991,
                policyOutcome='unknown',cacheKind='network',**{key:True for key in observer.PLAY_POLICY_FLAGS})
        endpoint=observer._endpoint_timing([{'playPolicyDiagnostics':envelope(rows,dropped=1000000,pending=32)}]*3)
        value={'stage':'follower-avplayer-rate-1.5','status':'passed','followLifecycle':{'endpointTiming':endpoint}}
        self.assertEqual(public.report_line(json.dumps(value)),value)
        dirty=copy.deepcopy(value);dirty['followLifecycle']['rawLog']='SECRET'*100000
        dirty['followLifecycle']['endpointTiming']['clients'][0]['playPolicy']['records'][0]['rawError']='SECRET'
        self.assertEqual(public.report_line(json.dumps(dirty)),value)
        self.assertLess(len(json.dumps(value)),50000)

    def test_saturated_success_and_actual_failure_shape_stay_below_existing_bound(self):
        def filled(spec):
            if spec is bool: return True
            if type(spec) is frozenset: return max(spec,key=len)
            if type(spec) is dict: return {key:filled(value) for key,value in spec.items()}
            if spec[0]=='list': return [filled(spec[1]) for _ in range(spec[2])]
            return spec[2] if spec[0]=='integer' else float(spec[2])
        rate=dict(public.RATE_SCHEMA,nativeTiming={'authority':timing.SCHEMA,'follower':timing.SCHEMA})
        success={'stage':'follower-avplayer-rate-1.5','status':'passed',
            'observationBasis':'retained_alignment_and_post_measurement_log',
            'rateMeasurement':filled(rate),'followLifecycle':filled(schema.FOLLOW_LIFECYCLE_SCHEMA)}
        failure={'stage':'follower-avplayer-rate-1.5:native-follow-alignment','status':'failed',
            'errorType':'TimeoutError','rateMeasurement':success['rateMeasurement'],
            'followLifecycle':success['followLifecycle']}
        for key in ('nativeLogClassifications','waitObservation','startupStreams','failureFrames',
                    'failureLocation','nativeErrors','nativePlayback'):
            failure[key]=filled(public.DIAGNOSTIC_SCHEMA[key])
        with patch.dict(public.RATE_SCHEMA,{'nativeTiming':rate['nativeTiming']}):
            for value in (success,failure):
                self.assertEqual(public.report_line(json.dumps(value)),value)
                encoded=json.dumps(value,separators=(',', ':'),allow_nan=False)
                self.assertEqual(json.loads(encoded),value)
                self.assertLess(len(encoded.encode('utf-8')),512*1024)
                clients=value['followLifecycle']['endpointTiming']['clients']
                self.assertEqual(len(clients),3)
                self.assertTrue(all(len(row['playPolicy']['records'])==33 for row in clients))

    def test_exact_inverse_preserves_every_original_observer_byte(self):
        text=restore_legacy_apply_parser(Path(observer.__file__).read_text())
        begin=text.index('ADMISSION_REASONS =')
        end=text.index('def _endpoint_timing(states):',begin)
        text=text[:begin]+text[end:]
        admission_hook=("        if 'recoveryAdmissionDiagnostics' in state:\n"
            "            row['recoveryAdmission'] = _admission_snapshot(state['recoveryAdmissionDiagnostics'])\n")
        self.assertEqual(text.count(admission_hook),1)
        text=text.replace(admission_hook,'',1)
        begin=text.index('\nPLAY_POLICY_PHASES =')
        end=text.index('def _endpoint_timing(states):',begin)
        restored=text[:begin]+text[end:]
        hook=("        if 'playPolicyDiagnostics' in state:\n"
              "            row['playPolicy'] = _play_policy_snapshot(state['playPolicyDiagnostics'])\n")
        self.assertEqual(restored.count(hook),1)
        restored=restored.replace(hook,'',1)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
            '61f845892a17587b30e223289a8899cbeab38861d9fcaba08057a03186c42ad2')

    def test_reducer_has_no_io_clock_poll_control_or_crossclock_arithmetic(self):
        source=inspect.getsource(observer._play_policy_record)+inspect.getsource(observer._play_policy_snapshot)
        for token in ('open(', 'read_log_since(', 'time.', 'datetime.', '.state(', '.command(', '.finish(', '.seek(', '.play('):
            self.assertNotIn(token,source)
        tree=ast.parse(source)
        operations=[n for n in ast.walk(tree) if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Sub,ast.Div,ast.Mult))]
        allowed=ast.parse("PLAY_POLICY_FIELDS - {'eventOrdinal', 'phase'}",mode='eval').body
        self.assertEqual([ast.dump(n) for n in operations],[ast.dump(allowed)])


if __name__=='__main__':unittest.main()
