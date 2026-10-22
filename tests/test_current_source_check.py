import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_source_check as c


class CurrentSourceCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'requests').mkdir()
        (self.root / c.REQUEST_PATH).write_text(json.dumps(c.REQUEST))
        self.sha = 'a' * 40
        self.event = {'before': c.PARENT, 'after': self.sha, 'ref': 'refs/heads/main',
                      'forced': False, 'deleted': False, 'created': False,
                      'head_commit': {'id': self.sha, 'message': c.MESSAGE}}
        self.path = self.root / 'event.json'
        self.path.write_text(json.dumps(self.event))
        self.env = {'GITHUB_REPOSITORY': c.p.BUILDER, 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_EVENT_NAME': 'push', 'GITHUB_WORKFLOW_REF': c.p.BUILDER + '/.github/workflows/current-source-check.yml@refs/heads/main',
                    'GITHUB_SHA': self.sha, 'GITHUB_RUN_ID': '1', 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_EVENT_PATH': str(self.path), 'SOURCE_SHA': c.SOURCE_SHA, 'BUILD_VERSION': c.VERSION}
        self.patches = [patch.dict(os.environ, self.env, clear=True), patch.object(c.p, 'ROOT', self.root)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_exact_transition(self):
        c.context()

    def test_wrong_environment_rejected(self):
        for key, value in [('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/other'),
                           ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('SOURCE_SHA', 'b' * 40),
                           ('BUILD_VERSION', '1.0.11+28'), ('SOURCE_REF', 'refs/heads/arbitrary'), ('RELEASE_MODE', 'publish-stable'),
                           ('RELEASE_WRITE_TOKEN', 'not-a-real-token'), ('GITHUB_WORKFLOW_REF', 'other'),
                           ('GITHUB_RUN_ID', '0'), ('GITHUB_SHA', 'invalid')]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(c.p.GateError):
                    c.context()

    def test_other_push_rejected(self):
        for key, value in [('before', 'b' * 40), ('after', 'b' * 40), ('forced', True),
                           ('created', True), ('deleted', True), ('ref', 'refs/heads/other')]:
            with self.subTest(key=key):
                data = copy.deepcopy(self.event); data[key] = value
                self.path.write_text(json.dumps(data))
                with self.assertRaises(c.p.GateError):
                    c.context()
        self.path.write_text(json.dumps(self.event))

    def test_wrong_message_rejected(self):
        self.event['head_commit']['message'] = 'unrelated'
        self.path.write_text(json.dumps(self.event))
        with self.assertRaises(c.p.GateError):
            c.context()

    def test_wrong_request_rejected(self):
        (self.root / c.REQUEST_PATH).write_text('{}')
        with self.assertRaises(c.p.GateError):
            c.context()

    def test_no_publishing_stage(self):
        with patch.object(c.p, 'publish') as publish:
            with self.assertRaises(c.p.GateError):
                c.run('publish')
            publish.assert_not_called()

    def test_reuses_only_allowed_stages(self):
        for stage in c.STAGES:
            if stage == 'prepare':
                continue
            with self.subTest(stage=stage), patch.object(c.p, stage) as operation:
                c.run(stage)
                operation.assert_called_once_with()

    def test_prepare_same_version_without_release_write(self):
        response = {'ref': c.SOURCE_REF, 'object': {'type': 'commit', 'sha': c.SOURCE_SHA}}
        with patch.dict(os.environ, {'SOURCE_READ_TOKEN': 'test-only'}), patch.object(c.p, 'api', return_value=response) as api, patch.object(c.p, 'remote_source_version', return_value=c.VERSION), patch.object(c.p, 'output') as output, patch.object(c.p, 'monotonic') as monotonic:
            c.prepare()
            api.assert_called_once_with('/repos/jsdfhasuh/emosonic/git/ref/' + c.SOURCE_REF.removeprefix('refs/'), 'test-only')
            monotonic.assert_not_called()
            self.assertEqual(output.call_count, 4)

    def test_moved_master_rejected(self):
        response = {'ref': c.SOURCE_REF, 'object': {'type': 'commit', 'sha': 'b' * 40}}
        with patch.dict(os.environ, {'SOURCE_READ_TOKEN': 'test-only'}), patch.object(c.p, 'api', return_value=response), patch.object(c.p, 'output') as output:
            with self.assertRaises(c.p.GateError):
                c.prepare()
            output.assert_not_called()

    def test_candidate_metadata_names_actual_branch_without_publishing(self):
        value = c.candidate_metadata(c.VERSION, c.SOURCE_SHA, 'a' * 64)
        self.assertEqual(value['source_ref'], c.SOURCE_REF)
        self.assertTrue(value['prerelease'])
        self.assertFalse(value['published'])
        self.assertEqual(value['mode'], 'build-only')

    def test_stable_gate_still_rejects_published_version(self):
        with self.assertRaises(c.p.GateError):
            c.p.monotonic(c.VERSION, ['v' + c.VERSION])

    def test_workflow_has_no_publish_or_release_credentials(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/current-source-check.yml'
        content = path.read_text()
        for forbidden in ('publish-stable', 'RELEASE_WRITE_TOKEN', 'environment: android-release', 'pipeline.py publish', 'pull_request_target'):
            self.assertNotIn(forbidden, content)
        self.assertIn('needs: [prepare, validate-source]', content)
        self.assertIn('requests/current-source-20261022.json', content)


if __name__ == '__main__':
    unittest.main()
