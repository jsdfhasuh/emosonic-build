import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_follow_lifecycle as c


class FocusedFollowOrchestrationTests(unittest.TestCase):
    def test_exact_request_workflow_and_fixed_scope(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / c.REQUEST_PATH).read_text()), c.REQUEST)
        self.assertEqual(c.SOURCE_SHA, '01967c853a4e6020097e9a2da61f9785b470ff7d')
        workflow = (root / '.github/workflows' / c.WORKFLOW).read_text()
        for value in (c.PARENT, c.MESSAGE, c.REQUEST_PATH, 'github.event.forced == false'):
            self.assertIn(value, workflow)
        self.assertIn(' native follow', workflow)
        self.assertNotIn(' native handoff', workflow)
        self.assertNotIn('upload-artifact', workflow)
        self.assertLess(workflow.index(' native preflight'), workflow.index('subosito/flutter-action'))
        self.assertIn("steps.native-cleanup.outcome == 'success'", workflow)

    def test_forbidden_stages(self):
        for args in [('source', 'publish'), ('source', 'android'), ('source', 'validate_source'), ('native', 'handoff'), ('native', 'unknown'), ('other', 'prepare')]:
            with patch.object(sys, 'argv', ['wrapper', *args]), patch.object(c.base, 'main') as run:
                self.assertEqual(c.main(), 1)
                run.assert_not_called()

    def test_existing_proofs_finish_before_observation_apply(self):
        calls = []
        with patch.object(sys, 'argv', ['wrapper', 'native', 'prepare']), patch.object(c.base, 'main', side_effect=lambda: calls.append('existing-proof') or 0), patch.object(c.lifecycle, 'apply', side_effect=lambda *a: calls.append('observation-apply')):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['existing-proof', 'observation-apply'])

    def test_failed_existing_proof_prevents_observation(self):
        with patch.object(sys, 'argv', ['wrapper', 'native', 'prepare']), patch.object(c.base, 'main', return_value=1), patch.object(c.lifecycle, 'apply') as apply:
            self.assertEqual(c.main(), 1)
            apply.assert_not_called()

    def test_integrity_before_native_operations(self):
        for stage in ('unit', 'attribution', 'build', 'follow'):
            calls = []
            def verify(repo, *, require_harness):
                calls.append(('verify', require_harness))
            with patch.object(sys, 'argv', ['wrapper', 'native', stage]), patch.object(c.lifecycle, 'verify_prepared', side_effect=verify), patch.object(c.base, 'main', side_effect=lambda: calls.append('native') or 0):
                self.assertEqual(c.main(), 0)
            self.assertEqual(calls, [('verify', stage in ('unit', 'attribution')), 'native'])

    def test_changed_observation_prevents_execution(self):
        with patch.object(sys, 'argv', ['wrapper', 'native', 'follow']), patch.object(c.lifecycle, 'verify_prepared', side_effect=ValueError('private details')), patch.object(c.base, 'main') as run:
            self.assertEqual(c.main(), 1)
            run.assert_not_called()

    def test_owned_cleanup_does_not_depend_on_proof(self):
        for category in ('native', 'source'):
            with patch.object(sys, 'argv', ['wrapper', category, 'cleanup']), patch.object(c.lifecycle, 'verify_prepared') as verify, patch.object(c.base, 'main', return_value=0):
                self.assertEqual(c.main(), 0)
                verify.assert_not_called()

    def test_bounded_constants_reach_existing_context_then_restore(self):
        original = c.base.PARENT
        def run():
            self.assertEqual(c.base.PARENT, c.PARENT)
            self.assertEqual(c.base.REQUEST, c.REQUEST)
            self.assertEqual(c.base.WORKFLOW, c.WORKFLOW)
            self.assertEqual(c.base.OBSERVED_HARNESS_SHA256, c.lifecycle.AFTER_HARNESS_SHA256)
            self.assertEqual(c.base.ATTRIBUTION_EXTRA_ARGS, ('--lab-debug-observation',))
            return 0
        with patch.object(sys, 'argv', ['wrapper', 'source', 'prepare']), patch.object(c.base, 'main', side_effect=run):
            self.assertEqual(c.main(), 0)
        self.assertEqual(c.base.PARENT, original)
        self.assertEqual(c.base.ATTRIBUTION_EXTRA_ARGS, ())
