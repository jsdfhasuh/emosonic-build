"""Synthetic actual-method contracts for strict sampled Follow acceptance."""
import ast
import copy
import contextlib
import io
import importlib.util
import math
from pathlib import Path
import unittest

PRIOR = None
FINAL = None
_spec = importlib.util.spec_from_file_location('precision_synthetic_states', Path(__file__).with_name('readiness_contract.py'))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def pair(at, expected=1.5):
    values = fixture.pair(at)
    for value in (values[0], values[2]):
        value['followSyncToleranceMs'] = 50
        value['nativePlayers'][0].update(positionMs=round(10000+at*expected*1000),
            playbackRate=expected, requestedRate=expected)
    return values


def load(clock, final):
    names = fixture.NAMES | {'native_requested_rate', 'follow_correction_identity',
        'native_follow_readiness_pending', 'follow_nominal_precision_ready', 'follow_precision_sample',
        'FollowPrecisionUnsafe', 'FollowPrecisionDeadline', '_follow_process_identity', '_follow_canonical_identity',
        '_follow_transition_ownership', 'begin_follow_precision_transition', 'observe_follow_precision_transition'}
    tree = ast.parse(FINAL if final else PRIOR)
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    ns = {'math':math, 'time':clock, 'FOLLOW_CONDITIONS': {'steady_sample_precision', 'native_evidence', 'safe_follow_task', 'authority_rate', 'follower_rate', 'hard_drift_limit', 'lab_five_second_settling', 'native_35s_progression', 'rate_change', 'restoration'}, 'summarize_state':lambda *a,**kw: {},
          'successful_follow_observation': lambda matrix: {}}
    exec(compile(ast.Module(body=selected,type_ignores=[]), '<owned-strict-precision>', 'exec'),ns)
    return ns


