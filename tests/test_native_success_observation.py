"""Synthetic success export checks; no private harness, fixtures or identities."""
import ast
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/native_follow_lifecycle_payload')]
import native_seek_anchor_observation as timing
import follow_lifecycle_observation as lifecycle
import current_native_check as public
from native_follow_lifecycle_schema import FOLLOW_LIFECYCLE_SCHEMA

SYNTHETIC = ('''import argparse
class Matrix:
    def alignment(self, states, authority_index, context, correction_identity, started):
        if states:
            authority, follower = states[authority_index], states[2]
            assert follow_correction_identity(states, authority_index, context) == correction_identity
    def rate(self, valid=True):
        label = 'follower-avplayer-rate-1.5'
        measured, last, elapsed, samples = 1.5, {'playbackRate': 1.5}, 3.2, 17
        self.trace.append('measurement_complete')
        assert valid and elapsed >= 3
''' + timing.RATE_SUCCESS + '''        self.rate_measurement = None
    def safe_failure(self):
        self.trace.append('original_failure')
        return {'stage': 'failure', 'status': 'failed', 'rateMeasurement': self.rate_measurement}
''').encode()


def measurement():
    return {'alignmentElapsedMs': 4200, 'elapsedSeconds': 3.2, 'nativeSamples': 17,
        'nativeTiming': {role: {'status': 'observed', 'clockObservation': {
            'status': 'observed', 'dartAckReceipt': 'unavailable', 'intervalAttribution': 'unknown',
            'rateCount': 2, 'rateDropped': 0, 'rateRecords': []}}
            for role in ('authority', 'follower')}}


def fixture():
    observer = SimpleNamespace(value={'status': 'observing', 'commandReturned': True, 'serverFollow': []},
        client=object(), original={'private': 'PRIVATE-IDENTITY'}, cursor={'status': 'captured'},
        finished=False, finish=Mock(side_effect=AssertionError('Must not finalize')),
        _server=Mock(side_effect=AssertionError('Must not read database')))
    return SimpleNamespace(rate_measurement=measurement(), follow_lifecycle_observation=observer,
        last=[{'private': 'PRIVATE-STATE'}], states=Mock(side_effect=AssertionError('Must not poll')))


def filled(schema):
    if schema is bool: return True
    if type(schema) is frozenset: return max(schema, key=len)
    if type(schema) is dict: return {key: filled(value) for key, value in schema.items()}
    if schema[0] == 'list': return [filled(schema[1]) for _ in range(schema[2])]
    return schema[2] if schema[0] == 'integer' else float(schema[2])


