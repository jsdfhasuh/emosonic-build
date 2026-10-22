import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'native_seek_anchor_observation.py'
if not SCRIPT.is_file(): SCRIPT = ROOT / 'scripts/native_seek_anchor_observation.py'
spec = importlib.util.spec_from_file_location('timing', SCRIPT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def rates(wall=1000000, mono=1000, effective=1.5):
    return {'wallBeforeMs': wall, 'wallAfterMs': wall + 0.1,
            'monoBeforeMs': mono, 'monoAfterMs': mono + 0.1,
            'requestedRate': 1.5, 'nativeRate': 1.5,
            'effectiveRate': effective, 'effectiveAvailable': effective is not None, 'identityMatches': True}


def fixture():
    return {'sampledAtMs': 1000400, 'positionMs': 10450, 'timingObservation': {
        'samplerCalls': 9, 'samplerAdmits': 2, 'samplerRejects': [1, 1, 1, 1, 1, 1, 1],
        'anchorPositionMs': 10000, 'anchorWallMs': 1000100, 'anchorRequestedRate': 1.5,
        'anchorNativeRate': 1.5, 'anchorEffectiveRate': 1.5, 'anchorElapsedMs': 0.2,
        'anchorSamePlaybackIdentity': True,
        'rejectedRequestedRate': 1.5, 'rejectedNativeRate': 1.5, 'rejectedEffectiveRate': 0.0,
        'seekInvocations': 1, 'seekCallbacks': 1, 'seekCompletions': 1,
        'unmatchedCallbacks': 0, 'duplicateCallbacks': 0, 'seeks': [{
            'sequence': 1, 'targetMs': 10000, 'invocation': rates(),
            'callbackSeen': True, 'callbackWallMs': 1000200, 'callbackMonoMs': 1200,
            'completionSeen': True, 'finished': True, 'completion': rates(1000201, 1201, effective=0.0),
        }]}}


class NativeTimingObservation(unittest.TestCase):
    def synthetic_prepared(self, root):
        for relative in (m.PREPARE, m.HARNESS):
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'before')
        return patch.multiple(m, AFTER={m.PREPARE: m.digest(b'after'), m.HARNESS: m.digest(b'after')},
                              patch_prepare=lambda _: b'after', patch_harness=lambda _: b'after')

    def test_prepare_verify_and_payload_only_mode_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.synthetic_prepared(root):
                m.apply(root); self.assertEqual(m.verify_prepared(root), {'status': 'verified'})
                (root / m.HARNESS).write_bytes(b'attribution-after')
                with self.assertRaises(ValueError): m.verify_prepared(root)
                self.assertEqual(m.verify_prepared(root, require_harness=False), {'status': 'verified'})
                (root / m.COPIED_HELPER).write_bytes(b'tampered')
                with self.assertRaises(ValueError): m.verify_prepared(root, require_harness=False)

    def test_manifest_boolean_type_and_empty_keysets_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.synthetic_prepared(root):
                expected = m.apply(root)
                for update in ({}, dict(expected, disposableOnly=1), dict(expected, native={})):
                    (root / m.STATE).write_text(json.dumps(update))
                    with self.assertRaises(ValueError): m.verify_prepared(root)

    def test_dangling_destination_link_rejected_before_source_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.synthetic_prepared(root):
                (root / m.COPIED_HELPER).symlink_to(root / 'missing')
                with self.assertRaises(ValueError): m.apply(root)
                self.assertEqual((root / m.HARNESS).read_bytes(), b'before')
                self.assertEqual((root / m.PREPARE).read_bytes(), b'before')

    def test_snapshot_wrapper_does_not_add_decoder_assertions(self):
        for value in (None, {}, {'nativePlayers': []}, {'nativePlayers': [{}, {}]}, {'nativePlayers': 'bad'}):
            self.assertEqual(m.summarize_state(value), {'status': 'unavailable'})

    def test_snapshot_distinguishes_held_clock_and_actual_seek_latency(self):
        result = m.summarize(fixture(), {'eventPositionMs': 10000, 'eventUpdatedAtMs': 1000100})
        row = result['seekRecords'][0]
        self.assertEqual(row['status'], 'completed')
        self.assertAlmostEqual(row['callbackAfterInvocationMs'], 199.9)
        self.assertAlmostEqual(row['completionAfterInvocationMs'], 200.9)
        self.assertTrue(row['completion']['positiveNominalRateWithHeldClock'])
        self.assertEqual(result['lastAdmittedAnchor']['nativeMinusAnchorProjectionMs'], 0)
        self.assertEqual(result['lastAdmittedAnchor']['dartEventMinusAnchorPositionMs'], 0)
        self.assertEqual(result['desiredTimelineAgeStatus'], 'unavailable')

    def test_missing_effective_rate_is_not_zero(self):
        raw = fixture(); raw['timingObservation']['seeks'][0]['completion'] = rates(1000201, 1201, None)
        result = m.summarize(raw)['seekRecords'][0]['completion']
        self.assertEqual(result['effectiveRateStatus'], 'unavailable')
        self.assertNotIn('positiveNominalRateWithHeldClock', result)

    def test_changed_identity_suppresses_old_seek_rates_and_anchor_projection(self):
        raw = fixture(); raw['timingObservation']['seeks'][0]['completion']['identityMatches'] = False
        raw['timingObservation']['anchorSamePlaybackIdentity'] = False
        result = m.summarize(raw)
        completion = result['seekRecords'][0]['completion']
        self.assertFalse(completion['samePlaybackIdentity'])
        self.assertNotIn('effectiveRate', completion)
        self.assertNotIn('nativeRate', completion)
        self.assertNotIn('nativeMinusAnchorProjectionMs', result['lastAdmittedAnchor'])

    def test_wall_clock_step_and_backwards_monotonic_are_not_latency(self):
        for key, value in [('wallBeforeMs', 1001201), ('monoAfterMs', 1), ('wallBeforeMs', float('nan'))]:
            raw = fixture(); raw['timingObservation']['seeks'][0]['completion'][key] = value
            row = m.summarize(raw)['seekRecords'][0]
            self.assertEqual(row['status'], 'invalid_clock_bracket')
            self.assertNotIn('completionAfterInvocationMs', row)

    def test_privacy_and_unknown_values_never_escape(self):
        raw = fixture(); raw['privateToken'] = 'SECRET'
        raw['timingObservation']['accountId'] = 'SECRET'
        raw['timingObservation']['seeks'][0]['invocation']['path'] = 'SECRET'
        encoded = json.dumps(m.summarize(raw), allow_nan=False)
        self.assertNotIn('SECRET', encoded)
        self.assertNotIn('wallBeforeMs', encoded)
        self.assertNotIn('monoBeforeMs', encoded)
        raw['timingObservation']['samplerCalls'] = True
        self.assertEqual(m.summarize(raw), {'status': 'malformed'})

    def test_missing_or_wrong_record_sequence_cannot_claim_complete_coverage(self):
        for records in ([], [{'sequence': 2}]):
            raw = fixture(); raw['timingObservation']['seeks'] = records
            self.assertEqual(m.summarize(raw)['seekRecordCoverage'], 'malformed')

    def test_source_pins_and_inverse_fail_closed(self):
        with self.assertRaises(ValueError): m.transform_native(b'wrong', b'wrong')
        with self.assertRaises(ValueError): m.patch_prepare(b'wrong')
        change = m.Transform('original;')
        change.once('original;', 'observation; original;')
        self.assertEqual(change.finish(), 'observation; original;')
        with self.assertRaises(ValueError): change.once('missing', 'other')

    def test_payload_no_new_position_read_or_event_emission(self):
        body = m.payload('lab_timing_native.inc') + m.payload('lab_timing_getters.inc')
        for token in ('currentTime', 'getCurrentPosition', 'broadcastPlaybackEvent', 'seekToTime', 'dispatch_after'):
            self.assertNotIn(token, body)
        self.assertEqual(body.count('CMTimebaseGetEffectiveRate('), 1)
        self.assertEqual(body.count('CFRetain(timebase)'), 1)
        self.assertEqual(body.count('CFRelease(timebase)'), 1)

    def test_actual_c_state_retains_overlaps_and_bounds_ring_counters(self):
        code = m.payload('lab_timing_state.h') + r'''
#include <assert.h>
int main(void) {
    LabTimingState state = {0};
    LabTimingRates rates = {.requestedRate=1.5, .nativeRate=0, .effectiveRate=0};
    unsigned a = LabTimingBegin(&state, 10000, rates);
    unsigned b = LabTimingBegin(&state, 11000, rates);
    LabTimingCallback(&state, b, 1300, 1300);
    LabTimingComplete(&state, b, true, rates);
    LabTimingCallback(&state, a, 1400, 1400);
    LabTimingComplete(&state, a, false, rates);
    assert(state.seeks[0].completionSeen && !state.seeks[0].finished);
    assert(state.seeks[1].completionSeen && state.seeks[1].finished);
    assert(state.seeks[0].targetMs == 10000 && state.seeks[1].targetMs == 11000);
    LabTimingCallback(&state, a, 1500, 1500);
    assert(state.duplicateCallbacks == 1);
    for (unsigned i=0; i<LAB_TIMING_RECORDS; ++i) LabTimingBegin(&state, i, rates);
    LabTimingCallback(&state, a, 1600, 1600);
    assert(state.unmatchedCallbacks == 1);
    for (unsigned i=0; i<70000; ++i) LabTimingIncrement(&state.samplerCalls);
    assert(state.samplerCalls == LAB_TIMING_LIMIT);
    state.seekInvocations = LAB_TIMING_LIMIT;
    assert(LabTimingBegin(&state, 1, rates) == 0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'state.c'; output = Path(tmp) / 'state'
            source.write_text(code)
            build = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(output)],
                                   capture_output=True)
            self.assertEqual(build.returncode, 0, 'Synthetic C state compilation failed')
            self.assertEqual(subprocess.run([str(output)], capture_output=True).returncode, 0)

    def test_real_output_satisfies_declared_closed_schema(self):
        def check(value, schema):
            if type(schema) is dict:
                self.assertIs(type(value), dict)
                self.assertTrue(set(value) <= set(schema))
                for key in value: check(value[key], schema[key])
            elif schema is bool: self.assertIs(type(value), bool)
            elif type(schema) is frozenset: self.assertIn(value, schema)
            elif schema[0] == 'list':
                self.assertLessEqual(len(value), schema[2])
                for item in value: check(item, schema[1])
            else:
                self.assertTrue(m.number(value, schema[1], schema[2]))
                if schema[0] == 'integer': self.assertIs(type(value), int)
        check(m.summarize(fixture()), m.SCHEMA)


if __name__ == '__main__': unittest.main()
