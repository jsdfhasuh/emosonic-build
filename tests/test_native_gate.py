"""Synthetic fail-closed checks; actual Java contracts run in the build job."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_pipeline import p


class NativeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.test-', dir=p.ROOT)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.plugin = self.source / 'third_party/just_audio'
        self.production = self.plugin / 'android/src/main/java/com/ryanheise/just_audio/NativeStartGate.java'
        self.test = self.plugin / 'android/src/test/java/com/ryanheise/just_audio/NativeStartGateTest.java'
        for path in (self.production, self.test):
            path.parent.mkdir(parents=True)
            path.write_text('synthetic-test-fixture')
        self.registration = self.source / '.flutter-plugins-dependencies'
        self.registration.write_text(json.dumps({'plugins': {'android': [
            {'name': 'just_audio', 'path': str(self.plugin), 'native_build': True}]}}))
        self.java = self.root / 'jdk'
        (self.java / 'bin').mkdir(parents=True)
        for name in ('java', 'javac'):
            (self.java / 'bin' / name).write_text('synthetic-test-fixture')
        self.env = {'JAVA_HOME': str(self.java)}
        self.apk = self.source / 'build/app/outputs/flutter-apk/app-debug.apk'
        self.calls = []
        self.marker = 'PASS NativeStartGateTest: 104 checks (deterministic JVM, no device claim)\n'
        self.missing_class = False
        self.skip_apk = False
        self.fail_stage = None
        self.root_patch = patch.object(p, 'ROOT', self.root)
        self.root_patch.start()
        self.print_patch = patch('builtins.print')
        self.print_patch.start()

    def tearDown(self):
        self.print_patch.stop()
        self.root_patch.stop()
        self.tmp.cleanup()

    def fake_quiet(self, args, source, env):
        self.assertEqual(source, self.source)
        self.assertEqual(env, self.env)
        self.calls.append(args)
        if self.fail_stage == len(self.calls):
            raise p.GateError('Synthetic subprocess failed.')
        if len(self.calls) == 1:
            self.assertEqual(args[:5], [str(self.java / 'bin/javac'), '--release', '8', '-encoding', 'UTF-8'])
            self.assertEqual(args[-2:], [str(self.production), str(self.test)])
            classes = Path(args[args.index('-d') + 1]) / 'com/ryanheise/just_audio'
            classes.mkdir(parents=True)
            for name in ('NativeStartGate', 'NativeStartGateTest'):
                if not (self.missing_class and name == 'NativeStartGateTest'):
                    (classes / (name + '.class')).write_bytes(b'synthetic-compiled-class')
        elif len(self.calls) == 2:
            self.assertEqual(args[0:3], [str(self.java / 'bin/java'), '-ea', '-cp'])
            self.assertEqual(args[-1], 'com.ryanheise.just_audio.NativeStartGateTest')
            return self.marker
        elif len(self.calls) == 3:
            self.assertEqual(args, ['flutter', 'build', 'apk', '--debug', '--target-platform=android-arm64'])
            if not self.skip_apk:
                self.apk.parent.mkdir(parents=True)
                self.apk.write_bytes(b'synthetic-apk')
        return ''

    def run_gate(self):
        with patch.object(p, 'quiet', side_effect=self.fake_quiet):
            p.native_android_contract(self.source, self.env)

    def test_compiles_production_and_test_then_executes_before_android_build(self):
        self.run_gate()
        self.assertEqual(len(self.calls), 3)
        self.assertFalse(list(self.root.glob('.native-contract-*')))

    def test_missing_production_or_test_fails_before_execution(self):
        for path in (self.production, self.test):
            data = path.read_bytes()
            path.unlink()
            with self.assertRaises(p.GateError):
                self.run_gate()
            self.assertEqual(self.calls, [])
            path.write_bytes(data)

    def test_nonvendored_registration_fails_before_execution(self):
        self.registration.write_text(json.dumps({'plugins': {'android': [
            {'name': 'just_audio', 'path': str(self.root / 'pub-cache/just_audio'), 'native_build': True}]}}))
        with self.assertRaises(p.GateError):
            self.run_gate()
        self.assertEqual(self.calls, [])

    def test_missing_compiled_class_fails_before_test_or_android_build(self):
        self.missing_class = True
        with self.assertRaises(p.GateError):
            self.run_gate()
        self.assertEqual(len(self.calls), 1)

    def test_missing_or_wrong_pass_count_fails_before_android_build(self):
        for marker in ('', 'PASS', self.marker.replace('104', '0'),
                       self.marker.replace('104', '103'), self.marker + 'extra'):
            self.calls.clear()
            self.marker = marker
            with self.subTest(marker=marker), self.assertRaises(p.GateError):
                self.run_gate()
            self.assertEqual(len(self.calls), 2)

    def test_each_nonzero_subprocess_stops_gate(self):
        for stage in (1, 2, 3):
            self.calls.clear()
            self.fail_stage = stage
            with self.subTest(stage=stage), self.assertRaises(p.GateError):
                self.run_gate()
            self.assertEqual(len(self.calls), stage)
            self.assertFalse(list(self.root.glob('.native-contract-*')))

    def test_missing_android_output_fails_gate(self):
        self.skip_apk = True
        with self.assertRaises(p.GateError):
            self.run_gate()

    def test_native_gate_runs_before_any_release_signing_material(self):
        env = {'ANDROID_KEYSTORE_BASE64': 'synthetic', 'ANDROID_STORE_PASSWORD': 'synthetic',
               'ANDROID_KEY_PASSWORD': 'synthetic', 'ANDROID_KEY_ALIAS': 'synthetic'}
        with (patch.dict(p.os.environ, env),
              patch.object(p, 'source_context', return_value=(self.source, '1.0.9+26', 'a' * 40, 'https://example.test')),
              patch.object(p, 'codegen'),
              patch.object(p, 'native_android_contract', side_effect=p.GateError('Blocked')),
              patch.object(p.base64, 'b64decode') as decode,
              self.assertRaises(p.GateError)):
            p.build()
        decode.assert_not_called()
        self.assertFalse((self.source / 'android/key.properties').exists())
        self.assertFalse((self.source / 'android/keystore/emosonic-release.jks').exists())
        self.assertFalse((self.source / 'build-defines.json').exists())


if __name__ == '__main__':
    unittest.main()
