import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import handoff_follow_timing as c

class TimingWrapperTests(unittest.TestCase):
    def proof(self):
        run={'id':39745934922,'head_sha':'4a099e5ecc1aa6e997dd1f776994590e57da774e',
             'path':'.github/workflows/follow-seek-latency-proof.yml','event':'push','head_branch':'main','status':'completed','conclusion':'success'}
        jobs={'jobs':[{'name':'red-baseline','run_id':39745934922,'head_sha':run['head_sha'],'status':'completed','conclusion':'success',
                      'steps':[{'name':name,'conclusion':'success'} for name in ('Require exact real-controller held-seek feedback regression','Remove private baseline and generated diagnostics')]}]}
        return run,jobs

    def test_exact_causal_proof_required(self):
        with patch.object(c.base.request.p,'api',side_effect=self.proof()):c.require_causal_proof()
        for key,value in [('conclusion','failure'),('status','in_progress'),('head_sha','0'*40),('head_branch','other'),('path','other')]:
            run,jobs=self.proof();run[key]=value
            with self.subTest(key=key),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_causal_proof()

    def test_failed_or_missing_proof_cleanup_refused(self):
        for mutate in ('missing','failure','duplicate','wrong-source'):
            run,jobs=self.proof();job=jobs['jobs'][0]
            if mutate=='missing':job['steps'].pop()
            elif mutate=='failure':job['steps'][0]['conclusion']='failure'
            elif mutate=='duplicate':jobs['jobs'].append(dict(job))
            else:job['head_sha']='0'*40
            with self.subTest(mutate=mutate),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_causal_proof()

    def test_prepare_order(self):
        calls=[]
        with patch.object(sys,'argv',['helper','native','prepare']),patch.object(c.recovery_observation,'verify'),patch.object(c.base,'main',side_effect=lambda:calls.append('base') or 0),patch.object(c.lifecycle,'apply',side_effect=lambda p:calls.append('lifecycle')),patch.object(c.timing,'apply',side_effect=lambda p:calls.append('timing')):
            self.assertEqual(c.main(),0)
        self.assertEqual(calls,['base','lifecycle','timing'])

    def test_explicit_composed_verification_and_schema(self):
        original_schema=dict(c.base.native.RATE_SCHEMA)
        def run():
            c.base.readiness.verify_prepared(Path('source'))
            self.assertEqual(c.base.ATTRIBUTION_EXTRA_ARGS,('--lab-debug-observation','--lab-timing-observation','--lab-recovery-observation'))
            self.assertEqual(c.base.OBSERVED_HARNESS_SHA256,c.timing.AFTER[c.timing.HARNESS])
            self.assertIs(c.base.native.RATE_SCHEMA['nativeTiming']['follower'],c.timing.SCHEMA)
            return 0
        with patch.object(sys,'argv',['helper','native','attribution']),patch.object(c.recovery_observation,'verify'),patch.object(c.base,'main',side_effect=run),patch.object(c.lifecycle,'verify_prepared') as lifecycle,patch.object(c.timing,'verify_prepared') as timing,patch.object(c.base.readiness,'verify_prepared') as readiness:
            self.assertEqual(c.main(),0)
            self.assertTrue(lifecycle.call_args.kwargs['timing_observation'])
            self.assertTrue(timing.call_args.kwargs['require_harness'])
            self.assertEqual(readiness.call_args.kwargs,{'timing_observation':True})
        self.assertEqual(c.base.native.RATE_SCHEMA,original_schema)

    def test_compile_verification_after_success_only(self):
        for result in (0,1):
            with self.subTest(result=result),patch.object(sys,'argv',['helper','native','build']),patch.object(c.recovery_observation,'verify'),patch.object(c.base,'main',return_value=result),patch.object(c.lifecycle,'verify_prepared'),patch.object(c.timing,'verify_prepared'),patch.object(c.timing,'verify_compiled') as compiled:
                self.assertEqual(c.main(),result)
                self.assertEqual(compiled.call_count,1 if result==0 else 0)

    def test_package_stages_forbidden(self):
        for category,stage in [('source','build'),('source','publish'),('native','publish'),('other','prepare')]:
            with self.subTest(category=category,stage=stage),patch.object(sys,'argv',['helper',category,stage]),patch.object(c.base,'main') as base:
                self.assertEqual(c.main(),1);base.assert_not_called()

    def test_exact_workflow_request(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows'/c.WORKFLOW).read_text()
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,workflow)
        self.assertLess(workflow.index("handoff_follow_timing.py native follow"), workflow.index("handoff_follow_timing.py native handoff"))
        self.assertIn('persist-credentials: false',workflow)
        self.assertNotIn('contents: write',workflow)
        self.assertNotIn('upload-artifact',workflow)
        self.assertNotIn('publish-stable',workflow)

    def test_timing_schema_ignores_unknown_private_content(self):
        value=c.base.native.diagnostic_value({'private':'secret','authority':{'private':'secret'},'follower':{'private':'secret'}},{'authority':c.timing.SCHEMA,'follower':c.timing.SCHEMA})
        self.assertNotIn('secret',json.dumps(value));self.assertNotIn('private',json.dumps(value))

