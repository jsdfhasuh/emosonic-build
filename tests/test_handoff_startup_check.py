import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import handoff_startup_check as c


class StartupRequestTests(unittest.TestCase):
    def test_frozen_request(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / c.REQUEST_PATH).read_text()), c.REQUEST)
        self.assertEqual(c.REQUEST['source_sha'], '01967c853a4e6020097e9a2da61f9785b470ff7d')
        self.assertEqual(c.BASELINE_SHA, '440d9345be2976fb21c3515b12078a7baccf4daa')
        workflow = (root / '.github/workflows' / c.WORKFLOW).read_text()
        self.assertIn(c.PARENT, workflow)
        self.assertIn(c.MESSAGE, workflow)
        self.assertNotIn('native-macos-server:', workflow)
        self.assertNotIn('publish', workflow)

    def test_forbidden_categories_and_stages(self):
        for args in [('native', 'build'), ('source', 'android'), ('source', 'publish'), ('other', 'red')]:
            with patch.object(sys, 'argv', ['wrapper', *args]), patch.object(c.request, 'main') as run:
                self.assertEqual(c.main(), 1)
                run.assert_not_called()

    def test_regression_constants_are_scoped(self):
        original = c.regression.BASELINE_SHA
        def invoke(stage):
            self.assertEqual(stage, 'red')
            self.assertEqual(c.regression.BASELINE_SHA, c.BASELINE_SHA)
            self.assertEqual(c.regression.TEST_NAME, c.TEST_NAME)
            self.assertEqual(c.regression.ASSERTION_MARKER, c.ASSERTION_MARKER)
            self.assertEqual(c.request.SOURCE_SHA, c.SOURCE_SHA)
        with patch.object(sys, 'argv', ['wrapper', 'regression', 'red']), patch.object(c.regression, 'regression', side_effect=invoke):
            self.assertEqual(c.main(), 0)
        self.assertEqual(c.regression.BASELINE_SHA, original)

    def test_source_validation_scoped(self):
        original = c.request.SOURCE_SHA
        def invoke():
            self.assertEqual(sys.argv[1:], ['validate_source'])
            self.assertEqual(c.request.SOURCE_SHA, c.SOURCE_SHA)
            return 0
        with patch.object(sys, 'argv', ['wrapper', 'source', 'validate_source']), patch.object(c.request, 'main', side_effect=invoke):
            self.assertEqual(c.main(), 0)
        self.assertEqual(c.request.SOURCE_SHA, original)
