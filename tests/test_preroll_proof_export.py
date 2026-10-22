import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_check as native


class PrerollProofExportTests(unittest.TestCase):
    def test_all_twenty_three_proof_results_are_finite(self):
        value = {'stage': 'native-follow-readiness-proof', 'status': 'failed',
                 'checks': 23, 'failedTestOrdinals': list(range(1, 24))}
        self.assertEqual(native.report_line(json.dumps(value)), value)

    def test_unknown_ordinal_count_and_private_fields_are_dropped(self):
        value = {'stage': 'native-follow-readiness-proof', 'status': 'failed',
                 'checks': 24, 'failedTestOrdinals': [0, 24, 'private assertion', True, 23],
                 'privateTrace': 'not exportable'}
        self.assertEqual(native.report_line(json.dumps(value)), {
            'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'failedTestOrdinals': [23]})


if __name__ == '__main__':
    unittest.main()
