import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_follow_ingress_proof import fixture, raw, NAMES, BASE
import follow_clock_proof as c


class ClockProofTests(unittest.TestCase):
    def fixture_tree(self, root):
        path = 'test/services/synthetic_clock_test.dart'
        target = root / path
        target.parent.mkdir(parents=True)
        target.write_text('synthetic private fixture')
        suite = dict(path=path, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                     names=NAMES, causalOrdinal=1)
        inv = root / c.INVENTORY_PATH
        inv.parent.mkdir(parents=True)
        inv.write_text(json.dumps(dict(suites=[suite])))
        return suite, hashlib.sha256(inv.read_bytes()).hexdigest()

    def test_complete_frozen_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            suite, digest = self.fixture_tree(root)
            with patch.multiple(c, EXPECTED_COUNT=3, INVENTORY_SHA256=digest):
                self.assertEqual(c.inventory(root), suite)
                (root / suite['path']).write_text('changed')
                with self.assertRaises(c.request.p.GateError):
                    c.inventory(root)

    def test_missing_ordinal_wrong_count_and_unknown_keys_fail_before_execution(self):
        for change in ('ordinal', 'count', 'extra'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                suite, _ = self.fixture_tree(root)
                if change == 'ordinal':
                    del suite['causalOrdinal']
                elif change == 'count':
                    suite['names'] = NAMES[:2]
                else:
                    suite['private_extra'] = 'do not export'
                inv = root / c.INVENTORY_PATH
                inv.write_text(json.dumps(dict(suites=[suite])))
                digest = hashlib.sha256(inv.read_bytes()).hexdigest()
                with patch.multiple(c, EXPECTED_COUNT=3, INVENTORY_SHA256=digest):
                    with self.assertRaises(c.request.p.GateError):
                        c.inventory(root)

    def test_proof_keeps_full_report_and_fingerprint_on_wrong_causal_error(self):
        from types import SimpleNamespace
        suite = dict(path='test/services/' + BASE, names=NAMES, causalOrdinal=1)
        result = SimpleNamespace(stdout=raw(fixture()), stderr='', returncode=1)
        with patch.object(c.request.p, 'source_context', return_value=(Path('/synthetic'), None, 'a' * 40, None)), \
             patch.object(c.request.p, 'source_fingerprint', return_value='unchanged') as fingerprint, \
             patch.object(c, 'inventory', return_value=suite), \
             patch.object(c, 'native_env', return_value={}), \
             patch.object(c.request.p, 'codegen'), \
             patch.object(c, 'bounded_run', return_value=(result, None)), \
             patch.object(c, 'EXPECTED_COUNT', 3), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(c.GreenVerificationError):
                c.prove()
        self.assertEqual(fingerprint.call_count, 2)
        observation = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(observation['visibleTests'], 3)
        self.assertNotIn('PRIVATE_URI_TOKEN_SOURCE_DO_NOT_EXPORT', output.getvalue())


if __name__ == '__main__':
    unittest.main()