class PrecisionTests(unittest.TestCase):
    def setup_matrix(self, *, final=True, mutate=None, expected=1.5, read_cost=0):
        clock=fixture.Clock(); ns=load(clock,final); matrix=ns['Matrix']()
        matrix.last=pair(0,expected); outcomes=[]; reads=[]
        def read():
            clock.now=round(clock.now+read_cost,6)
            states=pair(clock.now,expected)
            if mutate: mutate(states,clock.now)
            matrix.last=states; reads.append((clock.now,copy.deepcopy(states)))
            return states
        matrix.states=read
        matrix.outcome=lambda name,**metrics: outcomes.append((name,metrics,copy.deepcopy(matrix.rate_measurement)))
        return clock,ns,matrix,reads,outcomes

    def run_follow(self,matrix,expected=1.5):
        matrix.rate(2,expected,'precision',follow_context='authority-context',authority_index=0)

    def test_01_prior_accepts_correction_but_final_requires_nominal(self):
        def mutate(s,t):s[2]['nativePlayers'][0].update(playbackRate=1.56,requestedRate=1.56)
        prior=self.setup_matrix(final=False,mutate=mutate);self.run_follow(prior[2])
        self.assertEqual(prior[-1][-1][0],'precision')
        current=self.setup_matrix(mutate=mutate)
        with self.assertRaises(TimeoutError):self.run_follow(current[2])
        self.assertEqual(current[0].now,5);self.assertEqual(current[-1],[])

    def test_02_two_nominal_progress_pairs_required_before_window(self):
        def mutate(s,t):
            if t<.6:s[2]['nativePlayers'][0].update(playbackRate=1.56,requestedRate=1.56)
        clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
        self.run_follow(matrix)
        self.assertEqual(outcomes[0][1]['waitDurationMs'],800)
        self.assertEqual(outcomes[-1][2]['firstNative']['positionMs'],11200)
        self.assertGreaterEqual(outcomes[-1][1]['elapsedSeconds'],3)
        self.assertEqual(outcomes[-1][2]['precisionSamples'],outcomes[-1][1]['nativeSamples'])

    def test_03_one_nominal_sample_before_deadline_is_not_enough(self):
        def mutate(s,t):
            if t<4.8:s[2]['nativePlayers'][0].update(playbackRate=1.56,requestedRate=1.56)
        clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
        with self.assertRaises(TimeoutError):self.run_follow(matrix)
        self.assertEqual(clock.now,5);self.assertEqual(outcomes,[])

    def test_04_states_call_crossing_original_deadline_fails(self):
        clock,ns,matrix,reads,outcomes=self.setup_matrix(read_cost=2.6)
        with self.assertRaises(TimeoutError):self.run_follow(matrix)
        self.assertEqual(clock.now,5.4);self.assertEqual(outcomes,[])

    def test_05_requested_and_property_rates_both_must_be_nominal(self):
        for key in ('requestedRate','playbackRate'):
            def mutate(s,t):s[2]['nativePlayers'][0][key]=1.56
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.subTest(key=key),self.assertRaises(TimeoutError):self.run_follow(matrix)
            self.assertEqual(clock.now,5)

    def test_06_malformed_or_outside_cap_rates_fail_immediately(self):
        for key in ('requestedRate','playbackRate'):
            for value in (False,None,float('nan'),1.6):
                def mutate(s,t):s[2]['nativePlayers'][0][key]=value
                clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
                with self.subTest(key=key,value_type=type(value).__name__),self.assertRaises((AssertionError,TypeError)):self.run_follow(matrix)
                self.assertEqual(clock.now,0)

    def test_07_conservative_rounding_bound_at_both_rates(self):
        for expected,offset,allowed in ((1.5,46,True),(1.5,47,False),(.8,47,True),(.8,48,False)):
            def mutate(s,t):s[2]['nativePlayers'][0]['positionMs']+=offset
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate,expected=expected)
            if allowed:
                self.run_follow(matrix,expected)
                self.assertLessEqual(outcomes[-1][2]['precisionMaxWorstCaseMs'],50)
            else:
                with self.assertRaises(TimeoutError):self.run_follow(matrix,expected)
                self.assertEqual(clock.now,5)

    def test_08_prior_average_pass_does_not_mask_drift_excursion(self):
        def mutate(s,t):
            if 1<=t<1.6:s[2]['nativePlayers'][0]['positionMs']+=80
        prior=self.setup_matrix(final=False,mutate=mutate);self.run_follow(prior[2])
        current=self.setup_matrix(mutate=mutate)
        with self.assertRaises(AssertionError):self.run_follow(current[2])
        self.assertEqual(current[0].now,1)
        self.assertGreater(current[2].rate_measurement['precisionWorstCaseMs'],50)

    def test_09_reslew_after_measurement_start_fails_without_restart(self):
        for key in ('playbackRate','requestedRate'):
            def mutate(s,t):
                if t>=.4:s[2]['nativePlayers'][0][key]=1.56
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
            self.assertEqual(clock.now,.4)
            self.assertFalse(any(row[0]=='precision' for row in outcomes))

    def test_10_both_player_physical_short_stalls_fail(self):
        for role in (0,2):
            def mutate(s,t):
                if t>=1.4:s[role]['nativePlayers'][0]['positionMs']-=40
            prior=self.setup_matrix(final=False,mutate=mutate);self.run_follow(prior[2])
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
            self.assertEqual(clock.now,1.4)
            self.assertLessEqual(matrix.rate_measurement['precisionWorstCaseMs'],50)

    def test_11_both_player_short_jumps_cannot_average_away(self):
        for role in (0,2):
            def mutate(s,t):
                if t>=1.4:s[role]['nativePlayers'][0]['positionMs']+=40
            prior=self.setup_matrix(final=False,mutate=mutate);self.run_follow(prior[2])
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
            self.assertEqual(clock.now,1.4)

    def test_12_every_native_and_process_identity_is_frozen(self):
        for role in (0,2):
            for key in ('clientId','deviceSessionId','pid','bundleId','root','native_id'):
                def mutate(s,t):
                    if t>=.4:
                        if key=='native_id':s[role]['nativePlayers'][0]['id']='replacement'
                        else:s[role][key]=999 if key=='pid' else 'replacement'
                clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
                with self.subTest(role=role,key=key),self.assertRaises(AssertionError):self.run_follow(matrix)
                self.assertEqual(clock.now,.4)

    def test_13_control_epoch_queue_recovery_and_task_changes_fail(self):
        mutations=(lambda s:s[2].update(trackId='wrong'),lambda s:s[2].update(followSourceContextId='wrong'),
            lambda s:s[2]['preflightDiagnostics'].update(connectionGeneration=3),
            lambda s:s[2]['preflightDiagnostics'].update(recoveryControlVersion=6,recoveryAppliedControlVersion=6),
            lambda s:s[2]['preflightDiagnostics'].update(recoveryPhase='restoring'))
        for key in ('epoch','controlVersion','queueRevision'):
            mutations+= (lambda s,key=key:[v['contexts']['authority-context'].__setitem__(key,9) for v in (s[0],s[2])],)
        for mutate_value in mutations:
            def mutate(s,t):
                if t>=.4:mutate_value(s)
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
            self.assertEqual(clock.now,.4)

    def test_14_heartbeat_data_revision_is_not_control_identity(self):
        def mutate(s,t):
            for value in (s[0],s[2]):value['contexts']['authority-context']['version']=int(t*100)
        clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
        self.run_follow(matrix);self.assertEqual(outcomes[-1][0],'precision')

    def test_15_seek_pause_wait_or_missing_health_flag_fails(self):
        for update in ({'seekInProgress':True},{'playingIntent':False},{'seekInProgress':None},
                       {'playbackState':2,'avTimeControlStatus':1},{'playbackState':4,'playbackRate':0}):
            def mutate(s,t):
                if t>=.4:s[2]['nativePlayers'][0].update(update)
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
            self.assertEqual(clock.now,.4)

    def test_16_nominal_success_uses_exact_same_reads_and_sleeps(self):
        prior=self.setup_matrix(final=False);self.run_follow(prior[2])
        current=self.setup_matrix();self.run_follow(current[2])
        self.assertEqual([x[0] for x in prior[3]],[x[0] for x in current[3]])
        self.assertEqual(prior[0].sleeps,current[0].sleeps)
        self.assertEqual(current[-1][-1][1]['nativeSamples'],16)
        self.assertEqual(current[-1][-1][2]['precisionSamples'],16)

    def test_17_late_window_violation_cannot_be_omitted(self):
        def mutate(s,t):
            if t>=3.2:s[2]['nativePlayers'][0]['positionMs']+=60
        clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
        with self.assertRaises(AssertionError):self.run_follow(matrix)
        self.assertEqual(clock.now,3.2)
        self.assertFalse(any(row[0]=='precision' for row in outcomes))

    def test_18_uncertainty_and_fixed_fifty_policy_fail_closed(self):
        for value in (49,51,80,False,None):
            def mutate(s,t):s[2]['followSyncToleranceMs']=value
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises(AssertionError):self.run_follow(matrix)
        for value in (1,-1,False,None,float('nan')):
            def mutate(s,t):s[2]['followLeadCompensationMs']=value
            clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
            with self.assertRaises((AssertionError,TypeError)):self.run_follow(matrix)
        def mutate(s,t):
            if t>=.4:s[2]['nativePlayers'][0]['sampleUncertaintyMs']=40
        clock,ns,matrix,reads,outcomes=self.setup_matrix(mutate=mutate)
        with self.assertRaises(AssertionError):self.run_follow(matrix)
        self.assertEqual(clock.now,.4)

    def test_19_first_pair_identity_and_actual_validation_deadline(self):
        clock,ns,matrix,reads,outcomes=self.setup_matrix()
        original=matrix.outcome
        def expire(name,**metrics):
            original(name,**metrics)
            if name=='native-follow-aligned':clock.now=5
        matrix.outcome=expire
        with self.assertRaises(TimeoutError):self.run_follow(matrix)
        self.assertFalse(any(row[0]=='precision' for row in outcomes))
        clock,ns,matrix,reads,outcomes=self.setup_matrix()
        original=matrix.outcome
        def replace(name,**metrics):
            original(name,**metrics)
            if name=='native-follow-aligned':matrix.last[0]['nativePlayers'][0]['id']='replacement'
        matrix.outcome=replace
        with self.assertRaises(AssertionError):self.run_follow(matrix)

    def test_20_point_eight_and_fresh_second_invocation(self):
        for expected in (.8,1.5):
            clock,ns,matrix,reads,outcomes=self.setup_matrix(expected=expected)
            self.run_follow(matrix,expected)
            first_count=outcomes[-1][2]['precisionSamples']
            self.run_follow(matrix,expected)
            self.assertEqual(outcomes[-1][2]['precisionSamples'],first_count)
            self.assertGreaterEqual(outcomes[-1][1]['elapsedSeconds'],3)