class NativeSuccessObservationTests(unittest.TestCase):
    def test_retained_tape_and_later_log_are_explicit_without_new_reads(self):
        matrix = fixture(); old = copy.deepcopy(matrix.follow_lifecycle_observation.value)
        log = {'coverage': 'complete', 'correctionSequence': {'eventCount': 2, 'records': []}}
        with patch.object(lifecycle, 'read_log_since', return_value=log) as read, \
                patch.object(lifecycle, '_endpoint_timing', return_value={'status': 'unavailable'}) as endpoint:
            result = timing.successful_follow_observation(matrix)
        self.assertIs(result['rateMeasurement'], matrix.rate_measurement)
        self.assertEqual(result['observationBasis'], 'retained_alignment_and_post_measurement_log')
        self.assertEqual(result['followLifecycle']['ownedLog'], log)
        read.assert_called_once_with(matrix.follow_lifecycle_observation.client,
            matrix.follow_lifecycle_observation.original, matrix.follow_lifecycle_observation.cursor)
        endpoint.assert_called_once_with(matrix.last)
        self.assertEqual(matrix.follow_lifecycle_observation.value, old)
        self.assertFalse(matrix.follow_lifecycle_observation.finished)
        matrix.follow_lifecycle_observation.finish.assert_not_called()
        matrix.follow_lifecycle_observation._server.assert_not_called()
        matrix.states.assert_not_called()
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_success_does_not_freeze_later_failure_log(self):
        matrix = fixture(); observer = matrix.follow_lifecycle_observation
        observer._server = Mock()
        with patch.object(lifecycle, 'read_log_since', side_effect=[{'coverage': 'complete', 'bytesRead': 10},
                {'coverage': 'complete', 'bytesRead': 20}]) as read:
            first = timing.successful_follow_observation(matrix)
            self.assertFalse(observer.finished)
            self.assertNotIn('ownedLog', observer.value)
            second = lifecycle.FollowLifecycleObservation.finish(observer)
        self.assertEqual(first['followLifecycle']['ownedLog']['bytesRead'], 10)
        self.assertEqual(second['ownedLog']['bytesRead'], 20)
        self.assertEqual(read.call_count, 2)
        self.assertTrue(observer.finished)
        observer._server.assert_called_once_with('failure')

    def test_nonfollow_rates_or_malformed_tape_do_not_observe_logs(self):
        with patch.object(lifecycle, 'read_log_since') as read:
            for value in (None, {}, {'nativeTiming': None}, {'nativeTiming': {'follower': {}}}):
                self.assertEqual(timing.successful_follow_observation(SimpleNamespace(rate_measurement=value)), {})
        read.assert_not_called()

    def test_missing_observer_retains_tape_and_marks_unavailable(self):
        matrix = fixture(); matrix.follow_lifecycle_observation = None
        result = timing.successful_follow_observation(matrix)
        self.assertEqual(result['followLifecycle']['status'], 'not_observed')
        self.assertIs(result['rateMeasurement'], matrix.rate_measurement)

    def test_observer_error_cannot_change_success_or_mutate_measurement(self):
        matrix = fixture(); old = copy.deepcopy(matrix.rate_measurement)
        with patch.object(lifecycle, 'read_log_since', side_effect=OSError('SECRET-PATH')):
            result = timing.successful_follow_observation(matrix)
        self.assertEqual(result['followLifecycle'], {'status': 'observation_unavailable'})
        self.assertEqual(matrix.rate_measurement, old)
        self.assertNotIn('SECRET', json.dumps(result))

    def test_existing_file_bound_and_rotation_statuses_survive_without_raw_lines(self):
        for coverage in ('file_bound_exceeded', 'ownership_refused', 'rotated', 'unavailable'):
            matrix = fixture()
            with patch.object(lifecycle, 'read_log_since', return_value={'coverage': coverage}):
                result = timing.successful_follow_observation(matrix)
            self.assertEqual(result['followLifecycle']['ownedLog'], {'coverage': coverage})
        self.assertEqual(lifecycle.MAX_LOG, 8 * 1024 * 1024)
        self.assertEqual(lifecycle.MAX_LINE, 8192)

    def test_existing_correction_reducer_is_bounded_and_never_returns_raw_log(self):
        line = '[2026-01-01T00:00:00.000] [DEBUG] [AudioPlayerService] Setting playback speed to: 1.5\n'
        reduced = lifecycle.parse_log_slice((line * 300).encode())
        sequence = reduced['correctionSequence']
        self.assertEqual(sequence['eventCount'], 300)
        self.assertEqual(len(sequence['records']), 128)
        self.assertEqual(sequence['recordsDropped'], 172)
        self.assertTrue(sequence['recordsTruncated'])
        self.assertNotIn('Setting playback', json.dumps(reduced))

    def test_saturated_success_export_uses_same_finite_failure_schema(self):
        schema = dict(public.RATE_SCHEMA, nativeTiming={'authority': timing.SCHEMA, 'follower': timing.SCHEMA})
        record = {'stage': 'follower-avplayer-rate-1.5', 'status': 'passed',
            'observationBasis': 'retained_alignment_and_post_measurement_log',
            'rateMeasurement': filled(schema), 'followLifecycle': filled(FOLLOW_LIFECYCLE_SCHEMA)}
        with patch.dict(public.RATE_SCHEMA, {'nativeTiming': schema['nativeTiming']}):
            self.assertEqual(public.report_line(json.dumps(record)), record)
            injected = copy.deepcopy(record)
            injected['privateRawLog'] = 'SECRET' * 100000
            injected['rateMeasurement']['privateIdentity'] = 'SECRET'
            injected['followLifecycle']['rawStack'] = 'SECRET'
            self.assertEqual(public.report_line(json.dumps(injected)), record)
        self.assertLess(len(json.dumps(record)), 512 * 1024)

    def test_unknown_basis_nonfinite_and_wrong_types_are_not_exported(self):
        record = {'stage': 'follower-avplayer-rate-1.5', 'status': 'passed',
            'observationBasis': 'SECRET', 'rateMeasurement': {'elapsedSeconds': float('inf'), 'nativeSamples': True}}
        self.assertEqual(public.report_line(json.dumps(record)), {'stage': record['stage'], 'status': 'passed'})

    def synthetic(self):
        with patch.object(timing, 'HARNESS_SHA', timing.digest(SYNTHETIC)):
            observed = timing.patch_harness(SYNTHETIC)
            self.assertEqual(timing.restore_harness(observed), SYNTHETIC)
        return observed

    def test_exact_inverse_preserves_all_assertions_and_failure_method(self):
        observed = self.synthetic()
        before, after = ast.parse(SYNTHETIC), ast.parse(observed)
        self.assertEqual([ast.dump(n) for n in ast.walk(before) if isinstance(n, ast.Assert)],
                         [ast.dump(n) for n in ast.walk(after) if isinstance(n, ast.Assert)])
        def failure(tree): return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'safe_failure')
        self.assertEqual(ast.dump(failure(before)), ast.dump(failure(after)))
        with patch.object(timing, 'HARNESS_SHA', timing.digest(SYNTHETIC)):
            for tampered in (observed.replace(b'assert valid and elapsed >= 3', b'assert valid'),
                observed.replace(b'**successful_follow_observation(self)', b'**successful_follow_observation(None)')):
                with self.assertRaises(ValueError): timing.restore_harness(tampered)

    def test_export_runs_after_measurement_assertion_and_before_original_clear(self):
        namespace = {}; exec(compile(self.synthetic(), '<synthetic>', 'exec'), namespace)
        matrix = namespace['Matrix'](); matrix.trace = []; matrix.rate_measurement = measurement()
        matrix.outcome = lambda *a, **kw: matrix.trace.append(('original_success', kw))
        def snapshot(actual):
            self.assertIs(actual, matrix); self.assertIsNotNone(actual.rate_measurement)
            actual.trace.append('export'); return {'rateMeasurement': actual.rate_measurement}
        namespace['successful_follow_observation'] = snapshot
        matrix.rate()
        self.assertEqual(matrix.trace[:2], ['measurement_complete', 'export'])
        self.assertEqual(matrix.trace[2][0], 'original_success')
        self.assertIsNone(matrix.rate_measurement)
        matrix.trace = []; matrix.rate_measurement = measurement()
        with self.assertRaises(AssertionError): matrix.rate(valid=False)
        self.assertEqual(matrix.trace, ['measurement_complete'])
        self.assertIsNotNone(matrix.rate_measurement)


if __name__ == '__main__': unittest.main()
