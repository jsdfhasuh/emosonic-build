import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_broadcast_compat_green as c


def suites(counts, prefix):
    return [dict(path='test/services/%s_%d_test.dart' % (prefix, i),
                 names=['synthetic_%d_%d' % (i, j) for j in range(n)]) for i, n in enumerate(counts)]


class BroadcastCompatibilityTests(unittest.TestCase):
    def pins(self):
        return patch.multiple(c, SOURCE_SHA='a'*40, SOURCE_REF='refs/heads/test/synthetic',
            INVENTORY_PATH='tool/synthetic/inventory.json', INVENTORY_SHA256='b'*64,
            EXPECTED_COUNTS=(5,), REQUEST=dict(c.REQUEST, source_sha='a'*40, source_ref='refs/heads/test/synthetic'))

    def prior(self):
        return suites((3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,3,4,4), 'prior')

    def test_pending_invalid_and_inconsistent_pins_fail_closed(self):
        for field, value in [('SOURCE_SHA','PENDING'),('SOURCE_REF','PENDING'),
                             ('INVENTORY_PATH','../private'),('INVENTORY_SHA256','PENDING'),
                             ('EXPECTED_COUNTS',(None,)),('EXPECTED_COUNTS',(True,)),
                             ('EXPECTED_COUNTS',(0,)),('EXPECTED_COUNTS',(5,1)),
                             ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.pins(), patch.object(c,field,value), patch.object(c.previous,'main') as call, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1); call.assert_not_called()

    def test_targeted_first_and_all_prior_cases_preserved(self):
        target=suites((5,), 'target'); prior=self.prior(); before=json.dumps(prior)
        with self.pins(), patch.object(c.TIMING,'component_inventory',return_value=target) as loader, patch.object(c,'ORIGINAL_INVENTORY',return_value=prior):
            actual=c.inventory(Path('/synthetic'))
            loader.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(5,))
        self.assertEqual(actual,target+prior); self.assertEqual(len(actual),23)
        self.assertEqual(sum(len(s['names']) for s in actual),202)
        self.assertEqual(json.dumps(prior),before)

    def test_wrong_target_count_missing_prior_and_overlap_fail(self):
        for target, prior in [(suites((4,),'target'),self.prior()),
                              (suites((5,),'target'),self.prior()[:-1]),
                              (suites((5,),'prior'),self.prior())]:
            with self.pins(), patch.object(c.TIMING,'component_inventory',return_value=target), patch.object(c,'ORIGINAL_INVENTORY',return_value=prior):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_manifest_failure_propagates_without_prior_execution(self):
        with self.pins(), patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')), patch.object(c,'ORIGINAL_INVENTORY') as prior:
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
            prior.assert_not_called()

    def test_delegation_restores_all_existing_layers_on_error(self):
        downstream=c.previous.previous.CLOCK.previous
        original=(downstream.SOURCE_SHA,downstream.inventory,c.previous.SOURCE_SHA,c.previous.inventory)
        for fails in (False,True):
            def observe():
                self.assertEqual(downstream.SOURCE_SHA,c.SOURCE_SHA)
                self.assertEqual(downstream.REQUEST,c.REQUEST)
                self.assertIs(downstream.inventory,c.inventory)
                if fails:raise RuntimeError('synthetic')
                return 7
            with self.pins(),patch.object(downstream,'main',side_effect=observe):
                if fails:
                    with self.assertRaises(RuntimeError):c.main()
                else:self.assertEqual(c.main(),7)
            self.assertEqual((downstream.SOURCE_SHA,downstream.inventory,c.previous.SOURCE_SHA,c.previous.inventory),original)

    def test_workflow_retains_fatal_full_validation_and_always_cleanup(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,workflow)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup','persist-credentials: false'):self.assertIn(value,workflow)
        for value in ('upload-artifact','source native','source package','source publish','contents: write','workflow_dispatch'):self.assertNotIn(value,workflow)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertEqual(c.REQUEST['attempt'],71)
        self.assertLess(workflow.index('source focused'),workflow.index('source validate_source'))


if __name__=='__main__':unittest.main()
