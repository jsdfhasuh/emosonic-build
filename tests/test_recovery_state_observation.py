"""Public envelope contract and synthetic state snapshots, never controller code."""
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
import native_seek_anchor_observation as timing
import current_native_check as public
CONTRACT = ROOT/'tests/fixtures/recovery_check_schema.json'
NULLABLE = ('recoveryOrdinal', *observer.RECOVERY_CHECK_SEQUENCES, 'ageMs', 'floorPositionMs')


def record(ordinal=1, reason='check_enter'):
    return {'v': 1, 'eventOrdinal': ordinal, 'recoveryOrdinal': 1, 'reason': reason,
        'cachedSequence': 12, 'baselineSequence': 10, 'lastObservedSequence': 11,
        'nominalSequenceFloor': None, **{key: False for key in observer.RECOVERY_CHECK_FLAGS},
        'ageMs': None, 'floorPositionMs': None}


def envelope(rows=None, attempts=None, dropped=0):
    rows = [record()] if rows is None else rows
    attempts = max((row['eventOrdinal'] for row in rows), default=0) if attempts is None else attempts
    return {'schemaVersion': 1, 'status': 'truncated' if attempts == 129 else 'recording',
        'recordLimit': 128, 'truncationRecordLimit': 1, 'attemptCount': attempts,
        'droppedCount': dropped, 'droppedCountSaturated': dropped == 1000000, 'records': rows}


