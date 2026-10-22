from pathlib import Path
import unittest
from unittest.mock import patch
import follow_restore_green as gate


class PostRestoreGreenTests(unittest.TestCase):
    def originals(self):
        return [dict(path=f'test/services/original_{i}_test.dart', names=['x'] * n)
                for i, n in enumerate((3,45,13,6,3,34,18,17,7,2,3,1))]

    def test_preserves_all_152_and_requires_additional_unique_fixture(self):
        original = self.originals()
        added = dict(path='test/services/new_test.dart', names=['first','second'])
        with patch.object(gate, 'ORIGINAL_INVENTORY', side_effect=lambda _: list(original)), \
             patch.object(gate, 'COMPONENTS', [('p','d',(2,))]), \
             patch.object(gate.previous, 'component_inventory', return_value=[added]):
            self.assertEqual(sum(len(s['names']) for s in gate.inventory(Path('/owned'))),154)
            with patch.object(gate.previous, 'component_inventory', return_value=[original[0]]):
                with self.assertRaises(gate.previous.previous.recovery.request.p.GateError):
                    gate.inventory(Path('/owned'))
        original[0]['names'].pop()
        with patch.object(gate, 'ORIGINAL_INVENTORY', return_value=original):
            with self.assertRaises(gate.previous.previous.recovery.request.p.GateError):
                gate.inventory(Path('/owned'))

    def test_missing_component_pins_fail_closed(self):
        with patch.object(gate,'ORIGINAL_INVENTORY',return_value=self.originals()), \
             patch.object(gate,'COMPONENTS',[('p','PENDING',())]):
            with self.assertRaises(gate.previous.previous.recovery.request.p.GateError):
                gate.inventory(Path('/owned'))

    def test_delegates_original_fatal_full_gate_and_restores_globals(self):
        original = gate.previous.inventory
        def main():
            self.assertIs(gate.previous.inventory, gate.inventory)
            self.assertEqual(gate.previous.REQUEST, gate.REQUEST)
            return 9
        with patch.object(gate.previous,'main',side_effect=main):
            self.assertEqual(gate.main(),9)
        self.assertIs(gate.previous.inventory,original)

    def test_workflow_remains_focused_then_full_and_always_cleanup(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/follow-post-restore-green.yml').read_text()
        self.assertLess(text.index(' source focused'),text.index(' source validate_source'))
        for required in ('if: always()','github.event.before ==','persist-credentials: false'):
            self.assertIn(required,text)
        for forbidden in ('continue-on-error','RELEASE_WRITE_TOKEN','macos-','upload-artifact'):
            self.assertNotIn(forbidden,text)


if __name__ == '__main__':
    unittest.main()
