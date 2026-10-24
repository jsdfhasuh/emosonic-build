"""Synthetic transfer-only retention contracts, without private harness or native execution."""
import ast
import copy
import contextlib
import io
import inspect
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
import current_native_check as public
import native_follow_readiness as readiness
import native_seek_anchor_observation as timing
from test_native_clock_observation import raw_clock
import test_native_compact_export as compact
from test_native_seek_anchor_observation import fixture as timing_fixture


SCHEMA_ADDITIONS = {
    'nativeTiming': {'authority': timing.SCHEMA, 'follower': timing.SCHEMA},
    'nativeTimingBasis': timing.TRANSFER_NATIVE_BASIS_SCHEMA,
}
FINAL_FIELDS = (
    'nativeLogClassifications', 'waitObservation', 'startupStreams', 'failureFrames',
    'failureLocation', 'handoffDiagnostics', 'handoffBeforeStart', 'nativeErrors',
    'nativePlayback', 'serverCanonicalObservation', 'followLifecycle',
    'followConditions', 'followOutcomes',
)
TRANSFER_OBSERVATION_FIELDS = (
    'safety', 'authority', 'follower', 'followerMinusAuthorityClockOffsetMs',
    'alignedNativeDriftMs', 'readUncertaintyMs', 'nativeReadSkewMs',
    'syncToleranceMs', 'hardSeekThresholdMs', 'leadCompensationMs',
    'elapsedSeconds', 'unsettledSeconds', 'precision',
)


def filled(schema):
    """Populate every declared field and every existing bounded list to capacity."""
    if schema is bool:
        return True
    if type(schema) is frozenset:
        return max(schema, key=lambda value: (len(value), value))
    if type(schema) is dict:
        return {key: filled(value) for key, value in schema.items()}
    if schema[0] == 'list':
        return [filled(schema[1]) for _ in range(schema[2])]
    return schema[2] if schema[0] == 'integer' else float(schema[2])


def state(ordinal=1, count=12):
    native = timing_fixture()
    native.update(positionMs=20000 + ordinal * 100, sampledAtMs=1000400 + ordinal * 12,
        playbackRate=1.5, requestedRate=1.5, sampleUncertaintyMs=2,
        playingIntent=True, seekInProgress=False, playbackState=3)
    native['timingObservation']['clockObservation'] = raw_clock(count)
    return {'nativePlayers': [native], 'serverClockOffsetMs': 20 - ordinal,
        'latencySampleCount': 7, 'dartPositionSampledAtMs': native['sampledAtMs'] + 3,
        'dartPositionSampleUncertaintyMs': 2}


def states():
    return [state(0), state(1), state(2)]


def matrix(kind='transfer'):
    return SimpleNamespace(
        follow_precision_transition={'kind': kind, 'origin': 100.0, 'deadline': 110.0,
            'settled': False, 'settledAt': None, 'candidate': object(),
            'lastStates': object(), 'measurement': {'precisionSamples': 4}},
        rate_measurement={'expectedRate': 1.5, 'nativeTiming': {'oldAlignment': True}},
        follow_observation={'safety': {'exactNativeFollowTask': True}},
        states=Mock(side_effect=AssertionError('No additional state read')),
        wait=Mock(side_effect=AssertionError('No additional poll')),
        command=Mock(side_effect=AssertionError('No control command')))


# Public precision payload plus test-owned methods, never private harness content.
SYNTHETIC_HARNESS = ('''import argparse
''' + readiness.payload('follow_precision_helpers.py') + '''
class Matrix:
    def alignment(self, states, authority_index, context, correction_identity, started):
        if states:
            authority, follower = states[authority_index], states[2]
            assert follow_correction_identity(states, authority_index, context) == correction_identity
    def rate(self, label, measured, last, elapsed, samples):
        assert elapsed >= 3
''' + timing.RATE_SUCCESS + '''    def record_follow_condition(self, condition, passed):
        self.follow_conditions[condition] = passed
        if not passed and self.follow_first_failure is None:
            self.follow_first_failure = {'condition': condition,
                'observation': json.loads(json.dumps(self.follow_observation))}
''').encode()


def final_failure_envelope(include_nested=True):
    """Final .8/restore endpoint shape with one frozen transfer failure tape.

    The final followObservation is safety-only, not an invented duplicate of
    the old precision tape. All original final diagnostic fields remain.
    """
    with patch.dict(public.RATE_SCHEMA, SCHEMA_ADDITIONS):
        result = {
            'stage': 'follower-beyond-recovery-window', 'status': 'failed',
            'errorType': 'AssertionError',
            **{key: filled(public.DIAGNOSTIC_SCHEMA[key]) for key in FINAL_FIELDS},
            'followObservation': {'safety': filled(public.FOLLOW_OBSERVATION_SCHEMA['safety'])},
            'followFirstFailure': {'condition': 'steady_sample_precision', 'observation': {
                key: filled(public.FOLLOW_OBSERVATION_SCHEMA[key])
                for key in TRANSFER_OBSERVATION_FIELDS}},
        }
        if not include_nested:
            precision = result['followFirstFailure']['observation']['precision']
            precision.pop('nativeTiming'); precision.pop('nativeTimingBasis')
        return result


