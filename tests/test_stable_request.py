"""Synthetic tests for the single authorized stable request, with no credentials."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_pipeline import p, ENV


class StableRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.test-', dir=p.ROOT)
        self.root = Path(self.tmp.name)
        self.request = self.root / p.STABLE_PUSH_PATH
        self.request.parent.mkdir()
        self.request.write_text(json.dumps(p.STABLE_PUSH_REQUEST))
        self.event = {'before': p.STABLE_PUSH_PARENT, 'after': ENV['GITHUB_SHA'],
                      'ref': 'refs/heads/main', 'forced': False, 'created': False, 'deleted': False,
                      'head_commit': {'id': ENV['GITHUB_SHA'], 'message': p.STABLE_PUSH_MESSAGE}}
        self.event_path = self.root / 'event.json'
        self.event_path.write_text(json.dumps(self.event))
        self.env = dict(ENV, GITHUB_EVENT_NAME='push', GITHUB_EVENT_PATH=str(self.event_path),
                        GITHUB_WORKFLOW_REF=p.BUILDER + '/.github/workflows/android.yml@refs/heads/main',
                        SOURCE_SHA=p.STABLE_PUSH_REQUEST['source_sha'], BUILD_VERSION=p.STABLE_PUSH_REQUEST['version'])
        self.root_patch = patch.object(p, 'ROOT', self.root)
        self.env_patch = patch.dict(os.environ, self.env, clear=True)
        self.root_patch.start()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_exact_request_is_accepted_at_every_stage(self):
        p.context()
        for name in ('SOURCE_SHA', 'BUILD_VERSION', 'RELEASE_MODE'):
            os.environ.pop(name)
            p.context()

    def test_wrong_transition_is_rejected(self):
        for key, value in [('before', 'b' * 40), ('after', 'b' * 40), ('ref', 'refs/heads/other'),
                           ('forced', True), ('created', True), ('deleted', True)]:
            with self.subTest(key=key):
                self.event_path.write_text(json.dumps(dict(self.event, **{key: value})))
                with self.assertRaises(p.GateError):
                    p.context()
        self.event_path.write_text(json.dumps(self.event))

    def test_wrong_marker_is_rejected(self):
        for head in ({}, {'id': ENV['GITHUB_SHA'], 'message': 'normal change'},
                     {'id': 'b' * 40, 'message': p.STABLE_PUSH_MESSAGE}):
            self.event_path.write_text(json.dumps(dict(self.event, head_commit=head)))
            with self.assertRaises(p.GateError):
                p.context()

    def test_request_source_version_mode_or_attempt_cannot_change(self):
        for key, value in [('source_sha', 'b' * 40), ('version', '1.0.7+25'), ('mode', 'build-only'), ('attempt', 99)]:
            self.request.write_text(json.dumps(dict(p.STABLE_PUSH_REQUEST, **{key: value})))
            with self.assertRaises(p.GateError):
                p.context()
        self.request.unlink()
        with self.assertRaises(p.GateError):
            p.context()

    def test_wrong_workflow_or_environment_override_is_rejected(self):
        for key, value in [('GITHUB_WORKFLOW_REF', p.BUILDER + '/.github/workflows/other.yml@refs/heads/main'),
                           ('SOURCE_SHA', 'b' * 40), ('BUILD_VERSION', '1.0.7+25'), ('RELEASE_MODE', 'build-only')]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(p.GateError):
                p.context()

    def test_master_movement_and_version_mismatch_emit_no_outputs(self):
        os.environ.pop('BUILD_VERSION')
        os.environ['SOURCE_READ_TOKEN'] = 'synthetic'
        for sha, candidate in [('b' * 40, '1.0.7+24'), (p.STABLE_PUSH_REQUEST['source_sha'], '1.0.7+25')]:
            branch = {'ref': p.SOURCE_REF, 'object': {'type': 'commit', 'sha': sha}}
            with patch.object(p, 'api', return_value=branch), patch.object(p, 'remote_source_version', return_value=candidate), patch.object(p, 'history') as history, patch.object(p, 'output') as output, self.assertRaises(p.GateError):
                p.prepare()
            history.assert_not_called()
            output.assert_not_called()

    def test_exact_master_and_source_version_emit_shared_snapshot(self):
        os.environ.pop('BUILD_VERSION')
        os.environ['SOURCE_READ_TOKEN'] = 'synthetic'
        sha, candidate = p.STABLE_PUSH_REQUEST['source_sha'], p.STABLE_PUSH_REQUEST['version']
        branch = {'ref': p.SOURCE_REF, 'object': {'type': 'commit', 'sha': sha}}
        with patch.object(p, 'api', return_value=branch), patch.object(p, 'remote_source_version', return_value=candidate), patch.object(p, 'history', return_value=['v1.0.6+23']), patch.object(p, 'output') as output:
            p.prepare()
        self.assertEqual(dict(call.args for call in output.call_args_list)['source_sha'], sha)

    def test_windows_codegen_binds_dart_to_verified_flutter_installation(self):
        flutter = self.root / 'flutter/bin/flutter.bat'
        runtime = self.root / 'flutter/bin/cache/dart-sdk/bin/dart.exe'
        runtime.parent.mkdir(parents=True)
        flutter.write_text('synthetic')
        runtime.write_text('synthetic')
        # Patch only the platform branch; preserve this host's pathlib concrete class.
        with patch.object(p, 'Path', type(self.root)), patch.object(p.os, 'name', 'nt'), patch.object(p.shutil, 'which', return_value=str(flutter)), patch.object(p, 'quiet') as quiet:
            p.codegen(self.root, {})
        self.assertEqual(quiet.call_args_list[0].args[0], [str(flutter), 'pub', 'get'])
        self.assertEqual(quiet.call_args_list[1].args[0], [str(runtime), 'run', 'scripts/check_navigation_consistency.dart'])
        self.assertEqual(quiet.call_args_list[2].args[0], [str(runtime), 'run', 'build_runner', 'build', '--delete-conflicting-outputs'])

    def test_failure_diagnostics_never_emit_raw_private_output(self):
        import subprocess
        result = subprocess.CompletedProcess(['synthetic'], 255, b'private-source-secret', b'The system cannot find the path specified. private-secret')
        with patch.object(p.subprocess, 'run', return_value=result), self.assertRaises(p.GateError) as error:
            p.quiet(['synthetic'])
        self.assertIn('exit 255; missing-launcher-path', str(error.exception))
        self.assertNotIn('private', str(error.exception))

    def test_android_tools_reuses_installed_tools_without_path_dependency(self):
        sdk = self.root / 'sdk'
        target = sdk / 'build-tools' / p.POLICY['android_build_tools']
        target.mkdir(parents=True)
        for name in ('aapt', 'apksigner'):
            (target / name).write_text('synthetic')
        with patch.dict(os.environ, {'ANDROID_HOME': str(sdk)}), patch.object(p, 'quiet') as quiet:
            p.android_tools()
            quiet.assert_not_called()

    def test_android_tools_uses_absolute_manager_when_needed(self):
        sdk = self.root / 'sdk'
        manager = sdk / 'cmdline-tools/latest/bin/sdkmanager'
        manager.parent.mkdir(parents=True)
        manager.write_text('synthetic')
        def install(args):
            self.assertEqual(args, [str(manager), 'build-tools;' + p.POLICY['android_build_tools']])
            target = sdk / 'build-tools' / p.POLICY['android_build_tools']
            target.mkdir(parents=True)
            for name in ('aapt', 'apksigner'):
                (target / name).write_text('synthetic')
        with patch.dict(os.environ, {'ANDROID_HOME': str(sdk)}), patch.object(p, 'quiet', side_effect=install) as quiet:
            p.android_tools()
            quiet.assert_called_once()

    def test_android_tools_missing_manager_is_closed(self):
        with patch.dict(os.environ, {'ANDROID_HOME': str(self.root / 'missing')}), patch.object(p, 'quiet') as quiet, self.assertRaises(p.GateError):
            p.android_tools()
        quiet.assert_not_called()


if __name__ == '__main__':
    unittest.main()
