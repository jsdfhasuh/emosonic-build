import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import native_consistency_observation as o
import current_native_check as n


def fixture():
    assertions = ['        ' + item[1] for item in o.CHECKS]
    assertions.append('        ' + o.STREAM_ASSERT)
    return ("def local_setup_diagnostic(state):\n    result = {}\n    preflight = {}\n    result['preflight'] = preflight\n    return result\n" + 'class Matrix:\n    def run(self):\n' + '\n'.join(assertions) + "\n        a.command('playQueue', trackIds=ids)\n        until = time.monotonic() + timeout\n        if True:\n                states = self.states()\n" + o.FAILURE_ENTRY +
            "        print(json.dumps({'stage': self.stage,\n" + o.FAILURE_FIELDS + "\n        }))\n")


class ObservationTests(unittest.TestCase):
    def test_assertion_asts_identical(self):
        original = fixture()
        patched = o.patch_text(original)
        assertions = lambda text: [ast.dump(node) for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Assert)]
        self.assertEqual(assertions(original), assertions(patched))
        self.assertEqual(len(assertions(patched)), 8)
        self.assertTrue(o.STAGES <= n.PUBLIC_STAGES)
        for stage in o.STAGES:
            self.assertEqual(patched.count(repr(stage)), 1)

    def test_refuses_repeat_missing_or_duplicated_assertion(self):
        for text in (o.patch_text(fixture()), fixture().replace(o.CHECKS[0][1], 'pass'), fixture() + '\n' + fixture()):
            with self.assertRaises(ValueError):
                o.patch_text(text)

    def test_constrained_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'tool/native_playback_mac/run_lab.py'
            target.parent.mkdir(parents=True)
            target.write_text(fixture())
            o.apply_observations(target)
            self.assertIn('handoff-check-continuity', target.read_text())
            wrong = target.parent / 'other.py'
            wrong.write_text(fixture())
            with self.assertRaises(ValueError):
                o.apply_observations(wrong)
            target.unlink()
            target.symlink_to(wrong)
            with self.assertRaises(ValueError):
                o.apply_observations(target)

    def test_traceback_hook_returns_only_known_module_and_line(self):
        namespace = {'Path': Path, 'self': type('Snapshot', (), {'fixture_state_directory': None})()}
        snippet = 'def collect(error):\n' + ''.join(line[4:] + '\n' for line in o.FAILURE_LOCATION.splitlines()) + '    return _failure_location\n'
        exec(snippet, namespace)
        for filename, expected in (('/private/token/run_lab.py', {'module': 'run_lab.py', 'line': 1}),
                                   ('/private/token/extended_handoff.py', {'module': 'extended_handoff.py', 'line': 1}),
                                   ('/private/token/secret.py', {})):
            try:
                exec(compile('raise AssertionError()', filename, 'exec'))
            except AssertionError as error:
                self.assertEqual(namespace['collect'](error), expected)

    def test_failure_location_never_exposes_arbitrary_paths_or_text(self):
        for module in ('run_lab.py', 'extended_handoff.py'):
            self.assertEqual(n.report_line(json.dumps({'failureLocation': {'module': module, 'line': 123}})),
                             {'failureLocation': {'module': module, 'line': 123}})
        for line in (True, 0, 100001, 'secret', float('nan')):
            self.assertFalse(n.report_line(json.dumps({'failureLocation': {
                'module': '/private/run_lab.py', 'line': line, 'message': 'secret'}})))

    def test_existing_log_counts_never_return_raw_content(self):
        namespace = {'Path': Path, 'json': json}
        exec(o.LOG_HELPER, namespace)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'owned'; (root / 'logs').mkdir(parents=True)
            log = root / 'logs/debug.log'
            log.write_text('SECRET token=never-export\n'
                '[[AUDIO_EXECUTION_LEASE]] stale_audio_callback_dropped source=triggerPlay:scopedNativeQueue:beforePlay private-id\n'
                '[[AUDIO_EXECUTION_LEASE]] stale_audio_callback_dropped source=triggerPlay:scopedNativeQueue:beforePlayExtra secret\n'
                '[[AUDIO_EXECUTION_LEASE]] stale_audio_callback_dropped source=triggerPlay:scopedSingleSource:beforePlay\n'
                '[[CMD_DROP]] staleExecutionGuard secret\n'
                '[[AUDIO_EXECUTION_LEASE]] stale_command_side_effect_dropped secret\n'
                '[[PLAYER_ACT]] op=play failed secret\n[[PLAYER_ACT]] op=play slow-start secret\n')
            result = namespace['bounded_owned_log_counts'](root, root)
            self.assertEqual(result, {'readStatus': 'read', 'scopedNativeQueueBeforePlay': 1,
                'scopedSingleSourceBeforePlay': 1, 'staleExecutionGuard': 1, 'staleCommandSideEffect': 1,
                'playFailed': 1, 'playSlowStart': 1})
            self.assertNotIn('secret', json.dumps(result).lower())
            self.assertEqual(namespace['bounded_owned_log_counts'](root, root.parent)['readStatus'], 'unverified')
            with log.open('wb') as stream:
                stream.truncate(8 * 1024 * 1024 + 1)
            self.assertEqual(namespace['bounded_owned_log_counts'](root, root)['readStatus'], 'oversized')
            log.unlink(); log.symlink_to(root.parent / 'private.txt')
            self.assertEqual(namespace['bounded_owned_log_counts'](root, root)['readStatus'], 'symlink_refused')

    def test_log_owner_requires_exact_container_sentinel_and_process(self):
        namespace = {'Path': Path, 'json': json}
        exec(o.LOG_HELPER, namespace)
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'home', return_value=Path(folder)):
            bundle = 'com.example.emosonic.nativelab.r1-1.authority'
            root = Path(folder) / 'Library/Containers' / bundle / 'Data/Library/Application Support' / bundle / 'native-playback-lab-authority'
            (root / 'logs').mkdir(parents=True)
            (root / 'logs/debug.log').write_text('[[PLAYER_ACT]] op=play failed private-password')
            sentinel = root / '.native-mac-lab.json'
            sentinel.write_text(json.dumps({'kind': 'emosonic-native-mac-lab', 'bundleId': bundle, 'instance': 'authority'}))
            client = SimpleNamespace(bundle_id=bundle, role='authority', process=SimpleNamespace(pid=123))
            state = {'root': str(root), 'bundleId': bundle, 'pid': 123}
            self.assertEqual(namespace['owned_client_log_counts'](client, state)['playFailed'], 1)
            for changed in (dict(state, pid=124), dict(state, root=folder), dict(state, bundleId='other')):
                self.assertEqual(namespace['owned_client_log_counts'](client, changed), {'readStatus': 'ownership_refused'})
            sentinel.write_text('{}')
            self.assertEqual(namespace['owned_client_log_counts'](client, state), {'readStatus': 'ownership_refused'})

    def test_log_reads_only_bounded_tail(self):
        namespace = {'Path': Path, 'json': json}
        exec(o.LOG_HELPER, namespace)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'logs').mkdir()
            (root / 'logs/debug.log').write_text('[[PLAYER_ACT]] op=play failed\n' + 'x' * (256 * 1024) + '\n[[PLAYER_ACT]] op=play slow-start\n')
            result = namespace['bounded_owned_log_counts'](root, root)
            self.assertEqual(result['playFailed'], 0)
            self.assertEqual(result['playSlowStart'], 1)

    def test_attribution_proof_failure_is_typed_and_redacted(self):
        raw = {'stage': 'scoped-attribution-proof-failure', 'status': 'failed', 'diagnostic': {
            'phase': 'patched', 'category': 'compiler', 'code': 'compilation_failed',
            'exitCode': 1, 'failedTestOrdinal': 3, 'sourceModule': 'native_lab_scoped_api_client.dart',
            'sourceLine': 20, 'error': 'secret-token', 'uri': 'secret-url'}}
        out = n.report_line(json.dumps(raw))
        self.assertEqual(out['diagnostic']['sourceLine'], 20)
        self.assertNotIn('secret', json.dumps(out))
        self.assertFalse(n.report_line(json.dumps({'diagnostic': {'phase': 'private',
            'exitCode': True, 'failedTestOrdinal': 7, 'sourceLine': 2001,
            'sourceModule': '/private/native_lab_scoped_api_client.dart', 'code': 'secret'}})))

    def test_startup_and_follow_stages_are_finite(self):
        for stage in ('source-native-decode', 'real-apps-register', 'source-rate-controls-settled',
                      'extended-real-prepare-before-cancel', 'extended-native-cleanup-pause',
                      'extended-source-rate-0.8:native-advancement-readiness', 'paused-original-task-restored'):
            self.assertEqual(n.report_line(json.dumps({'stage': stage})), {'stage': stage})
        self.assertIsNone(n.report_line(json.dumps({'stage': 'source-native-decode-private-token'})))

    def test_every_diagnostic_schema_rejects_unknown_fields(self):
        def sample(schema, hostile=False):
            if schema is bool:
                return True
            if isinstance(schema, frozenset):
                return sorted(schema)[0]
            if isinstance(schema, tuple):
                if schema[0] == 'list':
                    return [sample(schema[1], hostile)]
                return max(0, schema[1])
            value = {key: sample(child, hostile) for key, child in schema.items()}
            if hostile:
                value['privateCredential'] = 'DO_NOT_EXPOSE'
            return value
        clean = sample(n.DIAGNOSTIC_SCHEMA)
        hostile = sample(n.DIAGNOSTIC_SCHEMA, True)
        self.assertEqual(n.report_line(json.dumps(hostile)), clean)
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(n.report_line(json.dumps(hostile))))

    def test_no_duplicate_play_command_or_assertion_changes(self):
        before = ast.parse(fixture()); after = ast.parse(o.patch_text(fixture()))
        def commands(tree):
            return [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == 'command']
        self.assertEqual(commands(before), commands(after))
        self.assertEqual(len(commands(after)), 1)

    def test_setup_and_wait_values_reject_wrong_types(self):
        out = n.report_line(json.dumps({'nativePlayback': [{'clientOrdinal': 0, 'setup': {
            'canControl': True, 'currentIndex': 0, 'queueLength': 3, 'trackPresent': True,
            'contextId': 'DO_NOT_EXPOSE', 'bindingRole': 'private-token',
            'preflight': {'processingState': 'ready', 'audioLeasePresent': True,
                          'queueHydrating': 'private-token', 'connectionGeneration': False}}}],
            'waitObservation': {'elapsedMs': 45000, 'pollCount': True, 'timeoutSeconds': 'secret'},
            'startupStreams': {'streamCount': 2, 'targetStreamCount': False, 'url': 'secret'}}))
        self.assertEqual(out['nativePlayback'][0]['setup']['preflight'],
                         {'processingState': 'ready', 'audioLeasePresent': True})
        self.assertEqual(out['waitObservation'], {'elapsedMs': 45000})
        self.assertEqual(out['startupStreams'], {'streamCount': 2})
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(out))

    def test_diagnostics_are_finite_typed_and_private(self):
        value = {'stage': 'handoff-check-media-provenance', 'consistencyObservation': {
            'streamCount': 4, 'targetStreamCount': 0, 'latestRequestDeltaMs': -42.5,
            'trackMatches': True, 'canonicalPlaying': 'private', 'targetTrackStreamCount': True,
            'nativeRate': float('inf'), 'continuityErrorMs': float('nan'),
            'atMs': 1777777777777, 'url': 'secret', 'sourcePositionMs': 'secret',
            'numericTimestampCount': -1, 'postStartStreamCount': 1000001}}
        self.assertEqual(n.report_line(json.dumps(value)), {'stage': 'handoff-check-media-provenance',
            'consistencyObservation': {'streamCount': 4, 'targetStreamCount': 0,
                'latestRequestDeltaMs': -42.5, 'trackMatches': True}})

if __name__ == '__main__':
    unittest.main()