class RecoveryValidationGateTests(unittest.TestCase):
    def evidence(self):
        run={'id':c.VALIDATION_RUN,'head_sha':c.VALIDATION_HEAD,
             'path':'.github/workflows/follow-recovery-check.yml','event':'push',
             'head_branch':'main','run_attempt':1,'status':'completed','conclusion':'success'}
        jobs={'jobs':[{'name':name,'run_id':c.VALIDATION_RUN,'head_sha':c.VALIDATION_HEAD,
                       'status':'completed','conclusion':'success',
                       'steps':[{'name':step,'status':'completed','conclusion':'success'} for step in steps]}
                      for name,steps in c.VALIDATION_STEPS.items()]}
        jobs['total_count']=len(jobs['jobs'])
        return run,jobs

    def test_complete_exact_evidence(self):
        with patch.object(c.base.request.p,'api',side_effect=self.evidence()) as api:
            c.require_recovery_validation()
        self.assertEqual(api.call_args_list[0].args[0],'/repos/jsdfhasuh/emosonic-build/actions/runs/39767536382')
        self.assertEqual(c.SOURCE_SHA,c.timing.SOURCE_SHA)

    def test_pending_failed_wrong_run_head_workflow_and_attempt_refused(self):
        for key,value in [('id',39763027779),('head_sha','0'*40),('path','other'),
                          ('event','workflow_dispatch'),('head_branch','other'),
                          ('status','in_progress'),('conclusion','failure'),
                          ('run_attempt',2),('run_attempt',True)]:
            run,jobs=self.evidence();run[key]=value
            with self.subTest(key=key),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
                c.require_recovery_validation()

    def test_missing_failed_duplicate_or_partial_jobs_refused(self):
        for mode in ('missing','duplicate','failed','wrong-head','wrong-run','pending','truncated'):
            run,jobs=self.evidence();job=jobs['jobs'][0]
            if mode=='missing':jobs['jobs'].pop()
            elif mode=='duplicate':jobs['jobs'].append(dict(job))
            elif mode=='failed':job['conclusion']='failure'
            elif mode=='wrong-head':job['head_sha']='0'*40
            elif mode=='wrong-run':job['run_id']=0
            elif mode=='pending':job['status']='in_progress'
            if mode!='truncated':jobs['total_count']=len(jobs['jobs'])
            else:jobs['total_count']=101
            with self.subTest(mode=mode),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
                c.require_recovery_validation()

    def test_every_required_test_proof_and_cleanup_step_must_succeed(self):
        for index, names in enumerate(c.VALIDATION_STEPS.values()):
            for ordinal in range(len(names)):
                for mode in ('absent','duplicate','failed','skipped','pending'):
                    run,jobs=self.evidence();steps=jobs['jobs'][index]['steps']
                    if mode=='absent':steps.pop(ordinal)
                    elif mode=='duplicate':steps.append(dict(steps[ordinal]))
                    elif mode=='pending':steps[ordinal]['status']='in_progress'
                    else:steps[ordinal]['conclusion']='failure' if mode=='failed' else 'skipped'
                    with self.subTest(index=index,ordinal=ordinal,mode=mode),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
                        c.require_recovery_validation()

    def test_prepare_gates_both_before_any_source_action(self):
        calls=[]
        with patch.object(sys,'argv',['helper','source','prepare']),patch.object(c,'require_causal_proof',side_effect=lambda:calls.append('causal')),patch.object(c,'require_recovery_validation',side_effect=lambda:calls.append('recovery')),patch.object(c,'require_ingress_validation',side_effect=lambda:calls.append('ingress')),patch.object(c.base,'main',side_effect=lambda:calls.append('source') or 0):
            self.assertEqual(c.main(),0)
        self.assertEqual(calls,['causal','recovery','ingress','source'])
        for blocked in ('require_recovery_validation','require_ingress_validation'):
            with self.subTest(blocked=blocked),patch.object(sys,'argv',['helper','source','prepare']),patch.object(c,'require_causal_proof'),patch.object(c,'require_recovery_validation'),patch.object(c,'require_ingress_validation'),patch.object(c,blocked,side_effect=c.base.request.p.GateError('not complete')),patch.object(c.base,'main') as base:
                self.assertEqual(c.main(),1)
                base.assert_not_called()


