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
    def test_original_thirty_five_method_bodies_are_unchanged(self):
        tree=ast.parse(r.payload('precision_contract.py'))
        methods={n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
        old={k:v for k,v in methods.items() if int(k.split('_')[1])<=35}
        self.assertEqual(len(old),35);self.assertEqual(len(methods),40)
        self.assertEqual(hashlib.sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest(), '14464687f2df6bfb9d84e27431e3616486e78b2398bbd52b71a150c6cc7f0897')

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
            and n.name.startswith('test_') and int(n.name.split('_')[1])>35)
        self.assertEqual([int(n.split('_')[1]) for n in names],[36,37,38,39,40])
        self.assertEqual(r.PRECISION_CHECKS,40)

if __name__=='__main__':unittest.main()
