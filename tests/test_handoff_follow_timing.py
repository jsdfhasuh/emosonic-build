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
        with patch.object(sys,'argv',['helper','native','prepare']),patch.object(c.base,'main',side_effect=lambda:calls.append('base') or 0),patch.object(c.lifecycle,'apply',side_effect=lambda p:calls.append('lifecycle')),patch.object(c.timing,'apply',side_effect=lambda p:calls.append('timing')):
            self.assertEqual(c.main(),0)
        self.assertEqual(calls,['base','lifecycle','timing'])

    def test_explicit_composed_verification_and_schema(self):
        original_schema=dict(c.base.native.RATE_SCHEMA)
        def run():
            c.base.readiness.verify_prepared(Path('source'))
            self.assertEqual(c.base.ATTRIBUTION_EXTRA_ARGS,('--lab-debug-observation','--lab-timing-observation'))
            self.assertEqual(c.base.OBSERVED_HARNESS_SHA256,c.timing.AFTER[c.timing.HARNESS])
            self.assertIs(c.base.native.RATE_SCHEMA['nativeTiming']['follower'],c.timing.SCHEMA)
            return 0
        with patch.object(sys,'argv',['helper','native','unit']),patch.object(c.base,'main',side_effect=run),patch.object(c.lifecycle,'verify_prepared') as lifecycle,patch.object(c.timing,'verify_prepared') as timing,patch.object(c.base.readiness,'verify_prepared') as readiness:
            self.assertEqual(c.main(),0)
            self.assertTrue(lifecycle.call_args.kwargs['timing_observation'])
            self.assertTrue(timing.call_args.kwargs['require_harness'])
            self.assertEqual(readiness.call_args.kwargs,{'timing_observation':True})
        self.assertEqual(c.base.native.RATE_SCHEMA,original_schema)

    def test_compile_verification_after_success_only(self):
        for result in (0,1):
            with self.subTest(result=result),patch.object(sys,'argv',['helper','native','build']),patch.object(c.base,'main',return_value=result),patch.object(c.lifecycle,'verify_prepared'),patch.object(c.timing,'verify_prepared'),patch.object(c.timing,'verify_compiled') as compiled:
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
        with patch.object(sys,'argv',['helper','source','prepare']),patch.object(c,'require_causal_proof'),patch.object(c,'require_recovery_validation',side_effect=c.base.request.p.GateError('not complete')),patch.object(c.base,'main') as base:
            self.assertEqual(c.main(),1)
            base.assert_not_called()


class IngressValidationGateTests(unittest.TestCase):
    def evidence(self):
        run={'id':c.INGRESS_RUN,'head_sha':c.INGRESS_HEAD,
             'path':'.github/workflows/follow-timing-green.yml','event':'push',
             'head_branch':'main','run_attempt':1,'status':'completed','conclusion':'success'}
        jobs={'jobs':[{'name':name,'run_id':c.INGRESS_RUN,'head_sha':c.INGRESS_HEAD,
                       'status':'completed','conclusion':'success',
                       'steps':[{'name':step,'status':'completed','conclusion':'success'} for step in steps]}
                      for name,steps in c.INGRESS_STEPS.items()]}
        jobs['total_count']=len(jobs['jobs'])
        return run,jobs

    def test_exact_current_candidate_green_required(self):
        with patch.object(c.base.request.p,'api',side_effect=self.evidence()):c.require_ingress_validation()

    def test_nonterminal_wrong_run_source_workflow_attempt_refused(self):
        for key,value in [('id',39788641373),('head_sha','0'*40),('path','other'),('status','in_progress'),('conclusion','failure'),('run_attempt',2)]:
            run,jobs=self.evidence();run[key]=value
            with self.subTest(key=key),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_ingress_validation()

    def test_failed_missing_or_duplicate_required_step_refused(self):
        for change in ('failure','missing','duplicate'):
            run,jobs=self.evidence();steps=jobs['jobs'][0]['steps']
            if change=='failure':steps[0]['conclusion']='failure'
            elif change=='missing':steps.pop()
            else:steps.append(dict(steps[0]))
            with self.subTest(change=change),patch.object(c.base.request.p,'api',side_effect=[run,jobs]),self.assertRaises(c.base.request.p.GateError):c.require_ingress_validation()
