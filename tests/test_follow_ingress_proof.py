import contextlib
import copy
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
import follow_ingress_proof as c

NAMES = ['synthetic causal case', 'synthetic control one', 'synthetic control two']
BASE = 'synthetic_ingress_test.dart'
SECRET = 'PRIVATE_URI_TOKEN_SOURCE_DO_NOT_EXPORT'


def evidence(ordinal):
    dispatch = dict(phase='B_released', targetMs=10150, nativeBeforeMs=11000, completed=True)
    return dict(change=c.EVIDENCE_CHANGES[ordinal - 1], bSampleElapsedMs=100, cSampleElapsedMs=200,
                bPositionMs=10150, cPositionMs=10300, pendingTargetMs=10150, bSequence=2, cSequence=3,
                metadataRequests=2, backwardCount=1 if ordinal == 1 else 0,
                whileHeld=[dict(dispatch)] if ordinal == 1 else [], nativeSeeks=[dict(dispatch)])


def fixture():
    events = [{'type': 'start'}, {'type': 'suite'}]
    for tid, name in enumerate(NAMES + ['synthetic lifecycle']):
        events.append({'type': 'testStart', 'test': {'id': tid, 'name': name}})
        events.append({'type': 'print', 'testID': tid, 'message': SECRET})
        if tid < 3:
            events.append(dict(type='print', testID=tid, message=c.EVIDENCE_PREFIX + json.dumps(evidence(tid + 1))))
        if tid == 0:
            events.append({'type': 'error', 'testID': tid, 'isFailure': True,
                           'error': c.ASSERTION_MARKER, 'stackTrace': f'{SECRET}/{BASE}:17:3 {SECRET}'})
        events.append({'type': 'testDone', 'testID': tid, 'result': 'failure' if tid == 0 else 'success',
                       'hidden': tid == 3, 'skipped': False})
    return events + [{'type': 'done', 'success': False}]


def raw(events):
    return '\n'.join(json.dumps(event) for event in events)


