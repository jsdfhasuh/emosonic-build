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
            self.assertEqual(command.call_count, 3)
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([r['suiteOrdinal'] for r in reports[:-1]], [1,2,3])
            self.assertTrue(all(r['reason']=='timeout' for r in reports[:-1]))
            self.assertEqual(reports[-1]['category'], 'GateError')
            self.assertEqual(reports[-1]['failedStage'], 'focused-verification')
            self.assertNotIn('private', output.getvalue())

    def test_bad_green_is_finite_and_collects_all_three_suites(self):
        result = subprocess.CompletedProcess([], 1, 'private non JSON', 'private stderr')
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint, _, command = self.focused_patches(stack, result=result)
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(fingerprint.call_count, 2)
            self.assertEqual(command.call_count, 3)
            self.assertNotIn('private', output.getvalue())
            reports = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(reports[0]['suiteOrdinal'], 1)
            self.assertEqual(reports[-1]['category'], 'GateError')
            self.assertEqual([r['suiteOrdinal'] for r in reports if r['stage']=='fixed-flutter-observation'], [1,2,3])

    def test_final_fingerprint_detects_mutation_even_on_timeout(self):
        with contextlib.ExitStack() as stack:
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.focused_patches(stack, error=subprocess.TimeoutExpired('private command', 600), fingerprints=['before', 'after'])
            stack.enter_context(patch.object(sys, 'argv', ['check', 'source', 'focused']))
            self.assertEqual(c.main(), 1)
            self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['failedStage'], 'final-fingerprint')

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

    def test_first_failure_does_not_hide_later_success_and_final_gate_fails(self):
        results=[]
        for index, suite in enumerate(self.suites):
            events=[{'type':'testStart','test':{'id':0,'name':suite['names'][0]}},
                    {'type':'testDone','testID':0,'hidden':False,'skipped':False,
                     'result':'failure' if index==0 else 'success'},
                    {'type':'done','success':index!=0}]
            results.append(subprocess.CompletedProcess([],1 if index==0 else 0,
                '\n'.join(json.dumps(e) for e in events),''))
        with contextlib.ExitStack() as stack:
            output=stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            fingerprint,_,command=self.focused_patches(stack)
            command.side_effect=results
            stack.enter_context(patch.object(sys,'argv',['check','source','focused']))
            self.assertEqual(c.main(),1)
            self.assertEqual(command.call_count,3)
            self.assertEqual(fingerprint.call_count,2)
            reports=[json.loads(line) for line in output.getvalue().splitlines()]
            observations=[r for r in reports if r['stage']=='fixed-flutter-observation']
            self.assertEqual([r['terminalSuccess'] for r in observations],[False,True,True])
            verified=[r for r in reports if r['stage']=='fixed-flutter-green']
            self.assertEqual([r['status'] for r in verified],['failed','passed','passed'])
            self.assertEqual(reports[-1]['category'],'GateError')

    def test_forbidden_stage_never_delegates(self):
        for category, stage in (('native', 'follow'), ('source', 'publish'), ('source', 'build_android'), ('regression', 'focused')):
            with self.subTest(stage=stage), patch.object(sys, 'argv', ['check', category, stage]), patch.object(c.request, 'main') as base, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(), 1)
                base.assert_not_called()


if __name__ == '__main__': unittest.main()

