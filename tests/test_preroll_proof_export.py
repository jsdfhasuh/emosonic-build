import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_native_check as native


class PrerollProofExportTests(unittest.TestCase):
    def test_all_thirty_five_proof_results_are_finite(self):
        value = {'stage': 'native-follow-readiness-proof', 'status': 'failed',
                 'checks': 35, 'failedTestOrdinals': list(range(1, 36))}
        self.assertEqual(native.report_line(json.dumps(value)), value)

    def test_noninteger_proof_counts_are_not_accepted(self):
        for count in (True, '35', 35.0, float('nan')):
            value = {'stage':'native-follow-readiness-proof', 'status':'passed', 'checks':count}
            self.assertEqual(native.report_line(json.dumps(value)), {'stage':'native-follow-readiness-proof','status':'passed'})

    def test_unknown_ordinal_count_and_private_fields_are_dropped(self):
        value = {'stage': 'native-follow-readiness-proof', 'status': 'failed',
                 'checks': 41, 'failedTestOrdinals': [0, 41, 'private assertion', True, 35],
                 'privateTrace': 'not exportable'}
        self.assertEqual(native.report_line(json.dumps(value)), {
            'stage': 'native-follow-readiness-proof', 'status': 'failed',
            'failedTestOrdinals': [35]})


if __name__ == '__main__':
    unittest.main()
