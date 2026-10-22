"""Public synthetic fixtures only. Never import private native lab snapshots."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts' if (ROOT / 'scripts').is_dir() else ROOT
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / 'native_follow_lifecycle_payload')]
import follow_lifecycle_observation as obs
import native_follow_lifecycle_schema as schema


def entry(message, level='DEBUG'):
    return f'[2026-01-01T00:00:00.000] [{level}] [SyntheticLogger] {message}\n'


def state(role='follower', *, active=False):
    return {'pid': 2 if role == 'follower' else 1, 'bundleId': 'private-' + role,
        'root': '/private/synthetic/' + role, 'clientId': role + '-client-secret',
        'deviceSessionId': role + '-session-secret', 'contextId': role + '-context-secret',
        'queue': ['original-track-secret'] if role == 'follower' and not active else ['source-track-secret'],
        'currentIndex': 0, 'trackId': 'original-track-secret' if role == 'follower' and not active else 'source-track-secret',
        'runtimeMode': 'follow' if active else 'solo', 'processingState': 'ready',
        'followSourceContextId': 'authority-context-secret' if active else None,
        'preflightDiagnostics': {'recoveryPhase': 'active' if active else None,
            'followRecoveryGateActive': active, 'restoreInProgress': False, 'queueHydrating': False},
        'nativePlayers': [{'playbackState': 3 if active else 4, 'playbackRate': 1.5 if active else 0,
            'requestedRate': 1.5 if active else 1, 'positionMs': 10000, 'seekInProgress': not active,
            'playingIntent': active}], 'unknown': 'DO-NOT-EMIT-AUTH-TOKEN'}


def validate(value, spec):
    if value is None:
        return
    if isinstance(spec, dict):
        assert isinstance(value, dict)
        assert not set(value) - set(spec), set(value) - set(spec)
        for k, v in value.items(): validate(v, spec[k])
    elif isinstance(spec, frozenset):
        assert type(value) is str and value in spec
    elif spec is bool:
        assert type(value) is bool
    elif spec[0] == 'list':
        assert type(value) is list and len(value) <= spec[2]
        for item in value: validate(item, spec[1])
    else:
        assert type(value) in ((int,) if spec[0] == 'integer' else (int, float))
        assert spec[1] <= value <= spec[2]


class ParsingTests(unittest.TestCase):
    def parse(self, text):
        result = obs.parse_log_slice(text.encode())
        validate(result, schema.LOG_SCHEMA)
        self.assertNotIn('secret', json.dumps(result))
        return result

    def test_all_exact_phases_reasons_and_events(self):
        text = ''.join(entry(obs.MARKER + 'recovery_record_persisted phase=' + phase + ' id=secret') for phase in obs.PHASES)
        text += ''.join(entry(obs.MARKER + 'recovery_cleared reason=' + reason + ' id=secret') for reason in obs.REASONS)
        text += ''.join(entry(obs.MARKER + event + ' error=secret') for event in obs.EVENTS[2:])
        result = self.parse(text)
        self.assertTrue(all(count == 1 for count in result['phases'].values()))
        self.assertTrue(all(count == 1 for count in result['clearReasons'].values()))
        self.assertTrue(all(result['events'][event] == 1 for event in obs.EVENTS[2:]))

    def test_nested_cause_and_companion_stack(self):
        text = entry(obs.MARKER + 'local_mirror_failure source=secret error=Bad state: 原账号的播放队列已经失效', 'WARNING')
        text += entry(obs.MARKER + 'local mirror stack: #0      AudioPlayerService._getScopedQueueSongs (private-source.dart:123:4)')
        text += '#1      AudioPlayerService._executeSeek.<anonymous closure> (private-secret.dart:8:9)\n<asynchronous suspension>\n'
        text += entry('unrelated secret')
        text += '#2      AudioPlayer.play (private-secret.dart:1:1)\n'
        result = self.parse(text)
        self.assertEqual(result['mirrorCauses']['stale_queue_owner'], 1)
        self.assertEqual(result['mirrorStackFrames']['queue_metadata_frame'], 1)
        self.assertEqual(result['mirrorStackFrames']['seek_command_frame'], 1)
        self.assertEqual(result['mirrorStackFrames']['player_play_frame'], 0)

    def test_all_known_causes_only_exact_error_body(self):
        result = self.parse(''.join(entry(obs.MARKER + 'local_mirror_failure error=Exception: ' + text) for text in obs.CAUSES))
        self.assertEqual(sum(result['mirrorCauses'].values()), len(obs.CAUSES))
        self.assertEqual(result['mirrorCauses']['other'], 0)
        result = self.parse(entry(obs.MARKER + 'local_mirror_failure error=secret 原账号的播放队列已经失效'))
        self.assertEqual(result['mirrorCauses']['other'], 1)

    def test_injected_unknown_fields_and_markers_never_classify(self):
        text = entry('arbitrary error=' + obs.MARKER + 'recovery_cleared reason=user_stop')
        text += entry(obs.MARKER + 'recovery_cleared error=secret reason=local_mirror_failure')
        text += entry(obs.MARKER + 'recovery_record_persisted phase=secret')
        text += entry(obs.MARKER + 'local_mirror_failure error=' + obs.MARKER + 'local mirror stack:')
        text += '#0      AudioPlayer.play (secret.dart:1:1)\n'
        result = self.parse(text)
        self.assertEqual(sum(result['clearReasons'].values()), 0)
        self.assertEqual(result['unknownReasonCount'], 1)
        self.assertEqual(result['unknownPhaseCount'], 1)
        self.assertEqual(sum(result['mirrorStackFrames'].values()), 0)

    def test_exact_actions_timeouts_and_speed_restore(self):
        text = ''.join(entry('[[EMO_FOLLOW_SYNC]] action=' + action + ' secret=value') for action in obs.ACTIONS)
        text += entry('[[PLAYER_ACT]] op=seek bounded-timeout source=secret position=5')
        text += entry('[[EMO_FOLLOW_SYNC]] speedCorrection restore failed reason=secret error=secret')
        text += entry('error=[[PLAYER_ACT]] op=seek bounded-timeout source=secret')
        result = self.parse(text)
        self.assertEqual(list(result['syncActions'].values()), [1]*6)
        self.assertEqual(result['seekBoundedTimeoutCount'], 1)
        self.assertEqual(result['speedRestoreFailedCount'], 1)

    def test_full_delta_larger_than_old_slice_keeps_first_and_last(self):
        text = entry(obs.MARKER + 'local_mirror_failure error=secret')
        text += entry('padding secret') * 9000
        text += entry(obs.MARKER + 'recovery_cleared reason=local_mirror_failure')
        self.assertGreater(len(text.encode()), 256*1024)
        result = self.parse(text)
        self.assertEqual(result['events']['local_mirror_failure'], 1)
        self.assertEqual(result['clearReasons']['local_mirror_failure'], 1)
        self.assertEqual(result['coverage'], 'complete')

    def test_partial_long_invalid_lines_have_explicit_coverage(self):
        result = self.parse(entry('x'*9000) + entry(obs.MARKER + 'recovery_cleared reason=user_stop').rstrip('\n'))
        self.assertEqual(result['coverage'], 'partial')
        self.assertTrue(result['lineTruncated'])
        self.assertTrue(result['partialFinalLine'])
        self.assertEqual(sum(result['clearReasons'].values()), 0)
        result = obs.parse_log_slice(b'\xff\n')
        self.assertTrue(result['invalidEncoding'])
        self.assertEqual(result['coverage'], 'partial')

    def test_companion_frame_count_is_bounded(self):
        text = entry(obs.MARKER + 'local mirror stack:') + '#1 AudioPlayer.play (secret.dart:1:1)\n'*100
        result = self.parse(text)
        self.assertTrue(result['stackTruncated'])
        self.assertEqual(result['mirrorStackFrames']['player_play_frame'], 64)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.original, self.authority = state(), state('authority')
        self.matrix = SimpleNamespace(clients=[None, None, object()], last=[self.authority, {}, self.original], fixture_state_directory='/private/synthetic')
        self.cursor = patch.object(obs, 'capture_log_cursor', return_value={'status':'unavailable'}).start()
        self.server = patch.object(obs, 'observe_follow_server', return_value={'status':'read_only_snapshot','admissionObserved':'unknown','leasePresent':False}).start()
        self.logs = patch.object(obs, 'read_log_since', return_value={'coverage':'unavailable'}).start()
        self.addCleanup(patch.stopall)
        obs.begin_follow_lifecycle(self.matrix, 'authority-context-secret', self.original,
            lambda a, f, c: f.get('runtimeMode') == 'follow' and f['nativePlayers'][0]['playbackRate'] == 1.5)

    def test_original_pending_seek_is_observed_not_rejected(self):
        value = self.matrix.follow_lifecycle_observation.value
        self.assertTrue(value['originalPausedTask']['seekInProgress'])
        self.assertFalse(value['originalPausedTask']['playingIntent'])
        self.assertTrue(value['originalPausedTask']['nativePaused'])
        validate(value, schema.FOLLOW_LIFECYCLE_SCHEMA)

    def test_never_entered_distinct_from_entered_auto_restored(self):
        observer = self.matrix.follow_lifecycle_observation
        observer.command_returned({'ok':True,'state':self.original})
        observer.sample([self.authority,{},self.original])
        self.assertFalse(observer.value['seenActiveRecovery'])
        active = state(active=True)
        observer.sample([self.authority,{},active])
        observer.sample([self.authority,{},self.original])
        value = observer.finish()
        self.assertTrue(value['seenActiveRecovery'])
        self.assertTrue(value['seenOriginalAfterFollow'])
        self.assertTrue(value['seenNativeReady'])
        self.assertEqual(self.server.call_count, 5)  # command, active, ready, restored, failure
        validate(value, schema.FOLLOW_LIFECYCLE_SCHEMA)
        for secret in ('secret', '/private', 'bundleId', 'clientId', 'pid', 'DO-NOT'):
            self.assertNotIn(secret, json.dumps(value))

    def test_only_existing_start_wait_samples_are_observed(self):
        original = copy.deepcopy(self.original)
        obs.observe_follow_wait(self.matrix, 'strict-native-measurement', [self.authority,{},state(active=True)])
        self.assertEqual(self.matrix.follow_lifecycle_observation.value['sampleCount'], 0)
        self.assertEqual(self.server.call_count, 0)
        obs.observe_follow_wait(self.matrix, 'native-follow-start', [self.authority,{},state(active=True)])
        self.assertEqual(self.matrix.follow_lifecycle_observation.value['sampleCount'], 1)
        self.assertEqual(self.original, original)

    def test_bounded_transitions_and_server_milestones(self):
        observer = self.matrix.follow_lifecycle_observation
        observer.command_returned({'ok':True,'state':self.original})
        for i in range(1002):
            observer.sample([self.authority,{},state(active=bool(i%2))])
        value = observer.finish()
        self.assertEqual(value['sampleCount'], 1000)
        self.assertTrue(value['sampleCountSaturated'])
        self.assertEqual(len(value['transitions']), 12)
        self.assertTrue(value['transitionsTruncated'])
        self.assertLessEqual(self.server.call_count, 6)
        observer.finish()
        self.assertEqual(self.logs.call_count, 1)
        validate(value, schema.FOLLOW_LIFECYCLE_SCHEMA)

    def test_identity_changes_are_finite_booleans(self):
        changed = copy.deepcopy(self.authority)
        changed['pid'] = 999
        obs.observe_follow_wait(self.matrix, 'native-follow-start', [changed,{},self.original])
        self.assertTrue(self.matrix.follow_lifecycle_observation.value['identityChangeObserved'])
        self.assertFalse(self.matrix.follow_lifecycle_observation.value['transitions'][-1]['sameAuthorityIdentity'])

    def test_command_output_is_finite_and_not_a_pass_verdict(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            obs.observe_follow_command(self.matrix, {'ok':True,'state':state(active=True),'error':'AUTH-TOKEN'})
        output = json.loads(stream.getvalue())
        self.assertIn(output['stage'], schema.STAGES)
        self.assertEqual(output['status'], 'not-verified')
        validate(output['followLifecycle'], schema.FOLLOW_LIFECYCLE_SCHEMA)
        self.assertNotIn('AUTH-TOKEN', stream.getvalue())

    def test_observer_failures_never_raise_or_change_original_state(self):
        with patch.object(self.matrix.follow_lifecycle_observation, 'sample', side_effect=RuntimeError('private')):
            obs.observe_follow_wait(self.matrix, 'native-follow-start', [])
        self.assertEqual(self.matrix.follow_lifecycle_observation.value['observationErrorCount'], 1)
        self.server.side_effect = RuntimeError('secret')
        self.matrix.follow_lifecycle_observation.command_returned({})
        self.assertEqual(self.matrix.follow_lifecycle_observation.value['serverFollow'][0]['observation']['status'], 'observation_unavailable')


class OwnedLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.bundle = 'com.example.emosonic.nativelab.rsynthetic.follower'
        self.root = self.home / 'Library/Containers' / self.bundle / 'Data/Library/Application Support' / self.bundle / 'native-playback-lab-follower'
        (self.root/'logs').mkdir(parents=True)
        (self.root/'.native-mac-lab.json').write_text(json.dumps({'kind':'emosonic-native-mac-lab','bundleId':self.bundle,'instance':'follower'}))
        self.log = self.root/'logs/debug.log'
        self.log.write_text('prior-secret\n')
        self.client = SimpleNamespace(role='follower', bundle_id=self.bundle, process=SimpleNamespace(pid=123))
        self.state = {'bundleId':self.bundle,'pid':123,'root':str(self.root)}
        patch.object(obs.Path, 'home', return_value=self.home).start()
        self.addCleanup(patch.stopall)

    def test_cursor_excludes_existing_log_and_reads_appended_events(self):
        cursor = obs.capture_log_cursor(self.client, self.state)
        with self.log.open('a') as stream: stream.write(entry(obs.MARKER+'recovery_cleared reason=local_mirror_failure'))
        result = obs.read_log_since(self.client, self.state, cursor)
        self.assertEqual(result['coverage'], 'complete')
        self.assertEqual(result['clearReasons']['local_mirror_failure'], 1)
        self.assertNotIn('secret', json.dumps(result))

    def test_rotation_and_in_place_rewrite_refuse_false_completeness(self):
        cursor = obs.capture_log_cursor(self.client, self.state)
        self.log.rename(self.log.with_suffix('.old'))
        self.log.write_text('new secret\n')
        self.assertEqual(obs.read_log_since(self.client, self.state, cursor), {'coverage':'rotated'})
        cursor = obs.capture_log_cursor(self.client, self.state)
        self.log.write_text('bad secret\n')
        self.assertEqual(obs.read_log_since(self.client, self.state, cursor), {'coverage':'rotated'})

    def test_wrong_process_and_symlink_are_refused(self):
        self.state['pid'] = 124
        self.assertEqual(obs.capture_log_cursor(self.client, self.state)['status'], 'ownership_refused')
        self.state['pid'] = 123
        self.log.rename(self.log.with_suffix('.old'))
        self.log.symlink_to(self.log.with_suffix('.old'))
        self.assertEqual(obs.capture_log_cursor(self.client, self.state)['status'], 'ownership_refused')

    def test_file_bound_and_partial_initial_line_are_explicit(self):
        with patch.object(obs, 'MAX_LOG', 5):
            self.assertEqual(obs.capture_log_cursor(self.client, self.state)['status'], 'file_bound_exceeded')
        self.log.write_text('partial secret')
        cursor = obs.capture_log_cursor(self.client, self.state)
        with self.log.open('a') as stream: stream.write(' ignored\n'+entry(obs.MARKER+'recovery_cleared reason=user_stop'))
        result = obs.read_log_since(self.client, self.state, cursor)
        self.assertTrue(result['partialInitialLine'])
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(result['clearReasons']['user_stop'], 1)


if __name__ == '__main__': unittest.main()
