"""Finite synthetic tests of the actual raw-native interval acceptance helper.

No native execution, private source, network, polling, control, or clock reads.
The raw points and corresponding public snapshots are constructed together;
rounding noise is not represented as physical motion.
"""
import ast
import copy
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'scripts/native_follow_readiness_payload'


def llround(value):
    """C llround for the nonnegative finite values in these fixtures."""
    floor = math.floor(value)
    return floor + (value - floor >= .5)


def raw_point(position, mono, *, wall=None, width=.01, sequence=1,
              owner=1, rate_sequence=1, seek_sequence=0, expected=1.5):
    if wall is None:
        wall = 1_000_000 + mono - 1000
    end, wall_end = mono + width, wall + width
    rates = dict(wallBeforeMs=wall_end + .005, wallAfterMs=wall_end + .01,
        monoBeforeMs=end + .005, monoAfterMs=end + .01,
        requestedRate=expected, nativeRate=expected, effectiveRate=expected,
        effectiveAvailable=True, effectiveReadCount=1, identityMatches=True,
        owner=owner, playingIntent=True, seeking=False, processingState=3,
        timeControl=2)
    return dict(sequence=sequence, owner=owner, rateSequence=rate_sequence,
        seekSequence=seek_sequence, positionMs=position, positionValid=True,
        wallBeforeMs=wall, wallAfterMs=wall_end, monoBeforeMs=mono,
        monoAfterMs=end, rates=rates)


def snapshot(point, *, identifier='synthetic-player', earlier=()):
    """Bind exactly the public fields emitted for this same native read."""
    return dict(id=identifier, positionMs=llround(point['positionMs']),
        sampledAtMs=llround((point['wallBeforeMs'] + point['wallAfterMs']) / 2),
        sampleUncertaintyMs=(point['wallAfterMs'] - point['wallBeforeMs']) / 2 + 1,
        playbackState=3, playbackRate=point['rates']['nativeRate'],
        requestedRate=point['rates']['requestedRate'], playingIntent=True,
        seekInProgress=False, durationMs=180000, avPlayerStatus=1, avItemStatus=1,
        avTimeControlStatus=2, errorCode=0,
        timingObservation={'seekInvocations': point['seekSequence'], 'clockObservation': dict(nativeCount=point['sequence'],
            ownerCount=point['owner'], rateCount=point['rateSequence'],
            anchorCount=0, unmatchedReplies=0, rates=[], anchors=[],
            native=[copy.deepcopy(value) for value in (*earlier, point)])})


def point_of(native):
    return native['timingObservation']['clockObservation']['native'][-1]


def bind_public(native):
    """Update only the three native snapshot fields when raw evidence changes."""
    point = point_of(native)
    native.update(positionMs=llround(point['positionMs']),
        sampledAtMs=llround((point['wallBeforeMs'] + point['wallAfterMs']) / 2),
        sampleUncertaintyMs=(point['wallAfterMs'] - point['wallBeforeMs']) / 2 + 1)


def interval(*, expected=1.5, position=10000.25, dt=6.25, delta=None,
             width=.01, mono=1000.125, wall=1_000_000.125):
    if delta is None:
        delta = expected * dt
    old = raw_point(position, mono, wall=wall, width=width, expected=expected)
    new = raw_point(position + delta, mono + dt, wall=wall + dt,
        width=width, sequence=2, expected=expected)
    return snapshot(old), snapshot(new, earlier=(old,))


