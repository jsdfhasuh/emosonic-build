import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_recovery_check as c


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name).resolve()
        (self.source / 'test/services').mkdir(parents=True)
        self.suites = []
        for index in range(3):
            name = f'test/services/synthetic_{index}_test.dart'
            data = f'private fixture {index}'.encode()
            (self.source / name).write_bytes(data)
            self.suites.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest(),
                                    names=[f'private synthetic test {index}']))
        self.write_inventory()

    def write_inventory(self, value=None):
        raw = json.dumps({'suites': self.suites} if value is None else value).encode()
        (self.source / 'inventory.json').write_bytes(raw)
        self.addCleanup(patch.stopall)
        patch.object(c, 'INVENTORY_PATH', 'inventory.json').start()
        patch.object(c, 'INVENTORY_SHA256', hashlib.sha256(raw).hexdigest()).start()

    def test_exact_inventory(self):
        self.assertEqual(c.inventory(self.source), self.suites)

    def test_inventory_hash_and_fixture_hash_tampering(self):
        (self.source / 'inventory.json').write_text('private changed')
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
        self.write_inventory()
        (self.source / self.suites[0]['path']).write_text('private mutation')
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def test_inventory_schema_names_duplicates_and_paths(self):
        for key, value in (('path', '../outside_test.dart'), ('path', '/outside_test.dart'),
                           ('names', []), ('names', ['same', 'same']), ('names', [True])):
            with self.subTest(key=key, value=value):
                old = self.suites[0][key]
                self.suites[0][key] = value
                self.write_inventory()
                with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
                self.suites[0][key] = old
        self.write_inventory({'suites': self.suites, 'secret': 'must not echo'})
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def test_inventory_and_fixture_leaf_symlinks(self):
        inventory = self.source / 'inventory.json'
        inventory.rename(self.source / 'actual.json')
        inventory.symlink_to(self.source / 'actual.json')
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
        inventory.unlink()
        (self.source / 'actual.json').rename(inventory)
        fixture = self.source / self.suites[0]['path']
        fixture.rename(self.source / 'real.dart')
        fixture.symlink_to(self.source / 'real.dart')
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def test_fixture_ancestor_symlink_refused_even_inside_source(self):
        directory = self.source / 'test/services'
        directory.rename(self.source / 'actual-services')
        directory.symlink_to(self.source / 'actual-services', target_is_directory=True)
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def test_inventory_ancestor_symlink_refused_even_inside_source(self):
        (self.source / 'real').mkdir()
        (self.source / 'inventory.json').rename(self.source / 'real/inventory.json')
        (self.source / 'alias').symlink_to(self.source / 'real', target_is_directory=True)
        with patch.object(c, 'INVENTORY_PATH', 'alias/inventory.json'):
            with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def focused_patches(self, stack, result=None, error=None, fingerprints=None):
        stack.enter_context(patch.object(c.request, 'context'))
        stack.enter_context(patch.object(c.request.p, 'source_context', return_value=(self.source, None, 'a'*40, None)))
        stack.enter_context(patch.object(c.regression.native, 'native_env', return_value={}))
        fingerprint = stack.enter_context(patch.object(c.request.p, 'source_fingerprint', side_effect=fingerprints or ['same', 'same']))
        codegen = stack.enter_context(patch.object(c.request.p, 'codegen'))
        command = stack.enter_context(patch.object(c.subprocess, 'run', return_value=result, side_effect=error))
        return fingerprint, codegen, command

    def test_timeout_checks_final_fingerprint_and_never_echoes_partial_output(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, command = self.focused_patches(stack, error=subprocess.TimeoutExpired('private command', 600, output='private log'))
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(command.call_count, 1)
            report = json.loads(output.getvalue())
            self.assertEqual(report['category'], 'TimeoutExpired')
            self.assertEqual(report['failedStage'], 'focused-test')
            self.assertNotIn('private', output.getvalue())

    def test_bad_green_is_finite_and_stops_before_next_suite(self):
        result = subprocess.CompletedProcess([], 1, 'private non JSON', 'private stderr')
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, command = self.focused_patches(stack, result=result)
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(command.call_count, 1)
            self.assertNotIn('private', output.getvalue())
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]['suiteOrdinal'], 1)
            self.assertEqual(reports[-1]['category'], 'GreenVerificationError')

    def test_final_fingerprint_detects_mutation_even_on_timeout(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.focused_patches(stack, error=subprocess.TimeoutExpired('private command', 600), fingerprints=['before', 'after'])
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(json.loads(output.getvalue())['failedStage'], 'final-fingerprint')

    def test_codegen_failure_still_checks_fingerprint_and_never_runs_flutter(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, codegen, command = self.focused_patches(stack)
            def failing_codegen(source, env):
                c.request.p.quiet(['flutter', 'pub', 'get'], cwd=source, env=env)
            codegen.side_effect = failing_codegen
            stack.enter_context(patch.object(c.request.p, 'quiet', side_effect=c.request.p.GateError('private setup detail')))
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(fingerprint.call_count, 2)
            command.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())['failedStage'], 'dependencies')
            self.assertNotIn('private', output.getvalue())

    def test_three_suites_use_pinned_names_and_bounded_commands(self):
        result = subprocess.CompletedProcess([], 0, 'private JSON', '')
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, command = self.focused_patches(stack, result=result)
            verifier = stack.enter_context(patch.object(c, 'verify_green', return_value={'stage': 'fixed-flutter-green', 'status': 'passed'}))
            c.focused()
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(command.call_count, 3)
            for index, call in enumerate(command.call_args_list):
                self.assertEqual(call.args[0], ['flutter', 'test', '--no-pub', '--reporter=json', self.suites[index]['path']])
                self.assertEqual(call.kwargs['timeout'], 600)
                self.assertEqual(call.kwargs['cwd'], self.source)
                self.assertEqual(verifier.call_args_list[index].kwargs['expected_names'], self.suites[index]['names'])
            self.assertNotIn('private', output.getvalue())

    def test_forbidden_stage_never_delegates(self):
        for category, stage in (('native', 'follow'), ('source', 'publish'), ('source', 'build_android'), ('regression', 'focused')):
            with self.subTest(stage=stage), patch.object(sys, 'argv', ['check', category, stage]), patch.object(c.request, 'main') as base, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(), 1)
                base.assert_not_called()


if __name__ == '__main__': unittest.main()