def transition_states(at, *, complete=False, propagated=True, rate=1.5):
    values=pair(at,rate)
    target=fixture.state(at,'b');target.update(pid=102,canControl=True)
    target['nativePlayers'][0].update(positionMs=round(10000+at*rate*1000),playbackRate=rate,requestedRate=rate)
    values[1]=target
    if not complete:
        target.update(contextId='target-original',queue=['target-track'],currentIndex=0,trackId='target-track')
        target['nativePlayers'][0].update(playbackState=4,playbackRate=0,avTimeControlStatus=0,playingIntent=False)
    else:
        values[0]['nativePlayers'][0].update(playbackState=4,playbackRate=0,avTimeControlStatus=0,playingIntent=False)
        target.update(contextId='authority-context',queue=list(values[2]['queue']),currentIndex=0,trackId='fixture-a')
        canonical={'authorityClientId':target['clientId'],'authorityDeviceSessionId':target['deviceSessionId'],
                   'epoch':2,'controlVersion':5,'queueRevision':2}
        target['contexts']['authority-context']=dict(canonical)
        if propagated:values[2]['contexts']['authority-context']=dict(canonical)
        target['handoff']={'status':'completed','contextId':'authority-context',
            'sourceClientId':values[0]['clientId'],'sourceDeviceSessionId':values[0]['deviceSessionId'],
            'targetClientId':target['clientId'],'targetDeviceSessionId':target['deviceSessionId']}
    return values


