"""Synthetic public fixtures only; the private test inventory stays private."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import follow_ordinary_slew_green as c


def suites(counts,prefix='prior'):
    return [dict(path='test/services/%s_%d_test.dart'%(prefix,i),
                 names=['synthetic_%d_%d'%(i,j) for j in range(n)]) for i,n in enumerate(counts)]


class OrdinarySlewGreenTests(unittest.TestCase):
    def reviewed_pins(self):
        return patch.multiple(c,SOURCE_SHA='a'*40,SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_SHA256='b'*64,EXPECTED_COUNTS=(4,3),
            REQUEST=dict(c.REQUEST,source_sha='a'*40,source_ref='refs/heads/fix/synthetic'))

    def original(self):
        return suites((3,45,13,6,3,34,18,17,7,2,3,1,4,6,6,7,3,4,4,3))

    def test_pending_or_inconsistent_pins_block_before_delegation(self):
        for field,value in [('SOURCE_SHA','PENDING'),('SOURCE_SHA','0'*39),('INVENTORY_SHA256','PENDING'),
                            ('SOURCE_REF','PENDING'),('EXPECTED_COUNTS',(4,None)),
                            ('EXPECTED_COUNTS',(4,True)),('EXPECTED_COUNTS',(3,4)),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.reviewed_pins(),patch.object(c,field,value),patch.object(c.previous,'main') as previous,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);previous.assert_not_called()

    def test_complete_delegation_preserves_natural_legacy_and_clock_overrides(self):
        downstream=c.previous.CLOCK.previous
        old=(c.previous.SOURCE_SHA,c.previous.inventory,downstream.SOURCE_SHA,downstream.inventory,
             c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.previous.restore.COMPONENTS)
        for raises in (False,True):
            def observe():
                self.assertEqual(downstream.SOURCE_SHA,c.SOURCE_SHA)
                self.assertEqual(downstream.REQUEST,c.REQUEST)
                self.assertIs(downstream.inventory,c.inventory)
                self.assertEqual(c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.previous.CLOCK.RECOVERY_DIGEST)
                self.assertEqual(c.previous.POST_RESTORE_DIGEST,'263dbe2a40cfd6f723f689fe71061cfdb44ac3920b31db50d216adb25cdc42e6')
                self.assertEqual(c.previous.restore.COMPONENTS,((c.previous.POST_RESTORE_PATH,c.previous.POST_RESTORE_DIGEST,(4,6)),))
                if raises:raise RuntimeError('synthetic')
                return 7
            with self.reviewed_pins(),patch.object(downstream,'main',side_effect=observe):
                if raises:
                    with self.assertRaises(RuntimeError):c.main()
                else:self.assertEqual(c.main(),7)
            self.assertEqual((c.previous.SOURCE_SHA,c.previous.inventory,downstream.SOURCE_SHA,downstream.inventory,
                             c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.previous.restore.COMPONENTS),old)

    def test_original189_then_frozen_baseline_and_boundary_cases_remain_ordered(self):
        original=self.original();additional=suites((4,3),'ordinary');snapshot=json.dumps(original)
        with self.reviewed_pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=original) as prior,patch.object(c.TIMING,'component_inventory',return_value=additional) as extra:
            actual=c.inventory(Path('/synthetic'))
        prior.assert_called_once_with(Path('/synthetic'))
        extra.assert_called_once_with(Path('/synthetic'),c.INVENTORY_PATH,'b'*64,(4,3))
        self.assertEqual(actual[:20],original);self.assertEqual(actual[20:],additional)
        self.assertEqual(len(actual),22);self.assertEqual(sum(len(x['names']) for x in actual),196)
        self.assertEqual(json.dumps(original),snapshot)

    def test_missing_or_duplicate_prior_suite_blocks_new_inventory_loader(self):
        original=self.original();missing_case=self.original();missing_case[-1]['names'].pop()
        for invalid in (original[:-1],original+[original[0]],suites((189,)),missing_case):
            with self.reviewed_pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=invalid),patch.object(c.TIMING,'component_inventory') as extra:
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
                extra.assert_not_called()

    def test_wrong_component_counts_and_duplicate_paths_refused(self):
        for extra in (suites((3,4),'extra'),suites((4,2),'extra'),suites((7,),'extra'),suites((4,3),'prior')):
            with self.reviewed_pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=self.original()),patch.object(c.TIMING,'component_inventory',return_value=extra):
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_frozen_inventory_validation_error_propagates(self):
        with self.reviewed_pins(),patch.object(c,'ORIGINAL_INVENTORY',return_value=self.original()),patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('changed fixture')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_exact_workflow_request_retains_full_acceptance_and_cleanup(self):
        root=Path(__file__).resolve().parents[1];workflow=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,workflow)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup','persist-credentials: false'):self.assertIn(value,workflow)
        for forbidden in ('upload-artifact','source native','source package','source publish','contents: write','workflow_dispatch'):self.assertNotIn(forbidden,workflow)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertEqual(c.REQUEST['attempt'],70)
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_smooth_magnitude/green_inventory.json')
        self.assertLess(workflow.index('source focused'),workflow.index('source validate_source'))


if __name__=='__main__':unittest.main()
