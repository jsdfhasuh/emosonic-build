import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_native_closure as c


class NativeClosureTests(unittest.TestCase):
    def test_exact_request_and_workflow(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / c.REQUEST_PATH).read_text()), c.REQUEST)
        self.assertEqual(c.SOURCE_SHA, '01967c853a4e6020097e9a2da61f9785b470ff7d')
        workflow = (root / '.github/workflows' / c.WORKFLOW).read_text()
        self.assertIn(c.PARENT, workflow)
        self.assertIn(c.MESSAGE, workflow)
        self.assertLess(workflow.index(' native preflight'), workflow.index('subosito/flutter-action'))
        self.assertLess(workflow.index(' native attribution'), workflow.index(' native build'))
        self.assertIn('native handoff', workflow)
        self.assertIn('native follow', workflow)
        self.assertNotIn('upload-artifact', workflow)

    def test_forbidden_stages(self):
        for args in [('source', 'publish'), ('source', 'android'), ('source', 'validate_source'), ('native', 'unknown'), ('other', 'prepare')]:
            with patch.object(sys, 'argv', ['wrapper', *args]), patch.object(c.native, 'main') as run:
                self.assertEqual(c.main(), 1)
                run.assert_not_called()

    def test_prepare_pristine_before_instrumentation(self):
        calls = []
        with patch.object(sys, 'argv', ['wrapper', 'native', 'prepare']), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.request.p, 'source_fingerprint', side_effect=lambda *a: calls.append('fingerprint')), patch.object(c.native, 'native_env', return_value={}), patch.object(c.native, 'main', side_effect=lambda: calls.append('server-pin') or 0), patch.object(c, 'apply_observations', side_effect=lambda *a: calls.append('observations')):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['context', 'fingerprint', 'server-pin', 'observations'])

    def test_attribution_order(self):
        calls = []
        with patch.object(sys, 'argv', ['wrapper', 'native', 'attribution']), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.request.p, 'source_context', side_effect=lambda **a: calls.append('sdk')), patch.object(c.request.p, 'codegen', side_effect=lambda *a: calls.append('codegen')), patch.object(c.native, 'native_env', return_value={}), patch.object(c.native, 'execute', side_effect=lambda command, label, report: calls.append(command[2])):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['context', 'sdk', 'codegen', 'proof', 'native'])

    def test_native_build_and_matrix_require_readonly_proof(self):
        for stage in ('build', 'handoff', 'follow'):
            calls = []
            def execute(command, label, report):
                self.assertEqual(command[2], 'verify')
                self.assertEqual(command[-2:], ['--expected-lab-before-sha256', c.OBSERVED_HARNESS_SHA256])
                calls.append('verify')
            with patch.object(sys, 'argv', ['wrapper', 'native', stage]), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.native, 'execute', side_effect=execute), patch.object(c.native, 'main', side_effect=lambda: calls.append(stage) or 0):
                self.assertEqual(c.main(), 0)
            self.assertEqual(calls, ['context', 'verify', stage])

    def test_failed_proof_prevents_native_execution(self):
        with patch.object(sys, 'argv', ['wrapper', 'native', 'build']), patch.object(c, 'checked_native_context'), patch.object(c.native, 'execute', side_effect=ValueError('bad proof')), patch.object(c.native, 'main') as run:
            self.assertEqual(c.main(), 1)
            run.assert_not_called()
