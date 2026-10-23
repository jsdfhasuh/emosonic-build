"""Lossless serialization of already-sanitized native observations."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_check as native


class CompactNativeExportTests(unittest.TestCase):
    def execute_record(self, record, code=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'source').mkdir()
            stream = io.StringIO()
            def run(command, **kwargs):
                self.assertEqual(command, ['synthetic-command'])
                kwargs['stdout'].write((json.dumps(record) + '\nPRIVATE RAW LINE\n').encode())
                return SimpleNamespace(returncode=code)
            with patch.object(native.p, 'ROOT', root), patch.object(native, 'native_env', return_value={}), \
                    patch.object(native.subprocess, 'run', side_effect=run), contextlib.redirect_stdout(stream):
                if code:
                    with self.assertRaises(native.p.GateError):
                        native.execute(['synthetic-command'], 'follow', report=True)
                else:
                    native.execute(['synthetic-command'], 'follow', report=True)
            return stream.getvalue().splitlines()

    def test_actual_export_is_lossless_ordered_and_still_private(self):
        record = {'stage': 'follower-avplayer-rate-1.5', 'status': 'passed',
            'positionMs': 1.25, 'nativePlayback': [
                {'clientOrdinal': 2, 'trackMatchesFirstClient': False},
                {'clientOrdinal': 0, 'trackMatchesFirstClient': True}],
            'privateRaw': 'SECRET'}
        expected = native.report_line(json.dumps(record))
        lines = self.execute_record(record)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], json.dumps(expected, separators=(',', ':'), allow_nan=False))
        self.assertEqual(json.loads(lines[0]), expected)
        self.assertEqual(list(json.loads(lines[0])), list(expected))
        self.assertEqual([v['clientOrdinal'] for v in json.loads(lines[0])['nativePlayback']], [2, 0])
        self.assertEqual(json.loads(lines[1]), {'stage': 'follow', 'status': 'passed', 'exitCode': 0})
        self.assertNotIn('SECRET', '\n'.join(lines)); self.assertNotIn('PRIVATE', '\n'.join(lines))

    def test_nonfinite_fields_are_filtered_before_serialization(self):
        lines = self.execute_record({'stage': 'build-authority', 'status': 'passed',
            'positionMs': float('nan'), 'driftMs': float('inf')})
        self.assertEqual(json.loads(lines[0]), {'stage': 'build-authority', 'status': 'passed'})
        self.assertNotIn('NaN', lines[0]); self.assertNotIn('Infinity', lines[0])

    def test_failed_command_preserves_diagnostic_then_failure_and_raises(self):
        lines = self.execute_record({'stage': 'follower-avplayer-rate-1.5',
            'status': 'failed', 'errorType': 'TimeoutError'}, code=1)
        self.assertEqual(json.loads(lines[0])['status'], 'failed')
        self.assertEqual(json.loads(lines[1]), {'stage': 'follow', 'status': 'failed', 'exitCode': 1})


if __name__ == '__main__':
    unittest.main()