class TransitionTests(PrecisionTests):
    # Inherit fixture utilities, not duplicate the20 initial-window contracts.
    def transition(self,kind='transfer'):
        clock=fixture.Clock();ns=load(clock,True);matrix=ns['Matrix']()
        before=transition_states(0,complete=kind=='rate_change')
        matrix.last=before
        ns['begin_follow_precision_transition'](matrix,before,'authority-context',kind,.8 if kind=='rate_change' else 1.5,0)
        return clock,ns,matrix

    def consume(self,clock,ns,matrix,at,**kwargs):
        clock.now=at;states=transition_states(at,**kwargs);matrix.last=states
        ns['observe_follow_precision_transition'](matrix,states)
        return states

    def test_21_old_expected_new_then_two_pairs(self):
        c,n,m=self.transition()
        self.consume(c,n,m,.1)
        self.consume(c,n,m,.2,complete=True,propagated=False)
        self.assertFalse(m.follow_precision_transition['settled'])
        self.consume(c,n,m,.4,complete=True)
        self.assertFalse(m.follow_precision_transition['settled'])
        self.consume(c,n,m,.6,complete=True)
        self.assertTrue(m.follow_precision_transition['settled'])
        self.assertEqual(m.follow_precision_transition['settledAt'],.6)

    def test_22_third_authority_and_other_follower_binding_fail(self):
        for change in ('authority','context'):
            c,n,m=self.transition();states=transition_states(.1)
            if change=='authority':states[2]['contexts']['authority-context']['authorityClientId']='third'
            else:states[2]['contextId']='another-local-task'
            with self.assertRaises(n['FollowPrecisionUnsafe']):n['observe_follow_precision_transition'](m,states)

    def test_23_completed_snapshot_must_match_owned_command(self):
        for key in ('contextId','sourceClientId','sourceDeviceSessionId','targetClientId','targetDeviceSessionId'):
            c,n,m=self.transition();states=transition_states(.1,complete=True);states[1]['handoff'][key]='wrong'
            with self.assertRaises(n['FollowPrecisionUnsafe']):n['observe_follow_precision_transition'](m,states)

    def test_24_never_propagated_and_deadline_crossing_do_not_settle(self):
        for propagated in (False,True):
            c,n,m=self.transition();self.consume(c,n,m,4.9,complete=True,propagated=propagated)
            with self.assertRaises(n['FollowPrecisionDeadline']):self.consume(c,n,m,5.0,complete=True,propagated=propagated)
            self.assertFalse(m.follow_precision_transition['settled'])

    def test_25_wait_does_not_retry_owned_transition_timeout(self):
        c,n,m=self.transition();n.update(observe_follow_wait=lambda *a:None,URLError=OSError)
        reads=[]
        def states():
            c.now=5.1;reads.append(c.now);m.last=transition_states(c.now);return m.last
        m.states=states
        with self.assertRaises(n['FollowPrecisionDeadline']):m.wait('handoff-native-completion',lambda s:False)
        self.assertEqual(len(reads),1);self.assertEqual(c.sleeps,[])

    def test_26_settled_state_does_not_rearm_on_excursion(self):
        c,n,m=self.transition();self.consume(c,n,m,.1,complete=True);self.consume(c,n,m,.3,complete=True)
        deadline=m.follow_precision_transition['deadline']
        s=transition_states(.5,complete=True);s[2]['nativePlayers'][0]['positionMs']+=60;c.now=.5
        with self.assertRaises(AssertionError):n['observe_follow_precision_transition'](m,s)
        self.assertTrue(m.follow_precision_transition['settled']);self.assertEqual(m.follow_precision_transition['deadline'],deadline)
        with self.assertRaises(AssertionError):n['begin_follow_precision_transition'](m,s,'authority-context','rate_change',.8,.5)

    def test_27_completed_control_tuple_is_fixed_not_heartbeat(self):
        c,n,m=self.transition();self.consume(c,n,m,.1,complete=True);self.consume(c,n,m,.3,complete=True)
        s=transition_states(.5,complete=True)
        for v in s[1:]:v['contexts']['authority-context']['version']=999
        c.now=.5;n['observe_follow_precision_transition'](m,s)
        for key in ('epoch','controlVersion','queueRevision'):
            s=transition_states(.7,complete=True)
            for v in s[1:]:v['contexts']['authority-context'][key]+=1
            with self.assertRaises(n['FollowPrecisionUnsafe']):n['observe_follow_precision_transition'](m,s)

    def setup_change(self,*,command_seconds=0,bad_at=None,after_change=None):
        clock=fixture.Clock();ns=load(clock,True);matrix=ns['Matrix']();outcomes=[];changed=[False]
        ns.update(observe_follow_wait=lambda *a:None,URLError=OSError)
        def read():
            states=transition_states(clock.now,complete=True,rate=.8 if changed[0] else 1.5)
            if bad_at is not None and clock.now>=bad_at:states[2]['nativePlayers'][0]['playbackRate']=.832
            if changed[0] and after_change:after_change(states,clock.now)
            matrix.last=states;return states
        matrix.states=read;matrix.last=read()
        class Client:
            def command(self,*a,**kw):clock.now=round(clock.now+command_seconds,6);changed[0]=True
        matrix.clients=[None,Client(),None]
        matrix.outcome=lambda name,**values:outcomes.append((name,values))
        return clock,ns,matrix,outcomes

    def test_28_actual_rate_change_carries_budget_through_source_window(self):
        c,n,m,out=self.setup_change(command_seconds=4.8)
        m.change_follow_rate('authority-context','fixture-a',['fixture-a','fixture-b'],0)
        self.assertGreater(c.now,10)
        source=next(v for k,v in out if k=='authority-after-follow-rate-change')
        follower=next(v for k,v in out if k=='follower-after-follow-rate-change')
        self.assertGreaterEqual(source['elapsedSeconds'],3);self.assertGreaterEqual(follower['elapsedSeconds'],3)
        self.assertIsNone(m.follow_precision_transition)

    def test_29_actual_rate_change_no_new_budget_after_overlap(self):
        c,n,m,out=self.setup_change(command_seconds=4.95)
        with self.assertRaises(n['FollowPrecisionDeadline']):m.change_follow_rate('authority-context','fixture-a',['fixture-a','fixture-b'],0)
        self.assertLess(c.now,5.2)
        self.assertFalse(any(k=='follower-after-follow-rate-change' for k,v in out))

        for wrong in (1.0,.832,.833):
            def mutation(s,t):s[2]['nativePlayers'][0].update(playbackRate=wrong,requestedRate=wrong)
            c,n,m,out=self.setup_change(after_change=mutation)
            with self.subTest(rate=wrong),self.assertRaises((AssertionError,TimeoutError)):
                m.change_follow_rate('authority-context','fixture-a',['fixture-a','fixture-b'],0)
            self.assertLessEqual(c.now,5.2)
            self.assertFalse(any(k=='follower-after-follow-rate-change' for k,v in out))

    def test_30_settled_then_reslew_during_source_window_fails(self):
        c,n,m,out=self.setup_change(bad_at=1.4)
        with self.assertRaises(AssertionError):m.change_follow_rate('authority-context','fixture-a',['fixture-a','fixture-b'],0)
        self.assertLess(c.now,2)
        self.assertFalse(any(k=='follower-after-follow-rate-change' for k,v in out))

        for key,value in (('followSourceContextId','wrong'),('queue',['other']),('trackId','other'),('currentIndex',1)):
            def mutation(s,t):s[2][key]=value
            c,n,m,out=self.setup_change(after_change=mutation)
            with self.subTest(field=key),self.assertRaises(n['FollowPrecisionUnsafe']):
                m.change_follow_rate('authority-context','fixture-a',['fixture-a','fixture-b'],0)
            self.assertFalse(out)

    def collection(self,ns):
        method=next(x for x in ast.parse(FINAL).body if isinstance(x,ast.ClassDef) and x.name=='Matrix')
        method=next(x for x in method.body if isinstance(x,ast.FunctionDef) and x.name=='run')
        block=next(x for x in method.body if isinstance(x,ast.If) and any(isinstance(y,ast.Constant) and y.value=='follower-beyond-recovery-window' for y in ast.walk(x)))
        end=next(i for i,x in enumerate(block.body) if isinstance(x,ast.Assign) and any(isinstance(y,ast.Attribute) and y.attr=='follow_precision_transition' for y in x.targets))
        f=ast.parse('def collect(self,after,context,follower_original):\n    pass').body[0];f.body=block.body[:end+1]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),'<actual-follow-35s>','exec'),ns)
        return ns['collect']

    def run_collection(self,mutate=None):
        c,n,m=self.transition();self.consume(c,n,m,.1,complete=True);after=self.consume(c,n,m,.3,complete=True)
        m.handoff_baseline={'targetClientId':after[1]['clientId'],'targetDeviceSessionId':after[1]['deviceSessionId']}
        n.update(json=__import__('json'),exact_pair=lambda a,b,c,d:bool(a and b and a==c and b==d),
            follow_timing_diagnostic=lambda a,b:{})
        def read():
            c.now=round(c.now+.01,6);states=transition_states(c.now,complete=True)
            states[2]['followHardSeekThresholdMs']=800
            if mutate:mutate(states,c.now)
            m.last=states;return states
        m.states=read
        with contextlib.redirect_stdout(io.StringIO()):
            self.collection(n)(m,after,'authority-context',after[2])
        return c,n,m

    def test_31_actual_35s_steady_coverage_uses_all_existing_samples(self):
        c,n,m=self.run_collection()
        self.assertGreaterEqual(c.now-.3,35)
        self.assertEqual(m.follow_outcomes['continuity'],'passed')
        self.assertIsNone(m.follow_first_failure)

    def test_32_actual_35s_excursion_latches_without_new_grace(self):
        def mutate(s,t):
            if 2<t<3:s[2]['nativePlayers'][0]['positionMs']+=60
        c,n,m=self.run_collection(mutate)
        self.assertEqual(m.follow_first_failure['condition'],'steady_sample_precision')
        self.assertEqual(m.follow_outcomes['continuity'],'failed')
        self.assertGreaterEqual(c.now-.3,35)

    def test_33_actual_35s_identity_change_stops_dependent_collection(self):
        def mutate(s,t):
            if t>2:s[2]['nativePlayers'][0]['id']='replacement'
        with self.assertRaises(AssertionError):self.run_collection(mutate)

    def test_34_duplicate_tuple_and_late_entry_cannot_invent_proof(self):
        c,n,m=self.transition();s=self.consume(c,n,m,4.8,complete=True)
        n['observe_follow_precision_transition'](m,s)
        self.assertFalse(m.follow_precision_transition['settled'])
        with self.assertRaises(n['FollowPrecisionDeadline']):self.consume(c,n,m,5.1,complete=True)

        # A completed witness cannot become a fresh window after output stalls.
        c,n,m=self.transition();self.consume(c,n,m,.1,complete=True);self.consume(c,n,m,.3,complete=True)
        c.now=.501
        with self.assertRaises(AssertionError):
            m.rate(2,1.5,'stale',follow_context='authority-context',authority_index=1)
        self.assertEqual(c.now,.501)
        # Even the first sample cannot claim success after a slow read crosses
        # the unchanged five-second measurement timeout.
        c,n,m,reads,outcomes=self.setup_matrix()
        original_read=m.states
        def slow():
            if c.now>.3:c.now+=6
            return original_read()
        m.states=slow
        with self.assertRaises(TimeoutError):self.run_follow(m)
        self.assertFalse(any(name=='precision' for name,_,_ in outcomes))

    def test_35_completed_transfer_witness_survives_only_valid_later_samples(self):
        c,n,m=self.transition();self.consume(c,n,m,4.7,complete=True);self.consume(c,n,m,4.9,complete=True)
        self.consume(c,n,m,8.2,complete=True)
        self.assertEqual(m.follow_precision_transition['settledAt'],4.9)
        self.assertEqual(m.follow_precision_transition['deadline'],5)
        s=transition_states(8.4,complete=True);s[2]['nativePlayers'][0]['requestedRate']=1.56;c.now=8.4
        with self.assertRaises(AssertionError):n['observe_follow_precision_transition'](m,s)


TEST_NAMES=tuple(sorted([name for name in PrecisionTests.__dict__ if name.startswith('test_')] +
                        [name for name in TransitionTests.__dict__ if name.startswith('test_')]))

def suite(prior,final):
    global PRIOR,FINAL
    PRIOR,FINAL=prior,final
    return unittest.TestSuite([PrecisionTests(name) for name in TEST_NAMES if name in PrecisionTests.__dict__] +
        [TransitionTests(name) for name in TEST_NAMES if name in TransitionTests.__dict__])
