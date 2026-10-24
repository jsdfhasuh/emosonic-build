"""Public fixture/inverse scope for owned provisional transfer admission only."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_follow_readiness as r

class OwnedProvisionalTransferTests(unittest.TestCase):
    def test_only_explicit_deadline_fixture_adaptations_to_original_forty(self):
        tree=ast.parse(r.payload('precision_contract.py'))
        methods={n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
        adapted=('test_01_prior_accepts_correction_but_final_requires_nominal', 'test_03_one_nominal_sample_before_deadline_is_not_enough', 'test_04_states_call_crossing_original_deadline_fails', 'test_05_requested_and_property_rates_both_must_be_nominal', 'test_07_conservative_rounding_bound_at_both_rates', 'test_19_first_pair_identity_and_actual_validation_deadline', 'test_24_never_propagated_and_deadline_crossing_do_not_settle', 'test_25_wait_does_not_retry_owned_transition_timeout', 'test_29_actual_rate_change_no_new_budget_after_overlap', 'test_34_duplicate_tuple_and_late_entry_cannot_invent_proof', 'test_35_completed_transfer_witness_survives_only_valid_later_samples', 'test_36_owned_empty_target_and_full_protocol_pending_sequence', 'test_39_owned_pending_wait_expires_at_original_command_deadline', 'test_40_pending_completion_cannot_skip_final_nominal_progress_or_expiry')
        unchanged={k:v for k,v in methods.items() if int(k.split('_')[1])<=40 and k not in adapted}
        self.assertEqual(len(methods),46)
        self.assertEqual(len(unchanged),26)
        self.assertEqual(hashlib.sha256(json.dumps(unchanged,sort_keys=True,separators=(',',':')).encode()).hexdigest(), '2e1c54730c69e80edfed3efac602a3398a13450879ac78e77b89b3670ab35e91')
        expected={'test_01_prior_accepts_correction_but_final_requires_nominal': '1aa3ca3da9629a1e5f4fdf58df498ac33a73f6ff35a471fb5a2d4aeb5c97f3fb', 'test_03_one_nominal_sample_before_deadline_is_not_enough': 'cef9cfdb188b77d9e884813b4e63167567f48c1ee5a6eda74653a57b60d5f012', 'test_04_states_call_crossing_original_deadline_fails': '838e62d2a643346eadecadea0aa193490f9557d768f4a4199307e21ac5920ad1', 'test_05_requested_and_property_rates_both_must_be_nominal': 'c2be99d399d7c35509c6ff514a451dec88054cfc1be6ba0ab2375e63e44347e1', 'test_07_conservative_rounding_bound_at_both_rates': 'f10cf22ce74c93b3d51bec0c66075d4585c6287ba6c04225a650e7ff9d359e7b', 'test_19_first_pair_identity_and_actual_validation_deadline': '080082650d9cbd45e719ff04c4ceecb7c7f81422b8b2698db7719dddc7753ef8', 'test_24_never_propagated_and_deadline_crossing_do_not_settle': '2c05bbf81961a3509f474a9a79e440ef02f4611e4f86073c1b2363a9e7dc12d3', 'test_25_wait_does_not_retry_owned_transition_timeout': '9051dea85c096115d9e294d93e8f4da2c7e5ec6e543457ad8f49b5c61bac4a52', 'test_29_actual_rate_change_no_new_budget_after_overlap': '0d0d4964e388bb254be771bbb89dc7f17e8fb6c4721bbff6caa714400b82be1e', 'test_34_duplicate_tuple_and_late_entry_cannot_invent_proof': '90d9933bc9596028c8c255ac20b11a85eb544aea1e7a6b8c88c297da28a9bf9c', 'test_35_completed_transfer_witness_survives_only_valid_later_samples': '989fa2ed98522e8b7171197cada98a4859f7bdf81205551087db54759e136a2f', 'test_36_owned_empty_target_and_full_protocol_pending_sequence': '4587ce5a75e46b78871a5503a305d2fe7ba8743ebdd81c937bec43c8f976159d', 'test_39_owned_pending_wait_expires_at_original_command_deadline': '4abba4d2d6330e52e56e1b9b9a024cd2c3fe63bce0c515300078d78a92e59840', 'test_40_pending_completion_cannot_skip_final_nominal_progress_or_expiry': '701586f315ea1d7f3a826f5a06af56de6de8604aafb25abac5bc75bb865b16e9'}
        self.assertEqual({k:hashlib.sha256(methods[k].encode()).hexdigest() for k in adapted},expected)

    def test_owned_command_response_is_reused_without_another_call(self):
        operations=r.precision_operations()
        capturing=[(a,b) for a,b in operations if "_handoff_response = a.command('handoff'" in b]
        self.assertEqual(len(capturing),1)
        self.assertEqual(capturing[0][0].count("a.command('handoff'"),1)
        self.assertEqual(capturing[0][1].count("a.command('handoff'"),1)
        pinning=[(a,b) for a,b in operations if 'pin_follow_transfer_command(self, _handoff_response)' in b]
        self.assertEqual(len(pinning),1)
        self.assertNotIn('.command(',pinning[0][1]);self.assertNotIn('.states(',pinning[0][1])

    def test_pending_branch_cannot_settle_and_keeps_deadline_first(self):
        tree=ast.parse(r.payload('follow_precision_helpers.py'))
        observer=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='observe_follow_precision_transition')
        branches=[n for n in observer.body if isinstance(n,ast.If)]
        pending=next(n for n in branches if ast.unparse(n.test)=='pending_target')
        deadline=next(n for n in branches if "transition['deadline']" in ast.unparse(n.test))
        self.assertLess(observer.body.index(deadline),observer.body.index(pending))
        self.assertEqual(ast.unparse(pending.body[0]),"transition['candidate'] = None")
        self.assertIsInstance(pending.body[-1],ast.Return)
        self.assertNotIn("['settled'] = True",ast.unparse(pending))

    def test_only_five_new_fixed_contract_methods(self):
        tree=ast.parse(r.payload('precision_contract.py'))
        names=sorted(n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
            and n.name.startswith('test_') and 35<int(n.name.split('_')[1])<=40)
        self.assertEqual([int(n.split('_')[1]) for n in names],[36,37,38,39,40])
        self.assertEqual(r.PRECISION_CHECKS,46)

if __name__=='__main__':unittest.main()
