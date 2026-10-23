import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import authority_rate_feedback_green as c


def suites(counts, prefix):
    return [dict(path='test/services/%s_%d_test.dart' % (prefix, i),
                 names=['synthetic_%d_%d' % (i,j) for j in range(n)]) for i,n in enumerate(counts)]


class RateFeedbackGreenTests(unittest.TestCase):
    def pins(self):
        return patch.multiple(c,SOURCE_SHA='a'*40,SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_SHA256='b'*64,EXPECTED_COUNTS=(3,4),
            REQUEST=dict(c.REQUEST,source_sha='a'*40,source_ref='refs/heads/fix/synthetic'))

    def prior(self):
        return suites((15,3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,3,4,4,3,5),'prior')

    def test_pending_invalid_inconsistent_pins_fail_before_delegation(self):
        for field,value in [('SOURCE_SHA','PENDING'),('SOURCE_REF','PENDING'),
                            ('INVENTORY_SHA256','PENDING'),('EXPECTED_COUNTS',(3,None)),
                            ('EXPECTED_COUNTS',(3,True)),('EXPECTED_COUNTS',(4,4)),
                            ('EXPECTED_COUNTS',(3,)),('EXPECTED_COUNTS',(3,0)),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.pins(),patch.object(c,field,value),patch.object(c.previous,'main') as call,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);call.assert_not_called()

    def test_all220_retained_then_both_exact_new_suites(self):
        prior=self.prior();extra=suites((3,4),'extra');before=json.dumps(prior)
        with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=prior),patch.object(c.TIMING,'component_inventory',return_value=extra) as load:
            actual=c.inventory(Path('/synthetic'));load.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(3,4))
        self.assertEqual(actual,prior+extra);self.assertEqual(len(actual),27)
        self.assertEqual(sum(len(s['names']) for s in actual),227);self.assertEqual(json.dumps(prior),before)

    def test_missing_changed_duplicate_cases_fail(self):
        for prior,extra in [(self.prior()[:-1],suites((3,4),'extra')),
                            (self.prior(),suites((3,3),'extra')),
                            (self.prior(),suites((7,),'extra')),
                            (self.prior(),suites((3,4),'prior'))]:
            with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=prior),patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_manifest_failure_remains_fatal(self):
        with self.pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=self.prior()),patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_complete_delegation_and_restoration_after_exception(self):
        lowest=c.TIMING.previous.recovery
        original=(lowest.SOURCE_SHA,lowest.inventory,c.previous.SOURCE_SHA,c.previous.inventory)
        for fails in (False,True):
            def observe():
                self.assertEqual(lowest.SOURCE_SHA,c.SOURCE_SHA)
                self.assertEqual(lowest.REQUEST,c.REQUEST)
                self.assertIs(lowest.inventory,c.inventory)
                if fails:raise RuntimeError('synthetic')
                return 7
            with self.pins(),patch.object(lowest,'main',side_effect=observe):
                if fails:
                    with self.assertRaises(RuntimeError):c.main()
                else:self.assertEqual(c.main(),7)
            self.assertEqual((lowest.SOURCE_SHA,lowest.inventory,c.previous.SOURCE_SHA,c.previous.inventory),original)

    def test_workflow_preserves_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1];w=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,w)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup','persist-credentials: false'):self.assertIn(value,w)
        for value in ('upload-artifact','source native','source package','source publish','contents: write','workflow_dispatch'):self.assertNotIn(value,w)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertEqual(c.REQUEST['attempt'],78)
        self.assertLess(w.index('source focused'),w.index('source validate_source'))


if __name__=='__main__':unittest.main()
