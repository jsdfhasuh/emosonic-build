import json
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import darwin_anchor_check as c


class DarwinAnchorCheckTests(unittest.TestCase):
    def child(self, stage, body, count=1):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'synthetic_anchor.py').write_text('import unittest\nclass Fixture(unittest.TestCase):\n    def test_anchor(self):\n        ' + body + '\n')
            r = subprocess.run([sys.executable, '-B', '-c', c.CHILD, stage,
                                'synthetic_anchor', 'synthetic_anchor.Fixture.test_anchor', c.MARKER, str(count)],
                               cwd=root, capture_output=True, text=True)
            return r.returncode, json.loads(r.stdout), r.stderr

    def test_exact_causal_red_only(self):
        code, value, stderr = self.child('red', 'self.fail(' + repr(c.MARKER) + ')')
        self.assertEqual(code, 0)
        self.assertTrue(value['expectedRegressionFailure'])
        self.assertEqual(value['failedTests'], [{'ordinal': 1, 'reason': 'causal_anchor_missing'}])
        self.assertEqual(stderr, '')

    def test_wrong_failure_error_skip_or_pass_cannot_prove_red(self):
        for body in ('self.fail("private unrelated")', 'raise RuntimeError("private compilation")', 'self.skipTest("private")', 'pass'):
            with self.subTest(body=body):
                code, value, stderr = self.child('red', body)
                self.assertNotEqual(code, 0)
                self.assertFalse(value['expectedRegressionFailure'])
                self.assertNotIn('private', json.dumps(value) + stderr)

    def test_marker_in_traceback_source_comment_is_not_causal(self):
        code, value, stderr = self.child('red', 'self.fail("private unrelated")  # ' + c.MARKER)
        self.assertEqual(code, 1)
        self.assertFalse(value['expectedRegressionFailure'])
        self.assertEqual(value['failedTests'], [{'ordinal': 1, 'reason': 'test_failure'}])
        self.assertNotIn('private', json.dumps(value) + stderr)

    def test_marker_in_wrong_exception_or_extra_argument_is_not_causal(self):
        for body in ('raise RuntimeError(' + repr(c.MARKER) + ')',
                     'raise AssertionError(' + repr(c.MARKER) + ', "private")',
                     'raise type("Other", (AssertionError,), {})(' + repr(c.MARKER) + ')',
                     'raise AssertionError(type("Trick", (), {"__eq__": lambda self, other: True})())',
                     'self.fail("prefix " + ' + repr(c.MARKER) + ')'):
            code, value, _ = self.child('red', body)
            self.assertEqual(code, 1)
            self.assertFalse(value['expectedRegressionFailure'])

    def test_green_count_no_skips_and_failure_privacy(self):
        for body, count, outcome in [('pass', 1, 0), ('pass', 2, 1), ('pass', 0, 1), ('self.skipTest("private")', 1, 1), ('self.fail("private")', 1, 1)]:
            with self.subTest(body=body, count=count):
                code, value, stderr = self.child('green', body, count)
                self.assertEqual(code, outcome)
                self.assertNotIn('private', json.dumps(value) + stderr)

    def test_subtest_failure_retains_parent_ordinal_without_private_detail(self):
        code, value, stderr = self.child('green', 'exec("with self.subTest(secret=123):\\n self.fail(\'private\')")')
        self.assertEqual(code, 1)
        self.assertEqual(value['failedTests'], [{'ordinal': 1, 'reason': 'test_failure'}])
        self.assertNotIn('private', json.dumps(value) + stderr)

    def test_exact_marker_in_subtest_does_not_satisfy_direct_causal_target(self):
        code, value, _ = self.child('red', 'exec("with self.subTest(secret=123):\\n self.fail(' + repr(c.MARKER) + ')")')
        self.assertEqual(code, 1)
        self.assertFalse(value['expectedRegressionFailure'])

    def test_finite_schema_rejects_unknown_private_fields_and_values(self):
        code, good, _ = self.child('green', 'pass')
        self.assertEqual(c.validate_summary(good, 'green', code, expected_count=1), good)
        bad_values = []
        for key, value in [('private', 'private path'), ('tests', True), ('tests', float('nan')),
                           ('status', 'private'), ('expectedRegressionFailure', 1)]:
            bad = copy.deepcopy(good); bad[key] = value; bad_values.append(bad)
        bad = copy.deepcopy(good); bad['tests'] = 2; bad_values.append(bad)
        for bad in bad_values:
            with self.subTest(keys=list(bad)):
                with self.assertRaises(c.request.p.GateError):
                    c.validate_summary(bad, 'green', 0, expected_count=1)
        with self.assertRaises(c.request.p.GateError):
            c.validate_summary(good, 'green', 1, expected_count=1)

    def test_finite_compile_diagnostics_allowlist(self):
        diagnostic = {'stage': 'compile', 'errors': [
            {'line': 123, 'column': 4, 'category': 'missing_property'},
        ], 'error_count': 1, 'truncated': False}
        for prefix in ('DARWIN_TEST_COMPILE_FAILURE (not causal red): ',
                       'DARWIN_TEST_COMPILE_FAILURE (iOS preprocessor isolation, not causal red): '):
            code, good, stderr = self.child('green', 'raise RuntimeError(' + repr(prefix + json.dumps(diagnostic)) + ')')
            self.assertEqual(code, 1)
            self.assertEqual(c.validate_summary(good, 'green', code, expected_count=1), good)
            self.assertEqual(good['failedTests'][0]['compile'], diagnostic)
            self.assertEqual(stderr, '')
            zero = copy.deepcopy(good)
            zero['failedTests'][0]['compile']['errors'][0].update(line=0, column=0)
            self.assertEqual(c.validate_summary(zero, 'green', code, expected_count=1), zero)
            for key, value in [('line', True), ('column', 1000001), ('category', 'private'),
                               ('path', '/private/source.m')]:
                bad = copy.deepcopy(good); bad['failedTests'][0]['compile']['errors'][0][key] = value
                with self.assertRaises(c.request.p.GateError):
                    c.validate_summary(bad, 'green', code, expected_count=1)
            bad = copy.deepcopy(good); bad['failedTests'][0]['compile']['truncated'] = True
            with self.assertRaises(c.request.p.GateError):
                c.validate_summary(bad, 'green', code, expected_count=1)

    def test_setup_compile_error_has_zero_test_ordinal(self):
        diagnostic = {'stage': 'compile', 'errors': [], 'error_count': 0, 'truncated': False}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            message = 'DARWIN_TEST_COMPILE_FAILURE (not causal red): ' + json.dumps(diagnostic)
            (root / 'synthetic_anchor.py').write_text(
                'import unittest\nclass Fixture(unittest.TestCase):\n'
                '    @classmethod\n    def setUpClass(cls):\n        raise RuntimeError(' + repr(message) + ')\n'
                '    def test_anchor(self):\n        pass\n')
            result = subprocess.run([sys.executable, '-B', '-c', c.CHILD, 'green', 'synthetic_anchor',
                                     'synthetic_anchor.Fixture.test_anchor', c.MARKER, '1'],
                                    cwd=root, capture_output=True, text=True)
            value = c.validate_summary(json.loads(result.stdout), 'green', result.returncode, expected_count=1)
            self.assertEqual(value['tests'], 0)
            self.assertEqual(value['failedTests'], [{'ordinal': 0, 'reason': 'compile_error', 'compile': diagnostic}])

    def test_child_env_and_parent_owned_temporary_output_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source = root / 'source'; source.mkdir()
            (source / 'synthetic_anchor.py').write_text(
                'import unittest, os, tempfile\nfrom pathlib import Path\n'
                'class Fixture(unittest.TestCase):\n    def test_anchor(self):\n'
                '        work = Path(tempfile.gettempdir())\n'
                '        self.assertEqual(work.parent, Path(__file__).resolve().parent.parent)\n'
                '        self.assertTrue(work.name.startswith(".darwin-anchor-work-"))\n'
                '        self.assertFalse(any(key in os.environ for key in '
                '("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STEP_SUMMARY")))\n'
                '        (work / "private-output").write_text("synthetic")\n')
            commands = {key: 'private-command-file' for key in
                        ('GITHUB_ENV', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY')}
            with patch.object(c.request.p, 'ROOT', root), patch.multiple(c, MODULE='synthetic_anchor',
                    TARGET='synthetic_anchor.Fixture.test_anchor', GREEN_COUNT=1), patch.dict(os.environ, commands):
                value = c.run_child(source, c.regression_env(), 'green')
            self.assertEqual(value['status'], 'passed')
            self.assertEqual(list(root.glob('.darwin-anchor-work-*')), [])

    def test_timeout_removes_parent_owned_outputs_and_kills_only_own_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); source = root / 'source'; source.mkdir()
            (source / 'synthetic_anchor.py').write_text('import time\ntime.sleep(30)\n')
            with patch.object(c.request.p, 'ROOT', root), patch.multiple(c, MODULE='synthetic_anchor',
                    TARGET='synthetic_anchor.Fixture.test_anchor', GREEN_COUNT=1), \
                    patch.object(c.os, 'killpg', wraps=os.killpg) as kill:
                with self.assertRaises(c.request.p.GateError):
                    c.run_child(source, c.regression_env(), 'green', timeout=0.1)
                kill.assert_called_once()
                self.assertGreater(kill.call_args.args[0], 0)
            self.assertEqual(list(root.glob('.darwin-anchor-work-*')), [])

    def test_intermediate_cleanup_preserves_manifest_final_cleanup_removes_only_owned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'source').mkdir()
            saved = root / c.MANIFEST; saved.write_text('{}')
            other = root / 'other'; other.write_text('preserved')
            with patch.object(c.request.p, 'ROOT', root):
                c.request.p.cleanup()
                self.assertTrue(saved.exists())
                c.final_cleanup()
                self.assertFalse(saved.exists())
                self.assertEqual(other.read_text(), 'preserved')
                saved.symlink_to(other)
                c.final_cleanup()
                self.assertFalse(saved.is_symlink())
                self.assertEqual(other.read_text(), 'preserved')

    def test_frozen_directory_digest_tracks_all_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = root / c.TEST_DIRECTORY; directory.mkdir(parents=True)
            file = directory / 'test_fixture.py'; file.write_text('first')
            first = c.test_manifest(root); file.write_text('second')
            self.assertNotEqual(first, c.test_manifest(root))
            (directory / 'linked.py').symlink_to(file)
            with self.assertRaises(c.request.p.GateError): c.test_manifest(root)

    def test_wrapper_restores_source_server_and_forbids_packages(self):
        original = (c.request.SOURCE_SHA, c.request.SERVER_SHA, c.request.REQUEST)
        def run():
            self.assertEqual(c.request.SOURCE_SHA, c.SOURCE_SHA)
            self.assertEqual(c.request.SERVER_SHA, c.SERVER_SHA)
            self.assertEqual(c.request.REQUEST, c.REQUEST)
            return 0
        with patch.object(sys, 'argv', ['wrapper', 'source', 'prepare']), patch.object(c.request, 'main', side_effect=run):
            self.assertEqual(c.main(), 0)
        self.assertEqual((c.request.SOURCE_SHA, c.request.SERVER_SHA, c.request.REQUEST), original)
        for args in [('source', 'publish'), ('source', 'build'), ('native', 'build'), ('bad', 'prepare')]:
            with patch.object(sys, 'argv', ['wrapper', *args]), patch.object(c.request, 'main') as run:
                self.assertEqual(c.main(), 1); run.assert_not_called()

    def test_workflow_is_bounded_and_does_not_build_native_apps(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows' / c.WORKFLOW).read_text()
        for value in (c.PARENT, c.MESSAGE, c.REQUEST_PATH, c.SOURCE_SHA, c.SOURCE_REF):
            self.assertIn(value, text)
        for value in ('upload-artifact', 'RELEASE_WRITE_TOKEN', 'DEFAULT_SERVER_URL', 'MAC_LAB_NETWORK_APPROVED'):
            self.assertNotIn(value, text)
        self.assertIn('needs: [prepare, native-anchor]', text)
        self.assertLess(text.index('regression red'), text.index('regression green'))
        native_job = text[text.index('  native-anchor:'):]
        self.assertNotIn('flutter-action', native_job)
        self.assertIn('if: always()', native_job)
        self.assertIn('regression cleanup', native_job)
        self.assertEqual(native_job.count('source cleanup'), 1)
        self.assertNotIn('PENDING_', text)


if __name__ == '__main__':
    unittest.main()
