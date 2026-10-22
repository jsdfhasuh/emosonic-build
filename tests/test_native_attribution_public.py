import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('public_attribution', ROOT / 'scripts/native_attribution/lab_stream_attribution.py')
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


class PublicAttributionTests(unittest.TestCase):
    def test_reviewed_payloads_and_script(self):
        self.assertEqual(a.digest(Path(a.__file__).read_bytes()), '63978c9cc9eec968c5ae24aa2f587ac33a2a1eff10e97a15571cb114cad06cd2')
        for name, expected in [('native_lab_scoped_api_client.dart', '853582b7c96254c3b8107e7633cb85eca08031dcfb70679d5315ca0731078a3d'), ('native_lab_scoped_attribution_test.dart', '6aa928bbf52683c0e47603079a105d4d1ba68748a1c4d2d554e6dc54a6182ad7')]:
            self.assertEqual(a.digest((a.ROOT / 'payload' / name).read_bytes()), expected)

    def test_exact_fixture_only(self):
        fixture = {'baseUrl': 'http://127.0.0.1:31337', 'tracks': [{'id': 'fixture-a'}]}
        value = json.loads(a.native_lab_stream_scope({'baseUrl': fixture['baseUrl'], 'password': 'never-copy-secret'}, fixture))
        self.assertEqual(value, {'streamUrl': 'http://127.0.0.1:31337/rest/stream', 'trackIds': ['fixture-a']})
        self.assertNotIn('secret', json.dumps(value))
        for url in ['https://example.com', 'http://localhost:31337', 'http://127.0.0.1:31337/other', 'http://u:p@127.0.0.1:31337', 'http://127.0.0.1:31337?token=x']:
            with self.assertRaises(ValueError):
                a.native_lab_stream_scope({'baseUrl': url}, dict(fixture, baseUrl=url))

    def test_exact_complete_six_test_gate(self):
        rows = []
        for i, name in enumerate(a.TEST_NAMES):
            rows.extend([{'type': 'testStart', 'test': {'id': i, 'name': name}}, {'type': 'testDone', 'testID': i, 'result': 'success', 'skipped': False, 'hidden': False}])
        rows.append({'type': 'done', 'success': True})
        self.assertEqual(a.completed_tests('\n'.join(map(json.dumps, rows))), 6)
        rows[0]['test']['name'] = 'unknown'
        with self.assertRaises(ValueError):
            a.completed_tests('\n'.join(map(json.dumps, rows)))

    def test_finite_failure_never_echoes_secrets(self):
        rows = [{'type': 'testStart', 'test': {'id': 2, 'name': a.TEST_NAMES[1]}}, {'type': 'error', 'testID': 2, 'isFailure': True, 'error': 'password=secret https://private/?token=secret', 'stackTrace': a.TEST + ':120:7 private secret'}]
        value = a.proof_failure_diagnostic('baseline', stdout='\n'.join(map(json.dumps, rows)), exit_code=1)
        self.assertEqual(value['diagnostic']['failedTestOrdinal'], 2)
        self.assertEqual(value['diagnostic']['sourceLine'], 120)
        self.assertNotIn('secret', json.dumps(value))
        self.assertNotIn('https', json.dumps(value))

    def test_native_and_verify_require_static_hash(self):
        for stage in ('native', 'verify'):
            with patch.object(sys, 'argv', ['helper', stage, '--repo', '/tmp/not-used']), self.assertRaises(SystemExit):
                a.main()
