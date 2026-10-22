"""Public synthetic contracts; private reviewed AST is injected by the runner."""
import ast
import copy
import json
import math
import unittest
BASELINE = None
PATCHED = None
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
    names = NAMES | {'follow_correction_identity', 'native_follow_seek_readiness'}
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    namespace = {'math': math, 'json': json, 'time': clock}
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


TEST_NAMES = tuple(sorted(name for name in ReadinessTests.__dict__ if name.startswith('test_')))


def suite(baseline, patched):
    global BASELINE, PATCHED
    BASELINE, PATCHED = baseline, patched
    return unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessTests)
