import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import follow_timing_green as gate


class TimingGreenTests(unittest.TestCase):
    def materialize(self, source, mutate=None):
        fixture = source/'test/services/synthetic_component_test.dart'
        fixture.parent.mkdir(parents=True)
        fixture.write_text('Synthetic fixture, no private source.')
        suite = dict(path='test/services/synthetic_component_test.dart', sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(), names=['first', 'second'])
        if mutate: mutate(suite)
        path = source/'tool/component/inventory.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'suites':[suite]}))
        return str(path.relative_to(source)), hashlib.sha256(path.read_bytes()).hexdigest(), (2,)

    def test_exact_inventory_and_fixture_hash_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=self.materialize(root)
            self.assertEqual(len(gate.component_inventory(root,*spec)[0]['names']),2)
            (root/'test/services/synthetic_component_test.dart').write_text('Changed')
            with self.assertRaises(gate.previous.recovery.request.p.GateError):gate.component_inventory(root,*spec)

    def test_rejects_bad_name_count_extra_keys_ordinal_and_duplicate_names(self):
        for mutate in (lambda s:s['names'].pop(),lambda s:s.update(extra=True),lambda s:s.update(causalOrdinal=1),lambda s:s.update(names=['first','first'])):
            with self.subTest(mutate=mutate),tempfile.TemporaryDirectory() as d:
                root=Path(d);spec=self.materialize(root,mutate)
                with self.assertRaises(gate.previous.recovery.request.p.GateError):gate.component_inventory(root,*spec)

    def test_missing_pins_fail_closed(self):
        with self.assertRaises(gate.previous.recovery.request.p.GateError):gate.component_inventory(Path('/owned'),'irrelevant','PENDING',())

    def test_preserves_previous_104_and_rejects_overlap(self):
        original=[dict(path=f'test/services/original_{i}_test.dart',names=['x']*n) for i,n in enumerate((3,45,13,6,3,34))]
        addition=dict(path='test/services/new_test.dart',names=['one','two'])
        with patch.object(gate,'ORIGINAL_INVENTORY',side_effect=lambda _:list(original)),patch.object(gate,'COMPONENTS',[('p','d',(2,))]),patch.object(gate,'component_inventory',return_value=[addition]):
            self.assertEqual(len(gate.inventory(Path('/owned'))),7)
            with patch.object(gate,'component_inventory',return_value=[original[0]]):
                with self.assertRaises(gate.previous.recovery.request.p.GateError):gate.inventory(Path('/owned'))
        original[0]['names'].pop()
        with patch.object(gate,'ORIGINAL_INVENTORY',return_value=original):
            with self.assertRaises(gate.previous.recovery.request.p.GateError):gate.inventory(Path('/owned'))

    def test_delegates_strict_full_gate_without_swallowing_return_code(self):
        original=gate.previous.inventory
        with patch.object(gate.previous,'main',return_value=7) as main:
            self.assertEqual(gate.main(),7);main.assert_called_once()
        self.assertIs(gate.previous.inventory,original)

    def test_workflow_keeps_focused_full_and_cleanup(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/follow-timing-green.yml').read_text()
        self.assertLess(text.index(' source focused'),text.index(' source validate_source'))
        self.assertIn('if: always()',text)
        self.assertIn('github.event.before ==',text)
        self.assertIn('persist-credentials: false',text)
        for forbidden in ('continue-on-error','RELEASE_WRITE_TOKEN','macos-'):
            self.assertNotIn(forbidden,text)
