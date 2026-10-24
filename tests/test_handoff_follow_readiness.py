import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_follow_readiness as c


class FollowReadinessOrchestrationTests(unittest.TestCase):
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
        with patch.object(sys, 'argv', ['wrapper', 'native', 'prepare']), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.request.p, 'source_fingerprint', side_effect=lambda *a: calls.append('fingerprint')), patch.object(c.native, 'native_env', return_value={}), patch.object(c.native, 'main', side_effect=lambda: calls.append('server-pin') or 0), patch.object(c, 'apply_observations', side_effect=lambda *a: calls.append('observations')), patch.object(c.readiness, 'apply', side_effect=lambda *a: calls.append('readiness')), patch.object(c.native, 'execute', side_effect=lambda *a: calls.append('red-green')):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['context', 'fingerprint', 'server-pin', 'observations', 'readiness', 'red-green'])

    def test_native_unit_requires_prepared_fixture_integrity(self):
        calls = []
        with patch.object(sys, 'argv', ['wrapper', 'native', 'unit']), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.readiness, 'verify_prepared', side_effect=lambda *a: calls.append('prepared')), patch.object(c.native, 'main', side_effect=lambda: calls.append('unit') or 0), patch.object(c.native, 'execute') as attribution:
            self.assertEqual(c.main(), 0)
            attribution.assert_not_called()
        self.assertEqual(calls, ['context', 'prepared', 'unit'])

    def test_changed_fixture_prevents_unit_execution(self):
        with patch.object(sys, 'argv', ['wrapper', 'native', 'unit']), patch.object(c, 'checked_native_context'), patch.object(c.readiness, 'verify_prepared', side_effect=ValueError('wrong fixture')), patch.object(c.native, 'main') as run:
            self.assertEqual(c.main(), 1)
            run.assert_not_called()

    def test_attribution_order(self):
        calls = []
        with patch.object(sys, 'argv', ['wrapper', 'native', 'attribution']), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.readiness, 'verify_prepared', side_effect=lambda *a: calls.append('prepared')), patch.object(c.request.p, 'source_context', side_effect=lambda **a: calls.append('sdk')), patch.object(c.request.p, 'codegen', side_effect=lambda *a: calls.append('codegen')), patch.object(c.native, 'native_env', return_value={}), patch.object(c.native, 'execute', side_effect=lambda command, label, report: calls.append(command[2])):
            self.assertEqual(c.main(), 0)
        self.assertEqual(calls, ['context', 'prepared', 'sdk', 'codegen', 'proof', 'native'])

    def test_native_build_and_matrix_require_readonly_proof(self):
        for stage in ('build', 'handoff', 'follow'):
            calls = []
            def execute(command, label, report):
                self.assertEqual(command[2], 'verify')
                self.assertEqual(command[-2:], ['--expected-lab-before-sha256', c.OBSERVED_HARNESS_SHA256])
                calls.append('verify')
            with patch.object(sys, 'argv', ['wrapper', 'native', stage]), patch.object(c, 'checked_native_context', side_effect=lambda: calls.append('context')), patch.object(c.readiness, 'verify_prepared', side_effect=lambda *a: calls.append('prepared')), patch.object(c.readiness, 'verify_compiled', side_effect=lambda *a: calls.append('compiled')), patch.object(c.native, 'execute', side_effect=execute), patch.object(c.native, 'main', side_effect=lambda: calls.append(stage) or 0):
                self.assertEqual(c.main(), 0)
            self.assertEqual(calls, ['context', 'prepared', 'verify', stage, 'compiled'] if stage == 'build' else ['context', 'prepared', 'compiled', 'verify', stage])

    def test_failed_proof_prevents_native_execution(self):
        with patch.object(sys, 'argv', ['wrapper', 'native', 'build']), patch.object(c, 'checked_native_context'), patch.object(c.readiness, 'verify_prepared'), patch.object(c.native, 'execute', side_effect=ValueError('bad proof')), patch.object(c.native, 'main') as run:
            self.assertEqual(c.main(), 1)
            run.assert_not_called()

    def test_bad_getter_integrity_blocks_measurement(self):
        for stage in ('handoff', 'follow'):
            with patch.object(sys, 'argv', ['wrapper', 'native', stage]), patch.object(c, 'checked_native_context'), patch.object(c.readiness, 'verify_prepared'), patch.object(c.readiness, 'verify_compiled', side_effect=ValueError('wrong getter')), patch.object(c.native, 'main') as run:
                self.assertEqual(c.main(), 1)
                run.assert_not_called()

    def test_pending_native_signals_are_typed_and_finite(self):
        raw = {'stage': 'native-follow-aligned', 'status': 'passed',
               'correctionReadinessPollCount': 3, 'correctionReadinessElapsedMs': 600.5,
               'rateMeasurement': {'correctionReadinessPollCount': 3, 'correctionReadinessElapsedMs': 600.5,
                   'alignmentFollowerNative': {'seekInProgress': True, 'playingIntent': True, 'privateSecret': 'forbidden'}},
               'privateSecret': 'forbidden'}
        safe = c.native.report_line(json.dumps(raw))
        self.assertEqual(safe['correctionReadinessPollCount'], 3)
        self.assertEqual(safe['rateMeasurement']['alignmentFollowerNative'], {'seekInProgress': True, 'playingIntent': True})
        self.assertNotIn('forbidden', json.dumps(safe))
        raw['correctionReadinessPollCount'] = 52
        raw['correctionReadinessElapsedMs'] = float('nan')
        raw['rateMeasurement']['alignmentFollowerNative'] = {'seekInProgress': 'yes', 'playingIntent': 1}
        safe = c.native.report_line(json.dumps(raw))
        self.assertNotIn('correctionReadinessPollCount', safe)
        self.assertNotIn('correctionReadinessElapsedMs', safe)
        self.assertNotIn('alignmentFollowerNative', safe['rateMeasurement'])
