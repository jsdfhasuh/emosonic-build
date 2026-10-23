"""Synthetic fixed-literal logs only; no native/private source or raw log export."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/native_follow_lifecycle_payload')]
import follow_lifecycle_observation as obs
import native_follow_lifecycle_schema as schema


def log(body, stamp='2026-10-22T15:00:00.000', logger='EmoRealtimeClient'):
    return f'[{stamp}] [DEBUG] [{logger}] {body}\n'


def parse(text):
    return obs.parse_log_slice(text.encode())['correctionSequence']


class CorrectionObservationTests(unittest.TestCase):
    def test_fixed_post_restore_cancellation_reasons_only(self):
        for reason in ('owner_changed', 'source_changed', 'restore_not_acknowledged', 'native_receipts_closed'):
            row = parse(log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=' + reason))['records'][0]
            self.assertEqual(row['reason'], reason)
        row = parse(log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=PRIVATE_UNKNOWN'))['records'][0]
        self.assertEqual(row['reason'], 'unrecognized')

    def test_actual_decision_fields_are_pre_recovery_policy_inputs(self):
        body = ('[[EMO_FOLLOW_SYNC]] action=softCorrectDrift trackId=PRIVATE index=0 '
            'positionMs=12000 driftMs=-80 correction=rateLimited settled=true '
            'adaptiveFollowDelayMs=0 followLeadCompensationMs=0 followSyncToleranceMs=50 '
            'latencySamples=7 sourceControlChanged=false')
        result = parse(log(body))
        row = result['records'][0]
        self.assertEqual(result['invalidFieldCount'], 0)
        self.assertEqual(row['positionMs'], 12000)
        self.assertEqual(row['driftMs'], -80)
        self.assertEqual(row['correction'], 'rateLimited')
        self.assertIs(row['settled'], True)
        self.assertIs(row['sourceControlChanged'], False)
        self.assertNotIn('PRIVATE', json.dumps(result))
        injected = parse(log(body + ' error=PRIVATE driftMs=0'))['records'][0]
        self.assertFalse(set(injected) & {'positionMs', 'driftMs', 'settled', 'sourceControlChanged'})

    def test_endpoint_latency_count_is_bounded_integer_only(self):
        rows = obs._endpoint_timing([{'latencySampleCount':7}, {'latencySampleCount':True}, {'latencySampleCount':1000001}])['clients']
        self.assertEqual(rows, [{'clientOrdinal':0,'latencySampleCount':7}, {'clientOrdinal':1}, {'clientOrdinal':2}])

    def test_real_literal_order_and_invocation_not_completion(self):
        text = log('[[EMO_FOLLOW_SYNC]] action=softCorrectDrift trackId=PRIVATE driftMs=-80')
        text += log('Setting playback speed to: 1.59', '2026-10-22T15:00:00.100', 'AudioPlayerService')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=settled', '2026-10-22T15:00:00.300')
        text += log('Setting playback speed to: 1.5', '2026-10-22T15:00:00.310', 'AudioPlayerService')
        text += log('[[EMO_FOLLOW_SYNC]] speedCorrection apply targetKey=PRIVATE driftMs=-80 baseSpeed=1.5 syncSpeed=1.59 durationMs=1333', '2026-10-22T15:00:00.500')
        text += log('[[EMO_FOLLOW_SYNC]] speedCorrection restore reason=timer targetKey=PRIVATE speed=1.5', '2026-10-22T15:00:01.833')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true', '2026-10-22T15:00:05.000')
        result = parse(text)
        self.assertEqual([r['ordinal'] for r in result['records']], list(range(1, 8)))
        self.assertEqual([r['wallOffsetMs'] for r in result['records']], [0, 100, 300, 310, 500, 1833, 5000])
        self.assertEqual(result['records'][1]['event'], 'speed_setting_invocation')
        self.assertEqual(result['records'][4]['syncSpeed'], 1.59)
        self.assertTrue(result['records'][-1]['supported'])
        self.assertFalse(result['monotonicClockPaired'])
        self.assertFalse(result['recoveryWindowStartObserved'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_all_known_reasons_and_explicit_unknown(self):
        result = parse(''.join(log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason='+reason)
            for reason in (*obs.CORRECTION_REASONS, 'PRIVATE')))
        self.assertEqual(result['unknownReasonCount'], 1)
        self.assertEqual(result['records'][-1]['reason'], 'unrecognized')
        self.assertEqual(obs.CORRECTION_REASONS, schema.CORRECTION_REASONS)
        self.assertEqual(obs.CORRECTION_EVENTS, schema.CORRECTION_EVENTS)

    def test_real_failures_and_false_supported_do_not_leak_errors(self):
        text = log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=false')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery restore failed error=PRIVATE reason=timer')
        text += log('[[EMO_FOLLOW_SYNC]] speedCorrection restore failed reason=timer error=PRIVATE reason=dispose')
        rows = parse(text)['records']
        self.assertIs(rows[0]['supported'], False)
        self.assertEqual(rows[1]['event'], 'seek_recovery_restore_failed')
        self.assertEqual(rows[2]['reason'], 'timer')
        self.assertNotIn('PRIVATE', json.dumps(rows))

    def test_lookalike_logger_and_embedded_markers_do_not_classify(self):
        text = log('error=[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=settled')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=settled', logger='WrongLogger')
        text += log('Setting playback speed to: 1.59', logger='EmoRealtimeClient')
        text += log('Error setting playback speed: Setting playback speed to: 1.59', logger='AudioPlayerService')
        self.assertEqual(parse(text)['eventCount'], 0)

    def test_nonfinite_out_of_bound_and_duplicate_fields_are_not_values(self):
        text = log('[[EMO_FOLLOW_SYNC]] speedCorrection apply targetKey=PRIVATE driftMs=NaN baseSpeed=99 syncSpeed=Infinity durationMs=999999')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=PRIVATE')
        text += log('[[EMO_FOLLOW_SYNC]] speedCorrection apply targetKey=PRIVATE driftMs=-80 driftMs=7 baseSpeed=1.5 syncSpeed=1.59 durationMs=1000')
        result = parse(text)
        self.assertEqual(result['invalidFieldCount'], 6)
        for row in result['records']:
            self.assertFalse(set(row) & {'driftMs', 'baseSpeed', 'syncSpeed', 'durationMs', 'supported'})

    def test_file_order_survives_clock_regression_and_date_boundary(self):
        text = log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=timer', '2026-10-22T23:59:59.900')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true', '2026-10-23T00:00:00.100')
        text += log('Setting playback speed to: 1.5', '2026-10-22T23:59:59.800', 'AudioPlayerService')
        result = parse(text)
        self.assertEqual([r['wallOffsetMs'] for r in result['records']], [0, 200, -100])
        self.assertTrue(result['wallClockRegressionObserved'])
        self.assertEqual([r['ordinal'] for r in result['records']], [1, 2, 3])

    def test_invalid_first_timestamp_never_reanchors_or_claims_elapsed(self):
        text = log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=timer', '2026-99-22T15:00:00.000')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true')
        result = parse(text)
        self.assertEqual(result['timestampIssueCount'], 2)
        self.assertTrue(all('wallOffsetMs' not in r for r in result['records']))

    def test_mixed_time_basis_and_excess_offset_are_unavailable(self):
        for stamp in ('2026-10-22T15:00:00.001Z', '2026-10-23T15:00:00.000'):
            result = parse(log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true') +
                log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=timer', stamp))
            self.assertEqual(result['timestampIssueCount'], 1)
            self.assertNotIn('wallOffsetMs', result['records'][1])

    def test_bounded_first_and_last_preserve_counts_and_terminal_events(self):
        text = log('[[EMO_FOLLOW_SYNC]] action=softCorrectDrift') * 150
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true')
        result = parse(text)
        self.assertEqual(result['eventCount'], 151)
        self.assertEqual(len(result['records']), 128)
        self.assertEqual(result['recordsDropped'], 23)
        self.assertTrue(result['recordsTruncated'])
        self.assertEqual([r['ordinal'] for r in result['records'][:64]], list(range(1, 65)))
        self.assertEqual(result['records'][64]['ordinal'], 88)
        self.assertEqual(result['records'][-1]['event'], 'seek_recovery_exhausted')

    def test_existing_stream_coverage_stays_partial_on_truncated_markers(self):
        text = log('[[EMO_FOLLOW_SYNC]] seekRecovery cancelled reason=timer')
        text += log('[[EMO_FOLLOW_SYNC]] seekRecovery exhausted supported=true').rstrip('\n')
        result = obs.parse_log_slice(text.encode())
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(result['correctionSequence']['eventCount'], 1)

    def test_endpoint_reads_existing_samples_and_does_not_mutate(self):
        state = {'privateId':'PRIVATE','serverClockOffsetMs': 2, 'dartPositionMs': 11000,
            'dartPositionSampledAtMs': 100010, 'dartPositionSampleUncertaintyMs':1.5,
            'nativePlayers': [{'positionMs': 10980,
                'sampledAtMs':100000,'playbackRate':1.5,'playbackState':3,'requestedRate':1.5,
                'seekInProgress':False,'playingIntent':True,'avTimeControlStatus':2,
                'sampleUncertaintyMs':1}], 'followTimingDiagnostics': {
                    'observedSourceFactPresent':True,'observedSourceFactMatchesCurrent':True,
                    'observedSourceTimingValid':True,'observedProjectionBasis':'strict_sampled_at',
                    'observedProjectedTargetMs':11000,'lastObservedControllerDriftMs':-4,
                    'observedSourceSampleAgeMs':123,'privateId':'PRIVATE'}}
        before = copy.deepcopy(state)
        matrix = SimpleNamespace(last=[state], clients=[])
        result = obs.finish_follow_lifecycle(matrix)
        self.assertEqual(result['status'], 'not_observed')
        row = result['endpointTiming']['clients'][0]
        self.assertEqual(row['dartReadSkewMs'], 10)
        self.assertEqual(row['nativeMinusObservedTargetAtDartReadMs'], -5)
        self.assertEqual(row['dartSampleUncertaintyMs'], 1.5)
        self.assertEqual(state, before)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('sampledAtMs', json.dumps(result))

    def test_held_clock_or_unknown_state_never_produces_projected_residual(self):
        item = {'positionMs':100,'sampledAtMs':100000,'playbackRate':1.5,'playbackState':3,
            'seekInProgress':False,'playingIntent':True,'avTimeControlStatus':2}
        state = {'dartPositionSampledAtMs':100010, 'nativePlayers':[item],
            'followTimingDiagnostics':{'observedProjectionBasis':'strict_sampled_at','observedProjectedTargetMs':120}}
        for key, bad in (('seekInProgress',True), ('seekInProgress',None), ('playingIntent',False),
                ('avTimeControlStatus',1), ('avTimeControlStatus',True), ('playbackState',4), ('playbackRate',0)):
            changed = copy.deepcopy(state); changed['nativePlayers'][0][key] = bad
            row = obs._endpoint_timing([changed])['clients'][0]
            self.assertNotIn('nativeMinusObservedTargetAtDartReadMs', row)
            self.assertEqual(row['nativePositionMs'], 100)

    def test_endpoint_unknown_boolean_nonfinite_and_malformed_are_not_exported(self):
        result = obs._endpoint_timing([{'serverClockOffsetMs':float('nan'), 'dartPositionMs':True,
            'followTimingDiagnostics':{'runtimeAdaptiveDelayMs':True, 'observedProjectionBasis':'PRIVATE',
            'observedSourceFactPresent':'true'},'nativePlayers':[]}])
        self.assertEqual(result['clients'], [{'clientOrdinal':0}])
        self.assertEqual(obs._endpoint_timing(None), {'status':'unavailable'})

    def test_complete_populated_output_survives_export_without_private_fields(self):
        import current_native_check as native
        value = {'stage':'native-follow-command-observation', 'followLifecycle': {
            'ownedLog': obs.parse_log_slice(log('[[EMO_FOLLOW_SYNC]] speedCorrection apply targetKey=PRIVATE driftMs=-80 baseSpeed=1.5 syncSpeed=1.59 durationMs=1000').encode()),
            'endpointTiming': obs._endpoint_timing([{'followTimingDiagnostics':{'observedSourceFactPresent':True}}])}}
        self.assertEqual(native.report_line(json.dumps(value)), value)
        value['followLifecycle']['ownedLog']['correctionSequence']['records'][0]['targetKey'] = 'PRIVATE'
        self.assertNotIn('PRIVATE', json.dumps(native.report_line(json.dumps(value))))


if __name__ == '__main__': unittest.main()
