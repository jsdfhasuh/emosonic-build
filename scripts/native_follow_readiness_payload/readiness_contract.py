"""Public synthetic contracts; private reviewed AST is injected by the runner."""
import ast
import copy
import json
import math
import unittest
BASELINE = None
PATCHED = None
SHARED_BASELINE = None
FINAL_PATCHED = None
NAMES = {'players', 'decoded', 'playing', 'stopped', 'native_follow_task_ready',
         'follow_native_rate_bounds', 'native_rate_matches', 'aligned_drift',
         'numeric_native_snapshot', 'Matrix'}

class Clock:
    def __init__(self): self.now = 0.0; self.sleeps = []
    def monotonic(self): return self.now
    def sleep(self, seconds):
        self.sleeps.append(seconds); self.now = round(self.now + seconds, 6)


def base_state(at, role, *, paused=False, offset=0, rate=1.5, native_error=0):
    return {'contextId': 'authority-context' if role == 'a' else 'original-context',
            'runtimeMode': 'solo' if role == 'a' else 'follow',
            'followSourceContextId': None if role == 'a' else 'authority-context',
            'trackId': 'fixture-a', 'queue': ['fixture-a', 'fixture-b'], 'currentIndex': 0,
            'followSyncToleranceMs': 80, 'followMaxCorrectionFraction': 0.04,
            'followLeadCompensationMs': 0,
            'nativePlayers': [{'id': 'native-' + role, 'positionMs': int(10000 + at * 1500 + offset),
                'durationMs': 180000, 'sampledAtMs': 100000 + int(at * 1000),
                'playbackState': 4 if paused else 3, 'playbackRate': 0 if paused else rate,
                'requestedRate': 1.5, 'sampleUncertaintyMs': 1,
                'avPlayerStatus': 1, 'avItemStatus': 1, 'avTimeControlStatus': 0 if paused else 2,
                'errorCode': native_error}]}

def load(clock, *, patched):
    source = PATCHED if patched else BASELINE
    tree = ast.parse(source)
    names = NAMES | {'follow_correction_identity', 'native_follow_readiness_pending'}
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    namespace = {'math': math, 'json': json, 'time': clock, 'summarize_state': lambda state, *observation: {'status':'unavailable'}}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<reviewed-harness>', 'exec'), namespace)
    return namespace


def state(at, role, **kw):
    seek = kw.pop('seek', False)
    value = base_state(at, role, **kw)
    value.update({'clientId': 'fixture-client-' + role, 'deviceSessionId': 'fixture-device-' + role,
        'pid': 101 if role == 'a' else 103, 'bundleId': 'fixture.bundle.' + role, 'root': '/owned/fixture/' + role,
        'identitySeedMatches': True, 'strictV2': True, 'connection': 'ready', 'followNegotiated': True,
        'processingState': 'buffering' if seek else 'ready',
        'contexts': {'authority-context': {'authorityClientId': 'fixture-client-a',
            'authorityDeviceSessionId': 'fixture-device-a', 'epoch': 1, 'controlVersion': 4, 'queueRevision': 2}},
        'preflightDiagnostics': {'connectionGeneration': 2, 'followRecoveryGateActive': True,
            'recoveryKind': 'follow', 'recoveryPhase': 'active', 'recoveryContextMatchesCurrent': True,
            'recoveryAuthorityMatchesSelf': True, 'recoveryControlVersion': 5,
            'recoveryAppliedControlVersion': 5, 'queueHydrating': False, 'restoreInProgress': False}})
    value['nativePlayers'][0].update({'seekInProgress': seek, 'playingIntent': True})
    return value


def pair(at, **kw): return [state(at, 'a'), {}, state(at, 'f', **kw)]


def waiting(at):
    values = pair(at)
    values[2]['processingState'] = 'buffering'
    values[2]['nativePlayers'][0].update(playbackState=2, avTimeControlStatus=1,
        playbackRate=1.5, requestedRate=1.5, seekInProgress=False, playingIntent=True)
    return values