class RedTests(unittest.TestCase):
    def verify(self, events=None, **kw):
        return c.exact_red(raw(fixture() if events is None else events), kw.pop('returncode', 1),
                           names=kw.pop('names', NAMES), basename=BASE,
                           causal_ordinal=kw.pop('causal_ordinal', 1), **kw)

    def refused(self, events, reason=None, **kw):
        with self.assertRaises(c.GreenVerificationError) as raised:
            self.verify(events, **kw)
        if reason:
            self.assertEqual(raised.exception.report['reason'], reason)
        self.assertNotIn(SECRET, json.dumps(raised.exception.report))
        for name in NAMES:
            self.assertNotIn(name, json.dumps(raised.exception.report))
        return raised.exception.report

    def test_exact_red_two_controls_and_all_hidden_success(self):
        self.assertEqual(self.verify(), dict(stage='follow-ingress-red', status='expected-failure-confirmed',
            visibleTests=3, hiddenTests=1, completedTests=4, causalOrdinal=1,
            expectedFailures=1, passedControls=2, unexpectedFailures=0))

    def test_causal_ordinal_comes_from_pinned_inventory(self):
        self.assertEqual(self.verify(names=[NAMES[1], NAMES[0], NAMES[2]], causal_ordinal=2)['causalOrdinal'], 2)
        self.refused(fixture(), 'causal-error-mismatch', causal_ordinal=2)

    def test_missing_extra_duplicate_visible_names(self):
        events = fixture()
        events = [e for e in events if e.get('testID') != 2 and not (e.get('type') == 'testStart' and e['test']['id'] == 2)]
        self.refused(events, 'inventory-mismatch')
        for name in ['unexpected synthetic', NAMES[1]]:
            events = fixture()
            events.insert(-1, dict(type='testStart', test=dict(id=50, name=name)))
            events.insert(-1, dict(type='testDone', testID=50, result='success', hidden=False, skipped=False))
            self.refused(events)

    def test_multiple_errors_even_if_later_test_is_success(self):
        for tid in [0, 1, 3, 99]:
            events = fixture()
            events.insert(-1, dict(type='error', testID=tid, isFailure=False, error=SECRET))
            self.refused(events, 'expected-single-error')

    def test_zero_errors_wrong_marker_setup_error_and_wrong_target(self):
        self.refused([e for e in fixture() if e['type'] != 'error'], 'expected-single-error')
        for field, value in [('error', c.ASSERTION_MARKER + '\n' + SECRET), ('error', 'StateError: ' + c.ASSERTION_MARKER),
                             ('error', 'TestFailure: ' + c.ASSERTION_MARKER), ('error', SECRET),
                             ('isFailure', False), ('isFailure', 1), ('testID', 1), ('testID', True), ('testID', 99)]:
            events = fixture()
            next(e for e in events if e['type'] == 'error')[field] = value
            self.refused(events, 'causal-error-mismatch')

    def test_causal_error_must_be_inside_target_lifecycle(self):
        for position in [0, -1]:
            events = fixture()
            error = next(e for e in events if e['type'] == 'error')
            events.remove(error)
            events.insert(position, error)
            self.refused(events, 'causal-completion-mismatch')

    def test_noncausal_control_failures_and_hidden_errors_rejected(self):
        for tid in [1, 2, 3]:
            for result in ['failure', 'error', 'unknown']:
                events = fixture()
                next(e for e in events if e['type'] == 'testDone' and e['testID'] == tid)['result'] = result
                self.refused(events, 'test-not-successful')

    def test_skip_hidden_flags_and_causal_completion(self):
        for tid in range(4):
            for key, value in [('skipped', True), ('skipped', 0), ('hidden', 1)]:
                events = fixture()
                next(e for e in events if e['type'] == 'testDone' and e['testID'] == tid)[key] = value
                self.refused(events)
        for key, value in [('result', 'success'), ('result', 'error'), ('hidden', True)]:
            events = fixture()
            next(e for e in events if e['type'] == 'testDone' and e['testID'] == 0)[key] = value
            self.refused(events, 'causal-completion-mismatch')
        events = fixture()
        next(e for e in events if e['type'] == 'testDone' and e['testID'] == 2)['hidden'] = True
        self.refused(events, 'expected-test-hidden')

    def test_missing_or_duplicate_lifecycle_and_incomplete_hidden(self):
        for kind in ['testStart', 'testDone']:
            events = fixture()
            event = next(e for e in events if e['type'] == kind and
                         (e.get('testID') == 3 or e.get('test', {}).get('id') == 3))
            events.insert(-1, copy.deepcopy(event))
            self.refused(events)
        self.refused([e for e in fixture() if not (e['type'] == 'testDone' and e['testID'] == 3)], 'incomplete-tests')

    def test_exit_one_and_single_false_final_terminal_required(self):
        for code in [0, 2, -9, True, None]:
            self.refused(fixture(), 'expected-exit-one', returncode=code)
        for success in [True, 0, None]:
            events = fixture()
            events[-1]['success'] = success
            self.refused(events, 'terminal-mismatch')
        self.refused(fixture()[:-1], 'terminal-mismatch')
        self.refused(fixture() + [dict(type='done', success=False)], 'terminal-mismatch')
        self.refused(fixture() + [dict(type='print', message=SECRET)], 'terminal-mismatch')

    def test_malformed_duplicate_key_nonfinite_and_unknown_events(self):
        for suffix in ['not JSON', '[]', '{"type":"print","type":"start"}',
                       '{"type":"print","x":NaN}', '{"type":"print","x":1e999}']:
            with self.assertRaises(c.GreenVerificationError):
                c.exact_red(raw(fixture()) + '\n' + suffix, 1, names=NAMES, basename=BASE, causal_ordinal=1)
        events = fixture()
        events.insert(-1, dict(type='unexpected'))
        self.refused(events, 'unknown-event')

    def test_compile_errors_in_stdout_or_stderr_never_count_as_causal(self):
        for name in [BASE, 'other_file.dart']:
            diagnostic = f'{SECRET}/{name}:10:20: Error: {SECRET}'
            self.refused(fixture(), 'compiler-diagnostic', stderr=diagnostic)
            with self.assertRaises(c.GreenVerificationError):
                c.exact_red(diagnostic, 1, names=NAMES, basename=BASE, causal_ordinal=1)

    def test_bounds_and_invalid_inventory(self):
        with patch.object(c, 'MAX_BYTES', 5):
            self.refused(fixture(), 'output-limit')
        with patch.object(c, 'MAX_EVENTS', 3):
            self.refused(fixture(), 'event-limit')
        for names in [[], NAMES[:2], NAMES + ['extra'], [NAMES[0]] * 3, [True, 'b', 'c']]:
            self.refused(fixture(), 'invalid-inventory', names=names)
        for ordinal in [0, 4, True, '1']:
            self.refused(fixture(), 'invalid-inventory', causal_ordinal=ordinal)

    def test_whole_stream_observation_retains_all_later_errors_and_terminal(self):
        events = fixture()
        events.insert(-1, dict(type='error', testID=2, isFailure=False, error='StateError: ' + SECRET))
        report = c.observe_green(raw(events), 1, expected_names=NAMES, fixture_basename=BASE)
        self.assertEqual(report['errorCount'], 2)
        self.assertEqual(report['completedTests'], 4)
        self.assertEqual(report['terminalCount'], 1)
        self.assertIs(report['terminalSuccess'], False)
        self.assertEqual(report['errors'][0]['locations'], [dict(line=17, column=3)])
        self.assertEqual(report['errors'][1]['testOrdinal'], 3)
        self.assertNotIn(SECRET, json.dumps(report))