def load_helpers():
    """Execute the shipped acceptance methods, not a test copy of them."""
    def decoded(state):
        return state['nativePlayers'][0]

    def rate_matches(state, expected, follower=False):
        value = decoded(state).get('playbackRate')
        return (type(value) in (int, float) and math.isfinite(value)
            and abs(value - expected) < (expected * .04001 if follower else .0001))

    def drift(authority, follower):
        a, f = decoded(authority), decoded(follower)
        elapsed = f['sampledAtMs'] - a['sampledAtMs']
        return (f['positionMs'] - a['positionMs'] - elapsed * a['playbackRate'],
            (a['sampleUncertaintyMs'] + f['sampleUncertaintyMs']) * a['playbackRate'])

    clock = SimpleNamespace(monotonic=Mock(side_effect=AssertionError('Unexpected clock read')),
        time=Mock(side_effect=AssertionError('Unexpected wall-clock read')),
        sleep=Mock(side_effect=AssertionError('Unexpected sleep')))
    ns = dict(math=math, time=clock, decoded=decoded,
        native_requested_rate=lambda s: decoded(s)['requestedRate'],
        native_rate_matches=rate_matches,
        follow_native_rate_bounds=lambda s, e: (e * .96, e * 1.04),
        native_follow_task_ready=lambda a, f, c: a.get('_taskReady', True) and f.get('_taskReady', True),
        aligned_drift=drift, numeric_native_snapshot=lambda native: {
            key: native[key] for key in ('positionMs', 'sampledAtMs', 'playbackRate')})
    for filename in ('follow_readiness_helpers.py', 'follow_precision_helpers.py'):
        exec(compile((PAYLOAD / filename).read_text(), str(PAYLOAD / filename), 'exec'), ns)
    return ns


