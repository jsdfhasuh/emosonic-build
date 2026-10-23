"""Public synthetic inventories only; no private fixture names or source."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import follow_directional_settle_green as c


def suites(counts,prefix='prior'):
    return [dict(path='test/services/%s_%d_test.dart'%(prefix,i),
                 names=['synthetic_%d_%d'%(i,j) for j in range(n)]) for i,n in enumerate(counts)]


class DirectionalSettleGreenTests(unittest.TestCase):
    def reviewed_pins(self):
        return patch.multiple(c,SOURCE_SHA='a'*40,SOURCE_REF='refs/heads/fix/synthetic',
            INVENTORY_SHA256='b'*64,POST_RESTORE_DIGEST='d'*64,
            REQUEST=dict(c.REQUEST,source_sha='a'*40,source_ref='refs/heads/fix/synthetic'))

    def prior(self):
        return suites((3,45,13,6,3,34,18,17,7,2,3,1,4,6))

    def scoped(self):
        return patch.object(c.restore,'COMPONENTS',((c.POST_RESTORE_PATH,'d'*64,(4,6)),))

    def test_pending_or_inconsistent_pins_block_before_any_delegation(self):
        for field,value in [('SOURCE_SHA','PENDING'),('SOURCE_SHA','0'*39),('INVENTORY_SHA256','PENDING'),
                            ('SOURCE_REF','PENDING'),('POST_RESTORE_DIGEST','PENDING'),
                            ('EXPECTED_COUNTS',(4,None)),('EXPECTED_COUNTS',(4,True)),('EXPECTED_COUNTS',(4,4)),
                            ('REQUEST',dict(c.REQUEST,source_sha='c'*40))]:
            with self.reviewed_pins(),patch.object(c,field,value),patch.object(c.previous,'main') as delegate,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);delegate.assert_not_called()

    def test_exact_delegation_preserves_clock_recovery_and_restores_all_globals(self):
        downstream=c.CLOCK.previous
        old=(c.previous.SOURCE_SHA,c.previous.inventory,downstream.SOURCE_SHA,downstream.inventory,
             c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.restore.COMPONENTS)
        for raises in (False,True):
            def observe():
                self.assertEqual(downstream.SOURCE_SHA,c.SOURCE_SHA)
                self.assertEqual(downstream.REQUEST,c.REQUEST)
                self.assertIs(downstream.inventory,c.inventory)
                self.assertEqual(c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.CLOCK.RECOVERY_DIGEST)
                self.assertEqual(c.restore.COMPONENTS,((c.POST_RESTORE_PATH,'d'*64,(4,6)),))
                if raises:raise RuntimeError('synthetic')
                return 7
            with self.reviewed_pins(),patch.object(downstream,'main',side_effect=observe):
                if raises:
                    with self.assertRaises(RuntimeError):c.main()
                else:self.assertEqual(c.main(),7)
            self.assertEqual((c.previous.SOURCE_SHA,c.previous.inventory,downstream.SOURCE_SHA,downstream.inventory,
                c.TIMING.previous.RECOVERY_INVENTORY_SHA256,c.restore.COMPONENTS),old)

    def test_only_exact_legacy_path_base_digest_and_integer_counts_are_admitted(self):
        exact=(c.POST_RESTORE_PATH,c.POST_RESTORE_BASE_DIGEST,(4,5))
        invalid=[(),(exact,exact),[exact],(('tool/other/fixed_green_inventory.json',exact[1],exact[2]),),
                 ((exact[0],'0'*64,exact[2]),),((exact[0],exact[1],(5,4)),),
                 ((exact[0],exact[1],(4,6)),),((exact[0],exact[1],(4.0,5)),),
                 ((exact[0],exact[1],[4,5]),)]
        for value in invalid:
            with self.reviewed_pins(),patch.object(c.restore,'COMPONENTS',value),patch.object(c.previous,'main') as delegate,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(c.main(),1);delegate.assert_not_called()
        with self.reviewed_pins():
            self.assertEqual(c.reviewed_restore_components(),((exact[0],'d'*64,(4,6)),))

    def test_original_post_restore_loader_retains_152_then_exact_four_and_six(self):
        prior=suites((3,45,13,6,3,34,18,17,7,2,3,1));additional=suites((4,6),'restore')
        with self.reviewed_pins(),self.scoped(),patch.object(c.restore,'ORIGINAL_INVENTORY',return_value=prior),patch.object(c.restore.previous,'component_inventory',return_value=additional) as loader:
            actual=c.BASE_INVENTORY(Path('/synthetic'))
        self.assertEqual(len(actual),14);self.assertEqual(sum(len(x['names']) for x in actual),162)
        loader.assert_called_once_with(Path('/synthetic'),c.POST_RESTORE_PATH,'d'*64,(4,6))

    def test_exact_162_175_182_189_order_digests_and_prior_names_preserved(self):
        original=self.prior();snapshot=json.dumps(original);source=Path('/synthetic')
        additions=[suites((6,7),'interval'),suites((3,4),'admission'),suites((4,3),'directional')]
        old=c.TIMING.COMPONENTS
        def prior_loader(root):
            self.assertEqual(root,source)
            expected=tuple((p,c.CLOCK.CLOCK_DIGEST if p==c.CLOCK.CLOCK_PATH else d,n) for p,d,n in old)
            self.assertEqual(c.TIMING.COMPONENTS,expected)
            return original
        with self.reviewed_pins(),self.scoped(),patch.object(c,'BASE_INVENTORY',side_effect=prior_loader),patch.object(c.TIMING,'component_inventory',side_effect=additions) as extra:
            actual=c.inventory(source)
        self.assertEqual(actual,original+sum(additions,[]));self.assertEqual(json.dumps(original),snapshot)
        self.assertEqual(sum(len(s['names']) for s in actual),189)
        self.assertEqual([call.args for call in extra.call_args_list],[
            (source,c.CLOCK.INTERVAL_PATH,c.CLOCK.INTERVAL_DIGEST,(6,7)),
            (source,c.previous.INVENTORY_PATH,c.previous.INVENTORY_SHA256,(3,4)),
            (source,c.INVENTORY_PATH,'b'*64,(4,3))])
        self.assertIs(c.TIMING.COMPONENTS,old)

    def test_missing_prior_case_or_duplicate_path_blocks_new_loaders(self):
        original=self.prior()
        invalid=[original[:-1],original+[original[0]],suites((162,))]
        lost=self.prior();lost[-1]['names'].pop();invalid.append(lost)
        for value in invalid:
            with self.reviewed_pins(),self.scoped(),patch.object(c,'BASE_INVENTORY',return_value=value),patch.object(c.TIMING,'component_inventory') as loader:
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
                loader.assert_not_called()

    def test_each_exact_component_count_and_cross_component_uniqueness_required(self):
        for ordinal in range(3):
            for mode in ('count','duplicate'):
                additions=[suites((6,7),'interval'),suites((3,4),'admission'),suites((4,3),'directional')]
                if mode=='count':additions[ordinal][0]['names'].pop()
                else:additions[ordinal][0]['path']=self.prior()[0]['path']
                with self.reviewed_pins(),self.scoped(),patch.object(c,'BASE_INVENTORY',return_value=self.prior()),patch.object(c.TIMING,'component_inventory',side_effect=additions):
                    with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_clock_component_missing_or_duplicated_refused_before_base_loader(self):
        original=c.TIMING.COMPONENTS
        for value in (tuple(v for v in original if v[0]!=c.CLOCK.CLOCK_PATH),original+tuple(v for v in original if v[0]==c.CLOCK.CLOCK_PATH)):
            with self.reviewed_pins(),self.scoped(),patch.object(c.TIMING,'COMPONENTS',value),patch.object(c,'BASE_INVENTORY') as base:
                with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))
                base.assert_not_called()

    def test_base_exception_restores_clock_override_and_component_errors_propagate(self):
        original=c.TIMING.COMPONENTS
        with self.reviewed_pins(),self.scoped(),patch.object(c,'BASE_INVENTORY',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):c.inventory(Path('/synthetic'))
        self.assertIs(c.TIMING.COMPONENTS,original)
        with self.reviewed_pins(),self.scoped(),patch.object(c,'BASE_INVENTORY',return_value=self.prior()),patch.object(c.TIMING,'component_inventory',side_effect=c.TIMING.previous.recovery.request.p.GateError('synthetic')):
            with self.assertRaises(c.TIMING.previous.recovery.request.p.GateError):c.inventory(Path('/synthetic'))

    def test_readonly_workflow_retains_complete_validation_and_cleanup(self):
        root=Path(__file__).resolve().parents[1];workflow=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH):self.assertIn(value,workflow)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup','persist-credentials: false'):self.assertIn(value,workflow)
        for forbidden in ('upload-artifact','source native','source package','source publish','contents: write','workflow_dispatch'):self.assertNotIn(forbidden,workflow)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
        self.assertEqual(c.REQUEST['attempt'],67)
        self.assertEqual(c.INVENTORY_PATH,'tool/follow_directional_settle/green_inventory.json')
        self.assertIn('Validate all189 focused cases and natural directional boundaries',workflow)


if __name__=='__main__':unittest.main()