class DispatchEvidenceTests(unittest.TestCase):
    def test_three_exact_finite_case_scoped_reports(self):
        report = c.dispatch_observation(raw(fixture()), NAMES)
        self.assertEqual(report['reportCount'], 3)
        self.assertEqual(report['invalidReports'], 0)
        self.assertEqual([item['testOrdinal'] for item in report['records']], [1, 2, 3])
        self.assertNotIn(SECRET, json.dumps(report))

    def test_private_unknown_fields_types_ranges_and_change_rejected(self):
        changes = [('secret', SECRET), ('change', SECRET), ('change', 'authority_owner'),
                   ('bSampleElapsedMs', -1), ('cSampleElapsedMs', 60001), ('cSampleElapsedMs', 100),
                   ('bSequence', 3), ('metadataRequests', 1), ('backwardCount', True),
                   ('pendingTargetMs', 300001),
                   ('nativeSeeks', [dict(phase=SECRET, targetMs=0, nativeBeforeMs=0, completed=True)]),
                   ('nativeSeeks', [dict(phase='B_released', targetMs=0, nativeBeforeMs=0, completed=1)]),
                   ('nativeSeeks', [dict(phase='B_released', targetMs=0, nativeBeforeMs=0, completed=True, secret=SECRET)])]
        changes.append(('whileHeld', [evidence(1)['nativeSeeks'][0]] * 10))
        for key, value in changes:
            events = fixture()
            message = next(e for e in events if e['type'] == 'print' and e.get('testID') == 0 and e['message'].startswith(c.EVIDENCE_PREFIX))
            data = evidence(1)
            data[key] = value
            message['message'] = c.EVIDENCE_PREFIX + json.dumps(data)
            report = c.dispatch_observation(raw(events), NAMES)
            self.assertEqual(report['invalidReports'], 1, (key, value))
            self.assertEqual(len(report['records']), 2)
            self.assertNotIn(SECRET, json.dumps(report))

    def test_missing_duplicate_unstarted_after_complete_and_wrong_case(self):
        for mutation in ['missing', 'duplicate', 'unstarted', 'after', 'wrong']:
            events = fixture()
            message = next(e for e in events if e['type'] == 'print' and e.get('testID') == 0 and e['message'].startswith(c.EVIDENCE_PREFIX))
            if mutation == 'missing': events.remove(message)
            elif mutation == 'duplicate': events.insert(events.index(message) + 1, dict(message))
            elif mutation == 'unstarted': message['testID'] = 50
            elif mutation == 'wrong': message['testID'] = 1
            else:
                events.remove(message)
                events.insert(-1, message)
            report = c.dispatch_observation(raw(events), NAMES)
            self.assertFalse(report['reportCount'] == 3 and report['invalidReports'] == 0 and len(report['records']) == 3)

    def test_malformed_evidence_and_capture_caps_are_finite(self):
        events = fixture()
        message = next(e for e in events if e['type'] == 'print' and e.get('testID') == 0 and e['message'].startswith(c.EVIDENCE_PREFIX))
        for body in [SECRET, '{"change":"same_generation","change":"same_generation"}', '[]', '{"x":NaN}', 'x' * 4096]:
            message['message'] = c.EVIDENCE_PREFIX + body
            report = c.dispatch_observation(raw(events), NAMES)
            self.assertEqual(report['invalidReports'], 1)
            self.assertNotIn(SECRET, json.dumps(report))
        with patch.object(c, 'MAX_BYTES', 10):
            self.assertEqual(c.dispatch_observation(raw(fixture()), NAMES)['reason'], 'output-limit')
        with patch.object(c, 'MAX_EVENTS', 1):
            self.assertEqual(c.dispatch_observation(raw(fixture()), NAMES)['reason'], 'event-limit')


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name).resolve()
        self.path = 'test/services/' + BASE
        (self.source / 'test/services').mkdir(parents=True)
        (self.source / self.path).write_text(SECRET)
        self.suite = dict(path=self.path, sha256=hashlib.sha256(SECRET.encode()).hexdigest(),
                          names=NAMES, causalOrdinal=1)
        self.addCleanup(patch.stopall)
        patch.object(c, 'INVENTORY_PATH', 'inventory.json').start()
        self.write()

    def write(self, value=None):
        data = json.dumps(dict(suites=[self.suite]) if value is None else value).encode()
        (self.source / 'inventory.json').write_bytes(data)
        patch.object(c, 'INVENTORY_SHA256', hashlib.sha256(data).hexdigest()).start()

    def test_hash_pinned_exact_private_inventory(self):
        self.assertEqual(c.inventory(self.source), self.suite)

    def test_manifest_fixture_and_schema_tampering(self):
        (self.source / 'inventory.json').write_text(SECRET)
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
        self.write()
        (self.source / self.path).write_text('changed')
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
        (self.source / self.path).write_text(SECRET)
        for key, value in [('path', '../escape_test.dart'), ('path', '/absolute_test.dart'),
                           ('sha256', 'bad'), ('causalOrdinal', True), ('causalOrdinal', 4),
                           ('names', NAMES[:2]), ('names', [NAMES[0]] * 3)]:
            old = self.suite[key]
            self.suite[key] = value
            self.write()
            with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
            self.suite[key] = old
        for value in [dict(suites=[]), dict(suites=[self.suite, self.suite]), dict(suites=[self.suite], extra=SECRET)]:
            self.write(value)
            with self.assertRaises(c.request.p.GateError): c.inventory(self.source)

    def test_fixture_and_manifest_symlinks_denied(self):
        for relative in [self.path, 'inventory.json']:
            path = self.source / relative
            data = path.read_bytes()
            path.unlink()
            other = self.source / 'actual'
            other.write_bytes(data)
            path.symlink_to(other)
            with self.assertRaises(c.request.p.GateError): c.inventory(self.source)
            path.unlink()
            path.write_bytes(data)
            other.unlink()
        directory = self.source / 'test/services'
        directory.rename(self.source / 'actual-services')
        directory.symlink_to(self.source / 'actual-services', target_is_directory=True)
        with self.assertRaises(c.request.p.GateError): c.inventory(self.source)