class TransferNativeRetentionTests(unittest.TestCase):
    def observe_namespace(self, now=102.5):
        with patch.object(timing, 'HARNESS_SHA', timing.digest(SYNTHETIC_HARNESS)):
            observed = timing.patch_harness(SYNTHETIC_HARNESS)
            self.assertEqual(timing.restore_harness(observed), SYNTHETIC_HARNESS)
        namespace = {'math': math, 'json': json, 'time': SimpleNamespace(monotonic=Mock(return_value=now))}
        exec(compile(observed, '<synthetic-transfer-fixture>', 'exec'), namespace)
        namespace['_follow_transition_ownership'] = Mock(return_value=True)
        return namespace

    def test_exact_existing_tuple_roles_and_passed_clock_are_used_without_mutation(self):
        owner = matrix(); samples = states(); before = copy.deepcopy(samples)
        transition = owner.follow_precision_transition
        acceptance_last = transition['lastStates']; original_rate = copy.deepcopy(owner.rate_measurement)
        with patch.object(timing, 'summarize_state', wraps=timing.summarize_state) as summarize:
            timing.retain_transfer_native_timing(owner, samples, 102.5)
        self.assertEqual(samples, before)
        self.assertEqual(owner.rate_measurement, original_rate)
        self.assertIs(transition['lastStates'], acceptance_last)
        self.assertIs(transition['nativeTimingLastStates'], samples)
        self.assertEqual(summarize.call_count, 2)
        authority, follower = summarize.call_args_list
        self.assertIs(authority.args[0], samples[1]); self.assertIs(authority.args[3], samples[2])
        self.assertIs(follower.args[0], samples[2]); self.assertIs(follower.args[3], samples[1])
        self.assertEqual(authority.args[2], 2500); self.assertEqual(follower.args[2], 2500)
        value = transition; basis = value['nativeTimingBasis']
        self.assertEqual(transition['measurement'], {'precisionSamples': 4})
        self.assertEqual(basis, {
            'snapshot': 'existing_transfer_tuple', 'authorityClientOrdinal': 1, 'followerClientOrdinal': 2,
            'capturedCommandElapsedMs': 2500, 'elapsedOrigin': 'before_transfer_command',
            'receiptAttribution': 'unpaired_vendor_receipts',
            'historyElapsedMeaning': 'command_relative_not_new_readiness_origin'})
        self.assertEqual(public.diagnostic_value(basis, timing.TRANSFER_NATIVE_BASIS_SCHEMA), basis)
        for role, ordinal in (('authority', 1), ('follower', 2)):
            row = value['nativeTiming'][role]['clockHistory']['records'][-1]
            self.assertEqual(row['nativePositionMs'], before[ordinal]['nativePlayers'][0]['positionMs'])
            self.assertEqual(row['readinessElapsedMs'], 2500)
            self.assertEqual(row['remainingReadinessBudgetMs'], 7500)
        self.assertEqual(value['nativeTiming']['authority']['clockHistory']['records'][0]['pairedNativeSampleDeltaMs'], -12)

    def test_identical_object_deduplicates_but_new_equal_tuple_counts(self):
        owner = matrix(); samples = states()
        timing.retain_transfer_native_timing(owner, samples, 101)
        first = copy.deepcopy({key: owner.follow_precision_transition[key]
            for key in ('nativeTiming', 'nativeTimingBasis')})
        timing.retain_transfer_native_timing(owner, samples, 109)
        self.assertEqual({key: owner.follow_precision_transition[key] for key in first}, first)
        equal_but_new = list(samples)
        self.assertEqual(equal_but_new, samples); self.assertIsNot(equal_but_new, samples)
        timing.retain_transfer_native_timing(owner, equal_but_new, 109)
        value = owner.follow_precision_transition
        self.assertEqual(value['nativeTiming']['follower']['clockHistory']['count'], 2)
        self.assertEqual(value['nativeTimingBasis']['capturedCommandElapsedMs'], 9000)
        self.assertEqual(first['nativeTiming']['follower']['clockHistory']['count'], 1)

    def test_existing_first_two_last_six_caps_and_disclosed_loss_are_unchanged(self):
        owner = matrix()
        for ordinal in range(1, 13):
            samples = states()
            samples[1]['nativePlayers'][0]['positionMs'] += ordinal
            timing.retain_transfer_native_timing(owner, samples, 100 + ordinal * .5)
        for role in ('authority', 'follower'):
            value = owner.follow_precision_transition['nativeTiming'][role]
            history = value['clockHistory']; clock = value['clockObservation']
            self.assertEqual(history['count'], 12); self.assertEqual(history['dropped'], 4)
            self.assertEqual([row['ordinal'] for row in history['records']], [1, 2, 7, 8, 9, 10, 11, 12])
            for field in ('rateRecords', 'nativeObservations', 'admittedAnchors'):
                self.assertEqual(len(clock[field]), 8)
                self.assertEqual([row['ordinal'] for row in clock[field]], [1, 2, 7, 8, 9, 10, 11, 12])
            self.assertEqual(clock['nativeDropped'], 4)
            self.assertEqual(clock['dartAckReceipt'], 'unavailable')
            self.assertEqual(clock['intervalAttribution'], 'unknown')
            self.assertEqual(history['recoveryArmAge'], 'unavailable')
        self.assertEqual(timing.SCHEMA['seekRecords'][2], 16)
        self.assertEqual(timing.SCHEMA['clockHistory']['records'][2], 8)

    def test_history_counter_saturation_stays_finite(self):
        owner = matrix(); timing.retain_transfer_native_timing(owner, states(), 101)
        for role in ('authority', 'follower'):
            owner.follow_precision_transition['nativeTiming'][role]['clockHistory']['count'] = 65535
        timing.retain_transfer_native_timing(owner, states(), 102)
        for role in ('authority', 'follower'):
            history = owner.follow_precision_transition['nativeTiming'][role]['clockHistory']
            self.assertEqual(history['count'], 65535); self.assertTrue(history['counterCapReached'])
            self.assertEqual(history['dropped'], 65527); self.assertLessEqual(len(history['records']), 8)

    def test_no_additional_clock_file_read_poll_or_control_calls(self):
        owner = matrix(); samples = states()
        with patch('time.monotonic', side_effect=AssertionError('No clock read')), \
                patch('time.time', side_effect=AssertionError('No wall clock read')), \
                patch('time.sleep', side_effect=AssertionError('No sleep')), \
                patch('builtins.open', side_effect=AssertionError('No file read')):
            timing.retain_transfer_native_timing(owner, samples, 102)
        owner.states.assert_not_called(); owner.wait.assert_not_called(); owner.command.assert_not_called()
        calls = [ast.unparse(node.func) for node in ast.walk(ast.parse(inspect.getsource(timing.retain_transfer_native_timing)))
            if isinstance(node, ast.Call)]
        for forbidden in ('time.monotonic', 'time.time', 'time.sleep', 'matrix.states', 'matrix.wait', 'matrix.command', 'open'):
            self.assertNotIn(forbidden, calls)

    def test_nontransfer_and_invalid_outer_inputs_are_exact_noops(self):
        for kind in ('initial', 'rate_change', None, 'PRIVATE-KIND'):
            owner = matrix(kind); transition = owner.follow_precision_transition
            before = dict(transition)
            timing.retain_transfer_native_timing(owner, states(), 102)
            self.assertEqual(transition, before)
        for invalid in (None, [], (), [state()], [state()] * 4):
            owner = matrix(); before = dict(owner.follow_precision_transition)
            timing.retain_transfer_native_timing(owner, invalid, 102)
            self.assertEqual(owner.follow_precision_transition, before)
        for now, origin in ((float('nan'), 100), (float('inf'), 100), (True, 100),
                            (99, 100), (1000, 100), (102, float('nan')), (102, True)):
            owner = matrix(); owner.follow_precision_transition['origin'] = origin
            before = dict(owner.follow_precision_transition)
            timing.retain_transfer_native_timing(owner, states(), now)
            self.assertEqual(owner.follow_precision_transition, before)
        for invalid in (None, [], 'PRIVATE', 1):
            owner = SimpleNamespace(follow_precision_transition=invalid)
            timing.retain_transfer_native_timing(owner, states(), 102)
            self.assertIs(owner.follow_precision_transition, invalid)

    def test_unknown_private_and_nonfinite_native_data_never_escape(self):
        for malformed in (None, {}, {'nativePlayers': 'PRIVATE'}, {'nativePlayers': [None]},
                          {'nativePlayers': [{'timingObservation': {'samplerCalls': True}}]}):
            owner = matrix(); samples = [state(0), malformed, state(2)]
            timing.retain_transfer_native_timing(owner, samples, 102)
            result = {key: owner.follow_precision_transition[key] for key in ('nativeTiming', 'nativeTimingBasis')}
            self.assertIn(result['nativeTiming']['authority']['status'], ('unavailable', 'malformed'))
            json.dumps(result, allow_nan=False)
        owner = matrix(); samples = states()
        samples[1]['privateIdentity'] = 'PRIVATE-TOKEN'
        samples[1]['nativePlayers'][0]['timingObservation']['seeks'][0]['invocation']['path'] = 'PRIVATE-PATH'
        samples[2]['nativePlayers'][0]['positionMs'] = float('nan')
        samples[2]['nativePlayers'][0]['timingObservation']['clockObservation']['native'][0]['monoBeforeMs'] = float('inf')
        timing.retain_transfer_native_timing(owner, samples, 102)
        result = {key: owner.follow_precision_transition[key] for key in ('nativeTiming', 'nativeTimingBasis')}; encoded = json.dumps(result, allow_nan=False)
        for private in ('PRIVATE', 'wallBeforeMs', 'monoBeforeMs', 'sampledAtMs'):
            self.assertNotIn(private, encoded)
        with patch.dict(public.RATE_SCHEMA, SCHEMA_ADDITIONS):
            self.assertEqual(public.diagnostic_value(result, public.RATE_SCHEMA), result)

    def test_synthetic_hook_inverse_is_byte_exact_with_all_original_assertions(self):
        with patch.object(timing, 'HARNESS_SHA', timing.digest(SYNTHETIC_HARNESS)):
            observed = timing.patch_harness(SYNTHETIC_HARNESS)
            self.assertEqual(timing.restore_harness(observed), SYNTHETIC_HARNESS)
            for changed in (observed.replace(b'retain_transfer_native_timing(matrix, states, now)',
                                            b'retain_transfer_native_timing(matrix, states, time.monotonic())'),
                            observed.replace(b"now >= transition['deadline']", b"now > transition['deadline']")):
                with self.assertRaises(ValueError): timing.restore_harness(changed)
        original, updated = ast.parse(SYNTHETIC_HARNESS), ast.parse(observed)
        self.assertEqual([ast.dump(node) for node in ast.walk(original) if isinstance(node, ast.Assert)],
                         [ast.dump(node) for node in ast.walk(updated) if isinstance(node, ast.Assert)])
        before_recorder = next(node for node in ast.walk(original)
            if isinstance(node, ast.FunctionDef) and node.name == 'record_follow_condition')
        after_recorder = copy.deepcopy(next(node for node in ast.walk(updated)
            if isinstance(node, ast.FunctionDef) and node.name == 'record_follow_condition'))
        branch = next(node for node in ast.walk(after_recorder) if isinstance(node, ast.If))
        self.assertEqual(ast.unparse(branch.body[-1]), 'emit_transfer_first_failure(self)')
        self.assertIsInstance(branch.body[-2], ast.Assign)
        branch.body.pop()
        self.assertEqual(ast.dump(before_recorder), ast.dump(after_recorder))
        for name in ('follow_precision_sample', 'begin_follow_precision_transition'):
            before = next(node for node in ast.walk(original) if isinstance(node, ast.FunctionDef) and node.name == name)
            after = next(node for node in ast.walk(updated) if isinstance(node, ast.FunctionDef) and node.name == name)
            self.assertEqual(ast.dump(before), ast.dump(after))

    def test_hook_retains_pending_and_exact_deadline_tuple_before_failure(self):
        namespace = self.observe_namespace(110.0); owner = matrix(); samples = states()
        owner.last = samples
        acceptance_last = owner.follow_precision_transition['lastStates']
        with self.assertRaises(namespace['FollowPrecisionDeadline']):
            namespace['observe_follow_precision_transition'](owner, samples)
        namespace['time'].monotonic.assert_called_once_with()
        namespace['_follow_transition_ownership'].assert_called_once_with(owner.follow_precision_transition, samples)
        precision = owner.follow_observation['precision']
        self.assertNotIn('nativeTiming', precision)
        self.assertEqual(owner.follow_precision_transition['nativeTimingBasis']['capturedCommandElapsedMs'], 10000)
        self.assertEqual(precision['convergenceElapsedMs'], 10000)
        self.assertEqual(precision['convergenceState'], 'pending')
        self.assertIs(owner.follow_precision_transition['lastStates'], acceptance_last)
        self.assertFalse(owner.follow_precision_transition['settled'])
        namespace['time'].monotonic.return_value = 102
        namespace['observe_follow_precision_transition'](owner, states())
        self.assertEqual(owner.follow_precision_transition['nativeTiming']['follower']['clockHistory']['count'], 2)
        self.assertIsNone(owner.follow_precision_transition['candidate'])

    def test_reducer_fault_preserves_deadline_and_emits_no_private_or_stale_tape(self):
        namespace = self.observe_namespace(110.0); owner = matrix()
        old_samples = states(); timing.retain_transfer_native_timing(owner, old_samples, 101)
        samples = states(); owner.last = samples
        owner.follow_conditions = {}; owner.follow_first_failure = None
        with patch.object(timing, 'summarize_state', side_effect=RuntimeError('PRIVATE-ERROR')):
            with self.assertRaises(namespace['FollowPrecisionDeadline']):
                namespace['observe_follow_precision_transition'](owner, samples)
        transition = owner.follow_precision_transition
        self.assertIs(transition['nativeTimingLastStates'], samples)
        self.assertEqual(transition['nativeTimingBasis']['capturedCommandElapsedMs'], 10000)
        self.assertIsNone(transition['nativeTiming'])
        before = copy.deepcopy(owner.follow_observation); stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            namespace['Matrix'].record_follow_condition(owner, 'lab_ten_second_convergence', False)
        record = json.loads(stream.getvalue()); evidence = record['transferNativeTiming']
        self.assertEqual(evidence['evidenceStatus'], 'malformed')
        self.assertNotIn('nativeTiming', evidence); self.assertNotIn('association', evidence)
        self.assertNotIn('PRIVATE', stream.getvalue()); self.assertNotIn('oldAlignment', stream.getvalue())
        self.assertEqual(owner.follow_first_failure['observation'], before)
        json.dumps(record, allow_nan=False)

    def test_owned_identity_rejection_still_precedes_clock_and_observation(self):
        namespace = self.observe_namespace(); owner = matrix(); samples = states()
        namespace['_follow_transition_ownership'].side_effect = namespace['FollowPrecisionUnsafe']('synthetic rejection')
        with self.assertRaises(namespace['FollowPrecisionUnsafe']):
            namespace['observe_follow_precision_transition'](owner, samples)
        namespace['time'].monotonic.assert_not_called()
        self.assertNotIn('nativeTiming', owner.follow_precision_transition['measurement'])
        self.assertNotIn('nativeTimingLastStates', owner.follow_precision_transition)

    def test_settled_precision_failure_retains_exact_failed_native_tuple(self):
        namespace = self.observe_namespace(105.0); owner = matrix(); samples = states()
        owner.last = samples
        transition = owner.follow_precision_transition
        transition.update(settled=True, settledAt=102.0, context='synthetic-context', expected=1.5,
            newAuthority=('synthetic-authority', 'synthetic-generation'), newCursors=(1, 1, 1),
            identity=('synthetic-correction',), lastPair=None)
        acceptance_last = transition['lastStates']
        namespace['_follow_transition_ownership'].return_value = False
        namespace['_follow_canonical_identity'] = lambda *_: (transition['newAuthority'], transition['newCursors'])
        namespace['follow_correction_identity'] = lambda *_: transition['identity']
        namespace['native_follow_task_ready'] = lambda *_: True
        namespace['decoded'] = lambda value: value['nativePlayers'][0]
        namespace['aligned_drift'] = lambda *_: (70, 4)
        namespace['numeric_native_snapshot'] = lambda value: {
            key: field for key, field in value.items() if key in public.NATIVE_SCHEMA}
        namespace['follow_nominal_precision_ready'] = lambda *_: True
        owner.follow_conditions = {}; owner.follow_first_failure = None
        with self.assertRaises(AssertionError):
            namespace['observe_follow_precision_transition'](owner, samples)
        namespace['time'].monotonic.assert_called_once_with()
        self.assertIs(transition['lastStates'], acceptance_last)
        self.assertEqual(transition['measurement']['precisionDriftMs'], 70)
        self.assertEqual(transition['measurement']['precisionWorstCaseMs'], 75)
        unchanged = copy.deepcopy(owner.follow_observation)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            namespace['Matrix'].record_follow_condition(owner, 'steady_sample_precision', False)
        frozen = copy.deepcopy(owner.follow_first_failure)
        self.assertEqual(frozen['observation'], unchanged)
        self.assertNotIn('nativeTiming', frozen['observation']['precision'])
        evidence = json.loads(stream.getvalue())['transferNativeTiming']
        self.assertEqual(evidence['evidenceStatus'], 'observed')
        self.assertEqual(evidence['nativeTimingBasis']['capturedCommandElapsedMs'], 5000)
        for role, ordinal in (('authority', 1), ('follower', 2)):
            self.assertEqual(evidence['nativeTiming'][role]['clockHistory']['records'][-1]['nativePositionMs'],
                             samples[ordinal]['nativePlayers'][0]['positionMs'])
        timing.retain_transfer_native_timing(owner, states(), 106)
        owner.follow_observation.clear(); owner.rate_measurement = {'expectedRate': .8}
        self.assertEqual(owner.follow_first_failure, frozen)

    def test_malformed_previous_history_does_not_leak_or_expand_retention(self):
        owner = matrix()
        owner.follow_precision_transition['nativeTiming'] = {
            'authority': {'private': 'PRIVATE', 'clockHistory': {'count': True,
                'records': [{'ordinal': 1, 'private': 'PRIVATE', 'nativePositionMs': float('nan')}] * 9}},
            'follower': ['PRIVATE']}
        timing.retain_transfer_native_timing(owner, states(), 102)
        tape = owner.follow_precision_transition['nativeTiming']
        for role in ('authority', 'follower'):
            self.assertEqual(tape[role]['clockHistory']['count'], 1)
            self.assertEqual(len(tape[role]['clockHistory']['records']), 1)
        self.assertNotIn('PRIVATE', json.dumps(tape, allow_nan=False))

    def test_failed_tuple_json_copy_and_emitted_text_survive_later_overwrites(self):
        namespace = self.observe_namespace(110.0); owner = matrix(); samples = states()
        owner.last = samples; owner.follow_conditions = {}; owner.follow_first_failure = None
        with self.assertRaises(namespace['FollowPrecisionDeadline']):
            namespace['observe_follow_precision_transition'](owner, samples)
        unchanged = copy.deepcopy(owner.follow_observation)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            namespace['Matrix'].record_follow_condition(owner, 'steady_sample_precision', False)
        frozen = copy.deepcopy(owner.follow_first_failure); emitted = stream.getvalue()
        self.assertEqual(frozen['observation'], unchanged)
        evidence = json.loads(emitted)['transferNativeTiming']
        self.assertEqual(evidence['nativeTimingBasis']['capturedCommandElapsedMs'], 10000)
        self.assertEqual(evidence['nativeTiming']['authority']['clockHistory']['records'][-1]['nativePositionMs'],
                         samples[1]['nativePlayers'][0]['positionMs'])
        samples[1]['nativePlayers'][0]['positionMs'] = 99999
        timing.retain_transfer_native_timing(owner, states(), 111)
        owner.follow_precision_transition['nativeTiming']['authority']['clockHistory']['records'][-1]['nativePositionMs'] = 88888
        owner.rate_measurement = {'expectedRate': .8}; owner.follow_precision_transition = None
        owner.follow_observation = {'safety': {'exactNativeFollowTask': False}}
        with contextlib.redirect_stdout(stream):
            namespace['Matrix'].record_follow_condition(owner, 'restoration', False)
        self.assertEqual(owner.follow_first_failure, frozen)
        self.assertEqual(stream.getvalue(), emitted)
        self.assertNotIn('oldAlignment', emitted)
        self.assertNotIn('nativeTiming', frozen['observation']['precision'])

    def test_basis_unknown_values_wrong_types_and_nonfinite_values_fail_closed(self):
        owner = matrix(); timing.retain_transfer_native_timing(owner, states(), 102)
        basis = owner.follow_precision_transition['nativeTimingBasis']
        for key, invalid in (('snapshot', 'PRIVATE'), ('authorityClientOrdinal', 0),
            ('authorityClientOrdinal', True), ('followerClientOrdinal', 1),
            ('capturedCommandElapsedMs', float('inf')), ('elapsedOrigin', 'new_readiness_origin'),
            ('receiptAttribution', 'paired'), ('historyElapsedMeaning', 'causal')):
            dirty = dict(basis, **{key: invalid, 'private': 'SECRET'})
            clean = public.diagnostic_value(dirty, timing.TRANSFER_NATIVE_BASIS_SCHEMA)
            self.assertEqual(clean, {field: value for field, value in basis.items() if field != key})

    def emit(self, owner):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            timing.emit_transfer_first_failure(owner)
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertLessEqual(len(lines[0].encode('utf-8')), timing.TRANSFER_RECORD_BYTE_LIMIT)
        return json.loads(lines[0]), lines[0]

    def associated_failure(self):
        owner = matrix(); owner.last = states()
        timing.retain_transfer_native_timing(owner, owner.last, 102)
        owner.follow_first_failure = {'condition': 'steady_sample_precision', 'observation': {
            'precision': {'convergenceKind': 'transfer', 'convergenceOrigin': 'before_transfer_command',
                'convergenceElapsedMs': 2500}}}
        return owner

    def test_side_record_metadata_and_older_deduplicated_capture_are_explicit(self):
        owner = self.associated_failure(); failure = copy.deepcopy(owner.follow_first_failure)
        timing.retain_transfer_native_timing(owner, owner.last, 102.5)
        record, text = self.emit(owner); evidence = record['transferNativeTiming']
        self.assertEqual(record['stage'], 'transfer-first-failure-native-timing')
        self.assertEqual(record['status'], 'not-verified')
        self.assertEqual({key: evidence[key] for key in ('recordOrdinal', 'firstFailureOrdinal',
            'recordCountLimit', 'recordByteLimit', 'condition', 'evidenceStatus', 'association')}, {
            'recordOrdinal': 1, 'firstFailureOrdinal': 1, 'recordCountLimit': 1, 'recordByteLimit': 262144,
            'condition': 'steady_sample_precision', 'evidenceStatus': 'observed',
            'association': 'same_first_failure_tuple'})
        self.assertEqual(evidence['failureObservationElapsedMs'], 2500)
        self.assertEqual(evidence['nativeTimingBasis']['capturedCommandElapsedMs'], 2000)
        self.assertEqual(evidence['nativeTiming']['authority']['clockHistory']['count'], 1)
        self.assertEqual(owner.follow_first_failure, failure)
        self.assertTrue(timing._transfer_schema_valid(evidence, timing.TRANSFER_RECORD_SCHEMA))
        self.assertEqual(text, json.dumps(record, separators=(',', ':'), allow_nan=False))

    def test_side_record_never_substitutes_old_alignment_or_wrong_tuple(self):
        cases = (
            ('missing_precision', 'unavailable'), ('wrong_transition', 'unavailable'),
            ('equal_but_new_tuple', 'mismatch'), ('wrong_kind', 'mismatch'),
            ('wrong_origin', 'mismatch'), ('capture_after_failure', 'mismatch'),
            ('nonfinite_elapsed', 'mismatch'), ('missing_tape', 'malformed'),
        )
        for case, expected in cases:
            with self.subTest(case=case):
                owner = self.associated_failure(); precision = owner.follow_first_failure['observation']['precision']
                if case == 'missing_precision': owner.follow_first_failure['observation'] = {'safety': {}}
                elif case == 'wrong_transition': owner.follow_precision_transition['kind'] = 'rate_change'
                elif case == 'equal_but_new_tuple': owner.last = list(owner.last)
                elif case == 'wrong_kind': precision['convergenceKind'] = 'initial'
                elif case == 'wrong_origin': precision['convergenceOrigin'] = 'observed_task_ready'
                elif case == 'capture_after_failure': precision['convergenceElapsedMs'] = 1000
                elif case == 'nonfinite_elapsed': precision['convergenceElapsedMs'] = float('nan')
                elif case == 'missing_tape': owner.follow_precision_transition.pop('nativeTiming')
                evidence = self.emit(owner)[0]['transferNativeTiming']
                self.assertEqual(evidence['evidenceStatus'], expected)
                for key in ('nativeTiming', 'nativeTimingBasis', 'association'): self.assertNotIn(key, evidence)
                self.assertNotIn('oldAlignment', json.dumps(evidence, allow_nan=False))

    def test_unknown_overcap_and_nonfinite_projection_fields_reject_not_filter(self):
        for edit in ('private_key', 'unknown_enum', 'nonfinite', 'too_many_records', 'wrong_bool'):
            with self.subTest(edit=edit):
                owner = self.associated_failure(); tape = owner.follow_precision_transition['nativeTiming']['authority']
                if edit == 'private_key': tape['private'] = 'PRIVATE'
                elif edit == 'unknown_enum': tape['status'] = 'PRIVATE'
                elif edit == 'nonfinite': tape['clockHistory']['records'][0]['nativePositionMs'] = float('inf')
                elif edit == 'too_many_records': tape['clockHistory']['records'] *= 9
                elif edit == 'wrong_bool': tape['clockHistory']['count'] = True
                evidence = self.emit(owner)[0]['transferNativeTiming']
                self.assertEqual(evidence['evidenceStatus'], 'malformed')
                self.assertNotIn('nativeTiming', evidence); self.assertNotIn('association', evidence)
                self.assertNotIn('PRIVATE', json.dumps(evidence))

    def test_emission_count_cap_survives_duplicates_and_new_transitions(self):
        owner = self.associated_failure(); record, first = self.emit(owner)
        owner.follow_precision_transition = self.associated_failure().follow_precision_transition
        owner.follow_first_failure['condition'] = 'restoration'
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            timing.emit_transfer_first_failure(owner); timing.emit_transfer_first_failure(owner)
        self.assertEqual(stream.getvalue(), '')
        self.assertEqual(record['transferNativeTiming']['recordCountLimit'], 1)
        self.assertEqual(timing.TRANSFER_RECORD_COUNT_LIMIT, 1)
        self.assertEqual(timing.TRANSFER_RECORD_BYTE_LIMIT, 262144)

    def test_forced_size_fallback_is_explicit_bounded_and_unassociated(self):
        owner = self.associated_failure()
        # Exercise the defensive branch without changing the deployed byte limit.
        with patch.object(timing, 'TRANSFER_RECORD_BYTE_LIMIT', 1024):
            record, text = self.emit(owner)
        evidence = record['transferNativeTiming']
        self.assertEqual(evidence['evidenceStatus'], 'oversized')
        self.assertEqual(evidence['recordByteLimit'], 1024)
        for key in ('nativeTiming', 'nativeTimingBasis', 'association'): self.assertNotIn(key, evidence)
        self.assertLessEqual(len(text.encode('utf-8')), 1024)
        self.assertEqual(timing.TRANSFER_RECORD_BYTE_LIMIT, 262144)

    def test_print_failure_cannot_mask_original_assertion_or_retry(self):
        owner = self.associated_failure()
        with patch('builtins.print', side_effect=OSError('PRIVATE')) as output:
            timing.emit_transfer_first_failure(owner)
            timing.emit_transfer_first_failure(owner)
        output.assert_called_once()
        self.assertTrue(owner._transfer_native_first_failure_emitted)

    def test_full_final_envelope_and_separate_saturated_record_are_lossless_within_caps(self):
        main = final_failure_envelope(include_nested=False); unchanged = copy.deepcopy(main)
        owner = self.associated_failure()
        owner.follow_precision_transition['nativeTiming'] = filled(SCHEMA_ADDITIONS['nativeTiming'])
        owner.follow_precision_transition['nativeTimingBasis'] = filled(timing.TRANSFER_NATIVE_BASIS_SCHEMA)
        owner.follow_first_failure['observation']['precision']['convergenceElapsedMs'] = 600000
        side, emitted = self.emit(owner)
        self.assertEqual(side['transferNativeTiming']['evidenceStatus'], 'observed')
        self.assertEqual(main, unchanged)
        with patch.object(public, 'PUBLIC_STAGES', public.PUBLIC_STAGES | {timing.TRANSFER_RECORD_STAGE}), \
                patch.dict(public.DIAGNOSTIC_SCHEMA, {'transferNativeTiming': timing.TRANSFER_RECORD_SCHEMA}):
            for record in (side, main):
                self.assertEqual(public.report_line(json.dumps(record)), record)
                lines = compact.CompactNativeExportTests().execute_record(record, code=1)
                self.assertEqual(json.loads(lines[0]), record)
                self.assertEqual(lines[0], json.dumps(public.report_line(json.dumps(record)), separators=(',', ':'), allow_nan=False))
                self.assertLessEqual(len(lines[0].encode('utf-8')), 512 * 1024)
        self.assertLessEqual(len(emitted.encode('utf-8')), 262144)
        # Exercise actual execute with both records in one failed-command log.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'source').mkdir(); output = io.StringIO()
            def run(command, **kwargs):
                self.assertEqual(command, ['synthetic-transfer-command'])
                kwargs['stdout'].write((emitted + '\n' + json.dumps(main) + '\nPRIVATE RAW LOG\n').encode())
                return SimpleNamespace(returncode=1)
            with patch.object(public, 'PUBLIC_STAGES', public.PUBLIC_STAGES | {timing.TRANSFER_RECORD_STAGE}), \
                    patch.dict(public.DIAGNOSTIC_SCHEMA, {'transferNativeTiming': timing.TRANSFER_RECORD_SCHEMA}), \
                    patch.object(public.p, 'ROOT', root), patch.object(public, 'native_env', return_value={}), \
                    patch.object(public.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(output):
                with self.assertRaises(public.p.GateError):
                    public.execute(['synthetic-transfer-command'], 'follow', report=True)
            lines = output.getvalue().splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual([json.loads(line) for line in lines],
                [side, main, {'stage': 'follow', 'status': 'failed', 'exitCode': 1}])
            self.assertEqual(len(lines[0].encode('utf-8')), len(emitted.encode('utf-8')))
            self.assertTrue(all(len(line.encode('utf-8')) <= 512 * 1024 for line in lines))
            self.assertNotIn('PRIVATE', output.getvalue())
        self.assertEqual(set(main), set(unchanged))
        self.assertNotIn('nativeTiming', main['followFirstFailure']['observation']['precision'])
        self.assertEqual(len(main['followLifecycle']['ownedLog']['correctionSequence']['records']), 128)
        for client in main['followLifecycle']['endpointTiming']['clients']:
            self.assertEqual(len(client['recoveryChecks']['records']), 129)
            self.assertEqual(len(client['playPolicy']['records']), 33)
            self.assertEqual(len(client['recoveryAdmission']['summaries']), 4)
        for key in ('handoffDiagnostics', 'handoffBeforeStart'):
            self.assertEqual(len(main[key]), 3)
            self.assertTrue(all(len(client['handoffHistory']) == 8 for client in main[key]))
        for role in ('authority', 'follower'):
            tape = side['transferNativeTiming']['nativeTiming'][role]
            self.assertEqual(len(tape['seekRecords']), 16)
            self.assertEqual(len(tape['clockHistory']['records']), 8)
            for field in ('rateRecords', 'nativeObservations', 'admittedAnchors'):
                self.assertEqual(len(tape['clockObservation'][field]), 8)

    def test_prior_nested_full_failure_is_demonstrably_over_512_kib(self):
        record = final_failure_envelope()
        with patch.dict(public.RATE_SCHEMA, SCHEMA_ADDITIONS):
            self.assertEqual(public.report_line(json.dumps(record)), record)
            dirty = copy.deepcopy(record)
            dirty['privateRaw'] = 'PRIVATE' * 100000
            dirty['followFirstFailure']['observation']['precision']['privateIdentity'] = 'PRIVATE'
            lines = compact.CompactNativeExportTests().execute_record(dirty, code=1)
            exported = json.loads(lines[0])
            self.assertEqual(exported, record)
            self.assertEqual(lines[0], json.dumps(public.report_line(json.dumps(record)), separators=(',', ':'), allow_nan=False))
        self.assertEqual(json.loads(lines[1]), {'stage': 'follow', 'status': 'failed', 'exitCode': 1})
        self.assertNotIn('PRIVATE', lines[0])
        lifecycle = exported['followLifecycle']
        self.assertEqual(len(lifecycle['ownedLog']['correctionSequence']['records']), 128)
        self.assertEqual(len(lifecycle['endpointTiming']['clients']), 3)
        for client in lifecycle['endpointTiming']['clients']:
            self.assertEqual(len(client['recoveryChecks']['records']), 129)
            self.assertEqual(len(client['playPolicy']['records']), 33)
            self.assertEqual(len(client['recoveryAdmission']['summaries']), 4)
        self.assertEqual(len(exported['handoffDiagnostics']), 3)
        self.assertEqual(len(exported['handoffBeforeStart']), 3)
        for key in ('handoffDiagnostics', 'handoffBeforeStart'):
            self.assertTrue(all(len(client['handoffHistory']) == 8 for client in exported[key]))
        tape = exported['followFirstFailure']['observation']['precision']['nativeTiming']
        for role in ('authority', 'follower'):
            self.assertEqual(len(tape[role]['seekRecords']), 16)
            self.assertEqual(len(tape[role]['clockHistory']['records']), 8)
            for field in ('rateRecords', 'nativeObservations', 'admittedAnchors'):
                self.assertEqual(len(tape[role]['clockObservation'][field]), 8)
        size = len(lines[0].encode('utf-8'))
        self.assertEqual(size, 541563)
        self.assertGreater(size, 512 * 1024, 'The oversized nested witness must remain visible.')


if __name__ == '__main__':
    unittest.main()