class FullDiagnosticTests(unittest.TestCase):
    def test_analyzer_severity_codes_and_locations_are_finite(self):
        source=Path('/owned/source');paths={'lib/private.dart','test/services/private_test.dart'}
        raw='\n'.join(f'{level} • secret source text • lib/private.dart:{i}:2 • unused_import'
                      for i,level in enumerate(('error','warning','info'),1))
        raw+='\nwarning • secret • /outside/private.dart:7:8 • secret_code\nmalformed private output'
        report=c.analyzer_observation(raw,'',paths,source,1)
        self.assertEqual(report['severityCounts'],dict(error=1,warning=2,info=1))
        self.assertEqual(report['findings'][0],dict(severity='error',code='unused_import',fileOrdinal=1,line=1,column=2))
        self.assertEqual(report['findings'][-1],dict(severity='warning',code='other'))
        self.assertNotIn('secret',json.dumps(report));self.assertNotIn('private',json.dumps(report))

    def test_full_test_accounting_unknown_and_known_test_names(self):
        source=Path('/owned/source');name='test/services/private_test.dart';paths={name}
        events=[{'type':'suite','suite':{'id':5,'path':str(source/name)}},
                {'type':'testStart','test':{'id':7,'suiteID':5,'name':'secret test'}},
                {'type':'error','testID':7,'isFailure':True,'error':'Expected: true\nActual: <false>',
                 'stackTrace':str(source/name)+' 17:3 secret'},
                {'type':'testDone','testID':7,'result':'failure','hidden':False,'skipped':False},
                {'type':'done','success':False}]
        raw='\n'.join(json.dumps(e) for e in events)
        report=c.full_test_observation(raw,'',paths,source,[dict(path=name,names=['secret test'])],1)
        error=report['errors'][0]
        self.assertEqual(error['fileOrdinal'],1);self.assertEqual(error['testOrdinal'],1)
        self.assertEqual(error['locations'],[dict(line=17,column=3)])
        self.assertEqual(report['results']['failure'],1);self.assertIs(report['terminalSuccess'],False)
        self.assertNotIn('secret',json.dumps(report));self.assertNotIn('private',json.dumps(report))
        report=c.full_test_observation(raw,'',paths,source,[],1)
        self.assertNotIn('testOrdinal',report['errors'][0])
        events.insert(1,dict(type='suite',suite=dict(id=5,path=str(source/name))))
        report=c.full_test_observation('\n'.join(json.dumps(e) for e in events),'',paths,source,[],1)
        self.assertNotIn('fileOrdinal',report['errors'][0])

    def test_malformed_unknown_test_output_has_no_raw_leak(self):
        raw='not JSON secret\n'+json.dumps({'type':'error','testID':True,'error':'secret','isFailure':False})
        report=c.full_test_observation(raw,'secret',{'test/private_test.dart'},Path('/owned'),[],1)
        self.assertEqual(report['malformedEvents'],1)
        self.assertEqual(report['errors'],[dict(isFailure=False,category='other')])
        self.assertNotIn('secret',json.dumps(report))

    def test_exact_commands_and_exit_criteria_retained(self):
        for command in (c.ANALYZE_COMMAND,c.FULL_TEST_COMMAND):
            for exitcode in (0,1):
                source=Path('/owned');paths={'test/private_test.dart'}
                result=subprocess.CompletedProcess(command,exitcode,b'private output',b'private stderr')
                original_quiet=c.request.p.quiet
                original_fingerprint=c.request.p.source_fingerprint
                def run_base():
                    self.assertEqual(c.request.p.source_fingerprint(source,'a'*40,{}),('digest',paths))
                    return c.request.p.quiet(list(command),source,{})
                with self.subTest(command=command,exitcode=exitcode),patch.object(c.request,'main',side_effect=run_base),patch.object(c.request.p,'source_fingerprint',return_value=('digest',paths)),patch.object(c,'inventory',return_value=[]),patch.object(c.subprocess,'run',return_value=result) as process,contextlib.redirect_stdout(io.StringIO()) as output:
                    if exitcode:
                        with self.assertRaises(c.request.p.GateError):c.validate_full()
                    else:self.assertEqual(c.validate_full(),'private output')
                    self.assertEqual(process.call_args.args[0],list(command))
                    self.assertEqual(process.call_args.kwargs,dict(cwd=source,env={},stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False))
                    self.assertNotIn('private',output.getvalue())
                self.assertIs(c.request.p.quiet,original_quiet)
                self.assertIs(c.request.p.source_fingerprint,original_fingerprint)

    def test_nonmatching_commands_delegate_without_capture(self):
        command=['flutter','analyze','--no-pub']
        with patch.object(c.request,'main',side_effect=lambda:c.request.p.quiet(command,Path('/owned'),{})),patch.object(c.request.p,'quiet',return_value='original') as quiet,patch.object(c.subprocess,'run') as process:
            self.assertEqual(c.validate_full(),'original');quiet.assert_called_once_with(command,Path('/owned'),{});process.assert_not_called()

    def test_workflow_full_validation_precedes_focused_without_omission(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/follow-recovery-check.yml').read_text()
        self.assertLess(workflow.index('source validate_source'),workflow.index('source focused'))
        self.assertEqual(workflow.count('source focused'),1)
        self.assertIn('if: always()',workflow)

    def test_original_full_parser_still_rejects_malformed_success_exit(self):
        source=Path('/owned');sha='a'*40
        paths={'test/services/native_start_dependency_contract_test.dart','tool/native_start/verify_vendored_source.py'}
        results=[subprocess.CompletedProcess([],0,b'',b''),subprocess.CompletedProcess([],0,b'private invalid JSON',b'')]
        with patch.object(c.request,'main',side_effect=c.request.p.validate_source),patch.object(c.request.p,'source_context',return_value=(source,None,sha,None)),patch.object(c.request.p,'build_env',return_value={}),patch.object(c.request.p,'source_fingerprint',return_value=('digest',paths)) as fingerprint,patch.object(c.request.p,'codegen'),patch.object(c.request.p,'quiet',return_value=''),patch.object(c,'inventory',return_value=[]),patch.object(c.subprocess,'run',side_effect=results),contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(c.request.p.GateError):c.validate_full()
            self.assertEqual(fingerprint.call_count,2)
            self.assertNotIn('private',output.getvalue())

    def test_diagnostic_cap_does_not_truncate_original_full_report(self):
        source=Path('/owned');raw='x'*(16777216+1)
        result=subprocess.CompletedProcess([],0,raw.encode(),b'')
        def base():
            c.request.p.source_fingerprint(source,'a'*40,{})
            return c.request.p.quiet(list(c.FULL_TEST_COMMAND),source,{})
        with patch.object(c.request,'main',side_effect=base),patch.object(c.request.p,'source_fingerprint',return_value=('digest',set())),patch.object(c,'inventory',return_value=[]),patch.object(c.subprocess,'run',return_value=result),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(c.validate_full(),raw)
            self.assertEqual(json.loads(output.getvalue())['malformedEvents'],1)
            self.assertNotIn('reason',json.loads(output.getvalue()))

    def test_flow_control_lint_has_fixed_code_and_tracked_location(self):
        report=c.analyzer_observation('info • private text • lib/private.dart:12:3 • curly_braces_in_flow_control_structures','',{'lib/private.dart'},Path('/owned'),1)
        self.assertEqual(report['findings'],[dict(severity='info',code='curly_braces_in_flow_control_structures',fileOrdinal=1,line=12,column=3)])
        self.assertEqual(report['exitCode'],1)

    def test_full_diagnostics_requests_explicit_larger_budget(self):
        with patch.object(c,'observe_green',return_value={'reason':'output-limit','errors':[]}) as observe:
            report=c.full_test_observation('', '', set(), Path('/owned'), [], 0)
            self.assertEqual(report['reason'],'output-limit')
            self.assertEqual(observe.call_args.kwargs['diagnostic_max_bytes'],128*1024*1024)
            self.assertEqual(observe.call_args.kwargs['diagnostic_max_events'],1000000)
