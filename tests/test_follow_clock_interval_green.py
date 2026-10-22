import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_clock_interval_green as c


def suites(counts):
    return [dict(path='test/services/synthetic_%d_test.dart' % i, names=['case%d_%d' % (i, j) for j in range(n)])
            for i, n in enumerate(counts)]


class ClockIntervalGreen(unittest.TestCase):
    def test_exact_delegation_restores_previous_gate(self):
        old = (c.previous.SOURCE_SHA, c.previous.inventory, c.previous.previous.previous.RECOVERY_INVENTORY_SHA256)
        def check():
            self.assertEqual(c.previous.SOURCE_SHA, c.SOURCE_SHA)
            self.assertEqual(c.previous.REQUEST, c.REQUEST)
            self.assertIs(c.previous.inventory, c.inventory)
            self.assertEqual(c.previous.previous.previous.RECOVERY_INVENTORY_SHA256,c.RECOVERY_DIGEST)
            return 7
        with patch.object(c.previous, 'main', side_effect=check):
            self.assertEqual(c.main(), 7)
        self.assertEqual((c.previous.SOURCE_SHA, c.previous.inventory,c.previous.previous.previous.RECOVERY_INVENTORY_SHA256), old)

    def test_only_reviewed_legacy_digest_replaced_and_all_cases_required(self):
        timing = c.previous.previous
        old = timing.COMPONENTS
        original = suites((3,45,13,6,3,34,18,17,7,2,3,1,4,5))
        additional = [dict(path='test/services/interval_%d_test.dart' % i, names=['new%d_%d' % (i,j) for j in range(n)]) for i,n in enumerate((6,7))]
        def prior(source):
            self.assertEqual(timing.COMPONENTS, tuple((p,c.CLOCK_DIGEST if p==c.CLOCK_PATH else h,n) for p,h,n in old))
            return list(original)
        with patch.object(c,'ORIGINAL_INVENTORY',side_effect=prior), patch.object(timing,'component_inventory',return_value=additional) as extra:
            self.assertEqual(sum(len(s['names']) for s in c.inventory(Path('/synthetic'))),174)
            extra.assert_called_once_with(Path('/synthetic'),c.INTERVAL_PATH,c.INTERVAL_DIGEST,(6,7))
        self.assertEqual(timing.COMPONENTS,old)
        for invalid in (original[:-1], original+[original[0]]):
            with patch.object(c,'ORIGINAL_INVENTORY',return_value=invalid), patch.object(timing,'component_inventory') as extra:
                with self.assertRaises(timing.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))
                extra.assert_not_called()
        with patch.object(c,'ORIGINAL_INVENTORY',return_value=list(original)), patch.object(timing,'component_inventory',return_value=[original[0],additional[1]]):
            with self.assertRaises(timing.previous.recovery.request.p.GateError): c.inventory(Path('/synthetic'))

    def test_workflow_is_fixed_readonly_full_source_and_cleanup(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows'/c.WORKFLOW).read_text()
        for value in (c.PARENT,c.MESSAGE,c.SOURCE_SHA,c.SOURCE_REF,c.REQUEST_PATH): self.assertIn(value,workflow)
        for value in ('contents: read','source focused','source validate_source','if: always()','source cleanup'): self.assertIn(value,workflow)
        for value in ('upload-artifact','source native','source package'): self.assertNotIn(value,workflow)
        self.assertEqual(json.loads((root/c.REQUEST_PATH).read_text()),c.REQUEST)
