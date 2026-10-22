import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import follow_clock_interval_proof as c


class ClockIntervalProof(unittest.TestCase):
    def test_exact_delegation_restores_historical_defaults(self):
        old = (c.base.SOURCE_SHA, c.base.EXPECTED_COUNT, c.base.ASSERTION_MARKER)
        def check():
            self.assertEqual(c.base.SOURCE_SHA, c.SOURCE_SHA)
            self.assertEqual(c.base.BASELINE_SHA, c.BASELINE_SHA)
            self.assertEqual(c.base.EXPECTED_COUNT, c.EXPECTED_COUNT)
            self.assertEqual(c.base.ASSERTION_MARKER, c.ASSERTION_MARKER)
            self.assertEqual(c.base.INVENTORY_SHA256, c.INVENTORY_SHA256)
            self.assertEqual(c.base.REQUEST, c.REQUEST)
            return 7
        with patch.object(c.base, 'main', side_effect=check):
            self.assertEqual(c.main(), 7)
        self.assertEqual((c.base.SOURCE_SHA, c.base.EXPECTED_COUNT, c.base.ASSERTION_MARKER), old)

    def test_unfrozen_source_and_unsupported_stage_fail_closed(self):
        for args in (['gate', 'source', 'red'], ['gate', 'native', 'run']):
            with patch.object(c, 'SOURCE_SHA', 'PENDING'), patch.object(sys, 'argv', args), \
                 patch.object(c.base.request, 'context') as context, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(c.main(), 1)
                context.assert_not_called()

    def test_workflow_request_are_exact_and_do_not_publish(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows' / c.WORKFLOW).read_text()
        for value in (c.PARENT, c.MESSAGE, c.SOURCE_SHA, c.SOURCE_REF, c.REQUEST_PATH):
            self.assertIn(value, workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn('if: always()', workflow)
        self.assertNotIn('upload-artifact', workflow)
        self.assertNotIn('publish', workflow)
        self.assertEqual(json.loads((root / c.REQUEST_PATH).read_text()), c.REQUEST)