class ReadinessTests(unittest.TestCase):
    def setup_matrix(self, *, patched=True, sample=None):
        clock = Clock(); ns = load(clock, patched=patched); matrix = ns['Matrix']()
        matrix.rate_measurement = {'expectedRate': 1.5, 'measurementWindowSeconds': 3}
        matrix.last = pair(0); outcomes = []; matrix.outcome = lambda name, **kw: outcomes.append((name, kw))
        def read():
            matrix.last = (sample or (lambda at: pair(at)))(clock.now)
            return matrix.last
        matrix.states = read
        return clock, ns, matrix, outcomes

    def test_baseline_red_same_ready_seek_stable_sequence(self):
        def sample(at): return pair(at, paused=at < 0.4, seek=at < 0.4)
        clock, ns, matrix, outcomes = self.setup_matrix(patched=False, sample=sample)
        with self.assertRaises(AssertionError): matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0)

    def test_patched_green_same_ready_seek_stable_sequence(self):
        def sample(at): return pair(at, paused=at < 0.4, seek=at < 0.4)
        clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
        matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0.6)
        self.assertEqual(outcomes[0][1]['consecutiveAlignedSamples'], 2)
        self.assertEqual(outcomes[0][1]['correctionReadinessPollCount'], 2)

    def test_hung_seek_uses_exact_original_deadline(self):
        clock, ns, matrix, outcomes = self.setup_matrix(sample=lambda at: pair(at, paused=True, seek=True))
        with self.assertRaises(TimeoutError): matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 5); self.assertEqual(outcomes, [])
        self.assertLessEqual(matrix.rate_measurement['correctionReadinessPollCount'], 25)
        self.assertEqual(matrix.rate_measurement['correctionReadinessElapsedMs'], 5000)

    def test_buffering_resets_consecutive_pair_not_deadline(self):
        clock, ns, matrix, outcomes = self.setup_matrix(sample=lambda at: pair(at, paused=at == 0.2, seek=at == 0.2))
        matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0.6)

    def test_missing_false_or_nonboolean_native_seek_flags_fail(self):
        for key in ('seekInProgress', 'playingIntent'):
            for flag in (None, False, 1, 'true'):
                def sample(at):
                    values=pair(at, paused=True, seek=True);values[2]['nativePlayers'][0][key]=flag;return values
                clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
                with self.subTest(key=key, flag=flag), self.assertRaises(AssertionError): matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
                self.assertEqual(clock.now, 0)

    def test_wrong_identity_cannot_enter_readiness_branch(self):
        mutations = [lambda s:s[2].update(trackId='wrong'), lambda s:s[2].update(queue=['wrong']),
            lambda s:s[2].update(currentIndex=1), lambda s:s[2].update(followSourceContextId='wrong'),
            lambda s:s[2].update(clientId='wrong'), lambda s:s[2].update(deviceSessionId='wrong'),
            lambda s:s[2].update(pid=999), lambda s:s[2].update(pid=True),
            lambda s:s[2].update(bundleId='wrong'), lambda s:s[2].update(root='wrong'),
            lambda s:s[2]['nativePlayers'][0].update(id='wrong'),
            lambda s:s[2]['preflightDiagnostics'].update(connectionGeneration=3),
            lambda s:s[2]['preflightDiagnostics'].update(recoveryControlVersion=6),
            lambda s:s[2]['preflightDiagnostics'].update(recoveryAppliedControlVersion=6),
            lambda s:s[2]['preflightDiagnostics'].update(recoveryPhase='restoring'),
            lambda s:s[0]['contexts']['authority-context'].update(epoch=2),
            lambda s:s[0]['contexts']['authority-context'].update(controlVersion=6),
            lambda s:s[2]['contexts']['authority-context'].update(queueRevision=3)]
        for mutate in mutations:
            def sample(at):
                values=pair(at, paused=True, seek=True);mutate(values);return values
            clock, ns, matrix, outcomes=self.setup_matrix(sample=sample)
            with self.assertRaises(AssertionError):matrix.follow_alignment('authority-context',0,1.5,0,5)
            self.assertEqual(clock.now,0)

    def test_wrong_speed_manual_pause_unknown_and_failed_states_fail_immediately(self):
        mutations=[lambda s:s[2]['nativePlayers'][0].update(requestedRate=1.0),
            lambda s:s[2]['nativePlayers'][0].update(playingIntent=False),
            lambda s:s[2].update(processingState='ready'),
            lambda s:s[2]['nativePlayers'][0].update(avItemStatus=0),
            lambda s:s[2]['nativePlayers'][0].update(avItemStatus=2),
            lambda s:s[0]['nativePlayers'][0].update(playbackState=4,playbackRate=0,avTimeControlStatus=0),
            lambda s:s[0]['nativePlayers'][0].update(playbackRate=1.0)]
        for mutate in mutations:
            def sample(at):
                values=pair(at,paused=True,seek=True);mutate(values);return values
            clock,ns,matrix,outcomes=self.setup_matrix(sample=sample)
            with self.assertRaises(AssertionError):matrix.follow_alignment('authority-context',0,1.5,0,5)
            self.assertEqual(clock.now,0)

    def test_steady_state_seek_buffering_remains_immediate_failure(self):
        clock,ns,matrix,outcomes=self.setup_matrix(sample=lambda at:pair(at,paused=at>=0.6,seek=at>=0.6))
        with self.assertRaises(AssertionError):matrix.rate(2,1.5,'follower-contract',follow_context='authority-context',authority_index=0)
        self.assertEqual(clock.now,0.7);self.assertEqual(matrix.stage,'follower-contract')
        self.assertEqual([entry[0] for entry in outcomes],['native-follow-aligned','follower-contract:native-advancement-readiness'])

    def test_full_continuous_measurement_after_readiness_is_not_shortened(self):
        clock,ns,matrix,outcomes=self.setup_matrix(sample=lambda at:pair(at,paused=at<0.4,seek=at<0.4))
        matrix.rate(2,1.5,'follower-contract',follow_context='authority-context',authority_index=0)
        self.assertEqual(outcomes[-1][0],'follower-contract');self.assertGreaterEqual(outcomes[-1][1]['elapsedSeconds'],3)
        self.assertGreaterEqual(clock.now,3.7)

    def test_original_assertions_and_strict_rate_method_are_unchanged(self):
        before=ast.parse(BASELINE);after=ast.parse(PATCHED)
        old=[ast.dump(n) for n in ast.walk(before) if isinstance(n,ast.Assert)]
        new=[ast.dump(n) for n in ast.walk(after) if isinstance(n,ast.Assert)]
        for assertion in old:self.assertIn(assertion,new)
        def rate(tree):return next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='rate')
        self.assertEqual(ast.dump(rate(before)),ast.dump(rate(after)))
        for name in ('players','native_follow_task_ready','aligned_drift','native_rate_matches'):
            def method(tree):return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(method(before)),ast.dump(method(after)))

    def test_public_native_fields_are_boolean_only_without_identity(self):
        clock,ns,matrix,outcomes=self.setup_matrix()
        row=state(0,'f',paused=True,seek=True)['nativePlayers'][0]
        result=ns['numeric_native_snapshot'](row)
        self.assertIs(result['seekInProgress'],True);self.assertIs(result['playingIntent'],True)
        self.assertNotIn('id',result);self.assertNotIn('sampledAtMs',result)
        row['seekInProgress']='private-string';self.assertNotIn('seekInProgress',ns['numeric_native_snapshot'](row))

    def test_baseline_red_documented_native_waiting_interval(self):
        def sample(at):
            return pair(at, offset=-515) if at == 0 else waiting(at)
        clock, ns, matrix, outcomes = self.setup_matrix(patched=False, sample=sample)
        with self.assertRaises(AssertionError):
            matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0.2)
        self.assertEqual(outcomes, [])

    def test_preroll_paused_seek_then_preroll_then_two_playing_samples(self):
        def sample(at):
            if at < 0.2:
                return pair(at, paused=True, seek=True)
            if at < 0.6:
                value = waiting(at)
                value[2]['nativePlayers'][0]['seekInProgress'] = at < 0.4
                return value
            return pair(at)
        clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
        matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0.8)
        self.assertEqual(outcomes[-1][1]['consecutiveAlignedSamples'], 2)
        self.assertEqual(matrix.rate_measurement['correctionReadinessPollCount'], 3)

    def test_preroll_does_not_require_claiming_observed_seek(self):
        clock, ns, matrix, outcomes = self.setup_matrix(sample=lambda at: waiting(at) if at < 0.4 else pair(at))
        matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 0.6)
        self.assertEqual(matrix.rate_measurement['correctionReadinessPollCount'], 2)

    def test_preroll_alternating_ready_seek_wait_does_not_reset_deadline(self):
        def sample(at):
            mode = int(round(at / 0.2)) % 3
            return pair(at) if mode == 0 else pair(at, paused=True, seek=True) if mode == 1 else waiting(at)
        clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
        with self.assertRaises(TimeoutError):
            matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
        self.assertEqual(clock.now, 5)
        self.assertEqual(outcomes, [])
        self.assertEqual(max(clock.sleeps), 0.2)

    def test_preroll_persistent_preroll_and_persistent_seek_both_fail_at_original_deadline(self):
        for sample in [waiting, lambda at: pair(at, paused=True, seek=True)]:
            clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
            with self.assertRaises(TimeoutError):
                matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
            self.assertEqual(clock.now, 5)
            self.assertEqual(outcomes, [])
            self.assertEqual(matrix.rate_measurement['correctionReadinessElapsedMs'], 5000)

    def test_preroll_each_pending_state_resets_alignment_pair(self):
        for pending in [waiting, lambda at: pair(at, paused=True, seek=True)]:
            clock, ns, matrix, outcomes = self.setup_matrix(sample=lambda at: pending(at) if at == 0.2 else pair(at))
            matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
            self.assertEqual(clock.now, 0.6)
            self.assertEqual(outcomes[-1][1]['consecutiveAlignedSamples'], 2)

    def test_preroll_native_state_rate_and_play_intent_negatives_fail_immediately(self):
        mutations = [
            lambda s: s[2]['nativePlayers'][0].update(playbackRate=0),
            lambda s: s[2]['nativePlayers'][0].update(playbackRate=1.56),
            lambda s: s[2]['nativePlayers'][0].update(requestedRate=1),
            lambda s: s[2]['nativePlayers'][0].update(requestedRate=float('nan')),
            lambda s: s[2]['nativePlayers'][0].update(playbackRate=float('inf')),
            lambda s: s[2]['nativePlayers'][0].update(playingIntent=False),
            lambda s: s[2]['nativePlayers'][0].update(playingIntent=1),
            lambda s: s[2]['nativePlayers'][0].pop('playingIntent'),
            lambda s: s[2]['nativePlayers'][0].pop('seekInProgress'),
            lambda s: s[2]['nativePlayers'][0].update(seekInProgress='unknown'),
            lambda s: s[2]['nativePlayers'][0].update(avPlayerStatus=0),
            lambda s: s[2]['nativePlayers'][0].update(avItemStatus=2),
            lambda s: s[2]['nativePlayers'][0].update(avTimeControlStatus=0),
            lambda s: s[2]['nativePlayers'][0].update(durationMs=0),
            lambda s: s[2]['nativePlayers'][0].update(errorCode=1),
            lambda s: s[2].update(processingState='ready'),
            lambda s: s[2].update(processingState='loading'),
            lambda s: s[0]['nativePlayers'][0].update(playbackRate=1),
            lambda s: s[0]['nativePlayers'][0].update(playbackState=4, avTimeControlStatus=0, playbackRate=0),
        ]
        for ordinal, mutation in enumerate(mutations):
            def sample(at):
                value = waiting(at)
                mutation(value)
                return value
            clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
            with self.subTest(ordinal=ordinal), self.assertRaises((AssertionError, KeyError, TypeError)):
                matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
            self.assertEqual(clock.now, 0)
            self.assertEqual(outcomes, [])

    def test_preroll_generic_pause_and_stopped_unknown_loading_are_not_preroll(self):
        for native_state in (0, 1, 4):
            def sample(at):
                value = waiting(at)
                value[2]['nativePlayers'][0].update(playbackState=native_state, avTimeControlStatus=0, playbackRate=0, seekInProgress=False)
                return value
            clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
            with self.subTest(native_state=native_state), self.assertRaises(AssertionError):
                matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
            self.assertEqual(clock.now, 0)

    def test_preroll_task_identity_authority_cursors_and_recovery_changes_fail_immediately(self):
        mutations = [
            lambda s: s[2].update(runtimeMode='solo'),
            lambda s: s[2].update(trackId='other'),
            lambda s: s[2].update(queue=['other']),
            lambda s: s[2].update(currentIndex=1),
            lambda s: s[2].update(followSourceContextId='other'),
            lambda s: s[2].update(clientId='other'),
            lambda s: s[2].update(deviceSessionId='other'),
            lambda s: s[2].update(pid=999),
            lambda s: s[2].update(bundleId='other'),
            lambda s: s[2].update(root='other'),
            lambda s: s[2]['nativePlayers'][0].update(id='other'),
            lambda s: s[2]['preflightDiagnostics'].update(connectionGeneration=3),
            lambda s: s[2]['preflightDiagnostics'].update(followRecoveryGateActive=False),
            lambda s: s[2]['preflightDiagnostics'].update(recoveryPhase='restoring'),
            lambda s: s[2]['preflightDiagnostics'].update(recoveryControlVersion=6),
            lambda s: s[2]['preflightDiagnostics'].update(recoveryAppliedControlVersion=6),
            lambda s: s[2]['preflightDiagnostics'].update(queueHydrating=True),
            lambda s: s[2]['preflightDiagnostics'].update(restoreInProgress=True),
            lambda s: s[0]['contexts']['authority-context'].update(epoch=2),
            lambda s: s[0]['contexts']['authority-context'].update(controlVersion=6),
            lambda s: s[2]['contexts']['authority-context'].update(queueRevision=3),
        ]
        for ordinal, mutation in enumerate(mutations):
            def sample(at):
                value = waiting(at)
                mutation(value)
                return value
            clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
            with self.subTest(ordinal=ordinal), self.assertRaises(AssertionError):
                matrix.follow_alignment('authority-context', 0, 1.5, 0, 5)
            self.assertEqual(clock.now, 0)
            self.assertEqual(outcomes, [])

    def test_preroll_complete_three_second_window_follows_all_premeasurement_states(self):
        def sample(at):
            if at < 0.2:
                return pair(at, paused=True, seek=True)
            if at < 0.6:
                return waiting(at)
            return pair(at)
        clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
        matrix.rate(2, 1.5, 'full-window', follow_context='authority-context', authority_index=0)
        self.assertEqual(outcomes[-1][0], 'full-window')
        self.assertGreaterEqual(outcomes[-1][1]['elapsedSeconds'], 3)
        self.assertGreaterEqual(clock.now, 3.9)

    def test_preroll_pending_during_advancement_and_every_strict_window_interval_fails(self):
        for pending in [waiting, lambda at: pair(at, paused=True, seek=True)]:
            for start in (0.3, 0.5, 1.5, 3.1):
                def sample(at):
                    return pending(at) if at >= start else pair(at)
                clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
                with self.subTest(start=start), self.assertRaises(AssertionError):
                    matrix.rate(2, 1.5, 'strict-window', follow_context='authority-context', authority_index=0)
                self.assertNotIn('strict-window', [entry[0] for entry in outcomes])
                self.assertLessEqual(clock.now, start + 0.2)

    def test_preroll_total_alignment_and_advancement_budget_stays_shared(self):
        def sample(at):
            return waiting(at) if at < 4.8 else pair(at)
        clock, ns, matrix, outcomes = self.setup_matrix(sample=sample)
        with self.assertRaises(TimeoutError):
            matrix.rate(2, 1.5, 'deadline', follow_context='authority-context', authority_index=0)
        self.assertEqual(clock.now, 5)
        self.assertEqual(outcomes, [])