class IngressValidationGateTests(unittest.TestCase):
    def evidence(self):
        run={'id':c.INGRESS_RUN,'head_sha':c.INGRESS_HEAD,
             'path':'.github/workflows/follow-bounded-budget-green.yml','event':'push',
             'head_branch':'main','run_attempt':1,'status':'completed','conclusion':'success'}
        jobs={'jobs':[{'name':name,'run_id':c.INGRESS_RUN,'head_sha':c.INGRESS_HEAD,
                       'status':'completed','conclusion':'success',
                       'steps':[{'name':step,'status':'completed','conclusion':'success'} for step in steps]}
                      for name,steps in c.INGRESS_STEPS.items()]}
        jobs['total_count']=len(jobs['jobs'])
        return run,jobs

    def test_exact_bounded_budget_successor_pins_and_both_matrix_stages(self):
        self.assertEqual(c.SOURCE_SHA,'bfc1967a8eae65154bdd5e74491f99136dfc198d')
        self.assertEqual(c.SOURCE_REF,'refs/heads/fix/follow-bounded-budget-20261024')
        self.assertEqual(c.PARENT,'99eff9a11146fe47d3cec5611d5207919f749514')
        self.assertEqual(c.REQUEST['attempt'],113)
        self.assertEqual(c.INGRESS_RUN,40062350211)
        self.assertEqual(c.INGRESS_HEAD,'99eff9a11146fe47d3cec5611d5207919f749514')
        self.assertEqual(c.REQUEST['ingress_validation_run_id'],c.INGRESS_RUN)
        self.assertEqual(c.INGRESS_STEPS['validate-source'][0],'Validate all 282 historical and bounded budget focused cases')
        self.assertIn('follow',c.NATIVE_STAGES);self.assertIn('handoff',c.NATIVE_STAGES)

    def test_exact_282_case_current_inventory_not_stale_275_gate(self):
        import follow_bounded_budget_green as green
        self.assertEqual(c.SOURCE_SHA, green.SOURCE_SHA)
        self.assertEqual(c.SOURCE_REF, green.SOURCE_REF)
        self.assertEqual(green.EXPECTED_COUNTS, (4, 3))
        self.assertEqual(green.INVENTORY_PATH, 'tool/follow_bounded_budget/green_inventory.json')
        self.assertEqual(green.INVENTORY_SHA256, '1eb1a52bcac9190ad9a1037b7c20e37f9e5e5c6ae15a78514e4c7571893f15e0')
        self.assertEqual(c.INGRESS_STEPS['validate-source'][0], 'Validate all 282 historical and bounded budget focused cases')
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/follow-bounded-budget-green.yml').read_text()
        self.assertIn(c.SOURCE_SHA, workflow)
        self.assertIn('follow_bounded_budget_green.py source focused', workflow)
        self.assertIn(c.INGRESS_STEPS['validate-source'][0], workflow)

    def test_exact_current_candidate_green_required(self):
        with patch.object(c.base.request.p,'api',side_effect=self.evidence()):c.require_ingress_validation()

    def test_nonterminal_wrong_run_source_workflow_attempt_refused(self):
        for key,value in [('id',39788641373),('head_sha','0'*40),('path','other'),('status','in_progress'),('conclusion','failure'),('run_attempt',2)]:
            run,jobs=self.evidence();run[key]=value
            with self.subTest(key=key),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_ingress_validation()

    def test_failed_missing_or_duplicate_required_step_refused(self):
        for ordinal in range(len(c.INGRESS_STEPS['validate-source'])):
            for change in ('failure','missing','duplicate','skipped','pending'):
                run,jobs=self.evidence();steps=jobs['jobs'][0]['steps']
                if change=='missing':steps.pop(ordinal)
                elif change=='duplicate':steps.append(dict(steps[ordinal]))
                elif change=='pending':steps[ordinal]['status']='in_progress'
                else:steps[ordinal]['conclusion']=change
                with self.subTest(ordinal=ordinal,change=change),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_ingress_validation()


    def test_terminal_previous_275_source_gate_cannot_admit_bounded_candidate(self):
        run,jobs=self.evidence()
        run.update(id=40051389321, head_sha='aaa7cc0cd8ba476d1b90e6900ab4e65163e7292b',
                   path='.github/workflows/follow-ordinary-settle-green.yml')
        jobs['jobs'][0].update(run_id=run['id'], head_sha=run['head_sha'])
        jobs['jobs'][0]['steps'][0]['name']='Validate all prior and ordinary settlement focused cases'
        with patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
            c.require_ingress_validation()

    def test_current_run_with_stale_275_focused_step_is_refused(self):
        run,jobs=self.evidence()
        jobs['jobs'][0]['steps'][0]['name']='Validate all prior and ordinary settlement focused cases'
        with patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
            c.require_ingress_validation()

    def test_bounded_gate_requires_matching_terminal_complete_job(self):
        for mode in ('missing','duplicate','wrong-run','wrong-head','pending','failed','truncated'):
            run,jobs=self.evidence();job=jobs['jobs'][0]
            if mode=='missing':jobs['jobs'].clear()
            elif mode=='duplicate':jobs['jobs'].append(dict(job))
            elif mode=='wrong-run':job['run_id']=40051389321
            elif mode=='wrong-head':job['head_sha']='aaa7cc0cd8ba476d1b90e6900ab4e65163e7292b'
            elif mode=='pending':job['status']='in_progress'
            elif mode=='failed':job['conclusion']='failure'
            jobs['total_count']=101 if mode=='truncated' else len(jobs['jobs'])
            with self.subTest(mode=mode),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):
                c.require_ingress_validation()