class ExecutionTests(unittest.TestCase):
    def test_capture_success_nonzero_timeout_and_output_limit(self):
        command = lambda code: [sys.executable, '-c', code]
        result, reason = c.bounded_run(command('import sys; print("ok"); print("err", file=sys.stderr); sys.exit(1)'))
        self.assertEqual((result.returncode, result.stdout, result.stderr, reason), (1, 'ok\n', 'err\n', None))
        result, reason = c.bounded_run(command('import time; print("partial", flush=True); time.sleep(10)'), timeout=1)
        self.assertEqual(reason, 'timeout')
        self.assertIn('partial', result.stdout)
        result, reason = c.bounded_run(command('print("x"*10000)'), max_bytes=1024)
        self.assertEqual(reason, 'output-limit')
        self.assertEqual(len(result.stdout.encode()) + len(result.stderr.encode()), 1024)

    def test_capture_unavailable_command_does_not_leak(self):
        with self.assertRaises(FileNotFoundError):
            c.bounded_run(['/nonexistent/' + SECRET])

    def proof_patches(self, stack, result=None, reason=None, fingerprints=None):
        source = Path('/synthetic/source')
        stack.enter_context(patch.object(c.request.p, 'source_context', return_value=(source, None, 'a' * 40, None)))
        stack.enter_context(patch.object(c, 'native_env', return_value={}))
        fingerprint = stack.enter_context(patch.object(c.request.p, 'source_fingerprint', side_effect=fingerprints or ['same', 'same']))
        codegen = stack.enter_context(patch.object(c.request.p, 'codegen'))
        suite = dict(path='test/services/' + BASE, names=NAMES, causalOrdinal=1)
        stack.enter_context(patch.object(c, 'inventory', return_value=suite))
        command = stack.enter_context(patch.object(c, 'bounded_run', return_value=(
            result or subprocess.CompletedProcess([], 1, raw(fixture()), ''), reason)))
        return fingerprint, codegen, command

    def test_proof_uses_complete_fixture_no_filter_and_fingerprint(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, command = self.proof_patches(stack)
            c.prove()
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(command.call_args.args[0], ['flutter', 'test', '--no-pub', '--reporter=json', 'test/services/' + BASE])
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]['completedTests'], 4)
            self.assertEqual(reports[-1]['passedControls'], 2)
            self.assertNotIn(SECRET, output.getvalue())

    def test_valid_marker_without_three_evidence_records_fails(self):
        events = [e for e in fixture() if not (e['type'] == 'print' and e.get('message', '').startswith(c.EVIDENCE_PREFIX))]
        result = subprocess.CompletedProcess([], 1, raw(events), '')
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, _ = self.proof_patches(stack, result=result)
            with self.assertRaises(c.request.p.GateError): c.prove()
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(c.STAGE, 'native-order-evidence')
            self.assertNotIn('expected-failure-confirmed', output.getvalue())

    def test_capture_failure_reports_whole_available_stream_before_rejecting(self):
        for reason in ['timeout', 'output-limit']:
            with self.subTest(reason=reason), contextlib.ExitStack() as stack:
                output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                fingerprint, _, _ = self.proof_patches(stack, reason=reason)
                with self.assertRaises(c.request.p.GateError): c.prove()
                self.assertEqual(fingerprint.call_count, 2)
                report = json.loads(output.getvalue().splitlines()[0])
                self.assertEqual(report['captureFailure'], reason)
                self.assertEqual(report['completedTests'], 4)
                self.assertNotIn(SECRET, output.getvalue())

    def test_codegen_failure_final_fingerprint_and_no_flutter(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, codegen, command = self.proof_patches(stack)
            codegen.side_effect = c.request.p.GateError(SECRET)
            with self.assertRaises(c.request.p.GateError): c.prove()
            self.assertEqual(fingerprint.call_count, 2)
            command.assert_not_called()
            self.assertNotIn(SECRET, output.getvalue())

    def test_final_fingerprint_mutation_overrides_success_and_failure(self):
        for reason in [None, 'timeout']:
            with contextlib.ExitStack() as stack:
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                self.proof_patches(stack, reason=reason, fingerprints=['before', 'after'])
                with self.assertRaises(c.request.p.GateError): c.prove()
                self.assertEqual(c.STAGE, 'final-fingerprint')

    def test_setup_failure_reports_only_finite_stage_and_exit(self):
        for args, stage in [(['flutter', 'pub', 'get'], 'dependencies'),
                            (['dart', 'run', 'scripts/check_navigation_consistency.dart'], 'navigation-check'),
                            (['dart', 'run', 'build_runner', 'build', '--delete-conflicting-outputs'], 'codegen')]:
            with patch.object(c, 'bounded_run', return_value=(subprocess.CompletedProcess([], 3, SECRET, SECRET), None)), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(c.request.p.GateError): c.bounded_quiet(args)
                self.assertEqual(json.loads(output.getvalue()), dict(stage=stage, status='failed', reason='command-failed', exitCode=3))
                self.assertNotIn(SECRET, output.getvalue())

    def test_setup_failure_reuses_finite_whole_stream_diagnostics(self):
        suite = dict(path='test/services/' + BASE, names=NAMES, causalOrdinal=1)
        diagnostic = f'{SECRET}/{BASE}:12:7: Error: {SECRET}'
        result = subprocess.CompletedProcess([], 1, diagnostic, SECRET)
        with patch.object(c, 'bounded_run', return_value=(result, None)), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(c.request.p.GateError):
                c.bounded_quiet(['dart', 'run', 'build_runner', 'build', '--delete-conflicting-outputs'], suite=suite)
            report = json.loads(output.getvalue())
            self.assertEqual(report['stage'], 'codegen')
            self.assertEqual(report['compileLocations'], [dict(line=12, column=7)])
            self.assertEqual(report['malformedEvents'], 1)
            self.assertNotIn(SECRET, output.getvalue())

    def test_pre_codegen_inventory_failure_still_fingerprints(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, codegen, command = self.proof_patches(stack)
            stack.enter_context(patch.object(c, 'inventory', side_effect=c.request.p.GateError(SECRET)))
            with self.assertRaises(c.request.p.GateError): c.prove()
            self.assertEqual(fingerprint.call_count, 2)
            codegen.assert_not_called()
            command.assert_not_called()
            self.assertEqual(c.STAGE, 'inventory')

    def test_workflow_pins_and_no_native_package_or_private_artifact_steps(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / '.github/workflows/follow-ingress-proof.yml').read_text()
        request = json.loads((root / c.REQUEST_PATH).read_text())
        self.assertEqual(request, c.REQUEST)
        for value in [c.PARENT, c.MESSAGE, c.SOURCE_SHA, c.SOURCE_REF]:
            self.assertIn(value, text)
        self.assertEqual(text.count('source red'), 1)
        self.assertIn('if: always()', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('contents: read', text)
        self.assertEqual(text.count('secrets.SOURCE_READ_TOKEN'), 2)
        for forbidden in ['upload-artifact', 'RELEASE_WRITE_TOKEN', 'DEFAULT_SERVER_URL', 'source build', 'source publish', 'source validate_source', 'workflow_dispatch']:
            self.assertNotIn(forbidden, text)

    def test_forbidden_stages_never_reach_helpers(self):
        for category, stage in [('source', 'validate_source'), ('source', 'build'), ('source', 'publish'), ('native', 'red'), ('regression', 'red')]:
            with patch.object(sys, 'argv', ['check', category, stage]), patch.object(c.request, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(), 1)
                run.assert_not_called()

    def test_main_exception_categories_are_finite(self):
        for failure in [c.request.p.GateError(SECRET), FileNotFoundError(SECRET), ValueError(SECRET)]:
            with patch.object(sys, 'argv', ['check', 'source', 'red']), patch.object(c, 'SOURCE_SHA', 'a' * 40), patch.object(c, 'SOURCE_REF', 'refs/heads/test/synthetic'), patch.object(c.request, 'context', side_effect=failure), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(c.main(), 1)
                self.assertNotIn(SECRET, output.getvalue())
                self.assertEqual(json.loads(output.getvalue())['failedStage'], 'red')


if __name__ == '__main__':
    unittest.main()
