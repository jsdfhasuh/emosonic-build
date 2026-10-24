"""Finite budget-only contracts; synthetic fixtures, no private source content."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import current_native_check as public
import native_follow_readiness as r
import native_seek_anchor_observation as timing
spec=importlib.util.spec_from_file_location('ten_budget_compat',r.ROOT/'native_follow_readiness_payload/legacy_precision_contract.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class TenSecondConvergenceTests(unittest.TestCase):
    def test_exact_manifest_and_only_follow_deadlines_change(self):
        manifest=r.expected_manifest()
        self.assertEqual(manifest['externalFollowConvergenceBudgetMs'],10000)
        self.assertEqual(manifest['strictMeasurementTimeoutMs'],5000)
        self.assertTrue(manifest['productRecoveryBudgetUnchanged'])
        operations=r.convergence_operations()
        text='\n'.join(new for _,new in operations)
        self.assertIn('10 if follow_context is not None else 5',text)
        self.assertNotIn('measurement_started + 10',text)
        for token in ('.states(','.command(','.sleep(','.wait('):
            self.assertEqual(sum(old.count(token) for old,_ in operations),sum(new.count(token) for _,new in operations))
        self.assertIn('deadline = measurement_started + 5', '\n'.join(new for _,new in r.precision_transition_operations()))

    def test_finite_elapsed_exports_roundtrip_and_unknown_is_not_internal_success(self):
        measurement={'convergenceKind':'transfer','convergenceOrigin':'before_transfer_command',
            'convergenceState':'sampled_steady','convergenceBudgetMs':10000,
            'convergenceElapsedMs':6200,'physicalConvergenceMs':6100,
            'internalRecoveryOutcome':'unknown','initialFollowCommandToConvergenceOriginMs':600,
            'initialFollowCommandToObservationMs':6800}
        value={'stage':'follower-avplayer-rate-1.5','status':'passed','rateMeasurement':measurement,
            'followObservation':{'precision':measurement}}
        self.assertEqual(public.report_line(json.dumps(value)),value)
        bad=copy.deepcopy(value);bad['rateMeasurement'].update(internalRecoveryOutcome='settled',
            convergenceElapsedMs=float('nan'),convergenceKind='private',privateOwner='secret')
        result=public.report_line(json.dumps(bad))['rateMeasurement']
        for key in ('internalRecoveryOutcome','convergenceElapsedMs','convergenceKind','privateOwner'):self.assertNotIn(key,result)

    def test_relative_export_is_read_free_and_preserves_independent_evidence(self):
        tree=ast.parse(r.payload('follow_precision_helpers.py'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='follow_convergence_observation')
        calls=[ast.unparse(n.func) for n in ast.walk(function) if isinstance(n,ast.Call)]
        for token in ('time.monotonic','matrix.states','decoded','open'):self.assertNotIn(token,calls)
        ns={};exec(compile(ast.Module(body=[function],type_ignores=[]),'<synthetic-relative-export>','exec'),ns)
        matrix=SimpleNamespace(rate_measurement={},follow_observation={'independent':'retained'},
            follow_precision_transition={'kind':'transfer','measurement':{}})
        result=ns['follow_convergence_observation'](matrix,'transfer',10200,None)
        self.assertEqual(result['convergenceElapsedMs'],10200)
        self.assertEqual(result['convergenceState'],'pending')
        self.assertEqual(result['internalRecoveryOutcome'],'unknown')
        self.assertNotIn('physicalConvergenceMs',result)
        self.assertEqual(matrix.follow_observation['independent'],'retained')
        self.assertEqual(matrix.follow_observation['precision'],result)

    def synthetic(self):
        before=b"class Case:\n    def test_limit(self):\n        self.assertLess(0, 5.25)\n"
        after=before.replace(b'5.25',b'10.25')
        method=lambda data:ast.parse(data).body[0].body[0]
        row={'ordinal':13,'caseSha256':u.digest(b'test_synthetic.Case.test_limit'),
            'beforeAstSha256':u.digest(ast.dump(method(before),include_attributes=False).encode()),
            'afterAstSha256':u.digest(ast.dump(method(after),include_attributes=False).encode()),
            'literals':[{'before':5.25,'after':10.25,'count':1}]}
        return before,after,{'externalBudgetAdaptations':{'test_synthetic.py':[row]}}

    def test_isolated_legacy_literal_adapter_exact_inverse(self):
        before,after,contract=self.synthetic()
        self.assertEqual(u.adapt_budget_fixture(before,'test_synthetic.py',contract),after)
        self.assertEqual(u.adapt_budget_fixture(after,'test_synthetic.py',contract,inverse=True),before)
        self.assertEqual(u.adapt_budget_fixture(before,'unrelated.py',contract),before)

    def test_legacy_wrong_case_ast_or_literal_count_fail_closed(self):
        before,after,contract=self.synthetic()
        for field,value in (('caseSha256','0'*64),('beforeAstSha256','0'*64),('afterAstSha256','0'*64)):
            bad=copy.deepcopy(contract);bad['externalBudgetAdaptations']['test_synthetic.py'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):u.adapt_budget_fixture(before,'test_synthetic.py',bad)
        bad=copy.deepcopy(contract);bad['externalBudgetAdaptations']['test_synthetic.py'][0]['literals'][0]['count']=2
        with self.assertRaises(AssertionError):u.adapt_budget_fixture(before,'test_synthetic.py',bad)
        with self.assertRaises(AssertionError):u.adapt_budget_fixture(before.replace(b'0,',b'1,'),'test_synthetic.py',contract)

    def test_legacy_all_cases_retained_and_adaptation_exactly_three(self):
        contract=u.inventory()
        self.assertEqual([row['ordinal'] for row in contract['cases'] if row.get('externalBudgetAdapted')],[13,17,25])
        self.assertEqual(contract['priorCount'],70);self.assertEqual(contract['finalCompatibleCount'],63)
        self.assertEqual(contract['finalPrecisionCount'],46);self.assertEqual(contract['mappedPrecisionPrefixCount'],35)
        self.assertEqual(set(contract['finalBudgetTestFiles']),set(contract['externalBudgetAdaptations']))
        self.assertEqual(sum(len(rows) for rows in contract['externalBudgetAdaptations'].values()),3)

    def test_clock_history_remaining_budget_crosses_old_boundary_without_reset(self):
        native={'sampledAtMs':1000000,'positionMs':10000,'playbackRate':1.5,'requestedRate':1.5}
        for elapsed,remaining in ((0,10000),(5001,4999),(9999,1),(10000,0),(10200,0)):
            record=timing.clock_history(None,{},native,elapsed,None)['records'][0]
            self.assertEqual(record['readinessElapsedMs'],elapsed)
            self.assertEqual(record['remainingReadinessBudgetMs'],remaining)

    def test_poll_ceiling_comes_from_budget_and_existing_cadence(self):
        import math
        self.assertEqual(math.ceil(10/.2)+1,51)
        self.assertEqual(public.RATE_SCHEMA['correctionReadinessPollCount'],('integer',0,51))
        self.assertEqual(public.RATE_SCHEMA['correctionReadinessElapsedMs'],('number',0,10000))
        self.assertEqual(r.PRECISION_CHECKS,46)

if __name__=='__main__':unittest.main()