class RecoveryStateObservationTests(unittest.TestCase):
    def test_exact_frozen_envelope_and_record_contracts(self):
        self.assertEqual(hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
            '530496ee1d92ce2238ec7fc8769633bcb41aae36c4008920d63c7b026a0bf808')
        contract = json.loads(CONTRACT.read_text()); item = contract['$defs']['record']
        self.assertEqual(hashlib.sha256((json.dumps(item, indent=2)+'\n').encode()).hexdigest(),
            'bd4490243ea60d5530855bee5bca6b1e37fbb5fc9988e1964870b90528e8edc9')
        self.assertEqual(set(contract['required']), set(envelope()))
        self.assertEqual(set(item['required']), observer.RECOVERY_CHECK_FIELDS)
        self.assertEqual(tuple(item['properties']['reason']['enum']), observer.RECOVERY_CHECK_REASONS)
        self.assertEqual(observer.RECOVERY_CHECK_REASONS, schema.RECOVERY_CHECK_REASONS)

    def test_valid_empty_and_populated_snapshots_remain_distinct_from_absence(self):
        self.assertEqual(observer._recovery_check_snapshot(None), {'status': 'unavailable'})
        self.assertEqual(observer._endpoint_timing([{}])['clients'], [{'clientOrdinal': 0}])
        self.assertEqual(observer._endpoint_timing([{'followRecoveryCheckDiagnostics': None}])['clients'][0]['recoveryChecks'], {'status': 'unavailable'})
        for raw in (envelope([]), envelope()):
            value = observer._recovery_check_snapshot(raw)
            self.assertEqual(value['status'], 'observed')
            self.assertEqual(value['coverage'], 'complete')
            self.assertEqual(len(value['records']), raw['attemptCount'])

    def test_all_reasons_and_truncation_marker_are_finite(self):
        rows = [record(i, reason) for i, reason in enumerate(observer.RECOVERY_CHECK_REASONS[:-1], 1)]
        rows.append(record(129, 'truncated'))
        value = observer._recovery_check_snapshot(envelope(rows, dropped=1))
        self.assertEqual(len(value['records']), 29)
        self.assertEqual(value['coverage'], 'incomplete')
        self.assertEqual(value['records'][-1]['reason'], 'truncated')
        for row in (record(128, 'truncated'), record(129, 'check_enter')):
            self.assertEqual(observer._recovery_check_snapshot(envelope([row], dropped=1)), {'status': 'invalid'})

    def test_exact_keys_boolean_types_ranges_and_nonfinite_values_fail_closed(self):
        bad = [('v', True), ('v', 2), ('eventOrdinal', 0), ('eventOrdinal', 130), ('eventOrdinal', True),
            ('recoveryOrdinal', -1), ('recoveryOrdinal', 130), ('reason', 'PRIVATE-TEXT'),
            ('cachedSequence', 9007199254740992), ('cachedSequence', 1.0), ('baselineSequence', True),
            ('floorPositionMs', 1.5), ('floorPositionMs', 86400001), ('ageMs', float('inf')),
            ('ageMs', float('nan')), ('ageMs', True), ('ageMs', -86400001)]
        bad += [(key, 0) for key in observer.RECOVERY_CHECK_FLAGS]
        for key, value in bad:
            row = record(); row[key] = value
            self.assertEqual(observer._recovery_check_snapshot(envelope([row], attempts=1)), {'status': 'invalid'})
        for edit in (lambda r:r.pop('ageMs'), lambda r:r.update(privateToken='SECRET')):
            row=record();edit(row)
            self.assertEqual(observer._recovery_check_snapshot(envelope([row])), {'status': 'invalid'})

    def test_envelope_types_relationships_and_extra_fields_fail_closed(self):
        bad = [('schemaVersion', True), ('status', 'private'), ('recordLimit', 129),
            ('truncationRecordLimit', 2), ('attemptCount', True), ('attemptCount', 130),
            ('droppedCount', -1), ('droppedCount', 1000001), ('droppedCountSaturated', 1),
            ('droppedCountSaturated', True), ('status', 'truncated'), ('records', {}),
            ('records', [record()]*130)]
        for key, value in bad:
            raw=envelope();raw[key]=value
            self.assertEqual(observer._recovery_check_snapshot(raw), {'status': 'invalid'})
        for edit in (lambda r:r.pop('records'), lambda r:r.update(privateToken='SECRET')):
            raw=envelope();edit(raw)
            self.assertEqual(observer._recovery_check_snapshot(raw), {'status': 'invalid'})

    def test_null_omission_and_sequence_domains_are_explicit_not_coerced(self):
        row=record();row.update({key:None for key in NULLABLE})
        value=observer._recovery_check_snapshot(envelope([row]))
        self.assertEqual(set(value['records'][0]), observer.RECOVERY_CHECK_FIELDS-set(NULLABLE))
        self.assertEqual(value['nullFields'], 'omitted_unavailable')
        self.assertEqual(value['sequenceBasis'], 'vendor_position_receipt_not_native_observer_ordinal')
        self.assertEqual(value['timeBasis'], 'existing_control_flow_values_no_new_clock')
        self.assertEqual(value['snapshotBasis'], 'existing_state_endpoint_not_alignment_sample')
        for sign in (-1,1):
            row=record();row.update({key:sign*9007199254740991 for key in observer.RECOVERY_CHECK_SEQUENCES})
            row.update(ageMs=sign*86400000.0, floorPositionMs=sign*86400000)
            value=observer._recovery_check_snapshot(envelope([row]))
            self.assertEqual(value['records'][0]['ageMs'], row['ageMs'])
            self.assertEqual(value['records'][0]['cachedSequence'], row['cachedSequence'])

    def test_drops_gaps_or_saturation_never_claim_complete_coverage(self):
        for raw in (envelope(dropped=1), envelope(dropped=1000000),
            envelope([record(2)], attempts=2), envelope([], attempts=1, dropped=1)):
            self.assertEqual(observer._recovery_check_snapshot(raw)['coverage'], 'incomplete')
        for raw in (envelope([record(2),record(1)], attempts=2),
            envelope([record(),record()], attempts=2), envelope([record(2)], attempts=1)):
            self.assertEqual(observer._recovery_check_snapshot(raw), {'status':'invalid'})

    def test_full_retention_cap_and_marker_remain_bounded(self):
        rows=[record(i) for i in range(1,129)]+[record(129,'truncated')]
        value=observer._recovery_check_snapshot(envelope(rows,dropped=1000000))
        self.assertEqual(len(value['records']),129)
        self.assertEqual(value['coverage'],'incomplete')
        self.assertTrue(value['droppedCountSaturated'])
        self.assertEqual(value['records'][-1]['eventOrdinal'],129)

    def test_endpoint_projection_never_mutates_or_clears_the_retained_state(self):
        raw={'followRecoveryCheckDiagnostics':envelope(),'privateToken':'SECRET'};before=copy.deepcopy(raw)
        first=observer._endpoint_timing([raw]);second=observer._endpoint_timing([raw])
        self.assertEqual(first,second);self.assertEqual(raw,before)
        self.assertEqual(first['clients'][0]['recoveryChecks']['status'],'observed')
        self.assertNotIn('SECRET',json.dumps(first))
        first['clients'][0]['recoveryChecks']['records'][0]['cachedSequence']=999
        self.assertEqual(raw,before)

    def test_success_failure_share_endpoint_snapshot_without_new_polls_or_scans(self):
        saved=SimpleNamespace(value={'status':'observing'},client=object(),original={},cursor={},
            finished=False,_server=Mock())
        saved.finish=MethodType(observer.FollowLifecycleObservation.finish,saved)
        matrix=SimpleNamespace(rate_measurement={'nativeTiming':{'authority':{},'follower':{}}},
            follow_lifecycle_observation=saved,last=[{'followRecoveryCheckDiagnostics':envelope()}],
            states=Mock(side_effect=AssertionError('No new state read')))
        with patch.object(observer,'read_log_since',return_value={'coverage':'complete'}) as read:
            success=timing.successful_follow_observation(matrix)
            failure=observer.finish_follow_lifecycle(matrix)
        a=success['followLifecycle']['endpointTiming'];b=failure['endpointTiming']
        self.assertEqual(a,b);matrix.states.assert_not_called()
        self.assertEqual(read.call_count,2) # Existing one scan per outcome, no checkpoint scan.

    def test_public_projection_preserves_every_retained_record_and_rejects_private_text(self):
        rows=[record(i) for i in range(1,129)]+[record(129,'truncated')]
        endpoint=observer._endpoint_timing([{'followRecoveryCheckDiagnostics':envelope(rows,dropped=1)}])
        record_value={'stage':'follower-avplayer-rate-1.5','status':'passed',
            'followLifecycle':{'endpointTiming':endpoint}}
        self.assertEqual(public.report_line(json.dumps(record_value)),record_value)
        dirty=copy.deepcopy(record_value)
        dirty['followLifecycle']['rawLog']='SECRET'*100000
        dirty['followLifecycle']['endpointTiming']['clients'][0]['recoveryChecks']['records'][0]['sourceId']='SECRET'
        self.assertEqual(public.report_line(json.dumps(dirty)),record_value)
        self.assertLess(len(json.dumps(record_value)),128000)

    def test_projection_has_no_io_clock_controller_or_playback_calls(self):
        source=inspect.getsource(observer._recovery_check_snapshot)+inspect.getsource(observer._recovery_check_record)
        for token in ('open(', 'read_log_since(', 'time.', 'datetime.', '.state(', '.command(', '.finish(', '.seek(', '.play('):
            self.assertNotIn(token,source)


if __name__=='__main__':unittest.main()