def state_tuple(authority, follower):
    spec = importlib.util.spec_from_file_location('interval_readiness_fixture', PAYLOAD / 'readiness_contract.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    states = fixture.pair(0)
    for index, native in ((0, authority), (2, follower)):
        states[index]['followSyncToleranceMs'] = 50
        states[index]['nativePlayers'][0] = copy.deepcopy(native)
        states[index]['nativePlayers'][0]['id'] = 'synthetic-authority' if index == 0 else 'synthetic-follower'
    return states


class NativeIntervalPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_helpers()
        self.check = self.ns['follow_native_interval_rate']
        self.assertTrue(self.check(*interval(), 1.5), 'Baseline raw fixture must be admissible')

    def reject(self, old, current, expected=1.5):
        # Both an explicit False and an assertion are fail-closed outcomes.
        try:
            result = self.check(old, current, expected)
        except AssertionError:
            return
        self.assertFalse(result, 'Invalid raw evidence was accepted')

    def sample(self, old, current, *, expected=1.5, mutate=None):
        previous_states = state_tuple(old, old)
        states = state_tuple(current, current)
        identity = self.ns['follow_correction_identity'](previous_states, 0, 'authority-context')
        matrix = SimpleNamespace(rate_measurement={},
            states=Mock(side_effect=AssertionError('Unexpected state read')),
            wait=Mock(side_effect=AssertionError('Unexpected polling')),
            command=Mock(side_effect=AssertionError('Unexpected control')))
        previous = self.ns['follow_precision_sample'](matrix, previous_states, 0,
            'authority-context', expected, identity)
        if mutate:
            mutate(states)
        result = self.ns['follow_precision_sample'](matrix, states, 0,
            'authority-context', expected, identity, previous)
        return result, matrix

    def test_exact_nominal_quantization_is_attainable_and_accepted(self):
        for expected, dt in ((1.5, 6.25), (.8, 3.125)):
            with self.subTest(expected=expected):
                old, new = interval(expected=expected, dt=dt)
                raw_delta = point_of(new)['positionMs'] - point_of(old)['positionMs']
                self.assertEqual(raw_delta / dt, expected)
                rounded_slope = (new['positionMs'] - old['positionMs']) / (new['sampledAtMs'] - old['sampledAtMs'])
                self.assertGreaterEqual(abs(rounded_slope - expected), .15)
                self.assertTrue(self.check(old, new, expected))
                result, matrix = self.sample(old, new, expected=expected)
                self.assertEqual(len(result), 2)
                self.assertEqual(matrix.rate_measurement['precisionSamples'], 2)

    def test_failure_shape_has_two_independently_valid_raw_native_slopes(self):
        # Numeric-only reproduction of the short-pair quantization shape, not
        # private logs or a claim that every raw fixture value was observed.
        for position, delta, dt, wall in (
                (58964.52901, 58973.758072 - 58964.52901, 6.1571875, 1_000_000.4),
                (58963.360259, 58972.515446 - 58963.360259, 6.107375, 1_000_000.1)):
            with self.subTest(position=position):
                old, new = interval(position=position, delta=delta, dt=dt, width=.02, wall=wall)
                self.assertLess(abs(delta / dt - 1.5), .002)
                self.assertTrue(self.check(old, new, 1.5))
        # No one shared integer elapsed time can make both 9 and 10 media ms
        # satisfy the original tolerance for these adjacent reads.
        self.assertGreater(abs(10 / 6 - 1.5), .15)
        self.assertGreater(abs(9 / 7 - 1.5), .15)

    def test_public_rounding_cannot_turn_a_raw_stall_or_jump_into_success(self):
        for position, delta in ((10000.49, 8.02), (10000.51, 9.98)):
            old, new = interval(position=position, dt=6, delta=delta)
            self.assertEqual((new['positionMs'] - old['positionMs']) /
                (new['sampledAtMs'] - old['sampledAtMs']), 1.5)
            self.reject(old, new)

    def test_small_and_large_genuine_stalls_and_jumps_reject(self):
        for dt, defect in ((6.25, -1.1), (6.25, 1.1), (200, -40), (200, 40),
                           (200, -300), (200, 300)):
            with self.subTest(dt=dt, defect=defect):
                old, new = interval(dt=dt, delta=1.5 * dt + defect)
                self.reject(old, new)

    def test_long_pair_does_not_need_a_rounded_position_fallback(self):
        for expected in (.8, 1, 1.5, 2):
            old, new = interval(expected=expected, dt=200)
            self.assertTrue(self.check(old, new, expected))

    def test_entire_rate_interval_must_fit_not_just_its_midpoint(self):
        # Nominal center, but possible elapsed times range from 5.25 to 7.25.
        old, new = interval(width=1)
        self.assertEqual((point_of(new)['positionMs'] - point_of(old)['positionMs']) / 6.25, 1.5)
        self.reject(old, new)

    def test_strict_tolerance_boundaries_and_conversion_enclosures(self):
        for rate in (1.35, 1.65):
            for candidate in (rate, math.nextafter(rate, 1.5)):
                with self.subTest(rate=rate, candidate=candidate):
                    old, new = interval(dt=100, delta=candidate * 100, width=0)
                    self.reject(old, new)
        for rate in (1.35001, 1.64999):
            old, new = interval(dt=100, delta=rate * 100, width=0)
            self.assertTrue(self.check(old, new, 1.5))

    def test_no_raw_evidence_means_no_rounded_or_nominal_fallback(self):
        edits = (
            lambda n: n.pop('timingObservation'),
            lambda n: n.update(timingObservation=None),
            lambda n: n.update(timingObservation={}),
            lambda n: n['timingObservation'].update(clockObservation=None),
            lambda n: n['timingObservation'].update(clockObservation={}),
            lambda n: n['timingObservation']['clockObservation'].update(native=[]),
            lambda n: n['timingObservation']['clockObservation'].update(native=None),
            lambda n: n['timingObservation']['clockObservation'].update(native=[None]),
        )
        for side in (0, 1):
            for ordinal, edit in enumerate(edits):
                with self.subTest(side=side, edit=ordinal):
                    pair = list(interval(dt=200)); edit(pair[side]); self.reject(*pair)

    def test_latest_record_must_be_present_and_match_native_count(self):
        for edit in (
                lambda c: c['native'].pop(),
                lambda c: c.update(nativeCount=3),
                lambda c: c['native'][-1].update(sequence=1),
                lambda c: c['native'].append(copy.deepcopy(c['native'][-1])),
                lambda c: c['native'][-1].update(sequence=3)):
            old, new = interval(); edit(new['timingObservation']['clockObservation'])
            self.reject(old, new)

    def test_saturated_or_malformed_counts_cannot_certify_freshness(self):
        for field in ('nativeCount', 'ownerCount', 'rateCount'):
            for value in (None, True, -1, 65535, 65536, 1.5, '2'):
                with self.subTest(field=field, value=value):
                    old, new = interval()
                    new['timingObservation']['clockObservation'][field] = value
                    self.reject(old, new)
        old, new = interval(); new['timingObservation']['clockObservation']['nativeCount'] = 0
        self.reject(old, new)

    def test_native_sequence_must_advance_even_when_public_time_advances(self):
        old, new = interval()
        c = new['timingObservation']['clockObservation']
        c['nativeCount'] = 1; c['native'] = [dict(c['native'][-1], sequence=1)]
        self.reject(old, new)
        self.reject(new, old)

    def test_owner_and_operation_identity_must_remain_unchanged(self):
        edits = (
            lambda n: n.update(id='replacement'),
            lambda n: point_of(n).update(owner=2),
            lambda n: point_of(n)['rates'].update(owner=2),
            lambda n: point_of(n).update(rateSequence=2),
            lambda n: point_of(n).update(seekSequence=1),
            lambda n: n['timingObservation']['clockObservation'].update(ownerCount=2),
            lambda n: n['timingObservation']['clockObservation'].update(rateCount=2),
        )
        for ordinal, edit in enumerate(edits):
            with self.subTest(edit=ordinal):
                old, new = interval(); edit(new); self.reject(old, new)

    def test_coherently_replaced_owner_or_rate_history_still_rejects(self):
        for field, count in (('owner', 'ownerCount'), ('rateSequence', 'rateCount')):
            old, new = interval(); point = point_of(new); point[field] = 2
            new['timingObservation']['clockObservation'][count] = 2
            if field == 'owner':
                point['rates']['owner'] = 2
            self.reject(old, new)

    def test_point_ordinals_require_exact_integers(self):
        for field in ('sequence', 'owner', 'rateSequence', 'seekSequence'):
            for value in (None, True, -1, 65535, 65536, 1.5, '1'):
                with self.subTest(field=field, value=value):
                    old, new = interval(); point_of(new)[field] = value
                    self.reject(old, new)

    def test_native_position_validity_and_rate_capture_identity_are_required(self):
        for path, key in (('point', 'positionValid'), ('rates', 'identityMatches'),
                          ('rates', 'effectiveAvailable'), ('rates', 'playingIntent')):
            for value in (None, False, 1, 'true'):
                with self.subTest(path=path, key=key, value=value):
                    old, new = interval(); point = point_of(new)
                    (point if path == 'point' else point['rates'])[key] = value
                    self.reject(old, new)
        for value in (None, True, 0, 'false'):
            old, new = interval(); point_of(new)['rates']['seeking'] = value
            self.reject(old, new)

    def test_all_three_captured_rates_must_be_finite_and_nominal(self):
        for key in ('requestedRate', 'nativeRate', 'effectiveRate'):
            for value in (None, False, float('nan'), float('inf'), -1, 0, .8, 1.56):
                with self.subTest(key=key, value=value):
                    old, new = interval(); point_of(new)['rates'][key] = value
                    self.reject(old, new)

    def test_missing_point_and_capture_fields_reject(self):
        fields = ('sequence', 'owner', 'rateSequence', 'seekSequence', 'positionMs',
            'positionValid', 'wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs', 'rates')
        for key in fields:
            old, new = interval(); point_of(new).pop(key)
            with self.subTest(point=key): self.reject(old, new)
        for key in ('requestedRate', 'nativeRate', 'effectiveRate', 'effectiveAvailable',
                    'identityMatches', 'owner', 'playingIntent', 'seeking',
                    'wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs'):
            old, new = interval(); point_of(new)['rates'].pop(key)
            with self.subTest(rate=key): self.reject(old, new)

    def test_raw_and_public_position_must_be_the_same_read(self):
        old, new = interval(dt=200)
        for side in (0, 1):
            for offset in (-1, 1):
                pair = copy.deepcopy([old, new]); pair[side]['positionMs'] += offset
                self.reject(*pair)
        for value in (None, True, float('nan'), float('inf'), -1, 86400001):
            a, b = interval(); point_of(b)['positionMs'] = value; self.reject(a, b)

    def test_public_time_and_uncertainty_must_exactly_match_raw_bracket(self):
        for field in ('sampledAtMs', 'sampleUncertaintyMs'):
            for delta in (-1, .0001, 1):
                old, new = interval(); new[field] += delta
                with self.subTest(field=field, delta=delta): self.reject(old, new)
            for value in (None, True, float('nan'), float('inf')):
                old, new = interval(); new[field] = value; self.reject(old, new)

    def test_half_millisecond_rounding_is_llround_not_bankers_rounding(self):
        old, new = interval(position=10000.5, dt=200, width=0, wall=1_000_000.5)
        self.assertEqual(old['positionMs'], 10001)
        self.assertEqual(old['sampledAtMs'], 1000001)
        self.assertTrue(self.check(old, new, 1.5))
        for key in ('positionMs', 'sampledAtMs'):
            bad = copy.deepcopy(old); bad[key] -= 1; self.reject(bad, new)

    def test_nonfinite_negative_and_unbounded_bracket_values_reject(self):
        for capture in (False, True):
            for key in ('wallBeforeMs', 'wallAfterMs', 'monoBeforeMs', 'monoAfterMs'):
                for value in (None, False, float('nan'), float('inf'), -1, 1e30):
                    old, new = interval(); target = point_of(new)
                    if capture: target = target['rates']
                    target[key] = value
                    with self.subTest(capture=capture, key=key, value=value): self.reject(old, new)

    def test_reversed_wide_and_incoherent_brackets_reject(self):
        for capture in (False, True):
            for key, amount in (('wallAfterMs', -1), ('monoAfterMs', -1),
                                ('wallAfterMs', 2001), ('monoAfterMs', 2001)):
                old, new = interval(); target = point_of(new)
                if capture: target = target['rates']
                target[key] += amount
                with self.subTest(capture=capture, key=key, amount=amount): self.reject(old, new)
        old, new = interval(); point = point_of(new)
        point['wallAfterMs'] += 5; bind_public(new)
        self.reject(old, new)

    def test_rate_capture_cannot_be_stale_or_in_a_different_clock_domain(self):
        for fields, offset in ((('monoBeforeMs', 'monoAfterMs'), 10000),
                               (('wallBeforeMs', 'wallAfterMs'), 10000),
                               (('monoBeforeMs', 'monoAfterMs', 'wallBeforeMs', 'wallAfterMs'), -10000)):
            old, new = interval(); rates = point_of(new)['rates']
            for field in fields: rates[field] += offset
            self.reject(old, new)

    def test_cross_sample_wall_clock_step_rejects_without_substituting_wall_dt(self):
        old, new = interval(); point = point_of(new)
        for target in (point, point['rates']):
            target['wallBeforeMs'] += 100; target['wallAfterMs'] += 100
        bind_public(new); self.reject(old, new)

    def test_overlapping_touching_and_backwards_monotonic_intervals_reject(self):
        for dt in (-1, 0, .005, .01):
            old, new = interval(dt=dt, delta=9)
            with self.subTest(dt=dt): self.reject(old, new)

    def test_actual_sample_preserves_fifty_millisecond_drift_limit(self):
        old, new = interval(dt=1000)
        independently_fast = copy.deepcopy(new)
        point_of(independently_fast)['positionMs'] += 60; bind_public(independently_fast)
        self.assertTrue(self.check(old, independently_fast, 1.5))
        def drift(states):
            native = states[2]['nativePlayers'][0]
            point_of(native)['positionMs'] += 60; bind_public(native)
        with self.assertRaises(AssertionError): self.sample(old, new, mutate=drift)

    def test_actual_sample_preserves_both_players_physical_stall_and_jump_rejection(self):
        for index in (0, 2):
            for delta in (-40, 40):
                old, new = interval(dt=200)
                def move(states):
                    native = states[index]['nativePlayers'][0]
                    point_of(native)['positionMs'] += delta; bind_public(native)
                with self.subTest(index=index, delta=delta), self.assertRaises(AssertionError):
                    self.sample(old, new, mutate=move)

    def test_actual_sample_keeps_public_nominal_health_and_task_predicates(self):
        edits = (
            lambda s: s[2]['nativePlayers'][0].update(requestedRate=1.56),
            lambda s: s[2]['nativePlayers'][0].update(playbackRate=1.56),
            lambda s: s[2]['nativePlayers'][0].update(seekInProgress=True),
            lambda s: s[2]['nativePlayers'][0].update(playingIntent=False),
            lambda s: s[2]['nativePlayers'][0].update(playbackState=4),
            lambda s: s[2].update(followSyncToleranceMs=51),
            lambda s: s[2].update(followLeadCompensationMs=1),
            lambda s: s[2].update(_taskReady=False),
            lambda s: s[2].update(trackId='different-track'),
            lambda s: s[2].update(clientId='different-process'),
        )
        for ordinal, edit in enumerate(edits):
            old, new = interval(dt=200)
            with self.subTest(edit=ordinal), self.assertRaises(AssertionError):
                self.sample(old, new, mutate=edit)

    def test_actual_sample_keeps_public_progress_and_uncertainty_predicates(self):
        # Helper independently accepts the raw slope, but these pre-existing
        # public predicates still veto insufficient progress or time certainty.
        old, new = interval(expected=.2, position=10000.5, dt=6.25)
        self.assertEqual(new['positionMs'] - old['positionMs'], 1)
        self.assertTrue(self.check(old, new, .2))
        with self.assertRaises(AssertionError): self.sample(old, new, expected=.2)
        old, new = interval(expected=2, dt=2)
        self.assertTrue(self.check(old, new, 2))
        with self.assertRaises(AssertionError): self.sample(old, new, expected=2)
        old, new = interval(dt=500, width=16)
        self.assertTrue(self.check(old, new, 1.5))
        with self.assertRaises(AssertionError): self.sample(old, new)

    def test_large_float64_timestamp_uncertainty_is_not_discarded(self):
        # A zero reported bracket does not make binary64 conversion exact.
        # At this magnitude the outward timestamp envelope is material.
        old, new = interval(mono=1e15 - 1000, wall=1e15 - 1000, width=0)
        point_delta = point_of(new)['positionMs'] - point_of(old)['positionMs']
        nominal_dt = point_of(new)['monoBeforeMs'] - point_of(old)['monoBeforeMs']
        self.assertEqual(point_delta / nominal_dt, 1.5)
        self.reject(old, new)
        old, new = interval(mono=1e15 - 1000, wall=1e15 - 1000, width=0, dt=100)
        self.assertTrue(self.check(old, new, 1.5))

    def test_large_position_conversion_error_encloses_a_near_boundary_rate(self):
        for nominal in (1.3500000001, 1.6499999999):
            old, new = interval(position=80_000_000, dt=200, delta=nominal * 200, width=0)
            raw_slope = (point_of(new)['positionMs'] - point_of(old)['positionMs']) / 200
            self.assertLess(abs(raw_slope - 1.5), .15)
            self.reject(old, new)

    def test_seek_invocation_count_must_exist_be_unsaturated_and_match(self):
        for value in (None, True, -1, 1, 65535, 65536, .5, '0'):
            old, new = interval(); new['timingObservation']['seekInvocations'] = value
            with self.subTest(value=value): self.reject(old, new)
        old, new = interval(); new['timingObservation'].pop('seekInvocations')
        self.reject(old, new)
        # Matching a new seek still cannot bridge its change in operation.
        old, new = interval(); new['timingObservation']['seekInvocations'] = 1
        point_of(new)['seekSequence'] = 1; self.reject(old, new)

    def test_capture_health_read_count_and_public_rate_equality_are_not_optional(self):
        for key, values in (('processingState', (None, True, 2, 4)),
                            ('timeControl', (None, True, 0, 1)),
                            ('effectiveReadCount', (None, True, 0, 2))):
            for value in values:
                old, new = interval(); point_of(new)['rates'][key] = value
                with self.subTest(key=key, value=value): self.reject(old, new)
        for key in ('requestedRate', 'playbackRate'):
            old, new = interval(); new[key] += .00001
            self.reject(old, new)

    def test_expected_rate_and_player_identity_are_validated(self):
        for value in (None, True, float('nan'), float('inf'), -1, 0, 5):
            old, new = interval()
            with self.subTest(expected=value): self.reject(old, new, value)
        for value in (None, '', True, 1):
            old, new = interval(); old['id'] = new['id'] = value
            self.reject(old, new)

    def test_obsolete_anchor_and_rate_tapes_cannot_substitute_for_native_points(self):
        old, new = interval(dt=200)
        for native in (old, new):
            clock = native['timingObservation']['clockObservation']
            clock['anchors'] = copy.deepcopy(clock['native'])
            clock['rates'] = [dict(firstNative=copy.deepcopy(point_of(native)), firstNativeSeen=True)]
            clock['native'] = []
        self.reject(old, new)

    def test_unsaturated_counter_tail_and_zero_operation_ordinals_are_accepted(self):
        old, new = interval(dt=200)
        for native, sequence in ((old, 65533), (new, 65534)):
            point = point_of(native)
            point.update(sequence=sequence, rateSequence=0)
            clock = native['timingObservation']['clockObservation']
            clock.update(nativeCount=sequence, rateCount=0)
            # The first two plus the latest six are the retained native tape.
            ordinals = [1, 2] + list(range(sequence - 5, sequence + 1))
            clock['native'] = [dict(copy.deepcopy(point), sequence=i) for i in ordinals]
        self.assertTrue(self.check(old, new, 1.5))

    def test_sub_half_millisecond_value_is_not_rounded_up_by_addition_error(self):
        old, new = interval(position=math.nextafter(.5, 0), width=0, dt=6.25)
        self.assertEqual(old['positionMs'], 0)
        self.assertTrue(self.check(old, new, 1.5))
        old['positionMs'] = 1; self.reject(old, new)

    def test_actual_sample_uses_raw_helper_once_per_existing_player_pair(self):
        old, new = interval(dt=200)
        check = Mock(wraps=self.check)
        self.ns['follow_native_interval_rate'] = check
        _, matrix = self.sample(old, new)
        self.assertEqual(check.call_count, 2)
        for call in check.call_args_list:
            self.assertEqual(call.args[2], 1.5)
            self.assertIn('timingObservation', call.args[0])
            self.assertIn('timingObservation', call.args[1])
        matrix.states.assert_not_called(); matrix.wait.assert_not_called(); matrix.command.assert_not_called()
        self.ns['time'].monotonic.assert_not_called(); self.ns['time'].time.assert_not_called()
        self.ns['time'].sleep.assert_not_called()

    def test_interval_helper_and_sample_have_no_new_io_control_poll_or_clock_calls(self):
        tree = ast.parse((PAYLOAD / 'follow_precision_helpers.py').read_text())
        funcs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        pending = ['follow_native_interval_rate', 'follow_precision_sample']; seen = set()
        while pending:
            name = pending.pop()
            if name in seen: continue
            seen.add(name)
            for node in ast.walk(funcs[name]):
                if not isinstance(node, ast.Call): continue
                called = ast.unparse(node.func)
                self.assertNotIn(called, ('open', '__import__', 'eval', 'exec',
                    'time.time', 'time.monotonic', 'time.sleep', 'matrix.states',
                    'matrix.wait', 'matrix.command', 'matrix.clients'))
                self.assertFalse(any(token in called.lower() for token in ('poll', 'command', 'sleep')))
                if isinstance(node.func, ast.Name) and node.func.id in funcs:
                    pending.append(node.func.id)


if __name__ == '__main__':
    unittest.main()