class FixedNativeUnitAdapterTests(unittest.TestCase):
    command = [sys.executable, '-m', 'unittest', 'discover', '-s',
               'tool/native_playback_mac', '-p', 'test_*.py']
    result = {'stage': 'native-follow-unit-layers', 'status': 'passed',
              'priorProvenanceChecks': 70, 'finalCompatibleChecks': 63, 'finalPrecisionChecks': 46}

    def run_unit(self, action, *, result=None, error=None):
        original = c.base.native.execute
        with patch.object(sys, 'argv', ['helper', 'native', 'unit']), \
             patch.object(c.recovery_observation, 'verify'), \
             patch.object(c.lifecycle, 'verify_prepared'), \
             patch.object(c.timing, 'verify_prepared'), \
             patch.object(c.base, 'main', side_effect=action), \
             patch.object(c.base.readiness, 'verify_units', create=True,
                          return_value=self.result if result is None else result, side_effect=error) as units:
            status = c.main()
        self.assertIs(c.base.native.execute, original)
        return status, units

    def execute_once(self):
        c.base.native.execute(list(self.command), 'native-measurement-guards')
        return 0

    def test_exact_unit_command_runs_all_layers_once_and_restores(self):
        status, units = self.run_unit(self.execute_once)
        self.assertEqual(status, 0)
        units.assert_called_once_with(c.base.request.p.ROOT / 'source')

    def test_unexpected_command_label_path_report_and_argument_types_fail_closed(self):
        wrong_path = list(self.command); wrong_path[5] = 'elsewhere'
        for args in [(wrong_path, 'native-measurement-guards'),
                     (self.command + ['extra'], 'native-measurement-guards'),
                     (self.command, 'other'), (self.command, 'native-measurement-guards', True),
                     (self.command, 'native-measurement-guards', 0),
                     (tuple(self.command), 'native-measurement-guards')]:
            with self.subTest(args=args):
                status, units = self.run_unit(lambda: c.base.native.execute(*args) or 0)
                self.assertEqual(status, 1); units.assert_not_called()

    def test_missing_or_duplicate_unit_invocation_fails_closed(self):
        status, units = self.run_unit(lambda: 0)
        self.assertEqual(status, 1); units.assert_not_called()
        def twice():
            self.execute_once(); return self.execute_once()
        status, units = self.run_unit(twice)
        self.assertEqual(status, 1); self.assertEqual(units.call_count, 1)

    def test_exact_unit_report_requires_all_counts_status_and_no_extra_keys(self):
        for key, value in [('priorProvenanceChecks', 69), ('finalCompatibleChecks', 62),
                           ('finalPrecisionChecks', 39), ('priorProvenanceChecks', 70.0),
                           ('finalPrecisionChecks', True), ('status', 'failed'),
                           ('stage', 'other'), ('extra', True)]:
            report = dict(self.result, **{key: value})
            with self.subTest(key=key, value=value):
                status, units = self.run_unit(self.execute_once, result=report)
                self.assertEqual(status, 1); self.assertEqual(units.call_count, 1)

    def test_unit_failure_restores_execute_and_does_not_retry(self):
        status, units = self.run_unit(self.execute_once, error=ValueError('synthetic'))
        self.assertEqual(status, 1); self.assertEqual(units.call_count, 1)

    def test_non_unit_execution_delegates_unchanged(self):
        def action():
            c.base.native.execute(['synthetic'], 'unchanged', True)
            return 0
        with patch.object(sys, 'argv', ['helper', 'native', 'dependencies']), \
             patch.object(c.recovery_observation, 'verify'), \
             patch.object(c.base, 'main', side_effect=action), \
             patch.object(c.base.native, 'execute') as execute, \
             patch.object(c.base.readiness, 'verify_units', create=True) as units:
            self.assertEqual(c.main(), 0)
        execute.assert_called_once_with(['synthetic'], 'unchanged', True)
        units.assert_not_called()

    def test_actual_base_unit_retains_context_source_server_and_platform_guards(self):
        for mode in ('valid', 'wrong-source', 'wrong-server', 'wrong-platform', 'no-network-approval'):
            with self.subTest(mode=mode):
                heads = [c.SOURCE_SHA, c.SERVER_SHA] * 2
                if mode == 'wrong-source': heads[0] = '0' * 40
                if mode == 'wrong-server': heads[1] = '0' * 40
                original = c.base.native.execute
                with patch.object(sys, 'argv', ['helper', 'native', 'unit']), \
                     patch.object(sys, 'platform', 'linux' if mode == 'wrong-platform' else 'darwin'), \
                     patch.dict(c.base.native.os.environ, {'EMOSONIC_MAC_LAB_NETWORK_APPROVED':
                         '0' if mode == 'no-network-approval' else '1'}), \
                     patch.object(c.recovery_observation, 'verify'), \
                     patch.object(c.lifecycle, 'verify_prepared'), \
                     patch.object(c.timing, 'verify_prepared'), \
                     patch.object(c.base.readiness, 'verify_prepared'), \
                     patch.object(c.base.request, 'context') as context, \
                     patch.object(c.base.request.p, 'quiet', side_effect=heads) as quiet, \
                     patch.object(c.base.readiness, 'verify_units', create=True, return_value=self.result) as units:
                    self.assertEqual(c.main(), 0 if mode == 'valid' else 1)
                self.assertIs(c.base.native.execute, original)
                if mode == 'valid':
                    self.assertEqual(context.call_count, 2)
                    self.assertEqual(quiet.call_count, 4)
                    units.assert_called_once_with(c.base.request.p.ROOT / 'source')
                else:
                    units.assert_not_called()


    def test_unit_api_inherits_exact_native_environment_filter_and_restores(self):
        excluded = ('SOURCE_READ_TOKEN', 'GITHUB_TOKEN', 'APP_PASSWORD', 'API_SECRET',
                    'KEYSTORE_PATH', 'KEY_ALIAS', 'DEFAULT_SERVER_URL', 'GITHUB_ENV',
                    'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY')
        values = {key: 'synthetic' for key in excluded}
        values['NATIVE_UNIT_SAFE_MARKER'] = 'retained'
        for fail in (False, True):
            def verify(_):
                self.assertTrue(all(key not in c.base.native.os.environ for key in excluded))
                self.assertEqual(c.base.native.os.environ['NATIVE_UNIT_SAFE_MARKER'], 'retained')
                if fail:
                    raise ValueError('synthetic')
                return dict(self.result)
            with self.subTest(fail=fail), patch.dict(c.base.native.os.environ, values):
                status, units = self.run_unit(self.execute_once, error=verify)
                self.assertEqual(status, 1 if fail else 0)
                self.assertEqual(units.call_count, 1)
                self.assertTrue(all(c.base.native.os.environ[key] == value for key, value in values.items()))