class SharedReadinessTests(unittest.TestCase):
    def setup_shared(self, *, shared=True, sample=None, late=False):
        clock = Clock()
        source = FINAL_PATCHED if shared else SHARED_BASELINE
        names = NAMES | {'follow_correction_identity', 'native_follow_readiness_pending', 'native_post_seek_ready'}
        selected = [n for n in ast.parse(source).body
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        ns = {'math':math, 'json':json, 'time':clock, 'summarize_state':lambda state, *observation: {'status':'unavailable'}}
        exec(compile(ast.Module(body=selected, type_ignores=[]), '<reviewed-shared-readiness>', 'exec'), ns)
        matrix = ns['Matrix'](); matrix.last = pair(0)
        reads, outcomes = [], []
        def read():
            if late and not reads: clock.now = 4.69
            elif late and len(reads) >= 2: clock.now = round(clock.now + .13, 6)
            matrix.last = (sample or pair)(clock.now)
            reads.append(clock.now)
            return matrix.last
        matrix.states = read
        matrix.outcome = lambda name, **kw: outcomes.append((name, kw, copy.deepcopy(matrix.rate_measurement)))
        return clock, ns, matrix, reads, outcomes

    def run_follow(self, matrix):
        matrix.rate(2, 1.5, 'shared', follow_context='authority-context', authority_index=0)

    def test_shared_01_current_baseline_red_redundant_poll_expires(self):
        clock, _, matrix, reads, outcomes = self.setup_shared(shared=False, late=True)
        with self.assertRaisesRegex(TimeoutError, 'did not begin advancing'):
            self.run_follow(matrix)
        self.assertEqual(reads[:2], [4.69, 4.89])
        self.assertEqual(clock.now, 5.12)
        self.assertEqual(outcomes[0][0], 'native-follow-aligned')
        self.assertEqual(matrix.stage, 'shared:native-advancement-readiness')

    def test_shared_02_late_pair_green_starts_full_window_at_second_sample(self):
        clock, _, matrix, reads, outcomes = self.setup_shared(late=True)
        self.run_follow(matrix)
        self.assertEqual(reads[:3], [4.69, 4.89, 5.22])
        proof = next(row for row in outcomes if row[0]=='shared:native-advancement-readiness')
        self.assertEqual(proof[1]['waitDurationMs'], 0)
        self.assertEqual(proof[1]['totalReadinessMs'], 4890)
        final = outcomes[-1]
        self.assertEqual(final[0], 'shared')
        self.assertGreaterEqual(final[1]['elapsedSeconds'], 3)
        self.assertEqual(final[1]['elapsedSeconds'], (int(reads[-1]*1000)-int(reads[1]*1000))/1000)
        self.assertEqual(final[2]['firstNative']['positionMs'], 17335)

    def test_shared_03_nonadvancing_and_discontinuous_pairs_never_fund_readiness(self):
        for mode in ('frozen', 'backward', 'jump', 'uncertainty'):
            def sample(at):
                rows = pair(at)
                for i in (0, 2):
                    native = rows[i]['nativePlayers'][0]
                    if mode == 'frozen': native['positionMs'] = 10000
                    elif mode == 'backward': native['positionMs'] = 20000-int(at*100)
                    elif mode == 'jump': native['positionMs'] = 10000+int(at*3000)
                    else: native['sampleUncertaintyMs'] = 101
                return rows
            clock, _, matrix, _, outcomes = self.setup_shared(sample=sample)
            with self.subTest(mode=mode), self.assertRaises((AssertionError, TimeoutError)):
                self.run_follow(matrix)
            self.assertFalse(any(row[0]=='shared:native-advancement-readiness' for row in outcomes))

    def test_shared_04_identity_control_and_rate_changes_reject_before_witness(self):
        mutations = [lambda rows: rows[2]['nativePlayers'][0].update(id='other'),
            lambda rows: rows[2].update(followSourceContextId='other'),
            lambda rows: rows[2]['contexts']['authority-context'].update(controlVersion=9),
            lambda rows: rows[2]['preflightDiagnostics'].update(recoveryAppliedControlVersion=9),
            lambda rows: rows[2]['nativePlayers'][0].update(playbackRate=1),
            lambda rows: rows[0]['nativePlayers'][0].update(playbackRate=1)]
        for mutate in mutations:
            def sample(at):
                rows = pair(at)
                if at >= .2: mutate(rows)
                return rows
            clock, _, matrix, _, outcomes = self.setup_shared(sample=sample)
            with self.subTest(mutation=mutations.index(mutate)), self.assertRaises(AssertionError):
                self.run_follow(matrix)
            self.assertFalse(any(row[0]=='shared:native-advancement-readiness' for row in outcomes))

    def test_shared_05_exact_deadline_is_not_extended_by_a_valid_pair(self):
        clock, _, matrix, reads, _ = self.setup_shared()
        def read():
            clock.now = 4.8 if not reads else 5.0
            matrix.last = pair(clock.now); reads.append(clock.now)
            return matrix.last
        matrix.states = read
        with self.assertRaisesRegex(TimeoutError, 'five-second readiness budget'):
            self.run_follow(matrix)
        self.assertEqual(clock.now, 5)

    def test_shared_06_deadline_rechecked_after_alignment_reporting(self):
        clock, _, matrix, _, outcomes = self.setup_shared(late=True)
        original = matrix.outcome
        def outcome(name, **kw):
            original(name, **kw)
            if name == 'native-follow-aligned': clock.now = 5
        matrix.outcome = outcome
        with self.assertRaisesRegex(TimeoutError, 'did not begin advancing'):
            self.run_follow(matrix)
        self.assertEqual(clock.now, 5)

    def test_shared_07_witness_is_fresh_and_compatible_original_contracts_hold(self):
        # Four historical cases encode the superseded mandatory 100ms poll or
        # whole rate AST. Their unchanged bodies test the inverse prior layer;
        # final replacements are cases 02/06/10/11/12 and exact inverse/tail proof.
        incompatible = {'test_original_assertions_and_strict_rate_method_are_unchanged',
            'test_full_continuous_measurement_after_readiness_is_not_shortened',
            'test_preroll_complete_three_second_window_follows_all_premeasurement_states',
            'test_steady_state_seek_buffering_remains_immediate_failure'}
        global PATCHED
        prior = PATCHED
        try:
            PATCHED = FINAL_PATCHED
            names = sorted(name for name in ReadinessTests.__dict__ if name.startswith('test_') and name not in incompatible)
            self.assertEqual(len(names), 19)
            result = unittest.TestResult()
            unittest.TestSuite(ReadinessTests(name) for name in names).run(result)
            self.assertEqual(result.testsRun, 19)
            self.assertFalse(result.errors or result.failures or result.skipped
                or result.expectedFailures or result.unexpectedSuccesses)
        finally:
            PATCHED = prior
        clock, _, matrix, _, outcomes = self.setup_shared()
        self.run_follow(matrix)
        began = clock.now
        fixed = pair(clock.now)
        def stalled():
            matrix.last = copy.deepcopy(fixed)
            for i in (0,2): matrix.last[i]['nativePlayers'][0]['sampledAtMs'] = 100000+int(clock.now*1000)
            return matrix.last
        matrix.states = stalled
        count = len(outcomes)
        with self.assertRaises(TimeoutError): self.run_follow(matrix)
        self.assertGreaterEqual(round(clock.now-began, 6), 5)
        self.assertEqual(len(outcomes), count)

    def test_shared_08_prefilled_witness_and_wrong_current_owner_are_rejected(self):
        clock, ns, matrix, _, _ = self.setup_shared()
        matrix.rate_measurement = {}
        with self.assertRaises(AssertionError):
            matrix.follow_alignment('authority-context', 0, 1.5, 0, 5, advancement_witness=[pair(0)])
        original = matrix.follow_alignment
        def wrong_owner(*args, **kw):
            current = original(*args, **kw)
            return copy.deepcopy(current)
        matrix.follow_alignment = wrong_owner
        with self.assertRaises(AssertionError): self.run_follow(matrix)

    def test_shared_09_nonfollow_and_postseek_still_require_new_advancement(self):
        for postseek in (False, True):
            clock, ns, matrix, reads, outcomes = self.setup_shared()
            kwargs = {'expected_position_ms':10000, 'after_seek':state(-.1,'a')} if postseek else {}
            matrix.rate(0, 1.5, 'ordinary', **kwargs)
            self.assertGreaterEqual(len(reads), 3)
            proof = next(row for row in outcomes if row[0]=='ordinary:native-advancement-readiness')
            self.assertGreaterEqual(proof[1]['waitDurationMs'], 100)
            self.assertGreaterEqual(outcomes[-1][1]['elapsedSeconds'], 3)

    def test_shared_10_pending_preroll_resets_pair_before_reuse(self):
        def sample(at):
            if .2 <= at < .4: return waiting(at)
            return pair(at)
        clock, _, matrix, reads, outcomes = self.setup_shared(sample=sample)
        self.run_follow(matrix)
        aligned = next(row for row in outcomes if row[0]=='native-follow-aligned')
        self.assertEqual(aligned[1]['waitDurationMs'], 600)
        self.assertEqual(outcomes[-1][2]['firstNative']['positionMs'], 10900)

    def test_shared_11_every_bad_strict_window_sample_still_fails(self):
        for mode in ('paused','buffering','rate','jump','source_context'):
            def sample(at):
                rows = pair(at)
                if at >= .4:
                    native = rows[2]['nativePlayers'][0]
                    if mode=='paused': native.update(playbackState=4, playbackRate=0)
                    elif mode=='buffering': native.update(playbackState=2)
                    elif mode=='rate': native.update(playbackRate=1)
                    elif mode=='jump': native['positionMs'] += 200
                    else: rows[2]['followSourceContextId'] = 'other'
                return rows
            clock, _, matrix, _, outcomes = self.setup_shared(sample=sample)
            with self.subTest(mode=mode), self.assertRaises(AssertionError): self.run_follow(matrix)
            self.assertEqual(matrix.stage, 'shared')
            self.assertEqual(clock.now, .4)
            self.assertFalse(any(row[0]=='shared' for row in outcomes))

    def test_shared_12_nominal_restore_interval_stays_inside_full_window(self):
        def sample(at):
            rows = pair(at)
            if .2 <= at <= 1:
                rows[2]['nativePlayers'][0]['playbackRate'] = 1.56
            rows[2]['nativePlayers'][0]['positionMs'] += int(max(0,min(at-.2,.8))*60)
            return rows
        clock, _, matrix, reads, outcomes = self.setup_shared(sample=sample)
        self.run_follow(matrix)
        final = outcomes[-1]
        self.assertAlmostEqual(final[1]['elapsedSeconds'], reads[-1] - .2)
        self.assertEqual(final[2]['firstNative']['positionMs'], 10300)
        self.assertGreaterEqual(final[1]['elapsedSeconds'], 3)
        self.assertTrue(any(.2 < at <= 1 for at in reads))
        self.assertGreater(final[1]['measuredRate'], 1.5)


TEST_NAMES = tuple(sorted(name for cls in (ReadinessTests, SharedReadinessTests)
                         for name in cls.__dict__ if name.startswith('test_')))


def suite(baseline, patched, shared_baseline=None):
    global BASELINE, PATCHED, SHARED_BASELINE, FINAL_PATCHED
    BASELINE, PATCHED, SHARED_BASELINE, FINAL_PATCHED = baseline, shared_baseline, shared_baseline, patched
    return unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(SharedReadinessTests)))
