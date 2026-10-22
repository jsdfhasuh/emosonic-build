import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_server_contract as proof


class ServerContractProofTests(unittest.TestCase):
    def child(self, stage, body):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('supysonic', 'tests', 'tests/base'):
                folder = root / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / '__init__.py').write_text('')
            (root / 'tests/base/test_emo_follow_store.py').write_text(
                'import unittest\nclass EmoFollowStoreTestCase(unittest.TestCase):\n'
                '    def test_accepted_nonunit_authority_rate_keeps_follow_source_active(self):\n'
                '        ' + body + '\n')
            result = subprocess.run([sys.executable, '-c', proof.CHILD, stage, proof.TARGET, proof.MARKER], cwd=root, capture_output=True, text=True)
            return result.returncode, json.loads(result.stdout), result.stderr

    def test_red_requires_exact_causal_failure(self):
        code, result, stderr = self.child('red', 'self.fail(' + repr(proof.MARKER) + ')')
        self.assertEqual(code, 0)
        self.assertTrue(result['expectedRegressionFailure'])
        self.assertEqual(result['failures'], 1)
        self.assertEqual(result['failedTestIds'], [proof.TARGET])
        self.assertEqual(stderr, '')

    def test_wrong_failure_and_unexpected_green_are_not_red_proof(self):
        for body in ('self.fail("unrelated private detail")', 'pass', 'raise RuntimeError("private setup")', 'self.skipTest("private reason")'):
            with self.subTest(body=body):
                code, result, stderr = self.child('red', body)
                self.assertEqual(code, 1)
                self.assertFalse(result['expectedRegressionFailure'])
                self.assertNotIn('private', json.dumps(result) + stderr)

    def test_green_and_follow_require_real_tests_without_skips(self):
        for stage in ('green', 'follow'):
            for body, expected in [('pass', 0), ('self.skipTest("private")', 1), ('self.fail("private")', 1)]:
                with self.subTest(stage=stage, body=body):
                    code, result, stderr = self.child(stage, body)
                    self.assertEqual(code, expected)
                    self.assertEqual(result['tests'], 1)
                    self.assertNotIn('private', json.dumps(result) + stderr)

    def test_full_suite_retains_explicit_optional_skip_count(self):
        code, result, stderr = self.child('full', 'self.skipTest("private")')
        self.assertEqual(code, 0)
        self.assertEqual(result['skipped'], 1)
        self.assertNotIn('private', json.dumps(result) + stderr)

    def test_exact_transition_and_request_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sha = 'a' * 40
            (root / 'requests').mkdir()
            (root / proof.REQUEST_PATH).write_text(json.dumps(proof.REQUEST))
            event = {'before': proof.PARENT, 'after': sha, 'forced': False, 'deleted': False, 'created': False, 'head_commit': {'id': sha, 'message': proof.MESSAGE}}
            file = root / 'event.json'; file.write_text(json.dumps(event))
            env = {'GITHUB_EVENT_PATH': str(file), 'GITHUB_SHA': sha, 'GITHUB_REPOSITORY': 'jsdfhasuh/emosonic-build', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_WORKFLOW_REF': 'jsdfhasuh/emosonic-build/.github/workflows/follow-server-contract.yml@refs/heads/main'}
            with patch.object(proof, 'ROOT', root), patch.object(proof, 'FIXED_SHA', 'b' * 40), patch.dict(os.environ, env, clear=True):
                proof.context()
                for key, value in [('before', 'c' * 40), ('forced', True), ('created', True)]:
                    changed = dict(event, **{key: value}); file.write_text(json.dumps(changed))
                    with self.assertRaises(AssertionError): proof.context()

    def test_workflow_has_no_private_credentials_or_release(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/follow-server-contract.yml').read_text()
        for word in ('secrets.', 'environment:', 'upload-artifact', 'publish', 'release:'):
            self.assertNotIn(word, workflow)
        for value in (proof.PARENT, proof.MESSAGE, proof.BASELINE_SHA, proof.FIXED_SHA):
            self.assertIn(value, workflow)
        self.assertLess(workflow.index('contract.py red'), workflow.index('contract.py green'))


if __name__ == '__main__':
    unittest.main()
